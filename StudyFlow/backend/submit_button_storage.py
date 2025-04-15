# submit_button_storage.py

import os
import hashlib
import json
from datetime import datetime
from flask import request, jsonify
from PIL import Image, ImageChops
import imagehash
import numpy as np
import cv2
from io import BytesIO

TEMPLATE_DIR = "static/button_templates"
INDEX_FILE = os.path.join(TEMPLATE_DIR, "submit_template_index.json")

# Ensure folder exists
def ensure_dir():
    os.makedirs(TEMPLATE_DIR, exist_ok=True)
    if not os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, "w") as f:
            json.dump({}, f)

# Crop whitespace
def auto_crop(image):
    bg = Image.new(image.mode, image.size, image.getpixel((0, 0)))
    diff = ImageChops.difference(image, bg)
    bbox = diff.getbbox()
    if bbox:
        return image.crop(bbox)
    return image

# Resize to standard size
def normalize_image(image):
    return image.resize((100, 40)).convert("RGB")

# Hash image
def get_image_hash(image):
    return str(imagehash.phash(image))

# Compare with existing templates
def find_match(new_img, new_hash):
    try:
        with open(INDEX_FILE, "r") as f:
            index = json.load(f)
    except:
        return None

    for filename, meta in index.items():
        existing_path = os.path.join(TEMPLATE_DIR, filename)
        if not os.path.exists(existing_path):
            continue

        existing_img = Image.open(existing_path).convert("RGB")
        existing_img = normalize_image(existing_img)

        # 1. Hash match
        existing_hash = meta.get("hash")
        hash_diff = imagehash.hex_to_hash(existing_hash) - imagehash.hex_to_hash(new_hash)

        # 2. SSIM match
        ssim = compare_ssim(existing_img, new_img)

        # 3. cv2 matchTemplate
        match_score = template_match_score(existing_img, new_img)

        # Use all 3
        if hash_diff <= 8 and ssim >= 0.85 and match_score >= 0.6:
            return filename

    return None

# SSIM comparison
from skimage.metrics import structural_similarity as ssim

def compare_ssim(img1, img2):
    arr1 = np.array(img1)
    arr2 = np.array(img2)
    try:
        score = ssim(arr1, arr2, channel_axis=2)
        return score
    except:
        return 0

# cv2 template match score

def template_match_score(img1, img2):
    img1_cv = cv2.cvtColor(np.array(img1), cv2.COLOR_RGB2GRAY)
    img2_cv = cv2.cvtColor(np.array(img2), cv2.COLOR_RGB2GRAY)
    try:
        res = cv2.matchTemplate(img1_cv, img2_cv, cv2.TM_CCOEFF_NORMED)
        return float(res.max())
    except:
        return 0

# Register route

def register_submit_button_upload(app):
    ensure_dir()

    @app.route("/api/submit_button_template", methods=["POST"])
    def upload_submit_button():
        if "template" not in request.files:
            return jsonify({"error": "No template image provided."}), 400

        try:
            file = request.files["template"]
            image = Image.open(file.stream).convert("RGB")
            image = auto_crop(image)
            image = normalize_image(image)
            new_hash = get_image_hash(image)

            match = find_match(image, new_hash)
            now = datetime.utcnow().isoformat()

            with open(INDEX_FILE, "r") as f:
                index = json.load(f)

            if match:
                index[match]["count"] += 1
                index[match]["last_seen"] = now
                filename = match
            else:
                filename = f"submit_template__{new_hash}.png"
                path = os.path.join(TEMPLATE_DIR, filename)
                image.save(path)
                index[filename] = {
                    "count": 1,
                    "first_seen": now,
                    "last_seen": now,
                    "hash": new_hash
                }

            with open(INDEX_FILE, "w") as f:
                json.dump(index, f, indent=2)

            return jsonify({"status": "stored", "filename": filename}), 200

        except Exception as e:
            return jsonify({"error": str(e)}), 500
