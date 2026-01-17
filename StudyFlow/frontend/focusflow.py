from PySide6.QtWidgets import (
    QDialog, QApplication, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QGraphicsDropShadowEffect, QGraphicsOpacityEffect
)
from PySide6.QtCore import Qt, QRect, QTimer, QPropertyAnimation
from PySide6.QtGui import QPainter, QPen, QColor, QFont, QPalette
import difflib

from StudyFlow.constants import (
    HIGHLIGHT_DISPLAY_MS, FADE_OUT_DURATION_MS, POLLING_INTERVAL_MS,
    DEBOUNCE_DELAY_MS, OCR_SIMILARITY_THRESHOLD, OVERLAY_WIDTH, OVERLAY_HEIGHT,
    OVERLAY_BACKGROUND_ALPHA, OVERLAY_MARGIN, OVERLAY_SPACING,
    SELECTION_OVERLAY_ALPHA, SELECTION_PEN_WIDTH, HIGHLIGHT_PEN_WIDTH,
    HIGHLIGHT_CORNER_RADIUS, HIGHLIGHT_COLOR, OVERLAY_BACKGROUND_COLOR
)

# Import OCR and AI functions from your modules.
from StudyFlow.frontend.ocr_extraction import (
    get_tagged_words_from_region,
    ai_structure_layout,
    fallback_structure,
    merge_ai_and_fallback,
    convert_answers_list_to_dict
)
from StudyFlow.backend.ai_manager import triple_call_ai_api_json_final

# Global variables to store the selected question region and the last OCR mapping.
QUESTION_REGION = None
LAST_MAPPING = None

