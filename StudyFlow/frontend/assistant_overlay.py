# assistant_overlay.py
"""
Floating assistant overlay that displays quiz processing status.
Shows question, answer, and reasoning in real-time.
Always stays on top and positioned on the left side of the screen.
"""

import sys
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QGraphicsDropShadowEffect,
    QFrame, QSizePolicy
)
from PySide6.QtGui import (
    QFont, QColor, QPainter, QLinearGradient, QBrush, QPen, QPainterPath
)
from PySide6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QTimer, Signal, QObject
)


# ============ Overlay State Manager (Singleton) ============
class OverlayState(QObject):
    """
    Singleton to communicate between the processing code and the overlay UI.
    Emits signals that the overlay listens to.
    """
    state_changed = Signal(str, dict)  # (state, data)

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            QObject.__init__(cls._instance)
        return cls._instance

    def set_idle(self):
        self.state_changed.emit("idle", {})

    def set_processing(self, question=""):
        self.state_changed.emit("processing", {"question": question})

    def set_answered(self, question, answer, reasoning="", confidence="", method=""):
        self.state_changed.emit("answered", {
            "question": question,
            "answer": answer,
            "reasoning": reasoning,
            "confidence": confidence,
            "method": method
        })

    def set_error(self, message):
        self.state_changed.emit("error", {"message": message})


# Global state instance
overlay_state = OverlayState()


# ============ Dark Panel Background ============
class DarkPanel(QWidget):
    """Dark semi-transparent panel with rounded corners."""

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Dark gradient background
        rect = self.rect()
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0, QColor(30, 30, 40, 240))
        gradient.setColorAt(1, QColor(20, 20, 30, 250))

        # Rounded rectangle path
        path = QPainterPath()
        path.addRoundedRect(rect.x(), rect.y(), rect.width(), rect.height(), 16, 16)

        # Fill background
        painter.fillPath(path, QBrush(gradient))

        # Subtle border
        painter.setPen(QPen(QColor(80, 80, 100, 150), 1))
        painter.drawPath(path)

        super().paintEvent(event)


# ============ Section Label ============
class SectionLabel(QLabel):
    """Styled section header label."""

    def __init__(self, text, color="#ff5f5f"):
        super().__init__(text)
        self.setStyleSheet(f"""
            QLabel {{
                color: {color};
                font-size: 11px;
                font-weight: bold;
                letter-spacing: 1px;
                padding: 0px;
                margin: 0px;
            }}
        """)


# ============ Content Label ============
class ContentLabel(QLabel):
    """Styled content text label with word wrap."""

    def __init__(self, text=""):
        super().__init__(text)
        self.setWordWrap(True)
        self.setStyleSheet("""
            QLabel {
                color: #e0e0e0;
                font-size: 13px;
                padding: 0px;
                margin: 0px;
                line-height: 1.4;
            }
        """)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)


