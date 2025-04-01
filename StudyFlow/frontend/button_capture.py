from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QMessageBox
from PySide6.QtCore import Qt
import pyautogui
from StudyFlow.screen_interaction import get_center
from StudyFlow.logging_utils import debug_log

# Global variables (assuming these are used elsewhere)
submit_button_x = None
submit_button_top = None
submit_button_bottom = None

class CaptureCornersDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Capture Button Template")
        self.top_left = None
        self.bottom_right = None

        layout = QVBoxLayout(self)
        self.label = QLabel("Hover over the TOP-LEFT corner of the button, then press Enter.", self)
        layout.addWidget(self.label)
        self.setLayout(layout)
        # Ensure the dialog gets keyboard focus
        self.setFocusPolicy(Qt.StrongFocus)
        self.setModal(True)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.on_enter()
        else:
            super().keyPressEvent(event)

    def on_enter(self):
        global submit_button_x, submit_button_top, submit_button_bottom
        if self.top_left is None:
            self.top_left = pyautogui.position()
            self.label.setText("Now hover over the BOTTOM-RIGHT corner, then press Enter.")
        elif self.bottom_right is None:
            self.bottom_right = pyautogui.position()
            x1, y1 = self.top_left
            x2, y2 = self.bottom_right
            region = (min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1))
            button_image = pyautogui.screenshot(region=region)
            button_template_path = "submit_button.png"
            button_image.save(button_template_path)
            submit_button_x, _ = get_center(region)
            submit_button_top = min(y1, y2)
            submit_button_bottom = max(y1, y2)
            QMessageBox.information(self, "Success", f"Button template saved at {button_template_path}")
            debug_log(f"Captured button template from region: {region}")
            self.accept()  # Close the dialog

def capture_button_template(root):
    dialog = CaptureCornersDialog(root)
    dialog.exec()
