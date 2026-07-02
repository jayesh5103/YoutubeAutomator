"""
Parallel Rendering Engine
Renders multiple videos simultaneously using Python's multiprocessing.
Usage: render_worker.py handles a single video job as a child process.
main.py dispatches to a ProcessPoolExecutor for farm-scale output.
"""

import os
import json
import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
logger = logging.getLogger("YoutubeAutomator")

def is_manim_available():
    try:
        import manim
        return True
    except ImportError:
        return False

def _render_single_job(job: dict) -> dict:
    """
    Worker function executed in a child process.
    Each job dict must contain: topic, niche_file
    Returns: dict with success, video_path, topic
    """
    # Imports must be inside the function for multiprocessing compatibility
    from dotenv import load_dotenv
    load_dotenv()

    import yaml
    from script_writer import generate_script, generate_metadata
    from voiceover import generate_voiceover
    from video_editor import create_video, fetch_multiple_pexels_videos, fetch_coding_visuals, validate_render, create_storyboard_video
    from storyboard_engine import generate_storyboard
    from utils import cleanup_temp_files, organize_render, TEMP_DIR
    
    # Ensure temp dir exists
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR, exist_ok=True)

    topic_raw = job['topic']
    niche_file = job.get('niche_file', 'coding.yaml')
    worker_id = job.get('worker_id', 0)
    channel_name = job.get('channel_name', 'this channel')

    # Detect long-form videos (DISABLED - focusing on Shorts)
    is_long = False # topic_raw.startswith('[long]') or job.get('video_type') == 'long'
    topic = topic_raw.replace('[long]', '').replace('[short]', '').strip()

    # Use unique temp file names per worker in the temp directory
    audio_path = os.path.join(TEMP_DIR, f"temp_audio_{worker_id}.mp3")
    video_path = os.path.join(TEMP_DIR, f"final_video_{worker_id}.mp4")

    print(f"[Worker {worker_id}] Starting: {topic} (SHORT ONLY)"
    )

    # Route to long-form pipeline (DISABLED)
    # if is_long:
    #     try:
    #         from long_video_pipeline import render_long_video
    #         with open(f"niches/{niche_file}", 'r') as f:
    #             config = yaml.safe_load(f)
    #         result = render_long_video(
    #             topic=topic, config=config,
    #             channel_name=channel_name, worker_id=worker_id
    #         )
    #         return result
    #     except Exception as e:
    #         print(f"[Worker {worker_id}] Long-form pipeline failed: {e}")
    #         import traceback; traceback.print_exc()
    #         return {"success": False, "topic": topic, "error": str(e)}

    try:
        with open(f"niches/{niche_file}", 'r') as f:
            config = yaml.safe_load(f)

        # ── STORYBOARD PIPELINE (new "real edit" approach) ────────────────────
        # Generate beat-by-beat storyboard: each sentence gets its own
        # precisely timed Manim animation + voice audio.
        print(f"[Worker {worker_id}] 🎬 Generating storyboard...")
        storyboard = generate_storyboard(topic, channel_name=channel_name)

        if storyboard:
            # Combined script text for metadata generation
            full_script = " ".join(b["text"] for b in storyboard)
            metadata    = generate_metadata(topic, full_script)

            if not metadata or "title" not in metadata:
                metadata = {
                    "title": f"{topic} | DSA in Hinglish",
                    "description": f"Learn {topic} in Hinglish with animations.",
                    "tags": ["DSA", "LeetCode", "Placement"],
                    "keywords": ["algorithm", "coding"],
                }

            res_val = create_storyboard_video(
                beats=storyboard,
                output_path=video_path,
                worker_id=worker_id,
                manim_enabled=is_manim_available(),
            )
            out = None
            storyboard_beats = []
            if isinstance(res_val, tuple):
                out, storyboard_beats = res_val
            else:
                out = res_val

            if out and os.path.exists(out):
                valid, reason = validate_render(out)
                if valid:
                    final_path = organize_render(out)
                    print(f"[Worker {worker_id}] ✅ Storyboard video done: {final_path}")
                    
                    # Compute hook style and pacing stats
                    from script_scorer import classify_hook_style
                    hook_text = storyboard_beats[0]["text"] if storyboard_beats else ""
                    hook_style = classify_hook_style(hook_text) if hook_text else "bold_claim"
                    
                    beat_count = len(storyboard_beats)
                    total_duration = storyboard_beats[-1]["end_sec"] if storyboard_beats else 0.0
                    avg_beat_dur = (total_duration / beat_count) if beat_count > 0 else 0.0

                    return {
                        "success": True,
                        "topic": topic,
                        "video_path": final_path,
                        "title": metadata["title"],
                        "description": metadata.get("description", ""),
                        "tags": metadata.get("tags", []) + config.get("tags", []),
                        "niche": config.get("niche_name", niche_file),
                        "storyboard_beats": storyboard_beats,
                        "hook_text": hook_text,
                        "hook_style": hook_style,
                        "avg_beat_duration": avg_beat_dur,
                        "beat_count": beat_count
                    }
                else:
                    print(f"[Worker {worker_id}] ⚠️  Storyboard validation failed ({reason}), falling back")
            else:
                print(f"[Worker {worker_id}] ⚠️  Storyboard video failed, falling back")

        # ── FALLBACK: legacy single-animation pipeline ────────────────────────
        print(f"[Worker {worker_id}] Using legacy pipeline as fallback")

        # 1. Script
        script = generate_script(topic, niche_config=config, channel_name=channel_name)
        if not script:
            return {"success": False, "topic": topic, "error": "Script generation failed"}
        logger.info(f"[Worker {worker_id}] Generated script: {script[:100]}...")

        # 2. Metadata
        metadata = generate_metadata(topic, script)
        if not metadata or 'title' not in metadata:
            return {"success": False, "topic": topic, "error": "Metadata failed"}

        # 3. Voiceover
        audio = generate_voiceover(script, audio_path, gender="male", niche_config=config)
        if not audio or not os.path.exists(audio_path):
            return {"success": False, "topic": topic, "error": "Audio failed"}

        # 4. Visuals
        anim_path = os.path.join(TEMP_DIR, f"worker_{worker_id}_anim.mp4")
        bg_paths  = []
        bg_paths = fetch_coding_visuals(topic, count=12,
                                        prefix=os.path.join(TEMP_DIR, f"worker_{worker_id}_"))
        if len(bg_paths) < 3:
                keywords = metadata.get('keywords', [topic])
                bg_paths += fetch_multiple_pexels_videos(
                    ", ".join(keywords[:3]), count=4,
                    prefix=os.path.join(TEMP_DIR, f"worker_{worker_id}_fallback_")
                )

        # 5. Video
        out = create_video(audio_path=audio_path, background_video_paths=bg_paths,
                           output_path=video_path, script_text=script)
        if not out:
            return {"success": False, "topic": topic, "error": "Video creation failed"}

        valid, reason = validate_render(out)
        if not valid:
            try: os.remove(out)
            except: pass
            return {"success": False, "topic": topic, "error": f"Render corrupted: {reason}"}

        final_path = organize_render(out)
        print(f"[Worker {worker_id}] ✅ Done: {final_path}")
        return {
            "success": True,
            "topic": topic,
            "video_path": final_path,
            "title": metadata['title'],
            "description": metadata.get('description', ''),
            "tags": metadata.get('tags', []) + config.get('tags', []),
            "niche": config.get('niche_name', niche_file)
        }

    except Exception as e:
        print(f"[Worker {worker_id}] ❌ Failed: {e}")
        return {"success": False, "topic": topic, "error": str(e)}
    finally:
        # Cleanup this worker's temp files and any background clips it downloaded
        import glob
        for pattern in [audio_path, video_path, os.path.join(TEMP_DIR, f"worker_{worker_id}_bg_clip_*.mp4")]:
            for f in glob.glob(pattern):
                try:
                    if os.path.exists(f):
                        os.remove(f)
                except:
                    pass
        print(f"[Worker {worker_id}] Exiting _render_single_job for {topic}")