# ============ Main Overlay Window ============
class AssistantOverlay(QWidget):
    """
    Floating overlay window that displays quiz processing status.
    """

    def __init__(self):
        super().__init__()

        # Window setup - frameless, always on top, transparent background
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint |
            Qt.Tool  # Don't show in taskbar
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # Size and position
        self.setFixedWidth(280)
        self.setMinimumHeight(200)

        # Position on left side of screen
        self.position_on_screen()

        # Build UI
        self.setup_ui()

        # Connect to state manager
        overlay_state.state_changed.connect(self.on_state_changed)

        # Drop shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(30)
        shadow.setOffset(5, 5)
        shadow.setColor(QColor(0, 0, 0, 100))
        self.setGraphicsEffect(shadow)

        # Fade in animation
        self.setWindowOpacity(0)
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(500)
        self.fade_anim.setStartValue(0)
        self.fade_anim.setEndValue(1)
        self.fade_anim.setEasingCurve(QEasingCurve.OutCubic)

    def position_on_screen(self):
        """Position the overlay on the left side of the screen."""
        screen = QApplication.primaryScreen().geometry()
        x = 20  # 20px from left edge
        y = (screen.height() - 400) // 2  # Vertically centered
        self.move(x, y)

    def setup_ui(self):
        """Build the overlay UI."""
        # Main container (dark panel)
        self.panel = DarkPanel(self)

        # Main layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.panel)

        # Panel layout
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(16, 16, 16, 16)
        panel_layout.setSpacing(12)

        # ===== Title =====
        title_layout = QVBoxLayout()
        title_layout.setSpacing(2)

        title = QLabel("StudyFlow")
        title.setStyleSheet("""
            QLabel {
                color: #ff5f5f;
                font-size: 18px;
                font-weight: bold;
            }
        """)
        title_layout.addWidget(title)

        subtitle = QLabel("Assistant")
        subtitle.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 11px;
                font-weight: normal;
            }
        """)
        title_layout.addWidget(subtitle)

        panel_layout.addLayout(title_layout)

        # ===== Divider =====
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet("background-color: #444455;")
        divider.setFixedHeight(1)
        panel_layout.addWidget(divider)

        # ===== Status =====
        self.status_label = QLabel("Waiting for quiz...")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 12px;
                font-style: italic;
            }
        """)
        panel_layout.addWidget(self.status_label)

        # ===== Question Section =====
        self.question_section = QWidget()
        question_layout = QVBoxLayout(self.question_section)
        question_layout.setContentsMargins(0, 0, 0, 0)
        question_layout.setSpacing(4)

        self.question_header = SectionLabel("QUESTION")
        question_layout.addWidget(self.question_header)

        self.question_text = ContentLabel()
        question_layout.addWidget(self.question_text)

        panel_layout.addWidget(self.question_section)
        self.question_section.hide()

        # ===== Answer Section =====
        self.answer_section = QWidget()
        answer_layout = QVBoxLayout(self.answer_section)
        answer_layout.setContentsMargins(0, 0, 0, 0)
        answer_layout.setSpacing(4)

        self.answer_header = SectionLabel("ANSWER", "#4ade80")
        answer_layout.addWidget(self.answer_header)

        self.answer_text = ContentLabel()
        self.answer_text.setStyleSheet("""
            QLabel {
                color: #4ade80;
                font-size: 14px;
                font-weight: bold;
                padding: 0px;
                margin: 0px;
            }
        """)
        answer_layout.addWidget(self.answer_text)

        panel_layout.addWidget(self.answer_section)
        self.answer_section.hide()

        # ===== Reasoning Section =====
        self.reasoning_section = QWidget()
        reasoning_layout = QVBoxLayout(self.reasoning_section)
        reasoning_layout.setContentsMargins(0, 0, 0, 0)
        reasoning_layout.setSpacing(4)

        self.reasoning_header = SectionLabel("REASONING", "#888888")
        reasoning_layout.addWidget(self.reasoning_header)

        self.reasoning_text = ContentLabel()
        self.reasoning_text.setStyleSheet("""
            QLabel {
                color: #aaaaaa;
                font-size: 12px;
                padding: 0px;
                margin: 0px;
            }
        """)
        reasoning_layout.addWidget(self.reasoning_text)

        panel_layout.addWidget(self.reasoning_section)
        self.reasoning_section.hide()

        # ===== Footer (method & confidence) =====
        self.footer = QLabel()
        self.footer.setStyleSheet("""
            QLabel {
                color: #666666;
                font-size: 10px;
            }
        """)
        panel_layout.addWidget(self.footer)
        self.footer.hide()

        # Add stretch at bottom
        panel_layout.addStretch()

    def on_state_changed(self, state, data):
        """Handle state changes from the processing code."""
        if state == "idle":
            self.show_idle()
        elif state == "processing":
            self.show_processing(data.get("question", ""))
        elif state == "answered":
            self.show_answered(
                data.get("question", ""),
                data.get("answer", ""),
                data.get("reasoning", ""),
                data.get("confidence", ""),
                data.get("method", "")
            )
        elif state == "error":
            self.show_error(data.get("message", "Unknown error"))

    def show_idle(self):
        """Show idle state."""
        self.status_label.setText("Waiting for quiz...")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #888888;
                font-size: 12px;
                font-style: italic;
            }
        """)
        self.status_label.show()
        self.question_section.hide()
        self.answer_section.hide()
        self.reasoning_section.hide()
        self.footer.hide()
        self.adjustSize()

    def show_processing(self, question):
        """Show processing state with question."""
        self.status_label.setText("Analyzing...")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #f59e0b;
                font-size: 12px;
                font-weight: bold;
            }
        """)
        self.status_label.show()

        if question:
            # Truncate long questions
            display_q = question[:150] + "..." if len(question) > 150 else question
            self.question_text.setText(display_q)
            self.question_section.show()

        self.answer_section.hide()
        self.reasoning_section.hide()
        self.footer.hide()
        self.adjustSize()

    def show_answered(self, question, answer, reasoning="", confidence="", method=""):
        """Show answered state with full info."""
        self.status_label.setText("Answer found!")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #4ade80;
                font-size: 12px;
                font-weight: bold;
            }
        """)

        # Question
        if question:
            display_q = question[:150] + "..." if len(question) > 150 else question
            self.question_text.setText(display_q)
            self.question_section.show()

        # Answer
        if answer:
            self.answer_text.setText(answer)
            self.answer_section.show()

        # Reasoning
        if reasoning:
            display_r = reasoning[:200] + "..." if len(reasoning) > 200 else reasoning
            self.reasoning_text.setText(display_r)
            self.reasoning_section.show()
        else:
            self.reasoning_section.hide()

        # Footer with method and confidence
        footer_parts = []
        if method:
            method_emoji = {'cache': '', 'text_api': '', 'vision_api': ''}.get(method, '')
            footer_parts.append(f"{method_emoji} {method.upper()}")
        if confidence:
            footer_parts.append(f"Confidence: {confidence}")

        if footer_parts:
            self.footer.setText(" | ".join(footer_parts))
            self.footer.show()
        else:
            self.footer.hide()

        self.adjustSize()

    def show_error(self, message):
        """Show error state."""
        self.status_label.setText(f"Error: {message}")
        self.status_label.setStyleSheet("""
            QLabel {
                color: #ef4444;
                font-size: 12px;
                font-weight: bold;
            }
        """)
        self.status_label.show()
        self.question_section.hide()
        self.answer_section.hide()
        self.reasoning_section.hide()
        self.footer.hide()
        self.adjustSize()

    def fade_in(self):
        """Fade in the overlay."""
        self.show()
        self.fade_anim.setDirection(QPropertyAnimation.Forward)
        self.fade_anim.start()

    def fade_out(self):
        """Fade out the overlay."""
        self.fade_anim.setDirection(QPropertyAnimation.Backward)
        self.fade_anim.finished.connect(self.hide)
        self.fade_anim.start()


# ============ Global Overlay Instance ============
_overlay_instance = None


def get_overlay():
    """Get or create the global overlay instance."""
    global _overlay_instance
    if _overlay_instance is None:
        _overlay_instance = AssistantOverlay()
    return _overlay_instance


def show_overlay():
    """Show the assistant overlay."""
    overlay = get_overlay()
    overlay.fade_in()
    return overlay


def hide_overlay():
    """Hide the assistant overlay."""
    global _overlay_instance
    if _overlay_instance:
        _overlay_instance.fade_out()


# ============ Test / Standalone ============
if __name__ == "__main__":
    app = QApplication(sys.argv)

    overlay = show_overlay()

    # Test state transitions
    def test_states():
        overlay_state.set_processing("What is the capital of France?")

        QTimer.singleShot(2000, lambda: overlay_state.set_answered(
            question="What is the capital of France?",
            answer="B. Paris",
            reasoning="Paris is the capital and largest city of France, located in the north-central part of the country.",
            confidence="high",
            method="text_api"
        ))

        QTimer.singleShot(5000, lambda: overlay_state.set_idle())

    QTimer.singleShot(500, test_states)

    sys.exit(app.exec())
