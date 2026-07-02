import sys
import os

# ── Headless Mode (GitHub Actions / Cloud) ────────────────────────────────────
HEADLESS_MODE = os.getenv("HEADLESS_MODE", "false").lower() == "true"

# ── Auto-activate venv ────────────────────────────────────────────────────────
# If not running inside the project venv, re-exec with the correct Python.
# This means you can just run `python3 main.py` without `source venv/bin/activate`.
# Skipped in headless/cloud mode where venv doesn't exist.
if not HEADLESS_MODE:
    _venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), "venv", "bin", "python3")
    if os.path.exists(_venv_python) and os.path.abspath(sys.executable) != os.path.abspath(_venv_python):
        os.execv(_venv_python, [_venv_python] + sys.argv)
# ─────────────────────────────────────────────────────────────────────────────

import logging
from logging.handlers import RotatingFileHandler
import yaml
import schedule
import time
from topic_engine import seed_topics, seed_coding_topics, get_best_unused_topic, get_trending_topics, save_trends_to_db
from database import init_db, log_video, get_viral_score_boost, get_todays_video_count
from script_writer import generate_script, generate_metadata
from voiceover import generate_voiceover
from video_editor import create_video, fetch_multiple_pexels_videos
from youtube_uploader import upload_video, post_first_comment, get_channel_stats
from utils import cleanup_temp_files, organize_render
from render_worker import render_batch_parallel
from upload_renders import bulk_upload

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        RotatingFileHandler("automation.log", maxBytes=10*1024*1024, backupCount=5),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("YoutubeAutomator")

# ─── FREE TIER LIMITS ────────────────────────────────────────────────
# Gemini free tier: 20 requests/day across all models
# Each video needs ~3-4 API calls (script + metadata + viral keywords)
# Target X videos per day to avoid account flagging (X from .env or default 6)
DAILY_VIDEO_LIMIT = int(os.getenv("DAILY_VIDEO_LIMIT", 6))
# ─────────────────────────────────────────────────────────────────────

# Ensure DB is ready and coding topics are seeded (Intelligence + Static fallback)
from db_migration import run_migration
run_migration()
init_db()
seed_topics()

def ensure_youtube_auth():
    """
    Pre-authenticates YouTube OAuth in the MAIN process before any
    parallel workers are spawned. This ensures the browser popup
    appears, and token.json is written before child processes try to use it.
    """
    logger.info("Checking YouTube authentication...")
    from youtube_uploader import get_authenticated_service
    service = get_authenticated_service()
    if service:
        logger.info("✅ YouTube authentication OK.")
        return True
    else:
        logger.error("❌ YouTube authentication failed. Uploads will be skipped.")
        return False

def get_niche_config(niche_file):
    with open(f"niches/{niche_file}", 'r') as f:
        config = yaml.safe_load(f)
        return config if config else {}

def run_batch(niche_file, video_count=5):
    config = get_niche_config(niche_file)
    niche_name = config.get('niche_name')
    logger.info(f"Starting Batch Gen for Niche: {niche_name} ({video_count} videos)")
    
    # Refresh trends
    keywords = config.get('tags', [])
    trends = get_trending_topics(keywords)
    save_trends_to_db(trends)
    
    completed = 0
    for i in range(video_count):
        topic = get_best_unused_topic()
        if not topic:
            logger.warning("No more unused topics for this niche.")
            break
            
        logger.info(f"Processing Video {i+1}/{video_count}: {topic}")
        
        # Wrapped in try-except for Failure Recovery
        try:
            success = single_video_pipeline(topic, config)
            if success: completed += 1
        except Exception as e:
            logger.error(f"Pipeline failed for topic '{topic}': {e}")
            continue
            
    logger.info(f"Batch completed: {completed}/{video_count} successful.")

