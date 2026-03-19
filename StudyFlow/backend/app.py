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

# Enable CORS for website
from flask_cors import CORS
CORS(app, resources={
    r"/api/*": {
        "origins": [
            "https://unclephilburt.github.io",
            "http://localhost:8000",
            "http://localhost:5000",
            "http://127.0.0.1:8000",
            "http://127.0.0.1:5000"
        ],
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"]
    }
})

def send_access_key_email(to_email: str, stripe_id: str) -> bool:
    # Build your message bodies
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

    # Create the SendGrid client from env var
    sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))

    # Construct the Mail object
    message = Mail(
        from_email=Email("info@studyflowsuite.com", "StudyFlow Suite"),
        to_emails=to_email,
        subject="Your StudyFlow Access Key",
        plain_text_content=plain_text_content,
        html_content=html_content
    )
    # Make sure sandbox is off
    message.mail_settings = MailSettings(sandbox_mode=SandBoxMode(enable=False))

    try:
        app.logger.debug(f"➤ Sending access key email to {to_email}")
        response = sg.send(message)
        app.logger.info(f"✔️  SendGrid replied {response.status_code}")
        app.logger.debug(f"   body: {response.body}")
        app.logger.debug(f"   headers: {response.headers}")
        return True
    except Exception as e:
        app.logger.error("❌  SendGrid error sending access key email", exc_info=e)
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


# ============================================================================
# USER AUTHENTICATION & SUBSCRIPTION ROUTES
# ============================================================================
import bcrypt
import jwt
from datetime import datetime, timedelta
from functools import wraps

