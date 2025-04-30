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
import psycopg2
import traceback
import requests
import stripe


from StudyFlow.backend.image_processing import preprocess_image
from StudyFlow.config import TESSERACT_PATH
from StudyFlow.logging_utils import debug_log
from StudyFlow.backend.submit_button_storage import register_submit_button_upload
from StudyFlow.backend.tasks import process_question_async, celery_app
from StudyFlow.backend import tasks  # 🧠 registers the Celery task
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email, MailSettings, SandBoxMode

BACKEND_URL = os.environ.get("BACKEND_URL", "https://studyflowsuite.onrender.com")

stripe.api_key = os.environ['STRIPE_SECRET_KEY']
WEBHOOK_SECRET    = os.environ['STRIPE_WEBHOOK_SECRET']

SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
if not SENDGRID_API_KEY:
    raise RuntimeError("Missing SENDGRID_API_KEY environment variable")
sg_client = SendGridAPIClient(SENDGRID_API_KEY)

# Import AI clients
from StudyFlow.backend.ai_manager import triple_call_ai_api_json_final
from StudyFlow.backend.deepflow import get_deepflow_question

# Set up Tesseract
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH

# Set up OpenAI
openai.api_key = os.getenv("OPENAI_API_KEY")

# Log Tesseract version
try:
    version_output = subprocess.check_output([TESSERACT_PATH, "--version"]).decode("utf-8")
    debug_log("✅ Tesseract version output:\n" + version_output)
except Exception as e:
    debug_log("❌ Failed to call Tesseract: " + str(e) + "\n" + traceback.format_exc())

app = Flask(__name__)

def send_access_key_email(to_email: str, stripe_id: str) -> bool:
    html_content = (
        "<p>Welcome to StudyFlow!</p>"
        "<p>Your access key is:</p>"
        f"<pre style='background:#f4f4f4;padding:8px;border-radius:4px;'>{stripe_id}</pre>"
        "<p>Keep it safe—enter it when launching the app.</p>"
    )
    plain_text_content = (
        f"Welcome to StudyFlow!\n\n"
        f"Your access key is: {stripe_id}\n\n"
        "Keep it safe—enter it when launching the app."
    )

    message = Mail(
        from_email=Email("noreply@studyflowsuite.com", "StudyFlow Suite"),
        to_emails=to_email,
        subject="Your StudyFlow Access Key",
        html_content=html_content,
        plain_text_content=plain_text_content
    )
    # make absolutely sure sandbox is off
    message.mail_settings = MailSettings(sandbox_mode=SandBoxMode(enable=False))

    try:
        response = sg_client.send(message)
        app.logger.info(f"📧 Sent access key to {to_email} (HTTP {response.status_code})")
        return True
    except Exception as e:
        app.logger.error(f"❌ Failed to send access key to {to_email}: {e}")
        return False

import logging
logging.basicConfig(level=logging.INFO)
app.logger.setLevel(logging.INFO)
register_submit_button_upload(app)


