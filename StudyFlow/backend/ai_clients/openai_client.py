import os
import openai
import re
from StudyFlow.logging_utils import debug_log

openai_api_key = os.environ.get('OPENAI_API_KEY')
if not openai_api_key:
    raise ValueError("OPENAI_API_KEY not found in environment variables. Please set it accordingly.")
openai.api_key = openai_api_key

def get_openai_answer(ocr_json):
    prompt = (
        "Here is the OCR output in JSON format:\n" +
        str(ocr_json) +
        "\nBased on the above, which answer option is correct? "
        "Return only the number corresponding to the correct answer with no extra text."
    )
    debug_log("Sending prompt to OpenAI: " + prompt)
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        ai_response = response['choices'][0]['message']['content'].strip()
        debug_log("Extracted OpenAI response: " + ai_response)
        match = re.fullmatch(r'\s*(\d+)\s*', ai_response)
        if match:
            return int(match.group(1))
        else:
            debug_log("OpenAI response format error: " + ai_response)
            return None
    except Exception as e:
        debug_log("OpenAI API error: " + str(e))
        return None
