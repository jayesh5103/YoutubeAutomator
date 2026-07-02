"""
Topic Engine for Coding & DSA Content.
Replaces trend_analyzer.py for the coding niche.

Features:
- 100+ curated DSA/coding topics organized by category and difficulty
- Series detection: big topics auto-expand into multi-part series
- Stores topics in the existing DB 'trends' table (seamless compatibility)
- get_best_unused_topic() works identically to the old trend_analyzer
"""

import sqlite3
import random
import logging
from datetime import datetime
from database import DB_PATH

logger = logging.getLogger("YoutubeAutomator")

# ─────────────────────────────────────────────────────────────────────────────
#  CURATED TOPIC BANK
#  Format: (topic_text, score, is_series, series_parts_list_or_None)
#  score: 100 = beginner (high demand), 85 = intermediate, 70 = advanced
# ─────────────────────────────────────────────────────────────────────────────

SINGLE_TOPICS = [
    # ── Beginner Concepts (High Demand) ──────────────────────────────────────
    ("Binary Search - Yeh Kya Hota Hai aur Kab Use Karein?", 100),
    ("Array aur List mein Kya Fark Hai? - Ekdum Clear Explanation", 100),
    ("Time Complexity kya hoti hai? O(n) ko Simply Samjho", 100),
    ("Stack Data Structure - Real Life Example se Samjho", 100),
    ("Queue Data Structure - FIFO ko Simple Example se Samjho", 100),
    ("Recursion ka Concept - Apne Aap ko Call Karta Hai?", 100),
    ("Two Pointer Technique - Interview mein Sabse Zyada Pooche Jaane Wala", 100),
    ("Sliding Window Pattern - Array Problems ke liye Magic Trick", 100),
    ("Hashing aur HashMap kya hai? O(1) lookup ka Secret", 100),
    ("Linked List vs Array - Kab Kya Use Karein?", 100),
    ("Bubble Sort kaise kaam karta hai? Animation se Samjho", 95),
    ("Selection Sort aur Insertion Sort - Dono ka Farak", 95),
    ("Merge Sort - Divide and Conquer ka Best Example", 95),
    ("Quick Sort - Average O(n log n) kaise Achieve Hota Hai?", 95),
    ("Big O Notation - Best, Worst, Average Case Samjho", 100),
    ("Space Complexity - Memory bhi Count Hoti Hai!", 95),
    ("Kadane's Algorithm - Maximum Subarray Problem", 95),
    ("Two Sum Problem - LeetCode #1 ka Perfect Solution", 100),
    ("Fibonacci Series - Recursion vs DP mein Farak", 95),
    ("Prime Numbers Check - Sieve of Eratosthenes", 90),
    ("Palindrome Check - String Problems ka Classic", 90),
    ("Anagram Detection - HashMap se O(n) Solution", 90),
    ("Dutch National Flag Problem - 3 Colors Sort Karo", 88),
    ("Moore's Voting Algorithm - Majority Element in O(n)", 88),
    ("Floyd's Cycle Detection - Tortoise and Hare Algorithm", 88),
    ("Bit Manipulation Basics - XOR ka Magic", 85),
    ("Power of Two Check - Bit Trick se 1 Line mein", 85),
    ("Integer Overflow kya hota hai? Coding mein Kab Hota Hai?", 85),
    ("Prefix Sum Array - Range Query Problems ke liye", 90),
    ("Monotonic Stack - Next Greater Element Pattern", 87),

    # ── Intermediate Topics ──────────────────────────────────────────────────
    ("Binary Search Tree - Insert, Delete, Search Kaise Kaam Karta Hai?", 85),
    ("AVL Tree - Self Balancing kyu zaroori hai?", 80),
    ("Heap Data Structure - Priority Queue kaise banta hai?", 85),
    ("Min Heap aur Max Heap - Kab Kya Use Karen?", 85),
    ("BFS vs DFS - Graph Traversal mein Farak", 88),
    ("Dijkstra's Algorithm - Shortest Path ka Raja", 85),
    ("Bellman-Ford Algorithm - Negative Edges Handle Karo", 82),
    ("Topological Sort - DAG mein Order kaise Nikalen?", 83),
    ("Union Find (Disjoint Set) - Connected Components", 82),
    ("Trie Data Structure - Autocomplete kaise Kaam Karta Hai?", 83),
    ("Segment Tree - Range Queries in O(log n)", 80),
    ("Fenwick Tree (BIT) - Point Update Range Query", 78),
    ("KMP Algorithm - String Pattern Matching O(n+m)", 80),
    ("Rabin-Karp - Rolling Hash se String Search", 78),
    ("Z-Algorithm - Pattern Matching ka Another Approach", 77),
    ("LRU Cache - Design Interview ka Favourite Question", 88),
    ("LFU Cache - LRU se Zyada Hard Version", 82),
    ("Design HashMap - Scratch se Banana Seekho", 85),
    ("Design Stack Using Queues - Tricky Interview Question", 80),
    ("Valid Parentheses - Stack ka Classic Use Case", 90),
    ("Next Greater Element - Monotonic Stack Magic", 85),
    ("Trapping Rain Water - Two Pointer Approach", 88),
    ("Container With Most Water - Greedy Thinking", 85),
    ("3Sum Problem - O(n²) Solution kaise Sochein?", 83),
    ("Rotate Array - In-place Rotation Tricks", 82),
    ("Product of Array Except Self - Without Division", 85),
    ("Longest Consecutive Sequence - O(n) mein Kaise?", 83),
    ("Jump Game - Greedy vs DP Approach", 82),
    ("Meeting Rooms Problem - Interval Scheduling", 83),
    ("Word Break Problem - DP + Trie Combination", 80),

    # ── Advanced Topics ──────────────────────────────────────────────────────
    ("Segment Tree Lazy Propagation - Range Update O(log n)", 75),
    ("Heavy Light Decomposition - Tree Query Optimization", 70),
    ("Suffix Array - O(n log n) Construction", 72),
    ("Manacher's Algorithm - All Palindromes in O(n)", 73),
    ("Articulation Points aur Bridges - Graph Theory", 72),
    ("Strongly Connected Components - Kosaraju's Algorithm", 72),
    ("Max Flow - Ford-Fulkerson Algorithm Samjho", 70),
    ("Bipartite Graph Check - BFS se Kaise Karein?", 75),
    ("Matrix Chain Multiplication - DP Classic", 75),
    ("Longest Common Subsequence (LCS) - DP Approach", 80),
    ("Edit Distance (Levenshtein) - DP on Strings", 78),
    ("Coin Change Problem - DP ka Evergreen Classic", 82),
    ("0/1 Knapsack - DP ki Duniya ka Pilllar", 80),
    ("Subset Sum Problem - DP + Backtracking", 78),

    # ── Logic Building ───────────────────────────────────────────────────────
    ("Mathematical Induction - Proof Techniques for Algorithms", 80),
    ("Pigeonhole Principle - Algorithm Design mein Use", 78),
    ("Amortized Analysis - ArrayList resize kyu O(1) hai?", 77),
    ("Master Theorem - Recurrence Relations Solve Karo", 75),
    ("Randomized Algorithms - Why Randomness Helps", 73),
    ("Game Theory Basics - Nim Game aur Sprague-Grundy", 72),
    ("Greedy vs DP - Kab Kya Kaam Karta Hai?", 85),
    ("Backtracking Pattern - N-Queens, Sudoku Solver", 83),
    ("Divide and Conquer - Sochne ka Ek Alag Tarika", 83),
    ("Memoization vs Tabulation - DP Dono Tarike", 85),
    ("Problem Solving Framework - DSA Problems kaise Sochen?", 92),
    ("LeetCode Easy se Hard kaise Jaayen? Roadmap", 90),
    ("Interview Mein Panic na Ho - Confidence Build Karo", 88),
    ("Coding Interview Communication Tips - Think Out Loud", 87),
    ("Time Management in Coding Interviews - 45 Minute Breakdown", 86),
]

