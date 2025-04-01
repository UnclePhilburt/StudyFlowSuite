# ai_manager.py
from ..ai_clients.openai_client import get_openai_answer
from ..ai_clients.claude_client import get_claude_answer
from ..ai_clients.cohere_client import get_cohere_answer
from StudyFlow.logging_utils import debug_log

def triple_call_ai_api_json_final(ocr_json):
    answer_openai = get_openai_answer(ocr_json)
    answer_claude = get_claude_answer(ocr_json)
    answer_cohere = get_cohere_answer(ocr_json)
    debug_log(f"Triple API answers: OpenAI -> {answer_openai}, Claude -> {answer_claude}, Cohere -> {answer_cohere}")
    
    votes = {}
    for ans in [answer_openai, answer_claude, answer_cohere]:
        if ans is not None:
            votes[ans] = votes.get(ans, 0) + 1
    majority = None
    for ans, count in votes.items():
        if count >= 2:
            majority = ans
            break
    if majority is not None:
        debug_log("Majority vote selected answer: " + str(majority))
        return majority
    else:
        debug_log("No majority vote. Using Claude's answer: " + str(answer_claude))
        return answer_claude