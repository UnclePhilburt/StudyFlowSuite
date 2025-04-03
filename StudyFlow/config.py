import os
from dotenv import load_dotenv

# Optional: Load variables from a .env file (if you want to override hardcoded values)
load_dotenv()

# For testing purposes, we're hardcoding API keys here.
# Replace the following strings with your actual API keys.
OPENAI_API_KEY = "<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>)"
ANTHROPIC_API_KEY = "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"
COHERE_API_KEY = "ICfqLeG3uky6PzX9XT5eyo1KCjSvW93XKQRSBaFp"

# Set up OpenAI API key
try:
    import openai
    openai.api_key = OPENAI_API_KEY
except ImportError:
    print("Warning: OpenAI library is not installed. Install it via 'pip install openai'.")

# Set up Anthropic API key
try:
    import anthropic
    # If the library requires client instantiation, adjust accordingly.
    anthropic.api_key = ANTHROPIC_API_KEY
except ImportError:
    print("Warning: Anthropic library is not installed. Install it via 'pip install anthropic'.")

# Set up Cohere client
try:
    import cohere
    co = cohere.Client(COHERE_API_KEY)
except ImportError:
    print("Warning: Cohere library is not installed. Install it via 'pip install cohere'.")

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