# ─────────────────────────────────────────────────────────────────────────────
#  SERIES TOPICS — Auto-expanded into multi-part video series
# ─────────────────────────────────────────────────────────────────────────────

SERIES_TOPICS = [
    {
        "series_name": "Dynamic Programming Complete Series",
        "score": 95,
        "parts": [
            "Dynamic Programming Part 1 - DP Kya Hai aur Kab Use Karein? (Intuition)",
            "Dynamic Programming Part 2 - Memoization Deep Dive with Examples",
            "Dynamic Programming Part 3 - Tabulation (Bottom-Up) Approach Samjho",
            "Dynamic Programming Part 4 - Classic DP Problems (Fibonacci, Climbing Stairs)",
            "Dynamic Programming Part 5 - 2D DP aur Grid Problems",
        ]
    },
    {
        "series_name": "Graph Algorithms Complete Series",
        "score": 90,
        "parts": [
            "Graph Algorithms Part 1 - Graph kya hota hai? Representation Samjho",
            "Graph Algorithms Part 2 - BFS (Breadth First Search) Step by Step",
            "Graph Algorithms Part 3 - DFS (Depth First Search) aur Recursion",
            "Graph Algorithms Part 4 - Shortest Path: Dijkstra's Algorithm",
            "Graph Algorithms Part 5 - Minimum Spanning Tree: Kruskal aur Prim",
        ]
    },
    {
        "series_name": "Binary Trees Complete Series",
        "score": 92,
        "parts": [
            "Binary Trees Part 1 - Tree Data Structure kya hota hai? Basic Concepts",
            "Binary Trees Part 2 - Tree Traversals: Inorder, Preorder, Postorder",
            "Binary Trees Part 3 - Binary Search Tree (BST) - Insert aur Search",
            "Binary Trees Part 4 - BST Delete Operation aur Balancing",
            "Binary Trees Part 5 - Tree DP aur Path Sum Problems",
        ]
    },
    {
        "series_name": "Recursion & Backtracking Series",
        "score": 88,
        "parts": [
            "Recursion Part 1 - Recursion Fundamentals aur Base Case",
            "Recursion Part 2 - Recursion Tree Visualize Karo",
            "Recursion Part 3 - Backtracking Pattern kya hota hai?",
            "Recursion Part 4 - N-Queens Problem Step by Step",
            "Recursion Part 5 - Subsets, Permutations, Combinations",
        ]
    },
    {
        "series_name": "Sorting Algorithms Complete Series",
        "score": 88,
        "parts": [
            "Sorting Algorithms Part 1 - Bubble Sort aur Selection Sort",
            "Sorting Algorithms Part 2 - Insertion Sort aur Shell Sort",
            "Sorting Algorithms Part 3 - Merge Sort - Divide and Conquer",
            "Sorting Algorithms Part 4 - Quick Sort aur Partition",
            "Sorting Algorithms Part 5 - Heap Sort, Counting Sort, Radix Sort",
        ]
    },
    {
        "series_name": "Linked List Complete Series",
        "score": 90,
        "parts": [
            "Linked List Part 1 - Kya Hai aur Array se Kyun Alag Hai?",
            "Linked List Part 2 - Insert aur Delete Operations",
            "Linked List Part 3 - Reverse a Linked List - 3 Tarike",
            "Linked List Part 4 - Cycle Detection - Floyd's Algorithm",
            "Linked List Part 5 - Merge Two Sorted Lists aur Other Classics",
        ]
    },
    {
        "series_name": "LeetCode Patterns Series",
        "score": 95,
        "parts": [
            "LeetCode Patterns Part 1 - Two Pointer Pattern",
            "LeetCode Patterns Part 2 - Sliding Window Pattern",
            "LeetCode Patterns Part 3 - Fast and Slow Pointers",
            "LeetCode Patterns Part 4 - Merge Intervals Pattern",
            "LeetCode Patterns Part 5 - Cyclic Sort Pattern",
            "LeetCode Patterns Part 6 - In-place Reversal of Linked List",
            "LeetCode Patterns Part 7 - BFS for Tree Level Order",
        ]
    },
    {
        "series_name": "Object-Oriented Programming Series",
        "score": 87,
        "parts": [
            "OOP Part 1 - Classes aur Objects kya hain? Real Life Example",
            "OOP Part 2 - Inheritance - Parent aur Child Classes",
            "OOP Part 3 - Polymorphism - Ek Name, Kai Kaam",
            "OOP Part 4 - Encapsulation aur Abstraction",
            "OOP Part 5 - SOLID Principles - Clean Code likho",
        ]
    },
    {
        "series_name": "System Design Basics Series",
        "score": 85,
        "parts": [
            "System Design Part 1 - Scalability kya hoti hai? Horizontal vs Vertical",
            "System Design Part 2 - Load Balancer kaise kaam karta hai?",
            "System Design Part 3 - Caching - Redis aur CDN",
            "System Design Part 4 - Database: SQL vs NoSQL kab kya use karein?",
            "System Design Part 5 - Design URL Shortener - End to End",
        ]
    },
    {
        "series_name": "Bit Manipulation Series",
        "score": 82,
        "parts": [
            "Bit Manipulation Part 1 - Binary Numbers aur Bit Operations",
            "Bit Manipulation Part 2 - AND, OR, XOR ka Magic",
            "Bit Manipulation Part 3 - Left Shift, Right Shift aur Their Uses",
            "Bit Manipulation Part 4 - Classic Bit Tricks in Interviews",
            "Bit Manipulation Part 5 - Bitmask DP Problems",
        ]
    },
]


