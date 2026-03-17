# smart_image.py
"""
Smart image processing utilities for hybrid quiz processing.
Includes image optimization, change detection, and question caching.
"""

import hashlib
import io
import re
from collections import OrderedDict
from PIL import Image
import imagehash
import pytesseract

from StudyFlow.logging_utils import debug_log
from StudyFlow.constants import (
    IMAGE_MAX_WIDTH,
    IMAGE_HASH_SIZE,
    CHANGE_DETECTION_THRESHOLD,
    CACHE_MAX_SIZE,
    OCR_CONFIDENCE_THRESHOLD,
    MIN_ANSWER_OPTIONS,
    MAX_ANSWER_OPTIONS,
    QUIZ_DETECTION_KEYWORDS,
)


# ============ Question Cache ============
# LRU cache for answered questions
_question_cache = OrderedDict()


def get_cached_answer(question_hash):
    """
    Check if we've seen this question before.
    Returns cached result or None.
    """
    if question_hash in _question_cache:
        # Move to end (most recently used)
        _question_cache.move_to_end(question_hash)
        result = _question_cache[question_hash]
        debug_log(f"CACHE HIT: Using cached answer for question")
        return result
    return None


def cache_answer(question_hash, result):
    """
    Store a question/answer in the cache.
    Evicts oldest entries if cache is full.
    """
    _question_cache[question_hash] = result
    _question_cache.move_to_end(question_hash)

    # Evict oldest if over limit
    while len(_question_cache) > CACHE_MAX_SIZE:
        oldest = next(iter(_question_cache))
        del _question_cache[oldest]
        debug_log(f"CACHE: Evicted oldest entry, size now {len(_question_cache)}")


def hash_question(question_text, answers):
    """
    Create a unique hash for a question based on text content.
    Normalizes whitespace and case for better matching.
    """
    # Normalize: lowercase, strip whitespace, remove punctuation
    normalized = question_text.lower().strip()
    normalized = re.sub(r'\s+', ' ', normalized)

    # Include first few chars of each answer for uniqueness
    answer_sig = "|".join(str(a)[:30].lower().strip() for a in answers)

    combined = f"{normalized}|||{answer_sig}"
    return hashlib.md5(combined.encode()).hexdigest()


# ============ Image Optimization ============

def optimize_screenshot(image):
    """
    Optimize a screenshot for processing.
    - Downscale if too large
    - Returns optimized PIL Image
    """
    width, height = image.size

    if width > IMAGE_MAX_WIDTH:
        ratio = IMAGE_MAX_WIDTH / width
        new_height = int(height * ratio)
        image = image.resize((IMAGE_MAX_WIDTH, new_height), Image.LANCZOS)
        debug_log(f"IMAGE: Downscaled from {width}x{height} to {IMAGE_MAX_WIDTH}x{new_height}")

    return image


def get_image_hash(image):
    """
    Get perceptual hash of an image for change detection.
    Uses average hash which is fast and works well for screenshots.
    """
    return imagehash.average_hash(image, hash_size=IMAGE_HASH_SIZE)


def images_are_similar(hash1, hash2):
    """
    Check if two image hashes represent similar images.
    Returns True if images are essentially the same.
    """
    if hash1 is None or hash2 is None:
        return False

    difference = hash1 - hash2
    is_similar = difference <= CHANGE_DETECTION_THRESHOLD

    if is_similar:
        debug_log(f"IMAGE: Similar to previous (diff={difference})")

    return is_similar


# ============ Quiz Detection ============

def extract_text_with_positions(image):
    """
    Run OCR and extract text with position data.
    Returns (full_text, word_data_list).
    """
    ocr_data = pytesseract.image_to_data(
        image,
        output_type=pytesseract.Output.DICT,
        config="--psm 6 --oem 3"
    )

    words = []
    full_text_parts = []

    for i in range(len(ocr_data['text'])):
        text = ocr_data['text'][i].strip()
        try:
            conf = float(ocr_data['conf'][i])
        except (ValueError, TypeError):
            continue

        if text and conf >= OCR_CONFIDENCE_THRESHOLD:
            words.append({
                'text': text,
                'left': ocr_data['left'][i],
                'top': ocr_data['top'][i],
                'width': ocr_data['width'][i],
                'height': ocr_data['height'][i],
                'conf': conf,
                'line': ocr_data['line_num'][i]
            })
            full_text_parts.append(text)

    full_text = ' '.join(full_text_parts)

    # Debug: Show what OCR extracted
    debug_log(f"OCR: Extracted {len(words)} words with confidence >= {OCR_CONFIDENCE_THRESHOLD}")
    debug_log(f"OCR: Full text preview (first 200 chars): {full_text[:200]}")

    return full_text, words


def detect_quiz_on_screen(text, words):
    """
    Detect if the screen contains a quiz interface.
    Returns True if quiz-like content is detected.
    """
    text_lower = text.lower()

    # Debug: Show what text we're analyzing
    debug_log(f"QUIZ DETECT: Analyzing text (length={len(text)})")
    debug_log(f"QUIZ DETECT: Text preview: '{text[:300]}'")

    # Check for question indicators
    found_keywords = [kw for kw in QUIZ_DETECTION_KEYWORDS if kw in text_lower]
    has_question = len(found_keywords) > 0

    debug_log(f"QUIZ DETECT: Found {len(found_keywords)} keywords: {found_keywords[:5]}")

    # Check for answer option patterns (A., B., C. or 1., 2., 3.)
    letter_pattern = re.search(r'\b[A-D]\s*[.:\)]', text)
    number_pattern = re.search(r'\b[1-4]\s*[.:\)]', text)

    has_options = letter_pattern or number_pattern

    if letter_pattern:
        debug_log(f"QUIZ DETECT: Found letter pattern: {letter_pattern.group()}")
    if number_pattern:
        debug_log(f"QUIZ DETECT: Found number pattern: {number_pattern.group()}")

    # Check for submit/next button text
    button_keywords = ['submit', 'next', 'continue', 'check', 'done', 'finish']
    found_buttons = [kw for kw in button_keywords if kw in text_lower]
    has_button = len(found_buttons) > 0

    if found_buttons:
        debug_log(f"QUIZ DETECT: Found button keywords: {found_buttons}")

    # More lenient detection: accept if we have question indicators OR multiple choice options
    # This helps detect quizzes even if OCR misses some text
    is_quiz = has_question or has_options or has_button

    debug_log(f"QUIZ DETECT: question={has_question}, options={has_options}, button={has_button} -> {is_quiz}")

    return is_quiz


