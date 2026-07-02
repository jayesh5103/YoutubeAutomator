import json
import logging
from script_writer import _generate_with_groq

logger = logging.getLogger("YoutubeAutomator")

def generate_storyboard(topic: str, channel_name: str = "this channel") -> list:
    """
    Generates a beat-by-beat storyboard for a coding/DSA YouTube Shorts video.
    Each beat contains localized Hinglish script text and a specific visual action for Manim.
    """
    
    prompt = f"""You are an expert YouTube Shorts director for an Indian coding channel called '{channel_name}'.
Topic: "{topic}"

Create a fast-paced, 50-60 second storyboard targeting Indian students and developers (use Hinglish: mix Hindi and English).
Break the video into exactly 5 to 9 sequential beats (scenes/sentences).

For each beat, provide:
1. text: The spoken Hinglish script for that beat. Must sound enthusiastic!
2. visual_action: Exactly ONE of these supported animation actions:
   [title_card, show_grid, place_char, highlight_row, show_arrows, highlight_code_line,
    show_array, highlight_element, show_pointers, show_mid,
    show_found, show_code, show_complexity, show_comparison, show_tree,
    show_stack, show_bars, show_dp_table, show_graph, text_only, cta_card]
3. visual_data: A valid JSON object representing the parameters needed for the chosen action.

Guidelines for visual_data based on visual_action:
- title_card: {{"title": "Short title", "subtitle": "Short subtitle"}}
- show_grid: {{"rows": 4, "cols": 4, "grid": [["A","B","C","D"], ["E","F","G","H"], ["I","J","K","L"], ["M","N","O","P"]], "lines": ["def search(grid):", "    return False"], "highlight_line": 0}}
- place_char: {{"rows": 4, "cols": 4, "grid": [["A","B","C","D"], ["E","F","X","H"], ["I","J","K","L"], ["M","N","O","P"]], "row": 1, "col": 2, "char": "X", "lines": ["def search(grid):", "    grid[1][2] = 'X'"], "highlight_line": 1}}
- highlight_row: {{"rows": 4, "cols": 4, "grid": [...], "row": 2, "lines": ["def search(grid):", "    # highlight row"], "highlight_line": 1}}
- show_arrows: {{"rows": 4, "cols": 4, "grid": [...], "arrows": [{{"start": [0,0], "end": [2,2]}}], "lines": [...], "highlight_line": 1}}
- highlight_code_line: {{"rows": 4, "cols": 4, "grid": [...], "lines": ["def search(grid):", "    for r in range(4):", "        pass"], "highlight_line": 1}}
- show_array: {{"values": [1,2,3,4], "label": "Array"}}
- highlight_element: {{"values": [1,2,3], "highlight_idx": 1, "color": "yellow", "label": "Target"}}
- show_pointers: {{"values": [1,2,3], "lo": 0, "hi": 2}}
- show_mid: {{"values": [1,2,3], "lo": 0, "hi": 2, "mid_idx": 1, "target": 2}}
- show_found: {{"values": [1,2,3], "found_idx": 1, "target": 2}}
- show_code: {{"lines": ["def solve():", "  return 1"], "highlight_line": 0}}
- show_complexity: {{"time": "O(n)", "space": "O(1)", "label": "Algorithm"}}
- show_comparison: {{"a_val": "O(n^2)", "b_val": "O(n log n)", "a_label": "Method A", "b_label": "Method B", "winner": "b"}}
- text_only: {{"text": "Key Insight", "color": "accent"}}
- cta_card: {{"text": "Subscribe for more!", "channel": "{channel_name}"}}

Example Response Format (MUST be a valid JSON array):
[
  {{
    "text": "Bhai, kya tumhe Arrays mein search karna aata hai?",
    "visual_action": "title_card",
    "visual_data": {{"title": "Linear Search", "subtitle": "Find the element"}}
  }},
  {{
    "text": "For example, apne paas ek simple array hai.",
    "visual_action": "show_array",
    "visual_data": {{"values": [10, 20, 30, 40], "label": "Numbers"}}
  }},
  {{
    "text": "Aur agar helpful laga toh subscribe zaroor karna!",
    "visual_action": "cta_card",
    "visual_data": {{"text": "Subscribe karo!", "channel": "{channel_name}"}}
  }}
]
"""

    logger.info(f"[Storyboard Engine] Generating storyboard for: {topic}")
    
    # Inject learning context and visual preferences
    try:
        from learning_engine import LearningEngine
        from topic_scorer import categorize_topic
        context = LearningEngine.build_script_context_block()
        if context:
            prompt = context + "\n" + prompt
            
        category = categorize_topic(topic)
        visual_seq = LearningEngine.suggest_visual_sequence(category)
        if visual_seq:
            prompt += f"\n\n[LEARNING CONTEXT — VISUAL SEQUENCE PREFERENCE]\nHistorically, for the algorithm category '{category}', the highest-performing visual sequence of beats is: {json.dumps(visual_seq)}. Try to align your storyboard visual actions with this sequence order where appropriate."
    except Exception as le_err:
        logger.error(f"[Storyboard Engine] Failed to inject learning preferences: {le_err}")

    prompt += "\n\nCRITICAL: OUTPUT ONLY VALID JSON. Do not include markdown tags like ```json or any other surrounding text."
    
    response = _generate_with_groq(prompt)
    if not response:
        logger.error("[Storyboard Engine] Received empty response from LLM.")
        return []
        
    try:
        # Strip potential markdown formatting if the LLM ignores instructions
        response_clean = response.strip()
        if response_clean.startswith("```json"):
            response_clean = response_clean[7:]
        elif response_clean.startswith("```"):
            response_clean = response_clean[3:]
            
        if response_clean.endswith("```"):
            response_clean = response_clean[:-3]
            
        storyboard = json.loads(response_clean.strip())
        logger.info(f"[Storyboard Engine] Successfully parsed {len(storyboard)} beats.")
        return storyboard
    except Exception as e:
        logger.error(f"[Storyboard Engine] Failed to parse JSON: {e}\nResponse snippet: {response[:200]}...")
        return []