def single_video_pipeline(topic, config):
    try:
        # 1. Script
        script = generate_script(topic, niche_config=config)
        
        # 2. Metadata
        metadata = generate_metadata(topic, script)
        if not metadata or 'title' not in metadata:
            logger.error(f"Failed to get metadata for {topic}")
            return False
            
        title = metadata['title']
        tags = metadata['tags'] + config.get('tags', [])
        
        # 3. Voiceover
        audio_path = generate_voiceover(script, "temp_audio.mp3", gender="male")
        if not audio_path or not os.path.exists(audio_path):
            logger.error(f"Failed to generate audio for {topic}")
            return False
        
        # 4. Visuals (Keywords from Metadata)
        visual_keywords = metadata.get('keywords', [topic])
        background_paths = fetch_multiple_pexels_videos(query=", ".join(visual_keywords), count=6)
        
        if not background_paths:
            background_paths = fetch_multiple_pexels_videos(query=topic, count=3)
            
        # 5. Video Compilation
        video_path = create_video(
            audio_path=audio_path,
            background_video_paths=background_paths,
            script_text=script
        )
        
        if not video_path: return False
        
        # 6. Organize & Upload
        final_path = organize_render(video_path)
        video_id = upload_video(final_path, title, metadata['description'], tags[:15])
        
        if video_id:
            from youtube_uploader import post_first_comment
            log_video(video_id, title, topic, config['niche_name'])
            post_first_comment(video_id, "Kaunsa part confuse kiya? Neeche batao! 💬 Part 2 ke liye subscribe karo! 🚀")
            return True
            
        return False
        
    finally:
        cleanup_temp_files()