def _get_all_coding_topics():
    """Flatten single topics and all series parts into one list."""
    all_topics = []
    for topic, score in SINGLE_TOPICS:
        all_topics.append({"topic": topic, "score": score, "source": "coding_engine"})
    for series in SERIES_TOPICS:
        for i, part in enumerate(series["parts"]):
            # Score decreases slightly for later parts so early parts are picked first
            part_score = series["score"] - (i * 2)
            all_topics.append({"topic": part, "score": part_score, "source": "coding_series"})
    return all_topics


def seed_coding_topics():
    """
    Seeds static curated coding topics into the DB.
    Called as fallback when YouTube Intelligence Engine is unavailable.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    all_topics = _get_all_coding_topics()
    inserted = 0
    for t in all_topics:
        try:
            cursor.execute(
                'INSERT OR IGNORE INTO trends (topic, score, timestamp) VALUES (?, ?, ?)',
                (t['topic'], t['score'], datetime.now())
            )
            if cursor.rowcount > 0:
                inserted += 1
        except Exception as e:
            logger.warning(f"[TopicEngine] Could not insert topic '{t['topic']}': {e}")
    conn.commit()
    conn.close()
    logger.info(f"[TopicEngine] Seeded {inserted} new coding topics into DB.")
    return inserted


def seed_topics():
    """
    Primary entry point: tries YouTube Intelligence Engine first,
    falls back to the static curated topic bank.
    """
    intelligence_count = 0
    try:
        from youtube_intelligence import seed_intelligent_topics
        intelligence_count = seed_intelligent_topics()
        if intelligence_count > 0:
            logger.info(f"[TopicEngine] Intelligence seeded {intelligence_count} AI-suggested topics.")
    except Exception as e:
        logger.warning(f"[TopicEngine] Intelligence Engine unavailable ({e}), using static topics.")

    # Always also ensure static topics are present as a safety net
    static_count = seed_coding_topics()
    return intelligence_count + static_count


def get_best_unused_topic():
    """
    Gets the highest-scoring unused coding topic from DB.
    Compatible with the old trend_analyzer.get_best_unused_topic() interface.
    """
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # Get top 5 unused topics and pick one for variety
    cursor.execute('SELECT topic FROM trends WHERE used = 0 ORDER BY score DESC LIMIT 5')
    results = cursor.fetchall()

    if results:
        candidate_topics = [r[0] for r in results]
        try:
            from topic_scorer import should_explore
            from learning_engine import LearningEngine
            
            if should_explore():
                topic = random.choice(candidate_topics)
                logger.info(f"[TopicEngine] Exploration active. Picked random topic: {topic}")
            else:
                ranked = LearningEngine.score_and_rank_topics(candidate_topics)
                topic = ranked[0][0]
                logger.info(f"[TopicEngine] Ranked topic selected: {topic} (Predicted Score: {ranked[0][1]:.1f})")
        except Exception as e:
            logger.error(f"[TopicEngine] Learning scoring failed, falling back to random: {e}")
            topic = random.choice(candidate_topics)

        cursor.execute('UPDATE trends SET used = 1 WHERE topic = ?', (topic,))
        conn.commit()
        conn.close()
        return topic

    conn.close()
    logger.warning("[TopicEngine] All topics used! Re-seeding...")
    # Re-seed if all topics exhausted (reset used flag for all)
    _reset_topics()
    return get_best_unused_topic()


def _reset_topics():
    """Resets all coding topics so they can be used again (new cycle)."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE trends SET used = 0 WHERE source = 'coding_engine' OR source = 'coding_series' OR topic LIKE '%(Part %'"
    )
    conn.commit()
    conn.close()
    logger.info("[TopicEngine] All topics reset for new cycle.")


