import sys
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QPushButton, QVBoxLayout, QLabel,
    QScrollArea, QStatusBar, QHBoxLayout, QGraphicsDropShadowEffect
)
from PySide6.QtGui import QFont, QIcon, QPixmap, QColor
from PySide6.QtCore import Qt, QPoint, QRect

# Attempt to import your StudyFlow functions; otherwise, define dummy versions.
try:
    from StudyFlow.core_engine import start_quiz
    from StudyFlow.button_capture import capture_button_template
    from StudyFlow.logging_utils import debug_log
except ImportError:
    def start_quiz(widget):
        print("DEBUG: Start Quiz function called")
    def capture_button_template(widget):
        print("DEBUG: Capture Button Template function called")
    def debug_log(msg):
        print("DEBUG:", msg)

# Expose the status label so core_engine.py can update it.
status_label = None

class MainWindow(QMainWindow):
    _resize_margin = 10  # pixels from the edge where resizing is enabled

    def __init__(self):
        super().__init__()
        debug_log("Launching GUI...")

        # Remove standard window frame and enable per-pixel transparency.
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

        # Create a container widget to hold all UI elements.
        self.container = QWidget(self)
        self.container.setObjectName("container")

        # Use a *different* pastel gradient (not the same as your other GUI).
        self.container.setStyleSheet("""
            #container {
                background: qlineargradient(
                    spread:pad, x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(248, 248, 248, 255),
                    stop:1 rgba(230, 234, 237, 255)
                );
                border-radius: 10px;
            }
        """)

        # Apply a drop shadow effect to the container.
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setXOffset(0)
        shadow.setYOffset(0)
        shadow.setColor(QColor(0, 0, 0, 180))
        self.container.setGraphicsEffect(shadow)

        # Use the container as the central widget.
        self.setCentralWidget(self.container)

        # Create the main layout for the container.
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # -----------------------------
        # Custom Title Bar (no blue background)
        # -----------------------------
        title_bar = QWidget(self.container)
        title_bar.setObjectName("titleBar")

        # Make the title bar transparent so the container's gradient shows through
        title_bar.setStyleSheet("""
            #titleBar {
                background-color: transparent;
                border-top-left-radius: 10px;
                border-top-right-radius: 10px;
            }
        """)

        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(10, 5, 10, 5)
        title_bar_layout.setSpacing(10)

        title_label = QLabel("StudyFlow - FreeFlow", title_bar)
        title_label.setStyleSheet("color: #333333; font-size: 16px; font-weight: bold;")
        title_bar_layout.addWidget(title_label)
        title_bar_layout.addStretch()

        # Close button (hover effect, no separate bar color)
        close_button = QPushButton("X", title_bar)
        close_button.setStyleSheet("""
            QPushButton {
                color: #333333;
                background: transparent;
                border: none;
                font-size: 14px;
                font-weight: bold;
                padding: 3px 6px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: rgba(0, 0, 0, 0.1);
            }
        """)
        close_button.setFont(QFont("Helvetica", 12, QFont.Bold))
        close_button.clicked.connect(self.close)
        title_bar_layout.addWidget(close_button)

        container_layout.addWidget(title_bar)

        # -----------------------------
        # Content Area
        # -----------------------------
        content = QWidget(self.container)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(15)

        # 1) Logo and Title Header
        header_layout = QVBoxLayout()
        # Logo
        logo_label = QLabel(content)
        logo_path = r"C:\StudyFlowSuite\StudyFlow\Media\FreeFlow.png"  # Update to your logo path.
        pixmap = QPixmap(logo_path)
        if pixmap.isNull():
            debug_log(f"Failed to load image at {logo_path}")
            logo_label.setText("Logo Not Found")
            logo_label.setAlignment(Qt.AlignCenter)
        else:
            scaled_pixmap = pixmap.scaled(120, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            logo_label.setPixmap(scaled_pixmap)
            logo_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(logo_label, alignment=Qt.AlignCenter)

        # Title text
        subtitle_label = QLabel("Welcome to FreeFlow", content)
        subtitle_label.setFont(QFont("Helvetica", 18, QFont.Bold))
        subtitle_label.setAlignment(Qt.AlignCenter)
        header_layout.addWidget(subtitle_label, alignment=Qt.AlignCenter)

        content_layout.addLayout(header_layout)

        # 2) Instruction Label
        instructions_label = QLabel(
            "Click 'Start Session' to begin.\n"
            "Use 'Capture Submit Button' if you need to define the Submit button region.",
            content)
        instructions_label.setFont(QFont("Helvetica", 12))
        instructions_label.setWordWrap(True)
        instructions_label.setAlignment(Qt.AlignCenter)
        content_layout.addWidget(instructions_label)

        # 3) Buttons Layout (No "Actions" group box)
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # Start Quiz Button
        start_button = QPushButton("Start Session", content)
        start_button.setFont(QFont("Helvetica", 16))
        start_button.setStyleSheet("""
            QPushButton {
                background-color: #ff5f5f;
                color: white;
                font-size: 16px;
                font-weight: bold;
                border-radius: 8px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #ff2f2f;
            }
        """)
        start_button.clicked.connect(lambda: start_quiz(self))
        button_layout.addWidget(start_button)

        # Capture Button
        capture_button = QPushButton("Capture Submit Button", content)
        capture_button.setFont(QFont("Helvetica", 14))
        capture_button.setStyleSheet("""
            QPushButton {
                background-color: #ff5f5f;
                color: white;
                font-size: 14px;
                font-weight: bold;
                border-radius: 8px;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #ff2f2f;
            }
        """)
        capture_button.clicked.connect(lambda: capture_button_template(self))
        button_layout.addWidget(capture_button)

        content_layout.addLayout(button_layout)

        # 4) Scrollable Status Label
        scroll_area = QScrollArea(content)
        scroll_area.setWidgetResizable(True)
        self.status_label = QLabel("", content)
        self.status_label.setFont(QFont("Helvetica", 12))
        self.status_label.setWordWrap(True)
        scroll_area.setWidget(self.status_label)
        content_layout.addWidget(scroll_area)

        container_layout.addWidget(content)

        # Make the status label globally available.
        global status_label
        status_label = self.status_label

        # Set an initial minimum size.
        self.setMinimumSize(500, 400)

        # Variables for window dragging and resizing.
        self._drag_pos = QPoint()
        self._resizing = False
        self._resize_direction = None
        self._orig_geometry = None

    def centerWindow(self):
        """Centers the window on the screen."""
        screen_geometry = QApplication.primaryScreen().availableGeometry()
        x = (screen_geometry.width() - self.width()) // 2
        y = (screen_geometry.height() - self.height()) // 2
        self.move(x, y)

    def getResizeDirection(self, pos):
        """Determine if the cursor is within the resize margin at any edge."""
        margin = self._resize_margin
        rect = self.rect()
        directions = []
        if pos.x() < margin:
            directions.append("left")
        elif pos.x() > rect.width() - margin:
            directions.append("right")
        if pos.y() < margin:
            directions.append("top")
        elif pos.y() > rect.height() - margin:
            directions.append("bottom")
        if directions:
            return "_".join(directions)
        return None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.pos()
            self._resize_direction = self.getResizeDirection(pos)
            if self._resize_direction:
                self._resizing = True
                self._drag_pos = event.globalPosition().toPoint()
                self._orig_geometry = QRect(self.geometry())  # make a copy
            else:
                # Start dragging for moving the window.
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        pos = event.pos()
        if self._resizing:
            delta = event.globalPosition().toPoint() - self._drag_pos
            orig = self._orig_geometry
            new_left = orig.left()
            new_top = orig.top()
            new_right = orig.right()
            new_bottom = orig.bottom()

            if "left" in self._resize_direction:
                new_left = orig.left() + delta.x()
            if "right" in self._resize_direction:
                new_right = orig.right() + delta.x()
            if "top" in self._resize_direction:
                new_top = orig.top() + delta.y()
            if "bottom" in self._resize_direction:
                new_bottom = orig.bottom() + delta.y()

            # Create new rectangle and enforce minimum sizes.
            new_width = new_right - new_left
            new_height = new_bottom - new_top
            if new_width < self.minimumWidth():
                new_width = self.minimumWidth()
                if "left" in self._resize_direction:
                    new_left = orig.right() - new_width
                else:
                    new_right = orig.left() + new_width
            if new_height < self.minimumHeight():
                new_height = self.minimumHeight()
                if "top" in self._resize_direction:
                    new_top = orig.bottom() - new_height
                else:
                    new_bottom = orig.top() + new_height

            new_geom = QRect(new_left, new_top, new_width, new_height)
            self.setGeometry(new_geom)
            event.accept()
        else:
            # Update cursor shape based on position.
            direction = self.getResizeDirection(pos)
            if direction:
                if direction in ("top", "bottom"):
                    self.setCursor(Qt.SizeVerCursor)
                elif direction in ("left", "right"):
                    self.setCursor(Qt.SizeHorCursor)
                elif direction in ("top_left", "bottom_right"):
                    self.setCursor(Qt.SizeFDiagCursor)
                elif direction in ("top_right", "bottom_left"):
                    self.setCursor(Qt.SizeBDiagCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            # If no resizing, handle dragging.
            if event.buttons() == Qt.LeftButton and not self._resizing:
                self.move(event.globalPosition().toPoint() - self._drag_pos)
                event.accept()

    def mouseReleaseEvent(self, event):
        self._resizing = False
        self._resize_direction = None
        self.setCursor(Qt.ArrowCursor)
        event.accept()

def launch_gui():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    launch_gui()