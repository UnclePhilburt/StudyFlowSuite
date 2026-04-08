# logging_utils.py
import datetime
import sys
from StudyFlow.config import LOG_FILENAME

def debug_log(message):
    timestamp = datetime.datetime.now().strftime("[%H:%M:%S] ")
    full_message = timestamp + message
    print(full_message, flush=True)
    sys.stdout.flush()
    try:
        with open(LOG_FILENAME, "a", encoding="utf-8") as log_file:
            log_file.write(full_message + "\n")
    except Exception:
        pass  # File logging optional (Render filesystem is ephemeral)
