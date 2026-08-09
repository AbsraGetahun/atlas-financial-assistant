import os
import sys

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
DB_URL = os.environ.get("DB_URL", "sqlite:///atlas_finance.db")

# Debug: print env state on startup
print(f"[config] TELEGRAM_BOT_TOKEN set: {bool(TELEGRAM_BOT_TOKEN)}", file=sys.stderr)
print(f"[config] GEMINI_API_KEY set: {bool(GEMINI_API_KEY)}", file=sys.stderr)
print(f"[config] GROQ_API_KEY set: {bool(GROQ_API_KEY)}", file=sys.stderr)
print(f"[config] All env keys: {[k for k in os.environ if 'TOKEN' in k or 'KEY' in k or 'URL' in k]}", file=sys.stderr)

if GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY
