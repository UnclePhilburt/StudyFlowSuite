# hybrid_processor.py
"""
Hybrid quiz processor that intelligently uses local and server resources.

Flow:
1. Optimize screenshot (downscale)
2. Check if screen changed (skip if same)
3. Run local OCR
4. Check cache (instant answer if seen before)
5. Try to parse quiz structure locally
6. If parseable -> Use cheap text API
7. If not -> Fall back to expensive Vision API
8. Cache result for future
9. Find click coordinates locally
"""

import base64
import io
import os
import requests
import pyautogui

from StudyFlow.logging_utils import debug_log
from StudyFlow.backend.smart_image import (
    optimize_screenshot,
    get_image_hash,
    images_are_similar,
    extract_text_with_positions,
    detect_quiz_on_screen,
    extract_quiz_structure,
    find_text_coordinates,
    find_button_coordinates,
    get_cached_answer,
    cache_answer,
    hash_question,
)

# Server endpoints
BASE_URL = os.getenv("VISION_API_URL", "https://studyflowsuite.onrender.com").replace("/api/vision", "")
TEXT_API_URL = f"{BASE_URL}/api/answer"
VISION_API_URL = f"{BASE_URL}/api/vision"

# Track previous screenshot hash for change detection
_previous_hash = None
_last_success = False  # Only skip if last attempt was successful


def encode_image_to_base64(image):
    """Convert PIL Image to base64 string."""
    buffered = io.BytesIO()
    image.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode('utf-8')


def call_text_api(question, answers):
    """
    Call the cheap text-only API endpoint.
    Returns result dict or None on failure.
    """
    try:
        debug_log(f"TEXT API: Sending question ({len(question)} chars) + {len(answers)} answers")

        response = requests.post(
            TEXT_API_URL,
            json={
                "question": question,
                "answers": [a.get('text', a) if isinstance(a, dict) else a for a in answers]
            },
            timeout=30
        )

        if response.status_code == 200:
            result = response.json()
            debug_log(f"TEXT API: Success! Answer index = {result.get('correct_answer_index')}")
            return result
        else:
            debug_log(f"TEXT API: Failed with status {response.status_code}")
            return None

    except Exception as e:
        debug_log(f"TEXT API: Error - {e}")
        return None


def call_vision_api(image):
    """
    Call the expensive Vision API endpoint.
    Returns result dict or None on failure.
    """
    try:
        debug_log("VISION API: Falling back to Vision (expensive)...")
        image_base64 = encode_image_to_base64(image)

        response = requests.post(
            VISION_API_URL,
            json={"image": image_base64},
            timeout=60
        )

        if response.status_code == 200:
            result = response.json()
            debug_log(f"VISION API: Success! Answer = {result.get('correct_answer_index')}")
            return result
        else:
            debug_log(f"VISION API: Failed with status {response.status_code}")
            return None

    except Exception as e:
        debug_log(f"VISION API: Error - {e}")
        return None


