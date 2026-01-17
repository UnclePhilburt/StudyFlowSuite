from StudyFlow.backend.ai_clients.cohere_client import get_cohere_answer
from StudyFlow.logging_utils import debug_log


def triple_call_ai_api_json_final(ocr_json):
    """Calls Cohere AI to get the answer."""
    debug_log("🔄 Calling Cohere AI with OCR JSON...")

    answer = get_cohere_answer(ocr_json)

    debug_log(f"🤖 Cohere answer: {answer}")

    if answer is not None:
        debug_log("✅ Cohere selected answer: " + str(answer))
        return answer
    else:
        debug_log("⚠️ Cohere returned None - will retry")
        return None  # Return None so core_engine.py can retry
