import os

# Load .env file (local dev only)
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                val = val.split("#")[0].strip()
                os.environ.setdefault(key.strip(), val)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")
DB_URL = os.environ.get("DB_URL", "sqlite:///atlas_finance.db")
AI_PROVIDER = os.environ.get("AI_PROVIDER", "gemini")
USE_FALLBACK_ON_QUOTA = os.environ.get("USE_FALLBACK_ON_QUOTA", "true").lower() == "true"

if GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY

# Print configuration for debugging
print(f"TELEGRAM_BOT_TOKEN set: {bool(TELEGRAM_BOT_TOKEN)}")
print(f"GEMINI_API_KEY set: {bool(GEMINI_API_KEY)}")
print(f"GROQ_API_KEY set: {bool(GROQ_API_KEY)}")
print(f"AI Provider: {AI_PROVIDER}")
print(f"USE_FALLBACK_ON_QUOTA: {USE_FALLBACK_ON_QUOTA}")