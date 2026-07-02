import os
import time
import random
import logging
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("YoutubeAutomator")

from database import set_api_cooldown, get_api_cooldown

PROVIDER_COOLDOWN_SECS = 60


def generate_script(topic, niche_config=None, channel_name="this channel"):
    """
    Generates a Hinglish coding/DSA YouTube Shorts script (50-60 seconds).
    CodeWithHarry style — energetic, relatable, educational.
    """

    # Detect if this is a series part
    is_series = "Part" in topic and ("Part 1" in topic or "Part 2" in topic or
                                      "Part 3" in topic or "Part 4" in topic or
                                      "Part 5" in topic or "Part 6" in topic or
                                      "Part 7" in topic)
    part_number = ""
    series_cta = ""
    if is_series:
        import re
        m = re.search(r'Part (\d+)', topic)
        if m:
            part_number = m.group(1)
            series_cta = f"Agar yeh helpful laga toh Part {int(part_number)+1} bhi dekhna — link in bio!"

    # Hook styles for coding content
    hook_styles = [
        "shocking fact about this algorithm",
        "common mistake that coders make",
        "interview trick question style",
        "real-life analogy approach",
        "counter-intuitive revelation",
        "challenge the viewer approach",
        "storytelling with a relatable struggle",
    ]

    selected_hook = random.choice(hook_styles)

    # Script language/style guide
    hinglish_guide = """
Hinglish Style Rules:
- Mix Hindi and English naturally, like CodeWithHarry or Striver does on YouTube
- Code terms ALWAYS in English: array, pointer, node, function, recursive, O(n), etc.
- Conversational Hindi for explanations: "dekho", "samjho", "yeh kya hai", "simple hai", "suno"
- Use "bhai", "yaar" occasionally for relatability
- Use real-world Indian analogies (dabba system, railway queue, chai shop etc.)
- Mention complexity: "Time complexity O(n log n) hai — perfect!"
- Phrases: "Interview mein yeh zaroor aata hai", "LeetCode pe yeh classic problem hai"
"""

    prompt = f"""You are an expert Indian coding educator in the style of CodeWithHarry and Striver.
Write a YouTube Shorts script for the topic: "{topic}"
Target length: 50-60 seconds when spoken (approximately 130-160 words).
Hook style: {selected_hook}
Channel name: '{channel_name}'

{hinglish_guide}

MANDATORY SCRIPT STRUCTURE:

1. HOOK (0-8s) — Grab attention immediately!
   Start with a bold statement, shocking fact, or challenge. Examples:
   - "Bhai, 90% coders yeh mistake karte hain..."
   - "Ek interview question jo sabko confuse karta hai..."
   - "Agar yeh concept clear nahi hai toh interview zaroor fail hoga!"

2. PROBLEM / CONCEPT INTRO (8-20s) — What are we solving?
   - Define the concept simply using a real-life Indian analogy
   - Example for Stack: "Socho ek dabba mein plates rakhte ho — jo aakhri mein rakhi, woh pehle nikli. LIFO!"

3. CORE INSIGHT / ALGORITHM STEPS (20-40s) — The "aha!" moment
   - Explain the key logic step-by-step (2-3 steps max)
   - Mention actual code terms, variable names, pseudocode in English
   - Give time/space complexity: "Yeh O(n) time aur O(1) space mein hota hai!"

4. QUICK EXAMPLE (40-50s) — 1 crisp example to make it stick
   - One concrete example with numbers or a brief code outline
   
5. CTA (50-60s) — Call to action
   {series_cta if series_cta else f"Subscribe karo '{channel_name}' ko — daily DSA aur coding concepts, bilkul free!"}

STRICT RULES:
- ONLY produce the spoken script. NO stage directions, NO labels like "HOOK:" or "CTA:".
- Length: 130-160 words exactly. Count them.
- Do NOT write actual code blocks — just mention variable names and logic verbally.
- Make it sound natural when read aloud.
- End every video with a direct, energetic CTA.
"""

    # Inject learning context block
    try:
        from learning_engine import LearningEngine
        context = LearningEngine.build_script_context_block()
        if context:
            prompt = context + "\n" + prompt
    except Exception as le_err:
        logger.error(f"[Script Writer] Failed to prepend learning context: {le_err}")

    try:
        cooldown_until = get_api_cooldown("Groq")
        if time.time() < cooldown_until:
            wait_left = int(cooldown_until - time.time())
            logger.info(f"[Script Writer] Groq cooldown. Waiting {wait_left}s.")
            time.sleep(wait_left)

        logger.info(f"[Script Writer] Generating Hinglish coding script for: {topic}")
        result = _generate_with_groq(prompt)

        if result:
            logger.info(f"[Script Writer] ✅ Script generated ({len(result.split())} words)")
            return result

    except Exception as e:
        error_str = str(e)
        logger.warning(f"[Script Writer] Groq failed: {error_str}")
        if "429" in error_str or "rate_limit" in error_str.lower():
            logger.warning(f"[Script Writer] Rate limited — cooling down {PROVIDER_COOLDOWN_SECS}s.")
            set_api_cooldown("Groq", time.time() + PROVIDER_COOLDOWN_SECS)

    return None


