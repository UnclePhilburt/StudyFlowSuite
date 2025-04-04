from flask import Flask, request, jsonify
from PIL import Image
from io import BytesIO
import pytesseract
import subprocess
import os
import json
import openai
import re
import traceback
import cohere
import anthropic

from StudyFlow.backend.image_processing import preprocess_image
from StudyFlow.config import TESSERACT_PATH, OPENAI_API_KEY, COHERE_API_KEY, ANTHROPIC_API_KEY
from StudyFlow.logging_utils import debug_log

# 🔧 Set the Tesseract binary path for pytesseract
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# 🔐 Set API keys
openai.api_key = OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY or os.getenv("CLAUDE_API_KEY"))
cohere_client = cohere.ClientV2(api_key=COHERE_API_KEY or os.getenv("COHERE_API_KEY"))

# 🔌 Initialize the Flask app
app = Flask(__name__)

# === AI CLIENT FUNCTIONS ===
def get_openai_answer(ocr_json):
    prompt = (
        "Here is the OCR output in JSON format:\n" +
        str(ocr_json) +
        "\nBased on the above, which answer option is correct? "
        "Return only the number corresponding to the correct answer with no extra text."
    )
    debug_log("\U0001F7E2 Sending prompt to OpenAI: " + prompt)

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        ai_response = response['choices'][0]['message']['content'].strip()
        debug_log("\U0001F4E8 Extracted OpenAI response: " + ai_response)
        match = re.fullmatch(r'\s*(\d+)\s*', ai_response)
        if match:
            return int(match.group(1))
        numbers = re.findall(r'\d+', ai_response)
        return int(numbers[0]) if numbers else None
    except Exception as e:
        debug_log("\U0001F525 OpenAI API error: " + str(e))
        debug_log("\U0001F525 Traceback:\n" + traceback.format_exc())
        return None

def get_claude_answer(ocr_json):
    prompt = (
        "Here is the OCR output in JSON format:\n" +
        str(ocr_json) +
        "\nBased on the above, which answer option is correct? "
        "Return only the number corresponding to the correct answer with no extra text."
    )
    debug_log("\U0001F7E1 Sending prompt to Claude: " + prompt)

    try:
        response = claude_client.messages.create(
            model="claude-3-7-sonnet-20250219",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        ai_response = response.content
        if isinstance(ai_response, list):
            ai_response = " ".join(map(str, ai_response)).strip()
        debug_log("\U0001F4E8 Claude response: " + ai_response)
        match = re.fullmatch(r'\s*Answer:\s*(\d+)\s*', ai_response)
        if match:
            return int(match.group(1))
        numbers = re.findall(r'\d+', ai_response)
        return int(numbers[0]) if numbers else None
    except Exception as e:
        debug_log("\U0001F525 Claude API error: " + str(e))
        debug_log("\U0001F525 Traceback:\n" + traceback.format_exc())
        return None

def get_cohere_answer(ocr_json):
    prompt = (
        "Here is the OCR output in JSON format:\n" +
        str(ocr_json) +
        "\nBased on the above, which answer option is correct? "
        "Return only the number corresponding to the correct answer with no extra text."
    )
    debug_log("\U0001F7E2 Sending prompt to Cohere: " + prompt)

    try:
        response = cohere_client.chat(
            model="command-r-plus-08-2024",
            messages=[{"role": "user", "content": prompt}]
        )
        content = getattr(response, "content", str(response)).strip()
        if isinstance(content, list):
            content = " ".join([str(item.get("text", item)) for item in content]).strip()
        debug_log("\U0001F4E8 Cohere response: " + content)
        match = re.fullmatch(r'\s*(\d+)\s*', content)
        if match:
            return int(match.group(1))
        numbers = re.findall(r'\d+', content)
        return int(numbers[0]) if numbers else None
    except Exception as e:
        debug_log("\U0001F525 Cohere API error: " + str(e))
        debug_log("\U0001F525 Traceback:\n" + traceback.format_exc())
        return None

# === AI VOTING ===
def triple_call_ai_api_json_final(ocr_json):
    debug_log("\U0001F501 Calling AI models with OCR JSON...")
    answers = [get_openai_answer(ocr_json), get_claude_answer(ocr_json), get_cohere_answer(ocr_json)]
    debug_log(f"\U0001F916 AI answers: {answers}")
    votes = {}
    for ans in answers:
        if ans is not None:
            votes[ans] = votes.get(ans, 0) + 1
    for ans, count in votes.items():
        if count >= 2:
            debug_log(f"✅ Majority voted for: {ans}")
            return ans
    fallback = answers[1]  # Claude fallback
    debug_log(f"⚠️ No majority, falling back to Claude: {fallback}")
    return fallback
