"""
YouTube Intelligence Engine
===========================
The bot's "brain" — it watches YouTube to understand what DSA/coding topics
are trending right now, analyzes competitor channels, and uses Groq AI to
decide what videos to produce next.

Uses the existing OAuth token (same as upload) — the 'youtube.force-ssl'
scope allows reading search results, video stats, and channel data.

Competitor Channels Watched:
  - NeetCode, CodeWithHarry, TakeUForward (Striver), Apna College,
    Abdul Bari, Love Babbar (CodeHelp), Kunal Kushwaha
"""

import os
import json
import logging
import sqlite3
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("YoutubeAutomator")

# ─── COMPETITOR CHANNELS + SEARCH QUERIES ────────────────────────────────────

# These are searched by channel name — we find their latest videos automatically
# Covers both Indian and global coding educators
COMPETITOR_CHANNELS = [
    "NeetCode",
    "CodeWithHarry",
    "takeUforward",
    "Apna College",
    "Abdul Bari",
    "CodeHelp - by Babbar",
    "Kunal Kushwaha",
    "Aditya Verma",
]

# High-intent DSA search queries — what students actually search for
TREND_SEARCH_QUERIES = [
    "DSA tutorial Hindi 2025",
    "LeetCode solution explained Hindi",
    "data structures algorithms beginner Hindi",
    "coding interview preparation DSA",
    "graph algorithms tutorial",
    "dynamic programming explained Hindi",
    "binary tree problems LeetCode",
    "system design interview Hindi",
    "recursion backtracking tutorial",
    "sorting algorithms visualization",
]

# How many days back to look for trending videos
TREND_WINDOW_DAYS = 7
MAX_RESULTS_PER_QUERY = 10


def _get_youtube_service():
    """Reuses the existing OAuth service from youtube_uploader.py"""
    from youtube_uploader import get_authenticated_service
    return get_authenticated_service()