def job(manual_topic=None, manual_niche=None):
    """
    Main Job: Uses Analytics Learning to prioritize the best-performing niches.
    Uses Parallel Rendering for maximum throughput.
    Accepts manual_topic to bypass trend engine and run a specific topic.
    """
    import traceback
    logger.info("--- TRACEBACK FOR JOB() CALL ---")
    for line in traceback.format_stack():
        logger.info(line.strip())
    logger.info("--------------------------------")
    # 0. CHECK PENDING RENDERS FIRST
    logger.info("Checking for pending renders to upload...")
    bulk_upload()

    # 0.5 PRE-AUTHENTICATE YouTube first (shows browser popup in main process)
    #    Must happen before parallel workers spawn — child processes can't open browsers
    youtube_ready = ensure_youtube_auth()
    
    # 0.6 FETCH CHANNEL NAME for branding
    channel_info = get_channel_stats()
    channel_name = channel_info.get('name', 'this channel') if channel_info else 'this channel'
    logger.info(f"Connected to YouTube Channel: {channel_name}")
    
    # 0.5 CHECK DAILY LIMIT (Skip if manual topic, user might explicitly want it)
    if not manual_topic:
        todays_count = get_todays_video_count()
        if todays_count >= DAILY_VIDEO_LIMIT:
            logger.warning(f"Daily limit reached: {todays_count}/{DAILY_VIDEO_LIMIT} videos uploaded today.")
            logger.warning("Skipping job to preserve free-tier API quota. Will try again tomorrow.")
            return
    
    # MANUAL OVERRIDE PATH
    if manual_topic and manual_niche:
        logger.info(f"🚀 MANUAL OVERRIDE: Starting generation for topic: {manual_topic}")
        config = get_niche_config(manual_niche)
        # Directly dispatch a single worker for this topic
        logger.info(f"Dispatching rendering worker for manual topic: {manual_topic}")
        success = render_batch_parallel([{"topic": manual_topic, "config": config, "worker_id": 1, "channel_name": channel_name}])
        if success:
            logger.info(f"✅ Manual video generation complete for {manual_topic}")
        else:
            logger.error(f"❌ Failed to generate manual video for {manual_topic}")
        return

    # 1. CODING NICHE — Always use coding.yaml as the primary niche.
    #    seed_topics() runs Intelligence Engine (YouTube trend analysis) + static fallback.
    seed_topics()

    # 2. Collect topics for batch generation
    todays_count = get_todays_video_count()
    remaining = DAILY_VIDEO_LIMIT - todays_count

    if remaining <= 0:
        logger.info(f"Target of {DAILY_VIDEO_LIMIT} videos already reached for today ({todays_count}). Skipping batch.")
        return

    logger.info(f"Daily Quota: {todays_count}/{DAILY_VIDEO_LIMIT}. Planning to generate {remaining} coding/DSA videos.")

    # Always run with coding.yaml as primary niche
    primary_niche = "coding.yaml"
    niche_dir = "niches"

    # Check if coding.yaml exists, fall back to tech.yaml if not
    if not os.path.exists(os.path.join(niche_dir, primary_niche)):
        logger.warning(f"{primary_niche} not found in niches/. Falling back to tech.yaml.")
        primary_niche = "tech.yaml"

    config = get_niche_config(primary_niche)
    logger.info(f"Active niche: {config.get('niche_name', primary_niche)}")

    batch_jobs = []
    worker_id = 0
    for _ in range(remaining):
        topic = get_best_unused_topic()
        if not topic:
            logger.warning("No unused topics left. Re-checking after seed...")
            seed_coding_topics()
            topic = get_best_unused_topic()
        if topic:
            boost = get_viral_score_boost(topic)
            batch_jobs.append({
                "topic": topic,
                "niche_file": primary_niche,
                "worker_id": worker_id,
                "score_boost": boost,
                "channel_name": channel_name
            })
            worker_id += 1
    
    if not batch_jobs:
        logger.warning("No topics available for batch. Skipping.")
        return
    
    logger.info(f"Dispatching {len(batch_jobs)} jobs to Parallel Render Farm... (Quota Remaining: {remaining})")
    
    # 3. SEQUENTIAL RENDERING — Incremental Upload Strategy
    # We process results one by one to strictly honor Gemini Rate Limits (15 RPM)
    # This prevents the 429 errors that were occurring with the parallel farm.
    from render_worker import _render_single_job
    
    quota_hit = False
    for job_data in batch_jobs:
        if quota_hit:
            logger.warning(f"⚠️  Skipping generation for '{job_data['topic']}' — daily limit already reached.")
            continue
            
        try:
            print(f"[MAIN] -----> Calling _render_single_job for {job_data['topic']}")
            result = _render_single_job(job_data)
            print(f"[MAIN] <----- Returned from _render_single_job for {job_data['topic']}")
            
            if result and result.get('success') and result.get('video_path'):
                # 4. Upload immediately
                logger.info(f"Worker finished: {result['topic']}. Determining best upload slot...")
                schedule_time = None
                hour, day_of_week = None, None
                try:
                    from learning_engine import LearningEngine
                    from datetime import datetime, timedelta
                    hour, day_of_week = LearningEngine.get_best_upload_slot()
                    now = datetime.now()
                    days_ahead = day_of_week - now.weekday()
                    if days_ahead < 0 or (days_ahead == 0 and now.hour >= hour):
                        days_ahead += 7
                    target_date = now + timedelta(days=days_ahead)
                    target_time = target_date.replace(hour=hour, minute=0, second=0, microsecond=0)
                    schedule_time = target_time.isoformat() + "Z"
                    logger.info(f"[MAIN] Scheduling publish for Day {day_of_week}, Hour {hour} -> {schedule_time}")
                except Exception as slot_err:
                    logger.error(f"[MAIN] Failed getting upload slot: {slot_err}")

                video_id = upload_video(
                    result['video_path'],
                    result.get('title', result['topic']),
                    result.get('description', ''),
                    result.get('tags', [])[:15],
                    schedule_time=schedule_time
                )
                if video_id == "QUOTA_EXCEEDED":
                    logger.warning("⚠️  Daily upload limit reached. Remaining renders will be uploaded in the next scheduled run.")
                    quota_hit = True
                elif video_id:
                    log_video(video_id, result.get('title'), result['topic'], result.get('niche', 'unknown'))
                    
                    # Record learning engine parameters
                    try:
                        from topic_scorer import record_topic_selection
                        from script_scorer import record_script_pattern
                        from visual_scorer import save_beat_metadata
                        from upload_optimizer import record_upload_details, record_thumbnail_metadata, analyze_thumbnail_attributes
                        
                        niche = result.get('niche', 'unknown')
                        topic = result.get('topic', '')
                        title = result.get('title', '')
                        storyboard_beats = result.get('storyboard_beats', [])
                        
                        record_topic_selection(video_id, topic, niche)
                        
                        if storyboard_beats:
                            record_script_pattern(
                                video_id,
                                result.get('hook_text', ''),
                                result.get('hook_style', 'bold_claim'),
                                result.get('avg_beat_duration', 0.0),
                                result.get('beat_count', 0)
                            )
                            save_beat_metadata(video_id, storyboard_beats)
                            
                        now = datetime.now()
                        up_hour = hour if schedule_time else now.hour
                        up_day = day_of_week if schedule_time else now.weekday()
                        record_upload_details(video_id, up_hour, up_day)
                        
                        thumb_meta = analyze_thumbnail_attributes(title, storyboard_beats)
                        record_thumbnail_metadata(video_id, thumb_meta)
                    except Exception as le_log_err:
                        logger.error(f"Failed to log learning engine parameters: {le_log_err}")

                    from youtube_uploader import post_first_comment
                    post_first_comment(video_id, "Kaunsa concept confuse kiya? Comment karo! 💬 Follow for daily DSA! 🚀")
                    from utils import archive_uploaded_video
                    archive_uploaded_video(result['video_path'])
                    logger.info(f"✅ Uploaded & Logged: {result['title']} [{video_id}]")
            else:
                err = result.get('error') if result else "Unknown error or None returned"
                logger.error(f"❌ Worker failed for {result.get('topic', job_data['topic'])}: {err}")
        except Exception as e:
            logger.error(f"❌ Pipeline error for job '{job_data['topic']}': {e}")
            import traceback
            traceback.print_exc()
    
    # 5. Global cleanup for any stalled patterns or leftovers
    cleanup_temp_files()