JWT_SECRET = os.environ.get("JWT_SECRET", "a7f3e9d2c4b8a1f6e3d9c2b7a5f8e1d4c9b6a3f7e2d8c5b1a6f9e4d3c8b2a7f5e1d8c4b9a6f3")

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash"""
    if not hashed:
        return False
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

def create_token(user_id: int, email: str) -> str:
    """Create JWT token for user"""
    payload = {
        'user_id': user_id,
        'email': email,
        'exp': datetime.utcnow() + timedelta(days=30)
    }
    return jwt.encode(payload, JWT_SECRET, algorithm='HS256')

def check_question_limit(user_id):
    """Check if user has exceeded their daily question limit. Returns (can_proceed, remaining_questions)"""
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()

        # Check user's subscription status
        cur.execute("SELECT subscription_status FROM users WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user:
            conn.close()
            return False, 0

        subscription_status = user[0]

        # Pro/trialing users have unlimited questions
        if subscription_status in ['active', 'trialing']:
            conn.close()
            return True, -1  # -1 means unlimited

        # Free users have 10 questions per day limit
        today = datetime.utcnow().date()

        # Get or create today's usage record
        cur.execute("""
            INSERT INTO question_usage (user_id, question_date, question_count)
            VALUES (%s, %s, 0)
            ON CONFLICT (user_id, question_date) DO NOTHING
        """, (user_id, today))

        cur.execute("""
            SELECT question_count FROM question_usage
            WHERE user_id = %s AND question_date = %s
        """, (user_id, today))

        result = cur.fetchone()
        current_count = result[0] if result else 0

        FREE_LIMIT = 10
        remaining = FREE_LIMIT - current_count

        if current_count >= FREE_LIMIT:
            conn.close()
            return False, 0

        # Increment count
        cur.execute("""
            UPDATE question_usage
            SET question_count = question_count + 1
            WHERE user_id = %s AND question_date = %s
        """, (user_id, today))

        conn.commit()
        conn.close()

        return True, remaining - 1

    except Exception as e:
        app.logger.error(f"Error checking question limit: {e}")
        return True, -1  # Allow on error to not block users

def token_required(f):
    """Decorator to protect routes with JWT authentication"""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'Token is missing'}), 401
        try:
            if token.startswith('Bearer '):
                token = token[7:]
            data = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
            request.user_id = data['user_id']
            request.user_email = data['email']
        except:
            return jsonify({'error': 'Token is invalid'}), 401
        return f(*args, **kwargs)
    return decorated

def init_users_table():
    """Create users table if it doesn't exist, and add missing columns if needed"""
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()

        print("🔧 Starting users table initialization...")

        # Create table if it doesn't exist
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                name VARCHAR(255),
                password_hash VARCHAR(255),
                stripe_customer_id VARCHAR(255) UNIQUE,
                stripe_subscription_id VARCHAR(255),
                subscription_status VARCHAR(50) DEFAULT 'free',
                trial_ends_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create question usage tracking table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS question_usage (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                question_date DATE NOT NULL DEFAULT CURRENT_DATE,
                question_count INTEGER DEFAULT 0,
                UNIQUE(user_id, question_date)
            );
        """)

        conn.commit()
        print("✅ Table creation/check complete")

        # Add missing columns if table already exists (compatible with older PostgreSQL)
        columns_to_add = [
            ("name", "VARCHAR(255)"),
            ("password_hash", "VARCHAR(255)"),
            ("stripe_customer_id", "VARCHAR(255)"),
            ("stripe_subscription_id", "VARCHAR(255)"),
            ("trial_ends_at", "TIMESTAMP"),
            ("created_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
        ]

        print(f"🔍 Checking {len(columns_to_add)} columns...")

        for column_name, column_type in columns_to_add:
            try:
                # Check if column exists first
                cur.execute("""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name='users' AND column_name=%s;
                """, (column_name,))

                result = cur.fetchone()
                if result is None:
                    # Column doesn't exist, add it
                    print(f"➕ Adding missing column: {column_name}")
                    cur.execute(f"ALTER TABLE users ADD COLUMN {column_name} {column_type};")
                    conn.commit()
                    print(f"✅ Added column: {column_name}")
                else:
                    print(f"✓ Column exists: {column_name}")
            except Exception as col_error:
                conn.rollback()
                print(f"⚠️ Column {column_name} error: {col_error}")
                import traceback
                print(traceback.format_exc())

        conn.close()
        print("✅ PostgreSQL: users table ready.")
    except Exception as e:
        print(f"❌ Users table init error: {e}")
        import traceback
        print(traceback.format_exc())

# Initialize users table
init_users_table()

@app.route("/api/signup", methods=["POST"])
def signup():
    """Create a new user account"""
    try:
        data = request.json
        email = data.get('email')
        name = data.get('name')
        password = data.get('password')

        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400

        # Hash password
        password_hash = hash_password(password)

        # Insert user into database
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()

        try:
            cur.execute("""
                INSERT INTO users (email, name, password_hash, subscription_status)
                VALUES (%s, %s, %s, 'free')
                RETURNING id
            """, (email, name, password_hash))
            user_id = cur.fetchone()[0]
            conn.commit()

            app.logger.info(f"✅ New user created: {email} (ID: {user_id})")

            return jsonify({
                'success': True,
                'message': 'Account created successfully'
            }), 201

        except psycopg2.IntegrityError:
            conn.rollback()
            return jsonify({'error': 'Email already exists'}), 409
        finally:
            conn.close()

    except Exception as e:
        app.logger.error(f"❌ Signup error: {e}\n{traceback.format_exc()}")
        return jsonify({'error': 'Signup failed'}), 500

@app.route("/api/login", methods=["POST"])
def login():
    """Authenticate user and return JWT token"""
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400

        # Get user from database
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute("""
            SELECT id, email, name, password_hash, subscription_status, stripe_customer_id
            FROM users WHERE email = %s
        """, (email,))
        user = cur.fetchone()
        conn.close()

        if not user:
            return jsonify({'error': 'Invalid email or password'}), 401

        user_id, user_email, name, password_hash, subscription_status, stripe_customer_id = user

        # Verify password
        if not verify_password(password, password_hash):
            return jsonify({'error': 'Invalid email or password'}), 401

        # Create JWT token
        token = create_token(user_id, user_email)

        app.logger.info(f"✅ User logged in: {email}")

        return jsonify({
            'success': True,
            'token': token,
            'user': {
                'id': user_id,
                'email': user_email,
                'name': name,
                'subscription_status': subscription_status,
                'stripe_customer_id': stripe_customer_id
            }
        }), 200

    except Exception as e:
        app.logger.error(f"❌ Login error: {e}\n{traceback.format_exc()}")
        return jsonify({'error': 'Login failed'}), 500

@app.route("/api/create-subscription", methods=["POST"])
def create_subscription():
    """Create Stripe subscription for user"""
    try:
        data = request.json
        email = data.get('email')
        name = data.get('name')
        payment_method_id = data.get('paymentMethodId')
        plan = data.get('plan', 'pro')

        if not email or not payment_method_id:
            return jsonify({'error': 'Missing required fields'}), 400

        # Create or get Stripe customer
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute("SELECT stripe_customer_id FROM users WHERE email = %s", (email,))
        result = cur.fetchone()

        if result and result[0]:
            customer_id = result[0]
            customer = stripe.Customer.retrieve(customer_id)
        else:
            customer = stripe.Customer.create(
                email=email,
                name=name,
                payment_method=payment_method_id,
                invoice_settings={'default_payment_method': payment_method_id}
            )
            customer_id = customer.id

        # Create subscription with 7-day trial - $4.99/month
        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{'price': 'price_1TCOih9LWKaKRffVWuR3bQin'}],  # $4.99/month
            trial_period_days=7,
            expand=['latest_invoice.payment_intent']
        )

        # Calculate trial end date
        trial_ends_at = datetime.fromtimestamp(subscription.trial_end)

        # Update or insert user
        try:
            cur.execute("""
                INSERT INTO users (email, name, stripe_customer_id, stripe_subscription_id, subscription_status, trial_ends_at)
                VALUES (%s, %s, %s, %s, 'trialing', %s)
                ON CONFLICT (email)
                DO UPDATE SET
                    stripe_customer_id = EXCLUDED.stripe_customer_id,
                    stripe_subscription_id = EXCLUDED.stripe_subscription_id,
                    subscription_status = EXCLUDED.subscription_status,
                    trial_ends_at = EXCLUDED.trial_ends_at
                RETURNING id
            """, (email, name, customer_id, subscription.id, trial_ends_at))
            user_id = cur.fetchone()[0]
            conn.commit()

            # Send welcome email
            send_access_key_email(email, customer_id)

            # Create JWT token
            token = create_token(user_id, email)

            app.logger.info(f"✅ Subscription created for {email}: {subscription.id}")

            return jsonify({
                'success': True,
                'token': token,
                'user': {
                    'id': user_id,
                    'email': email,
                    'name': name,
                    'subscription_status': 'trialing',
                    'stripe_customer_id': customer_id,
                    'trial_ends_at': trial_ends_at.isoformat()
                }
            }), 200

        except Exception as db_error:
            conn.rollback()
            raise db_error
        finally:
            conn.close()

    except stripe.error.CardError as e:
        app.logger.error(f"❌ Card error: {e}")
        return jsonify({'error': 'Card was declined'}), 400
    except Exception as e:
        app.logger.error(f"❌ Subscription creation error: {e}\n{traceback.format_exc()}")
        return jsonify({'error': 'Subscription creation failed'}), 500

@app.route("/api/me", methods=["GET"])
@token_required
def get_current_user():
    """Get current user info (protected route)"""
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute("""
            SELECT id, email, name, subscription_status, stripe_customer_id, trial_ends_at, created_at
            FROM users WHERE id = %s
        """, (request.user_id,))
        user = cur.fetchone()
        conn.close()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        user_id, email, name, subscription_status, stripe_customer_id, trial_ends_at, created_at = user

        return jsonify({
            'id': user_id,
            'email': email,
            'name': name,
            'subscription_status': subscription_status,
            'stripe_customer_id': stripe_customer_id,
            'trial_ends_at': trial_ends_at.isoformat() if trial_ends_at else None,
            'created_at': created_at.isoformat()
        }), 200

    except Exception as e:
        app.logger.error(f"❌ Get user error: {e}\n{traceback.format_exc()}")
        return jsonify({'error': 'Failed to get user info'}), 500

@app.route("/api/create-portal-session", methods=["POST"])
@token_required
def create_portal_session():
    """Create a Stripe Customer Portal session for managing subscription"""
    try:
        # Get user's stripe_customer_id
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute("""
            SELECT stripe_customer_id FROM users WHERE id = %s
        """, (request.user_id,))
        result = cur.fetchone()
        conn.close()

        if not result or not result[0]:
            return jsonify({'error': 'No active subscription found'}), 404

        stripe_customer_id = result[0]

        # Create Stripe Customer Portal session
        session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url='https://unclephilburt.github.io/studyflowwebsite/dashboard.html'
        )

        return jsonify({'url': session.url}), 200

    except Exception as e:
        app.logger.error(f"❌ Create portal session error: {e}\n{traceback.format_exc()}")
        return jsonify({'error': 'Failed to create portal session'}), 500

# ============================================================================
# END USER AUTHENTICATION & SUBSCRIPTION ROUTES
# ============================================================================


@app.route("/api/process", methods=["POST"])
@token_required
def process_data():
    try:
        # Check rate limit for free users
        can_proceed, remaining = check_question_limit(request.user_id)
        if not can_proceed:
            debug_log(f"❌ Rate limit exceeded for user {request.user_id}")
            return jsonify({
                "error": "Daily question limit exceeded",
                "message": "Free users are limited to 10 questions per day. Upgrade to Pro for unlimited questions!",
                "limit_exceeded": True
            }), 429

        debug_log(f"✅ Rate limit check passed. Remaining questions: {remaining if remaining >= 0 else 'unlimited'}")

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
            
            if send_access_key_email(email, cust_id):
                app.logger.info(f"✅ Access key emailed to {email}")
            else:
                app.logger.error(f"❌ Could not email access key to {email}")

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
        templates_dir = os.path.join(os.path.dirname(__file__), "static", "button_templates")
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
        templates_dir = os.path.join(os.path.dirname(__file__), "static", "button_templates")
        return send_from_directory(templates_dir, filename)
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




# ============ TEXT-ONLY ANSWER ENDPOINT (CHEAP) ============
@app.route("/api/answer", methods=["POST"])
@token_required
def answer_question():
    """
    Answer a quiz question using text only (no image). Uses OpenAI API.
    MUCH cheaper than Vision API - use this when OCR extraction works.

    Expects JSON:
    {
        "question": "What is the capital of France?",
        "answers": ["London", "Paris", "Berlin", "Madrid"]
    }

    Returns:
    {
        "correct_answer_index": 2,
        "correct_answer_text": "Paris",
        "confidence": "high",
        "reasoning": "Paris is the capital..."
    }
    """
    try:
        # Check rate limit for free users
        can_proceed, remaining = check_question_limit(request.user_id)
        if not can_proceed:
            debug_log(f"❌ Rate limit exceeded for user {request.user_id}")
            return jsonify({
                "error": "Daily question limit exceeded",
                "message": "Free users are limited to 10 questions per day. Upgrade to Pro for unlimited questions!",
                "limit_exceeded": True
            }), 429

        debug_log(f"✅ Rate limit check passed. Remaining questions: {remaining if remaining >= 0 else 'unlimited'}")

        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON provided"}), 400

        question = data.get("question", "")
        answers = data.get("answers", [])
        model = data.get("model", "gemini-2.5-flash")  # Get model from request, default to 2.5 Flash

        if not question or not answers:
            return jsonify({"error": "Missing question or answers"}), 400

        # Format answers for the prompt
        answers_text = "\n".join(f"{i+1}. {a}" for i, a in enumerate(answers))

        prompt = f"""You are answering a quiz question. Analyze carefully and select the correct answer.

