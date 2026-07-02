from beat_renderer import MANIM_FPS
import os
import requests
import random
from moviepy import VideoFileClip, AudioFileClip, TextClip, CompositeVideoClip, concatenate_videoclips
from dotenv import load_dotenv

load_dotenv()


def fetch_coding_visuals(topic: str, count: int = 8, prefix: str = "") -> list:
    """
    Fetches topic-relevant background videos for a coding/DSA topic.
    Uses topic_engine.get_topic_visual_hints() to determine the best Pexels queries,
    then falls back to generic coding visuals.

    This is the primary entry point for visual fetching in the coding niche.
    It replaces the old pattern of passing raw metadata keywords.
    """
    try:
        from topic_engine import get_topic_visual_hints
        visual_hints = get_topic_visual_hints(topic)
        print(f"[Visuals] Topic: '{topic}' → Queries: {visual_hints}")
    except Exception as e:
        print(f"[Visuals] topic_engine unavailable ({e}), using generic fallback")
        visual_hints = ["algorithm flowchart", "programming code screen"]

    # Build a combined query string from hints
    combined_query = ", ".join(visual_hints)

    paths = fetch_multiple_pexels_videos(query=combined_query, count=count, prefix=prefix)

    # Fallback: generic coding visuals if topic-specific search returns nothing
    if not paths:
        print("[Visuals] Topic hints returned no clips. Trying generic coding fallback...")
        fallback_queries = [
            "programming code screen",
            "developer laptop coding",
            "algorithm flowchart whiteboard",
            "technology abstract digital",
        ]
        fallback_q = ", ".join(random.sample(fallback_queries, 2))
        paths = fetch_multiple_pexels_videos(query=fallback_q, count=count, prefix=prefix)

    return paths

