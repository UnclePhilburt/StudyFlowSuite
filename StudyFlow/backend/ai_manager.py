import openai  # Ensure OpenAI is imported so its API key can be used
from StudyFlow import config  # This ensures OPENAI_API_KEY is loaded and set
from StudyFlow.backend.ai_clients.openai_client import get_openai_answer
from StudyFlow.backend.ai_clients.claude_client import get_claude_answer
from StudyFlow.backend.ai_clients.cohere_client import get_cohere_answer
from StudyFlow.logging_utils import debug_log


def triple_call_ai_api_json_final(ocr_json):
    debug_log("🔄 Calling AI models with OCR JSON...")

    answer_openai = get_openai_answer(ocr_json)
    answer_claude = get_claude_answer(ocr_json)
    answer_cohere = get_cohere_answer(ocr_json)

    debug_log(f"🤖 Triple API answers:\n - OpenAI: {answer_openai}\n - Claude: {answer_claude}\n - Cohere: {answer_cohere}")
    
    votes = {}
    for ans in [answer_openai, answer_claude, answer_cohere]:
        if ans is not None:
            votes[ans] = votes.get(ans, 0) + 1

    # Use majority if possible, fallback to Claude
    final_answer = None
    for ans, count in votes.items():
        if count >= 2:
            final_answer = ans
            break

    if final_answer:
        debug_log("✅ Majority vote selected answer: " + str(final_answer))
    else:
        final_answer = answer_claude
        debug_log("⚠️ No majority vote. Falling back to Claude's answer: " + str(final_answer))

    # 🔍 Match the final answer text to a key in ocr_json["answers"]
    for key, val in ocr_json.get("answers", {}).items():
        if val["text"].strip() == final_answer.strip():
            debug_log(f"✅ Returning matching answer key: {key}")
            return key

    # ❌ If no match is found, return "1" as a safe fallback
    debug_log("❌ No matching key found in OCR answers. Defaulting to '1'")
    return "1"
