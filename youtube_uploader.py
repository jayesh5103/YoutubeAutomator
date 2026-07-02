import os
import logging
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

logger = logging.getLogger("YoutubeAutomator")

# Scopes needed: upload + comment posting + analytics
SCOPES = [
    'https://www.googleapis.com/auth/youtube.upload',
    'https://www.googleapis.com/auth/youtube.force-ssl',
    'https://www.googleapis.com/auth/yt-analytics.readonly',
    'https://www.googleapis.com/auth/youtube.readonly'
]

def get_authenticated_service():
    """
    Authenticates the user and returns the YouTube Data API service.
    In headless mode (GitHub Actions), only token refresh is attempted — no browser auth.
    """
    import json
    headless = os.getenv("HEADLESS_MODE", "false").lower() == "true"
    creds = None
    # Invalidate token if scopes mismatch
    if os.path.exists('token.json'):
        try:
            with open('token.json', 'r') as token_file:
                token_data = json.load(token_file)
            token_scopes = token_data.get('scopes', [])
            if not all(s in token_scopes for s in SCOPES):
                if headless:
                    logger.error("[YouTube] token.json lacks required scopes and cannot re-auth in headless mode.")
                    logger.error("[YouTube] Re-generate token.json locally and update GOOGLE_OAUTH_TOKEN secret.")
                    return None
                logger.warning("[YouTube] token.json lacks new required scopes. Deleting it to trigger re-auth...")
                os.remove('token.json')
        except Exception as e:
            logger.error(f"[YouTube] Error checking token scopes: {e}")

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # Save refreshed token back for future runs
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())
                logger.info("[YouTube] Access token refreshed successfully.")
            except Exception as e:
                logger.error(f"[YouTube] Failed to refresh token: {e}")
                creds = None
        
        if not creds or not creds.valid:
            if headless:
                logger.error("[YouTube] Cannot authenticate in headless mode — no valid token available.")
                logger.error("[YouTube] Run locally first to generate token.json, then update GOOGLE_OAUTH_TOKEN secret.")
                return None

            if not os.path.exists('client_secrets.json'):
                logger.error("[YouTube] ERROR: client_secrets.json not found! Please download it from Google Cloud Console.")
                return None
                
            flow = InstalledAppFlow.from_client_secrets_file('client_secrets.json', SCOPES)
            creds = flow.run_local_server(port=0)
            
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build('youtube', 'v3', credentials=creds)

def upload_video(video_path, title, description, tags, category_id="22", privacy_status="public", schedule_time=None):
    """
    Uploads a video to YouTube. Supports scheduling via schedule_time (ISO string).
    """
    # Sanitize title: unescape HTML entities and enforce YouTube's 100-char limit
    import html
    title = html.unescape(title or "").strip()
    if not title:
        title = "Amazing Hindi Facts #Shorts"
    title = title[:100]  # YouTube max title length

    logger.info(f"[YouTube] Preparing to upload {video_path}...")

    youtube = get_authenticated_service()
    if not youtube:
        logger.error("[YouTube] Authentication service not available.")
        return False

    body = {
        'snippet': {
            'title': title,
            'description': description,
            'tags': tags,
            'categoryId': category_id
        },
        'status': {
            'privacyStatus': 'private' if schedule_time else privacy_status,
            'selfDeclaredMadeForKids': False
        }
    }
    if schedule_time:
        body['status']['publishAt'] = schedule_time

    # Use a specific chunksize (5MB) for more reliable uploads on unstable connections
    media = MediaFileUpload(video_path, chunksize=1024*1024*5, resumable=True)

    insert_request = youtube.videos().insert(
        part=','.join(body.keys()),
        body=body,
        media_body=media
    )

    try:
        logger.info(f"[YouTube] Executing upload for: {title}")
        response = None
        while response is None:
            status, response = insert_request.next_chunk()
            if status:
                logger.info(f"[YouTube] Upload progress: {int(status.progress() * 100)}%")

        video_id = response.get('id')
        logger.info(f"[YouTube] ✅ Uploaded successfully! ID: {video_id} | URL: https://youtu.be/{video_id}")
        return video_id
    except Exception as e:
        logger.error(f"[YouTube] ❌ Upload failed: {e}")
        # Common causes: token expired, quota exceeded, bad file path
        if 'uploadLimitExceeded' in str(e) or 'uploadlimitexceeded' in str(e).lower():
            logger.warning("[YouTube] ⚠️  Daily upload limit exceeded. No more uploads will be attempted today.")
            return "QUOTA_EXCEEDED"
        elif 'quota' in str(e).lower():
            logger.warning("[YouTube] ⚠️  API quota exceeded. Try again tomorrow.")
            return "QUOTA_EXCEEDED"
        elif 'token' in str(e).lower() or 'auth' in str(e).lower():
            logger.warning("[YouTube] ⚠️  Auth error. Delete token.json and re-authenticate.")
        elif not os.path.exists(video_path):
            logger.warning(f"[YouTube] ⚠️  File not found: {video_path}")
        return None