def init_postgres_db():
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS qa_pairs (
                id SERIAL PRIMARY KEY,
                question TEXT UNIQUE,
                answer TEXT,
                count INTEGER DEFAULT 1,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS app_config (
                key   TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        conn.commit()
        conn.close()
        print("✅ PostgreSQL: qa_pairs and app_config tables ready.")
    except Exception as e:
        print(f"❌ DB init error: {e}")

# Initialize DB on startup
init_postgres_db()


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

        # Connect and check cache
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute("SELECT answer, count FROM qa_pairs WHERE question = %s", (question_text,))
        row = cur.fetchone()

        if row:
            saved_answer, current_count = row
            new_count = current_count + 1
            cur.execute(
                "UPDATE qa_pairs SET count = %s WHERE question = %s",
                (new_count, question_text)
            )
            conn.commit()

            debug_log("📦 Using cached answer from DB")
            debug_log(f"✅ Q: {question_text[:100]}")
            debug_log(f"✅ A: {saved_answer}")
            debug_log(f"📈 Count incremented to {new_count}")

            # Try to find which key in the incoming answers matches the saved text
            for key, val in ocr_json.get("answers", {}).items():
                if val.get("text", "").strip() == saved_answer.strip():
                    conn.close()
                    return jsonify({"result": int(key)})

    
            # Fallback if none matched exactly
            conn.close()
            return jsonify({"result": 1})
    

        # Not cached → queue an async AI task
        debug_log("📨 About to queue async task...")
        task = process_question_async.delay(ocr_json)
        conn.close()
        debug_log(f"✅ Task queued: {task.id}")
        return jsonify({
            "status": "processing",
            "message": "Question sent for async processing",
            "task_id": task.id
        })

    except Exception as e:
        debug_log(f"🔥 Error in /api/process: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

from StudyFlow.logging_utils import debug_log

@app.route("/api/stripe_webhook", methods=["POST"])
def stripe_webhook():
    # 1) Raw body + signature header
    payload    = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")

    # 2) Verify & parse
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
        app.logger.info(f"✅ Stripe webhook verified: {event['id']} → {event['type']}")
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        app.logger.error(f"⚠️ Webhook validation failed: {e}")
        return "", 400

    # 3) Connect to Postgres
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur  = conn.cursor()
    except Exception as db_err:
        app.logger.error(f"❌ DB connection error: {db_err}")
        return "", 500

    evt_type = event["type"]
    obj      = event["data"]["object"]

    # 4) Handle subscription.created (with email fetch + upsert)
    if evt_type == "customer.subscription.created":
        cust_id = obj["customer"]
        status  = obj["status"]
        # fetch customer email
        try:
            customer = stripe.Customer.retrieve(cust_id)
            email = customer.get("email")
        except Exception as e:
            app.logger.error(f"❌ Failed to retrieve customer email: {e}")
            cur.close(); conn.close()
            return "", 500

        try:
            cur.execute(
                """
                INSERT INTO users (email, stripe_id, subscription_status)
                VALUES (%s, %s, %s)
                ON CONFLICT (stripe_id)
                DO UPDATE SET subscription_status = EXCLUDED.subscription_status
                """,
                (email, cust_id, status)
            )
            conn.commit()
            app.logger.info(f"📥 Subscription created/upserted: {cust_id} → {status}")
        except Exception as e:
            app.logger.error(f"❌ Failed to upsert subscription_status: {e}")
            cur.close(); conn.close()
            return "", 500

    # 5) Handle subscription.updated
    elif evt_type == "customer.subscription.updated":
        cust_id = obj["customer"]
        status  = obj["status"]
        try:
            cur.execute(
                "UPDATE users SET subscription_status = %s WHERE stripe_id = %s",
                (status, cust_id)
            )
            conn.commit()
            app.logger.info(f"🔄 Subscription updated: {cust_id} → {status}")
        except Exception as e:
            app.logger.error(f"❌ Failed to update subscription_status: {e}")
            cur.close(); conn.close()
            return "", 500

    # 6) Handle subscription.deleted
    elif evt_type == "customer.subscription.deleted":
        cust_id = obj["customer"]
        try:
            cur.execute(
                "UPDATE users SET subscription_status = %s WHERE stripe_id = %s",
                ("canceled", cust_id)
            )
            conn.commit()
            app.logger.info(f"🗑️ Subscription canceled: {cust_id}")
        except Exception as e:
            app.logger.error(f"❌ Failed to cancel subscription: {e}")
            cur.close(); conn.close()
            return "", 500

    # 7) Handle checkout.session.completed (new customers)
    elif evt_type == "checkout.session.completed":
        cust_id = obj["customer"]
        email   = obj["customer_details"]["email"]
        if send_access_key_email(email, cust_id):
            app.logger.info(f"✅ Access key emailed to {email}")
        else:
            app.logger.error(f"❌ Could not email access key to {email}")
        try:
            cur.execute(
                """
                INSERT INTO users (email, stripe_id, subscription_status)
                VALUES (%s, %s, %s)
                ON CONFLICT (stripe_id) DO NOTHING
                """,
                (email, cust_id, "active")
            )
            conn.commit()
            app.logger.info(f"🎉 New user created: {email} | {cust_id}")
        except Exception as e:
            app.logger.error(f"❌ Failed to insert new user: {e}")
            cur.close(); conn.close()
            return "", 500

    # 8) Clean up & return
    cur.close()
    conn.close()
    return jsonify({"received": True}), 200

@app.route("/api/deepflow_question", methods=["POST"])
def deepflow_question():
    try:
        data = request.get_json()
        topic = data.get("topic", "default topic")
        previous_questions = data.get("previous_questions", [])
        debug_log(f"Received deepflow question request for topic '{topic}' with previous questions: {previous_questions}")

        question_data = get_deepflow_question(topic, previous_questions)
        if question_data is None:
            debug_log("Failed to generate deepflow question.")
            return jsonify({"error": "Failed to generate question"}), 500

        debug_log("Deepflow question generated successfully.")
        return jsonify(question_data), 200

    except Exception as e:
        debug_log(f"🔥 Error in /api/deepflow_question: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/check_subscription")
def check_subscription():
    sid = request.args.get("stripe_id")
    if not sid:
        return jsonify({"error": "Missing stripe_id"}), 400

    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute(
            "SELECT subscription_status FROM users WHERE stripe_id = %s",
            (sid,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()

        if not row:
            return jsonify({"error": "Unknown customer"}), 404

        return jsonify({"subscription_status": row[0]}), 200

    except Exception as e:
        app.logger.error(f"❌ check_subscription error: {e}")
        return jsonify({"error": "Server error"}), 500


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
        data = pytesseract.image_to_data(
            processed,
            output_type=pytesseract.Output.DICT,
            config="--psm 6 --oem 3"
        )
        mapping = {}
        tag_number = 1
        for i, txt in enumerate(data["text"]):
            text = txt.strip()
            try:
                conf = float(data["conf"][i])
            except:
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

        tagged_text = " ".join(f"[{k}] {v['text']}" for k, v in mapping.items())
        return jsonify({"ocr_text": tagged_text, "mapping": mapping})

    except Exception as e:
        debug_log(f"🔥 OCR processing failed: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/layout", methods=["POST"])
def layout():
    data = request.get_json()
    text = data.get("text", "")
    if not text:
        return jsonify({"error": "No text provided"}), 400

    try:
        # 1) Let the model extract question + answers, preserving tags
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            temperature=0,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are an OCR layout engine. The input text is annotated with "
                        "bracketed numeric tags, for example:\n\n"
                        "[12] A. Clostridium difficile\n"
                        "[15] B. Helicobacter pylori\n"
                        "[18] C. Helicobacter baculiformis\n"
                        "[21] D. Vibrio vulnificus\n\n"
                        "Extract the question and the answer options into JSON using "
                        "exactly those same bracket numbers as both the keys and the "
                        "`tag` values. Do NOT renumber anything.\n\n"
                        "Return JSON in this shape:\n"
                        "{\n"
                        '  "question": "<the question text>",\n'
                        '  "answers": {\n'
                        '    "12": {"text": "A. Clostridium difficile",       "tag": 12},\n'
                        '    "15": {"text": "B. Helicobacter pylori",        "tag": 15},\n'
                        '    "18": {"text": "C. Helicobacter baculiformis", "tag": 18},\n'
                        '    "21": {"text": "D. Vibrio vulnificus",         "tag": 21}\n'
                        "  }\n"
                        "}"
                    )
                },
                {"role": "user", "content": text}
            ]
        )

        # 2) Parse the model’s output
        extracted = json.loads(resp.choices[0].message.content.strip())
        raw_answers = extracted.get("answers", {})

        # 3) Remap into position-based keys "1", "2", … while keeping the original tag
        #    sorted by numeric tag so display order matches the OCR tags in reading order
        sorted_tags = sorted(raw_answers.keys(), key=lambda k: int(k))
        positioned = {}
        for i, tag_str in enumerate(sorted_tags, start=1):
            entry = raw_answers[tag_str]
            positioned[str(i)] = {
                "text": entry["text"],
                "tag": int(tag_str)
            }

        # 4) Overwrite and return
        extracted["answers"] = positioned
        return jsonify({"structured_ai": extracted}), 200

    except Exception as e:
        debug_log(f"🔥 /api/layout error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/fallback", methods=["POST"])
def fallback():
    try:
        data = request.get_json()
        mapping = data.get("ocr_mapping")
        expected = int(data.get("expected_answers", 4))
        if not mapping:
            return jsonify({"error": "Missing ocr_mapping"}), 400

        from StudyFlow.backend.ocr_logic import fallback_structure
        return jsonify(fallback_structure(mapping, expected)), 200

    except Exception as e:
        debug_log(f"🔥 /api/fallback error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/merge", methods=["POST"])
def merge():
    try:
        data = request.get_json()
        from StudyFlow.backend.ocr_logic import merge_ai_and_fallback
        merged = merge_ai_and_fallback(
            data.get("ai_json", {}),
            data.get("fallback_json", {}),
            data.get("ocr_mapping", {})
        )
        return jsonify(merged), 200

    except Exception as e:
        debug_log(f"🔥 /api/merge error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/select-best-ocr", methods=["POST"])
def select_best_ocr():
    data = request.get_json()
    cands = data.get("candidates")
    if not isinstance(cands, list) or not cands:
        return jsonify({"error": "You must provide a list of candidates"}), 400
    if len(cands) == 1:
        return jsonify({"chosen_index": 1}), 200

    prompt = "Below are OCR candidate outputs:\n\n" + "\n\n".join(
        f"Candidate {i+1}:\n{txt}" for i, txt in enumerate(cands)
    ) + f"\n\nWhich is best? Return only the number 1–{len(cands)}."
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        m = re.search(r"(\d+)", resp.choices[0].message.content)
        return jsonify({"chosen_index": int(m.group(1)) if m else 1}), 200
    except Exception as e:
        debug_log(f"🔥 /api/select-best-ocr error: {e}")
        return jsonify({"chosen_index": 1}), 200


@app.route("/api/log", methods=["POST"])
def receive_log():
    try:
        data = request.get_json()
        msg = data.get("message", "")
        if msg:
            print(msg)
            with open("backend_log.txt", "a", encoding="utf-8") as f:
                f.write(msg + "\n")
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        debug_log(f"🔥 /api/log error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/explanation", methods=["POST"])
def generate_explanation():
    try:
        data = request.get_json()
        ocr_json = data.get("ocr_json")
        idx = data.get("chosen_index")
        if ocr_json is None or idx is None:
            return jsonify({"error": "Missing data"}), 400

        prompt = (
            f"Here is the OCR output in JSON:\n{ocr_json}\n"
            f"Explain why answer option {idx} is correct (max 100 words)."
        )
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        return jsonify({"explanation": resp.choices[0].message.content.strip()}), 200

    except Exception as e:
        debug_log(f"🔥 /api/explanation error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/focusflow", methods=["POST"])
def api_focusflow():
    try:
        from StudyFlow.backend.ocr_logic import fallback_structure, merge_ai_and_fallback

        # 1️⃣ grab the uploaded image
        if "image" not in request.files:
            return jsonify({"error":"No image file provided"}), 400
        file = request.files["image"]
        img = Image.open(file.stream).convert("RGB")

        # 2️⃣ preprocess & OCR
        proc = preprocess_image(img)
        data = pytesseract.image_to_data(proc, output_type=pytesseract.Output.DICT)
        mapping = {}
        tag = 1
        for i, txt in enumerate(data["text"]):
            w = txt.strip()
            try: conf = float(data["conf"][i])
            except: continue
            if w and conf > 0:
                mapping[str(tag)] = {
                    "text": w,
                    "left":   data["left"][i],
                    "top":    data["top"][i],
                    "width":  data["width"][i],
                    "height": data["height"][i],
                    "line_num": data["line_num"][i]
                }
                tag += 1
        tagged = " ".join(f"[{k}] {v['text']}" for k,v in mapping.items())

        # 3️⃣ layout via API
        layout_resp = requests.post(f"{BACKEND_URL}/api/layout", json={"text": tagged})
        if layout_resp.status_code != 200:
            return jsonify({"error":"Layout failed","details":layout_resp.text}), 500
        ai_json = layout_resp.json().get("structured_ai", {})

        # 4️⃣ merge with fallback
        expected = len(ai_json.get("answers", {})) if ai_json else 4
        fb_json  = fallback_structure(mapping, expected)
        merged = merge_ai_and_fallback(ai_json, fb_json, mapping) if ai_json and fb_json.get("answers") else ai_json or fb_json

           # 5️⃣ AI vote
        idx = triple_call_ai_api_json_final(merged)
        full = merged["answers"].get(str(idx), {}).get("text", "Unknown")

    # 6️⃣ Generate explanation inline
        prompt = (
            f"Here is the OCR output in JSON:\n{json.dumps(merged)}\n"
            f"Explain why answer option {idx} is correct (max 100 words)."
        )
        resp = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )
        explanation = resp.choices[0].message.content.strip()

    # 7️⃣ Return everything
        return jsonify({
            "full_answer": full,
            "explanation": explanation,
            "merged_json": merged,
            "tagged_text": tagged
        }), 200

    except Exception as e:
        debug_log(f"🔥 /api/focusflow error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500



@app.route("/api/find_button", methods=["POST"])
def find_button():
    try:
        if "image" not in request.files or "template" not in request.files:
            return jsonify({"error": "Missing image or template"}), 400

        npimg = np.frombuffer(request.files["image"].read(), np.uint8)
        img = cv2.imdecode(npimg, cv2.IMREAD_GRAYSCALE)

        tnp = np.frombuffer(request.files["template"].read(), np.uint8)
        tmpl = cv2.imdecode(tnp, cv2.IMREAD_GRAYSCALE)

        best_val, best_loc, best_shape = 0, None, None
        for scale in np.linspace(0.8, 1.2, 10):
            tpl = cv2.resize(tmpl, None, fx=scale, fy=scale)
            res = cv2.matchTemplate(img, tpl, cv2.TM_CCOEFF_NORMED)
            _, mx, _, ml = cv2.minMaxLoc(res)
            if mx > best_val:
                best_val, best_loc, best_shape = mx, ml, tpl.shape

        if best_val >= 0.7 and best_loc and best_shape:
            h, w = best_shape
            cx, cy = best_loc[0] + w//2, best_loc[1] + h//2
            return jsonify({
                "center_x": int(cx),
                "center_y": int(cy),
                "confidence": float(best_val)
            }), 200

        return jsonify({"error": "Button not found", "confidence": best_val}), 404

    except Exception as e:
        debug_log(f"🔥 /api/find_button error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/admin/button-templates")
def admin_view_button_templates():
    try:
        templates_dir = "/mnt/data/button_templates"
        meta = os.path.join(templates_dir, "submit_template_index.json")
        data = {}
        if os.path.exists(meta):
            data = json.load(open(meta, encoding="utf-8"))
        items = sorted(data.items(), key=lambda kv: -kv[1].get("count", 0))

        html = """
        <!DOCTYPE html><html><head><title>Submit Button Templates</title>
        <style>
        body{font-family:Arial;background:#f4f4f4;padding:20px}
        .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:20px}
        .item{background:#fff;padding:10px;border-radius:8px;box-shadow:0 2px 5px rgba(0,0,0,0.1);text-align:center}
        .item img{max-width:100%;border-radius:6px;margin-bottom:10px}
        h1{text-align:center}
        </style></head><body>
        <h1>Submit Button Templates</h1><div class="grid">
        {% for filename,data in templates %}
          <div class="item">
            <img src="/admin/button-image/{{ filename }}" alt="{{ filename }}">
            <div><strong>{{ filename }}</strong></div>
            <div>Matches: {{ data.get('count',0) }}</div>
          </div>
        {% endfor %}
        </div></body></html>
        """
        return render_template_string(html, templates=items)

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
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute("SELECT question, answer, timestamp, count FROM qa_pairs ORDER BY count DESC")
        rows = cur.fetchall()
        cur.execute("SELECT COUNT(*), SUM(count) FROM qa_pairs")
        total, total_count = cur.fetchone()
        conn.close()

        html = f"<h1>Stored Questions & Answers</h1><p>Total Questions: {total} | Total Attempts: {total_count}</p><ul>"
        for q,a,t,c in rows:
            html += f"<li><b>Q:</b> {q}<br><b>A:</b> {a}<br><small>{t} | Count: {c}</small><br><br></li>"
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
        if task.state == "SUCCESS":
            return jsonify({"status": "complete", "result": task.result}), 200
        if task.state == "FAILURE":
            return jsonify({"status": "failed"}), 500
        return jsonify({"status": task.state}), 202

    except Exception as e:
        debug_log(f"🔥 /api/status error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

@app.route("/api/home_message", methods=["GET", "POST"])
def home_message():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    if request.method == "POST":
        # Read the new message from the JSON body
        msg = request.get_json().get("message", "").strip()
        # Insert or update the key/value in app_config
        cur.execute("""
            INSERT INTO app_config (key, value)
            VALUES ('home_message', %s)
            ON CONFLICT (key)
            DO UPDATE SET value = EXCLUDED.value
        """, (msg,))
        conn.commit()
        conn.close()
        return jsonify({"message": msg})

    # GET: fetch the stored message or return a default
    cur.execute("SELECT value FROM app_config WHERE key = 'home_message'")
    row = cur.fetchone()
    conn.close()
    return jsonify({
        "message": row[0] if row else "Welcome to StudyFlow!"
    })

@app.route("/api/freeflow_message", methods=["GET", "POST"])
def freeflow_message():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    if request.method == "POST":
        msg = request.get_json().get("message", "").strip()
        cur.execute("""
            INSERT INTO app_config (key, value)
            VALUES ('freeflow_message', %s)
            ON CONFLICT (key)
            DO UPDATE SET value = EXCLUDED.value
        """, (msg,))
        conn.commit()
        conn.close()
        return jsonify({"message": msg})

    cur.execute("SELECT value FROM app_config WHERE key = 'freeflow_message'")
    row = cur.fetchone()
    conn.close()
    return jsonify({
        "message": row[0] if row else "Welcome to FreeFlow!"
    })

@app.route("/api/focusflow_message", methods=["GET", "POST"])
def focusflow_message():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    if request.method == "POST":
        msg = request.get_json().get("message", "").strip()
        cur.execute("""
            INSERT INTO app_config (key, value)
            VALUES ('focusflow_message', %s)
            ON CONFLICT (key)
            DO UPDATE SET value = EXCLUDED.value
        """, (msg,))
        conn.commit()
        conn.close()
        return jsonify({"message": msg})

    cur.execute("SELECT value FROM app_config WHERE key = 'focusflow_message'")
    row = cur.fetchone()
    conn.close()
    return jsonify({
        "message": row[0] if row else "Welcome to FocusFlow!"
    })

@app.route("/api/deepflow_message", methods=["GET", "POST"])
def deepflow_message():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    if request.method == "POST":
        msg = request.get_json().get("message", "").strip()
        cur.execute("""
            INSERT INTO app_config (key, value)
            VALUES ('deepflow_message', %s)
            ON CONFLICT (key)
            DO UPDATE SET value = EXCLUDED.value
        """, (msg,))
        conn.commit()
        conn.close()
        return jsonify({"message": msg})

    cur.execute("SELECT value FROM app_config WHERE key = 'deepflow_message'")
    row = cur.fetchone()
    conn.close()
    return jsonify({
        "message": row[0] if row else "Welcome to DeepFlow!"
    })

@app.route("/admin/freeflow_message", methods=["GET", "POST"])
def admin_freeflow_message():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    if request.method == "POST":
        new_msg = request.form.get("message", "").strip()
        cur.execute("""
            INSERT INTO app_config (key, value)
            VALUES ('freeflow_message', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, (new_msg,))
        conn.commit()
        current = new_msg
    else:
        cur.execute("SELECT value FROM app_config WHERE key = 'freeflow_message'")
        row = cur.fetchone()
        current = row[0] if row else ""

    conn.close()

    return render_template_string("""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8">
        <title>Admin: FreeFlow Message</title>
      </head>
      <body style="font-family: sans-serif; padding: 2rem;">
        <h1>Update FreeFlow Message</h1>
        <form method="post">
          <textarea name="message" rows="4" cols="60"
            style="font-size:1rem; padding:0.5rem;">{{ message }}</textarea><br><br>
          <button type="submit" style="font-size:1rem; padding:0.5rem 1rem;">
            Save
          </button>
        </form>
      </body>
    </html>
    """, message=current)


@app.route("/admin/focusflow_message", methods=["GET", "POST"])
def admin_focusflow_message():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    if request.method == "POST":
        new_msg = request.form.get("message", "").strip()
        cur.execute("""
            INSERT INTO app_config (key, value)
            VALUES ('focusflow_message', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, (new_msg,))
        conn.commit()
        current = new_msg
    else:
        cur.execute("SELECT value FROM app_config WHERE key = 'focusflow_message'")
        row = cur.fetchone()
        current = row[0] if row else ""

    conn.close()

    return render_template_string("""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8">
        <title>Admin: FocusFlow Message</title>
      </head>
      <body style="font-family: sans-serif; padding: 2rem;">
        <h1>Update FocusFlow Message</h1>
        <form method="post">
          <textarea name="message" rows="4" cols="60"
            style="font-size:1rem; padding:0.5rem;">{{ message }}</textarea><br><br>
          <button type="submit" style="font-size:1rem; padding:0.5rem 1rem;">
            Save
          </button>
        </form>
      </body>
    </html>
    """, message=current)


@app.route("/admin/deepflow_message", methods=["GET", "POST"])
def admin_deepflow_message():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    if request.method == "POST":
        new_msg = request.form.get("message", "").strip()
        cur.execute("""
            INSERT INTO app_config (key, value)
            VALUES ('deepflow_message', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, (new_msg,))
        conn.commit()
        current = new_msg
    else:
        cur.execute("SELECT value FROM app_config WHERE key = 'deepflow_message'")
        row = cur.fetchone()
        current = row[0] if row else ""

    conn.close()

    return render_template_string("""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8">
        <title>Admin: DeepFlow Message</title>
      </head>
      <body style="font-family: sans-serif; padding: 2rem;">
        <h1>Update DeepFlow Message</h1>
        <form method="post">
          <textarea name="message" rows="4" cols="60"
            style="font-size:1rem; padding:0.5rem;">{{ message }}</textarea><br><br>
          <button type="submit" style="font-size:1rem; padding:0.5rem 1rem;">
            Save
          </button>
        </form>
      </body>
    </html>
    """, message=current)



@app.route("/admin/home_message", methods=["GET", "POST"])
def admin_home_message():
    # connect to DB
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    if request.method == "POST":
        # grab the form value and upsert
        new_msg = request.form.get("message", "").strip()
        cur.execute("""
            INSERT INTO app_config (key, value)
            VALUES ('home_message', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        """, (new_msg,))
        conn.commit()
        current = new_msg
    else:
        # fetch the existing message
        cur.execute("SELECT value FROM app_config WHERE key = 'home_message'")
        row = cur.fetchone()
        current = row[0] if row else ""

    conn.close()

    # render a minimal HTML form
    return render_template_string("""
    <!doctype html>
    <html>
      <head>
        <meta charset="utf-8">
        <title>Admin: Home Message</title>
      </head>
      <body style="font-family: sans-serif; padding: 2rem;">
        <h1>Update Home Message</h1>
        <form method="post">
          <textarea name="message" rows="4" cols="60"
            style="font-size:1rem; padding:0.5rem;">{{ message }}</textarea><br><br>
          <button type="submit" style="font-size:1rem; padding:0.5rem 1rem;">
            Save
          </button>
        </form>
      </body>
    </html>
    """, message=current)




if __name__ == "__main__":
    try:
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port)
    except Exception as e:
        debug_log(f"🔥 Server startup error: {e}\n{traceback.format_exc()}")
