import sqlite3
import json
import logging
import random
from datetime import datetime
from database import DB_PATH

logger = logging.getLogger("YoutubeAutomator")

# Helper to classify title patterns
def analyze_title_patterns(title: str) -> dict:
    title_lower = title.lower()
    words = title_lower.split()
    
    starts_with_number = 1 if words and words[0][0].isdigit() else 0
    contains_question = 1 if "?" in title_lower or any(q in title_lower for q in ["kya", "kyun", "kaise", "how", "why"]) else 0
    contains_hindi = 1 if any(h in title_lower for h in ["bhai", "samjho", "kaise", "kya", "mein", "aur", "farak", "dabba", "suno", "dekho"]) else 0
    contains_emoji = 1 if any(char in title for char in ["🚀", "🔥", "💬", "🧠", "💡", "👑"]) else 0
    
    return {
        "starts_with_number": starts_with_number,
        "contains_question": contains_question,
        "contains_hindi_word": contains_hindi,
        "contains_emoji": contains_emoji,
        "word_count": len(words)
    }

def record_upload_details(video_id: str, upload_hour: int, upload_day_of_week: int):
    """
    Saves initial upload time slot mapping.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR REPLACE INTO upload_performance 
    (video_id, upload_hour, upload_day_of_week, views_6hr, views_24hr, views_48hr, ctr, avg_view_duration, recorded_at)
    VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL, ?)
    ''', (video_id, upload_hour, upload_day_of_week, datetime.now()))
    conn.commit()
    conn.close()
    logger.info(f"[Upload Intelligence] Recorded upload schedule for video {video_id} at Day {upload_day_of_week}, Hour {upload_hour}")

def record_thumbnail_metadata(video_id: str, metadata: dict):
    """
    Saves initial thumbnail attributes.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR REPLACE INTO thumbnail_performance 
    (video_id, has_face, primary_color, has_code_snippet, has_large_number, has_emoji, ctr, impressions)
    VALUES (?, ?, ?, ?, ?, ?, NULL, NULL)
    ''', (video_id, metadata.get('has_face', 0), metadata.get('primary_color', '#0d1117'),
          metadata.get('has_code_snippet', 0), metadata.get('has_large_number', 0),
          metadata.get('has_emoji', 0)))
    conn.commit()
    conn.close()
    logger.info(f"[Upload Intelligence] Recorded thumbnail properties for video {video_id}")

def get_best_upload_slot() -> tuple[int, int]:
    """
    Selects one of the top 3 best time slots (hour, day_of_week), randomly weighted.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Baseline slots (12 PM, 3 PM, 6 PM daily)
    baseline_slots = []
    for day in range(7):
        for hr in [12, 15, 18]:
            baseline_slots.append((hr, day))
            
    # Check if we have enough historical data points
    cursor.execute("SELECT COUNT(*) FROM upload_performance WHERE views_24hr IS NOT NULL")
    history_count = cursor.fetchone()[0]
    
    if history_count < 20:
        conn.close()
        # Cold start fallback: pick a random baseline slot
        slot = random.choice(baseline_slots)
        logger.info(f"[Upload Intelligence] Cold start (data points: {history_count}/20). Fallback upload slot: Day {slot[1]}, Hour {slot[0]}")
        return slot
        
    # Query performance of all slots
    cursor.execute('''
    SELECT upload_hour, upload_day_of_week, AVG(views_24hr) as score
    FROM upload_performance
    WHERE views_24hr IS NOT NULL
    GROUP BY upload_hour, upload_day_of_week
    ''')
    db_slots = { (row[0], row[1]): float(row[2]) for row in cursor.fetchall() }
    conn.close()
    
    # Calculate scores for all 168 cells
    all_slots_scores = []
    for day in range(7):
        for hr in range(24):
            key = (hr, day)
            if key in db_slots:
                score = db_slots[key]
            else:
                # Fallback to general hour average or simple low baseline
                score = 10.0
            all_slots_scores.append((key, score))
            
    # Sort and take top 3
    all_slots_scores.sort(key=lambda x: x[1], reverse=True)
    top_3 = all_slots_scores[:3]
    
    # Randomly weighted choice
    slots, scores = zip(*top_3)
    total_score = sum(scores)
    
    if total_score > 0:
        weights = [s / total_score for s in scores]
        selected_slot = random.choices(slots, weights=weights, k=1)[0]
    else:
        selected_slot = random.choice(slots)
        
    logger.info(f"[Upload Intelligence] Selected upload slot: Day {selected_slot[1]}, Hour {selected_slot[0]} (Top 3 scores: {scores})")
    return selected_slot

def get_title_template() -> str:
    """
    Returns the optimized title instruction template.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM upload_preferences WHERE key = 'best_title_template'")
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return row[0]
    return "Master [Topic Keyword] | [Catchy Hinglish Phrase] #Shorts #DSA"

def update_upload_preferences():
    """
    Recomputes upload hour/day preferences, thumbnail priorities, and title guidelines.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Best hour & day of week
    cursor.execute('''
    SELECT upload_hour, AVG(views_24hr) as score, COUNT(*) as cnt
    FROM upload_performance WHERE views_24hr IS NOT NULL GROUP BY upload_hour ORDER BY score DESC LIMIT 1
    ''')
    best_hr_row = cursor.fetchone()
    if best_hr_row:
        cursor.execute("INSERT OR REPLACE INTO upload_preferences (key, value, confidence, last_updated) VALUES ('best_upload_hour', ?, ?, ?)",
                       (str(best_hr_row[0]), min(1.0, best_hr_row[2]/10.0), datetime.now()))
                       
    cursor.execute('''
    SELECT upload_day_of_week, AVG(views_24hr) as score, COUNT(*) as cnt
    FROM upload_performance WHERE views_24hr IS NOT NULL GROUP BY upload_day_of_week ORDER BY score DESC LIMIT 1
    ''')
    best_day_row = cursor.fetchone()
    if best_day_row:
        cursor.execute("INSERT OR REPLACE INTO upload_preferences (key, value, confidence, last_updated) VALUES ('best_upload_day', ?, ?, ?)",
                       (str(best_day_row[0]), min(1.0, best_day_row[2]/10.0), datetime.now()))

    # 2. Thumbnail intelligence correlations
    cursor.execute("SELECT has_face, primary_color, has_code_snippet, has_large_number, has_emoji, ctr FROM thumbnail_performance WHERE ctr IS NOT NULL")
    rows = cursor.fetchall()
    
    if len(rows) >= 5:
        thumbnail_attrs = ['has_face', 'has_code_snippet', 'has_large_number', 'has_emoji']
        attr_ctr = {attr: [] for attr in thumbnail_attrs}
        
        for r in rows:
            face, col, code, num, emoji, ctr = r
            # Map values to their positions
            vals = [face, code, num, emoji]
            for idx, val in enumerate(vals):
                if val == 1:
                    attr_ctr[thumbnail_attrs[idx]].append(ctr)
                    
        # Average CTR where present
        attr_scores = []
        for attr, ctrs in attr_ctr.items():
            avg_ctr = sum(ctrs) / len(ctrs) if ctrs else 0.0
            attr_scores.append((attr, avg_ctr))
            
        attr_scores.sort(key=lambda x: x[1], reverse=True)
        ranked_list = [x[0] for x in attr_scores]
        
        cursor.execute("INSERT OR REPLACE INTO upload_preferences (key, value, confidence, last_updated) VALUES ('thumbnail_preferences', ?, ?, ?)",
                       (json.dumps(ranked_list), min(1.0, len(rows)/15.0), datetime.now()))

    # 3. Title pattern correlations
    cursor.execute("SELECT v.title, u.ctr FROM upload_performance u JOIN videos v ON u.video_id = v.video_id WHERE u.ctr IS NOT NULL")
    title_rows = cursor.fetchall()
    
    if len(title_rows) >= 5:
        pattern_data = {
            "starts_with_number": [],
            "contains_question": [],
            "contains_hindi_word": [],
            "contains_emoji": []
        }
        word_counts = []
        
        for title, ctr in title_rows:
            patterns = analyze_title_patterns(title)
            word_counts.append((patterns['word_count'], ctr))
            for k in pattern_data.keys():
                if patterns[k] == 1:
                    pattern_data[k].append(ctr)
                    
        # Compute guidelines
        guidelines = []
        for pat, ctrs in pattern_data.items():
            if ctrs:
                avg_pat_ctr = sum(ctrs) / len(ctrs)
                # Compute background CTR without this pattern
                other_ctrs = [ctr for t, ctr in title_rows if analyze_title_patterns(t)[pat] == 0]
                avg_other_ctr = sum(other_ctrs) / len(other_ctrs) if other_ctrs else 0.0
                
                if avg_pat_ctr > avg_other_ctr:
                    guidelines.append(f"prefer {pat.replace('_', ' ')}")
                    
        # Compute optimal word count based on top 20% performing titles
        word_counts.sort(key=lambda x: x[1], reverse=True)
        top_wc = [w[0] for w in word_counts[:max(1, len(word_counts)//5)]]
        opt_wc = int(sum(top_wc) / len(top_wc)) if top_wc else 8
        guidelines.append(f"aim for exactly {opt_wc} words")
        
        template_instructions = "Title structure preferences: " + ", ".join(guidelines)
        cursor.execute("INSERT OR REPLACE INTO upload_preferences (key, value, confidence, last_updated) VALUES ('best_title_template', ?, ?, ?)",
                       (template_instructions, min(1.0, len(title_rows)/15.0), datetime.now()))

    conn.commit()
    conn.close()
    logger.info("[Upload Intelligence] Recomputed upload preferences.")
