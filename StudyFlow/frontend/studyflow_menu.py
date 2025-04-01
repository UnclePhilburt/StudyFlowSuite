import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QLabel,
    QHBoxLayout, QGraphicsDropShadowEffect, QSplashScreen, QTabBar,
    QStackedWidget
)
from PySide6.QtGui import (
    QFont, QPixmap, QColor, QPainter, QLinearGradient, QBrush
)
from PySide6.QtCore import (
    Qt, QPoint, QRect, QPropertyAnimation, QEasingCurve, QTimer
)

# Attempt to import your quiz GUI, or use a placeholder.
try:
    from StudyFlow.gui import MainWindow as QuizMainWindow
except ImportError:
    class QuizMainWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.setWindowTitle("Quiz Window Placeholder")

###############################################################################
# GradientWidget: Pastel background with rounded corners
###############################################################################
class GradientWidget(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0, QColor(220, 239, 255))  # Light pastel at top
        gradient.setColorAt(1, QColor(174, 201, 245))  # Slightly darker pastel
        painter.setBrush(QBrush(gradient))
        corner_radius = 16
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, corner_radius, corner_radius)
        super().paintEvent(event)

###############################################################################
# GlowButton: Red glow on hover, more rounded corners
###############################################################################
class GlowButton(QPushButton):
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setStyleSheet("""
            QPushButton {
                background-color: #ff5f5f;
                color: white;
                font-size: 16px;
                font-weight: 600;
                border-radius: 30px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #ff2f2f;
            }
        """)
        self.setFixedHeight(40)

    def enterEvent(self, event):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(255, 47, 47, 150))
        shadow.setOffset(0, 0)
        self.setGraphicsEffect(shadow)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setGraphicsEffect(None)
        super().leaveEvent(event)

###############################################################################
# FlashcardWidget (kept for legacy or future use, not integrated now)
###############################################################################
class FlashcardWidget(QWidget):
    def __init__(self, question, answer, parent=None):
        super().__init__(parent)
        self.question = question
        self.answer = answer
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        self.question_label = QLabel(f"Q: {self.question}", self)
        self.question_label.setWordWrap(True)
        layout.addWidget(self.question_label)
        self.answer_label = QLabel(f"A: {self.answer}", self)
        self.answer_label.setWordWrap(True)
        self.answer_label.setVisible(False)
        layout.addWidget(self.answer_label)
        self.toggle_button = QPushButton("Show Answer", self)
        self.toggle_button.clicked.connect(self.toggle_answer)
        layout.addWidget(self.toggle_button)
        self.setLayout(layout)

    def toggle_answer(self):
        if self.answer_label.isVisible():
            self.answer_label.setVisible(False)
            self.toggle_button.setText("Show Answer")
        else:
            self.answer_label.setVisible(True)
            self.toggle_button.setText("Hide Answer")