Question: {question}

Answer options:
{answers_text}

Return a JSON object with this EXACT structure:
{{
    "correct_answer_index": <number 1-{len(answers)}>,
    "correct_answer_text": "<exact text of correct answer>",
    "confidence": "high/medium/low",
    "reasoning": "<brief explanation why this is correct>"
}}

RULES:
- correct_answer_index is 1-based (1, 2, 3, etc.)
- Return ONLY valid JSON, no other text"""

        # Use OpenAI API (gpt-4o-mini for speed/cost, gpt-4o for accuracy)
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Use model name directly (extension sends gpt-4o-mini or gpt-4o)
        openai_model = model if model in ["gpt-4o-mini", "gpt-4o"] else "gpt-4o-mini"

        answers_text = "\n".join(f"{i+1}. {a}" for i, a in enumerate(answers))

        prompt = f"""Answer this quiz question and return ONLY a JSON object.

Question: {question}

Options:
{answers_text}

Return this exact JSON format:
{{
    "correct_answer_index": <number 1-{len(answers)}>,
    "correct_answer_text": "<answer text>",
    "confidence": "high",
    "reasoning": "<brief explanation>"
}}

Return ONLY valid JSON, no markdown, no other text."""

        response = client.chat.completions.create(
            model=openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            response_format={"type": "json_object"}
        )

        result = json.loads(response.choices[0].message.content)

        if not result or not result.get('correct_answer_index'):
            return jsonify({"error": "AI processing failed"}), 500

        debug_log(f"TEXT API (OpenAI {openai_model}): Answer={result.get('correct_answer_index')}, Confidence={result.get('confidence')}")
        return jsonify(result), 200

    except json.JSONDecodeError as e:
        debug_log(f"TEXT API JSON parse error: {e}")
        return jsonify({"error": "JSON parse failed"}), 500
    except Exception as e:
        debug_log(f"TEXT API error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ============ ESSAY ANSWER ENDPOINT ============
@app.route("/api/essay", methods=["POST"])
@token_required
def essay_answer():
    """
    Generate an essay answer for a short-answer or essay question.

    Expects JSON:
    {
        "question": "Explain the process of photosynthesis."
    }

    Returns:
    {
        "essay_answer": "Photosynthesis is the process by which..."
    }
    """
    try:
        # Check rate limit for free users
        can_proceed, remaining = check_question_limit(request.user_id)
        if not can_proceed:
            debug_log(f"❌ Rate limit exceeded for user {request.user_id}")
            return jsonify({
                "error": "Daily question limit exceeded",
                "message": "Free users are limited to 10 questions per day. Upgrade to Pro for unlimited questions!",
                "limit_exceeded": True
            }), 429

        debug_log(f"✅ Rate limit check passed. Remaining questions: {remaining if remaining >= 0 else 'unlimited'}")

        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON provided"}), 400

        question = data.get("question", "")
        model = data.get("model", "gemini-2.5-flash")  # Get model from request, default to 2.5 Flash

        if not question:
            return jsonify({"error": "Missing question"}), 400

        prompt = f"""You are answering a quiz question that requires a text response (essay, short answer, or fill-in-the-blank).

