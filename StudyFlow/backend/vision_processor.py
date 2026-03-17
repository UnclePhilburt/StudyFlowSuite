# vision_processor.py
"""
Vision-based quiz processing using GPT-4o.
Analyzes full screen to identify questions, answers, and buttons automatically.
Uses the Render server endpoint so API key stays on server.

Now supports HYBRID MODE which uses:
1. Local OCR + cheap text API (90% of cases)
2. Vision API only as fallback (expensive)
"""

import base64
import json
import io
import os
import pyautogui
import pytesseract
import requests
from StudyFlow.logging_utils import debug_log
from StudyFlow.backend.image_processing import preprocess_image

# Server URL for vision API
VISION_API_URL = os.getenv("VISION_API_URL", "https://studyflowsuite.onrender.com/api/vision")

# Processing mode: 'hybrid' (smart/cheap) or 'vision' (always use Vision API)
PROCESSING_MODE = os.getenv("PROCESSING_MODE", "vision")


def encode_image_to_base64(image):
    """Convert PIL Image to base64 string."""
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')


def analyze_quiz_screen(screenshot):
    """
    Analyze a screenshot using GPT-4o Vision via the server endpoint.
    API key is stored on the server, not locally.

    Args:
        screenshot: PIL Image of the screen

    Returns:
        dict with question, answers, correct answer, and button info
    """
    debug_log("🔍 Analyzing screen with Vision API...")
    debug_log(f"📡 Using server: {VISION_API_URL}")

    image_base64 = encode_image_to_base64(screenshot)

    try:
        response = requests.post(
            VISION_API_URL,
            json={"image": image_base64},
            timeout=60  # Vision API can take a while
        )

        if response.status_code != 200:
            error_msg = response.json().get("error", "Unknown server error")
            debug_log(f"❌ Server error: {error_msg}")
            return {"error": error_msg}

        result = response.json()
        debug_log(f"✅ Parsed: Q='{result.get('question', '')[:50]}...' Answer={result.get('correct_answer_index')}")
        return result

    except requests.exceptions.Timeout:
        debug_log("❌ Vision API timeout")
        return {"error": "Server timeout - try again"}
    except requests.exceptions.ConnectionError:
        debug_log("❌ Cannot connect to vision server")
        return {"error": "Cannot connect to server - check internet connection"}
    except Exception as e:
        debug_log(f"❌ Vision API error: {e}")
        return {"error": str(e)}


def find_text_on_screen(target_text, screenshot=None):
    """
    Find the screen coordinates of specific text using OCR.

    Args:
        target_text: Text to find on screen
        screenshot: Optional PIL Image, captures new one if not provided

    Returns:
        tuple (x, y) of center coordinates, or None if not found
    """
    if screenshot is None:
        screenshot = pyautogui.screenshot()

    processed = preprocess_image(screenshot)
    ocr_data = pytesseract.image_to_data(
        processed,
        output_type=pytesseract.Output.DICT,
        config="--psm 6 --oem 3"
    )

    target_lower = target_text.lower().strip()
    target_words = target_lower.split()

    # First try: exact match of first few words
    for i in range(len(ocr_data['text'])):
        word = ocr_data['text'][i].strip().lower()
        if word and target_words and word == target_words[0]:
            # Check if subsequent words match
            match_len = 1
            combined_text = word
            for j in range(1, min(len(target_words), 5)):
                if i + j < len(ocr_data['text']):
                    next_word = ocr_data['text'][i + j].strip().lower()
                    if next_word == target_words[j]:
                        match_len += 1
                        combined_text += " " + next_word

            if match_len >= min(2, len(target_words)):
                # Found a match - calculate click coordinates
                x = ocr_data['left'][i] + ocr_data['width'][i] // 2
                y = ocr_data['top'][i] + ocr_data['height'][i] // 2
                debug_log(f"📍 Found '{combined_text}' at ({x}, {y})")
                return (x, y)

    # Second try: partial match on any significant word
    for i in range(len(ocr_data['text'])):
        word = ocr_data['text'][i].strip().lower()
        if len(word) >= 4:  # Skip short words
            for target_word in target_words:
                if len(target_word) >= 4 and target_word in word:
                    x = ocr_data['left'][i] + ocr_data['width'][i] // 2
                    y = ocr_data['top'][i] + ocr_data['height'][i] // 2
                    debug_log(f"📍 Partial match '{word}' for '{target_word}' at ({x}, {y})")
                    return (x, y)

    debug_log(f"⚠️ Could not find '{target_text[:30]}...' on screen")
    return None


def find_button_on_screen(button_text, screenshot=None):
    """
    Find submit/next button coordinates.
    Tries the exact text first, then common button texts.
    """
    if screenshot is None:
        screenshot = pyautogui.screenshot()

    # Try the exact button text first
    coords = find_text_on_screen(button_text, screenshot)
    if coords:
        return coords

    # Try common button texts
    common_buttons = ["Submit", "Next", "Continue", "Check", "Done", "Finish"]
    for btn_text in common_buttons:
        if btn_text.lower() != button_text.lower():
            coords = find_text_on_screen(btn_text, screenshot)
            if coords:
                return coords

    return None


