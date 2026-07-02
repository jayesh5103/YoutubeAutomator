import sqlite3
import logging
import json
from datetime import datetime
from database import DB_PATH

logger = logging.getLogger("YoutubeAutomator")

HOOK_STYLES = ['question', 'bold_claim', 'number_stat', 'challenge', 'story']

def classify_hook_style(hook_text: str) -> str:
    """
    Heuristically classifies hook text into one of the 5 styles:
    question, bold_claim, number_stat, challenge, story.
    """
    text_lower = hook_text.lower()
    
    # Heuristics
    if "?" in text_lower or any(q in text_lower for q in ["kya", "kyun", "kaise", "how", "why"]):
        return 'question'
    if any(n in text_lower for n in ["%", "90%", "80%", "10", "5", "1"]):
        return 'number_stat'
    if any(c in text_lower for c in ["challenge", "try", "solv", "dhoond", "code karo"]):
        return 'challenge'
    if any(s in text_lower for s in ["socho", "bhai", "yaar", "story", "struggle", "interview", "fail"]):
        return 'story'
    return 'bold_claim' # default fallback

def get_best_hook_style() -> tuple[str, float]:
    """
    Returns (best_hook_style, confidence) based on historical retention data.
    Defaults to a random style if insufficient data.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value, confidence FROM script_preferences WHERE key = 'best_hook_style'")
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return row[0], float(row[1])
    return random_hook_style(), 0.0

def random_hook_style() -> str:
    import random
    return random.choice(HOOK_STYLES)

def record_script_pattern(video_id: str, hook_text: str, hook_style: str, avg_beat_duration: float, beat_count: int):
    """
    Logs script pattern data during video generation.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR REPLACE INTO script_patterns (video_id, hook_text, hook_style, avg_beat_duration, beat_count, retention_rate, recorded_at)
    VALUES (?, ?, ?, ?, ?, NULL, ?)
    ''', (video_id, hook_text, hook_style, avg_beat_duration, beat_count, datetime.now()))
    conn.commit()
    conn.close()
    logger.info(f"[Script Intelligence] Recorded script pattern for video {video_id} (Hook: '{hook_style}', Pacing: {avg_beat_duration:.1f}s)")

def update_script_preferences():
    """
    Aggregates script data to find best hook style, optimal pacing range, and pacing flags.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Update best hook style
    cursor.execute('''
    SELECT hook_style, AVG(retention_rate) as avg_ret, COUNT(*) as sample_count
    FROM script_patterns
    WHERE retention_rate IS NOT NULL
    GROUP BY hook_style
    ''')
    rows = cursor.fetchall()
    
    best_style = 'bold_claim'
    best_ret = -1.0
    total_samples = 0
    
    for style, avg_ret, sample_count in rows:
        total_samples += sample_count
        if avg_ret > best_ret:
            best_ret = avg_ret
            best_style = style
            
    if total_samples >= 5:
        confidence = min(1.0, total_samples / 15.0)
        cursor.execute('''
        INSERT OR REPLACE INTO script_preferences (key, value, confidence, last_updated)
        VALUES ('best_hook_style', ?, ?, ?)
        ''', (best_style, confidence, datetime.now()))
        
    # 2. Update optimal beat duration range based on top 25% performing videos
    cursor.execute("SELECT COUNT(*) FROM script_patterns WHERE retention_rate IS NOT NULL")
    count_row = cursor.fetchone()
    total_valid = count_row[0] if count_row else 0
    
    if total_valid >= 5:
        top_25_count = max(1, (total_valid + 3) // 4)
        cursor.execute(f'''
        SELECT avg_beat_duration FROM script_patterns
        WHERE retention_rate IS NOT NULL
        ORDER BY retention_rate DESC
        LIMIT {top_25_count}
        ''')
        durations = [r[0] for r in cursor.fetchall()]
        
        if durations:
            opt_min = min(durations)
            opt_max = max(durations)
            confidence = min(1.0, total_valid / 15.0)
            
            cursor.execute('''
            INSERT OR REPLACE INTO script_preferences (key, value, confidence, last_updated)
            VALUES ('optimal_beat_duration_min', ?, ?, ?)
            ''', (str(round(opt_min, 1)), confidence, datetime.now()))
            
            cursor.execute('''
            INSERT OR REPLACE INTO script_preferences (key, value, confidence, last_updated)
            VALUES ('optimal_beat_duration_max', ?, ?, ?)
            ''', (str(round(opt_max, 1)), confidence, datetime.now()))

        # 3. Update pacing preference: check if < 5s beats perform better
        cursor.execute('''
        SELECT AVG(retention_rate) FROM script_patterns WHERE avg_beat_duration < 5.0 AND retention_rate IS NOT NULL
        ''')
        short_ret = cursor.fetchone()[0] or 0.0
        
        cursor.execute('''
        SELECT AVG(retention_rate) FROM script_patterns WHERE avg_beat_duration >= 5.0 AND retention_rate IS NOT NULL
        ''')
        long_ret = cursor.fetchone()[0] or 0.0
        
        pref = 'normal'
        if short_ret > long_ret and short_ret > 0:
            pref = 'short'
            
        cursor.execute('''
        INSERT OR REPLACE INTO script_preferences (key, value, confidence, last_updated)
        VALUES ('pacing_preference', ?, ?, ?)
        ''', (pref, min(1.0, total_valid / 15.0), datetime.now()))

    conn.commit()
    conn.close()
    logger.info("[Script Intelligence] Recomputed script preferences.")

def build_script_context_block() -> str:
    """
    Builds the LEARNING CONTEXT system instruction string dynamically from preferences.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get values
    cursor.execute("SELECT key, value, confidence FROM script_preferences")
    prefs = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}
    
    # Get top keywords
    cursor.execute("SELECT keyword FROM keyword_weights WHERE avg_score > 60 ORDER BY avg_score DESC LIMIT 3")
    keywords = [row[0] for row in cursor.fetchall()]
    
    # Get bad keywords
    cursor.execute("SELECT keyword FROM keyword_weights WHERE avg_score < 40 ORDER BY avg_score ASC LIMIT 2")
    bad_keywords = [row[0] for row in cursor.fetchall()]
    
    # Get total video sample count
    cursor.execute("SELECT COUNT(*) FROM script_patterns WHERE retention_rate IS NOT NULL")
    total_videos = cursor.fetchone()[0]
    
    conn.close()
    
    # Defaults
    hook_style = prefs.get('best_hook_style', ('bold_claim', 0.0))
    # We will format retention as a clean percentage. Say, retention_rate is 0.0 - 1.0 (or 0 - 100). We will display it out of 100.
    hook_retention_pct = "N/A"
    
    # Get hook retention if we have history
    if hook_style[1] > 0:
        conn = sqlite3.connect(DB_PATH)
        c2 = conn.cursor()
        c2.execute("SELECT AVG(retention_rate) FROM script_patterns WHERE hook_style = ?", (hook_style[0],))
        r_val = c2.fetchone()[0]
        if r_val is not None:
            hook_retention_pct = f"{round(r_val * 100, 1) if r_val <= 1.0 else round(r_val, 1)}"
        conn.close()
        
    opt_min = prefs.get('optimal_beat_duration_min', ('4.0', 0.0))[0]
    opt_max = prefs.get('optimal_beat_duration_max', ('6.0', 0.0))[0]
    pacing_pref = prefs.get('pacing_preference', ('normal', 0.0))[0]
    
    kw_str = ", ".join(keywords) if keywords else "binary search, recursion, hashmap"
    bad_kw_str = ", ".join(bad_keywords) if bad_keywords else "unstructured rambling, bubble sort"
    
    # Only inject if we have some minimal data
    if total_videos < 5:
        return ""
        
    block = f"""
[LEARNING CONTEXT — DO NOT IGNORE]
Based on {total_videos} past videos:
- Best performing hook style: {hook_style[0]} (avg retention: {hook_retention_pct}%)
- Optimal beat duration: {opt_min}–{opt_max} seconds (pacing bias: {pacing_pref})
- Top performing keywords this month: [{kw_str}]
- Avoid these underperforming patterns: [{bad_kw_str}]
Write this script using the above learned preferences.
"""
    return block
