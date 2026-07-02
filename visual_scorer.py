import sqlite3
import json
import logging
from datetime import datetime
from database import DB_PATH

logger = logging.getLogger("YoutubeAutomator")

def save_beat_metadata(video_id: str, storyboard_beats: list):
    """
    Saves the initial beat parameters and durations to the database before upload.
    storyboard_beats: list of dicts, each with {"text": str, "visual_action": str, "start_sec": float, "end_sec": float}
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for i, beat in enumerate(storyboard_beats):
        visual_type = beat.get("visual_action", "text_only")
        start_sec = beat.get("start_sec", 0.0)
        end_sec = beat.get("end_sec", 0.0)
        
        cursor.execute('''
        INSERT OR REPLACE INTO beat_performance 
        (video_id, beat_index, visual_type, beat_start_second, beat_end_second, avg_retention_in_window, recorded_at)
        VALUES (?, ?, ?, ?, ?, NULL, ?)
        ''', (video_id, i, visual_type, start_sec, end_sec, datetime.now()))
        
    conn.commit()
    conn.close()
    logger.info(f"[Visual Intelligence] Saved metadata for {len(storyboard_beats)} storyboard beats under video {video_id}")

def suggest_visual_sequence(algorithm_category: str) -> list[str]:
    """
    Returns the historically best-performing visual sequence for a category.
    Returns None if confidence is too low (< 0.4).
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    SELECT best_visual_sequence, confidence FROM visual_preferences
    WHERE algorithm_category = ?
    ''', (algorithm_category,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        seq_json, confidence = row
        if confidence >= 0.4:
            try:
                return json.loads(seq_json)
            except Exception as e:
                logger.error(f"[Visual Intelligence] Error parsing sequence JSON: {e}")
    return None

def update_visual_preferences():
    """
    Identifies the highest-retaining video in each category and saves its visual sequence.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Find all categories and their top-performing video ID based on average beat retention
    cursor.execute('''
    SELECT tp.algorithm_category, bp.video_id, AVG(bp.avg_retention_in_window) as avg_ret
    FROM beat_performance bp
    JOIN topic_performance tp ON bp.video_id = tp.video_id
    WHERE bp.avg_retention_in_window IS NOT NULL
    GROUP BY tp.algorithm_category, bp.video_id
    ''')
    rows = cursor.fetchall()
    
    # Organize by category to find the best video
    category_best = {} # cat -> (video_id, avg_ret)
    category_samples = {} # cat -> count of unique videos
    
    for cat, vid, avg_ret in rows:
        category_samples[cat] = category_samples.get(cat, 0) + 1
        
        if cat not in category_best or avg_ret > category_best[cat][1]:
            category_best[cat] = (vid, avg_ret)
            
    # 2. For each category, get the sequence of the best video
    for cat, (best_vid, max_ret) in category_best.items():
        cursor.execute('''
        SELECT visual_type FROM beat_performance
        WHERE video_id = ?
        ORDER BY beat_index ASC
        ''', (best_vid,))
        sequence = [row[0] for row in cursor.fetchall()]
        
        if sequence:
            seq_json = json.dumps(sequence)
            sample_count = category_samples[cat]
            confidence = min(1.0, sample_count / 5.0)
            
            cursor.execute('''
            INSERT OR REPLACE INTO visual_preferences 
            (algorithm_category, best_visual_sequence, confidence, sample_count, last_updated)
            VALUES (?, ?, ?, ?, ?)
            ''', (cat, seq_json, confidence, sample_count, datetime.now()))
            
    conn.commit()
    conn.close()
    logger.info(f"[Visual Intelligence] Recomputed visual preferences for {len(category_best)} categories.")
