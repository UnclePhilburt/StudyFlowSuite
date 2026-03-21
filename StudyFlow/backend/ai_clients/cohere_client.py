import os
import re
import traceback
import google.generativeai as genai
from StudyFlow.logging_utils import debug_log
from StudyFlow import config  # centralized config with API key

# Load Gemini API key from config or environment
GEMINI_API_KEY = config.GEMINI_API_KEY if hasattr(config, 'GEMINI_API_KEY') else os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY is None:
    raise ValueError("❌ GEMINI_API_KEY not found in environment variables.")

genai.configure(api_key=GEMINI_API_KEY)

def get_cohere_answer(ocr_json, cohere_client_instance=None):
    """
    Get answer using Gemini 3.1 Flash-Lite (renamed from get_cohere_answer for backwards compatibility)
    """
    # Build a clearer prompt with explicit option numbering
    question = ocr_json.get("question", "")
    answers = ocr_json.get("answers", {})

    options_text = ""
    for key in sorted(answers.keys(), key=lambda x: int(x)):
        text = answers[key].get("text", "")
        options_text += f"Option {key}: {text}\n"

    prompt = f"""You are answering a multiple choice question.

Question: {question}

{options_text}
Which option number (1, 2, 3, or 4) is the correct answer?

IMPORTANT: Reply with ONLY a single digit: 1, 2, 3, or 4. Nothing else."""

    debug_log("🟢 Sending prompt to Gemini 3.1 Flash-Lite: " + prompt)

    try:
        # Use Gemini 3.1 Flash-Lite (fastest, cheapest)
        model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')
        response = model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=0.1,  # Very low for factual answers
                max_output_tokens=10  # Only need 1 digit
            )
        )

        content = response.text.strip()
        debug_log("📨 Extracted Gemini response: " + content)

        # Only accept 1, 2, 3, or 4 as valid answers
        # First try exact match
        if content in ["1", "2", "3", "4"]:
            return int(content)

        # Look for option references like "Option 4" or "option 4"
        option_match = re.search(r'[Oo]ption\s*(\d)', content)
        if option_match and option_match.group(1) in ["1", "2", "3", "4"]:
            return int(option_match.group(1))

        # Look for standalone 1-4 at start of response
        start_match = re.match(r'^[^\d]*([1-4])[^\d]', content + " ")
        if start_match:
            return int(start_match.group(1))

        # Last resort: find any 1-4 in the response
        valid_numbers = re.findall(r'[1-4]', content)
        if valid_numbers:
            return int(valid_numbers[0])

        debug_log("❓ Cohere response format error. Raw: " + content)
        return None

    except Exception as e:
        debug_log("🔥 Cohere API error: " + str(e))
        debug_log("🔥 Traceback:\n" + traceback.format_exc())
        return None