def run_scheduler():
    logger.info("Scheduler started. Running batch 3 times a day.")
    schedule.every(8).hours.do(job)
    
    # Run sync immediately in a background thread to refresh preferences on boot
    try:
        from analytics_sync import run_analytics_sync
        import threading
        logger.info("Triggering initial analytics sync in background thread...")
        threading.Thread(target=run_analytics_sync, daemon=True).start()
        
        # Schedule the sync every 6 hours
        schedule.every(6).hours.do(run_analytics_sync)
    except Exception as e:
        logger.error(f"Failed to start analytics sync schedule: {e}")
    
    while True:
        schedule.run_pending()
        time.sleep(60)

def run_headless_cycle():
    """Runs one batch cycle and exits. GitHub Actions handles the schedule."""
    logger.info("[HEADLESS] Starting single batch cycle...")
    job()
    logger.info("[HEADLESS] Batch cycle complete. Exiting.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--now":
        if HEADLESS_MODE:
            run_headless_cycle()
        else:
            job()
    elif len(sys.argv) > 1 and sys.argv[1] == "--topic":
        if len(sys.argv) > 2:
            topic = sys.argv[2]
            niche = "coding.yaml"
            is_long = "--long" in sys.argv
            if is_long:
                # topic = f"[long] {topic}"  <-- DISABLED
                logger.warning("⚠️  Long-form pipeline is currently disabled. Processing as Short.")
            for i, a in enumerate(sys.argv):
                if a.endswith(".yaml"):
                    niche = a
            job(manual_topic=topic, manual_niche=niche)
        else:
            print("Usage: python3 main.py --topic \"My Topic\" [coding.yaml] [--long]")
    elif len(sys.argv) > 1 and sys.argv[1] == "--batch":
        niche = sys.argv[2] if len(sys.argv) > 2 else "coding.yaml"
        count = int(sys.argv[3]) if len(sys.argv) > 3 else 3
        run_batch(niche, count)
    elif len(sys.argv) > 1 and sys.argv[1] == "--intelligence":
        from youtube_intelligence import seed_intelligent_topics, get_intelligence_report
        print("\n🧠 Running Intelligence Engine...")
        count = seed_intelligent_topics()
        print(f"Inserted {count} AI-suggested topics.")
        print(get_intelligence_report())
    elif HEADLESS_MODE:
        # Cloud mode without explicit flags — run one cycle and exit
        run_headless_cycle()
    else:
        run_scheduler()
