import sqlite3
from datetime import datetime
import os

# Use absolute path for DB to avoid GUI/Engine sync issues if run from different folders
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "automation.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Videos table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS videos (
        video_id TEXT PRIMARY KEY,
        title TEXT,
        topic TEXT,
        niche TEXT,
        upload_time DATETIME,
        status TEXT,
        views INTEGER DEFAULT 0,
        likes INTEGER DEFAULT 0,
        comments INTEGER DEFAULT 0,
        retention_score FLOAT DEFAULT 0.0
    )
    ''')
    
    # Trends table to avoid duplicates
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS trends (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT UNIQUE,
        score FLOAT,
        timestamp DATETIME,
        used BOOLEAN DEFAULT 0
    )
    ''')

    # System configuration / Shared State (for cross-process cooldowns)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS system_config (
        key TEXT PRIMARY KEY,
        value TEXT,
        updated_at DATETIME
    )
    ''')

    # Video pipeline table for human-in-the-loop workflow
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS video_pipeline (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        topic           TEXT NOT NULL,
        niche           TEXT,
        status          TEXT NOT NULL DEFAULT 'DRAFT',
        script_json     TEXT,
        script_version  INTEGER DEFAULT 1,
        video_path      TEXT,
        thumbnail_path  TEXT,
        title           TEXT,
        description     TEXT,
        tags            TEXT,
        rejection_reason TEXT,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        approved_at     TIMESTAMP,
        uploaded_at     TIMESTAMP,
        youtube_video_id TEXT
    )
    ''')

    # Script edit history table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS script_edit_history (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        pipeline_id  INTEGER NOT NULL REFERENCES video_pipeline(id),
        version      INTEGER NOT NULL,
        script_json  TEXT NOT NULL,
        edited_by    TEXT DEFAULT 'user',
        edit_note    TEXT,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Beat versions table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS beat_versions (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        pipeline_id     INTEGER NOT NULL REFERENCES video_pipeline(id),
        beat_index      INTEGER NOT NULL,
        beat_json       TEXT NOT NULL,
        clip_path       TEXT,
        audio_path      TEXT,
        duration_seconds REAL,
        is_current      INTEGER DEFAULT 1,
        render_status   TEXT DEFAULT 'PENDING',
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Timeline edits log table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS timeline_edits (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        pipeline_id   INTEGER NOT NULL REFERENCES video_pipeline(id),
        edit_type     TEXT NOT NULL,
        edit_payload  TEXT NOT NULL,
        applied_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Pipeline log table
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS pipeline_log (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        pipeline_id  INTEGER REFERENCES video_pipeline(id),
        stage        TEXT NOT NULL,
        level        TEXT DEFAULT 'INFO',
        message      TEXT NOT NULL,
        duration_ms  INTEGER,
        created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()

def log_video(video_id, title, topic, niche, status="uploaded"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Use OR IGNORE to prevent overwriting views/likes if row exists
    cursor.execute('''
    INSERT OR IGNORE INTO videos (video_id, title, topic, niche, upload_time, status)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (video_id, title, topic, niche, datetime.now(), status))
    
    # Update title/topic/niche/status just in case it's a re-log, but preserve views/likes
    cursor.execute('''
    UPDATE videos SET title = ?, topic = ?, niche = ?, status = ?
    WHERE video_id = ?
    ''', (title, topic, niche, status, video_id))
    
    conn.commit()
    conn.close()

def update_video_stats(video_id, views, likes, comments):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    UPDATE videos SET views = ?, likes = ?, comments = ?
    WHERE video_id = ?
    ''', (views, likes, comments, video_id))
    conn.commit()
    conn.close()

def get_todays_video_count():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Count videos uploaded today (using date(upload_time) = date('now', 'localtime'))
    cursor.execute('''
    SELECT COUNT(*) FROM videos
    WHERE date(upload_time) = date('now', 'localtime')
    ''')
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 0

def get_best_performing_niches():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    SELECT niche, SUM(views) as total_views 
    FROM videos 
    GROUP BY niche 
    ORDER BY total_views DESC
    ''')
    results = cursor.fetchall()
    conn.close()
    return results

def get_viral_score_boost(topic):
    """
    Returns a score boost for a topic based on past performance of similar topics.
    This is the Analytics Learning Engine - it reads its own history to evolve.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Find any videos with similar topics that performed well
    cursor.execute('''
    SELECT AVG(views) as avg_views
    FROM videos
    WHERE topic LIKE ?
    ''', (f"%{topic.split()[0]}%",))  # Match by first word of topic
    
    result = cursor.fetchone()
    conn.close()
    
    avg_views = result[0] if result and result[0] else 0
    
    # Boost score based on past performance
    # Views > 10K = +30 boost, > 1K = +15, < 1K = 0
    if avg_views > 10000:
        return 30
    elif avg_views > 1000:
        return 15
    elif avg_views > 100:
        return 5
    return 0

def learn_best_niches():
    """
    Analyzes upload history and returns a ranked list of niches with score multipliers.
    Main loop uses this to prioritize which niches to run more batches for.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    SELECT niche, 
           COUNT(*) as video_count,
           AVG(views) as avg_views,
           AVG(likes) as avg_likes,
           SUM(views) as total_reach
    FROM videos 
    GROUP BY niche 
    ORDER BY avg_views DESC
    ''')
    results = cursor.fetchall()
    conn.close()
    
    niche_scores = []
    for row in results:
        niche, count, avg_views, avg_likes, total_reach = row
        avg_views = avg_views or 0
        avg_likes = avg_likes or 0
        
        # Weighted score formula
        score = (avg_views * 1.0) + (avg_likes * 5.0)
        niche_scores.append({
            "niche": niche,
            "score": score,
            "avg_views": int(avg_views),
            "video_count": count
        })
        
    return sorted(niche_scores, key=lambda x: x['score'], reverse=True)

def sync_all_video_stats():
    """
    Syncs views, likes, and comments for all videos from YouTube using batch requests.
    """
    from youtube_uploader import get_batch_video_stats
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT video_id FROM videos")
    video_ids = [row[0] for row in cursor.fetchall()]
    
    updated_count = 0
    # Process in chunks of 50 (YouTube API limit)
    for i in range(0, len(video_ids), 50):
        chunk = video_ids[i:i+50]
        batch_stats = get_batch_video_stats(chunk)
        
        for vid, stats in batch_stats.items():
            cursor.execute('''
            UPDATE videos SET views = ?, likes = ?, comments = ?
            WHERE video_id = ?
            ''', (stats['views'], stats['likes'], stats['comments'], vid))
            updated_count += 1
    
    conn.commit()
    conn.close()
    return updated_count

def set_api_cooldown(provider, until_timestamp):
    """
    Sets a global cooldown for an API provider (Gemini, OpenAI, etc.)
    Shared across all processes.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT OR REPLACE INTO system_config (key, value, updated_at)
    VALUES (?, ?, ?)
    ''', (f"cooldown_{provider}", str(until_timestamp), datetime.now()))
    conn.commit()
    conn.close()

def get_api_cooldown(provider):
    """
    Returns the cooldown timestamp for a provider.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_config WHERE key = ?", (f"cooldown_{provider}",))
    row = cursor.fetchone()
    conn.close()
    if row:
        return float(row[0])
    return 0.0

# ── Pipeline Workflow Database Functions ─────────────────────────────────────

def create_pipeline_entry(topic: str, niche: str = None, script_json: str = None, title: str = None, description: str = None, tags: str = None) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now()
    cursor.execute('''
    INSERT INTO video_pipeline (topic, niche, status, script_json, title, description, tags, created_at, updated_at)
    VALUES (?, ?, 'DRAFT', ?, ?, ?, ?, ?, ?)
    ''', (topic, niche, script_json, title, description, tags, now, now))
    pipeline_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return pipeline_id

def get_pipeline(pipeline_id: int) -> dict | None:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM video_pipeline WHERE id = ?", (pipeline_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None

def update_pipeline_status(pipeline_id: int, status: str, rejection_reason: str = None, video_path: str = None, thumbnail_path: str = None, title: str = None, description: str = None, tags: str = None, script_json: str = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    now = datetime.now()
    
    updates = ["status = ?", "updated_at = ?"]
    params = [status, now]

    if rejection_reason is not None:
        updates.append("rejection_reason = ?")
        params.append(rejection_reason)
    if video_path is not None:
        updates.append("video_path = ?")
        params.append(video_path)
    if thumbnail_path is not None:
        updates.append("thumbnail_path = ?")
        params.append(thumbnail_path)
    if title is not None:
        updates.append("title = ?")
        params.append(title)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if tags is not None:
        updates.append("tags = ?")
        params.append(tags)
    if script_json is not None:
        updates.append("script_json = ?")
        params.append(script_json)
    if status == 'APPROVED':
        updates.append("approved_at = ?")
        params.append(now)
    if status == 'UPLOADED':
        updates.append("uploaded_at = ?")
        params.append(now)

    params.append(pipeline_id)
    sql = f"UPDATE video_pipeline SET {', '.join(updates)} WHERE id = ?"
    cursor.execute(sql, tuple(params))
    conn.commit()
    conn.close()

def save_script_version(pipeline_id: int, script_json: str, edited_by: str = 'user', edit_note: str = None) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Fetch latest version
    cursor.execute("SELECT MAX(version) FROM script_edit_history WHERE pipeline_id = ?", (pipeline_id,))
    max_ver = cursor.fetchone()[0]
    next_ver = (max_ver or 0) + 1

    cursor.execute('''
    INSERT INTO script_edit_history (pipeline_id, version, script_json, edited_by, edit_note, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (pipeline_id, next_ver, script_json, edited_by, edit_note, datetime.now()))

    # Update pipeline current version and script_json
    cursor.execute('''
    UPDATE video_pipeline SET script_version = ?, script_json = ?, updated_at = ?
    WHERE id = ?
    ''', (next_ver, script_json, datetime.now(), pipeline_id))

    conn.commit()
    conn.close()
    return next_ver

def save_beat_version(pipeline_id: int, beat_index: int, beat_json: str, clip_path: str = None, audio_path: str = None, duration_seconds: float = None, render_status: str = 'PENDING') -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Mark existing beat versions for this index as non-current
    cursor.execute('''
    UPDATE beat_versions SET is_current = 0 WHERE pipeline_id = ? AND beat_index = ?
    ''', (pipeline_id, beat_index))

    cursor.execute('''
    INSERT INTO beat_versions (pipeline_id, beat_index, beat_json, clip_path, audio_path, duration_seconds, is_current, render_status, created_at)
    VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
    ''', (pipeline_id, beat_index, beat_json, clip_path, audio_path, duration_seconds, render_status, datetime.now()))
    
    beat_ver_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return beat_ver_id

def mark_beat_current(beat_version_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT pipeline_id, beat_index FROM beat_versions WHERE id = ?", (beat_version_id,))
    row = cursor.fetchone()
    if row:
        pid, bidx = row
        cursor.execute("UPDATE beat_versions SET is_current = 0 WHERE pipeline_id = ? AND beat_index = ?", (pid, bidx))
        cursor.execute("UPDATE beat_versions SET is_current = 1 WHERE id = ?", (beat_version_id,))
        conn.commit()
    conn.close()

def record_timeline_edit(pipeline_id: int, edit_type: str, edit_payload: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO timeline_edits (pipeline_id, edit_type, edit_payload, applied_at)
    VALUES (?, ?, ?, ?)
    ''', (pipeline_id, edit_type, edit_payload, datetime.now()))
    conn.commit()
    conn.close()

def log_pipeline_event(pipeline_id: int | None, stage: str, level: str, message: str, duration_ms: int = None):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    INSERT INTO pipeline_log (pipeline_id, stage, level, message, duration_ms, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    ''', (pipeline_id, stage, level, message, duration_ms, datetime.now()))
    conn.commit()
    conn.close()

def get_videos_by_status(status: str) -> list:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM video_pipeline WHERE status = ? ORDER BY id ASC", (status,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_pipeline_logs(pipeline_id: int = None, stage: str = None, level: str = None, date_from: str = None, date_to: str = None) -> list:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    query = "SELECT * FROM pipeline_log WHERE 1=1"
    params = []

    if pipeline_id:
        query += " AND pipeline_id = ?"
        params.append(pipeline_id)
    if stage:
        query += " AND stage = ?"
        params.append(stage)
    if level:
        query += " AND level = ?"
        params.append(level)
    if date_from:
        query += " AND created_at >= ?"
        params.append(date_from)
    if date_to:
        query += " AND created_at <= ?"
        params.append(date_to)

    query += " ORDER BY id DESC LIMIT 500"
    cursor.execute(query, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
    print("\nNiche Performance:")
    for n in learn_best_niches():
        print(f"  {n['niche']}: Score {n['score']:.1f} | Avg Views: {n['avg_views']}")

