# constants.py
# Centralized configuration values for StudyFlow

# ============ Timing Constants ============
# Delays and intervals in milliseconds/seconds
HIGHLIGHT_DISPLAY_MS = 3000          # How long answer highlight shows (ms)
FADE_OUT_DURATION_MS = 500           # Fade out animation duration (ms)
POLLING_INTERVAL_MS = 1000           # OCR scanning poll interval (ms)
DEBOUNCE_DELAY_MS = 2000             # Debounce delay for OCR updates (ms)
CLICK_DELAY_SEC = 0.5                # Delay after clicking an answer (sec)
WINDOW_HIDE_DELAY_SEC = 2            # Delay after hiding window (sec)
API_RETRY_DELAY_SEC = 1              # Delay between API retries (sec)
QUESTION_WAIT_MIN_SEC = 7            # Min wait for new question (sec)
QUESTION_WAIT_MAX_SEC = 10           # Max wait for new question (sec)

# ============ OCR Constants ============
OCR_SIMILARITY_THRESHOLD = 0.90      # Text similarity threshold for change detection
DEFAULT_EXPECTED_ANSWERS = 4         # Default number of answer options
IMAGE_CONTRAST_FACTOR = 4.0          # Contrast factor for image preprocessing
IMAGE_THRESHOLD_VALUE = 120          # Threshold value for image preprocessing

# ============ API Constants ============
MAX_API_RETRIES = 3                  # Maximum number of API call retries

# ============ UI Constants ============
# FocusFlow Overlay
OVERLAY_WIDTH = 500
OVERLAY_HEIGHT = 350
OVERLAY_BACKGROUND_ALPHA = 240       # Background opacity (0-255)
OVERLAY_MARGIN = 20
OVERLAY_SPACING = 15

# Selection overlay
SELECTION_OVERLAY_ALPHA = 100        # Selection screen background alpha
SELECTION_PEN_WIDTH = 2              # Selection rectangle pen width

# Highlight
HIGHLIGHT_PEN_WIDTH = 4              # Answer highlight pen width
HIGHLIGHT_CORNER_RADIUS = 10         # Rounded corner radius for highlight

# Colors (R, G, B, A)
HIGHLIGHT_COLOR = (0, 255, 128, 200)  # Pastel green for answer highlight
OVERLAY_BACKGROUND_COLOR = (255, 255, 255, 240)  # White with slight transparency

# ============ Click Constants ============
CLICK_CENTER_OFFSET = 0.5            # Click at center of word (50%)

# ============ Scrolling Constants ============
SCROLL_PIXELS = 100                  # Pixels to scroll per attempt
MAX_SCROLL_ATTEMPTS = 5              # Max scroll attempts before giving up
SCROLL_SETTLE_DELAY_SEC = 0.3        # Wait for page to settle after scroll
SCROLL_RESET_ATTEMPTS = 8            # Scrolls to reset to top of page
