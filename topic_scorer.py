import sqlite3
import random
import logging
from datetime import datetime
from database import DB_PATH

logger = logging.getLogger("YoutubeAutomator")

TRACKED_KEYWORDS = [
    "binary search", "two pointer", "sliding window", "hashmap", "hashing",
    "linked list", "bubble sort", "selection sort", "insertion sort",
    "merge sort", "quick sort", "recursion", "backtracking", "dynamic programming",
    "dp", "stack", "queue", "bst", "binary tree", "avl tree", "heap", "priority queue",
    "bfs", "dfs", "dijkstra", "bellman-ford", "topological sort", "union find",
    "trie", "segment tree", "fenwick tree", "kmp", "rabin-karp", "lru cache", "lfu cache",
    "bit manipulation", "greedy", "sorting", "complexity", "big o", "time complexity",
    "space complexity", "system design", "scalability", "load balancer", "caching",
    "palindrome", "anagram", "knapsack", "lcs", "longest common subsequence"
]

def categorize_topic(topic: str) -> str:
    """
    Categorizes a topic into one of the standard DSA categories.
    """
    topic_lower = topic.lower()
    categories = {
        'trees': ['tree', 'binary tree', 'bst', 'avl', 'trie', 'segment tree', 'fenwick'],
        'searching': ['search', 'binary search', 'find', 'lookup'],
        'sorting': ['sort', 'bubble', 'selection', 'insertion', 'merge', 'quick', 'heap sort', 'dutch national'],
        'dp': ['dynamic programming', 'dp', 'memoization', 'tabulation', 'knapsack', 'lcs', 'longest common', 'coin change', 'fibonacci'],
        'graphs': ['graph', 'bfs', 'dfs', 'dijkstra', 'bellman', 'topological', 'union find', 'articulation', 'bridge', 'path'],
        'strings': ['string', 'palindrome', 'anagram', 'kmp', 'rabin-karp', 'z-algorithm', 'pattern matching', 'manacher'],
    }
    for cat, keywords in categories.items():
        if any(kw in topic_lower for kw in keywords):
            return cat
    return 'other'

def extract_keywords(topic: str) -> list[str]:
    """
    Extracts relevant keywords from a topic. Falls back to significant word tokens.
    """
    topic_lower = topic.lower()
    matched = []
    for kw in TRACKED_KEYWORDS:
        if kw in topic_lower:
            matched.append(kw)
    if not matched:
        # Fall back to single word tokens, filtering out common words
        words = [w.strip("?,.:!\"'") for w in topic_lower.split()]
        stop_words = {"yeh", "kya", "hota", "hai", "aur", "kab", "use", "karein", "ekdum", "clear", 
                      "explanation", "se", "samjho", "ko", "simply", "ka", "concept", "apne", "aap", 
                      "pe", "classic", "problem", "farak", "vs", "kyun", "kab", "kya", "bhai", "yaar"}
        matched = [w for w in words if len(w) > 3 and w not in stop_words]
    return list(set(matched))

def score_topic(topic: str, keyword_weight_map: dict) -> float:
    """
    Scores a topic by checking its keywords against the keyword weight map.
    New/unseen keywords get a neutral score of 50.0.
    """
    keywords = extract_keywords(topic)
    if not keywords:
        return 50.0

    scores = []
    for kw in keywords:
        if kw in keyword_weight_map:
            scores.append(keyword_weight_map[kw])
        else:
            scores.append(50.0) # neutral score

    return sum(scores) / len(scores)

def get_keyword_weight_map() -> dict:
    """
    Returns the keyword weights map from the database.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT keyword, avg_score FROM keyword_weights")
    weights = {row[0]: row[1] for row in cursor.fetchall()}
    conn.close()
    return weights

def record_topic_selection(video_id: str, topic: str, niche: str):
    """
    Inserts initial records in topic_performance for each keyword of the selected topic.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    category = categorize_topic(topic)
    keywords = extract_keywords(topic)
    
    for kw in keywords:
        cursor.execute('''
        INSERT OR IGNORE INTO topic_performance 
        (keyword, niche, algorithm_category, video_id, performance_score, views, likes, watch_time_minutes, recorded_at)
        VALUES (?, ?, ?, ?, NULL, 0, 0, 0.0, ?)
        ''', (kw, niche, category, video_id, datetime.now()))
        
    conn.commit()
    conn.close()
    logger.info(f"[Topic Intelligence] Recorded topic selection for video {video_id}: {keywords} in category {category}")

def should_explore() -> bool:
    """
    Determines if the bot should choose a random/untested topic (Exploration Budget: 1 in 7).
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Query system configuration for the video counter
    cursor.execute("SELECT value FROM system_config WHERE key = 'video_generation_counter'")
    row = cursor.fetchone()
    
    counter = int(row[0]) if row else 0
    counter += 1
    
    cursor.execute("INSERT OR REPLACE INTO system_config (key, value, updated_at) VALUES ('video_generation_counter', ?, ?)",
                   (str(counter), datetime.now()))
    conn.commit()
    conn.close()
    
    # Exploration budget: 1 out of every 7 videos
    is_explore = (counter % 7 == 0)
    if is_explore:
        logger.info(f"[Topic Intelligence] Exploration active (video counter: {counter}). Selecting untested topic.")
    return is_explore

def update_keyword_weights():
    """
    Recalculates keyword weights with aging decay.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 1. Decay scores older than 30 days by multiplying by 0.85
    # Since recorded_at is stored, we can compare with datetime('now', '-30 days')
    cursor.execute('''
    UPDATE topic_performance
    SET performance_score = performance_score * 0.85
    WHERE recorded_at < datetime('now', '-30 days') AND performance_score IS NOT NULL
    ''')
    
    # 2. Compute rolling average performance score and count
    cursor.execute('''
    SELECT keyword, AVG(performance_score) as avg_score, COUNT(*) as sample_count
    FROM topic_performance
    WHERE performance_score IS NOT NULL
    GROUP BY keyword
    ''')
    rows = cursor.fetchall()
    
    for keyword, avg_score, sample_count in rows:
        cursor.execute('''
        INSERT OR REPLACE INTO keyword_weights (keyword, avg_score, sample_count, last_updated)
        VALUES (?, ?, ?, ?)
        ''', (keyword, avg_score, sample_count, datetime.now()))
        
    conn.commit()
    conn.close()
    logger.info(f"[Topic Intelligence] Recomputed weights for {len(rows)} keywords.")