Question: {question}

Provide an accurate answer. Follow these rules:
- For fill-in-the-blank questions (asking for a single word/phrase/number): Give ONLY the answer, no extra text
- For short answer questions: Provide 2-5 complete sentences
- For essay questions: Provide 1-3 well-structured paragraphs
- Be factually accurate and direct
- Use a natural, student-like tone
- If the question asks for a definition, name, date, or specific term, provide just that without elaboration

Return ONLY the answer text, nothing else."""

        # Use OpenAI API for essay generation
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Use model name directly (extension sends gpt-4o-mini or gpt-4o)
        openai_model = model if model in ["gpt-4o-mini", "gpt-4o"] else "gpt-4o-mini"

        response = client.chat.completions.create(
            model=openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=500
        )

        essay_answer = response.choices[0].message.content.strip()

        if not essay_answer:
            return jsonify({"error": "AI processing failed"}), 500

        debug_log(f"ESSAY API (OpenAI {openai_model}): Generated {len(essay_answer)} characters")

        return jsonify({"essay_answer": essay_answer}), 200

    except Exception as e:
        debug_log(f"ESSAY API error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ============ VISION API ENDPOINT ============
@app.route("/api/send-download-link", methods=["POST"])
def send_download_link():
    """Send download link email to mobile users"""
    try:
        data = request.get_json()
        email = data.get('email')

        if not email:
            return jsonify({'error': 'Email is required'}), 400

        # Send email using SendGrid
        message = Mail(
            from_email=Email("info@studyflowsuite.com", "StudyFlow Suite"),
            to_emails=email,
            subject="StudyFlow Download Link - Open on Desktop",
            html_content="""
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2 style="color: #667eea;">Open StudyFlow on Your Computer</h2>
                    <p>You visited StudyFlow on your mobile device, but our Chrome extension only works on desktop computers.</p>
                    <p style="margin: 30px 0;">
                        <a href="https://unclephilburt.github.io/studyflowwebsite/"
                           style="display: inline-block; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                                  color: white; padding: 15px 30px; text-decoration: none; border-radius: 8px;
                                  font-weight: bold;">
                            Open on Desktop
                        </a>
                    </p>
                    <h3 style="color: #1e293b;">Requirements:</h3>
                    <ul style="line-height: 1.8;">
                        <li>✅ Desktop or laptop computer</li>
                        <li>✅ Chrome browser</li>
                        <li>✅ Follow the installation guide on the website</li>
                    </ul>
                    <p style="margin-top: 30px; color: #64748b; font-size: 14px;">
                        Questions? Visit our <a href="https://unclephilburt.github.io/studyflowwebsite/docs.html" style="color: #667eea;">FAQ page</a>.
                    </p>
                    <hr style="margin: 30px 0; border: none; border-top: 1px solid #e2e8f0;">
                    <p style="color: #94a3b8; font-size: 12px; text-align: center;">
                        StudyFlow Suite - AI-Powered Quiz Automation<br>
                        <a href="https://unclephilburt.github.io/studyflowwebsite/" style="color: #667eea;">unclephilburt.github.io/studyflowwebsite</a>
                    </p>
                </div>
            """
        )

        # Make sure sandbox is off
        message.mail_settings = MailSettings(sandbox_mode=SandBoxMode(enable=False))

        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        response = sg.send(message)

        app.logger.info(f"✅ Download link sent to {email}")
        return jsonify({'success': True, 'message': 'Email sent successfully'}), 200

    except Exception as e:
        app.logger.error(f"❌ Error sending download link: {e}")
        return jsonify({'error': 'Failed to send email'}), 500


@app.route("/api/vision", methods=["POST"])
def vision_analyze():
    """
    Analyze a screenshot using GPT-4o Vision.
    Expects JSON with 'image' field containing base64-encoded PNG.
    Returns question, answers, correct answer, and button text.
    """
    try:
        data = request.get_json()
        if not data or 'image' not in data:
            return jsonify({"error": "No image provided"}), 400

        image_base64 = data['image']

        # Use OpenAI client (v1.0+ style)
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        prompt = """Analyze this screenshot of a quiz/test interface.

