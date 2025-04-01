import re
import anthropic
from StudyFlow.config import ANTHROPIC_API_KEY
from StudyFlow.logging_utils import debug_log

def get_claude_answer(ocr_json, claude_client_instance=None):
    # Create a client instance if one isn't provided.
    if claude_client_instance is None:
        claude_client_instance = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    
    prompt = (
        "Here is the OCR output in JSON format:\n" +
        str(ocr_json) +
        "\nBased on the above, which answer option is correct? "
        "Return only the number corresponding to the correct answer with no extra text."
    )
    debug_log("Sending prompt to Claude: " + prompt)
    try:
        response = claude_client_instance.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        ai_response = response.content
        if isinstance(ai_response, list):
            ai_response = " ".join(map(str, ai_response))
        ai_response = ai_response.strip()
        if ai_response.startswith("TextBlock("):
            match = re.search(r"text='(\d+)'", ai_response)
            if match:
                extracted_number = match.group(1)
                debug_log("Extracted number from Claude TextBlock: " + extracted_number)
                ai_response = "Answer: " + extracted_number
            else:
                debug_log("Failed to extract number from Claude: " + ai_response)
        debug_log("Extracted Claude response: " + ai_response)
        match = re.fullmatch(r'\s*Answer:\s*(\d+)\s*', ai_response)
        if match:
            return int(match.group(1))
        else:
            numbers = re.findall(r'\d+', ai_response)
            if numbers:
                return int(numbers[0])
            else:
                debug_log("Claude response format error: " + ai_response)
                return None
    except Exception as e:
        debug_log("Claude API error: " + str(e))
        return None