def _generate_with_groq(prompt):
    """
    Uses Groq API (free tier: 14,400 requests/day).
    Models: llama-3.3-70b-versatile → llama-3.1-8b-instant (fallback)
    """
    from groq import Groq, RateLimitError, AuthenticationError

    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key or api_key == "YOUR_GROQ_KEY_HERE":
        logger.error("[Groq] No API key. Add GROQ_API_KEY to .env file.")
        return None

    client = Groq(api_key=api_key)
    models_to_try = ["llama-3.3-70b-versatile", "llama-3.1-8b-instant"]

    for model in models_to_try:
        try:
            logger.info(f"[Groq] Calling {model}...")
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a professional YouTube Shorts script writer specializing in "
                            "coding education for Indian audiences. You write in Hinglish — a natural "
                            "mix of Hindi and English. Code terms stay in English. Explanations are in "
                            "conversational Hindi. Style is energetic, like CodeWithHarry or Striver. "
                            "Scripts are 130-160 words, designed to be spoken in 50-60 seconds."
                        )
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=1000,
                temperature=0.82
            )
            text = response.choices[0].message.content
            if text and text.strip():
                logger.info(f"[Groq] ✅ Generated with {model}")
                return text.strip()
        except RateLimitError as e:
            logger.warning(f"[Groq] Rate limit on {model}: {e}")
            continue
        except AuthenticationError as e:
            logger.error(f"[Groq] Invalid API key: {e}")
            return None
        except Exception as e:
            logger.error(f"[Groq] {model} error: {e}")
            continue

    return None


def generate_metadata(topic, script):
    """
    Generates viral metadata for coding content.
    Returns English/Hinglish title, description, DSA tags, and visual keywords.
    """
    import html

    topic = html.unescape(topic).strip()

    # Detect series info for title
    series_label = ""
    if "Part" in topic:
        import re
        m = re.search(r'Part (\d+)', topic)
        if m:
            series_label = f" | Part {m.group(1)}"

    prompt = f"""Based on this coding/DSA YouTube Shorts script about '{topic}', generate metadata.

Script:
{script}

Generate EXACTLY in this format:
TITLE: [Catchy English/Hinglish title, max 70 chars, include #Shorts or topic keyword]
DESCRIPTION: [2-3 line Hinglish description with emojis, mention key concept, end with hashtags: #DSA #LeetCode #CodingInterview #Shorts]
TAGS: [15 comma-separated tags mixing English and Hindi: DSA, LeetCode, CodingHindi, algorithm name, etc.]
KEYWORDS: [8 ENGLISH visual search terms for Pexels stock footage, comma-separated. Be specific: e.g. "algorithm flowchart", "network nodes", "sorting conveyor belt"]

Rules:
- Title must be click-worthy and mention the specific concept
- Include "{series_label}" in title if it's a series part
- Tags must include: DSA, CodingInterview, LeetCode, Shorts, Placement, SDE
"""

    # Get title template instructions from learning engine
    try:
        from learning_engine import LearningEngine
        title_template = LearningEngine.get_title_template()
        if title_template:
            prompt += f"\n- Title Template Guidelines: {title_template}\n"
    except Exception as le_err:
        logger.error(f"[Metadata] Failed to append title guidelines: {le_err}")


    response_text = None
    try:
        logger.info(f"[Metadata] Generating metadata for: {topic}")
        response_text = _generate_with_groq(prompt)
    except Exception as e:
        logger.error(f"[Metadata] Groq failed: {e}")

    def _sanitize_title(t):
        if not t:
            return f"{topic[:55]} #Shorts"
        t = html.unescape(t).replace('"', '').replace("'", '').strip()
        return t[:100]

    if not response_text:
        return {
            "title": _sanitize_title(f"Master {topic} #DSA #Shorts"),
            "description": f"Learn {topic} in under 60 seconds! 🚀\n#DSA #LeetCode #CodingInterview #Shorts",
            "tags": ["DSA", "LeetCode", "CodingInterview", "Shorts", "DataStructures",
                     "Algorithms", "Placement", "SDE", "FAANG", "Programming"],
            "keywords": ["algorithm flowchart", "programming code screen", "developer laptop coding",
                         "network nodes", "data structure", "computer science"]
        }

    metadata = {}
    try:
        for line in response_text.split('\n'):
            line = line.strip()
            if line.startswith("TITLE:"):
                metadata['title'] = _sanitize_title(line.replace("TITLE:", "").strip())
            elif line.startswith("DESCRIPTION:"):
                metadata['description'] = line.replace("DESCRIPTION:", "").strip()
            elif line.startswith("TAGS:"):
                raw_tags = line.replace("TAGS:", "").strip().strip("[]")
                metadata['tags'] = [t.strip() for t in raw_tags.split(',') if t.strip()]
            elif line.startswith("KEYWORDS:"):
                raw_kw = line.replace("KEYWORDS:", "").strip().strip("[]")
                metadata['keywords'] = [k.strip() for k in raw_kw.split(',') if k.strip()]
    except Exception as e:
        logger.error(f"[Metadata] Parsing error: {e}")

    # Fallbacks
    if not metadata.get('title'):
        metadata['title'] = _sanitize_title(f"Master {topic} #DSA #Shorts")
    if not metadata.get('description'):
        metadata['description'] = f"Learn {topic} in 60 seconds! 🚀 #DSA #LeetCode #CodingInterview #Shorts"
    if not metadata.get('tags'):
        metadata['tags'] = ["DSA", "LeetCode", "CodingInterview", "Shorts", "Placement", "SDE"]
    if not metadata.get('keywords'):
        metadata['keywords'] = ["algorithm flowchart", "programming code screen", "network nodes"]

    return metadata
