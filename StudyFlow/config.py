import os
import sys
from dotenv import load_dotenv
load_dotenv()  # Optional if you use a .env file

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "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")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "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")
COHERE_API_KEY = os.getenv("COHERE_API_KEY", "ICfqLeG3uky6PzX9XT5eyo1KCjSvW93XKQRSBaFp")

# If running as a bundled executable, sys._MEIPASS will be defined.
if getattr(sys, '_MEIPASS', False):
    TESSERACT_PATH = os.path.join(sys._MEIPASS, "external", "tesseract", "tesseract.exe")
else:
    # Otherwise, use the value from the environment, or default to our bundled location.
    TESSERACT_PATH = os.getenv("TESSERACT_PATH", os.path.join(os.path.dirname(__file__), "external", "tesseract", "tesseract.exe"))

DEBUG_DIR = os.getenv("DEBUG_DIR", "debug")
LOG_FILENAME = os.getenv("LOG_FILENAME", "debug_log.txt")