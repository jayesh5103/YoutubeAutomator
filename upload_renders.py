
import os
import logging
from youtube_uploader import upload_video, post_first_comment
from database import log_video, init_db
from utils import cleanup_temp_files

# Configure logging to console as well
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("YoutubeAutomator")

# Known metadata for existing renders
MANUAL_METADATA = {
    "video_20260315_221059.mp4": {
        "title": "Space Travel के बारे में हैरान कर देने वाली बातें! #Shorts",
        "topic": "Space Travel",
        "niche": "Technology"
    },
    "video_20260315_222031.mp4": {
        "title": "Espresso History: कॉफ़ी का असली सच! #Shorts",
        "topic": "Espresso History",
        "niche": "History"
    },
    "video_20260316_140839.mp4": {
        "title": "Viral Facts जो आपको हैरान कर देंगे! #Shorts",
        "topic": "Viral Facts",
        "niche": "Entertainment"
    }
}


def bulk_upload():
    init_db()
    render_dir = "renders"
    if not os.path.exists(render_dir):
        print("Renders directory not found.")
        return

    files = [f for f in os.listdir(render_dir) if f.endswith(".mp4")]
    if not files:
        print("No videos found in renders/")
        return

    logger.info(f"Found {len(files)} videos to upload.")

    for filename in files:
        video_path = os.path.join(render_dir, filename)
        
        metadata = MANUAL_METADATA.get(filename, {
            "title": "Amazing Hindi Facts #Shorts",
            "topic": "Viral Facts",
            "niche": "Entertainment"
        })

        logger.info(f"Uploading {filename} as '{metadata['title']}'...")
        
        video_id = upload_video(
            video_path,
            metadata['title'],
            f"यह वीडियो {metadata['topic']} के बारे में है। ऐसी और भी रोचक जानकारी के लिए सब्सक्राइब करें!",
            ["hindi", "facts", "trending", metadata['topic']]
        )

        if video_id == "QUOTA_EXCEEDED":
            logger.warning("⚠️  Daily upload limit reached. Stopping all uploads — will retry in next scheduled run.")
            break
        elif video_id:
            log_video(video_id, metadata['title'], metadata['topic'], metadata['niche'])
            post_first_comment(video_id, "क्या आपको यह पता था? 🤔 कमेंट्स में बताएं!")
            logger.info(f"✅ Successfully uploaded and logged: {filename} -> {video_id}")
            
            # Optional: Move to an 'uploaded' folder
            uploaded_dir = os.path.join(render_dir, "uploaded")
            if not os.path.exists(uploaded_dir):
                os.makedirs(uploaded_dir)
            os.rename(video_path, os.path.join(uploaded_dir, filename))
        else:
            logger.error(f"❌ Failed to upload {filename}")

    # Perform cleanup of temporary files after processing renders
    logger.info("Starting cleanup of temporary files...")
    cleanup_temp_files()

if __name__ == "__main__":
    bulk_upload()