def fetch_multiple_pexels_videos(query="abstract", orientation="portrait", count=3, prefix=""):
    """
    Fetches multiple stock videos from Pexels based on a search query.
    Expects `query` to be a comma-separated list of EXACT Pexels search terms (e.g. "telescope, observatory, space shuttle").
    """
    keys_str = os.getenv("PEXELS_API_KEY", "")
    api_keys = [k.strip() for k in keys_str.split(',') if k.strip()]
    
    if not api_keys:
        print("[Pexels] API Key not found. Cannot fetch video.")
        return []

    # Clean up query: Pexels works best with literal single/double terms
    keywords = [k.strip() for k in query.split(',') if k.strip()]
    if not keywords:
        keywords = ["abstract"]
        
    downloaded_paths = []
    
    def _attempt_download(search_query, target_count, current_paths):
        print(f"[Pexels] Searching for '{search_query}' videos...")
        random_page = random.randint(1, 4)
        url = f"https://api.pexels.com/videos/search?query={search_query}&orientation={orientation}&per_page=15&page={random_page}"
        
        for api_key in api_keys:
            headers = {"Authorization": api_key}
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 429:
                    continue
                response.raise_for_status()
                
                data = response.json()
                videos = data.get("videos", [])
                if not videos:
                    continue
                    
                random.shuffle(videos)
                
                for video in videos:
                    if len(current_paths) >= target_count:
                        return True
                        
                    video_files = video.get("video_files", [])
                    if not video_files:
                        continue
                        
                    best_file = max(video_files, key=lambda x: x.get("width", 0) * x.get("height", 0))
                    download_link = best_file.get("link")
                    
                    output_path = f"{prefix}bg_clip_{len(current_paths)}.mp4"
                    
                    try:
                        print(f"[Pexels] Downloading '{search_query}' clip to {output_path}...")
                        video_response = requests.get(download_link, stream=True, timeout=15)
                        video_response.raise_for_status()
                        
                        with open(output_path, "wb") as f:
                            for chunk in video_response.iter_content(chunk_size=8192):
                                f.write(chunk)
                        
                        # VALIDATE CLIP IMMEDIATELY
                        try:
                            is_healthy, reason = is_clip_healthy(output_path, min_duration=1.0)
                            if is_healthy:
                                current_paths.append(output_path)
                                print(f"[Pexels] ✅ Valid clip saved: {output_path}")
                            else:
                                print(f"[Pexels] ⚠️ Clip rejected ({reason}), deleting.")
                                os.remove(output_path)
                        except Exception as ve:
                            print(f"[Pexels] ❌ Clip evaluation error: {ve}")
                            if os.path.exists(output_path): os.remove(output_path)
                            
                    except Exception as e:
                        print(f"[Pexels] Download failed: {e}")
                        continue
                
                if len(current_paths) >= target_count:
                    return True
                    
            except Exception as e:
                print(f"[Pexels] Key error: {e}")
                continue
        return False

    print(f"[Pexels] Target: {count} clips across genres: {keywords}")
    
    # Try to get at least one clip per keyword if possible to ensure coverage
    for kw in keywords:
        if len(downloaded_paths) >= count:
            break
        
        # Target at least 2 clips per keyword to have variety, up to the total count
        target_for_this_kw = len(downloaded_paths) + max(1, count // len(keywords))
        if keywords.index(kw) == len(keywords) - 1:
            target_for_this_kw = count
            
        success = _attempt_download(kw, target_for_this_kw, downloaded_paths)
        
        # If a specific keyword fails entirely, try a slightly more generic version of it
        if not success:
            generic_kw = kw.split()[-1] # Try just the last word (usually the noun)
            if generic_kw != kw:
                print(f"[Pexels] Keyword '{kw}' failed. Trying generic '{generic_kw}'...")
                _attempt_download(generic_kw, target_for_this_kw, downloaded_paths)

    # Final fallback: coding-themed generic if still empty
    if not downloaded_paths:
        print(f"[Pexels] Final fallback (coding generic)")
        _attempt_download("programming code screen", count, downloaded_paths)
        if not downloaded_paths:
            _attempt_download("technology abstract digital", count, downloaded_paths)

    return downloaded_paths

def add_background_music(audio_clip, music_folder="music"):
    """
    Mixes background music with the voiceover if music files are available.
    """
    if not os.path.exists(music_folder):
        return audio_clip
        
    music_files = [f for f in os.listdir(music_folder) if f.endswith(('.mp3', '.wav'))]
    if not music_files:
        return audio_clip
        
    try:
        music_path = os.path.join(music_folder, random.choice(music_files))
        print(f"[Video Editor] Adding background music: {music_path}")
        
        # Use context manager for music clip
        with AudioFileClip(music_path) as music:
            music = music.with_volume_scaled(0.15)
            
            # Use audio_loop for efficient looping in moviepy v2
            from moviepy.audio.fx.AudioLoop import AudioLoop as audio_loop
            music = music.with_effects([audio_loop(duration=audio_clip.duration)])
            music = music.subclipped(0, audio_clip.duration)
            
            from moviepy import CompositeAudioClip
            combined = CompositeAudioClip([audio_clip, music])
            # Note: The combined clip will be closed when the main video export finishes
            return combined
            
    except Exception as e:
        print(f"[Video Editor] Error adding background music: {e}")
        return audio_clip

def create_video(audio_path, background_video_paths, output_path="final_video.mp4", script_text=""):
    """
    Combines an audio file, multiple background videos, and dynamic captions.
    """
    print(f"[Video Editor] Starting video creation: {output_path}")
    try:
        # Load audio
        if not audio_path or not os.path.exists(audio_path):
            print(f"[Video Editor] Invalid audio path: {audio_path}")
            return None
            
        with AudioFileClip(audio_path) as audio:
            audio_duration = audio.duration
            target_size = (720, 1280) 
            clips = []
            
            if not background_video_paths or len(background_video_paths) < 1:
                print("[Video Editor] ❌ No background paths provided. Aborting.")
                return None

            for path in background_video_paths:
                try:
                    if not os.path.exists(path):
                        print(f"[Video Editor] Skipping missing file: {path}")
                        continue
                    
                    clip = VideoFileClip(path).resized(height=target_size[1])
                    if clip.w > target_size[0]:
                        clip = clip.cropped(x_center=clip.w/2, width=target_size[0])
                    
                    max_clip_duration = 8.0
                    if clip.duration > max_clip_duration:
                        max_start = clip.duration - max_clip_duration
                        start = random.uniform(0, max_start)
                        clip = clip.subclipped(start, start + max_clip_duration)
                    clips.append(clip)
                except Exception as e:
                    print(f"[Video Editor] ❌ Could not load/resize clip {path}: {e}")
                    
            if not clips:
                print("[Video Editor] ❌ No valid background clips loaded. Aborting.")
                return None

            # Concatenate background clips
            stitched_bg = concatenate_videoclips(clips, method="chain")

            # Efficient looping
            if stitched_bg.duration < audio_duration:
                from moviepy.video.fx.Loop import Loop as loop
                stitched_bg = stitched_bg.with_effects([loop(duration=audio_duration)])

            # Truncate and set audio
            video = stitched_bg.subclipped(0, audio_duration)
            final_audio = add_background_music(audio)
            final_video = video.with_audio(final_audio)

            # Export
            print(f"[Video Editor] Exporting {output_path}...")
            final_video.write_videofile(
                output_path, 
                fps=24, 
                codec="libx264", 
                audio_codec="aac",
                bitrate="5000k",
                threads=4,
                preset="ultrafast",
                logger=None
            )
            
            # Clean up
            final_video.close()
            video.close()
            stitched_bg.close()
            for c in clips:
                c.close()
            
            import gc
            gc.collect()
            
            print(f"[Video Editor] Successfully created {output_path}")
            return output_path

    except Exception as e:
        print(f"[Video Editor] Error creating video: {e}")
        import traceback
        traceback.print_exc()
        return None


def create_chapter_card(chapter_title: str, output_path: str, duration: float = 2.0) -> str | None:
    """
    Creates a short title card clip (dark background + chapter title text).
    Used as a separator between chapters in long-form videos.
    """
    try:
        from moviepy import ColorClip, TextClip, CompositeVideoClip

        bg = ColorClip(size=(720, 1280), color=(13, 17, 23), duration=duration)

        txt = TextClip(
            text=chapter_title,
            font_size=52,
            color="#58A6FF",
            font="Arial-Bold",
            size=(650, None),
            method="caption",
        ).with_duration(duration)
        txt = txt.with_position("center")

        comp = CompositeVideoClip([bg, txt])
        comp.write_videofile(output_path, fps=30, codec="libx264", audio=False,
                             preset="ultrafast", logger=None)
        comp.close(); bg.close(); txt.close()
        return output_path
    except Exception as e:
        print(f"[Video Editor] Chapter card failed: {e}")
        return None


def create_long_video(chapter_clips: list, output_path: str = "long_video.mp4") -> str | None:
    """
    Stitches multiple chapter clips into a single long-form video.
    
    chapter_clips: list of dicts with keys:
        - chapter_title: str
        - animation_path: str (The pre-rendered chapter video with audio and subtitles)
    
    Each chapter = [title card (2s)] + [chapter animation]
    All chapters concatenated → final video.
    """
    from moviepy import VideoFileClip, concatenate_videoclips, ColorClip, CompositeVideoClip
    
    print(f"[LongForm Editor] Stitching {len(chapter_clips)} chapters...")
    all_clips = []
    temp_files = []

    for i, chapter in enumerate(chapter_clips):
        ch_title = chapter.get("chapter_title", f"Chapter {i+1}")
        anim_path = chapter.get("animation_path")

        if not anim_path or not os.path.exists(anim_path):
            print(f"[LongForm Editor] Skipping chapter {i} — no animation_path")
            continue

        # 1. Title card (2 seconds)
        card_path = anim_path.replace(".mp4", "_card.mp4")
        card = create_chapter_card(ch_title, card_path, duration=2.0)
        if card:
            try:
                card_clip = VideoFileClip(card)
                all_clips.append(card_clip)
                temp_files.append(card_path)
            except Exception as e:
                print(f"[LongForm Editor] Card load failed: {e}")

        # 2. Main chapter layout (already contains audio and subtitles from create_storyboard_video)
        try:
            chapter_video = VideoFileClip(anim_path)
            all_clips.append(chapter_video)
        except Exception as e:
            print(f"[LongForm Editor] Chapter {i} processing failed: {e}")
            continue

    if not all_clips:
        print("[LongForm Editor] No chapters rendered successfully.")
        return None

    # Concatenate all chapters
    try:
        print(f"[LongForm Editor] Concatenating {len(all_clips)} clips...")
        final = concatenate_videoclips(all_clips, method="chain")
        print(f"[LongForm Editor] Total duration: {final.duration:.1f}s ({final.duration/60:.1f} min)")

        final.write_videofile(
            output_path,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            bitrate="4000k",
            threads=4,
            preset="ultrafast",
            logger=None,
        )
        final.close()
        for c in all_clips:
            try: c.close()
            except: pass

        import gc; gc.collect()
        print(f"[LongForm Editor] ✅ Long video created: {output_path}")
        return output_path

    except Exception as e:
        print(f"[LongForm Editor] Concatenation failed: {e}")
        import traceback; traceback.print_exc()
        return None
    finally:
        # Clean up temp title card files
        for f in temp_files:
            if os.path.exists(f):
                try: os.remove(f)
                except: pass


def is_clip_healthy(video_path: str, min_duration: float = 1.0) -> tuple[bool, str]:
    """
    Checks an individual stock video clip for corruption or invalid duration.
    """
    import numpy as np

    if not video_path or not os.path.exists(video_path):
        return False, "File does not exist"

    file_size = os.path.getsize(video_path)
    if file_size < 10_000:  # Increased threshold to 10KB
        return False, f"File too small ({file_size} bytes)"

    try:
        # Use a context manager but ensure we catch init errors
        clip = VideoFileClip(video_path)
    except Exception as e:
        return False, f"Cannot open video/header corrupt: {e}"

    try:
        duration = clip.duration
        if duration is None or duration < min_duration:
            return False, f"Duration too short ({duration}s)"

        # Rigorous visual check: Sample frames at 10%, 30%, 50%, 70%, 90%
        sample_positions = [duration * p for p in [0.1, 0.3, 0.5, 0.7, 0.9]]
        frames = []
        
        for t in sample_positions:
            try:
                # Capture frame as numpy array (HxWx3)
                frame = clip.get_frame(t)
                frames.append(frame.astype(np.float32))
            except Exception as e:
                print(f"[is_clip_healthy] Frame extraction error at {t}s: {e}")
                return False, f"Frame extraction failure at {t}s"

        if len(frames) < 3:
            return False, "Could not extract enough frames for validation"

        # 1. Total Corruption / Black/Green Screen Check
        # Pure green (0, 255, 0) or pure black
        bad_frames = 0
        for frame in frames:
            mean_r, mean_g, mean_b = frame.mean(axis=(0, 1))
            total_mean = frame.mean()
            
            # Pure green check
            if (mean_r < 5 and mean_g > 250 and mean_b < 5):
                bad_frames += 1
            # Pure black check
            elif total_mean < 2.0:
                bad_frames += 1
            # Static/Noisy check: Scan-line variance
            else:
                row_means = frame.mean(axis=(1, 2))
                row_variance = float(np.var(row_means))
                if row_variance < 5.0:
                    bad_frames += 1

        if bad_frames >= 2:
            return False, f"Visual corruption detected ({bad_frames}/5 frames bad)"

        # 2. Frozen Frame Check: Compare frames for near-perfect identity
        # (Indicates the video is just a still image or frozen)
        similarities = 0
        for i in range(len(frames) - 1):
            diff = np.abs(frames[i] - frames[i+1]).mean()
            if diff < 0.5: # Extremely similar frames
                similarities += 1
        
        if similarities >= len(frames) - 1:
            return False, "Video is frozen or a still image"

        return True, "OK"
    except Exception as e:
        return False, f"Validation logic crash: {e}"
    finally:
        try:
            clip.close()
            # Explicitly clear from memory
            del clip
        except:
            pass

def validate_render(video_path: str, min_duration: float = 5.0) -> tuple[bool, str]:
    """
    Validates that a rendered MP4 is decodable and visually sane.
    Now re-uses is_clip_healthy.
    """
    return is_clip_healthy(video_path, min_duration=min_duration)


def create_storyboard_video(beats: list, output_path: str,
                             worker_id: int = 0, manim_enabled: bool = True,
                             target_size: tuple = (720, 1280)) -> str | None:
    """
    "Real edit" pipeline — builds one video clip per storyboard beat,
    each with its OWN precisely-timed Manim animation synced to the voiceover.
    Finally burns styled subtitles into the final video.

    beats: list of {id, text, visual_action, visual_data}
    target_size: (width, height). Default is portrait. Use (1920, 1080) for landscape.
    """
    from moviepy import VideoFileClip, AudioFileClip, concatenate_videoclips, ColorClip
    from moviepy.video.fx.Loop import Loop as loop_clip
    from voiceover import generate_voiceover
    from beat_renderer import render_beat, generate_srt, burn_subtitles

    TEMP = "temp"
    os.makedirs(TEMP, exist_ok=True)
    TARGET_SIZE = target_size

    beat_clips       = []
    beats_with_timing = []
    current_sec       = 0.0

    for i, beat in enumerate(beats):
        text          = beat.get("text", "")
        visual_action = beat.get("visual_action", "text_only")
        visual_data   = beat.get("visual_data", {})

        if not text.strip():
            continue

        # ── 1. Audio for this beat ────────────────────────────────────────────
        audio_path = os.path.join(TEMP, f"sb_{worker_id}_b{i}_audio.mp3")
        audio_ok = generate_voiceover(text, audio_path)
        if not audio_ok or not os.path.exists(audio_path):
            print(f"[Storyboard] Beat {i} audio failed, skipping")
            continue

        # ── 2. Exact duration from audio ─────────────────────────────────────
        try:
            with AudioFileClip(audio_path) as ac:
                dur = round(ac.duration, 3)
        except Exception as e:
            print(f"[Storyboard] Beat {i} duration read failed: {e}")
            dur = 5.0

        # ── 3. Subtitle timing record ─────────────────────────────────────────
        beats_with_timing.append({
            "text":      text,
            "start_sec": current_sec,
            "end_sec":   current_sec + dur,
        })
        current_sec += dur

        # ── 4. Manim animation for exact duration ─────────────────────────────
        anim_path = os.path.join(TEMP, f"sb_{worker_id}_b{i}_anim.mp4")
        rendered  = None

        if manim_enabled:
            rendered = render_beat(visual_action, visual_data, dur, anim_path)

        # ── 5. Assemble beat clip (animation + audio) ─────────────────────────
        try:
            if rendered and os.path.exists(rendered):
                bg = VideoFileClip(rendered)
                # Resize to portrait if needed while preserving aspect ratio
                if bg.size != list(TARGET_SIZE):
                    bg = bg.resized(height=TARGET_SIZE[1])
                    if bg.w > TARGET_SIZE[0]:
                        bg = bg.cropped(x_center=bg.w/2, width=TARGET_SIZE[0])
                    else:
                        bg = bg.resized(TARGET_SIZE)  # fallback if height ratio misses
                # Loop or trim to match audio
                if bg.duration < dur:
                    bg = bg.with_effects([loop_clip(duration=dur)])
                bg = bg.subclipped(0, dur)
            else:
                # Dark background fallback
                bg = ColorClip(size=TARGET_SIZE, color=(13, 17, 23), duration=dur)

            audio_clip = AudioFileClip(audio_path)
            beat_video = bg.with_audio(audio_clip)
            beat_clips.append(beat_video)
            print(f"[Storyboard] Beat {i} [{visual_action}] ✅ {dur:.1f}s")

        except Exception as e:
            print(f"[Storyboard] Beat {i} assembly failed: {e}")
            continue

    if not beat_clips:
        print("[Storyboard] No beats rendered — aborting")
        return None

    # ── 6. Concatenate all beats ──────────────────────────────────────────────
    raw_path = output_path.replace(".mp4", "_nosubs.mp4")
    try:
        final = concatenate_videoclips(beat_clips, method="chain")
        print(f"[Storyboard] Stitching {len(beat_clips)} beats, total {final.duration:.1f}s")
        final.write_videofile(
            raw_path, fps=MANIM_FPS if False else 30,
            codec="libx264", audio_codec="aac",
            bitrate="4000k", threads=4, preset="ultrafast", logger=None,
        )
        final.close()
        for c in beat_clips:
            try: c.close()
            except: pass
    except Exception as e:
        print(f"[Storyboard] Concatenation failed: {e}")
        import traceback; traceback.print_exc()
        return None

    # ── 7. Generate SRT + burn subtitles ─────────────────────────────────────
    srt_content = generate_srt(beats_with_timing)
    srt_path    = output_path.replace(".mp4", ".srt")
    try:
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(srt_content)

        result = burn_subtitles(raw_path, srt_path, output_path)
        if not result:
            print("[Storyboard] Subtitle burn failed — returning video without subs")
            import shutil
            shutil.copy(raw_path, output_path)
    except Exception as e:
        print(f"[Storyboard] Subtitle step failed: {e}")
        import shutil
        shutil.copy(raw_path, output_path)
    finally:
        for p in [raw_path, srt_path]:
            try: os.remove(p)
            except: pass

    print(f"[Storyboard] ✅ Final video with subtitles: {output_path}")
    return output_path, beats_with_timing


if __name__ == "__main__":
    print("Run module from main script.")
