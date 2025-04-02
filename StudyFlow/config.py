import os
import sys
from dotenv import load_dotenv

load_dotenv()  # Load variables from a .env file, if present

# Sensitive API keys (consider not providing default values in production)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
COHERE_API_KEY = os.getenv("COHERE_API_KEY")

# Set the Tesseract path based on the operating system.
# On Windows, use the bundled executable. Otherwise, assume a Linux environment.
if os.name == "nt":
    TESSERACT_PATH = os.getenv("TESSERACT_PATH", os.path.join(os.path.dirname(__file__), "external", "tesseract", "tesseract.exe"))
else:
    TESSERACT_PATH = os.getenv("TESSERACT_PATH", "/usr/bin/tesseract")

DEBUG_DIR = os.getenv("DEBUG_DIR", "debug")
LOG_FILENAME = os.getenv("LOG_FILENAME", "debug_log.txt")
