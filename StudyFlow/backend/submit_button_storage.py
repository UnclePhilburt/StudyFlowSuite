# backend/submit_button_storage.py

import os
import hashlib
import time
from flask import request, jsonify
from werkzeug.utils import secure_filename

from StudyFlow.logging_utils import debug_log

# Where we save the captured PNGs
TEMPLATE_FOLDER = os.path.join("backend", "static", "button_templates")
os.makedirs(TEMPLATE_FOLDER, exist_ok=True)

def generate_filename(image_bytes):
    """
    Generate a unique filename based on the image content + timestamp hash.
    """
    timestamp = str(time.time()).encode("utf-8")
    image_hash = hashlib.sha256(image_bytes + timestamp).hexdigest()
    return f"submit_{image_hash[:16]}.png"

def register_submit_button_upload(app):
    @app.route("/api/upload_submit_button", methods=["POST"])
    def upload_submit_button():
        if "image" not in request.files:
            debug_log("❌ No image file in request.")
            return jsonify({"error": "No image file provided."}), 400

        image_file = request.files["image"]
        image_bytes = image_file.read()

        try:
            filename = generate_filename(image_bytes)
            filepath = os.path.join(TEMPLATE_FOLDER, secure_filename(filename))

            with open(filepath, "wb") as f:
                f.write(image_bytes)

            debug_log(f"✅ Stored submit button to: {filepath}")
            return jsonify({"status": "success", "filename": filename}), 200

        except Exception as e:
            debug_log(f"🔥 Failed to save submit button: {e}")
            return jsonify({"error": str(e)}), 500