def post_first_comment(video_id, text):
    """
    Posts the first comment on a video and pins it if possible.
    """
    youtube = get_authenticated_service()
    if not youtube:
        return False
        
    logger.info(f"[YouTube] Posting comment on video {video_id}: {text}")
    try:
        youtube.commentThreads().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "topLevelComment": {
                        "snippet": {
                            "textOriginal": text
                        }
                    }
                }
            }
        ).execute()
        return True
    except Exception as e:
        logger.error(f"[YouTube] Error posting comment: {e}")
        return False

def get_video_stats(video_id):
    """
    Fetches view count, like count, and comment count for a specific video.
    """
    youtube = get_authenticated_service()
    if not youtube:
        return None
        
    try:
        response = youtube.videos().list(
            part="statistics",
            id=video_id
        ).execute()
        
        if not response['items']:
            return None
            
        stats = response['items'][0]['statistics']
        return {
            "views": int(stats.get('viewCount', 0)),
            "likes": int(stats.get('likeCount', 0)),
            "comments": int(stats.get('commentCount', 0))
        }
    except Exception as e:
        logger.error(f"[YouTube] Error fetching stats for {video_id}: {e}")
        return None

def get_batch_video_stats(video_ids):
    """
    Fetches stats for a list of video IDs (up to 50) in a single request.
    """
    if not video_ids: return {}
    
    youtube = get_authenticated_service()
    if not youtube:
        return {}
        
    try:
        # Join IDs with commas
        id_query = ",".join(video_ids)
        response = youtube.videos().list(
            part="statistics",
            id=id_query
        ).execute()
        
        results = {}
        for item in response.get('items', []):
            vid = item['id']
            stats = item['statistics']
            results[vid] = {
                "views": int(stats.get('viewCount', 0)),
                "likes": int(stats.get('likeCount', 0)),
                "comments": int(stats.get('commentCount', 0))
            }
        return results
    except Exception as e:
        logger.error(f"[YouTube] Error fetching batch stats: {e}")
        return {}

def get_channel_stats():
    """
    Fetches the authenticated channel's name, subscriber count, and total view count.
    """
    youtube = get_authenticated_service()
    if not youtube:
        return None
        
    try:
        # 'mine=True' fetches the channel info for the authenticated user
        response = youtube.channels().list(
            part="snippet,statistics",
            mine=True
        ).execute()
        
        if not response['items']:
            return None
            
        channel = response['items'][0]
        snippet = channel['snippet']
        stats = channel['statistics']
        
        return {
            "name": snippet['title'],
            "subscribers": int(stats.get('subscriberCount', 0)),
            "total_views": int(stats.get('viewCount', 0)),
            "video_count": int(stats.get('videoCount', 0))
        }
    except Exception as e:
        logger.error(f"[YouTube] Error fetching channel stats: {e}")
        return None

if __name__ == '__main__':
    # upload_video('final_video.mp4', 'Test Video', 'Test Description', ['test'])
    pass
