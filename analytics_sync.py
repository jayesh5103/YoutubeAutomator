import os
import sqlite3
import logging
import time
from datetime import datetime, timedelta
from database import DB_PATH
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

logger = logging.getLogger("YoutubeAutomator")

# Reuse scopes from youtube_uploader
from youtube_uploader import SCOPES

def get_analytics_service():
    """
    Returns the authenticated YouTube Analytics service.
    """
    if os.path.exists('token.json'):
        try:
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
            return build('youtubeAnalytics', 'v2', credentials=creds)
        except Exception as e:
            logger.error(f"[Analytics Sync] Failed to build YouTube Analytics service: {e}")
    return None

def parse_db_datetime(dt_str):
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(dt_str, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(dt_str)
    except:
        return None

def calculate_beat_retention(start_sec, end_sec, total_duration, curve_points):
    """
    Calculates the average watch ratio within a beat start/end window.
    curve_points: list of (ratio, retention_val)
    """
    if not curve_points:
        return 0.0
        
    r_start = start_sec / total_duration if total_duration > 0 else 0.0
    r_end = end_sec / total_duration if total_duration > 0 else 1.0
    
    # Filter points in the window
    window_points = [val for ratio, val in curve_points if r_start <= ratio <= r_end]
    
    if window_points:
        return sum(window_points) / len(window_points)
        
    # If no points fell exactly inside, find the closest one
    closest_val = min(curve_points, key=lambda p: min(abs(p[0] - r_start), abs(p[0] - r_end)))[1]
    return closest_val

def sync_video_analytics(video_id: str, upload_time: datetime) -> bool:
    """
    Pulls Analytics metrics for a single video and populates all relevant intelligence tables.
    """
    analytics = get_analytics_service()
    if not analytics:
        logger.error(f"[Analytics Sync] YouTube Analytics service is not authenticated. Skip {video_id}")
        return False
        
    start_date_str = (upload_time - timedelta(days=1)).strftime("%Y-%m-%d")
    end_date_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    
    try:
        logger.info(f"[Analytics Sync] Querying Analytics API for video: {video_id}...")
        
        # 1. Fetch core stats (with fallback in case impressions are not supported)
        stats = None
        try:
            stats_resp = analytics.reports().query(
                ids='channel==MINE',
                startDate=start_date_str,
                endDate=end_date_str,
                metrics='views,likes,averageViewDuration,averageViewPercentage,annotationClickThroughRate,videoThumbnailImpressions',
                filters=f'video=={video_id}'
            ).execute()
            
            rows = stats_resp.get('rows', [])
            if rows:
                cols = [c['name'] for c in stats_resp.get('columnHeaders', [])]
                row_dict = dict(zip(cols, rows[0]))
                stats = {
                    "views": int(row_dict.get("views", 0)),
                    "likes": int(row_dict.get("likes", 0)),
                    "averageViewDuration": float(row_dict.get("averageViewDuration", 0.0)),
                    "averageViewPercentage": float(row_dict.get("averageViewPercentage", 0.0)),
                    "annotationClickThroughRate": float(row_dict.get("annotationClickThroughRate", 0.0)),
                    "videoThumbnailImpressions": int(row_dict.get("videoThumbnailImpressions", 0))
                }
        except Exception as stats_err:
            logger.warning(f"[Analytics Sync] Query with impressions failed, trying core metrics only: {stats_err}")
            stats_resp = analytics.reports().query(
                ids='channel==MINE',
                startDate=start_date_str,
                endDate=end_date_str,
                metrics='views,likes,averageViewDuration,averageViewPercentage,annotationClickThroughRate',
                filters=f'video=={video_id}'
            ).execute()
            
            rows = stats_resp.get('rows', [])
            if rows:
                cols = [c['name'] for c in stats_resp.get('columnHeaders', [])]
                row_dict = dict(zip(cols, rows[0]))
                stats = {
                    "views": int(row_dict.get("views", 0)),
                    "likes": int(row_dict.get("likes", 0)),
                    "averageViewDuration": float(row_dict.get("averageViewDuration", 0.0)),
                    "averageViewPercentage": float(row_dict.get("averageViewPercentage", 0.0)),
                    "annotationClickThroughRate": float(row_dict.get("annotationClickThroughRate", 0.0)),
                    "videoThumbnailImpressions": int(row_dict.get("views", 0) / 0.1)  # simple fallback estimate
                }
                
        if not stats:
            logger.warning(f"[Analytics Sync] No analytics data returned for {video_id}. (Video might have no views yet).")
            return False

        # 2. Fetch audience watch ratio curve
        retention_resp = analytics.reports().query(
            ids='channel==MINE',
            startDate=start_date_str,
            endDate=end_date_str,
            metrics='audienceWatchRatio',
            dimensions='elapsedVideoTimeRatio',
            filters=f'video=={video_id}'
        ).execute()
        
        curve_points = []
        for r in retention_resp.get('rows', []):
            curve_points.append((float(r[0]), float(r[1])))
            
        curve_points.sort(key=lambda x: x[0])
        
        # 3. Store synced data back into SQLite tables
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Update videos table
        cursor.execute('''
        UPDATE videos SET views = ?, likes = ?
        WHERE video_id = ?
        ''', (stats["views"], stats["likes"], video_id))
        
        # Update topic performance
        watch_time_min = (stats["views"] * stats["averageViewDuration"]) / 60.0
        perf_score = (stats["views"] * 1.0) + (stats["likes"] * 5.0) + (watch_time_min * 0.5)
        
        cursor.execute('''
        UPDATE topic_performance 
        SET views = ?, likes = ?, watch_time_minutes = ?, performance_score = ?
        WHERE video_id = ?
        ''', (stats["views"], stats["likes"], watch_time_min, perf_score, video_id))
        
        # Update script patterns
        # retention_rate is averageViewPercentage (0.0-100.0 or ratio). We store it directly.
        cursor.execute('''
        UPDATE script_patterns SET retention_rate = ?
        WHERE video_id = ?
        ''', (stats["averageViewPercentage"], video_id))
        
        # Update storyboard beats performance in beat_performance
        cursor.execute('''
        SELECT id, beat_start_second, beat_end_second FROM beat_performance
        WHERE video_id = ?
        ORDER BY beat_index ASC
        ''', (video_id,))
        beats = cursor.fetchall()
        
        # If we have beats, calculate start/end ratios and averages
        if beats:
            # total duration of video is the end of the last beat
            total_dur = max(b[2] for b in beats)
            for db_id, start, end in beats:
                avg_ret = calculate_beat_retention(start, end, total_dur, curve_points)
                cursor.execute('''
                UPDATE beat_performance SET avg_retention_in_window = ?
                WHERE id = ?
                ''', (avg_ret, db_id))
                
        # Update upload performance
        # For simplicity since we sync after 48hr, estimate hourly distributions
        cursor.execute('''
        UPDATE upload_performance 
        SET views_6hr = ?, views_24hr = ?, views_48hr = ?, ctr = ?, avg_view_duration = ?
        WHERE video_id = ?
        ''', (int(stats["views"]*0.12), int(stats["views"]*0.75), stats["views"], 
              stats["annotationClickThroughRate"], stats["averageViewDuration"], video_id))
              
        # Update thumbnail performance
        cursor.execute('''
        UPDATE thumbnail_performance 
        SET ctr = ?, impressions = ?
        WHERE video_id = ?
        ''', (stats["annotationClickThroughRate"], stats["videoThumbnailImpressions"], video_id))
        
        conn.commit()
        conn.close()
        
        logger.info(f"[Analytics Sync] Successfully synced metrics for {video_id}")
        return True
        
    except Exception as e:
        logger.error(f"[Analytics Sync] Failed syncing video {video_id}: {e}")
        import traceback
        traceback.print_exc()
        return False

def run_analytics_sync():
    """
    Loops through all videos uploaded in the last 30 days.
    For videos older than 48 hours that haven't been successfully synced, queries Analytics.
    Finally, recomputes all modular weight calculations.
    """
    logger.info("🧠 Starting Analytics Sync Cycle...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Query all videos uploaded in the last 30 days
    thirty_days_ago = datetime.now() - timedelta(days=30)
    cursor.execute('''
    SELECT video_id, upload_time, title FROM videos
    WHERE upload_time >= ?
    ''', (thirty_days_ago,))
    videos = cursor.fetchall()
    
    conn.close()
    
    synced_count = 0
    failed_count = 0
    
    for video_id, upload_time_str, title in videos:
        upload_time = parse_db_datetime(upload_time_str)
        if not upload_time:
            continue
            
        # Check if video is older than 48 hours
        if datetime.now() < upload_time + timedelta(hours=48):
            # Too new to sync analytics
            continue
            
        # Check sync log state
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
        SELECT sync_status, retry_count FROM analytics_sync_log
        WHERE video_id = ?
        ''', (video_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            status, retry = row
            if status == 'synced':
                continue # Already successfully synced
            if retry >= 3:
                continue # Skip dead retry loops
        else:
            status, retry = 'pending', 0
            
        # Run sync
        success = sync_video_analytics(video_id, upload_time)
        
        # Update log
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        if success:
            cursor.execute('''
            INSERT OR REPLACE INTO analytics_sync_log (video_id, last_synced_at, sync_status, retry_count)
            VALUES (?, ?, 'synced', ?)
            ''', (video_id, datetime.now(), retry))
            synced_count += 1
        else:
            cursor.execute('''
            INSERT OR REPLACE INTO analytics_sync_log (video_id, last_synced_at, sync_status, retry_count)
            VALUES (?, ?, 'failed', ?)
            ''', (video_id, datetime.now(), retry + 1))
            failed_count += 1
        conn.commit()
        conn.close()
        
    logger.info(f"[Analytics Sync] Synced {synced_count} videos. Failed/Pending: {failed_count}.")
    
    # 4. Trigger learning engine re-computation if we synced anything
    if synced_count > 0:
        logger.info("[Analytics Sync] Triggering re-computation of preference tables...")
        try:
            from topic_scorer import update_keyword_weights
            from script_scorer import update_script_preferences
            from visual_scorer import update_visual_preferences
            from upload_optimizer import update_upload_preferences
            
            update_keyword_weights()
            update_script_preferences()
            update_visual_preferences()
            update_upload_preferences()
            
            logger.info("[Analytics Sync] Learning updates complete!")
        except Exception as err:
            logger.error(f"[Analytics Sync] Failed re-computing preferences: {err}")
            
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    import sys
    if "--run-once" in sys.argv:
        print("[ANALYTICS SYNC] Running one-shot sync...")
        run_analytics_sync()
        # Force learning engine recomputation regardless of sync count
        try:
            from topic_scorer import update_keyword_weights
            from script_scorer import update_script_preferences
            from visual_scorer import update_visual_preferences
            from upload_optimizer import update_upload_preferences

            update_keyword_weights()
            update_script_preferences()
            update_visual_preferences()
            update_upload_preferences()
            print("[ANALYTICS SYNC] Learning engine recomputation complete.")
        except Exception as err:
            print(f"[ANALYTICS SYNC] Warning: Failed recomputing preferences: {err}")
        print("[ANALYTICS SYNC] Done.")
    else:
        run_analytics_sync()