def fetch_trending_dsa_videos() -> list:
    """
    Searches YouTube for the most-viewed DSA/coding videos published in the
    last 7 days. Returns a list of {title, views, likes, channel, published_at}.
    """
    youtube = _get_youtube_service()
    if not youtube:
        logger.error("[Intelligence] Cannot connect to YouTube API.")
        return []

    published_after = (datetime.utcnow() - timedelta(days=TREND_WINDOW_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    all_video_data = []
    seen_ids = set()

    for query in TREND_SEARCH_QUERIES[:5]:  # Limit to 5 queries to save quota
        try:
            logger.info(f"[Intelligence] Searching: '{query}'")
            search_resp = youtube.search().list(
                q=query,
                part="snippet",
                type="video",
                maxResults=MAX_RESULTS_PER_QUERY,
                publishedAfter=published_after,
                order="viewCount",
                relevanceLanguage="hi",  # Prefer Hindi/Indian content
            ).execute()

            video_ids = []
            for item in search_resp.get("items", []):
                vid_id = item["id"]["videoId"]
                if vid_id not in seen_ids:
                    video_ids.append(vid_id)
                    seen_ids.add(vid_id)

            if not video_ids:
                continue

            # Fetch stats for these videos in one batch call
            stats_resp = youtube.videos().list(
                part="statistics,snippet,contentDetails",
                id=",".join(video_ids),
            ).execute()

            for item in stats_resp.get("items", []):
                stats = item.get("statistics", {})
                snippet = item.get("snippet", {})
                all_video_data.append({
                    "title": snippet.get("title", ""),
                    "channel": snippet.get("channelTitle", ""),
                    "views": int(stats.get("viewCount", 0)),
                    "likes": int(stats.get("likeCount", 0)),
                    "comments": int(stats.get("commentCount", 0)),
                    "published_at": snippet.get("publishedAt", ""),
                    "description": snippet.get("description", "")[:200],
                    "tags": snippet.get("tags", [])[:5],
                    "duration": item.get("contentDetails", {}).get("duration", ""),
                })

            time.sleep(0.5)  # Be gentle with the API

        except Exception as e:
            logger.warning(f"[Intelligence] Search query failed for '{query}': {e}")
            continue

    logger.info(f"[Intelligence] Fetched {len(all_video_data)} trending videos.")
    return sorted(all_video_data, key=lambda x: x["views"], reverse=True)


def fetch_competitor_latest_videos() -> list:
    """
    Finds the latest 3 videos from each competitor channel published in the
    last 7 days.
    """
    youtube = _get_youtube_service()
    if not youtube:
        return []

    published_after = (datetime.utcnow() - timedelta(days=TREND_WINDOW_DAYS)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    competitor_videos = []

    for channel_name in COMPETITOR_CHANNELS:
        try:
            # Search for the channel's recent videos
            search_resp = youtube.search().list(
                q=channel_name,
                part="snippet",
                type="video",
                maxResults=3,
                publishedAfter=published_after,
                order="date",
            ).execute()

            for item in search_resp.get("items", []):
                if channel_name.lower() in item["snippet"].get("channelTitle", "").lower():
                    competitor_videos.append({
                        "channel": item["snippet"]["channelTitle"],
                        "title": item["snippet"]["title"],
                        "video_id": item["id"]["videoId"],
                    })

            time.sleep(0.3)

        except Exception as e:
            logger.warning(f"[Intelligence] Failed to fetch for channel '{channel_name}': {e}")
            continue

    logger.info(f"[Intelligence] Found {len(competitor_videos)} competitor videos.")
    return competitor_videos


def analyze_trends_with_ai(trending_videos: list, competitor_videos: list) -> list:
    """
    Sends the trend data to Groq AI. Groq analyzes the landscape and returns:
    - Which DSA topics are trending RIGHT NOW
    - What gaps exist (topics competitors haven't covered yet)
    - Specific video topic titles we should produce, with rationale
    
    Returns list of {topic, score, rationale}
    """
    from groq import Groq

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        logger.error("[Intelligence] No GROQ_API_KEY set.")
        return []

    # Prepare compact summary for the prompt
    top_videos_summary = "\n".join([
        f"- '{v['title']}' by {v['channel']} | {v['views']:,} views"
        for v in trending_videos[:15]
    ])

    competitor_summary = "\n".join([
        f"- {v['channel']}: '{v['title']}'"
        for v in competitor_videos[:15]
    ])

    prompt = f"""You are a YouTube content strategist for a Hinglish coding education channel targeting Indian engineering students.

TRENDING DSA VIDEOS THIS WEEK (by views):
{top_videos_summary if top_videos_summary else "No data available"}

WHAT COMPETITORS RECENTLY PUBLISHED:
{competitor_summary if competitor_summary else "No data available"}

YOUR TASK:
Analyze the above data and identify the 10 best video topics for our channel to produce RIGHT NOW.
Consider:
1. Topics with HIGH viewer demand (many popular videos = proven demand)
2. Topics competitors just covered = still hot, we can cover from a different angle
3. Topics that are MISSING from competitors but clearly needed
4. Topics that suit Indian students (placement, FAANG prep, Hinglish style)

Respond with EXACTLY this JSON format (no extra text):
[
  {{"topic": "Binary Search - Aur Common Mistakes", "score": 95, "rationale": "NeetCode's video got 400K views, demand proven", "video_type": "short"}},
  {{"topic": "Recursion Concept - Dabba Analogy", "score": 90, "rationale": "High demand for beginner concepts in Hinglish", "video_type": "short"}},
  ...
]

Rules:
- "score": 60-100 (higher = more urgent to produce)
- "video_type": MUST ALWAYS BE "short" (50-60s for YouTube Shorts)
- Topic titles should be in Hinglish style (mix Hindi + English)
- Prioritize topics that Indian students search for during placement prep
"""

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": "You are a YouTube content strategist. Always respond with valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=1500,
            temperature=0.7,
        )

        raw = response.choices[0].message.content.strip()

        # Extract JSON from response
        if "```" in raw:
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]

        suggestions = json.loads(raw)
        logger.info(f"[Intelligence] AI suggested {len(suggestions)} topics.")
        return suggestions

    except json.JSONDecodeError as e:
        logger.error(f"[Intelligence] AI response was not valid JSON: {e}")
        return []
    except Exception as e:
        logger.error(f"[Intelligence] AI analysis failed: {e}")
        return []


def seed_intelligent_topics() -> int:
    """
    Main entry point: fetches trends, asks AI, stores in DB.
    Returns number of new topics inserted.
    
    Safe to call multiple times — only fetches fresh data if >6 hours since last run.
    """
    from database import DB_PATH

    # Check if we ran recently (don't hammer the YouTube API)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM system_config WHERE key = 'intelligence_last_run'")
    row = cursor.fetchone()
    conn.close()

    if row:
        last_run = float(row[0])
        hours_since = (time.time() - last_run) / 3600
        if hours_since < 6:
            logger.info(f"[Intelligence] Skipping — ran {hours_since:.1f}h ago (threshold: 6h)")
            return 0

    logger.info("[Intelligence] 🧠 Starting YouTube trend analysis...")

    # 1. Fetch data
    trending = fetch_trending_dsa_videos()
    competitors = fetch_competitor_latest_videos()

    if not trending and not competitors:
        logger.warning("[Intelligence] No data fetched. Using static fallback topics.")
        return 0

    # 2. AI analysis
    suggestions = analyze_trends_with_ai(trending, competitors)

    if not suggestions:
        logger.warning("[Intelligence] AI returned no suggestions.")
        return 0

    # Score and rank topics using the learning engine
    try:
        from learning_engine import LearningEngine
        candidate_names = [s.get("topic", "").strip() for s in suggestions if s.get("topic")]
        ranked_topics = LearningEngine.score_and_rank_topics(candidate_names)
        ranked_scores = dict(ranked_topics)
        for s in suggestions:
            topic_name = s.get("topic", "").strip()
            if topic_name in ranked_scores:
                s["score"] = ranked_scores[topic_name]
    except Exception as le_err:
        logger.error(f"[Intelligence] Failed to rank candidate topics: {le_err}")

    # 3. Store in DB
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    inserted = 0

    for s in suggestions:
        topic = s.get("topic", "").strip()
        score = float(s.get("score", 80))
        video_type = "short" # Force shorts: s.get("video_type", "short")
        rationale = s.get("rationale", "")

        # Only Shorts allowed now
        tagged_topic = topic # f"[{video_type}] {topic}" if video_type == "long" else topic

        try:
            cursor.execute(
                "INSERT OR IGNORE INTO trends (topic, score, timestamp) VALUES (?, ?, ?)",
                (tagged_topic, score, datetime.now())
            )
            if cursor.rowcount > 0:
                inserted += 1
                logger.info(f"[Intelligence] ➕ New topic: {tagged_topic} (score={score:.0f}) — {rationale}")
        except Exception as e:
            logger.warning(f"[Intelligence] Could not insert '{topic}': {e}")

    # Record last run time
    cursor.execute(
        "INSERT OR REPLACE INTO system_config (key, value, updated_at) VALUES (?, ?, ?)",
        ("intelligence_last_run", str(time.time()), datetime.now())
    )
    conn.commit()
    conn.close()

    logger.info(f"[Intelligence] ✅ Seeded {inserted} AI-suggested topics.")
    return inserted


def get_intelligence_report() -> str:
    """Returns a human-readable summary of the last intelligence run for the GUI."""
    from database import DB_PATH
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT topic, score FROM trends WHERE used = 0 ORDER BY score DESC LIMIT 10"
    )
    rows = cursor.fetchall()
    cursor.execute("SELECT value FROM system_config WHERE key = 'intelligence_last_run'")
    last_row = cursor.fetchone()
    conn.close()

    last_run_str = "Never"
    if last_row:
        ts = float(last_row[0])
        last_run_str = datetime.fromtimestamp(ts).strftime("%d %b %H:%M")

    lines = [f"🧠 Intelligence Engine — Last run: {last_run_str}\n"]
    lines.append("Top Pending Topics:")
    for topic, score in rows:
        lines.append(f"  [{score:.0f}] {topic}")

    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv
    from database import init_db
    load_dotenv()
    init_db()

    if "--report" in sys.argv:
        print(get_intelligence_report())
    else:
        print("🧠 Running YouTube Intelligence Engine...")
        count = seed_intelligent_topics()
        print(f"✅ Inserted {count} new AI-suggested topics.")
        print()
        print(get_intelligence_report())
