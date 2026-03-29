import sys
import os

# Get the Media directory path (works on Mac and Windows)
MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "Media")

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QLabel,
    QHBoxLayout, QGraphicsDropShadowEffect, QSplashScreen, QGridLayout, QFrame
)
from PySide6.QtGui import (
    QFont, QPixmap, QColor, QPainter
)
from PySide6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QTimer, QRect
)

# Attempt to import your quiz GUI, or use a placeholder.
try:
    from StudyFlow.frontend.gui import MainWindow as QuizMainWindow
except ImportError as e:
    print(f"Warning: Could not import QuizMainWindow: {e}")
    class QuizMainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Quiz Window Placeholder")

###############################################################################
# ZenCard: Minimal card with subtle hover effect
###############################################################################
class ZenCard(QFrame):
    def __init__(self, title, description, icon_path, button_text, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: #FFFFFF;
                border-radius: 12px;
                border: 1px solid #E8E5E1;
            }
            QFrame:hover {
                border: 1px solid #8B9D83;
            }
        """)

        # Add subtle shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 20))
        shadow.setOffset(0, 4)
        self.setGraphicsEffect(shadow)

        # Layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(20)

        # Icon
        icon_label = QLabel(self)
        pixmap = QPixmap(icon_path)
        pixmap = pixmap.scaled(80, 80, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        icon_label.setPixmap(pixmap)
        icon_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_label)

        # Title
        title_label = QLabel(title, self)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            font-size: 24px;
            font-weight: 500;
            color: #2C2C2C;
            letter-spacing: -0.5px;
        """)
        layout.addWidget(title_label)

        # Description
        desc_label = QLabel(description, self)
        desc_label.setAlignment(Qt.AlignCenter)
        desc_label.setWordWrap(True)
        desc_label.setStyleSheet("""
            font-size: 14px;
            font-weight: 400;
            color: #6B6B6B;
            line-height: 1.7;
        """)
        layout.addWidget(desc_label)

        layout.addStretch()

        # Button
        self.action_button = QPushButton(button_text, self)
        self.action_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #8B9D83;
                font-size: 15px;
                font-weight: 500;
                border: 2px solid #8B9D83;
                border-radius: 8px;
                padding: 12px 24px;
            }
            QPushButton:hover {
                background-color: #8B9D83;
                color: white;
            }
        """)
        layout.addWidget(self.action_button, alignment=Qt.AlignCenter)

        # Animation properties
        self._hover_anim = None
        self._original_geometry = None

    def enterEvent(self, event):
        """Subtle lift on hover"""
        self._original_geometry = self.geometry()
        self._hover_anim = QPropertyAnimation(self, b"geometry")
        self._hover_anim.setDuration(200)
        self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)
        geo = self.geometry()
        self._hover_anim.setStartValue(geo)
        self._hover_anim.setEndValue(QRect(geo.x(), geo.y() - 4, geo.width(), geo.height()))
        self._hover_anim.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """Return to original position"""
        if self._original_geometry:
            self._hover_anim = QPropertyAnimation(self, b"geometry")
            self._hover_anim.setDuration(200)
            self._hover_anim.setEasingCurve(QEasingCurve.OutCubic)
            self._hover_anim.setStartValue(self.geometry())
            self._hover_anim.setEndValue(self._original_geometry)
            self._hover_anim.start()
        super().leaveEvent(event)

###############################################################################
# ZenDashboard: Complete redesign with dashboard tiles
###############################################################################
class ZenDashboard(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("StudyFlow")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(1100, 720)

        # Fade-in animation
        self.setWindowOpacity(0)
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(600)
        self.fade_anim.setStartValue(0)
        self.fade_anim.setEndValue(1)
        self.fade_anim.setEasingCurve(QEasingCurve.OutCubic)
        self.fade_anim.start()

        # Main container
        self.main_widget = QWidget(self)
        self.main_widget.setStyleSheet("""
            QWidget {
                background-color: #FAF8F5;
                border-radius: 16px;
            }
        """)
        self.setCentralWidget(self.main_widget)

        # Drop shadow on window
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(60)
        shadow.setOffset(0, 10)
        shadow.setColor(QColor(0, 0, 0, 40))
        self.setGraphicsEffect(shadow)

        # Main layout
        main_layout = QVBoxLayout(self.main_widget)
        main_layout.setContentsMargins(48, 48, 48, 48)
        main_layout.setSpacing(40)

        # ---------------------------
        # Header Section
        # ---------------------------
        header_layout = QHBoxLayout()

        # Logo and title
        logo_title_layout = QVBoxLayout()
        logo_title_layout.setSpacing(12)

        # Small logo
        logo_label = QLabel(self)
        logo_pixmap = QPixmap(os.path.join(MEDIA_DIR, "StudyFlow.png"))
        logo_pixmap = logo_pixmap.scaled(48, 48, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        logo_label.setPixmap(logo_pixmap)
        logo_title_layout.addWidget(logo_label)

        # Title
        title_label = QLabel("StudyFlow", self)
        title_label.setStyleSheet("""
            font-size: 28px;
            font-weight: 300;
            color: #2C2C2C;
            letter-spacing: -0.5px;
        """)
        logo_title_layout.addWidget(title_label)

        header_layout.addLayout(logo_title_layout)
        header_layout.addStretch()

        # Close button (minimal)
        close_button = QPushButton("×", self)
        close_button.setFixedSize(32, 32)
        close_button.setStyleSheet("""
            QPushButton {
                color: #6B6B6B;
                font-size: 24px;
                font-weight: 300;
                background-color: transparent;
                border: none;
                border-radius: 16px;
            }
            QPushButton:hover {
                background-color: #E8E5E1;
                color: #2C2C2C;
            }
        """)
        close_button.clicked.connect(self.close)
        header_layout.addWidget(close_button, alignment=Qt.AlignTop)

        main_layout.addLayout(header_layout)

        # ---------------------------
        # Subtitle
        # ---------------------------
        subtitle = QLabel("Choose your path to mindful learning", self)
        subtitle.setStyleSheet("""
            font-size: 16px;
            font-weight: 400;
            color: #6B6B6B;
            margin-bottom: 20px;
        """)
        main_layout.addWidget(subtitle)

        # ---------------------------
        # Dashboard Grid
        # ---------------------------
        grid_layout = QGridLayout()
        grid_layout.setSpacing(24)
        grid_layout.setContentsMargins(0, 0, 0, 0)

        # FreeFlow Card
        self.freeflow_card = ZenCard(
            "FreeFlow",
            "Automate repetitive study tasks and stay focused on what matters most",
            os.path.join(MEDIA_DIR, "FreeFlow.png"),
            "Start FreeFlow",
            self
        )
        self.freeflow_card.action_button.clicked.connect(self.show_freeflow_options)
        grid_layout.addWidget(self.freeflow_card, 0, 0)

        # FocusFlow Card
        self.focusflow_card = ZenCard(
            "FocusFlow",
            "Real-time guidance that helps you understand as you learn",
            os.path.join(MEDIA_DIR, "FocusFlow.png"),
            "Start FocusFlow",
            self
        )
        self.focusflow_card.action_button.clicked.connect(self.start_focus_flow)
        grid_layout.addWidget(self.focusflow_card, 0, 1)

        # DeepFlow Card
        self.deepflow_card = ZenCard(
            "DeepFlow",
            "Transform any topic into interactive practice questions",
            os.path.join(MEDIA_DIR, "DeepFlow.png"),
            "Start DeepFlow",
            self
        )
        self.deepflow_card.action_button.clicked.connect(self.open_deepflow)
        grid_layout.addWidget(self.deepflow_card, 0, 2)

        main_layout.addLayout(grid_layout)
        main_layout.addStretch()

        # For window dragging
        self._drag_pos = None

    def show_freeflow_options(self):
        """Show options for FreeFlow (Classic or Vision Mode)"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton

        dialog = QDialog(self)
        dialog.setWindowTitle("FreeFlow Options")
        dialog.setFixedSize(400, 280)
        dialog.setStyleSheet("""
            QDialog {
                background-color: #FAF8F5;
            }
        """)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(20)

        title = QLabel("Choose your mode", dialog)
        title.setStyleSheet("""
            font-size: 20px;
            font-weight: 500;
            color: #2C2C2C;
        """)
        layout.addWidget(title)

        desc = QLabel("Select between classic OCR or AI-powered vision", dialog)
        desc.setStyleSheet("""
            font-size: 14px;
            color: #6B6B6B;
        """)
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # Classic button
        classic_btn = QPushButton("Classic Mode", dialog)
        classic_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #8B9D83;
                font-size: 15px;
                font-weight: 500;
                border: 2px solid #8B9D83;
                border-radius: 8px;
                padding: 12px 24px;
            }
            QPushButton:hover {
                background-color: #8B9D83;
                color: white;
            }
        """)
        classic_btn.clicked.connect(lambda: (dialog.accept(), self.open_quiz_gui()))
        layout.addWidget(classic_btn)

        # Vision button
        vision_btn = QPushButton("Vision Mode", dialog)
        vision_btn.setStyleSheet("""
            QPushButton {
                background-color: #8B9D83;
                color: white;
                font-size: 15px;
                font-weight: 500;
                border: 2px solid #8B9D83;
                border-radius: 8px;
                padding: 12px 24px;
            }
            QPushButton:hover {
                background-color: #7A8C73;
            }
        """)
        vision_btn.clicked.connect(lambda: (dialog.accept(), self.start_vision_mode()))
        layout.addWidget(vision_btn)

        dialog.exec()

    # ~~~~~~~~~~~~~~ MOUSE DRAG TO MOVE WINDOW ~~~~~~~~~~~~~~
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        self._drag_pos = None
        event.accept()

    def open_quiz_gui(self):
        """Opens the classic quiz GUI."""
        self.quiz_window = QuizMainWindow()
        self.quiz_window.show()

    def start_focus_flow(self):
        """Starts FocusFlow mode with real-time overlay."""
        from StudyFlow.frontend.focusflow import FocusFlowOverlay
        full_answer = "FocusFlow"
        explanation = "Real-time guidance that helps you understand as you learn."
        self.focusflow_overlay = FocusFlowOverlay(full_answer, explanation)
        self.focusflow_overlay.show()

    def open_deepflow(self):
        """Opens the DeepFlow practice quiz generator."""
        from .deepflow_gui import DeepFlowWindow
        self.deepflow_window = DeepFlowWindow()
        self.deepflow_window.show()

    def start_vision_mode(self):
        """Starts Vision Mode - AI-powered quiz solving."""
        from PySide6.QtWidgets import QMessageBox
        from StudyFlow.frontend.button_capture import capture_button_template

        # First, capture the submit button
        reply = QMessageBox.question(
            self,
            "Capture Submit Button",
            "First, we need to capture your Submit button.\n\n"
            "Step 1: Click 'Yes' below\n"
            "Step 2: Hover over the TOP-LEFT corner of the Submit button and press Enter\n"
            "Step 3: Hover over the BOTTOM-RIGHT corner of the Submit button and press Enter\n\n"
            "Ready?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply != QMessageBox.Yes:
            return

        # Capture the button template
        capture_button_template(self)

        # Show confirmation dialog
        reply = QMessageBox.question(
            self,
            "Start Vision Mode",
            "Vision Mode will analyze your full screen using AI.\n\n"
            "Make sure a quiz is visible on screen before starting.\n\n"
            "The app will hide and start processing in 3 seconds.\n\n"
            "Press ESC to stop at any time.\n\n"
            "Start now?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes
        )

        if reply == QMessageBox.Yes:
            # Hide main window immediately
            self.hide()
            # Process events to ensure window actually hides
            QApplication.processEvents()
            # Use QTimer to delay start (doesn't block event loop)
            QTimer.singleShot(3000, self._run_vision_mode)

    def _run_vision_mode(self):
        """Actually runs vision mode after delay."""
        from PySide6.QtWidgets import QMessageBox
        from StudyFlow.frontend.core_engine import start_quiz_vision

        # Run vision mode
        questions, errors = start_quiz_vision()

        # Show results
        self.show()
        if errors:
            QMessageBox.warning(
                self,
                "Vision Mode Complete",
                f"Answered {questions} questions.\n\nErrors:\n" + "\n".join(errors)
            )
        else:
            QMessageBox.information(
                self,
                "Vision Mode Complete",
                f"Successfully answered {questions} questions!"
            )

# Prevent garbage collection
main_window = None

def show_main_window(splash):
    global main_window
    main_window = ZenDashboard()
    main_window.show()
    splash.finish(main_window)

def main():
    app = QApplication(sys.argv)
    splash_pix = QPixmap(os.path.join(MEDIA_DIR, "StudyFlow.png"))
    splash_pix = splash_pix.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    splash = QSplashScreen(splash_pix)
    splash.setStyleSheet("background-color: #FAF8F5;")
    splash.show()
    QTimer.singleShot(1500, lambda: show_main_window(splash))
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
