from flask import Flask, request, jsonify
from PIL import Image
from io import BytesIO
import pytesseract
from StudyFlow.backend.image_processing import preprocess_image  # Ensure this exists

app = Flask(__name__)

# Define the /api/process endpoint
@app.route("/api/process", methods=["POST"])
def process_data():
    try:
        ocr_json = request.get_json()
        if not ocr_json:
            return jsonify({"error": "No JSON provided"}), 400
        # Here, replace the following dummy logic with your actual processing.
        # For demonstration, we'll assume the processing returns a result value.
        result = 1  # Dummy result
        return jsonify({"result": result})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Define the /ocr endpoint
@app.route("/ocr", methods=["POST"])
def ocr_endpoint():
    if "image" not in request.files:
        return jsonify({"error": "No image provided"}), 400
    try:
        file = request.files["image"]
        image = Image.open(file.stream)
        # Process the image using your backend image processing function.
        processed = preprocess_image(image)
        # Run OCR using pytesseract.
        ocr_text = pytesseract.image_to_string(processed)
        # Optionally, build a mapping (this example leaves it empty).
        mapping = {}
        return jsonify({"ocr_text": ocr_text, "mapping": mapping})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
