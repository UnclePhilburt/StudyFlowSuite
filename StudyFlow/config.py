import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get API keys from environment variables
# These should be set in .env file locally or in Render environment variables for production
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Used for embeddings (vector search)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")  # Used for conversational chat and quiz answering

# Set up OpenAI API key
try:
    import openai
    openai.api_key = OPENAI_API_KEY
except ImportError:
    print("Warning: OpenAI library is not installed. Install it via 'pip install openai'.")

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