Your task:
1. Find the quiz QUESTION being asked
2. Find ALL answer options (usually 2-4 options)
3. Determine which answer is CORRECT
4. Identify the Submit/Next button
5. PROVIDE CLICK COORDINATES for the correct answer and the button

Return a JSON object with this EXACT structure:
{
    "question": "the full question text",
    "answers": [
        {"index": 1, "text": "first answer option text exactly as shown"},
        {"index": 2, "text": "second answer option text exactly as shown"},
        {"index": 3, "text": "third answer option text exactly as shown"},
        {"index": 4, "text": "fourth answer option text exactly as shown"}
    ],
    "correct_answer_index": 2,
    "correct_answer_text": "the exact text of the correct answer",
    "answer_click_x": 500,
    "answer_click_y": 300,
    "button_text": "Submit or Next or Continue - exact text shown",
    "button_click_x": 800,
    "button_click_y": 450,
    "confidence": "high/medium/low",
    "reasoning": "Brief explanation why this answer is correct"
}

CRITICAL RULES:
- correct_answer_index is 1-based (1, 2, 3, or 4)
- answer_click_x and answer_click_y should be the CENTER of the correct answer option (where to click)
- button_click_x and button_click_y should be the CENTER of the Submit/Next button
- Coordinates are in pixels from top-left (0,0) of the image
- Look for radio buttons or checkboxes next to answers - provide coordinates there
- If no quiz visible, set question to null
- Return ONLY valid JSON, no other text"""

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}",
                                "detail": "high"
                            }
                        }
                    ]
                }
            ],
            max_tokens=1000,
            temperature=0.1
        )

        response_text = response.choices[0].message.content.strip()
        debug_log(f"📨 Vision API response received ({len(response_text)} chars)")

        # Parse JSON - handle markdown code blocks
        if "```" in response_text:
            lines = response_text.split("\n")
            json_lines = []
            in_json = False
            for line in lines:
                if line.startswith("```json") or line.startswith("```"):
                    in_json = not in_json
                    continue
                if in_json:
                    json_lines.append(line)
            response_text = "\n".join(json_lines)

        result = json.loads(response_text)
        return jsonify(result), 200

    except json.JSONDecodeError as e:
        debug_log(f"❌ Vision JSON parse error: {e}")
        return jsonify({"error": "JSON parse failed", "raw": response_text}), 500
    except Exception as e:
        debug_log(f"❌ Vision API error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    try:
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port)
    except Exception as e:
        debug_log(f"🔥 Server startup error: {e}\n{traceback.format_exc()}")