def extract_quiz_structure(text, words):
    """
    Try to extract quiz structure from OCR text locally.
    Returns dict with question and answers, or None if can't parse.
    """
    lines = text.split('\n')
    lines = [l.strip() for l in lines if l.strip()]

    question = None
    answers = []

    # Pattern for answer options
    answer_pattern = re.compile(r'^([A-Da-d]|[1-4])\s*[.:\)]\s*(.+)$')

    for line in lines:
        match = answer_pattern.match(line)
        if match:
            letter, answer_text = match.groups()
            answers.append({
                'label': letter.upper(),
                'text': answer_text.strip()
            })
        elif '?' in line and question is None:
            question = line
        elif not answers and question is None:
            # Accumulate text before answers as question
            if question:
                question += ' ' + line
            else:
                question = line

    # Validate structure
    if question and MIN_ANSWER_OPTIONS <= len(answers) <= MAX_ANSWER_OPTIONS:
        debug_log(f"LOCAL PARSE: Found question + {len(answers)} answers")
        return {
            'question': question,
            'answers': answers
        }

    debug_log(f"LOCAL PARSE: Failed (q={bool(question)}, answers={len(answers)})")
    return None


def find_text_coordinates(target_text, words):
    """
    Find coordinates of target text in the word list.
    Returns (x, y) center coordinates or None.
    """
    target_lower = target_text.lower().strip()
    target_words = target_lower.split()

    if not target_words:
        return None

    # Try to find the first word
    for i, word in enumerate(words):
        if word['text'].lower() == target_words[0]:
            # Found start - calculate center
            x = word['left'] + word['width'] // 2
            y = word['top'] + word['height'] // 2
            debug_log(f"COORDS: Found '{target_text[:30]}' at ({x}, {y})")
            return (x, y)

    # Partial match fallback
    for word in words:
        word_lower = word['text'].lower()
        for target_word in target_words:
            if len(target_word) >= 4 and target_word in word_lower:
                x = word['left'] + word['width'] // 2
                y = word['top'] + word['height'] // 2
                debug_log(f"COORDS: Partial match '{word['text']}' at ({x}, {y})")
                return (x, y)

    return None


def find_button_coordinates(words):
    """
    Find submit/next button coordinates.
    Prioritizes Submit/Next over Finish to avoid ending quiz early.
    Also tries common OCR misreadings of Submit.
    Returns (x, y, button_text) or (None, None, None).
    """
    # Priority order: prefer Submit/Next/Continue over Finish/Done
    high_priority_keywords = ['submit', 'next', 'continue', 'check']
    low_priority_keywords = ['finish', 'done', 'end', 'complete']

    # Common OCR misreadings of "Submit"
    submit_variations = ['submit', 'submi', 'submlt', 'suhmit', 'subnit']

    found_buttons = []

    # Collect all button candidates
    for word in words:
        word_lower = word['text'].lower()

        # Check for Submit variations first (highest priority)
        for variation in submit_variations:
            if variation in word_lower:
                x = word['left'] + word['width'] // 2
                y = word['top'] + word['height'] // 2
                found_buttons.append((0, x, y, word['text'], 'submit'))
                debug_log(f"BUTTON: Found candidate '{word['text']}' (submit variation) at ({x}, {y}), priority=0")
                break

        # Check other high priority keywords
        for keyword in high_priority_keywords:
            if keyword in word_lower:
                x = word['left'] + word['width'] // 2
                y = word['top'] + word['height'] // 2
                found_buttons.append((1, x, y, word['text'], keyword))
                debug_log(f"BUTTON: Found candidate '{word['text']}' (keyword: {keyword}) at ({x}, {y}), priority=1")
                break

        # Check low priority keywords
        for keyword in low_priority_keywords:
            if keyword in word_lower:
                x = word['left'] + word['width'] // 2
                y = word['top'] + word['height'] // 2
                found_buttons.append((2, x, y, word['text'], keyword))
                debug_log(f"BUTTON: Found candidate '{word['text']}' (keyword: {keyword}) at ({x}, {y}), priority=2")
                break

    # Exclude Finish button if Submit button exists
    if found_buttons:
        has_submit = any(b[0] == 0 or (b[0] == 1 and 'submit' in b[4]) for b in found_buttons)
        if has_submit:
            # Filter out finish/done buttons
            found_buttons = [b for b in found_buttons if b[4] not in ['finish', 'done', 'end', 'complete']]
            debug_log(f"BUTTON: Excluded Finish/Done buttons because Submit was found")

    # Return highest priority button (lowest priority number)
    if found_buttons:
        found_buttons.sort(key=lambda b: b[0])  # Sort by priority
        best = found_buttons[0]
        debug_log(f"BUTTON: Selected '{best[3]}' at ({best[1]}, {best[2]})")
        return (best[1], best[2], best[3])

    debug_log("BUTTON: No button found")
    return (None, None, None)
