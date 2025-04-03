import os
from dotenv import load_dotenv

load_dotenv()  # Load variables from a .env file, if present

# Sensitive API keys (don't default these in prod)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

# Define debug-related paths
DEBUG_DIR = os.getenv("DEBUG_DIR", "debug")
LOG_FILENAME = os.getenv("LOG_FILENAME", "debug_log.txt")

# 🔍 Tesseract path resolution
TESSERACT_PATH = None
if os.name == "nt":
    # Windows: check env var or fallback to bundled tesseract
    TESSERACT_PATH = os.getenv(
        "TESSERACT_PATH",
        os.path.join(os.path.dirname(__file__), "external", "tesseract", "tesseract.exe")
    )
else:
    # Linux/Mac: Try known common paths
    POSSIBLE_TESSERACT_PATHS = [
        os.getenv("TESSERACT_PATH"),  # .env override
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/bin/tesseract",
        "/opt/homebrew/bin/tesseract",  # macOS M1/M2
    ]

    for path in POSSIBLE_TESSERACT_PATHS:
        if path and os.path.exists(path):
            TESSERACT_PATH = path
            print(f"[config.py] ✅ Tesseract found at: {path}")
            break

    if not TESSERACT_PATH:
        TESSERACT_PATH = "tesseract"  # fallback to PATH
        print("[config.py] ⚠️ No known path found. Falling back to 'tesseract' in PATH.")
