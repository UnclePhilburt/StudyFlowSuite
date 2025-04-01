# logging_utils.py
import datetime
from StudyFlow.config import LOG_FILENAME

def debug_log(message):
    timestamp = datetime.datetime.now().strftime("[%H:%M:%S] ")
    full_message = timestamp + message
    print(full_message)
    with open(LOG_FILENAME, "a") as log_file:
        log_file.write(full_message + "\n")
