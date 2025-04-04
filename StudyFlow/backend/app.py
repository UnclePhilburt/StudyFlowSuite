from flask import Flask, request, jsonify
from PIL import Image
from io import BytesIO
import pytesseract
import subprocess
import os
import json
import openai
import re

from StudyFlow.backend.image_processing import preprocess_image
from StudyFlow.config import TESSERACT_PATH
from StudyFlow.logging_utils import debug_log
from ai_clients.openai_client import get_openai_answer
from ai_clients.claude_client import get_claude_answer
from ai_clients.cohere_client import get_cohere_answer

# 🔧 Set the Tesseract binary path for pytesseract
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# 🔐 Set OpenAI API key (comes from Render env)
openai.api_key = os.getenv("OPENAI_API_KEY")

# 🔌 Initialize the Flask app
app = Flask(__name__)

# 🧠 Triple AI Voting Logic
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

    for ans, count in votes.items():
        if count >= 2:
            debug_log("✅ Majority vote selected answer: " + str(ans))
            return ans

    debug_log("⚠️ No majority vote. Falling back to Claude's answer: " + str(answer_claude))
    return answer_claude

@app.route("/api/process", methods=["POST"])
def process_data():
    try:
        ocr_json = request.get_json()
        if not ocr_json:
            debug_log("❌ No JSON provided")
            return jsonify({"error": "No JSON provided"}), 400

        if "ocr_text" not in ocr_json or "answers" not in ocr_json:
            debug_log("❌ Missing 'ocr_text' or 'answers' in request")
            return jsonify({"error": "Missing 'ocr_text' or 'answers'"}), 400

        voted_answer = triple_call_ai_api_json_final(ocr_json)
        answer_texts = [a["text"] for a in ocr_json["answers"]]
        try:
            result_index = answer_texts.index(voted_answer) + 1
            debug_log(f"✅ Correct answer matched at index: {result_index}")
        except ValueError:
            debug_log("⚠️ Voted answer not found. Using index 1.")
            result_index = 1

        return jsonify({"result": result_index, "answers": ocr_json["answers"]})
    except Exception as e:
        debug_log(f"🔥 Error in /api/process: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/ocr", methods=["POST"])
def ocr_endpoint():
    debug_log("🔍 /ocr endpoint hit")
    if "image" not in request.files:
        debug_log("❌ No image in request")
        return jsonify({"error": "No image provided"}), 400

    try:
        file = request.files["image"]
        image = Image.open(file.stream)
        processed = preprocess_image(image)
        ocr_text = pytesseract.image_to_string(processed)

        data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT, config="--psm 6 --oem 3")
        mapping = {}
        tag_number = 1
        for i in range(len(data["text"])):
            text = data["text"][i].strip()
            try:
                conf = float(data["conf"][i])
            except ValueError:
                continue
            if text and conf > 0:
                mapping[str(tag_number)] = {
                    "text": text,
                    "left": data["left"][i],
                    "top": data["top"][i],
                    "width": data["width"][i],
                    "height": data["height"][i],
                    "line_num": data["line_num"][i]
                }
                tag_number += 1

        tagged_text = " ".join([f"[{k}] {v['text']}" for k, v in mapping.items()])
        return jsonify({"ocr_text": tagged_text, "mapping": mapping})
    except Exception as e:
        debug_log(f"🔥 OCR processing failed: {e}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/layout", methods=["POST"])
def layout():
    data = request.get_json()
    text = data.get("text", "")
    if not text:
        debug_log("❌ /api/layout: No text provided")
        return jsonify({"error": "No text provided"}), 400

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "You are an OCR layout engine. Turn OCR exam text into JSON with 'question' and 'answers'. 'answers' should be a list of answer strings."
                },
                {
                    "role": "user",
                    "content": text
                }
            ]
        )
        layout_text = response.choices[0].message.content.strip()
        structured = json.loads(layout_text)
        return jsonify({"structured_ai": structured}), 200
    except Exception as e:
        debug_log(f"🔥 /api/layout error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/select-best-ocr", methods=["POST"])
def select_best_ocr():
    data = request.get_json()
    candidates = data.get("candidates")
    if not candidates or not isinstance(candidates, list) or len(candidates) != 3:
        return jsonify({"error": "You must provide exactly 3 OCR candidates in a list"}), 400

    prompt = (
        f"Candidate 1:\n{candidates[0]}\n\n"
        f"Candidate 2:\n{candidates[1]}\n\n"
        f"Candidate 3:\n{candidates[2]}\n\n"
        "Which candidate is best? Return only the number (1, 2, or 3)."
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        ai_choice = response.choices[0].message.content.strip()
        match = re.findall(r'\d+', ai_choice)
        chosen = int(match[0]) if match else 1
        return jsonify({"chosen_index": chosen})
    except Exception as e:
        debug_log(f"🔥 /api/select-best-ocr error: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/log", methods=["POST"])
def receive_log():
    data = request.get_json()
    message = data.get("message", "")
    if message:
        print(message)
        try:
            with open("backend_log.txt", "a", encoding="utf-8") as f:
                f.write(message + "\n")
        except Exception as e:
            print(f"[Logging Error] Could not write to file: {e}")
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
