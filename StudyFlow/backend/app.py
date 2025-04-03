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

# 🚀 Start the server when running directly
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
