import os
import pytesseract
from StudyFlow.config import TESSERACT_PATH
from StudyFlow.studyflow_menu import main as launch_menu
from StudyFlow.logging_utils import debug_log

# Set Tesseract command path early
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
else:
    raise FileNotFoundError(f"Tesseract not found at {TESSERACT_PATH}")

def main():
    debug_log("StudyFlow starting up...")
    launch_menu()

if __name__ == "__main__":
    main()
