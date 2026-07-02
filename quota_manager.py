import webbrowser
import os

def get_quota_info():
    """
    Returns a formatted string containing known Gemini API quota limits
    and other helpful information for the user.
    """
    info = """
    📊 Gemini API Quota Limits (Free Tier)
    --------------------------------------
    
    1. Gemini 1.5 Flash:
       - 15 RPM (Requests Per Minute)
       - 1 million TPM (Tokens Per Minute)
       - 1,500 RPD (Requests Per Day)
    
    2. Gemini 2.0 Flash:
       - 10 RPM (Requests Per Minute)
       - 4 million TPM (Tokens Per Minute)
       - 1,500 RPD (Requests Per Day)
    
    3. Gemini 1.5 Pro:
       - 2 RPM (Requests Per Minute)
       - 32,000 TPM (Tokens Per Minute)
       - 50 RPD (Requests Per Day)
    
    💡 Pro Tip: The YouTube Automator uses 'gemini-1.5-flash' 
    as the primary model because it has a generous daily limit.
    
    🔗 For real-time usage monitoring, visit your Google AI Studio Dashboard:
    https://aistudio.google.com/app/plan_and_billing

    📺 YouTube Upload Limits:
    - 3 Videos Per Day (Bot-enforced limit)
    - Avoiding "Spam" flags is crucial for channel longevity.
    """
    return info.strip()

def open_ai_studio_dashboard():
    """Opens the Google AI Studio plan and billing page in the default browser."""
    url = "https://aistudio.google.com/app/plan_and_billing"
    webbrowser.open(url)

if __name__ == "__main__":
    print(get_quota_info())
