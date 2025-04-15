# submit_button_storage.py (backend logic)

import os
import uuid
import datetime
from flask import request, jsonify
from werkzeug.utils import secure_filename

from StudyFlow.logging_utils import debug_log

# Directory to store all button templates
BUTTON_DIR = os.path.join("static", "button_templates")
os.makedirs(BUTTON_DIR, exist_ok=True)

@app.route("/api/save_button_template", methods=["POST"])
def save_button_template():
    try:
        if "image" not in request.files:
            return jsonify({"error": "No image file in request."}), 400

        file = request.files["image"]
        if file.filename == "":
            return jsonify({"error": "No selected file."}), 400

        # Create a unique filename with timestamp
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        filename = f"button_{timestamp}_{unique_id}.png"
        save_path = os.path.join(BUTTON_DIR, secure_filename(filename))

        file.save(save_path)
        debug_log(f"✅ Saved button template: {filename}")

        # Optionally: save metadata here if needed later
        return jsonify({"status": "ok", "filename": filename}), 200

    except Exception as e:
        debug_log(f"🔥 Error saving button template: {e}")
        return jsonify({"error": str(e)}), 500
