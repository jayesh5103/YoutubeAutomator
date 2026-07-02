import os
import shutil
import glob

TEMP_DIR = "temp"

def cleanup_temp_files():
    """
    Removes temporary background clips, audio files, and intermediate moviepy files.
    """
    if not os.path.exists(TEMP_DIR):
        os.makedirs(TEMP_DIR, exist_ok=True)
        
    patterns = [
        os.path.join(TEMP_DIR, "bg_clip_*.mp4"),
        os.path.join(TEMP_DIR, "test_bg_clip_*.mp4"),
        os.path.join(TEMP_DIR, "test_long_bg_clip_*.mp4"),
        os.path.join(TEMP_DIR, "temp_audio*.mp3"),
        os.path.join(TEMP_DIR, "test_audio*.mp3"),
        os.path.join(TEMP_DIR, "downloaded_background.mp4"),
        os.path.join(TEMP_DIR, "final_video*.mp4"),
        os.path.join(TEMP_DIR, "*TEMP_MPY_*.mp4"),
        os.path.join(TEMP_DIR, "*TEMP_MPY_*.mp3"),
        os.path.join(TEMP_DIR, "sb_*"),
        "*.mp4.slot",           # MoviePy artifacts (usually in root)
    ]
    
    # Also clean legacy files in root if they exist
    patterns += [
        "bg_clip_*.mp4",
        "test_bg_clip_*.mp4",
        "temp_audio*.mp3",
        "test_audio*.mp3",
        "final_video*.mp4"
    ]
    
    files_removed = 0
    for pattern in patterns:
        for file_path in glob.glob(pattern):
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    files_removed += 1
            except Exception as e:
                print(f"[Cleanup] Error removing {file_path}: {e}")
                
    if files_removed > 0:
        print(f"[Cleanup] Removed {files_removed} temporary files.")

def enforce_retention(keep_last_n=10):
    """
    Deletes older video renders, keeping only the most recent N files.
    """
    render_dir = "renders"
    if not os.path.exists(render_dir):
        return

    files = glob.glob(os.path.join(render_dir, "video_*.mp4"))
    # Sort by modification time (newest first)
    files.sort(key=os.path.getmtime, reverse=True)

    if len(files) > keep_last_n:
        to_delete = files[keep_last_n:]
        for f in to_delete:
            try:
                os.remove(f)
            except Exception as e:
                print(f"[Cleanup] Error deleting old render {f}: {e}")
        print(f"[Cleanup] Retention policy: Removed {len(to_delete)} old renders.")

def organize_render(video_path):
    """
    Moves the final video to a 'renders' folder and renames it with a timestamp.
    """
    from datetime import datetime
    
    if not video_path or not os.path.exists(video_path):
        return None
        
    render_dir = "renders"
    if not os.path.exists(render_dir):
        os.makedirs(render_dir)
        
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    new_name = f"video_{timestamp}.mp4"
    dest_path = os.path.join(render_dir, new_name)
    
    try:
        shutil.move(video_path, dest_path)
        print(f"[Cleanup] Organized final video to: {dest_path}")
        # Enforce retention after organizing a new render
        enforce_retention()
        return dest_path
    except Exception as e:
        print(f"[Cleanup] Error organizing video: {e}")
        return video_path

def archive_uploaded_video(video_path):
    """
    Moves an uploaded video from 'renders' to 'renders/uploaded' to prevent duplicate uploads.
    """
    if not video_path or not os.path.exists(video_path):
        return
        
    render_dir = os.path.dirname(video_path)
    if os.path.basename(render_dir) == "uploaded":
        return  # Already archived
        
    uploaded_dir = os.path.join("renders", "uploaded")
    if not os.path.exists(uploaded_dir):
        os.makedirs(uploaded_dir)
        
    filename = os.path.basename(video_path)
    dest_path = os.path.join(uploaded_dir, filename)
    
    try:
        shutil.move(video_path, dest_path)
        print(f"[Cleanup] Archived uploaded video to: {dest_path}")
    except Exception as e:
        print(f"[Cleanup] Error archiving video: {e}")

def delete_uploaded_videos():
    """
    Deletes all video files in the 'renders/uploaded' directory.
    """
    uploaded_dir = os.path.join("renders", "uploaded")
    if not os.path.exists(uploaded_dir):
        print("[Cleanup] No uploaded videos found to delete.")
        return

    files = glob.glob(os.path.join(uploaded_dir, "*.mp4"))
    files_deleted = 0
    for f in files:
        try:
            os.remove(f)
            files_deleted += 1
        except Exception as e:
            print(f"[Cleanup] Error deleting uploaded video {f}: {e}")
            
    if files_deleted > 0:
        print(f"[Cleanup] Deleted {files_deleted} uploaded videos.")
    else:
        print("[Cleanup] No uploaded videos to delete.")
