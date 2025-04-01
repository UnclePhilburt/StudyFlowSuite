import pyautogui
import cv2
import numpy as np
import os
import time
import difflib  # new import for fuzzy matching
from StudyFlow.logging_utils import debug_log
from StudyFlow.image_processing import preprocess_image
import pytesseract
from StudyFlow.ocr_extraction import get_tagged_words_from_region  # ensure OCR function is available

def human_move_click(x, y, duration=0.5):
    debug_log(f"Moving mouse to ({x}, {y}) over {duration}s and clicking.")
    pyautogui.moveTo(x, y, duration=duration)
    pyautogui.click()

def get_center(bbox):
    left, top, right, bottom = bbox
    return int((left + right) / 2), int((top + bottom) / 2)

def click_button_by_template(region, template_path):
    try:
        btn_location = pyautogui.locateCenterOnScreen(template_path, region=region, confidence=0.7)
        if btn_location:
            debug_log(f"Button found by template at: {btn_location}")
            human_move_click(btn_location.x, btn_location.y)
            return True
        else:
            debug_log("Button template not found on screen.")
            return False
    except pyautogui.ImageNotFoundException:
        debug_log("Button image not found (exception caught).")
        return False

def advanced_click_submit(region, template_path="submit_button.png", scales=np.linspace(0.8, 1.2, 10), threshold=0.7):
    if not os.path.exists(template_path):
        debug_log("Submit button template image not found.")
        return False
    screenshot = pyautogui.screenshot(region=region)
    screen_img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)
    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    if template is None:
        debug_log("Failed to load template image.")
        return False
    best_val = 0
    best_loc = None
    best_temp_shape = None
    for scale in scales:
        resized_template = cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        result = cv2.matchTemplate(screen_img, resized_template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val > best_val:
            best_val = max_val
            best_loc = max_loc
            best_temp_shape = resized_template.shape
    if best_val >= threshold and best_loc and best_temp_shape:
        tH, tW = best_temp_shape
        center_x = best_loc[0] + tW // 2
        center_y = best_loc[1] + tH // 2
        abs_x = region[0] + center_x
        abs_y = region[1] + center_y
        debug_log(f"Advanced matching found submit button at: ({abs_x}, {abs_y}) with confidence: {best_val:.2f}")
        human_move_click(abs_x, abs_y)
        return True
    else:
        debug_log("Advanced template matching did not find a suitable match.")
        return False

def locate_submit_button(region, template_path="submit_button.png", scales=np.linspace(0.8, 1.2, 10), threshold=0.7):
    if not os.path.exists(template_path):
        debug_log("Submit button template image not found.")
        return None
    screenshot = pyautogui.screenshot(region=region)
    screen_img = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2GRAY)
    template = cv2.imread(template_path, cv2.IMREAD_GRAYSCALE)
    if template is None:
        debug_log("Failed to load template image.")
        return None
    best_val = 0
    best_loc = None
    best_temp_shape = None
    for scale in scales:
        resized_template = cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        result = cv2.matchTemplate(screen_img, resized_template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val > best_val:
            best_val = max_val
            best_loc = max_loc
            best_temp_shape = resized_template.shape
    if best_val >= threshold and best_loc and best_temp_shape:
        tH, tW = best_temp_shape
        center_x = best_loc[0] + tW // 2
        center_y = best_loc[1] + tH // 2
        abs_x = region[0] + center_x
        abs_y = region[1] + center_y
        debug_log(f"Located submit button at ({abs_x}, {abs_y}), size ({tW}x{tH}).")
        return abs_x, abs_y, tW, tH
    return None

def click_button(region):
    template_path = "submit_button.png"
    if os.path.exists(template_path):
        if click_button_by_template(region, template_path):
            return True
        else:
            debug_log("Simple matching did not find the button. Trying advanced matching...")
            if advanced_click_submit(region, template_path):
                return True
            else:
                debug_log("Advanced matching failed to locate the submit button.")
                return False
    else:
        debug_log("Submit button template image not found.")
        return False

def scroll_all_the_way_up(region, scroll_pixels=100, max_attempts=10):
    debug_log("Scrolling all the way up to reset the region...")
    for _ in range(max_attempts):
        pyautogui.scroll(scroll_pixels)
        time.sleep(0.5)
    debug_log("Finished scrolling up.")

# New functions to detect additional text by scrolling down.
def check_for_more_text(region, scroll_pixels=100, similarity_threshold=0.95):
    """
    Check if scrolling down reveals additional text.
    Captures OCR text, scrolls down a bit, and compares the new OCR text to the original.
    Returns True if the texts differ significantly (i.e., new text is detected).
    """
    original_text, _ = get_tagged_words_from_region(region)
    pyautogui.scroll(-scroll_pixels)  # negative to scroll down
    time.sleep(0.5)
    new_text, _ = get_tagged_words_from_region(region)
    similarity = difflib.SequenceMatcher(None, original_text.strip(), new_text.strip()).ratio()
    debug_log(f"Scroll check similarity ratio: {similarity:.2f}")
    return similarity < similarity_threshold

def scroll_down_until_no_more_text(region, scroll_pixels=100, max_attempts=10, similarity_threshold=0.95):
    """
    Scrolls down repeatedly until no additional text is detected (or max_attempts reached).
    """
    attempts = 0
    while attempts < max_attempts:
        if check_for_more_text(region, scroll_pixels, similarity_threshold):
            debug_log("Additional text detected; scrolling down further.")
            # Already scrolled in check_for_more_text, so just wait and increment
            time.sleep(0.5)
            attempts += 1
        else:
            debug_log("No additional text detected.")
            break

def submit_button_visible(region):
    screenshot = pyautogui.screenshot(region=region)
    processed = preprocess_image(screenshot)
    ocr_data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT,
                                          config="--psm 6 --oem 3")
    debug_log(f"OCR Data extracted keys: {list(ocr_data.get('text', []))} with {len(ocr_data.get('text', []))} entries.")
    for i in range(len(ocr_data['text'])):
        word = ocr_data['text'][i].strip().lower()
        if word and (("submit" in word) or ("next" in word)):
            return True
    return False
