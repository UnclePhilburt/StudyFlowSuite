# deepflow_gui.py

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QPushButton, QVBoxLayout, QLabel, QHBoxLayout, QGraphicsDropShadowEffect, QLineEdit
)
from PySide6.QtGui import QPainter, QColor, QLinearGradient, QBrush, QPixmap
from PySide6.QtCore import Qt, QPropertyAnimation, QEasingCurve
# Import the DeepFlow logic; adjust the import as needed for your package structure.
from .deepflow import get_deepflow_question

class GradientWidget(QWidget):
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = self.rect()
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gradient.setColorAt(0, QColor(220, 239, 255))
        gradient.setColorAt(1, QColor(174, 201, 245))
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(rect, 16, 16)
        super().paintEvent(event)

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
        from PySide6.QtWidgets import QGraphicsDropShadowEffect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(255, 47, 47, 150))
        shadow.setOffset(0, 0)
        self.setGraphicsEffect(shadow)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.setGraphicsEffect(None)
        super().leaveEvent(event)

class DeepFlowWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DeepFlow")
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(600, 500)
        self._drag_pos = None  # For moving the window

        # State variables for quiz logic
        self.topic = ""
        self.previous_questions = []
        self.current_question_data = None

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

        # Create gradient background widget and set it as central widget
        self.gradient_widget = GradientWidget()
        self.setCentralWidget(self.gradient_widget)

        # Main vertical layout
        self.main_layout = QVBoxLayout(self.gradient_widget)
        self.main_layout.setContentsMargins(16, 16, 16, 16)
        self.main_layout.setSpacing(10)

        # --- Topic Input Area ---
        topic_layout = QHBoxLayout()
        self.topic_input = QLineEdit()
        self.topic_input.setPlaceholderText("Enter topic here...")
        topic_layout.addWidget(self.topic_input)
        self.start_button = GlowButton("Start", self)
        self.start_button.clicked.connect(self.start_deepflow)
        topic_layout.addWidget(self.start_button)
        self.main_layout.addLayout(topic_layout)

        # --- Top Bar with Title and Close Button ---
        top_bar = QWidget(self.gradient_widget)
        top_layout = QHBoxLayout(top_bar)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(10)
        title_label = QLabel("DeepFlow", top_bar)
        title_label.setStyleSheet("color: #333333; font-size: 18px; font-weight: bold;")
        top_layout.addWidget(title_label)
        top_layout.addStretch()
        close_button = QPushButton("×", top_bar)
        close_button.setFixedSize(25, 25)
        close_button.setStyleSheet("""
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
        close_button.clicked.connect(self.close)
        top_layout.addWidget(close_button)
        self.main_layout.addWidget(top_bar)

        # --- Content Area for Quiz ---
        self.content_widget = QWidget(self.gradient_widget)
        self.content_layout = QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(20, 20, 20, 20)
        self.content_layout.setSpacing(20)
        self.main_layout.addWidget(self.content_widget)

        # Label for displaying the question
        self.question_label = QLabel("Your question will appear here", self.content_widget)
        self.question_label.setWordWrap(True)
        self.question_label.setStyleSheet("font-size: 16px; color: #333333;")
        self.content_layout.addWidget(self.question_label)

        # Container for answer option buttons
        self.options_widget = QWidget(self.content_widget)
        self.options_layout = QVBoxLayout(self.options_widget)
        self.options_layout.setSpacing(10)
        self.content_layout.addWidget(self.options_widget)

        # Label for explanation (hidden initially)
        self.explanation_label = QLabel("", self.content_widget)
        self.explanation_label.setWordWrap(True)
        self.explanation_label.setStyleSheet("font-size: 14px; color: #555555;")
        self.explanation_label.setVisible(False)
        self.content_layout.addWidget(self.explanation_label)

        # Control buttons (Help and Next)
        control_widget = QWidget(self.content_widget)
        control_layout = QHBoxLayout(control_widget)
        control_layout.setSpacing(10)
        self.help_button = GlowButton("Help", self.content_widget)
        self.help_button.clicked.connect(self.show_explanation)
        control_layout.addWidget(self.help_button)
        self.next_button = GlowButton("Next", self.content_widget)
        self.next_button.clicked.connect(self.load_next_question)
        control_layout.addWidget(self.next_button)
        self.content_layout.addWidget(control_widget)

        # Do not automatically load a question; wait until the user enters a topic and clicks Start

    def start_deepflow(self):
        """Triggered when the user clicks the Start button."""
        entered_topic = self.topic_input.text().strip()
        if entered_topic:
            self.topic = entered_topic
            self.previous_questions = []  # Reset previous questions for the new topic
            self.load_next_question()
        else:
            self.question_label.setText("Please enter a topic before starting DeepFlow.")

    def load_next_question(self):
        """Loads a new quiz question using your deepflow logic."""
        self.explanation_label.setVisible(False)
        # Call your deepflow logic to get a new question
        question_data = get_deepflow_question(self.topic, self.previous_questions)
        if question_data:
            self.current_question_data = question_data
            self.previous_questions.append(question_data.get("question", ""))
            self.question_label.setText(question_data.get("question", "No question generated."))
            # Clear existing answer option buttons
            for i in reversed(range(self.options_layout.count())):
                widget = self.options_layout.itemAt(i).widget()
                if widget:
                    widget.deleteLater()
            # Create new answer option buttons
            for idx, option_text in enumerate(question_data.get("options", [])):
                btn = GlowButton(option_text, self.options_widget)
                btn.clicked.connect(lambda checked, index=idx: self.check_answer(index))
                self.options_layout.addWidget(btn)
        else:
            self.question_label.setText("Failed to load question.")

    def check_answer(self, selected_index):
        """Checks the answer and displays feedback."""
        correct_index = self.current_question_data.get("correct_index", -1)
        explanation = self.current_question_data.get("explanation", "")
        if selected_index == correct_index:
            self.question_label.setText("Correct! " + self.current_question_data.get("question", ""))
        else:
            self.question_label.setText("Incorrect! " + self.current_question_data.get("question", ""))
        self.explanation_label.setText(explanation)
        self.explanation_label.setVisible(True)

    def show_explanation(self):
        """Shows the explanation for the current question."""
        explanation = self.current_question_data.get("explanation", "")
        self.explanation_label.setText(explanation)
        self.explanation_label.setVisible(True)

    # Overridden mouse events to allow the window to be moved by dragging anywhere
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