def save_trends_to_db(trends):
    """
    Legacy compatibility function — older code calls this after get_trending_topics().
    Since we use a curated engine, this is a no-op (topics are already seeded).
    """
    pass


def get_trending_topics(niche_keywords, geo='IN'):
    """
    Legacy compatibility function — returns empty list.
    Topic seeding is handled by seed_coding_topics() at startup.
    """
    return []


def get_topic_visual_hints(topic: str) -> list:
    """
    Returns Pexels-friendly visual search queries for a given coding topic.
    These are used by video_editor.py to fetch relevant background footage.
    """
    topic_lower = topic.lower()

    keyword_map = [
        (["array", "list", "sequence"], ["data row sequence", "bookshelf organized", "matrix grid"]),
        (["stack"], ["stacked objects tower", "pile books stack", "push pop"]),
        (["queue"], ["queue waiting line people", "conveyor belt", "line waiting"]),
        (["linked list", "node"], ["chain links", "connected pearls", "linked chain"]),
        (["tree", "binary tree", "bst", "avl"], ["tree branching fractal", "network nodes branching", "family tree diagram"]),
        (["graph", "bfs", "dfs", "dijkstra", "bellman", "traversal"], ["network connection nodes", "web spider map", "interconnected dots"]),
        (["sort", "sorting", "merge sort", "quick sort", "bubble"], ["sorting organizing objects", "assembly line conveyor", "sorted books shelf"]),
        (["search", "binary search"], ["magnifying glass search", "finding needle haystack", "spotlight search"]),
        (["hash", "hashmap", "dictionary"], ["key lock mechanism", "filing cabinet drawer", "lookup table"]),
        (["dynamic programming", "dp", "memoization", "tabulation"], ["chess strategy planning", "puzzle solving strategy", "decision tree"]),
        (["recursion", "recursive"], ["mirror reflection infinite", "fractal spiral", "russian dolls matryoshka"]),
        (["bit", "binary", "xor", "bitwise"], ["binary code matrix", "digital circuit board", "zeros ones digital"]),
        (["heap", "priority queue"], ["mountain peak priority", "organized layers pyramid", "weighted scales"]),
        (["trie"], ["word tree branches", "autocomplete typing", "alphabet tree"]),
        (["segment tree", "fenwick", "bit tree"], ["segment division", "range measurement", "ruler divisions"]),
        (["backtracking", "n-queens", "sudoku"], ["maze solving path", "decision making choices", "labyrinth navigation"]),
        (["greedy"], ["gold coins collecting", "optimal choice selection", "treasure hunting path"]),
        (["two pointer"], ["two arrows approaching", "pincer movement", "converging lines"]),
        (["sliding window"], ["window sliding building", "moving frame camera", "scanning motion"]),
        (["complexity", "big o", "time complexity", "space complexity"], ["measuring performance", "stopwatch measurement", "performance analytics"]),
        (["interview", "placement", "faang", "leetcode"], ["job interview professional", "whiteboard coding", "office tech company"]),
        (["oop", "object", "class", "inheritance", "polymorphism"], ["blueprint architecture", "building blocks lego", "inheritance family"]),
        (["system design", "scalability", "load balancer", "cache"], ["server room data center", "cloud technology", "network infrastructure"]),
        (["string", "palindrome", "anagram", "pattern"], ["alphabet letters", "text typography", "word arrangement"]),
        (["coin change", "knapsack", "subset"], ["coins collection", "backpack items", "selection choices"]),
    ]

    topic_lower = topic.lower()
    for keywords, queries in keyword_map:
        if any(kw in topic_lower for kw in keywords):
            return random.sample(queries, min(2, len(queries)))

    # Generic coding fallback
    return random.choice([
        ["programming code screen", "developer laptop coding"],
        ["algorithm flowchart whiteboard", "tech coding dark screen"],
        ["computer science abstract", "coding terminal dark"],
    ])


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    print("Seeding coding topics...")
    count = seed_coding_topics()
    print(f"Inserted {count} topics.")
    print("\nSample topics:")
    for _ in range(5):
        t = get_best_unused_topic()
        print(f"  → {t}")
        hints = get_topic_visual_hints(t)
        print(f"     Visuals: {hints}")
