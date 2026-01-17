import os
import re
import traceback
import cohere
from StudyFlow.logging_utils import debug_log
from StudyFlow import config  # centralized config with API key

# Load from centralized config or fallback
COHERE_API_KEY = config.COHERE_API_KEY or os.getenv("COHERE_API_KEY")
if COHERE_API_KEY is None:
    raise ValueError("❌ COHERE_API_KEY not found in environment variables.")

def get_cohere_answer(ocr_json, cohere_client_instance=None):
    if cohere_client_instance is None:
        cohere_client_instance = cohere.ClientV2(api_key=COHERE_API_KEY)

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

    debug_log("🟢 Sending prompt to Cohere: " + prompt)

    try:
        response = cohere_client_instance.chat(
            model="command-r-plus-08-2024",
            messages=[{"role": "user", "content": prompt}],
        )

        # Normalize response structure
        if isinstance(response, list):
            first_message = response[0]
        elif isinstance(response, dict) and "message" in response:
            first_message = response["message"]
            if isinstance(first_message, list):
                first_message = first_message[0]
        else:
            first_message = response

        content = ""
        if hasattr(first_message, "content"):
            content = first_message.content
        elif hasattr(first_message, "message") and hasattr(first_message.message, "content"):
            content = first_message.message.content
        elif isinstance(first_message, dict):
            content = first_message.get("content", "")

        # Normalize list to string
        if isinstance(content, list):
            content = " ".join(
                item.get("text", "") if isinstance(item, dict) else str(item)
                for item in content
            ).strip()
        else:
            content = str(content).strip()

        debug_log("📨 Extracted Cohere response: " + content)

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
