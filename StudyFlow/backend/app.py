from flask import Flask, request, jsonify
from PIL import Image
from io import BytesIO
import pytesseract
from StudyFlow.backend.image_processing import preprocess_image  # or your actual processing function

app = Flask(__name__)

# Existing endpoints...
@app.route("/api/process", methods=["POST"])
def process_data():
    # ... your code for processing OCR JSON ...
    pass

# NEW: Define the /ocr endpoint
@app.route("/ocr", methods=["POST"])
def ocr_endpoint():
    if "image" not in request.files:
        return jsonify({"error": "No image provided"}), 400
    try:
        file = request.files["image"]
        image = Image.open(file.stream)
        # Process the image (you can adjust this logic)
        processed = preprocess_image(image)
        # Run OCR with pytesseract:
        ocr_text = pytesseract.image_to_string(processed)
        # Optionally, build a mapping if needed
        mapping = {}  # For now, leave this empty or build your mapping
        return jsonify({"ocr_text": ocr_text, "mapping": mapping})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
