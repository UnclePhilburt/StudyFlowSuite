import requests
import pyautogui
from io import BytesIO
import os

def capture_and_send_screenshot(region):
    """
    Captures a screenshot from the specified region (x, y, width, height),
    sends it to the OCR service, and then uses the returned OCR mapping
    to calculate the absolute screen coordinates for a given answer tag.
    """
    # region is a tuple: (x, y, width, height)
    x_offset, y_offset, width, height = region

    # 1. Capture the screenshot of the given region locally
    screenshot = pyautogui.screenshot(region=region)
    
    # 2. Convert the screenshot to bytes
    buf = BytesIO()
    screenshot.save(buf, format='PNG')
    image_bytes = buf.getvalue()

    # 3. Send the image bytes to your cloud OCR service
    url = os.environ.get("BACKEND_URL", "https://studyflowsuite.onrender.com") + "/ocr"  # Replace with your actual endpoint URL
    files = {"image": ("screenshot.png", image_bytes, "image/png")}

    response = requests.post(url, files=files)
    if response.status_code == 200:
        # 4. Assume the server returns a JSON object with OCR results, for example:
        # {
        #   "text": "...",
        #   "mapping": {
        #       "3": {"left": 50, "top": 100, "width": 80, "height": 20, ...},
        #       ... 
        #   },
        #   "answers": {
        #       "1": {"text": "Answer 1", "tag": 3},
        #       "2": {"text": "Answer 2", "tag": 5},
        #       ...
        #   }
        # }
        data = response.json()
        print("Server returned:", data)

        # 5. Use the returned OCR mapping to calculate absolute coordinates.
        # For example, let's say we want to click the answer for option "1".
        answers = data.get("answers", {})
        mapping = data.get("mapping", {})

        answer_data = answers.get("1", {})  # Selecting answer "1" as an example
        relative_tag = answer_data.get("tag")
        if relative_tag and str(relative_tag) in mapping:
            word_info = mapping[str(relative_tag)]
            # Calculate absolute coordinates by adding the region's top-left offset
            abs_x = x_offset + word_info["left"] + word_info["width"] // 2
            abs_y = y_offset + word_info["top"] + word_info["height"] // 2
            print("Clicking at absolute position:", abs_x, abs_y)
            pyautogui.click(abs_x, abs_y)
        else:
            print("Could not find the relative tag in the mapping.")
    else:
        print("Error from server:", response.text)

# Example usage:
# Define the region you want to capture (for example, a window or a portion of the screen)
# region = (x_offset, y_offset, width, height)
region = (100, 200, 800, 600)
capture_and_send_screenshot(region)