def render_batch_parallel(jobs: list, max_workers: int = 3) -> list:
    """
    Renders multiple videos in parallel using a ProcessPoolExecutor.
    
    Args:
        jobs: list of dicts, each with {"topic": str, "niche_file": str, "worker_id": int}
        max_workers: Number of parallel render processes (default 3, tune based on CPU cores)
    
    Returns:
        list of result dicts
    """
    results = []
    print(f"[Render Farm] Starting {len(jobs)} parallel render jobs with {max_workers} workers...")

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all jobs
        future_to_job = {executor.submit(_render_single_job, job): job for job in jobs}

        for future in as_completed(future_to_job):
            try:
                result = future.result(timeout=600)  # 10min timeout per video
                results.append(result)
                if result['success']:
                    print(f"[Render Farm] ✅ Completed: {result['topic']}")
                else:
                    print(f"[Render Farm] ❌ Failed: {result['topic']} - {result.get('error')}")
            except Exception as e:
                job = future_to_job[future]
                print(f"[Render Farm] ❌ Worker crashed for {job['topic']}: {e}")
                results.append({"success": False, "topic": job['topic'], "error": str(e)})

    successful = sum(1 for r in results if r['success'])
    print(f"[Render Farm] Batch complete: {successful}/{len(jobs)} successful.")
    return results


if __name__ == "__main__":
    # Quick test with 2 parallel jobs
    test_jobs = [
        {"topic": "Secret iPhone hacks", "niche_file": "tech.yaml", "worker_id": 0},
        {"topic": "Top AI tools of 2026", "niche_file": "ai_news.yaml", "worker_id": 1},
    ]
    results = render_batch_parallel(test_jobs, max_workers=2)
    for r in results:
        print(r)
