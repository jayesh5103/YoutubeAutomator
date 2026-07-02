import sqlite3
import os
import logging

logger = logging.getLogger("YoutubeAutomator")

# Database Path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "automation.db")

def run_migration():
    """
    Creates all the required tables for the learning engine if they do not exist.
    """
    logger.info("Running database migrations for Self-Learning Intelligence Layer...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 1. Module 1: Topic Intelligence tables
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS topic_performance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword TEXT,
        niche TEXT,
        algorithm_category TEXT,
        video_id TEXT,
        performance_score REAL,
        views INTEGER,
        likes INTEGER,
        watch_time_minutes REAL,
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS keyword_weights (
        keyword TEXT PRIMARY KEY,
        avg_score REAL,
        sample_count INTEGER,
        last_updated TIMESTAMP
    );
    ''')

    # 2. Module 2: Script Intelligence tables
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS script_patterns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT,
        hook_text TEXT,
        hook_style TEXT,       -- question/bold_claim/number_stat/challenge/story
        avg_beat_duration REAL,
        beat_count INTEGER,
        retention_rate REAL,   -- filled after 48hr YouTube Analytics sync
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS script_preferences (
        key TEXT PRIMARY KEY,  -- e.g. 'best_hook_style', 'optimal_beat_duration_min'
        value TEXT,
        confidence REAL,       -- 0.0–1.0, based on sample_count
        last_updated TIMESTAMP
    );
    ''')

    # 3. Module 3: Visual Intelligence tables
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS beat_performance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT,
        beat_index INTEGER,
        visual_type TEXT,
        beat_start_second REAL,
        beat_end_second REAL,
        avg_retention_in_window REAL,  -- pulled from YouTube Analytics
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS visual_preferences (
        algorithm_category TEXT PRIMARY KEY,
        best_visual_sequence TEXT,   -- JSON array, e.g. ["show_array","show_pointers","show_code"]
        confidence REAL,
        sample_count INTEGER,
        last_updated TIMESTAMP
    );
    ''')

    # 4. Module 4: Upload Intelligence tables
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS upload_performance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT,
        upload_hour INTEGER,
        upload_day_of_week INTEGER,
        views_6hr INTEGER,
        views_24hr INTEGER,
        views_48hr INTEGER,
        ctr REAL,               -- from YouTube Analytics
        avg_view_duration REAL, -- from YouTube Analytics
        recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS thumbnail_performance (
        video_id TEXT PRIMARY KEY,
        has_face INTEGER,         -- 0/1
        primary_color TEXT,
        has_code_snippet INTEGER, -- 0/1
        has_large_number INTEGER, -- 0/1
        has_emoji INTEGER,        -- 0/1
        ctr REAL,
        impressions INTEGER
    );
    ''')

    cursor.execute('''
    CREATE TABLE IF NOT EXISTS upload_preferences (
        key TEXT PRIMARY KEY,   -- e.g. 'best_upload_hour', 'best_title_template'
        value TEXT,
        confidence REAL,
        last_updated TIMESTAMP
    );
    ''')

    # 5. Module 5: Analytics Sync Log
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS analytics_sync_log (
        video_id TEXT PRIMARY KEY,
        last_synced_at TIMESTAMP,
        sync_status TEXT,   -- 'pending' / 'synced' / 'failed'
        retry_count INTEGER DEFAULT 0
    );
    ''')

    conn.commit()
    conn.close()
    logger.info("Migrations completed successfully.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
