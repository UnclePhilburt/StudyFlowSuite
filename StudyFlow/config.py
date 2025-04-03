import os
from dotenv import load_dotenv

# Load variables from a .env file, if present
load_dotenv()

# Sensitive API keys (do not default these in production)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

# Set up OpenAI API key
if OPENAI_API_KEY:
    import openai
    openai.api_key = OPENAI_API_KEY
else:
    print("Warning: OPENAI_API_KEY is not set.")

# Set up Anthropic API key (if the anthropic library supports global assignment)
if ANTHROPIC_API_KEY:
    try:
        import anthropic
        # This is a placeholder – if anthropic requires client instantiation, adjust accordingly:
        anthropic.api_key = ANTHROPIC_API_KEY
    except ImportError:
        print("Warning: Anthropics library is not installed; skipping Anthropic API configuration.")
else:
    print("Warning: ANTHROPIC_API_KEY is not set.")

# Set up Cohere client if the API key is available
if COHERE_API_KEY:
    try:
        import cohere
        co = cohere.Client(COHERE_API_KEY)
    except ImportError:
        print("Warning: Cohere library is not installed; skipping Cohere API configuration.")
else:
    print("Warning: COHERE_API_KEY is not set.")

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