class RegionSelector(QDialog):
    """
    A full-screen transparent dialog that allows the user to select a region.
    The user clicks and drags to form a rectangle. The selected region is stored in self.selected_rect.
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Select Question Region")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.showFullScreen()
        self.start_point = None
        self.end_point = None
        self.selected_rect = None

    def mousePressEvent(self, event):
        self.start_point = event.globalPosition().toPoint()
        self.end_point = self.start_point
        self.update()

    def mouseMoveEvent(self, event):
        self.end_point = event.globalPosition().toPoint()
        self.update()

    def mouseReleaseEvent(self, event):
        self.end_point = event.globalPosition().toPoint()
        self.selected_rect = QRect(self.start_point, self.end_point).normalized()
        self.accept()  # Close the dialog

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, SELECTION_OVERLAY_ALPHA))
        if self.start_point and self.end_point:
            pen = QPen(Qt.red, SELECTION_PEN_WIDTH)
            painter.setPen(pen)
            selection_rect = QRect(self.start_point, self.end_point).normalized()
            painter.drawRect(selection_rect)

class AnswerHighlighter(QDialog):
    """
    A temporary overlay that highlights a specified rectangle.
    It fades out after a few seconds.
    """
    def __init__(self, highlight_rect, parent=None):
        super().__init__(None)  # Top-level window
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        # Cover the whole screen.
        self.setGeometry(QApplication.primaryScreen().geometry())
        self.highlight_rect = highlight_rect
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(1.0)
        self.show()
        QTimer.singleShot(HIGHLIGHT_DISPLAY_MS, self.start_fade_out)

    def start_fade_out(self):
        self.anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.anim.setDuration(FADE_OUT_DURATION_MS)
        self.anim.setStartValue(1.0)
        self.anim.setEndValue(0.0)
        self.anim.finished.connect(self.close)
        self.anim.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        pen = QPen(QColor(*HIGHLIGHT_COLOR), HIGHLIGHT_PEN_WIDTH)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(self.highlight_rect, HIGHLIGHT_CORNER_RADIUS, HIGHLIGHT_CORNER_RADIUS)

class FocusFlowOverlay(QDialog):
    """
    A standalone overlay window that displays the full answer and an explanation.
    Includes buttons to set the question region, toggle scanning, refresh immediately, and close.
    The overlay is moveable.
    """
    def __init__(self, full_answer, explanation, parent=None):
        super().__init__(None)  # Top-level window
        self.setWindowTitle("FocusFlow Mode")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setFixedSize(OVERLAY_WIDTH, OVERLAY_HEIGHT)
        self._drag_pos = None  # For moving the window
        self.timer = None      # For polling
        self.debounce_timer = None  # For debouncing updates
        self.last_tagged_text = None  # To store last OCR text
        self.scanning_active = False  # State flag for scanning

        # Center the overlay on the screen.
        screen = self.screen().availableGeometry()
        self.move(screen.center().x() - self.width() // 2,
                  screen.center().y() - self.height() // 2)

        # Set up a professional opaque background.
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(*OVERLAY_BACKGROUND_COLOR))
        self.setAutoFillBackground(True)
        self.setPalette(palette)
        self.setStyleSheet("""
            QDialog {
                background-color: #FFFFFF;
                border: 2px solid #E0E0E0;
                border-radius: 15px;
            }
            QLabel {
                color: #333333;
                font-family: 'Segoe UI', sans-serif;
            }
            QPushButton {
                background-color: #ff5f5f;
                color: white;
                border: none;
                border-radius: 20px;
                padding: 10px 12px;
                font-size: 12px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #ff2f2f;
            }
        """)

        # Add drop shadow for a modern look.
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 0, 0, 120))
        self.setGraphicsEffect(shadow)

        self.full_answer = full_answer
        self.explanation = explanation

        layout = QVBoxLayout(self)
        layout.setContentsMargins(OVERLAY_MARGIN, OVERLAY_MARGIN, OVERLAY_MARGIN, OVERLAY_MARGIN)
        layout.setSpacing(OVERLAY_SPACING)

        self.answer_label = QLabel(f"Answer:\n{self.full_answer}", self)
        self.answer_label.setWordWrap(True)
        self.answer_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        layout.addWidget(self.answer_label)

        self.explanation_label = QLabel(f"Explanation:\n{self.explanation}", self)
        self.explanation_label.setWordWrap(True)
        self.explanation_label.setFont(QFont("Segoe UI", 10))
        layout.addWidget(self.explanation_label)

        # Create a horizontal layout for the buttons.
        buttons_layout = QHBoxLayout()

        # Set Question Region button.
        self.set_region_button = QPushButton("Set Question Region", self)
        self.set_region_button.clicked.connect(self.select_region)
        buttons_layout.addWidget(self.set_region_button)

        # Toggle Scanning button.
        self.toggle_scanning_button = QPushButton("Start Scanning", self)
        self.toggle_scanning_button.clicked.connect(self.toggle_scanning)
        buttons_layout.addWidget(self.toggle_scanning_button)

        # Refresh Now button.
        self.refresh_button = QPushButton("Refresh Now", self)
        self.refresh_button.clicked.connect(self.immediate_refresh)
        buttons_layout.addWidget(self.refresh_button)

        # Add a stretch so that the Close button is pushed to the right.
        buttons_layout.addStretch()

        # Close button.
        close_button = QPushButton("Close", self)
        close_button.clicked.connect(self.close)
        buttons_layout.addWidget(close_button)

        # Add the buttons layout to the main vertical layout.
        layout.addLayout(buttons_layout)
        self.setLayout(layout)
    
    def toggle_scanning(self):
        """Toggle scanning on or off."""
        if not self.scanning_active:
            # Start polling
            self.start_polling(interval_ms=POLLING_INTERVAL_MS)
            self.scanning_active = True
            self.toggle_scanning_button.setText("Stop Scanning")
        else:
            # Stop polling
            self.stop_polling()
            self.scanning_active = False
            self.toggle_scanning_button.setText("Start Scanning")

    def select_region(self):
        global QUESTION_REGION
        selector = RegionSelector()
        if selector.exec() == QDialog.Accepted:
            QUESTION_REGION = selector.selected_rect
            full_answer, explanation, merged_json, chosen_index = get_focusflow_data(QUESTION_REGION)
            self.full_answer = full_answer
            self.explanation = explanation
            self.answer_label.setText(f"Answer:\n{self.full_answer}")
            self.explanation_label.setText(f"Explanation:\n{self.explanation}")
            region_tuple = (QUESTION_REGION.x(), QUESTION_REGION.y(), QUESTION_REGION.width(), QUESTION_REGION.height())
            new_tagged_text, _ = get_tagged_words_from_region(region_tuple)
            self.last_tagged_text = new_tagged_text
            # Optionally, create a highlighter overlay.
            try:
                chosen_tag = merged_json["answers"][str(chosen_index)]["tag"]
                global LAST_MAPPING
                if LAST_MAPPING and chosen_tag in LAST_MAPPING:
                    word_info = LAST_MAPPING[chosen_tag]
                    highlight_rect = QRect(
                        QUESTION_REGION.x() + word_info['left'],
                        QUESTION_REGION.y() + word_info['top'],
                        word_info['width'],
                        word_info['height']
                    )
                    # Store reference to prevent garbage collection
                    self._highlighter = AnswerHighlighter(highlight_rect)
            except Exception as e:
                print("Error highlighting answer:", e)

    def immediate_refresh(self):
        # Cancel any pending debounce timer and update immediately.
        if self.debounce_timer:
            self.debounce_timer.stop()
            self.debounce_timer = None
        self.update_focusflow_data()

    def start_polling(self, interval_ms=POLLING_INTERVAL_MS):
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_for_update)
        self.timer.start(interval_ms)

    def check_for_update(self):
        global QUESTION_REGION
        if QUESTION_REGION:
            region_tuple = (QUESTION_REGION.x(), QUESTION_REGION.y(), QUESTION_REGION.width(), QUESTION_REGION.height())
            new_tagged_text, mapping = get_tagged_words_from_region(region_tuple)
            # If there's no previous text or the new text is significantly different.
            if self.last_tagged_text is None or difflib.SequenceMatcher(None, self.last_tagged_text, new_tagged_text).ratio() < OCR_SIMILARITY_THRESHOLD:
                self.pending_tagged_text = new_tagged_text
                # Only start a new debounce timer if one isn't already running.
                if not self.debounce_timer or not self.debounce_timer.isActive():
                    self.debounce_timer = QTimer(self)
                    self.debounce_timer.setSingleShot(True)
                    self.debounce_timer.timeout.connect(self.update_focusflow_data)
                    self.debounce_timer.start(DEBOUNCE_DELAY_MS)

    def update_focusflow_data(self):
        global QUESTION_REGION
        if QUESTION_REGION:
            region_tuple = (QUESTION_REGION.x(), QUESTION_REGION.y(), QUESTION_REGION.width(), QUESTION_REGION.height())
            current_tagged_text, mapping = get_tagged_words_from_region(region_tuple)
            if difflib.SequenceMatcher(None, self.pending_tagged_text, current_tagged_text).ratio() >= OCR_SIMILARITY_THRESHOLD:
                full_answer, explanation, _ = get_focusflow_data(QUESTION_REGION)
                if full_answer != self.full_answer or explanation != self.explanation:
                    self.full_answer = full_answer
                    self.explanation = explanation
                    self.answer_label.setText(f"Answer:\n{self.full_answer}")
                    self.explanation_label.setText(f"Explanation:\n{self.explanation}")
                    self.last_tagged_text = self.pending_tagged_text
        self.debounce_timer = None

    def stop_polling(self):
        if self.timer:
            self.timer.stop()
            self.timer = None
        if self.debounce_timer:
            self.debounce_timer.stop()
            self.debounce_timer = None

    def closeEvent(self, event):
        self.stop_polling()
        event.accept()

    # Make the overlay moveable.
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        event.accept()

def get_explanation(ocr_json, chosen_index):
    """
    Uses the OCR JSON output to generate an explanation for why a particular answer is correct.
    Replace the prompt/model details as needed.
    """
    prompt = (
        "Here is the OCR output in JSON format:\n" + str(ocr_json) +
        "\nExplain why answer option " + str(chosen_index) +
        " is correct. Provide a concise explanation (max 100 words)."
    )
    try:
        from openai import OpenAI
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        explanation = response.choices[0].message.content.strip()
    except Exception as e:
        explanation = "Error generating explanation: " + str(e)
    return explanation

# We'll also store the OCR mapping globally so we can access it for highlighting.
LAST_MAPPING = None

def get_focusflow_data(region):
    """
    Uses OCR/AI processing on the given region to return the full answer, explanation, merged JSON, and correct index.
    This function integrates your existing OCR extraction and AI functions.
    """
    global LAST_MAPPING
    # Convert region (a QRect) to a tuple (x, y, width, height) as expected by pyautogui.
    region_tuple = (region.x(), region.y(), region.width(), region.height())

    tagged_text, mapping = get_tagged_words_from_region(region_tuple)
    LAST_MAPPING = mapping
    ai_json = ai_structure_layout(tagged_text)
    if not ai_json:
        ai_json = fallback_structure(mapping, expected_answers=4)
    if isinstance(ai_json.get("answers"), list):
        ai_json = convert_answers_list_to_dict(ai_json)
    merged_json = merge_ai_and_fallback(ai_json, fallback_structure(mapping, expected_answers=4), mapping)
    correct_index = triple_call_ai_api_json_final(merged_json)
    if correct_index is None:
        correct_index = 1
    try:
        full_answer = merged_json["answers"][str(correct_index)]["text"]
    except Exception as e:
        full_answer = "Unknown"  # Fallback
    explanation = get_explanation(merged_json, correct_index)
    return full_answer, explanation, merged_json, correct_index

def launch_focus_flow(parent_window):
    """
    Checks if a question region is set; if not, launches the region selector.
    Then, processes that region to obtain the full answer and explanation,
    and displays the FocusFlow overlay.
    Also creates an AnswerHighlighter over the correct answer area if possible.
    """
    global QUESTION_REGION
    if QUESTION_REGION is None:
        selector = RegionSelector()
        if selector.exec() == QDialog.Accepted:
            QUESTION_REGION = selector.selected_rect
    full_answer, explanation, merged_json, correct_index = get_focusflow_data(QUESTION_REGION)
    overlay = FocusFlowOverlay(full_answer, explanation, parent=parent_window)
    overlay.show()

    # Attempt to highlight the correct answer.
    try:
        chosen_tag = merged_json["answers"][str(correct_index)]["tag"]
        global LAST_MAPPING
        if LAST_MAPPING and chosen_tag in LAST_MAPPING:
            word_info = LAST_MAPPING[chosen_tag]
            highlight_rect = QRect(
                QUESTION_REGION.x() + word_info['left'],
                QUESTION_REGION.y() + word_info['top'],
                word_info['width'],
                word_info['height']
            )
            # Store reference on overlay to prevent garbage collection
            overlay._highlighter = AnswerHighlighter(highlight_rect)
    except Exception as e:
        print("Error highlighting answer:", e)

    return overlay
