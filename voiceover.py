import os
import asyncio
import random
import edge_tts
from text_preprocessor import preprocess_for_tts

# ─── HINGLISH VOICE POOL ─────────────────────────────────────────────────────
# Selected for clarity with Hinglish (Hindi + English mix) content.
# These voices handle code terms (English words) naturally within Hindi speech.
# ─────────────────────────────────────────────────────────────────────────────
VOICE_POOL = {
    "male": [
        "hi-IN-MadhurNeural",      # Hindi male — deep, authoritative fallback
    ],
    "female": [
        "hi-IN-SwaraNeural",       # Hindi female — warm fallback
    ]
}

# Tuned for natural Hinglish cadence — previous +5%/+15% caused consonant clipping
SPEECH_RATE = "+2%"    # Gentle uplift without swallowing syllables
SPEECH_PITCH = "+0Hz"   # No chipmunk/robotic tone distortion
SPEECH_VOLUME = "+8%"   # Audible but not overdriven


def get_random_voice(gender="male", niche_config=None):
    """
    Returns a voice from the Hinglish pool.
    If niche_config specifies a voice_id, that takes priority.
    """
    if niche_config and niche_config.get('voice_id'):
        return niche_config['voice_id']

    pool = VOICE_POOL.get(gender, VOICE_POOL["male"])
    selected = random.choice(pool)
    print(f"[Voiceover] Selected voice: {selected}")
    return selected


def generate_voiceover(text, output_path="temp_audio.mp3", gender="male", niche_config=None):
    """
    Generates a voiceover using edge-tts.
    Tuned for Hinglish coding content — clear, energetic, 50-60s target.
    Text is preprocessed through 6 rule sets before TTS synthesis.
    """
    voice = get_random_voice(gender, niche_config)
    
    # Run all 6 preprocessing rules (complexity notation, code symbols,
    # acronym spelling, phonetic fixes, Hindi pauses, number normalization)
    processed_text = preprocess_for_tts(text)
    print(f"[Voiceover] Generating speech | Voice: {voice} | Words: {len(processed_text.split())}")

    async def _generate():
        MAX_RETRIES = 3
        for attempt in range(MAX_RETRIES):
            try:
                communicate = edge_tts.Communicate(
                    processed_text,
                    voice,
                    rate=SPEECH_RATE,
                    pitch=SPEECH_PITCH,
                    volume=SPEECH_VOLUME
                )
                await communicate.save(output_path)
                print(f"[Voiceover] ✅ Saved to {output_path}")
                return output_path
            except Exception as e:
                print(f"[Voiceover] ❌ Error generating audio (Attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    return None

    try:
        result = asyncio.run(_generate())
        return result
    except Exception as e:
        print(f"[Voiceover] Runtime error: {e}")
        return None


if __name__ == "__main__":
    print("Testing Hinglish voice pool:")
    test_text = (
        "Bhai, Binary Search ek bahut powerful algorithm hai. "
        "Sorted array mein element dhundhne ke liye hum O(log n) time use karte hain. "
        "Array ko do halves mein divide karo — agar target middle se chota hai "
        "toh left half check karo, warna right half. Bas itna simple hai! "
        "Subscribe karo daily DSA ke liye!"
    )
    for gender in ["male", "female"]:
        v = get_random_voice(gender)
        print(f"  {gender}: {v}")
    print("\nGenerating test audio...")
    result = generate_voiceover(test_text, "/tmp/test_hinglish.mp3", gender="male")
    print(f"Result: {result}")
