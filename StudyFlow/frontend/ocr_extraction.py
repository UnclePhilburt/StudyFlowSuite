import pytesseract
import json
import re
import difflib
import pyautogui
from StudyFlow.backend.image_processing import preprocess_image, preprocess_image_custom
from StudyFlow.logging_utils import debug_log
from StudyFlow.constants import (
    IMAGE_CONTRAST_FACTOR, IMAGE_THRESHOLD_VALUE,
    QUESTION_WAIT_MIN_SEC, QUESTION_WAIT_MAX_SEC
)
import time
import random

# Patterns to filter out debug/log text from OCR
DEBUG_PATTERNS = [
    r'\[\d{2}:\d{2}:\d{2}\]',  # Timestamps like [08:47:44]
    r'\(\d{2}:\d{2}:\d{2}\)',  # Timestamps like (08:47:44)
    r'debug[:\s]',             # debug: or debug
    r'info[:\s]',              # info: or info
    r'error[:\s]',             # error: or error
    r'warning[:\s]',           # warning: or warning
    r'majority\s*vote',        # "majority vote" log message
    r'falling\s*back',         # "falling back" log message
    r'api\s*call\s*attempt',   # "API call attempt" log message
    r'waiting\s*\d+\.?\d*\s*seconds',  # "Waiting X seconds" log message
    r'starting\s*i[mn]age',    # "Starting image" log message
    r'processed.*saved',       # "Processed...saved" log message
    r'rechecking',             # "Rechecking" log message
]

def is_debug_text(text):
    """Check if text matches common debug/log patterns."""
    text_lower = text.lower()
    for pattern in DEBUG_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    return False

def filter_debug_words(words):
    """Filter out words that are part of debug/log output."""
    filtered = []
    skip_until_line = -1

    for w in words:
        # If we detected a debug line, skip all words on that line
        if w['line_num'] == skip_until_line:
            continue

        # Check if this word looks like debug output
        if is_debug_text(w['text']):
            skip_until_line = w['line_num']  # Skip rest of this line
            continue

        filtered.append(w)

    return filtered

def get_tagged_words_from_processed(processed):
    data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT,
                                     config="--psm 6 --oem 3")
    words = []
    mapping = {}
    tagged_words = []
    tag_number = 1
    for i in range(len(data['text'])):
        text = data['text'][i].strip()
        try:
            conf = float(data['conf'][i])
        except ValueError:
            continue
        if text and conf > 0:
            word_info = {
                'text': text,
                'left': data['left'][i],
                'top': data['top'][i],
                'width': data['width'][i],
                'height': data['height'][i],
                'line_num': data['line_num'][i]
            }
            words.append(word_info)
    words.sort(key=lambda w: (w['line_num'], w['left']))
    words = filter_debug_words(words)  # Filter out debug/log text
    for w in words:
        mapping[tag_number] = w
        tagged_words.append(f"[{tag_number}] {w['text']}")
        tag_number += 1
    tagged_text = " ".join(tagged_words)
    return tagged_text, mapping

def get_tagged_words_from_region(region):
    screenshot = pyautogui.screenshot(region=region)
    processed = preprocess_image(screenshot)
    data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT,
                                     config="--psm 6 --oem 3")
    words = []
    mapping = {}
    tagged_words = []
    tag_number = 1
    for i in range(len(data['text'])):
        text = data['text'][i].strip()
        try:
            conf = float(data['conf'][i])
        except ValueError:
            continue
        if text and conf > 0:
            word_info = {
                'text': text,
                'left': data['left'][i],
                'top': data['top'][i],
                'width': data['width'][i],
                'height': data['height'][i],
                'line_num': data['line_num'][i]
            }
            words.append(word_info)
    words.sort(key=lambda w: (w['line_num'], w['left']))
    words = filter_debug_words(words)  # Filter out debug/log text
    for w in words:
        mapping[tag_number] = w
        tagged_words.append(f"[{tag_number}] {w['text']}")
        tag_number += 1
    tagged_text = " ".join(tagged_words)
    return tagged_text, mapping

def ai_structure_layout(ocr_text):
    prompt = (
        "The following is raw OCR output from a quiz screen. "
        "Please restructure it into a JSON object with two keys: 'question' and 'answers'. "
        "The 'question' value should be a string containing the quiz question, and 'answers' should be an array "
        "of strings, each representing one answer option. Do not add any labels or extra text. Return only valid JSON.\n\n"
        "OCR Output:\n" + ocr_text
    )
    debug_log("Sending OCR text to OpenAI for layout correction.")
    try:
        from openai import OpenAI
        client = OpenAI()
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        ai_response = response.choices[0].message.content.strip()
        debug_log("AI layout correction response: " + ai_response)
        structured = json.loads(ai_response)
        return structured
    except Exception as e:
        debug_log("Error in AI layout correction: " + str(e))
        return None

