from flask import Flask, request, jsonify, send_from_directory, render_template_string
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
import sqlite3
import traceback

from StudyFlow.backend.image_processing import preprocess_image
from StudyFlow.config import TESSERACT_PATH
from StudyFlow.logging_utils import debug_log
from StudyFlow.backend.submit_button_storage import register_submit_button_upload
from StudyFlow.backend.tasks import process_question_async, celery_app
from StudyFlow.backend import tasks  # 🧠 This registers the task with Celery
print("✅ tasks module imported successfully")

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
    debug_log("❌ Failed to call Tesseract: " + str(e) + "\n" + traceback.format_exc())

app = Flask(__name__)
register_submit_button_upload(app)

DB_PATH = "/mnt/data/questions_answers.db"

def init_question_db():
    os.makedirs("/mnt/data", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS qa_pairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT UNIQUE,
            answer TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

def add_count_column_if_needed():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("ALTER TABLE qa_pairs ADD COLUMN count INTEGER DEFAULT 1")
        conn.commit()
        conn.close()
        print("✅ Added 'count' column to qa_pairs table.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e):
            print("ℹ️ 'count' column already exists.")
        else:
            print(f"❌ Error adding 'count' column: {e}")

# Initialize on startup
init_question_db()
add_count_column_if_needed()

@app.route("/api/process", methods=["POST"])
def process_data():
    try:
        ocr_json = request.get_json()
        if not ocr_json:
            debug_log("❌ No JSON provided")
            return jsonify({"error": "No JSON provided"}), 400

        question_text = ocr_json.get("question", "").strip()
        if not question_text:
            debug_log("❌ No question found in input")
            return jsonify({"error": "No question text provided"}), 400

        # 🧠 Check DB for exact match
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT answer, count FROM qa_pairs WHERE question = ?", (question_text,))
        row = c.fetchone()

        if row:
            saved_answer, current_count = row
            c.execute("UPDATE qa_pairs SET count = ? WHERE question = ?", (current_count + 1, question_text))
            conn.commit()
            conn.close()
            debug_log(f"📦 Using cached answer from DB")
            debug_log(f"✅ Q: {question_text[:100]}")
            debug_log(f"✅ A: {saved_answer}")
            debug_log(f"✅ Found cached answer: '{saved_answer}'")
            return jsonify({"result": saved_answer, "source": "cache"})

        # 🧠 If not in DB, queue async task to process with AI
        # 🧠 If not in DB, queue async task to process with AI
        debug_log("📨 About to queue async task...")
        task = process_question_async.delay(ocr_json)
        debug_log(f"✅ Task queued: {task.id}")
        conn.close()
        debug_log("🚀 Queued async AI task")
        return jsonify({
            "status": "processing",
            "message": "Question sent for async processing",
            "task_id": task.id
        })


    except Exception as e:
        debug_log(f"🔥 Error in /api/process: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

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
        debug_log(f"🔥 Error in /api/deepflow_question: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

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
            debug_log(f"⚠️ preprocess_image failed: {pe}\n{traceback.format_exc()}")
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
        debug_log(f"🔥 OCR processing failed: {e}\n{traceback.format_exc()}")
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
                {"role": "system", "content": "You are an OCR layout engine. Turn OCR exam text into JSON with 'question' and 'answers'. 'answers' should be a list of answer strings."},
                {"role": "user", "content": text}
            ]
        )
        layout_text = response.choices[0].message.content.strip()
        structured = json.loads(layout_text)
        debug_log("✅ /api/layout: Structured data returned successfully")
        return jsonify({"structured_ai": structured}), 200
    except Exception as e:
        debug_log(f"🔥 /api/layout error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

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
        debug_log(f"🔥 /api/fallback error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

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
        debug_log(f"🔥 /api/merge error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/select-best-ocr", methods=["POST"])
def select_best_ocr():
    data = request.get_json()
    candidates = data.get("candidates")
    if not candidates or not isinstance(candidates, list):
        debug_log("❌ /api/select-best-ocr: Invalid candidate data")
        return jsonify({"error": "You must provide a list of OCR candidates"}), 400

    # If there's only one candidate, just pick it immediately
    if len(candidates) == 1:
        debug_log("ℹ️ /api/select-best-ocr: Single candidate received, selecting index 1")
        return jsonify({"chosen_index": 1}), 200

    # Otherwise, prompt GPT to choose among them
    prompt = "Below are OCR candidate outputs for the same question:\n\n"
    for i, text in enumerate(candidates):
        prompt += f"Candidate {i+1}:\n{text}\n\n"
    prompt += (
        f"Based on clarity and completeness, which candidate best represents the actual question text? "
        f"Return only the candidate number (1–{len(candidates)})."
    )

    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0
        )
        ai_choice = response.choices[0].message.content.strip()
        match = re.search(r\"(\\d+)\", ai_choice)
        chosen = int(match.group(1)) if match else 1
        debug_log(f"✅ /api/select-best-ocr: AI chose candidate {chosen}")
        return jsonify({"chosen_index": chosen}), 200

    except Exception as e:
        debug_log(f"🔥 /api/select-best-ocr error: {e}\\n{traceback.format_exc()}")
        # fallback to first if something goes wrong
        return jsonify({"chosen_index": 1}), 200


@app.route("/api/log", methods=["POST"])
def receive_log():
    try:
        data = request.get_json()
        message = data.get("message", "")
        if message:
            print(message)  # Always show in server logs
            try:
                with open("backend_log.txt", "a", encoding="utf-8") as f:
                    f.write(message + "\n")
            except Exception as e:
                print(f"[Logging Error] Could not write to file: {e}\n{traceback.format_exc()}")
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        debug_log(f"🔥 /api/log error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

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
        debug_log(f"🔥 /api/explanation error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": f"Failed to generate explanation: {e}"}), 500

@app.route("/api/focusflow", methods=["POST"])
def api_focusflow():
    try:
        from StudyFlow.backend.ocr_logic import fallback_structure, merge_ai_and_fallback
        region = request.json.get("region")  # [x, y, width, height]
        if not region or len(region) != 4:
            return jsonify({"error": "Missing or invalid region"}), 400

        region_tuple = tuple(region)

        from StudyFlow.backend.screen_grab import grab_screen_region
        image = grab_screen_region(region_tuple)

        from StudyFlow.backend.image_processing import preprocess_image
        processed = preprocess_image(image)

        from pytesseract import image_to_string, image_to_data, Output
        text = image_to_string(processed)
        data = image_to_data(processed, output_type=Output.DICT, config="--psm 6 --oem 3")

        mapping = {}
        tag_number = 1
        for i in range(len(data["text"])):
            txt = data["text"][i].strip()
            try:
                conf = float(data["conf"][i])
            except ValueError:
                continue
            if txt and conf > 0:
                mapping[str(tag_number)] = {
                    "text": txt,
                    "left": data["left"][i],
                    "top": data["top"][i],
                    "width": data["width"][i],
                    "height": data["height"][i],
                    "line_num": data["line_num"][i]
                }
                tag_number += 1

        tagged_text = " ".join([f"[{k}] {v['text']}" for k, v in mapping.items()])

        from StudyFlow.backend.ocr_logic import ai_structure_layout, convert_answers_list_to_dict
        ai_json = ai_structure_layout(tagged_text)
        expected_answers = len(ai_json.get("answers", [])) if ai_json else 4

        fallback_json = fallback_structure(mapping, expected_answers)

        if ai_json and fallback_json.get("answers"):
            ai_json = convert_answers_list_to_dict(ai_json)
            merged_json = merge_ai_and_fallback(ai_json, fallback_json, mapping)
        elif ai_json:
            merged_json = ai_json
        else:
            merged_json = fallback_json

        from StudyFlow.backend.ai_manager import triple_call_ai_api_json_final
        chosen_index = triple_call_ai_api_json_final(merged_json)

        from StudyFlow.backend.explanation_generator import generate_explanation_for_index
        explanation = generate_explanation_for_index(merged_json, chosen_index)

        full_answer = merged_json["answers"].get(str(chosen_index), {}).get("text", "Unknown")

        return jsonify({
            "full_answer": full_answer,
            "explanation": explanation,
            "merged_json": merged_json,
            "tagged_text": tagged_text
        }), 200
    except Exception as e:
        debug_log(f"🔥 /api/focusflow error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/find_button", methods=["POST"])
def find_button():
    try:
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
    except Exception as e:
        debug_log(f"🔥 /api/find_button error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

@app.route("/admin/button-templates")
def admin_view_button_templates():
    try:
        templates_dir = "/mnt/data/button_templates"
        metadata_path = os.path.join(templates_dir, "submit_template_index.json")

        # Load metadata
        metadata = {}
        if os.path.exists(metadata_path):
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)

        sorted_templates = sorted(metadata.items(), key=lambda x: -x[1].get("count", 0))

        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Submit Button Templates</title>
            <style>
                body { font-family: Arial; background: #f4f4f4; padding: 20px; }
                .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; }
                .item { background: #fff; padding: 10px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); text-align: center; }
                .item img { max-width: 100%; border-radius: 6px; margin-bottom: 10px; }
                h1 { text-align: center; }
            </style>
        </head>
        <body>
            <h1>Submit Button Templates</h1>
            <div class="grid">
                {% for filename, data in templates %}
                    <div class="item">
                        <img src="/admin/button-image/{{ filename }}" alt="{{ filename }}">
                        <div><strong>{{ filename }}</strong></div>
                        <div>Matches: {{ data.get('count', 0) }}</div>
                    </div>
                {% endfor %}
            </div>
        </body>
        </html>
        """
        return render_template_string(html, templates=sorted_templates)
    except Exception as e:
        debug_log(f"🔥 /admin/button-templates error: {e}\n{traceback.format_exc()}")
        return f"<h1>Error:</h1><p>{e}</p>"

@app.route("/admin/button-image/<path:filename>")
def serve_button_template(filename):
    try:
        return send_from_directory("/mnt/data/button_templates", filename)
    except Exception as e:
        debug_log(f"🔥 /admin/button-image error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

@app.route("/admin/view-qa")
def view_qa():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT question, answer, timestamp, count FROM qa_pairs ORDER BY count DESC")
        rows = c.fetchall()
        conn.close()
        html = "<h1>Stored Questions & Answers</h1><ul>"
        for q, a, t, count in rows:
            html += f"<li><b>Q:</b> {q}<br><b>A:</b> {a}<br><small>{t} | Count: {count}</small><br><br></li>"
        html += "</ul>"
        return html
    except Exception as e:
        debug_log(f"🔥 /admin/view-qa error: {e}\n{traceback.format_exc()}")
        return f"<h1>Error:</h1><p>{e}</p>"

@app.route("/api/status/<task_id>")
def get_task_status(task_id):
    try:
        task = celery_app.AsyncResult(task_id)
        if task.state == "PENDING":
            return jsonify({"status": "pending"}), 202
        elif task.state == "SUCCESS":
            return jsonify({"status": "complete", "result": task.result}), 200
        elif task.state == "FAILURE":
            return jsonify({"status": "failed"}), 500
        else:
            return jsonify({"status": task.state}), 202
    except Exception as e:
        debug_log(f"🔥 /api/status error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

# 🚀 Start the server when running directly
if __name__ == "__main__":
    try:
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port)
    except Exception as e:
        debug_log(f"🔥 Server startup error: {e}\n{traceback.format_exc()}")