###############################################################################
# ModernMenu QMainWindow (Main Application Window)
###############################################################################
class ModernMenu(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("StudyFlow")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(600, 400)

        # Fade-in animation
        self.setWindowOpacity(0)
        self.fade_anim = QPropertyAnimation(self, b"windowOpacity")
        self.fade_anim.setDuration(800)
        self.fade_anim.setStartValue(0)
        self.fade_anim.setEndValue(1)
        self.fade_anim.setEasingCurve(QEasingCurve.InOutQuad)
        self.fade_anim.start()

        # Drop shadow
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(40)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.setGraphicsEffect(shadow)

        # Main gradient background
        self.gradient_widget = GradientWidget(self)
        self.setCentralWidget(self.gradient_widget)

        # Main vertical layout
        self.main_layout = QVBoxLayout(self.gradient_widget)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(10)

        # ---------------------------
        # Top Bar
        # ---------------------------
        self.top_bar = QWidget(self.gradient_widget)
        self.top_bar_layout = QHBoxLayout(self.top_bar)
        self.top_bar_layout.setContentsMargins(0, 0, 0, 0)
        self.top_bar_layout.setSpacing(10)

        # "StudyFlow" label
        self.title_label = QLabel("StudyFlow", self.top_bar)
        self.title_label.setStyleSheet("color: #333333; font-size: 18px; font-weight: bold;")
        self.top_bar_layout.addWidget(self.title_label)

        # Spacer
        spacer = QWidget()
        spacer.setFixedWidth(20)
        self.top_bar_layout.addWidget(spacer)

        # Tab bar - now with four tabs: Home, FreeFlow, FocusFlow, DeepFlow
        self.tab_bar = QTabBar(self.top_bar)
        self.tab_bar.setStyleSheet("""
            QTabBar::tab {
                background: transparent;
                border: none;
                font-weight: bold;
                color: #333333;
                font-size: 14px;
                padding: 4px 8px;
            }
            QTabBar::tab:hover {
                background-color: rgba(255, 95, 95, 0.1);
                border-radius: 4px;
            }
            QTabBar::tab:selected {
                background: transparent;
                border: none;
                color: #ff5f5f;
            }
        """)
        self.tab_bar.addTab("Home")       # index 0
        self.tab_bar.addTab("FreeFlow")     # index 1
        self.tab_bar.addTab("FocusFlow")    # index 2
        self.tab_bar.addTab("DeepFlow")     # index 3
        self.tab_bar.setCurrentIndex(0)
        self.tab_bar.currentChanged.connect(self.slide_to_index)
        self.top_bar_layout.addWidget(self.tab_bar)
        self.top_bar_layout.addStretch()

        # Close button
        self.close_button = QPushButton("×", self.top_bar)
        self.close_button.setFixedSize(25, 25)
        self.close_button.setStyleSheet("""
            QPushButton {
                color: #333333;
                font-size: 20px;
                font-weight: bold;
                background-color: transparent;
                border: none;
            }
            QPushButton:hover {
                color: #ffdddd;
            }
        """)
        self.close_button.clicked.connect(self.close)
        self.top_bar_layout.addWidget(self.close_button)

        self.main_layout.addWidget(self.top_bar, 0, Qt.AlignTop)

        # ---------------------------
        # Stacked Widget (Pages)
        # ---------------------------
        self.stacked_widget = QStackedWidget(self.gradient_widget)
        self.main_layout.addWidget(self.stacked_widget, 1)

        # -- (0) Home Page
        self.home_page = QWidget()
        home_layout = QVBoxLayout(self.home_page)
        home_layout.setContentsMargins(20, 20, 20, 20)
        home_layout.setSpacing(20)

        self.image_label = QLabel(self.home_page)
        pixmap = QPixmap(r"C:\StudyFlowSuite\StudyFlow\Media\StudyFlow.png")
        pixmap = pixmap.scaled(400, 400, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(pixmap)
        self.image_label.setAlignment(Qt.AlignCenter)
        home_layout.addWidget(self.image_label)

        self.subtitle_label = QLabel("Simplifying Studying, Amplifying Success.", self.home_page)
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setStyleSheet("color: #333333; font-size: 20px; font-weight: bold;")
        home_layout.addWidget(self.subtitle_label)

        self.home_page.setLayout(home_layout)
        self.stacked_widget.addWidget(self.home_page)  # index 0

        # -- (1) FreeFlow Page
        self.freeflow_page = QWidget()
        freeflow_layout = QVBoxLayout(self.freeflow_page)
        freeflow_layout.setContentsMargins(20, 20, 20, 20)
        freeflow_layout.setSpacing(20)

        self.flowfree_image_label = QLabel(self.freeflow_page)
        flowfree_pixmap = QPixmap(r"C:\StudyFlowSuite\StudyFlow\Media\FreeFlow.png")
        flowfree_pixmap = flowfree_pixmap.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.flowfree_image_label.setPixmap(flowfree_pixmap)
        self.flowfree_image_label.setAlignment(Qt.AlignCenter)
        freeflow_layout.addWidget(self.flowfree_image_label)

        self.flowfree_desc = QLabel(
            "FreeFlow is your advanced study companion, streamlining repetitive tasks "
            "so you can stay fully focused on learning.",
            self.freeflow_page)
        self.flowfree_desc.setAlignment(Qt.AlignCenter)
        self.flowfree_desc.setWordWrap(True)
        self.flowfree_desc.setStyleSheet("""
            font-size: 18px;
            color: #333333;
            font-weight: bold;
            padding: 10px;
        """)
        freeflow_layout.addWidget(self.flowfree_desc)

        self.flowfree_button = GlowButton("Open FreeFlow", self.freeflow_page)
        self.flowfree_button.clicked.connect(self.open_quiz_gui)
        freeflow_layout.addWidget(self.flowfree_button, alignment=Qt.AlignCenter)

        self.freeflow_page.setLayout(freeflow_layout)
        self.stacked_widget.addWidget(self.freeflow_page)  # index 1

        # -- (2) FocusFlow Page
        self.focusflow_page = QWidget()
        focus_layout = QVBoxLayout(self.focusflow_page)
        focus_layout.setContentsMargins(20, 20, 20, 20)
        focus_layout.setSpacing(20)

        self.focusflow_image_label = QLabel(self.focusflow_page)
        focusflow_pixmap = QPixmap(r"C:\StudyFlowSuite\StudyFlow\Media\FocusFlow.png")
        focusflow_pixmap = focusflow_pixmap.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.focusflow_image_label.setPixmap(focusflow_pixmap)
        self.focusflow_image_label.setAlignment(Qt.AlignCenter)
        focus_layout.addWidget(self.focusflow_image_label)

        self.focusflow_desc = QLabel(
            "FocusFlow puts understanding front and center — so you're not just studying, you're truly getting it.",
            self.focusflow_page)
        self.focusflow_desc.setAlignment(Qt.AlignCenter)
        self.focusflow_desc.setWordWrap(True)
        self.focusflow_desc.setStyleSheet("""
            font-size: 18px;
            color: #333333;
            font-weight: bold;
            padding: 10px;
        """)
        focus_layout.addWidget(self.focusflow_desc)

        self.focusflow_button = GlowButton("Open FocusFlow", self.focusflow_page)
        self.focusflow_button.clicked.connect(self.start_focus_flow)
        focus_layout.addWidget(self.focusflow_button, alignment=Qt.AlignCenter)

        self.focusflow_page.setLayout(focus_layout)
        self.stacked_widget.addWidget(self.focusflow_page)  # index 2

        # -- (3) DeepFlow Page
        self.deepflow_page = QWidget()
        deep_layout = QVBoxLayout(self.deepflow_page)
        deep_layout.setContentsMargins(20, 20, 20, 20)
        deep_layout.setSpacing(20)

        self.deepflow_image_label = QLabel(self.deepflow_page)
        deepflow_pixmap = QPixmap(r"C:\StudyFlowSuite\StudyFlow\Media\DeepFlow.png")
        deepflow_pixmap = deepflow_pixmap.scaled(300, 300, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.deepflow_image_label.setPixmap(deepflow_pixmap)
        self.deepflow_image_label.setAlignment(Qt.AlignCenter)
        deep_layout.addWidget(self.deepflow_image_label)

        self.deepflow_desc = QLabel(
            "DeepFlow takes your understanding to the next level by breaking down complex topics into interactive quizzes.",
            self.deepflow_page)
        self.deepflow_desc.setAlignment(Qt.AlignCenter)
        self.deepflow_desc.setWordWrap(True)
        self.deepflow_desc.setStyleSheet("""
            font-size: 18px;
            color: #333333;
            font-weight: bold;
            padding: 10px;
        """)
        deep_layout.addWidget(self.deepflow_desc)

        self.deepflow_button = GlowButton("Open DeepFlow", self.deepflow_page)
        # Import DeepFlowWindow from deepflow_gui.py when the button is clicked
        self.deepflow_button.clicked.connect(self.open_deepflow)
        deep_layout.addWidget(self.deepflow_button, alignment=Qt.AlignCenter)

        self.deepflow_page.setLayout(deep_layout)
        self.stacked_widget.addWidget(self.deepflow_page)  # index 3

        # For window dragging in the main window
        self._drag_pos = None

    def slide_to_index(self, index):
        """Flicker-Free Sliding Transition (inverted direction)."""
        current_index = self.stacked_widget.currentIndex()
        if index == current_index:
            return
        current_widget = self.stacked_widget.currentWidget()
        next_widget = self.stacked_widget.widget(index)
        if not next_widget:
            return
        w = self.stacked_widget.width()
        h = self.stacked_widget.height()
        direction = 1 if index > current_index else -1
        next_widget.setVisible(False)
        next_widget.setGeometry(QRect(direction * w, 0, w, h))
        self.anim_current = QPropertyAnimation(current_widget, b"geometry")
        self.anim_current.setDuration(400)
        self.anim_current.setEasingCurve(QEasingCurve.InOutQuad)
        self.anim_current.setStartValue(QRect(0, 0, w, h))
        self.anim_current.setEndValue(QRect(-direction * w, 0, w, h))
        self.anim_next = QPropertyAnimation(next_widget, b"geometry")
        self.anim_next.setDuration(400)
        self.anim_next.setEasingCurve(QEasingCurve.InOutQuad)
        self.anim_next.setStartValue(QRect(direction * w, 0, w, h))
        self.anim_next.setEndValue(QRect(0, 0, w, h))
        def finalize_switch():
            self.stacked_widget.setCurrentIndex(index)
            current_widget.setGeometry(QRect(0, 0, w, h))
            next_widget.setGeometry(QRect(0, 0, w, h))
            next_widget.setVisible(True)
        next_widget.setVisible(True)
        self.anim_next.finished.connect(finalize_switch)
        self.anim_current.start()
        self.anim_next.start()

    # ~~~~~~~~~~~~~~ MOUSE DRAG TO MOVE WINDOW (Main Window) ~~~~~~~~~~~~~~
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
        """Opens your quiz GUI."""
        self.quiz_window = QuizMainWindow()
        self.quiz_window.show()
    
    def start_focus_flow(self):
        """Starts FocusFlow mode by displaying a separate floating overlay with the full answer and explanation."""
        from StudyFlow.focusflow import FocusFlowOverlay
        question = "What is the capital of France?"  # For reference
        full_answer = "FocusFlow"
        explanation = "Because sometimes, all you need is the right nudge in the right moment — FocusFlow delivers clarity when it matters most."
        self.focusflow_overlay = FocusFlowOverlay(full_answer, explanation)
        self.focusflow_overlay.show()
    
    def open_deepflow(self):
        """Opens the DeepFlow GUI in a separate movable window."""
        # Import the DeepFlowWindow class from deepflow_gui.py
        from .deepflow_gui import DeepFlowWindow
        self.deepflow_window = DeepFlowWindow()
        self.deepflow_window.show()

# Prevent garbage collection
main_window = None

def show_main_window(splash):
    global main_window
    main_window = ModernMenu()
    main_window.show()
    splash.finish(main_window)

def main():
    app = QApplication(sys.argv)
    splash_pix = QPixmap(r"C:\StudyFlowSuite\StudyFlow\Media\StudyFlow.png")
    splash_pix = splash_pix.scaled(splash_pix.width() * 0.1,
                                   splash_pix.height() * 0.1,
                                   Qt.KeepAspectRatio,
                                   Qt.SmoothTransformation)
    splash = QSplashScreen(splash_pix)
    splash.show()
    QTimer.singleShot(2000, lambda: show_main_window(splash))
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