def process_quiz_with_vision():
    """
    Main function: Capture screen, analyze with vision, return actionable data.

    Now supports HYBRID MODE (default):
    - Uses local OCR + cheap text API for most cases
    - Falls back to expensive Vision API only when needed

    Returns:
        dict with:
        - success: bool
        - answer_coords: (x, y) tuple for clicking the answer
        - button_coords: (x, y) tuple for clicking submit
        - question: str
        - correct_answer: str
        - reasoning: str
        - method: 'cache' | 'text_api' | 'vision_api'
        - error: str (if failed)
    """
    # Use hybrid mode by default (cheaper)
    if PROCESSING_MODE == "hybrid":
        debug_log("🔄 Using HYBRID mode (smart/cheap)...")
        try:
            from StudyFlow.backend.hybrid_processor import process_quiz_hybrid
            return process_quiz_hybrid()
        except ImportError as e:
            debug_log(f"⚠️ Hybrid processor not available: {e}")
            debug_log("⚠️ Falling back to Vision-only mode")

    # Vision-only mode (original behavior)
    debug_log("📸 Using VISION mode (expensive)...")
    screenshot = pyautogui.screenshot()

    # Analyze with GPT-4o Vision
    vision_result = analyze_quiz_screen(screenshot)

    if "error" in vision_result:
        return {
            "success": False,
            "error": vision_result.get("error"),
            "raw": vision_result.get("raw")
        }

    if vision_result.get("question") is None:
        return {
            "success": False,
            "error": "No quiz interface detected on screen"
        }

    correct_text = vision_result.get("correct_answer_text", "")
    correct_index = vision_result.get("correct_answer_index", 1)

    # FIRST: Try to use coordinates from Vision API (most reliable!)
    answer_coords = None
    if "answer_click_x" in vision_result and "answer_click_y" in vision_result:
        answer_coords = (vision_result["answer_click_x"], vision_result["answer_click_y"])
        debug_log(f"✅ Using Vision API coordinates for answer: {answer_coords}")
    else:
        # Fallback: Try OCR-based finding (less reliable)
        debug_log(f"🔎 Vision API didn't provide coordinates, falling back to OCR...")
        debug_log(f"🔎 Looking for answer text: '{correct_text[:40]}...'")
        answer_coords = find_text_on_screen(correct_text, screenshot)

        # If full text not found, try finding by answer option letter/number
        if not answer_coords:
            # Try common answer formats: A., B., C., D. or 1., 2., 3., 4.
            option_letters = ['A', 'B', 'C', 'D', 'E', 'F']
            if correct_index <= len(option_letters):
                option_letter = option_letters[correct_index - 1]
                debug_log(f"🔎 Trying to find answer by option letter: '{option_letter}.'")
                answer_coords = find_text_on_screen(f"{option_letter}.", screenshot)

                if not answer_coords:
                    debug_log(f"🔎 Trying to find answer by number: '{correct_index}.'")
                    answer_coords = find_text_on_screen(f"{correct_index}.", screenshot)

    # FIRST: Try to use button coordinates from Vision API (most reliable!)
    button_coords = None
    if "button_click_x" in vision_result and "button_click_y" in vision_result:
        button_coords = (vision_result["button_click_x"], vision_result["button_click_y"])
        debug_log(f"✅ Using Vision API coordinates for button: {button_coords}")
    else:
        # Fallback: Use template matching for button
        debug_log("🔎 Vision API didn't provide button coordinates, using template matching...")
        try:
            import os
            import cv2
            import numpy as np

            template_path = "submit_button.png"
            if os.path.exists(template_path):
                # Load the captured button template
                template = cv2.imread(template_path)
                screenshot_np = np.array(screenshot)
                screenshot_cv = cv2.cvtColor(screenshot_np, cv2.COLOR_RGB2BGR)

                # Find the button on screen using template matching
                result = cv2.matchTemplate(screenshot_cv, template, cv2.TM_CCOEFF_NORMED)
                min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

                if max_val > 0.6:  # 60% confidence threshold
                    h, w = template.shape[:2]
                    button_x = max_loc[0] + w // 2
                    button_y = max_loc[1] + h // 2
                    button_coords = (button_x, button_y)
                    debug_log(f"✅ Found button via template matching at {button_coords} (confidence: {max_val:.2f})")
                else:
                    debug_log(f"⚠️ Template match confidence too low: {max_val:.2f}")
            else:
                debug_log("⚠️ No button template found - Vision API should provide coordinates")
        except Exception as e:
            debug_log(f"❌ Button template matching failed: {e}")

    return {
        "success": True,
        "question": vision_result.get("question"),
        "answers": vision_result.get("answers", []),
        "correct_index": vision_result.get("correct_answer_index"),
        "correct_answer": correct_text,
        "answer_coords": answer_coords,
        "button_text": "Submit",
        "button_coords": button_coords,
        "confidence": vision_result.get("confidence", "unknown"),
        "reasoning": vision_result.get("reasoning", ""),
        "method": "vision_api"
    }
