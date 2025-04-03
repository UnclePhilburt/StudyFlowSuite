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
    
    prompt = (
        "Here is the OCR output in JSON format:\n" +
        str(ocr_json) +
        "\nBased on the above, which answer option is correct? "
        "Return only the number corresponding to the correct answer with no extra text."
    )
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

        # Match strictly a number
        match = re.fullmatch(r'\s*(\d+)\s*', content)
        if match:
            return int(match.group(1))

        # Try to grab any digit fallback
        numbers = re.findall(r'\d+', content)
        if numbers:
            return int(numbers[0])
        else:
            debug_log("❓ Cohere response format error. Raw: " + content)
            return None

    except Exception as e:
        debug_log("🔥 Cohere API error: " + str(e))
        debug_log("🔥 Traceback:\n" + traceback.format_exc())
        return None