def process_quiz_hybrid():
    """
    Main hybrid processing function.

    Returns dict with:
    - success: bool
    - answer_coords: (x, y) tuple for clicking the answer
    - button_coords: (x, y) tuple for clicking submit
    - question: str
    - correct_answer: str
    - reasoning: str
    - method: 'cache' | 'text_api' | 'vision_api'
    - error: str (if failed)
    """
    global _previous_hash, _last_success

    # 1. Capture and optimize screenshot
    debug_log("HYBRID: Capturing screen...")
    screenshot = pyautogui.screenshot()
    original_width, original_height = screenshot.size
    optimized = optimize_screenshot(screenshot)
    optimized_width, optimized_height = optimized.size

    # Calculate scale factor to convert coordinates back to original size
    scale_x = original_width / optimized_width
    scale_y = original_height / optimized_height
    debug_log(f"HYBRID: Scale factors: x={scale_x:.2f}, y={scale_y:.2f}")

    # 2. Check for screen change - only skip if last attempt was successful
    current_hash = get_image_hash(optimized)
    if _last_success and images_are_similar(current_hash, _previous_hash):
        debug_log("HYBRID: Screen unchanged (after success), skipping...")
        return {
            "success": False,
            "error": "Screen unchanged",
            "skip": True
        }
    _previous_hash = current_hash
    _last_success = False  # Reset until we succeed

    # 3. Run local OCR
    debug_log("HYBRID: Running local OCR...")
    try:
        full_text, words = extract_text_with_positions(optimized)
    except Exception as e:
        debug_log(f"HYBRID: OCR failed with error: {e}")
        return {
            "success": False,
            "error": f"OCR error: {e}"
        }

    if not full_text.strip():
        debug_log("HYBRID: No text detected on screen (empty OCR result)")
        return {
            "success": False,
            "error": "No text detected on screen"
        }

    debug_log(f"HYBRID: OCR successful - extracted {len(full_text)} characters")

    # 4. Detect if this is a quiz
    if not detect_quiz_on_screen(full_text, words):
        debug_log("HYBRID: No quiz interface detected")
        return {
            "success": False,
            "error": "No quiz interface detected"
        }

    # 5. Try to parse quiz structure locally
    local_structure = extract_quiz_structure(full_text, words)

    result = None
    method = None

    if local_structure:
        question = local_structure['question']
        answers = local_structure['answers']
        answer_texts = [a['text'] for a in answers]

        # 6. Check cache first
        q_hash = hash_question(question, answer_texts)
        cached = get_cached_answer(q_hash)

        if cached:
            result = cached
            method = 'cache'
            debug_log("HYBRID: Using cached answer!")
        else:
            # 7. Try cheap text API
            result = call_text_api(question, answer_texts)
            if result:
                method = 'text_api'
                # Cache the result
                cache_answer(q_hash, result)
                debug_log("HYBRID: Text API succeeded, result cached")

    # 8. Fall back to Vision API if text approach failed
    if not result:
        debug_log("HYBRID: Local parsing failed or text API failed, using Vision...")
        result = call_vision_api(optimized)
        method = 'vision_api'

        if result and result.get('question'):
            # Cache vision result too
            q_hash = hash_question(
                result.get('question', ''),
                [a.get('text', '') for a in result.get('answers', [])]
            )
            cache_answer(q_hash, result)

    if not result:
        return {
            "success": False,
            "error": "All processing methods failed"
        }

    if result.get('question') is None:
        return {
            "success": False,
            "error": "No quiz detected in result"
        }

    # 9. Find click coordinates - use ORIGINAL screenshot for better accuracy
    correct_text = result.get('correct_answer_text', '')
    correct_index = result.get('correct_answer_index', 1)

    debug_log(f"HYBRID: Finding click coords for: '{correct_text[:50]}'")

    # Re-run OCR on original screenshot for accurate coordinate finding
    debug_log("HYBRID: Re-running OCR on full-resolution screenshot for click coordinates...")
    full_res_text, full_res_words = extract_text_with_positions(screenshot)

    # Try to find answer coordinates on full resolution
    answer_coords = None
    if correct_text:
        answer_coords = find_text_coordinates(correct_text, full_res_words)
        if answer_coords:
            debug_log(f"HYBRID: Found answer at {answer_coords} (full resolution)")

    # If exact match fails, try partial matching with first few words
    if not answer_coords and correct_text:
        # Try matching just the first significant word
        words_in_answer = [w for w in correct_text.split() if len(w) > 3][:3]
        if words_in_answer:
            partial_search = ' '.join(words_in_answer)
            debug_log(f"HYBRID: Trying partial match with: '{partial_search}'")
            answer_coords = find_text_coordinates(partial_search, full_res_words)
            if answer_coords:
                debug_log(f"HYBRID: Found answer via partial match at {answer_coords}")

    # If we used local structure, try using the answer from there
    if not answer_coords and local_structure:
        try:
            idx = correct_index - 1  # Convert to 0-based
            if 0 <= idx < len(local_structure['answers']):
                ans_text = local_structure['answers'][idx]['text']
                answer_coords = find_text_coordinates(ans_text, full_res_words)
        except (IndexError, KeyError):
            pass

    # Find button coordinates on full resolution
    # Prioritize Vision API's button suggestion if available
    button_coords = None
    if result.get('button_text'):
        debug_log(f"HYBRID: Vision API suggests button: '{result['button_text']}'")
        button_coords = find_text_coordinates(result['button_text'], full_res_words)
        if button_coords:
            debug_log(f"HYBRID: Found Vision API's suggested button at {button_coords}")

    # Fall back to OCR-based button detection
    if not button_coords:
        debug_log("HYBRID: Vision API button not found, trying OCR detection...")
        btn_x, btn_y, btn_text = find_button_coordinates(full_res_words)
        button_coords = (btn_x, btn_y) if btn_x else None

    # No need to scale - coordinates are already in original resolution
    if answer_coords:
        debug_log(f"HYBRID: Answer coords (original resolution): {answer_coords}")
    if button_coords:
        debug_log(f"HYBRID: Button coords (original resolution): {button_coords}")

    # Mark as successful so we skip unchanged screens after this
    _last_success = True

    return {
        "success": True,
        "question": result.get('question', local_structure.get('question') if local_structure else ''),
        "answers": result.get('answers', []),
        "correct_index": correct_index,
        "correct_answer": correct_text,
        "answer_coords": answer_coords,
        "button_text": btn_text or result.get('button_text', 'Submit'),
        "button_coords": button_coords,
        "confidence": result.get('confidence', 'unknown'),
        "reasoning": result.get('reasoning', ''),
        "method": method
    }


def get_processing_stats():
    """
    Get statistics about processing methods used.
    Useful for monitoring cost efficiency.
    """
    from StudyFlow.backend.smart_image import _question_cache

    return {
        "cache_size": len(_question_cache),
        "cache_max": 100
    }
