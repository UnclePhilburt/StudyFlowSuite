from flask import Flask, request, jsonify
from PIL import Image
from io import BytesIO
import pytesseract
import subprocess
import os
import json
import openai

from StudyFlow.backend.image_processing import preprocess_image
from StudyFlow.config import TESSERACT_PATH
from StudyFlow.logging_utils import debug_log

# 🔧 Set the Tesseract binary path for pytesseract
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# 🔐 Set OpenAI API key (comes from Render env)
openai.api_key = os.getenv("OPENAI_API_KEY")

# 🧪 Log the Tesseract version to verify the path works
try:
    version_output = subprocess.check_output([TESSERACT_PATH, "--version"]).decode("utf-8")
    debug_log("✅ Tesseract version output:\n" + version_output)
except Exception as e:
    debug_log("❌ Failed to call Tesseract: " + str(e))

# 🔌 Initialize the Flask app
app = Flask(__name__)

# 🧠 Dummy endpoint for testing data processing
@app.route("/api/process", methods=["POST"])
def process_data():
    try:
        ocr_json = request.get_json()
        if not ocr_json:
            debug_log("❌ No JSON provided")
            return jsonify({"error": "No JSON provided"}), 400

        result = 1  # Placeholder logic
        return jsonify({"result": result})
    except Exception as e:
        debug_log(f"🔥 Error in /api/process: {e}")
        return jsonify({"error": str(e)}), 500

# 👁️ OCR endpoint that handles image upload and returns extracted text
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

        ocr_text = pytesseract.image_to_string(processed)
        debug_log("🔡 OCR complete")

        mapping = {}  # Placeholder
        return jsonify({"ocr_text": ocr_text, "mapping": mapping})
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

        debug_log("✅ /api/layout: Structured data returned successfully")
        return jsonify({"structured_ai": structured}), 200

    except Exception as e:
        debug_log(f"🔥 /api/layout error: {str(e)}")
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


# 🚀 Start the server when running directly
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
