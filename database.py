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

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
    print("\nNiche Performance:")
    for n in learn_best_niches():
        print(f"  {n['niche']}: Score {n['score']:.1f} | Avg Views: {n['avg_views']}")
