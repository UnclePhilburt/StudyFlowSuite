import os
import pytesseract
from StudyFlow.config import TESSERACT_PATH
from StudyFlow.frontend.studyflow_menu import main as launch_menu
from StudyFlow.logging_utils import debug_log

# Set Tesseract command path early
if os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
    print(f"[DEBUG] Tesseract configured at: {TESSERACT_PATH}")
else:
    print(f"[ERROR] Tesseract not found at: {TESSERACT_PATH}")
    raise FileNotFoundError(f"Tesseract not found at {TESSERACT_PATH}")

def main():
    debug_log("StudyFlow starting up...")

    # Start extension bridge server
    try:
        from StudyFlow.frontend.extension_bridge import start_server
        start_server(port=5555)
        debug_log("✅ Extension bridge server started on port 5555")
    except Exception as e:
        debug_log(f"⚠️ Could not start extension bridge: {e}")

    launch_menu()

if __name__ == "__main__":
    main()