def convert_answers_list_to_dict(ai_json):
    answers = ai_json.get("answers")
    if isinstance(answers, list) and answers:
        new_answers = {}
        for i, answer in enumerate(answers, start=1):
            new_answers[str(i)] = {"text": answer, "tag": None}
        ai_json["answers"] = new_answers
    return ai_json

def fallback_structure(mapping, expected_answers):
    lines = {}
    for tag, info in mapping.items():
        line = info.get('line_num', 0)
        lines.setdefault(line, []).append((tag, info['text']))
    sorted_line_nums = sorted(lines.keys())
    sorted_lines = [lines[line_num] for line_num in sorted_line_nums]
    line_texts = []
    line_tags = []
    for line in sorted_lines:
        line.sort(key=lambda x: x[0])
        first_tag = line[0][0]
        text = " ".join(word for tag, word in line)
        line_texts.append(text)
        line_tags.append(first_tag)
    total_lines = len(line_texts)
    if total_lines <= expected_answers:
        question = " ".join(line_texts)
        answers = {}
    else:
        question = " ".join(line_texts[:-expected_answers])
        answers = {}
        for i in range(expected_answers):
            answers[str(i+1)] = {"text": line_texts[-expected_answers + i], "tag": line_tags[-expected_answers + i]}
    return {"question": question, "answers": answers}

def assign_tags_from_ocr(ai_answers, ocr_mapping):
    for key, answer in ai_answers.items():
        if answer.get("tag") is None:
            ocr_texts = {tag: data['text'] for tag, data in ocr_mapping.items()}
            best_match = difflib.get_close_matches(answer["text"], list(ocr_texts.values()), n=1)
            if best_match:
                for tag, text in ocr_texts.items():
                    if text == best_match[0]:
                        answer["tag"] = tag
                        debug_log(f"Assigned tag {tag} to answer '{answer['text']}' using text similarity.")
                        break
    return ai_answers

def merge_ai_and_fallback(ai_json, fallback_json, ocr_mapping):
    merged = {}
    merged["question"] = ai_json.get("question", fallback_json.get("question", ""))
    ai_answers = ai_json.get("answers", {})
    fallback_answers = fallback_json.get("answers", {})
    
    merged_answers = {}
    for key, answer in ai_answers.items():
        if answer.get("tag") is None and key in fallback_answers:
            merged_answers[key] = {
                "text": answer.get("text", fallback_answers[key].get("text")),
                "tag": fallback_answers[key].get("tag")
            }
        else:
            merged_answers[key] = answer
    
    if any(a.get("tag") is None for a in merged_answers.values()):
        debug_log("Missing tags detected after merge. Attempting reassignment.")
        merged_answers = assign_tags_from_ocr(merged_answers, ocr_mapping)
    
    merged["answers"] = merged_answers
    return merged

def validate_and_correct(merged_json, region, expected_answers):
    missing_tags = [key for key, answer in merged_json["answers"].items() if answer.get("tag") is None]
    if missing_tags:
        debug_log(f"Missing tags for answers: {missing_tags}. Initiating correction process.")
        screenshot = pyautogui.screenshot(region=region)
        processed_alt = preprocess_image_custom(screenshot, contrast_factor=IMAGE_CONTRAST_FACTOR, threshold_val=IMAGE_THRESHOLD_VALUE)
        new_tagged_text, new_mapping = get_tagged_words_from_processed(processed_alt)
        fallback_alt = fallback_structure(new_mapping, expected_answers)
        ai_json = {"question": merged_json.get("question", ""), "answers": merged_json.get("answers", {})}
        merged_json = merge_ai_and_fallback(ai_json, fallback_alt, new_mapping)
    return merged_json

def normalize_text(text):
    # Lowercase and remove non-alphanumeric characters (optional)
    return re.sub(r'\W+', ' ', text).strip().lower()

def wait_for_text_change(region, last_text, poll_interval=5, similarity_threshold=1):
    # Instead of checking for text change, wait a random duration.
    delay = random.uniform(QUESTION_WAIT_MIN_SEC, QUESTION_WAIT_MAX_SEC)
    debug_log(f"Waiting {delay:.2f} seconds for the new question to load...")
    time.sleep(delay)
    current_text, _ = get_tagged_words_from_region(region)
    return current_text

