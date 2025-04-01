import time
import json
from StudyFlow.ocr_extraction import (
    get_tagged_words_from_region,
    ai_structure_layout,
    convert_answers_list_to_dict,
    fallback_structure,
    merge_ai_and_fallback,
    validate_and_correct,
    wait_for_text_change,
    reprocess_and_combine_ocr
)
from StudyFlow.ai_manager import triple_call_ai_api_json_final
from StudyFlow.screen_interaction import human_move_click, click_button, submit_button_visible
from StudyFlow.logging_utils import debug_log

# Global state variables (you may later refactor these to a proper state manager)
emergency_stop = False
error_messages = []

def process_quiz(region):
    global emergency_stop
    same_text_count = 0
    max_same_text_repeats = 3
    last_question_text = ""
    
    debug_log("Checking if submit button is visible before starting...")

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
            expected_answers = 4
            debug_log("AI layout correction failed; falling back to 4 answer options.")
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
        max_retries = 3
        correct_index = None
        for attempt in range(max_retries):
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
                time.sleep(1)
        
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
        click_x = word_data['left'] + int(word_data['width'] * 0.5)
        click_y = word_data['top'] + int(word_data['height'] * 0.5)
        abs_option_x = region[0] + click_x
        abs_option_y = region[1] + click_y
        debug_log(f"Clicking word '{word_data['text']}' with tag {chosen_tag} at ({abs_option_x}, {abs_option_y})")
        human_move_click(abs_option_x, abs_option_y)
        time.sleep(0.5)
        
        if not click_button(region):
            error_messages.append("No 'Next' or 'Submit' button detected. Stopping.")
            debug_log("No button detected. Exiting quiz loop.")
            break
        
        debug_log("Waiting for question text to change...")
        new_text = wait_for_text_change(region, tagged_text)
        debug_log(f"Detected new text: {new_text[:100]}...")
        last_question_text = new_text

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
    time.sleep(2)
    
    process_quiz(region)
    
    # Update the status label.
    # Here we assume that StudyFlow.gui exposes a QLabel named status_label.
    # Adjust this import based on your actual structure.
    from StudyFlow.gui import status_label  
    result_message = "Quiz complete."
    if error_messages:
        result_message += "\nErrors:\n" + "\n".join(error_messages)
    
    status_label.setText(result_message)
    
    # Show the window again (like deiconify() in tkinter).
    root.show()