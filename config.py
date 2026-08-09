import os

# Load .env file manually (local dev only — ignored on Railway)
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

# Use ATLAS_DB_URL to avoid Railway intercepting the reserved DATABASE_URL name
DATABASE_URL = os.environ.get("ATLAS_DB_URL") or os.environ.get("DATABASE_URL", "sqlite:///atlas_finance.db")

if GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY
