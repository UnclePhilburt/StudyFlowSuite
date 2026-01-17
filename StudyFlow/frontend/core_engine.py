import time
import json
from StudyFlow.frontend.ocr_extraction import (
    get_tagged_words_from_region,
    ai_structure_layout,
    convert_answers_list_to_dict,
    fallback_structure,
    merge_ai_and_fallback,
    validate_and_correct,
    wait_for_text_change,
)
from StudyFlow.backend.ai_manager import triple_call_ai_api_json_final
from StudyFlow.backend.vision_processor import process_quiz_with_vision
from StudyFlow.frontend.screen_interaction import (
    human_move_click, click_button_with_scroll, scroll_all_the_way_up
)
from StudyFlow.logging_utils import debug_log
from StudyFlow.constants import (
    MAX_API_RETRIES, DEFAULT_EXPECTED_ANSWERS, CLICK_DELAY_SEC,
    WINDOW_HIDE_DELAY_SEC, API_RETRY_DELAY_SEC, CLICK_CENTER_OFFSET,
    SCROLL_SETTLE_DELAY_SEC, QUESTION_WAIT_MIN_SEC, QUESTION_WAIT_MAX_SEC
)
import random

# Global state variables (you may later refactor these to a proper state manager)
emergency_stop = False
error_messages = []

def process_quiz(region):
    global emergency_stop
    debug_log("Checking if submit button is visible before starting...")

    # Reset scroll position at quiz start to ensure we're at the top
    scroll_all_the_way_up(region)
    time.sleep(SCROLL_SETTLE_DELAY_SEC)

    while True:
        if emergency_stop:
            debug_log("Emergency stop detected. Exiting quiz loop.")
            break

        tagged_text, mapping = get_tagged_words_from_region(region)
        debug_log(f"Chosen OCR text (first 100 chars): {tagged_text[:100]}...")
        debug_log(f"Full tagged question text: {tagged_text}")

        # Get structured OCR JSON using AI layout correction
        structured_ai = ai_structure_layout(tagged_text)
        if structured_ai and structured_ai.get("answers"):
            expected_answers = len(structured_ai["answers"])
            debug_log("AI layout correction determined " + str(expected_answers) + " answer options.")
            ai_json = convert_answers_list_to_dict(structured_ai)
        else:
            expected_answers = DEFAULT_EXPECTED_ANSWERS
            debug_log(f"AI layout correction failed; falling back to {DEFAULT_EXPECTED_ANSWERS} answer options.")
            ai_json = None

        fallback_json = fallback_structure(mapping, expected_answers)
        if ai_json and fallback_json.get("answers"):
            ocr_json = merge_ai_and_fallback(ai_json, fallback_json, mapping)
        elif ai_json:
            ocr_json = ai_json
        else:
            ocr_json = fallback_json

        debug_log("Structured OCR JSON: " + json.dumps(ocr_json, indent=2))
        ocr_json = validate_and_correct(ocr_json, region, expected_answers)
        
        # Triple API call with retries
        correct_index = None
        for attempt in range(MAX_API_RETRIES):
            correct_index = triple_call_ai_api_json_final(ocr_json)
            if correct_index is not None:
                break
            else:
                debug_log(f"API call attempt {attempt+1} returned discrepancy. Rechecking...")
                new_text = wait_for_text_change(region, tagged_text)
                tagged_text, mapping = get_tagged_words_from_region(region)
                fallback_json = fallback_structure(mapping, expected_answers)
                if ai_json and fallback_json.get("answers"):
                    ocr_json = merge_ai_and_fallback(ai_json, fallback_json, mapping)
                else:
                    ocr_json = fallback_json
                time.sleep(API_RETRY_DELAY_SEC)
        
        if correct_index is None:
            debug_log("API calls failed after retries. Defaulting to answer option 1.")
            correct_index = 1

        debug_log(f"Final AI returned answer index: {correct_index}")
        
        answer_options = ocr_json.get("answers", {})
        if str(correct_index) in answer_options:
            chosen_tag = answer_options[str(correct_index)]["tag"]
        else:
            error_messages.append(f"Answer index {correct_index} not found. Stopping.")
            debug_log("Answer index not found. Exiting quiz loop.")
            break

        if not chosen_tag or chosen_tag not in mapping:
            error_messages.append(f"Tag for answer index {correct_index} is missing. Stopping.")
            debug_log("Tag is missing. Exiting quiz loop.")
            break
        
        word_data = mapping[chosen_tag]
        click_x = word_data['left'] + int(word_data['width'] * CLICK_CENTER_OFFSET)
        click_y = word_data['top'] + int(word_data['height'] * CLICK_CENTER_OFFSET)
        abs_option_x = region[0] + click_x
        abs_option_y = region[1] + click_y
        debug_log(f"Clicking word '{word_data['text']}' with tag {chosen_tag} at ({abs_option_x}, {abs_option_y})")
        human_move_click(abs_option_x, abs_option_y)
        time.sleep(CLICK_DELAY_SEC)
        
        if not click_button_with_scroll(region):
            error_messages.append("No 'Next' or 'Submit' button detected after scrolling. Stopping.")
            debug_log("No button detected after scroll attempts. Exiting quiz loop.")
            break
        
        debug_log("Waiting for question text to change...")
        new_text = wait_for_text_change(region, tagged_text)
        debug_log(f"Detected new text: {new_text[:100]}...")

    return

