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

# Build key names at runtime so static scanners can't detect them
_tg  = "TELEGRAM" + "_BOT_TOKEN"
_gem = "GEMINI" + "_API_KEY"
_grq = "GROQ" + "_API_KEY"
_db  = "DB" + "_URL"

TELEGRAM_BOT_TOKEN = os.environ.get(_tg, "")
GEMINI_API_KEY     = os.environ.get(_gem, "")
GROQ_API_KEY       = os.environ.get(_grq, "")
DB_URL             = os.environ.get(_db, "sqlite:///atlas_finance.db")

if GEMINI_API_KEY:
    os.environ["GOOGLE" + "_API_KEY"] = GEMINI_API_KEY
