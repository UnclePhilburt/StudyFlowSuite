from flask import Flask, request, jsonify
from PIL import Image
from io import BytesIO
import pytesseract
import subprocess
import os
import json
import openai
import re
import cv2
import numpy as np

from StudyFlow.backend.image_processing import preprocess_image
from StudyFlow.config import TESSERACT_PATH
from StudyFlow.logging_utils import debug_log

# Import the triple-call function for the AI clients
from StudyFlow.backend.ai_manager import triple_call_ai_api_json_final
# Import the deepflow function for generating quiz questions
from StudyFlow.backend.deepflow import get_deepflow_question

# Set the Tesseract binary path for pytesseract
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# Set OpenAI API key (comes from Render env)
openai.api_key = os.getenv("OPENAI_API_KEY")

# Log the Tesseract version to verify the path works
try:
    version_output = subprocess.check_output([TESSERACT_PATH, "--version"]).decode("utf-8")
    debug_log("✅ Tesseract version output:\n" + version_output)
except Exception as e:
    debug_log("❌ Failed to call Tesseract: " + str(e))

app = Flask(__name__)

# 🤖 Updated endpoint to call the three AI clients instead of using dummy code
@app.route("/api/process", methods=["POST"])
def process_data():
    try:
        ocr_json = request.get_json()
        if not ocr_json:
            debug_log("❌ No JSON provided")
            return jsonify({"error": "No JSON provided"}), 400

        # Call the function that invokes all three AI clients and returns the chosen answer
        result = triple_call_ai_api_json_final(ocr_json)
        return jsonify({"result": result})
    except Exception as e:
        debug_log(f"🔥 Error in /api/process: {e}")
        return jsonify({"error": str(e)}), 500

# ➕ NEW: DeepFlow Quiz Question Endpoint
@app.route("/api/deepflow_question", methods=["POST"])
def deepflow_question():
    try:
        data = request.get_json()
        topic = data.get("topic", "default topic")
        previous_questions = data.get("previous_questions", [])
        debug_log(f"Received deepflow question request for topic '{topic}' with previous questions: {previous_questions}")

        # Use the deepflow function to generate the question
        question_data = get_deepflow_question(topic, previous_questions)
        if question_data is None:
            debug_log("Failed to generate deepflow question.")
            return jsonify({"error": "Failed to generate question"}), 500

        debug_log("Deepflow question generated successfully.")
        return jsonify(question_data), 200

    except Exception as e:
        debug_log(f"🔥 Error in /api/deepflow_question: {e}")
        return jsonify({"error": str(e)}), 500

# 👁️ OCR endpoint that handles image upload and returns extracted text and mapping
@app.route("/ocr", methods=["POST"])
def ocr_endpoint():
    debug_log("🔍 /ocr endpoint hit")
    if "image" not in request.files:
        debug_log("❌ No image in request")
        return jsonify({"error": "No image provided"}), 400
    try:
        file = request.files["image"]
        debug_log(f"📁 Received file: {file.filename}")
        image = Image.open(file.stream)
        debug_log("🧼 Image opened successfully")
        debug_log(f"📏 Image size: {image.size}, mode: {image.mode}")

        try:
            processed = preprocess_image(image)
            debug_log("🛠️ Image preprocessed successfully")
        except Exception as pe:
            debug_log(f"⚠️ preprocess_image failed: {pe}")
            return jsonify({"error": f"preprocess_image failed: {pe}"}), 500

        # Perform OCR using Tesseract
        ocr_text = pytesseract.image_to_string(processed)
        debug_log("🔡 OCR complete")

        # Create a word-level mapping using pytesseract.image_to_data
        data = pytesseract.image_to_data(processed, output_type=pytesseract.Output.DICT,
                                         config="--psm 6 --oem 3")
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

        # Create a tagged string using the mapping (e.g., "[1] word1 [2] word2 ...")
        tagged_text = " ".join([f"[{k}] {v['text']}" for k, v in mapping.items()])
        return jsonify({"ocr_text": tagged_text, "mapping": mapping})
    except Exception as e:
        debug_log(f"🔥 OCR processing failed: {e}")
        return jsonify({"error": str(e)}), 500

# 🤖 OpenAI Layout Structuring endpoint
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
                {"role": "system", "content": "You are an OCR layout engine. Turn OCR exam text into JSON with 'question' and 'answers'. 'answers' should be a list of answer strings."},
                {"role": "user", "content": text}
            ]
        )
        layout_text = response.choices[0].message.content.strip()
        structured = json.loads(layout_text)
        debug_log("✅ /api/layout: Structured data returned successfully")
        return jsonify({"structured_ai": structured}), 200
    except Exception as e:
        debug_log(f"🔥 /api/layout error: {str(e)}")
        return jsonify({"error": str(e)}), 500