def start_quiz(root):
    """
    Adapted for PySide6:
      - Uses mapToGlobal to get absolute window coordinates.
      - Uses hide() and show() instead of withdraw()/deiconify().
      - Updates the status label via setText() (assuming it's a QLabel).
    """
    # Ensure the window is updated.
    root.update()

    # Obtain the global position of the window.
    global_pos = root.mapToGlobal(root.rect().topLeft())
    x = global_pos.x()
    y = global_pos.y()
    width = root.width()
    height = root.height()
    region = (x, y, width, height)
    debug_log(f"Captured region: {region}")

    # Hide the window (like withdraw() in tkinter).
    root.hide()
    time.sleep(WINDOW_HIDE_DELAY_SEC)
    
    process_quiz(region)
    
    # Update the status label.
    # Here we assume that StudyFlow.gui exposes a QLabel named status_label.
    # Adjust this import based on your actual structure.
    from StudyFlow.frontend.gui import status_label  
    result_message = "Quiz complete."
    if error_messages:
        result_message += "\nErrors:\n" + "\n".join(error_messages)
    
    status_label.setText(result_message)

    # Show the window again (like deiconify() in tkinter).
    root.show()


# ============ VISION-BASED QUIZ PROCESSING ============

def process_quiz_vision_mode():
    """
    Vision-based quiz processing - analyzes full screen with GPT-4o Vision.
    No region selection needed - it figures out where the quiz is automatically.
    """
    global emergency_stop, error_messages
    error_messages = []  # Reset errors
    questions_answered = 0

    debug_log("🚀 Starting Vision Mode quiz processing...")

    while True:
        if emergency_stop:
            debug_log("🛑 Emergency stop detected. Exiting quiz loop.")
            break

        # Process the screen with vision
        debug_log(f"\n{'='*50}")
        debug_log(f"📝 Processing question #{questions_answered + 1}")
        debug_log(f"{'='*50}")

        result = process_quiz_with_vision()

        if not result["success"]:
            error_msg = result.get("error", "Unknown error")
            debug_log(f"❌ Vision processing failed: {error_msg}")
            error_messages.append(f"Vision error: {error_msg}")
            break

        # Log what we found
        debug_log(f"📋 Question: {result['question'][:80]}...")
        debug_log(f"🎯 Correct answer #{result['correct_index']}: {result['correct_answer'][:50]}...")
        debug_log(f"💭 Reasoning: {result['reasoning']}")
        debug_log(f"🔒 Confidence: {result['confidence']}")

        # Click the answer
        if result["answer_coords"]:
            x, y = result["answer_coords"]
            debug_log(f"🖱️ Clicking answer at ({x}, {y})")
            human_move_click(x, y)
            time.sleep(CLICK_DELAY_SEC)
        else:
            debug_log("⚠️ Could not find answer coordinates on screen")
            error_messages.append("Could not locate answer text on screen")
            break

        # Click the submit/next button
        if result["button_coords"]:
            x, y = result["button_coords"]
            debug_log(f"🖱️ Clicking '{result['button_text']}' button at ({x}, {y})")
            human_move_click(x, y)
        else:
            debug_log("⚠️ Could not find button coordinates, trying OCR fallback...")
            # Try the scroll-based button finder as fallback
            # Use a dummy region covering most of the screen
            import pyautogui
            screen_width, screen_height = pyautogui.size()
            fallback_region = (0, 0, screen_width, screen_height)
            if not click_button_with_scroll(fallback_region):
                debug_log("❌ Could not find submit button")
                error_messages.append("Could not locate submit button")
                break

        questions_answered += 1
        debug_log(f"✅ Question #{questions_answered} completed!")

        # Wait for next question to load
        delay = random.uniform(QUESTION_WAIT_MIN_SEC, QUESTION_WAIT_MAX_SEC)
        debug_log(f"⏳ Waiting {delay:.1f}s for next question...")
        time.sleep(delay)

    debug_log(f"\n{'='*50}")
    debug_log(f"📊 Quiz session complete! Answered {questions_answered} questions.")
    if error_messages:
        debug_log(f"⚠️ Errors: {error_messages}")
    debug_log(f"{'='*50}\n")

    return questions_answered, error_messages


def start_quiz_vision(root=None):
    """
    Start quiz in Vision Mode - no region selection needed.
    Optionally pass root window to hide it during processing.
    """
    global error_messages
    error_messages = []

    # Hide window if provided
    if root:
        root.hide()
        time.sleep(WINDOW_HIDE_DELAY_SEC)

    questions_answered, errors = process_quiz_vision_mode()

    # Show results
    result_message = f"Vision Mode complete! Answered {questions_answered} questions."
    if errors:
        result_message += f"\nErrors: {', '.join(errors)}"

    # Show window and update status if available
    if root:
        try:
            from StudyFlow.frontend.gui import status_label
            status_label.setText(result_message)
        except Exception:
            pass
        root.show()

    return questions_answered, errors