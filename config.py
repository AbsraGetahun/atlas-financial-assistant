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

def _env(key, default=""):
    return os.environ.get(key, default)

TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY     = _env("GEMINI_API_KEY")
GROQ_API_KEY       = _env("GROQ_API_KEY")
DB_URL             = _env("DB_URL", "sqlite:///atlas_finance.db")

if GEMINI_API_KEY:
    os.environ["GOOGLE_API_KEY"] = GEMINI_API_KEY