# 🧠 Fallback Structure Generator
@app.route("/api/fallback", methods=["POST"])
def fallback():
    try:
        data = request.get_json()
        mapping = data.get("ocr_mapping")
        expected_answers = int(data.get("expected_answers", 4))

        if not mapping:
            return jsonify({"error": "Missing ocr_mapping"}), 400

        from StudyFlow.backend.ocr_logic import fallback_structure
        result = fallback_structure(mapping, expected_answers)
        return jsonify(result), 200
    except Exception as e:
        debug_log(f"🔥 /api/fallback error: {str(e)}")
        return jsonify({"error": str(e)}), 500

# 🔀 Merge AI + Fallback JSON
@app.route("/api/merge", methods=["POST"])
def merge():
    try:
        data = request.get_json()
        ai_json = data.get("ai_json", {})
        fallback_json = data.get("fallback_json", {})
        mapping = data.get("ocr_mapping", {})

        from StudyFlow.backend.ocr_logic import merge_ai_and_fallback
        merged = merge_ai_and_fallback(ai_json, fallback_json, mapping)
        return jsonify(merged), 200
    except Exception as e:
        debug_log(f"🔥 /api/merge error: {str(e)}")
        return jsonify({"error": str(e)}), 500

# 🧠 OpenAI OCR Candidate Selection
@app.route("/api/select-best-ocr", methods=["POST"])
def select_best_ocr():
    data = request.get_json()
    candidates = data.get("candidates")
    if not candidates or not isinstance(candidates, list) or len(candidates) != 3:
        debug_log("❌ /api/select-best-ocr: Invalid candidate data")
        return jsonify({"error": "You must provide exactly 3 OCR candidates in a list"}), 400

    prompt = (
        "Below are three OCR candidate outputs for the same question:\n\n"
        f"Candidate 1:\n{candidates[0]}\n\n"
        f"Candidate 2:\n{candidates[1]}\n\n"
        f"Candidate 3:\n{candidates[2]}\n\n"
        "Based on clarity and completeness, which candidate best represents the actual question text? "
        "Return only the candidate number (1, 2, or 3)."
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
        debug_log(f"✅ /api/select-best-ocr: AI chose candidate {chosen}")
        return jsonify({"chosen_index": chosen})
    except Exception as e:
        debug_log(f"🔥 /api/select-best-ocr error: {str(e)}")
        return jsonify({"error": str(e)}), 500

# 🪵 Endpoint for logging frontend messages to the backend
@app.route("/api/log", methods=["POST"])
def receive_log():
    data = request.get_json()
    message = data.get("message", "")
    if message:
        print(message)  # Always show in server logs
        try:
            with open("backend_log.txt", "a", encoding="utf-8") as f:
                f.write(message + "\n")
        except Exception as e:
            print(f"[Logging Error] Could not write to file: {e}")
    return jsonify({"status": "ok"}), 200

@app.route("/api/explanation", methods=["POST"])
def generate_explanation():
    try:
        data = request.get_json()
        ocr_json = data.get("ocr_json")
        chosen_index = data.get("chosen_index")

        if not ocr_json or chosen_index is None:
            return jsonify({"error": "Missing data"}), 400

        prompt = (
            "Here is the OCR output in JSON format:\n" + str(ocr_json) +
            "\nExplain why answer option " + str(chosen_index) +
            " is correct. Provide a concise explanation (max 100 words)."
        )

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        explanation = response['choices'][0]['message']['content'].strip()
        return jsonify({"explanation": explanation})
    except Exception as e:
        return jsonify({"error": f"Failed to generate explanation: {e}"}), 500

# ➕ NEW: Find Button Endpoint with User-Supplied Template
@app.route("/api/find_button", methods=["POST"])
def find_button():
    # Verify the screenshot file is provided.
    if "image" not in request.files:
        return jsonify({"error": "No screenshot image provided"}), 400

    screenshot_file = request.files["image"]
    npimg = np.frombuffer(screenshot_file.read(), np.uint8)
    img = cv2.imdecode(npimg, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return jsonify({"error": "Screenshot image decoding failed."}), 400

    # Verify the user-supplied template is provided.
    if "template" not in request.files:
        return jsonify({"error": "No template image provided"}), 400

    template_file = request.files["template"]
    t_np = np.frombuffer(template_file.read(), np.uint8)
    template = cv2.imdecode(t_np, cv2.IMREAD_GRAYSCALE)
    if template is None:
        return jsonify({"error": "Template image decoding failed."}), 400

    best_val = 0
    best_loc = None
    best_temp_shape = None
    scales = np.linspace(0.8, 1.2, 10)
    for scale in scales:
        resized_template = cv2.resize(template, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        result = cv2.matchTemplate(img, resized_template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)
        if max_val > best_val:
            best_val = max_val
            best_loc = max_loc
            best_temp_shape = resized_template.shape

    threshold = 0.7
    if best_val >= threshold and best_loc and best_temp_shape:
        tH, tW = best_temp_shape
        center_x = best_loc[0] + tW // 2
        center_y = best_loc[1] + tH // 2
        return jsonify({
            "center_x": int(center_x),
            "center_y": int(center_y),
            "confidence": float(best_val)
        }), 200
    else:
        return jsonify({"error": "Button not found", "confidence": best_val}), 404

# 🚀 Start the server when running directly
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
