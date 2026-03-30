"""StudyFlow Suite Backend - Flask API Server"""

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
import uuid
import requests
import stripe
import google.generativeai as genai


from StudyFlow.backend.image_processing import preprocess_image
from StudyFlow.config import TESSERACT_PATH
from StudyFlow.logging_utils import debug_log
from StudyFlow.backend.submit_button_storage import register_submit_button_upload
from StudyFlow.backend.tasks import process_question_async, celery_app
from StudyFlow.backend import tasks  # registers the Celery task
from StudyFlow.backend.supabase_auth import supabase_auth_required, account_not_frozen  # Supabase Auth decorators
from StudyFlow.backend.supabase_client import supabase  # Supabase client for database operations

BACKEND_URL = os.environ.get("BACKEND_URL", "https://studyflowsuite.onrender.com")

stripe.api_key = os.environ['STRIPE_SECRET_KEY']
WEBHOOK_SECRET    = os.environ['STRIPE_WEBHOOK_SECRET']

BREVO_API_KEY = os.environ.get("BREVO_API_KEY")
if not BREVO_API_KEY:
    raise RuntimeError("Missing BREVO_API_KEY environment variable")

# Brevo API helper function using requests
def send_brevo_email(to_email, to_name, subject, html_content, text_content=None, sender_email="info@studyflowsuite.com", sender_name="StudyFlow Suite"):
    """Send email via Brevo REST API"""
    url = "https://api.brevo.com/v3/smtp/email"

    headers = {
        "accept": "application/json",
        "api-key": BREVO_API_KEY,
        "content-type": "application/json"
    }

    payload = {
        "sender": {"email": sender_email, "name": sender_name},
        "to": [{"email": to_email, "name": to_name}] if to_name else [{"email": to_email}],
        "subject": subject,
        "htmlContent": html_content
    }

    if text_content:
        payload["textContent"] = text_content

    response = requests.post(url, json=payload, headers=headers)
    return response

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
CORS(app,
     resources={r"/api/*": {"origins": [
         "https://unclephilburt.github.io",
         "https://studyflowsuite.com",
         "https://www.studyflowsuite.com",
         "http://studyflowsuite.com",
         "http://www.studyflowsuite.com",
         "http://localhost:*",
         "http://127.0.0.1:*"
     ]}, r"/admin/*": {"origins": [
         "https://unclephilburt.github.io",
         "https://studyflowsuite.com",
         "https://www.studyflowsuite.com",
         "http://studyflowsuite.com",
         "http://www.studyflowsuite.com",
         "http://localhost:*",
         "http://127.0.0.1:*"
     ]}},
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
     supports_credentials=True,
     expose_headers=["Content-Type", "Authorization"]
)

# ============ DMCA EMAIL NOTIFICATIONS ============

def send_dmca_report_notification_to_admin(takedown_id: str, note_filename: str, reporter_email: str, reason: str) -> bool:
    """Notify admin when new DMCA report is submitted"""
    admin_email = os.getenv("ADMIN_EMAIL", "info@studyflowsuite.com")

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #dc2626;">New DMCA Takedown Report</h2>
        <p>A copyright infringement report has been submitted and requires your review.</p>

        <div style="background: #f3f4f6; padding: 16px; border-radius: 8px; margin: 20px 0;">
            <p><strong>Note File:</strong> {note_filename}</p>
            <p><strong>Reporter:</strong> {reporter_email}</p>
            <p><strong>Reason:</strong></p>
            <p style="margin-left: 16px; font-style: italic;">{reason}</p>
        </div>

        <p><strong>Next Steps:</strong></p>
        <ol>
            <li>Review the report in Supabase dashboard</li>
            <li>Verify the claim is legitimate</li>
            <li>Process with admin endpoint:</li>
        </ol>

        <pre style="background: #1f2937; color: #10b981; padding: 12px; border-radius: 4px; font-size: 12px; overflow-x: auto;">
POST https://studyflowsuite.onrender.com/api/dmca/process/{takedown_id}
{{
  "admin_key": "YOUR_ADMIN_KEY",
  "action": "approve"  // or "reject"
}}
        </pre>

        <p style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px;">
            Legal Requirement: DMCA Safe Harbor requires responding to takedown requests within a reasonable timeframe (typically 24-48 hours).
        </p>
    </div>
    """

    plain_text = f"""
New DMCA Takedown Report

Note File: {note_filename}
Reporter: {reporter_email}
Reason: {reason}

Review this report in your Supabase dashboard and process using the admin endpoint.

Legal Requirement: DMCA Safe Harbor requires responding within 24-48 hours.
    """

    try:
        response = send_brevo_email(
            to_email=admin_email,
            to_name=None,
            subject=f"[DMCA] New Takedown Report - {note_filename}",
            html_content=html_content,
            text_content=plain_text,
            sender_name="StudyFlow DMCA System"
        )

        if response.status_code in (200, 201):
            app.logger.info("DMCA admin notification sent successfully")
            return True
        else:
            app.logger.error(f"Failed to send DMCA admin notification: {response.text}")
            return False
    except Exception as e:
        app.logger.error(f"Failed to send DMCA admin notification: {e}")
        return False


def send_dmca_strike_notification_to_user(user_email: str, user_name: str, strike_count: int, note_filename: str, is_permanent_ban: bool) -> bool:
    """Notify user when they receive a DMCA strike"""

    if is_permanent_ban:
        subject = "Account Suspended - 3 DMCA Strikes"
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #dc2626;">Account Suspended</h2>
            <p>Hello {user_name},</p>

            <p>Your StudyFlow account has been <strong>permanently suspended</strong> from Good Standing privileges due to repeated copyright violations.</p>

            <div style="background: #fee2e2; border-left: 4px solid #dc2626; padding: 16px; margin: 20px 0;">
                <p style="margin: 0;"><strong>Strike Count: 3/3 (PERMANENT BAN)</strong></p>
                <p style="margin: 8px 0 0 0;">Most recent violation: {note_filename}</p>
            </div>

            <p><strong>What this means:</strong></p>
            <ul>
                <li>You can NO LONGER download notes from StudyFlow</li>
                <li>This suspension is PERMANENT and cannot be appealed</li>
                <li>Uploading new notes will NOT restore your access</li>
            </ul>

            <p><strong>Why this happened:</strong></p>
            <p>You uploaded copyrighted material (lecture slides, textbooks, etc.) owned by professors or publishers. This violates copyright law and our Terms of Service.</p>

            <p style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px;">
                StudyFlow maintains a Three-Strikes Policy in compliance with DMCA Safe Harbor requirements. Repeat copyright infringers are permanently banned from the platform.
            </p>
        </div>
        """
    else:
        subject = f"DMCA Strike {strike_count}/3 - Warning"
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #f59e0b;">Copyright Strike Warning</h2>
            <p>Hello {user_name},</p>

            <p>You have received a copyright strike for uploading infringing content to StudyFlow.</p>

            <div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 16px; margin: 20px 0;">
                <p style="margin: 0;"><strong>Strike Count: {strike_count}/3</strong></p>
                <p style="margin: 8px 0 0 0;">File removed: {note_filename}</p>
            </div>

            <p><strong>What happened:</strong></p>
            <p>A copyright owner (likely a professor or publisher) reported that your uploaded file contained their copyrighted material.</p>

            <p><strong>What this means:</strong></p>
            <ul>
                <li>Your file has been removed from public access</li>
                <li>{'One more strike and you will be PERMANENTLY BANNED' if strike_count == 2 else 'You have 2 strikes remaining before permanent ban'}</li>
                <li>You currently maintain Good Standing (if you have recent uploads)</li>
            </ul>

            <p><strong>How to avoid future strikes:</strong></p>
            <ul>
                <li>Only upload YOUR OWN notes that you personally wrote</li>
                <li>Do NOT upload professor's lecture slides or PowerPoints</li>
                <li>Do NOT upload textbook pages or publisher materials</li>
                <li>Do NOT upload copyrighted exam/quiz materials</li>
            </ul>

            <p style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px;">
                <strong>Three-Strikes Policy:</strong> Strike 1 = Warning. Strike 2 = Final Warning. Strike 3 = Permanent ban from downloading any notes.
            </p>
        </div>
        """

    try:
        response = send_brevo_email(
            to_email=user_email,
            to_name=user_name,
            subject=subject,
            html_content=html_content,
            sender_name="StudyFlow Legal"
        )

        if response.status_code in (200, 201):
            app.logger.info("DMCA strike notification sent to user successfully")
            return True
        else:
            app.logger.error(f"Failed to send DMCA strike notification: {response.text}")
            return False
    except Exception as e:
        app.logger.error(f"Failed to send DMCA strike notification: {e}")
        return False


def send_dmca_report_confirmation_to_reporter(reporter_email: str, reporter_name: str, note_filename: str, action: str) -> bool:
    """Notify reporter when their DMCA report is processed"""

    if action == "approve":
        subject = "DMCA Report Processed - Content Removed"
        status_html = """
        <div style="background: #d1fae5; border-left: 4px solid #10b981; padding: 16px; margin: 20px 0;">
            <p style="margin: 0;"><strong>Status: APPROVED</strong></p>
            <p style="margin: 8px 0 0 0;">The infringing content has been removed and the uploader has received a copyright strike.</p>
        </div>
        """
    else:
        subject = "DMCA Report Processed - No Action Taken"
        status_html = """
        <div style="background: #fef3c7; border-left: 4px solid #f59e0b; padding: 16px; margin: 20px 0;">
            <p style="margin: 0;"><strong>Status: REJECTED</strong></p>
            <p style="margin: 8px 0 0 0;">After review, we determined the content does not constitute copyright infringement.</p>
        </div>
        """

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #1f2937;">DMCA Report Update</h2>
        <p>Hello {reporter_name or 'there'},</p>

        <p>Your copyright infringement report has been processed by our team.</p>

        {status_html}

        <p><strong>Reported File:</strong> {note_filename}</p>

        <p>Thank you for helping us maintain a legal and respectful learning community.</p>

        <p style="margin-top: 24px; padding-top: 16px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px;">
            If you have questions or wish to submit additional reports, please contact us at info@studyflowsuite.com
        </p>
    </div>
    """

    try:
        response = send_brevo_email(
            to_email=reporter_email,
            to_name=reporter_name,
            subject=subject,
            html_content=html_content,
            sender_name="StudyFlow Legal"
        )

        if response.status_code in (200, 201):
            app.logger.info("DMCA confirmation sent to reporter successfully")
            return True
        else:
            app.logger.error(f"Failed to send DMCA confirmation: {response.text}")
            return False
    except Exception as e:
        app.logger.error(f"Failed to send DMCA confirmation: {e}")
        return False


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

    try:
        app.logger.debug(f"Sending access key email to {to_email}")

        response = send_brevo_email(
            to_email=to_email,
            to_name=None,
            subject="Your StudyFlow Access Key",
            html_content=html_content,
            text_content=plain_text_content
        )

        if response.status_code in (200, 201):
            app.logger.info("Access key email sent successfully")
            return True
        else:
            app.logger.error(f"Brevo error sending access key email: {response.text}")
            return False
    except Exception as e:
        app.logger.error("Brevo error sending access key email", exc_info=e)
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
    # Everything is free for now - unlimited questions for everyone
    return True, -1  # -1 means unlimited

    # Legacy code (disabled):
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()

        # Check user's subscription status and beta status
        cur.execute("SELECT subscription_tier, created_at FROM user_profiles WHERE id = %s", (user_id,))
        user = cur.fetchone()
        if not user:
            conn.close()
            return False, 0

        subscription_status, is_beta = user

        # Beta testers (grandfathered) have unlimited questions
        if is_beta:
            conn.close()
            return True, -1  # -1 means unlimited

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
                is_beta BOOLEAN DEFAULT FALSE,
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

        # Create questions table for storing all questions and answers
        cur.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                question_text TEXT NOT NULL,
                question_type VARCHAR(50) NOT NULL,
                answers_json TEXT,
                ai_answer TEXT,
                ai_reasoning TEXT,
                correct BOOLEAN,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create notes table for NoteFlow
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                filename VARCHAR(255) NOT NULL,
                original_filename VARCHAR(255) NOT NULL,
                file_path TEXT,
                file_type VARCHAR(50),
                file_size INTEGER,
                ocr_text TEXT,
                page_count INTEGER,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Create indexes for fast lookups
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_question_hash
            ON questions(MD5(question_text));
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_questions
            ON questions(user_id, created_at);
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_question_type
            ON questions(question_type);
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_notes
            ON notes(user_id, uploaded_at DESC);
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_notes_ocr_text
            ON notes USING gin(to_tsvector('english', ocr_text));
        """)

        conn.commit()
        print("✅ Table creation/check complete")

        # Add missing columns if table already exists (compatible with older PostgreSQL)
        columns_to_add = [
            ("name", "VARCHAR(255)"),
            ("password_hash", "VARCHAR(255)"),
            ("stripe_customer_id", "VARCHAR(255)"),
            ("stripe_subscription_id", "VARCHAR(255)"),
            ("is_beta", "BOOLEAN DEFAULT FALSE"),
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
    """Create a new user account with Supabase Auth"""
    try:
        from StudyFlow.backend.supabase_auth import create_user_with_metadata

        data = request.json
        email = data.get('email')
        name = data.get('name')
        password = data.get('password')
        collective_brain_opt_in = data.get('collective_brain_opt_in', False)

        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400

        # Create user with Supabase Auth + profile
        result, error = create_user_with_metadata(
            email=email,
            password=password,
            full_name=name,
            collective_brain_opt_in=collective_brain_opt_in
        )

        if error:
            # Check if it's a duplicate email error
            if 'already registered' in error.lower() or 'already exists' in error.lower():
                return jsonify({'error': 'Email already exists'}), 409
            return jsonify({'error': error}), 400

        debug_log(f"✅ New user created: {email}")

        return jsonify({
            'success': True,
            'message': 'Account created successfully',
            'access_token': result['session'].access_token if result['session'] else None,
            'refresh_token': result['session'].refresh_token if result['session'] else None,
            'user': {
                'id': result['user'].id,
                'email': result['user'].email,
                'collective_brain_opt_in': collective_brain_opt_in
            }
        }), 201

    except Exception as e:
        debug_log(f"❌ Signup error: {e}\n{traceback.format_exc()}")
        return jsonify({'error': 'Signup failed'}), 500


@app.route("/api/login", methods=["POST"])
def login():
    """Authenticate user with Supabase Auth and return access token"""
    try:
        from StudyFlow.backend.supabase_auth import sign_in_user
        from StudyFlow.backend.supabase_client import get_user_profile

        data = request.json
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({'error': 'Email and password are required'}), 400

        # Sign in with Supabase Auth
        result, error = sign_in_user(email, password)

        if error:
            return jsonify({'error': error}), 401

        # Get user profile for additional info
        user_profile = get_user_profile(result['user'].id)

        debug_log(f"✅ User logged in: {email}")

        return jsonify({
            'success': True,
            'access_token': result['access_token'],
            'refresh_token': result['refresh_token'],
            'expires_in': result['expires_in'],
            'user': {
                'id': result['user'].id,
                'email': result['user'].email,
                'full_name': user_profile.get('full_name') if user_profile else None,
                'subscription_tier': user_profile.get('subscription_tier') if user_profile else 'free',
                'stripe_customer_id': user_profile.get('stripe_customer_id') if user_profile else None,
                'collective_brain_opt_in': user_profile.get('collective_brain_opt_in') if user_profile else False
            }
        }), 200

    except Exception as e:
        debug_log(f"❌ Login error: {e}\n{traceback.format_exc()}")
        return jsonify({'error': 'Login failed'}), 500


@app.route("/api/refresh", methods=["POST"])
def refresh_token():
    """Refresh an expired access token"""
    try:
        from StudyFlow.backend.supabase_auth import refresh_access_token

        data = request.json
        refresh_token_str = data.get('refresh_token')

        if not refresh_token_str:
            return jsonify({'error': 'Refresh token is required'}), 400

        result, error = refresh_access_token(refresh_token_str)

        if error:
            return jsonify({'error': error}), 401

        return jsonify({
            'success': True,
            'access_token': result['access_token'],
            'refresh_token': result['refresh_token'],
            'expires_in': result['expires_in']
        }), 200

    except Exception as e:
        debug_log(f"❌ Refresh token error: {e}\n{traceback.format_exc()}")
        return jsonify({'error': 'Failed to refresh token'}), 500


@app.route("/api/logout", methods=["POST"])
def logout():
    """Sign out user (invalidate session)"""
    try:
        from StudyFlow.backend.supabase_auth import sign_out_user

        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        if not auth_header or not auth_header.startswith('Bearer '):
            return jsonify({'error': 'Missing or invalid Authorization header'}), 401

        token = auth_header[7:]  # Remove 'Bearer ' prefix

        success, error = sign_out_user(token)

        if error:
            return jsonify({'error': error}), 400

        return jsonify({'success': True, 'message': 'Logged out successfully'}), 200

    except Exception as e:
        debug_log(f"❌ Logout error: {e}\n{traceback.format_exc()}")
        return jsonify({'error': 'Logout failed'}), 500


@app.route("/api/reset-password", methods=["POST"])
def reset_password():
    """Send password reset email"""
    try:
        from StudyFlow.backend.supabase_auth import reset_password_email

        data = request.json
        email = data.get('email')

        if not email:
            return jsonify({'error': 'Email is required'}), 400

        success, error = reset_password_email(email)

        if error:
            return jsonify({'error': error}), 400

        return jsonify({
            'success': True,
            'message': 'Password reset email sent. Check your inbox.'
        }), 200

    except Exception as e:
        debug_log(f"❌ Reset password error: {e}\n{traceback.format_exc()}")
        return jsonify({'error': 'Failed to send reset email'}), 500

@app.route("/api/create-subscription", methods=["POST"])
def create_subscription():
    """Create Stripe subscription for user (with Supabase)"""
    from StudyFlow.backend.supabase_client import supabase
    from datetime import datetime

    try:
        data = request.json
        email = data.get('email')
        name = data.get('name')
        payment_method_id = data.get('paymentMethodId')
        plan = data.get('plan', 'pro')

        if not email or not payment_method_id:
            return jsonify({'error': 'Missing required fields'}), 400

        # Check if user already exists in Supabase
        result = supabase.table("user_profiles").select("id, stripe_customer_id").eq("email", email).execute()

        user_id = None
        customer_id = None

        if result.data and len(result.data) > 0:
            # User exists
            user_id = result.data[0]['id']
            customer_id = result.data[0].get('stripe_customer_id')
            debug_log(f"Existing user found: {user_id}")
        else:
            # Create new Supabase auth user (auto-creates user_profile via trigger)
            import secrets
            temp_password = secrets.token_urlsafe(32)

            auth_result = supabase.auth.sign_up({
                "email": email,
                "password": temp_password,
                "options": {
                    "data": {
                        "full_name": name
                    }
                }
            })

            if auth_result.user:
                user_id = auth_result.user.id
                debug_log(f"New user created: {user_id}")
            else:
                raise Exception("Failed to create user account")

        # Create or retrieve Stripe customer
        if customer_id:
            customer = stripe.Customer.retrieve(customer_id)
        else:
            customer = stripe.Customer.create(
                email=email,
                name=name,
                payment_method=payment_method_id,
                invoice_settings={'default_payment_method': payment_method_id},
                metadata={'user_id': user_id}
            )
            customer_id = customer.id

        # Create subscription with 7-day trial - $4.99/month
        subscription = stripe.Subscription.create(
            customer=customer_id,
            items=[{'price': 'price_1TCOih9LWKaKRffVWuR3bQin'}],  # $4.99/month
            trial_period_days=7,
            expand=['latest_invoice.payment_intent'],
            metadata={'user_id': user_id}
        )

        # Calculate trial end date
        trial_ends_at = datetime.fromtimestamp(subscription.trial_end).isoformat()

        # Update user_profile with subscription info
        supabase.table("user_profiles").update({
            "stripe_customer_id": customer_id,
            "stripe_subscription_id": subscription.id,
            "subscription_tier": "pro",
            "subscription_status": "trialing",
            "full_name": name
        }).eq("id", user_id).execute()

        # Send welcome email
        send_access_key_email(email, customer_id)

        # Create JWT token for website auth
        token = create_token(user_id, email)

        debug_log(f"✅ Subscription created for {email}: {subscription.id}")

        return jsonify({
            'success': True,
            'token': token,
            'user': {
                'id': user_id,
                'email': email,
                'name': name,
                'subscription_status': 'trialing',
                'subscription_tier': 'pro',
                'stripe_customer_id': customer_id,
                'trial_ends_at': trial_ends_at
            }
        }), 200

    except stripe.error.CardError as e:
        debug_log(f"❌ Card error: {e}")
        return jsonify({'error': 'Card was declined'}), 400
    except Exception as e:
        debug_log(f"❌ Subscription creation error: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500

@app.route("/api/me", methods=["GET"])
@supabase_auth_required
def get_me():
    """Get current user info (protected route)"""
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute("""
            SELECT id, email, full_name, subscription_tier, stripe_customer_id, NULL as trial_ends_at, created_at, FALSE as is_beta
            FROM user_profiles WHERE id = %s
        """, (request.user_id,))
        user = cur.fetchone()
        conn.close()

        if not user:
            return jsonify({'error': 'User not found'}), 404

        user_id, email, name, subscription_status, stripe_customer_id, trial_ends_at, created_at, is_beta = user

        return jsonify({
            'id': user_id,
            'email': email,
            'name': name,
            'subscription_status': subscription_status,
            'stripe_customer_id': stripe_customer_id,
            'trial_ends_at': trial_ends_at.isoformat() if trial_ends_at else None,
            'is_beta': is_beta if is_beta is not None else False,
            'created_at': created_at.isoformat()
        }), 200

    except Exception as e:
        app.logger.error(f"❌ Get user error: {e}\n{traceback.format_exc()}")
        return jsonify({'error': 'Failed to get user info'}), 500

@app.route("/api/create-portal-session", methods=["POST"])
@supabase_auth_required
def create_portal_session():
    """Create a Stripe Customer Portal session for managing subscription"""
    try:
        # Get user's stripe_customer_id
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()
        cur.execute("""
            SELECT stripe_customer_id FROM user_profiles WHERE id = %s
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

@app.route("/api/current-user", methods=["GET"])
@supabase_auth_required
def get_current_user():
    """Get current authenticated user info"""
    try:
        from StudyFlow.backend.supabase_client import get_user_profile, create_user_profile

        # Get user profile from Supabase
        profile = get_user_profile(request.user_id)

        # If profile doesn't exist, create it (handles edge case where auth exists but profile is missing)
        if not profile:
            debug_log(f"⚠️ User profile missing for {request.user_email}, creating now...")
            profile = create_user_profile(
                user_id=request.user_id,
                email=request.user_email,
                full_name=None,
                collective_brain_opt_in=False
            )

            if not profile:
                return jsonify({"error": "Failed to create user profile"}), 500

        return jsonify({
            "id": profile.get("id"),
            "email": profile.get("email"),
            "name": profile.get("full_name"),
            "subscription_status": profile.get("subscription_tier", "free"),
            "edu_verified": profile.get("edu_email_verified", False),
            "is_beta": False,  # Legacy field, always False for new users
            "created_at": profile.get("created_at")
        }), 200

    except Exception as e:
        debug_log(f"❌ Get current user error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/stats", methods=["GET"])
@supabase_auth_required
def get_user_stats():
    """Get user statistics"""
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()

        # Get user info
        cur.execute("""
            SELECT email, full_name, subscription_tier, FALSE as is_beta, created_at
            FROM user_profiles WHERE id = %s
        """, (request.user_id,))
        user = cur.fetchone()

        if not user:
            conn.close()
            return jsonify({'error': 'User not found'}), 404

        email, name, subscription_status, is_beta, created_at = user

        # Get total questions
        cur.execute("""
            SELECT COUNT(*) FROM questions WHERE user_id = %s
        """, (request.user_id,))
        total_questions = cur.fetchone()[0]

        # Get questions today
        cur.execute("""
            SELECT COUNT(*) FROM questions
            WHERE user_id = %s AND created_at >= CURRENT_DATE
        """, (request.user_id,))
        questions_today = cur.fetchone()[0]

        # Get questions this week
        cur.execute("""
            SELECT COUNT(*) FROM questions
            WHERE user_id = %s AND created_at >= CURRENT_DATE - INTERVAL '7 days'
        """, (request.user_id,))
        questions_this_week = cur.fetchone()[0]

        # Get question type breakdown
        cur.execute("""
            SELECT question_type, COUNT(*)
            FROM questions
            WHERE user_id = %s
            GROUP BY question_type
        """, (request.user_id,))
        question_types = dict(cur.fetchall())

        # Get most recent question date
        cur.execute("""
            SELECT MAX(created_at) FROM questions WHERE user_id = %s
        """, (request.user_id,))
        last_activity = cur.fetchone()[0]

        conn.close()

        # Determine tier
        tier = 'Free'
        if is_beta:
            tier = 'Beta (Pro)'
        elif subscription_status in ['active', 'trialing']:
            tier = 'Pro'

        return jsonify({
            'user': {
                'name': name,
                'email': email,
                'tier': tier,
                'created_at': created_at.isoformat() if created_at else None
            },
            'stats': {
                'total_questions': total_questions,
                'questions_today': questions_today,
                'questions_this_week': questions_this_week,
                'last_activity': last_activity.isoformat() if last_activity else None
            },
            'question_types': question_types
        }), 200

    except Exception as e:
        app.logger.error(f"❌ Get stats error: {e}\n{traceback.format_exc()}")
        return jsonify({'error': 'Failed to get stats'}), 500


@app.route("/api/user/dashboard-layout", methods=["GET"])
@supabase_auth_required
def get_dashboard_layout():
    """Get user's dashboard widget layout and canvas pan position"""
    try:
        # Use Supabase to get dashboard_layout
        result = supabase.table("user_profiles").select("dashboard_layout").eq("id", request.user_id).execute()

        if result.data and len(result.data) > 0 and result.data[0].get('dashboard_layout'):
            data = result.data[0]['dashboard_layout']
            # Handle both old format (array) and new format (object with layout + canvasPan)
            if isinstance(data, list):
                # Old format - just array of widgets
                return jsonify({'layout': data, 'canvasPan': {'x': 0, 'y': 0}}), 200
            elif isinstance(data, dict):
                # New format - object with layout and canvasPan
                return jsonify(data), 200
            else:
                # Return default
                return jsonify({
                    'layout': ['recentConversations', 'upcomingEvents', 'studyGroups'],
                    'canvasPan': {'x': 0, 'y': 0}
                }), 200
        else:
            # Return default layout
            return jsonify({
                'layout': ['recentConversations', 'upcomingEvents', 'studyGroups'],
                'canvasPan': {'x': 0, 'y': 0}
            }), 200

    except Exception as e:
        debug_log(f"❌ Get dashboard layout error: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route("/api/user/dashboard-layout", methods=["POST"])
@supabase_auth_required
def save_dashboard_layout():
    """Save user's dashboard widget layout and canvas pan position"""
    try:
        data = request.get_json()
        layout = data.get('layout', [])
        canvas_pan = data.get('canvasPan', {'x': 0, 'y': 0})

        if not isinstance(layout, list):
            return jsonify({'error': 'Layout must be an array'}), 400

        # Store as a single JSON object with both layout and canvasPan
        dashboard_data = {
            'layout': layout,
            'canvasPan': canvas_pan
        }

        # Use Supabase to update dashboard_layout
        supabase.table("user_profiles").update({
            "dashboard_layout": dashboard_data
        }).eq("id", request.user_id).execute()

        return jsonify({'success': True}), 200

    except Exception as e:
        debug_log(f"❌ Save dashboard layout error: {e}\n{traceback.format_exc()}")
        return jsonify({'error': str(e)}), 500


@app.route("/api/user/preferences", methods=["GET"])
@supabase_auth_required
def get_user_preferences():
    """Get user's preferences (theme, etc.)"""
    try:
        # Try to get preferences column, but fallback gracefully if it doesn't exist
        try:
            result = supabase.table("user_profiles").select("preferences").eq("id", request.user_id).execute()
            if result.data and len(result.data) > 0:
                preferences = result.data[0].get('preferences') or {}
                return jsonify(preferences), 200
        except Exception as column_error:
            # Column might not exist yet - return defaults
            debug_log(f"⚠️ Preferences column not found, using defaults: {column_error}")
            pass

        # Return default preferences
        return jsonify({'theme': 'default'}), 200

    except Exception as e:
        debug_log(f"❌ Get preferences error: {e}\n{traceback.format_exc()}")
        # Don't fail - return defaults
        return jsonify({'theme': 'default'}), 200


@app.route("/api/user/preferences", methods=["PATCH"])
@supabase_auth_required
def update_user_preferences():
    """Update user's preferences (theme, etc.)"""
    try:
        updates = request.get_json()

        # Try to update preferences, but gracefully handle if column doesn't exist
        try:
            # Get current preferences
            result = supabase.table("user_profiles").select("preferences").eq("id", request.user_id).execute()
            current_prefs = {}
            if result.data and len(result.data) > 0:
                current_prefs = result.data[0].get('preferences') or {}

            # Merge updates with current preferences
            current_prefs.update(updates)

            # Save back to database
            supabase.table("user_profiles").update({
                "preferences": current_prefs
            }).eq("id", request.user_id).execute()

            return jsonify({'success': True, 'preferences': current_prefs}), 200

        except Exception as db_error:
            # Column might not exist - just acknowledge the update locally
            debug_log(f"⚠️ Could not save preferences to DB (column may not exist): {db_error}")
            return jsonify({'success': True, 'preferences': updates, 'note': 'Saved locally only'}), 200

    except Exception as e:
        debug_log(f"❌ Update preferences error: {e}\n{traceback.format_exc()}")
        return jsonify({'success': True, 'preferences': {}}), 200


@app.route("/api/leaderboard", methods=["GET"])
@supabase_auth_required
def get_leaderboard():
    """Get top contributors to the Nexus (leaderboard)"""
    try:
        # Try to use the stored procedure first
        try:
            result = supabase.rpc("get_nexus_leaderboard", {
                "limit_count": 20
            }).execute()

            if result.data:
                return jsonify(result.data), 200
        except Exception as rpc_error:
            debug_log(f"RPC call failed (expected if stored procedure doesn't exist): {rpc_error}")
            # Continue to fallback logic below

        # Fallback: manually aggregate if RPC doesn't exist or returns no data
        from collections import defaultdict

        # Get all notes with user info
        notes = supabase.table("notes").select("user_id, page_count").eq("is_public", True).execute()

        # Aggregate pages by user
        user_pages = defaultdict(int)
        for note in notes.data:
            user_pages[note['user_id']] += note.get('page_count', 0)

        # Get user profiles for top contributors
        top_users = sorted(user_pages.items(), key=lambda x: x[1], reverse=True)[:20]

        leaderboard = []
        for user_id, pages in top_users:
            try:
                profile = supabase.table("user_profiles").select("username, university").eq("id", user_id).single().execute()
                if profile.data:
                    leaderboard.append({
                        "user_id": user_id,
                        "username": profile.data.get('username'),
                        "university": profile.data.get('university'),
                        "pages_contributed": pages
                    })
            except:
                pass

        return jsonify(leaderboard), 200

    except Exception as e:
        debug_log(f"❌ Leaderboard error: {e}\n{traceback.format_exc()}")
        return jsonify([]), 200


@app.route("/api/leaderboard/cited", methods=["GET"])
@supabase_auth_required
def get_most_cited_notes():
    """Get most cited notes from AI chat responses"""
    try:
        from collections import defaultdict

        # Get all AI response logs with sources
        logs = supabase.table("ai_response_logs").select("sources_used").execute()

        # Count citations per note_id
        citation_counts = defaultdict(int)
        note_details = {}  # Store first occurrence details

        for log in logs.data:
            sources = log.get('sources_used') or []
            for source in sources:
                # Each source in the array counts as one citation
                note_id = source.get('note_id')
                if note_id:
                    citation_counts[note_id] += 1
                    # Store details from first occurrence
                    if note_id not in note_details:
                        note_details[note_id] = {
                            'filename': source.get('filename'),
                            'username': source.get('contributor_username'),
                        }

        # Get full note metadata for top cited notes
        top_note_ids = sorted(citation_counts.items(), key=lambda x: x[1], reverse=True)[:50]

        cited_notes = []
        for note_id, count in top_note_ids:
            try:
                # Get note metadata
                note = supabase.table("notes").select(
                    "id, original_filename, user_id, university, course_code"
                ).eq("id", note_id).single().execute()

                if note.data:
                    # Get username if not already in note_details
                    username = note_details[note_id].get('username')
                    if not username:
                        try:
                            profile = supabase.table("user_profiles").select("username").eq("id", note.data['user_id']).single().execute()
                            username = profile.data.get('username') if profile.data else None
                        except:
                            username = None

                    cited_notes.append({
                        "note_id": note_id,
                        "filename": note.data.get('original_filename') or note_details[note_id].get('filename'),
                        "username": username,
                        "university": note.data.get('university'),
                        "course_code": note.data.get('course_code'),
                        "citation_count": count
                    })
            except:
                # Note might have been deleted, skip it
                pass

        return jsonify(cited_notes[:20]), 200

    except Exception as e:
        debug_log(f"❌ Most cited error: {e}\n{traceback.format_exc()}")
        return jsonify([]), 200


@app.route("/api/leaderboard/downloaded", methods=["GET"])
@supabase_auth_required
def get_most_downloaded_notes():
    """Get most downloaded notes"""
    try:
        # Get notes with highest download counts
        # TODO: Implement download tracking (add download_count column to notes table)

        # Get all public notes
        result = supabase.table("notes").select(
            "id, original_filename, user_id, university, course_code, page_count"
        ).eq("is_public", True).limit(50).execute()

        downloaded_notes = []
        for note in result.data:
            # Skip Wikipedia entries
            university = note.get('university', '')
            if university and 'wikipedia' in university.lower():
                continue

            # Get username
            try:
                profile = supabase.table("user_profiles").select("username").eq("id", note['user_id']).single().execute()
                username = profile.data.get('username') if profile.data else None
            except:
                username = None

            downloaded_notes.append({
                "note_id": note['id'],
                "filename": note['original_filename'],
                "username": username,
                "university": note.get('university'),
                "course_code": note.get('course_code'),
                "download_count": note.get('page_count', 0)  # Temporary: simulate downloads
            })

        # Sort by download count
        downloaded_notes.sort(key=lambda x: x['download_count'], reverse=True)

        return jsonify(downloaded_notes[:20]), 200

    except Exception as e:
        debug_log(f"❌ Most downloaded error: {e}\n{traceback.format_exc()}")
        return jsonify([]), 200


@app.route("/api/leaderboard/rising", methods=["GET"])
@supabase_auth_required
def get_rising_stars():
    """Get rising stars (new contributors from last 30 days)"""
    try:
        from datetime import datetime, timedelta

        # Get notes uploaded in last 30 days
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()

        result = supabase.table("notes").select("user_id, page_count").eq("is_public", True).gte("uploaded_at", thirty_days_ago).execute()

        # Aggregate pages by user
        from collections import defaultdict
        user_pages = defaultdict(int)
        for note in result.data:
            user_pages[note['user_id']] += note.get('page_count', 0)

        # Get top contributors
        top_users = sorted(user_pages.items(), key=lambda x: x[1], reverse=True)[:20]

        rising_stars = []
        for user_id, pages in top_users:
            try:
                profile = supabase.table("user_profiles").select("username, university").eq("id", user_id).single().execute()
                if profile.data:
                    rising_stars.append({
                        "user_id": user_id,
                        "username": profile.data.get('username'),
                        "university": profile.data.get('university'),
                        "pages_contributed": pages
                    })
            except:
                pass

        return jsonify(rising_stars), 200

    except Exception as e:
        debug_log(f"❌ Rising stars error: {e}\n{traceback.format_exc()}")
        return jsonify([]), 200


@app.route("/api/leaderboard/most-helpful", methods=["GET", "OPTIONS"])
@supabase_auth_required
def get_most_helpful_notes():
    """Get notes ranked by helpfulness votes"""
    # Handle OPTIONS preflight
    if request.method == 'OPTIONS':
        return '', 200

    try:
        from collections import defaultdict

        # Get all response ratings
        ratings = supabase.table("ai_response_ratings").select("cited_note_ids, vote").execute()

        # Calculate score for each note (upvotes - downvotes)
        note_scores = defaultdict(lambda: {"upvotes": 0, "downvotes": 0, "score": 0})

        for rating in ratings.data:
            cited_note_ids = rating.get('cited_note_ids', [])
            vote = rating.get('vote', 0)

            # Apply vote to all notes cited in that response
            for note_id in cited_note_ids:
                if vote == 1:
                    note_scores[note_id]["upvotes"] += 1
                elif vote == -1:
                    note_scores[note_id]["downvotes"] += 1
                note_scores[note_id]["score"] = note_scores[note_id]["upvotes"] - note_scores[note_id]["downvotes"]

        # Get top notes by score
        sorted_notes = sorted(note_scores.items(), key=lambda x: x[1]['score'], reverse=True)[:20]

        # Fetch note details
        helpful_notes = []
        for note_id, scores in sorted_notes:
            try:
                note = supabase.table("notes").select(
                    "id, original_filename, user_id, university, course_code"
                ).eq("id", note_id).single().execute()

                if note.data:
                    # Get username
                    profile = supabase.table("user_profiles").select("username").eq("id", note.data['user_id']).single().execute()
                    username = profile.data.get('username') if profile.data else None

                    helpful_notes.append({
                        "note_id": note_id,
                        "filename": note.data.get('original_filename'),
                        "username": username,
                        "university": note.data.get('university'),
                        "course_code": note.data.get('course_code'),
                        "helpfulness_score": scores['score'],
                        "upvotes": scores['upvotes'],
                        "downvotes": scores['downvotes']
                    })
            except:
                pass

        return jsonify(helpful_notes), 200

    except Exception as e:
        debug_log(f"❌ Most helpful notes error: {e}\n{traceback.format_exc()}")
        return jsonify([]), 200


@app.route("/api/leaderboard/universities", methods=["GET"])
@supabase_auth_required
def get_university_leaderboard():
    """Get university leaderboard - Springfield Showdown style"""
    try:
        from collections import defaultdict

        # Get list of valid universities from user_profiles (universities users have selected from dropdown)
        profiles = supabase.table("user_profiles").select("university").execute()
        valid_universities = set()
        for profile in profiles.data:
            uni = profile.get('university')
            if uni and 'wikipedia' not in uni.lower():
                valid_universities.add(uni)

        debug_log(f"[*] Valid universities from user profiles: {len(valid_universities)}")

        # Get all public notes with university info
        result = supabase.table("notes").select("university, page_count, user_id").eq("is_public", True).execute()

        # Aggregate stats by university (only valid ones)
        university_stats = defaultdict(lambda: {"total_pages": 0, "total_notes": 0, "contributors": set()})

        for note in result.data:
            university = note.get('university')
            # Only include universities that exist in user_profiles (from official dropdown)
            if university and university in valid_universities:
                university_stats[university]["total_pages"] += note.get('page_count', 0)
                university_stats[university]["total_notes"] += 1
                university_stats[university]["contributors"].add(note['user_id'])

        # Convert to list and sort by total pages
        leaderboard = []
        for university, stats in university_stats.items():
            leaderboard.append({
                "university": university,
                "total_pages": stats["total_pages"],
                "total_notes": stats["total_notes"],
                "contributor_count": len(stats["contributors"])
            })

        # Sort by total pages contributed
        leaderboard.sort(key=lambda x: x['total_pages'], reverse=True)

        return jsonify(leaderboard), 200

    except Exception as e:
        debug_log(f"❌ University leaderboard error: {e}\n{traceback.format_exc()}")
        return jsonify([]), 200


@app.route("/api/my-stats/citation-rank", methods=["GET"])
@supabase_auth_required
def get_my_citation_rank():
    """Get current user's rank by citation count"""
    try:
        from collections import defaultdict

        # Get all AI response logs with sources
        logs = supabase.table("ai_response_logs").select("sources_used").execute()

        # Count citations per note_id (and track which user owns each note)
        note_citations = defaultdict(int)
        note_owners = {}

        for log in logs.data:
            sources = log.get('sources_used') or []
            for source in sources:
                note_id = source.get('note_id')
                if note_id:
                    note_citations[note_id] += 1

        # Get note owners
        if note_citations:
            note_ids = list(note_citations.keys())
            notes = supabase.table("notes").select("id, user_id").in_("id", note_ids).execute()
            for note in notes.data:
                note_owners[note['id']] = note['user_id']

        # Aggregate citations by user
        user_citations = defaultdict(int)
        for note_id, count in note_citations.items():
            user_id = note_owners.get(note_id)
            if user_id:
                user_citations[user_id] += count

        # Sort users by citation count
        sorted_users = sorted(user_citations.items(), key=lambda x: x[1], reverse=True)

        # Find current user's rank
        my_rank = None
        my_citations = user_citations.get(request.user_id, 0)
        total_ranked_users = len(sorted_users)

        for index, (user_id, count) in enumerate(sorted_users):
            if user_id == request.user_id:
                my_rank = index + 1
                break

        # If user has no citations, they're unranked
        if my_rank is None:
            my_rank = total_ranked_users + 1 if total_ranked_users > 0 else 1

        return jsonify({
            "rank": my_rank,
            "citation_count": my_citations,
            "total_users": max(total_ranked_users, my_rank)
        }), 200

    except Exception as e:
        debug_log(f"❌ Citation rank error: {e}\n{traceback.format_exc()}")
        return jsonify({"rank": 0, "citation_count": 0, "total_users": 0}), 200


@app.route("/api/my-stats/university-rank", methods=["GET"])
@supabase_auth_required
def get_my_university_rank():
    """Get current user's university rank"""
    try:
        from collections import defaultdict

        # Get user's university
        profile = supabase.table("user_profiles").select("university").eq("id", request.user_id).single().execute()
        my_university = profile.data.get('university') if profile.data else None

        if not my_university:
            return jsonify({"rank": 0, "university": None, "total_pages": 0, "total_universities": 0}), 200

        # Get list of valid universities
        profiles = supabase.table("user_profiles").select("university").execute()
        valid_universities = set()
        for p in profiles.data:
            uni = p.get('university')
            if uni and 'wikipedia' not in uni.lower():
                valid_universities.add(uni)

        # Get all public notes with university info
        result = supabase.table("notes").select("university, page_count").eq("is_public", True).execute()

        # Aggregate stats by university
        university_pages = defaultdict(int)
        for note in result.data:
            university = note.get('university')
            if university and university in valid_universities:
                university_pages[university] += note.get('page_count', 0)

        # Sort universities by total pages
        sorted_universities = sorted(university_pages.items(), key=lambda x: x[1], reverse=True)

        # Find my university's rank
        my_rank = None
        my_pages = university_pages.get(my_university, 0)
        total_universities = len(sorted_universities)

        for index, (university, pages) in enumerate(sorted_universities):
            if university == my_university:
                my_rank = index + 1
                break

        # If university has no pages, it's unranked
        if my_rank is None:
            my_rank = total_universities + 1 if total_universities > 0 else 1

        return jsonify({
            "rank": my_rank,
            "university": my_university,
            "total_pages": my_pages,
            "total_universities": max(total_universities, my_rank)
        }), 200

    except Exception as e:
        debug_log(f"❌ University rank error: {e}\n{traceback.format_exc()}")
        return jsonify({"rank": 0, "university": None, "total_pages": 0, "total_universities": 0}), 200


# ============================================================================
# END USER AUTHENTICATION & SUBSCRIPTION ROUTES
# ============================================================================


@app.route("/api/process", methods=["POST"])
@supabase_auth_required
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
    """
    Handle Stripe webhook events for Scholar's Club subscriptions

    Events handled:
    - checkout.session.completed: User completes payment, upgrade to 'pro' tier
    - customer.subscription.updated: Subscription status changes
    - customer.subscription.deleted: Subscription canceled, downgrade to 'free' tier
    """
    from StudyFlow.backend.supabase_client import supabase

    # 1) Raw body + signature header
    payload = request.get_data()
    sig_header = request.headers.get("Stripe-Signature")

    # 2) Verify & parse
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, WEBHOOK_SECRET)
        debug_log(f"✅ Stripe webhook verified: {event['id']} → {event['type']}")
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        debug_log(f"⚠️ Webhook validation failed: {e}")
        return "", 400

    evt_type = event["type"]
    obj = event["data"]["object"]

    # 3) Handle checkout.session.completed - User just subscribed to Scholar's Club
    if evt_type == "checkout.session.completed":
        try:
            cust_id = obj["customer"]
            subscription_id = obj.get("subscription")
            user_id = obj["metadata"].get("user_id")  # From checkout session metadata

            if not user_id:
                debug_log(f"⚠️ No user_id in checkout session metadata")
                return jsonify({"received": True}), 200

            # Update user_profiles to 'pro' tier
            supabase.table("user_profiles").update({
                "subscription_tier": "pro",
                "subscription_status": "active",
                "stripe_customer_id": cust_id,
                "stripe_subscription_id": subscription_id
            }).eq("id", user_id).execute()

            debug_log(f"🎉 Scholar's Club activated for user {user_id}")

        except Exception as e:
            debug_log(f"❌ checkout.session.completed error: {e}\n{traceback.format_exc()}")
            return "", 500

    # 4) Handle customer.subscription.updated - Subscription status changed
    elif evt_type == "customer.subscription.updated":
        try:
            cust_id = obj["customer"]
            status = obj["status"]
            subscription_id = obj["id"]

            # Update subscription status in user_profiles
            supabase.table("user_profiles").update({
                "subscription_status": status,
                "stripe_subscription_id": subscription_id
            }).eq("stripe_customer_id", cust_id).execute()

            debug_log(f"🔄 Subscription updated: {cust_id} → {status}")

        except Exception as e:
            debug_log(f"❌ customer.subscription.updated error: {e}\n{traceback.format_exc()}")
            return "", 500

    # 5) Handle customer.subscription.deleted - User canceled or subscription expired
    elif evt_type == "customer.subscription.deleted":
        try:
            cust_id = obj["customer"]

            # Downgrade user back to free tier
            supabase.table("user_profiles").update({
                "subscription_tier": "free",
                "subscription_status": "canceled",
                "stripe_subscription_id": None
            }).eq("stripe_customer_id", cust_id).execute()

            debug_log(f"🗑️ Subscription canceled, user downgraded to free tier: {cust_id}")

        except Exception as e:
            debug_log(f"❌ customer.subscription.deleted error: {e}\n{traceback.format_exc()}")
            return "", 500

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
            "SELECT subscription_tier FROM user_profiles WHERE stripe_customer_id = %s",
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


@app.route("/admin/view-questions")
def view_questions():
    """Admin page to view all questions from the questions table"""
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cur = conn.cursor()

        # Get filter parameters
        user_id_filter = request.args.get('user_id', None)
        question_type_filter = request.args.get('type', None)
        limit = int(request.args.get('limit', 100))

        # Build query with filters
        query = "SELECT q.id, q.user_id, u.email, q.question_text, q.question_type, q.answers_json, q.ai_answer, q.ai_reasoning, q.created_at FROM questions q LEFT JOIN user_profiles u ON q.user_id = u.id WHERE 1=1"
        params = []

        if user_id_filter:
            query += " AND q.user_id = %s"
            params.append(int(user_id_filter))

        if question_type_filter:
            query += " AND q.question_type = %s"
            params.append(question_type_filter)

        query += " ORDER BY q.created_at DESC LIMIT %s"
        params.append(limit)

        cur.execute(query, params)
        rows = cur.fetchall()

        # Get statistics
        cur.execute("SELECT COUNT(*) FROM questions")
        total_questions = cur.fetchone()[0]

        cur.execute("SELECT question_type, COUNT(*) FROM questions GROUP BY question_type")
        type_counts = cur.fetchall()

        cur.execute("SELECT COUNT(DISTINCT user_id) FROM questions")
        unique_users = cur.fetchone()[0]

        conn.close()

        # Build HTML with stats
        stats_html = ""
        for q_type, count in type_counts:
            stats_html += f'<div class="stat-card"><h3>{count}</h3><p>{q_type.replace("_", " ").title()}</p></div>'

        # Build table rows
        rows_html = ""
        for row in rows:
            q_id, user_id, email, question_text, question_type, answers_json, ai_answer, ai_reasoning, created_at = row
            question_display = (question_text[:100] + '...') if len(question_text) > 100 else question_text
            answer_display = (ai_answer[:80] + '...') if ai_answer and len(ai_answer) > 80 else (ai_answer or 'N/A')
            timestamp_str = created_at.strftime('%Y-%m-%d %H:%M') if created_at else 'N/A'

            rows_html += f'''<tr>
                <td>{q_id}</td>
                <td><div><strong>ID {user_id}</strong></div><div class="email">{email or 'Unknown'}</div></td>
                <td><span class="badge badge-{question_type}">{question_type.replace("_", " ").title()}</span></td>
                <td class="question-text" title="{question_text}">{question_display}</td>
                <td class="answer-text" title="{ai_answer or ''}">{answer_display}</td>
                <td class="timestamp">{timestamp_str}</td>
            </tr>'''

        html = f'''<!DOCTYPE html>
<html>
<head>
    <title>Question Database</title>
    <style>
        body {{ font-family: Arial, sans-serif; background: #f4f4f4; padding: 20px; }}
        .header {{ background: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 20px; }}
        .stat-card {{ background: #667eea; color: white; padding: 15px; border-radius: 8px; text-align: center; }}
        .stat-card h3 {{ margin: 0; font-size: 32px; }}
        .stat-card p {{ margin: 5px 0 0 0; font-size: 14px; }}
        .filters {{ background: white; padding: 15px; border-radius: 8px; margin-bottom: 20px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        .filters form {{ display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }}
        .filters input, .filters select, .filters button {{ padding: 8px 12px; border: 1px solid #ddd; border-radius: 4px; }}
        .filters button {{ background: #667eea; color: white; cursor: pointer; border: none; }}
        .filters button:hover {{ background: #5568d3; }}
        .filters a {{ padding: 8px 12px; background: #f5f5f5; border-radius: 4px; text-decoration: none; color: #333; }}
        table {{ width: 100%; background: white; border-collapse: collapse; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }}
        th {{ background: #667eea; color: white; padding: 12px; text-align: left; font-weight: 600; }}
        td {{ padding: 12px; border-bottom: 1px solid #eee; }}
        tr:hover {{ background: #f9f9f9; }}
        .question-text {{ max-width: 400px; overflow: hidden; text-overflow: ellipsis; }}
        .answer-text {{ max-width: 300px; overflow: hidden; text-overflow: ellipsis; color: #333; }}
        .badge {{ display: inline-block; padding: 4px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }}
        .badge-multiple_choice {{ background: #e3f2fd; color: #1976d2; }}
        .badge-multiple_answer {{ background: #f3e5f5; color: #7b1fa2; }}
        .badge-essay {{ background: #fff3e0; color: #f57c00; }}
        .badge-short_answer {{ background: #e8f5e9; color: #388e3c; }}
        .badge-fill_in_blank {{ background: #fce4ec; color: #c2185b; }}
        .email {{ color: #666; font-size: 12px; }}
        .timestamp {{ color: #999; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>📊 Question Database</h1>
        <p>All questions answered by StudyFlow users</p>
    </div>
    <div class="stats">
        <div class="stat-card"><h3>{total_questions}</h3><p>Total Questions</p></div>
        <div class="stat-card"><h3>{unique_users}</h3><p>Unique Users</p></div>
        {stats_html}
    </div>
    <div class="filters">
        <form method="get">
            <input type="number" name="user_id" placeholder="User ID" value="{user_id_filter or ''}">
            <select name="type">
                <option value="">All Types</option>
                <option value="multiple_choice" {"selected" if question_type_filter == "multiple_choice" else ""}>Multiple Choice</option>
                <option value="multiple_answer" {"selected" if question_type_filter == "multiple_answer" else ""}>Multiple Answer</option>
                <option value="essay" {"selected" if question_type_filter == "essay" else ""}>Essay</option>
                <option value="short_answer" {"selected" if question_type_filter == "short_answer" else ""}>Short Answer</option>
                <option value="fill_in_blank" {"selected" if question_type_filter == "fill_in_blank" else ""}>Fill in Blank</option>
            </select>
            <select name="limit">
                <option value="50" {"selected" if limit == 50 else ""}>50 results</option>
                <option value="100" {"selected" if limit == 100 else ""}>100 results</option>
                <option value="500" {"selected" if limit == 500 else ""}>500 results</option>
                <option value="1000" {"selected" if limit == 1000 else ""}>1000 results</option>
            </select>
            <button type="submit">Filter</button>
            <a href="/admin/view-questions">Clear</a>
        </form>
    </div>
    <table>
        <thead>
            <tr>
                <th>ID</th>
                <th>User</th>
                <th>Type</th>
                <th>Question</th>
                <th>AI Answer</th>
                <th>Date</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>
</body>
</html>'''

        return html

    except Exception as e:
        debug_log(f"🔥 /admin/view-questions error: {e}\n{traceback.format_exc()}")
        return f"<h1>Error:</h1><p>{e}</p><pre>{traceback.format_exc()}</pre>"


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
@supabase_auth_required
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
        is_multiple_answer = data.get("isMultipleAnswer", False)  # New field for checkbox questions
        model = data.get("model", "gemini-2.5-flash")  # Get model from request, default to 2.5 Flash

        if not question or not answers:
            return jsonify({"error": "Missing question or answers"}), 400

        # Use OpenAI API (gpt-4o-mini for speed/cost, gpt-4o for accuracy)
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # Use model name directly (extension sends gpt-4o-mini or gpt-4o)
        openai_model = model if model in ["gpt-4o-mini", "gpt-4o"] else "gpt-4o-mini"

        answers_text = "\n".join(f"{i+1}. {a}" for i, a in enumerate(answers))

        # Different prompts for single-answer vs multiple-answer questions
        if is_multiple_answer:
            prompt = f"""Answer this quiz question that allows MULTIPLE correct answers (checkboxes). Return ONLY a JSON object.

Question: {question}

Options:
{answers_text}

This question allows selecting MULTIPLE correct answers. Identify ALL answers that are correct.

Return this exact JSON format:
{{
    "correct_answer_indices": [<array of numbers, e.g., [1, 3, 4]>],
    "correct_answer_texts": ["<first correct answer>", "<second correct answer>", ...],
    "confidence": "high/medium/low",
    "reasoning": "<brief explanation why these answers are correct>"
}}

RULES:
- correct_answer_indices is 1-based (1, 2, 3, etc.)
- Include ALL correct answers in the array
- If only one answer is correct, return array with one element: [2]
- Return ONLY valid JSON, no markdown, no other text."""
        else:
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

        # Validate result based on question type
        if is_multiple_answer:
            if not result or not result.get('correct_answer_indices'):
                return jsonify({"error": "AI processing failed"}), 500
            debug_log(f"TEXT API (OpenAI {openai_model}) MULTIPLE-ANSWER: Answers={result.get('correct_answer_indices')}, Confidence={result.get('confidence')}")
        else:
            if not result or not result.get('correct_answer_index'):
                return jsonify({"error": "AI processing failed"}), 500
            debug_log(f"TEXT API (OpenAI {openai_model}): Answer={result.get('correct_answer_index')}, Confidence={result.get('confidence')}")

        # Store question in database for analytics/caching
        try:
            conn = psycopg2.connect(os.environ["DATABASE_URL"])
            cur = conn.cursor()

            # Prepare answer text based on question type
            if is_multiple_answer:
                answer_indices = result.get('correct_answer_indices', [])
                ai_answer = ', '.join([answers[idx - 1] for idx in answer_indices if idx <= len(answers)])
            else:
                answer_idx = result.get('correct_answer_index', 1)
                ai_answer = answers[answer_idx - 1] if answer_idx <= len(answers) else 'Unknown'

            cur.execute("""
                INSERT INTO questions (user_id, question_text, question_type, answers_json, ai_answer, ai_reasoning)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                request.user_id,
                question,
                'multiple_answer' if is_multiple_answer else 'multiple_choice',
                json.dumps(answers),
                ai_answer,
                result.get('reasoning', '')
            ))
            conn.commit()
            conn.close()
            debug_log(f"✅ Question stored in database for user {request.user_id}")
        except Exception as db_error:
            debug_log(f"⚠️ Failed to store question in database: {db_error}")
            # Don't fail the request if database storage fails

        return jsonify(result), 200

    except json.JSONDecodeError as e:
        debug_log(f"TEXT API JSON parse error: {e}")
        return jsonify({"error": "JSON parse failed"}), 500
    except Exception as e:
        debug_log(f"TEXT API error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ============ LEGAL TUTOR EXPLANATION ENDPOINT ============
@app.route("/api/tutor/explain", methods=["POST"])
@supabase_auth_required
def tutor_explain():
    """
    Legal AI tutoring endpoint - Returns step-by-step explanations WITHOUT selecting answers.
    Complies with Missouri HB 2271 by acting as a tutor, not a cheating tool.

    Human-in-the-loop: Student must read explanation and click answer themselves.

    Expects JSON:
    {
        "question": "What is the capital of France? A) London B) Paris C) Berlin D) Madrid"
    }

    Returns:
    {
        "explanation": "1. This question asks about...\n2. Consider the geography...\n3. Paris is located in...",
        "concept": "European Geography - Capital Cities",
        "engagement_time": 0  // Server tracks when explanation was generated
    }
    """
    try:
        # Check rate limit
        can_proceed, remaining = check_question_limit(request.user_id)
        if not can_proceed:
            return jsonify({
                "error": "Daily question limit exceeded",
                "message": "Free users are limited to 10 questions per day. Upgrade to Pro for unlimited access!",
                "limit_exceeded": True
            }), 429

        data = request.get_json()
        if not data:
            return jsonify({"error": "No JSON provided"}), 400

        question = data.get("question", "")
        if not question:
            return jsonify({"error": "Missing question"}), 400

        # Use GPT-4o-mini for cost-effectiveness (tutoring requires explanation, not just accuracy)
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        prompt = f"""You are an AI tutor helping a student understand a quiz question. Your job is to explain the CONCEPT and REASONING, not to directly give the answer.

Question: {question}

Provide a step-by-step explanation that helps the student understand:
1. What concept is being tested
2. How to approach this type of question
3. Key facts or formulas they should consider
4. How to eliminate wrong answers (if multiple choice)
5. A hint toward the correct approach (WITHOUT saying "the answer is X")

Format your response as numbered steps. Be educational and helpful, like a tutor.

IMPORTANT: Do NOT say "The answer is..." or "Click option B". Guide them to figure it out themselves.

Your explanation:"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful AI tutor focused on teaching concepts, not giving direct answers."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=500
        )

        explanation = response.choices[0].message.content.strip()

        # Identify concept being tested (simple extraction)
        concept_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You identify educational concepts in one short phrase."},
                {"role": "user", "content": f"What concept is this question testing? Return ONLY the concept name in 3-5 words.\n\nQuestion: {question}"}
            ],
            temperature=0.3,
            max_tokens=20
        )

        concept = concept_response.choices[0].message.content.strip()

        # Store in database for analytics (as tutoring session, not answer)
        try:
            conn = psycopg2.connect(os.environ.get("DATABASE_URL"))
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO questions (user_id, question_text, question_type, answer_text, ai_reasoning)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                request.user_id,
                question,
                'tutoring_session',  # Different type to distinguish from automated answers
                '',  # No answer provided in tutoring mode
                explanation
            ))
            conn.commit()
            conn.close()
            debug_log(f"✅ Tutoring session stored for user {request.user_id}")
        except Exception as db_error:
            debug_log(f"⚠️ Failed to store tutoring session: {db_error}")

        result = {
            "explanation": explanation,
            "concept": concept,
            "engagement_time": 0,  # Client will track actual read time
            "legal_mode": True  # Flag indicating this is legal tutoring, not automation
        }

        return jsonify(result), 200

    except Exception as e:
        debug_log(f"TUTOR API error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ============ ESSAY ANSWER ENDPOINT ============
@app.route("/api/essay", methods=["POST"])
@supabase_auth_required
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

        # Store question in database for analytics/caching
        try:
            conn = psycopg2.connect(os.environ["DATABASE_URL"])
            cur = conn.cursor()

            # Determine question type based on answer length
            if len(essay_answer) < 50:
                question_type = 'fill_in_blank'
            elif len(essay_answer) < 200:
                question_type = 'short_answer'
            else:
                question_type = 'essay'

            cur.execute("""
                INSERT INTO questions (user_id, question_text, question_type, answers_json, ai_answer, ai_reasoning)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                request.user_id,
                question,
                question_type,
                None,  # No multiple choice options for essay questions
                essay_answer,
                None  # No reasoning for essay questions
            ))
            conn.commit()
            conn.close()
            debug_log(f"✅ Essay question stored in database for user {request.user_id}")
        except Exception as db_error:
            debug_log(f"⚠️ Failed to store essay question in database: {db_error}")
            # Don't fail the request if database storage fails

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

        html_content = """
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <h2 style="color: #667eea;">Open StudyFlow on Your Computer</h2>
                <p>You visited StudyFlow on your mobile device, but our Chrome extension only works on desktop computers.</p>
                <p style="margin: 30px 0;">
                    <a href="https://studyflowsuite.com/"
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
                    Questions? Visit our <a href="https://studyflowsuite.com/docs.html" style="color: #667eea;">FAQ page</a>.
                </p>
                <hr style="margin: 30px 0; border: none; border-top: 1px solid #e2e8f0;">
                <p style="color: #94a3b8; font-size: 12px; text-align: center;">
                    StudyFlow Suite - AI-Powered Quiz Automation<br>
                    <a href="https://studyflowsuite.com/" style="color: #667eea;">studyflowsuite.com</a>
                </p>
            </div>
        """

        response = send_brevo_email(
            to_email=email,
            to_name=None,
            subject="StudyFlow Download Link - Open on Desktop",
            html_content=html_content
        )

        if response.status_code in (200, 201):
            app.logger.info(f"Download link sent to {email}")
            return jsonify({'success': True, 'message': 'Email sent successfully'}), 200
        else:
            app.logger.error(f"Error sending download link: {response.text}")
            return jsonify({'error': 'Failed to send email'}), 500

    except Exception as e:
        app.logger.error(f"Error sending download link: {e}")
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


# ============ NOTEFLOW ENDPOINTS ============

@app.route("/api/notes/upload", methods=["POST"])
@supabase_auth_required
def upload_note():
    """
    Upload a note file (PDF, image, Word doc, TXT) to Supabase.

    NEW: Uses Supabase Storage + pgvector + background processing

    Expects: multipart/form-data with:
        - file: The document file
        - university: (optional) University name
        - course_code: (optional) Course code (e.g., "BIO 101")
        - professor: (optional) Professor name
        - semester: (optional) Semester (e.g., "Fall 2024")

    Returns:
    {
        "success": true,
        "note_id": "uuid",
        "filename": "Biology_Chapter_3.pdf",
        "pages": 5,
        "processing": true
    }
    """
    try:
        from StudyFlow.backend.supabase_client import (
            check_page_limit, upload_file_to_storage, create_note_record, increment_page_count, log_upload, get_user_profile
        )
        from StudyFlow.backend.tasks import process_note_async
        import hashlib

        # Get user profile to extract username
        user_profile = get_user_profile(request.user_id)
        username = user_profile.get('username') if user_profile else None

        # Check if file was uploaded
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400

        # Get course metadata from form
        course_metadata = {
            "university": request.form.get('university'),
            "course_code": request.form.get('course_code'),
            "professor": request.form.get('professor'),
            "semester": request.form.get('semester')
        }

        # Get Nexus sharing preference (Missouri SB 1324 compliance)
        share_with_nexus = request.form.get('share_with_nexus', 'false').lower() == 'true'

        # Get user's IP address (for security logging)
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip_address and ',' in ip_address:
            # X-Forwarded-For can have multiple IPs, take the first
            ip_address = ip_address.split(',')[0].strip()

        # Get file info
        original_filename = file.filename
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)  # Reset file pointer

        # Determine file type
        file_ext = original_filename.rsplit('.', 1)[1].lower() if '.' in original_filename else ''
        allowed_extensions = ['pdf', 'jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp', 'txt', 'doc', 'docx']
        if file_ext not in allowed_extensions:
            return jsonify({"error": "Unsupported file type. Allowed: PDF, images, TXT, DOC/DOCX"}), 400

        # Read file content
        file_content = file.read()

        # Calculate SHA-256 hash for tamper verification (Missouri SB 1324 compliance)
        file_hash = hashlib.sha256(file_content).hexdigest()
        debug_log(f"[*] File hash (SHA-256): {file_hash}")

        # Log upload to database (7-year retention for Missouri compliance)
        log_upload(
            user_id=request.user_id,
            file_name=original_filename,
            file_hash=file_hash,
            file_size=file_size,
            shared_with_nexus=share_with_nexus,
            ip_address=ip_address,
            university=course_metadata.get('university'),
            course_code=course_metadata.get('course_code')
        )

        # Extract text based on file type
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')

        if file_ext in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp']:
            # Image file
            import PIL.Image
            import io
            image = PIL.Image.open(io.BytesIO(file_content))

            prompt = """Extract ALL text from this image. This is a student's class notes.

            Return ONLY the extracted text, preserving:
            - All text content
            - Line breaks and structure
            - Headings and bullet points

            Do not add any commentary. Just return the extracted text."""

            response = model.generate_content([prompt, image])
            ocr_text = response.text.strip()
            page_count = 1

        elif file_ext == 'pdf':
            # PDF file
            import PyPDF2
            import io

            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
            page_count = len(pdf_reader.pages)

            # Try extracting text first (faster if PDF has text layer)
            ocr_text = ""
            for page in pdf_reader.pages:
                page_text = page.extract_text()
                if page_text:
                    ocr_text += page_text + "\n\n"

            # If no text extracted, skip for now
            if not ocr_text.strip():
                ocr_text = f"[PDF document: {page_count} pages - requires OCR]"

        elif file_ext == 'txt':
            # Plain text file
            ocr_text = file_content.decode('utf-8', errors='ignore')
            page_count = 1

        elif file_ext in ['doc', 'docx']:
            # Word documents -- extract text with python-docx
            try:
                import io
                from docx import Document
                doc = Document(io.BytesIO(file_content))
                ocr_text = '\n'.join(p.text for p in doc.paragraphs)
                if not ocr_text.strip():
                    ocr_text = f"[{file_ext.upper()} document - no text extracted]"
            except Exception:
                ocr_text = f"[{file_ext.upper()} document]"
            page_count = 1

        else:
            ocr_text = f"[{file_ext.upper()} document]"
            page_count = 1

        # Check page limit BEFORE uploading
        allowed, message = check_page_limit(request.user_id, page_count)
        if not allowed:
            return jsonify({"error": message, "limit_exceeded": True}), 403

        # Convert all files to PDF at upload time
        # Text extraction already happened above on the original format
        from StudyFlow.backend.pdf_flatten import convert_to_pdf
        pdf_data, pdf_filename = convert_to_pdf(file_content, original_filename)
        if pdf_data is None:
            return jsonify({"error": f"Failed to convert {file_ext.upper()} to PDF"}), 500

        # Use converted PDF for storage
        file_content = pdf_data
        original_filename = pdf_filename
        file_ext = 'pdf'
        file_size = len(file_content)
        debug_log(f"[*] Converted to PDF: {pdf_filename} ({file_size} bytes)")

        # Upload PDF to Supabase Storage
        import uuid
        unique_filename = f"{request.user_id}/{uuid.uuid4()}_{original_filename}"
        content_type = 'application/pdf'

        file_url = upload_file_to_storage(file_content, unique_filename, content_type)
        if not file_url:
            return jsonify({"error": "Failed to upload file to storage"}), 500

        # Create note record in Supabase
        debug_log(f"[*] Creating note for user_id: {request.user_id}")
        note = create_note_record(
            user_id=request.user_id,
            filename=original_filename,
            file_type=file_ext,
            file_size=file_size,
            file_path=unique_filename,
            page_count=page_count,
            course_metadata=course_metadata,
            username=username
        )

        if not note:
            return jsonify({"error": "Failed to create note record"}), 500

        note_id = note['id']
        debug_log(f"[*] Created note {note_id} for user {request.user_id}")

        # Increment user's page count
        increment_page_count(request.user_id, page_count)

        # Trigger background processing (chunking, embedding, anonymization)
        process_note_async.delay(note_id, request.user_id, ocr_text, course_metadata, file_hash, username)

        debug_log(f"Note uploaded: {original_filename} ({file_size} bytes, {page_count} pages)")
        debug_log(f"Background processing started for note {note_id}")

        # GOOD STANDING: Verify upload with AI (Missouri HB 2271 compliance)
        verification_result = None
        try:
            if len(ocr_text.strip()) >= 50:
                print(f"[GOOD STANDING] Verifying upload for note {note_id}...", flush=True)

                # Quick AI verification with Gemini
                import google.generativeai as genai
                genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
                model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')

                prompt = f"""Analyze this document to determine if it's legitimate study material.

DOCUMENT TEXT (first 2000 chars):
{ocr_text[:2000]}

Respond with ONLY a JSON object:
{{
    "is_study_material": true/false,
    "confidence": 0.0-1.0,
    "reason": "brief explanation",
    "category": "notes" | "textbook" | "slides" | "homework" | "spam" | "blank" | "other"
}}

Study material includes: class notes, textbook chapters, lecture slides, study guides, homework, assignments, etc.
NOT study material: grocery lists, personal emails, blank pages, random text, advertisements."""

                response = model.generate_content(prompt)
                ai_text = response.text.strip()

                # Parse JSON response
                import json
                import re
                if ai_text.startswith("```"):
                    ai_text = re.sub(r'^```json?\s*', '', ai_text)
                    ai_text = re.sub(r'\s*```$', '', ai_text)

                result = json.loads(ai_text)
                is_verified = result.get('is_study_material', False)
                confidence = result.get('confidence', 0.5)
                category = result.get('category', 'other')

                # Determine rejection reason
                rejection_reason = None
                if not is_verified:
                    if category == 'spam':
                        rejection_reason = 'spam'
                    elif category == 'blank':
                        rejection_reason = 'blank'
                    else:
                        rejection_reason = 'invalid_format'

                # Log verification
                from StudyFlow.backend.supabase_client import supabase
                supabase.table("upload_verifications").insert({
                    "user_id": request.user_id,
                    "note_id": note_id,
                    "verification_status": "verified" if is_verified else "rejected",
                    "rejection_reason": rejection_reason,
                    "ai_confidence": confidence
                }).execute()

                # If verified, update user's Good Standing status
                if is_verified:
                    from datetime import datetime
                    supabase.table("user_profiles").update({
                        "good_standing": True,
                        "last_verified_upload_date": datetime.utcnow().isoformat()
                    }).eq("id", request.user_id).execute()

                    print(f"[GOOD STANDING] User {request.user_id} verified upload, status updated", flush=True)
                    verification_result = {"verified": True, "confidence": confidence}
                else:
                    print(f"[GOOD STANDING] Upload rejected as {category}: {result.get('reason')}", flush=True)
                    verification_result = {"verified": False, "reason": rejection_reason}
            else:
                print(f"[GOOD STANDING] Skipping verification (text too short)", flush=True)
        except Exception as verify_error:
            print(f"[GOOD STANDING] Verification failed: {verify_error}", flush=True)
            # Don't fail the upload if verification fails

        # Notify other users in the same course about the new note
        try:
            uni = course_metadata.get('university')
            ccode = course_metadata.get('course_code')
            if uni and ccode:
                # Find all users who have uploaded to the same university+course_code
                course_users = supabase.table("notes") \
                    .select("user_id") \
                    .eq("university", uni) \
                    .eq("course_code", ccode) \
                    .neq("user_id", request.user_id) \
                    .execute()
                notified_ids = set()
                for row in (course_users.data or []):
                    uid = row.get("user_id")
                    if uid and uid not in notified_ids:
                        notified_ids.add(uid)
                        create_notification(
                            user_id=uid,
                            notif_type="course_new_note",
                            title="New Note in Course",
                            message=f"New note in {ccode}: {original_filename} by @{username or 'someone'}",
                            note_id=note_id,
                            actor_username=username,
                        )
                if notified_ids:
                    debug_log(f"[+] Notified {len(notified_ids)} users about new note in {ccode}")
        except Exception as notif_err:
            debug_log(f"[-] Upload notification failed (non-blocking): {notif_err}")

        return jsonify({
            "success": True,
            "note_id": note_id,
            "filename": original_filename,
            "pages": page_count,
            "processing": True,
            "verification": verification_result,
            "message": "Note uploaded! Processing in background..."
        }), 200

    except Exception as e:
        debug_log(f"Upload error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/list", methods=["GET", "OPTIONS"])
@supabase_auth_required
def list_notes():
    """
    Get list of all notes for current user.

    Returns:
    [
        {
            "id": "uuid",
            "filename": "Biology_Chapter_3.pdf",
            "pages": 5,
            "uploaded_at": "2024-01-15T10:30:00",
            "processed": true,
            "university": "MSU",
            "course_code": "BIO 101"
        },
        ...
    ]
    """
    # Handle OPTIONS preflight
    if request.method == 'OPTIONS':
        return '', 200

    try:
        from StudyFlow.backend.supabase_client import get_user_notes

        debug_log(f"[*] Fetching notes for user: {request.user_id}")
        notes = get_user_notes(request.user_id)
        debug_log(f"[*] Found {len(notes)} notes for user {request.user_id}")

        # Format response
        formatted_notes = []
        for note in notes:
            formatted_notes.append({
                "id": note['id'],
                "filename": note['original_filename'],
                "file_type": note['file_type'],
                "file_size": note['file_size'],
                "pages": note['page_count'],
                "uploaded_at": note['uploaded_at'],
                "processed": note['processed'],
                "is_public": note['is_public'],
                "university": note.get('university'),
                "course_code": note.get('course_code'),
                "professor": note.get('professor'),
                "folder_id": note.get('folder_id')  # Include folder assignment
            })

        return jsonify(formatted_notes), 200

    except Exception as e:
        debug_log(f"❌ List notes error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/usage-stats", methods=["GET"])
@supabase_auth_required
def get_notes_usage_stats():
    """
    Get usage statistics for user's notes showing how many times they've been used to help answer questions.

    Returns:
    {
        "totalUsage": 47,
        "weeklyUsage": 12,
        "activeNotes": 5,
        "noteUsage": {
            "note_id_1": 23,
            "note_id_2": 15,
            ...
        },
        "topNotes": [
            {"filename": "Biology_Chapter_3.pdf", "count": 23},
            {"filename": "Chemistry_Notes.pdf", "count": 15},
            ...
        ]
    }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        from datetime import datetime, timedelta

        user_id = request.user_id

        # Get user's notes
        notes_response = supabase.table("notes").select("id, original_filename").eq("user_id", user_id).execute()
        user_notes = {note['id']: note['original_filename'] for note in notes_response.data}

        # Get usage counts from conversation sources
        # This queries how many times each note was used in conversations
        note_usage = {}
        total_usage = 0
        weekly_usage = 0
        week_ago = (datetime.now() - timedelta(days=7)).isoformat()

        # Query all assistant messages with sources
        all_messages_response = supabase.table("conversation_messages").select("sources, created_at").eq("role", "assistant").not_.is_("sources", "null").execute()

        for message in all_messages_response.data:
            sources = message.get('sources', [])
            created_at = message.get('created_at', '')

            # Check each source in the message
            for source in sources:
                source_note_id = source.get('note_id')
                if source_note_id in user_notes:
                    # Count this usage
                    note_usage[source_note_id] = note_usage.get(source_note_id, 0) + 1
                    total_usage += 1

                    # Count weekly usage
                    if created_at >= week_ago:
                        weekly_usage += 1

        # Get top notes
        top_notes = []
        for note_id, count in sorted(note_usage.items(), key=lambda x: x[1], reverse=True)[:5]:
            top_notes.append({
                "filename": user_notes[note_id],
                "count": count
            })

        active_notes = len([c for c in note_usage.values() if c > 0])

        return jsonify({
            "totalUsage": total_usage,
            "weeklyUsage": weekly_usage,
            "activeNotes": active_notes,
            "noteUsage": note_usage,
            "topNotes": top_notes
        }), 200

    except Exception as e:
        debug_log(f"❌ Usage stats error: {e}\n{traceback.format_exc()}")
        # Return empty stats on error
        return jsonify({
            "totalUsage": 0,
            "weeklyUsage": 0,
            "activeNotes": 0,
            "noteUsage": {},
            "topNotes": []
        }), 200


@app.route("/api/notes/<note_id>", methods=["DELETE"])
@supabase_auth_required
def delete_note_endpoint(note_id):
    """
    Delete a note by ID (only if it belongs to current user).
    """
    try:
        from StudyFlow.backend.supabase_client import delete_note

        success = delete_note(note_id, request.user_id)

        if success:
            return jsonify({"success": True}), 200
        else:
            return jsonify({"error": "Note not found or unauthorized"}), 404

    except Exception as e:
        debug_log(f"❌ Delete note error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/<note_id>/rename", methods=["PATCH"])
@supabase_auth_required
def rename_note_endpoint(note_id):
    """
    Rename a note by ID (only if it belongs to current user).
    Request body: { "original_filename": "new_name.pdf" }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        data = request.get_json()
        new_filename = data.get("original_filename", "").strip()

        if not new_filename:
            return jsonify({"error": "Filename is required"}), 400

        # Verify ownership and update filename
        response = supabase.table("notes").update({
            "original_filename": new_filename
        }).eq("id", note_id).eq("user_id", request.user_id).execute()

        if response.data:
            debug_log(f"Renamed note {note_id} to {new_filename}")
            return jsonify({"success": True, "original_filename": new_filename}), 200
        else:
            return jsonify({"error": "Note not found or unauthorized"}), 404

    except Exception as e:
        debug_log(f"❌ Rename note error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/<note_id>/visibility", methods=["POST"])
@supabase_auth_required
def toggle_note_visibility(note_id):
    """
    Toggle note public/private visibility (only if it belongs to current user).
    Request body: { "is_public": true/false }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        data = request.get_json()
        is_public = data.get("is_public")

        if is_public is None:
            return jsonify({"error": "is_public field is required"}), 400

        # Verify ownership and update visibility
        response = supabase.table("notes").update({
            "is_public": is_public
        }).eq("id", note_id).eq("user_id", request.user_id).execute()

        if response.data:
            debug_log(f"Updated note {note_id} visibility to {'public' if is_public else 'private'}")
            return jsonify({"success": True, "is_public": is_public}), 200
        else:
            return jsonify({"error": "Note not found or unauthorized"}), 404

    except Exception as e:
        debug_log(f"❌ Toggle visibility error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/user/send-edu-verification", methods=["POST"])
@supabase_auth_required
def send_edu_verification():
    """
    Send verification email to .edu email address.
    Request body: { "edu_email": "user@university.edu" }
    """
    try:
        import uuid
        from StudyFlow.backend.supabase_client import supabase

        data = request.get_json()
        edu_email = data.get("edu_email", "").strip().lower()

        if not edu_email:
            return jsonify({"error": "edu_email is required"}), 400

        if not edu_email.endswith('.edu'):
            return jsonify({"error": "Email must be a .edu address"}), 400

        # Generate verification token
        verification_token = str(uuid.uuid4())

        # Store pending verification in user_profiles
        response = supabase.table("user_profiles").update({
            "pending_edu_email": edu_email,
            "edu_verification_token": verification_token
        }).eq("id", request.user_id).execute()

        if not response.data:
            return jsonify({"error": "Failed to update profile"}), 500

        # Send verification email
        verification_url = f"https://studyflowsuite.com/verify-edu.html?token={verification_token}"

        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <h2 style="color: #7c9885;">Verify Your University Email</h2>
            <p>Click the button below to verify your .edu email address and unlock access to the StudyFlow Nexus note library.</p>
            <div style="margin: 30px 0; text-align: center;">
                <a href="{verification_url}"
                   style="background: linear-gradient(135deg, #7c9885 0%, #6b8575 100%);
                          color: white;
                          padding: 14px 32px;
                          text-decoration: none;
                          border-radius: 12px;
                          display: inline-block;
                          font-weight: 600;">
                    Verify Email Address
                </a>
            </div>
            <p style="color: #5d5d5d; font-size: 14px;">Or copy and paste this link into your browser:</p>
            <p style="color: #7c9885; word-break: break-all; font-size: 12px;">{verification_url}</p>
            <p style="color: #999; font-size: 12px; margin-top: 30px;">If you didn't request this verification, you can safely ignore this email.</p>
        </div>
        """

        response = send_brevo_email(
            to_email=edu_email,
            to_name=None,
            subject="Verify your university email - StudyFlow Suite",
            html_content=html_content
        )

        if response.status_code in (200, 201):
            debug_log(f"Verification email sent to {edu_email}")
            return jsonify({"success": True, "message": "Verification email sent"}), 200
        else:
            debug_log(f"Failed to send verification email: {response.text}")
            return jsonify({"error": "Failed to send email"}), 500

    except Exception as e:
        debug_log(f"Send .edu verification error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/user/verify-edu-email", methods=["POST"])
def verify_edu_email():
    """
    Verify .edu email using token from verification link.
    Request body: { "token": "uuid-token" }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        data = request.get_json()
        token = data.get("token")

        if not token:
            return jsonify({"error": "token is required"}), 400

        # Find user with matching token
        response = supabase.table("user_profiles").select("*").eq("edu_verification_token", token).execute()

        if not response.data or len(response.data) == 0:
            return jsonify({"error": "Invalid or expired verification token"}), 404

        user_profile = response.data[0]
        pending_email = user_profile.get("pending_edu_email")

        if not pending_email:
            return jsonify({"error": "No pending verification found"}), 404

        # Update user profile to mark as verified
        update_response = supabase.table("user_profiles").update({
            "edu_email_verified": True,
            "edu_email": pending_email,
            "pending_edu_email": None,
            "edu_verification_token": None
        }).eq("id", user_profile["id"]).execute()

        if update_response.data:
            debug_log(f"✅ User {user_profile['id']} verified .edu email: {pending_email}")
            return jsonify({
                "success": True,
                "message": "Email verified successfully",
                "edu_email": pending_email
            }), 200
        else:
            return jsonify({"error": "Failed to update verification status"}), 500

    except Exception as e:
        debug_log(f"[-] Verify .edu email error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/user/verify-age", methods=["POST"])
@supabase_auth_required
def verify_age():
    """
    Verify user's age using transactional data (Missouri SB 1455 / GUARD Act).

    Request body: {
        "legal_name": "Cody Williams",
        "zip_code": "65802",
        "birthdate": "1998-03-15"
    }

    Returns verification result and unfreezes account if successful.
    """
    try:
        from StudyFlow.backend.age_verification import verify_age_transactional
        from StudyFlow.backend.supabase_client import update_age_verification

        data = request.get_json()
        if not data:
            return jsonify({"error": "Missing request body"}), 400

        legal_name = data.get('legal_name', '').strip()
        zip_code = data.get('zip_code', '').strip()
        birthdate = data.get('birthdate', '').strip()
        address = data.get('address', '').strip()
        city = data.get('city', '').strip()
        state = data.get('state', '').strip()

        if not legal_name or not zip_code or not birthdate:
            return jsonify({"error": "legal_name, zip_code, and birthdate are required"}), 400

        # Validate zip code format
        if not zip_code.replace('-', '').isdigit() or len(zip_code.replace('-', '')) not in (5, 9):
            return jsonify({"error": "Invalid zip code format"}), 400

        # Call Veratad AgeMatch5.0 verification
        result = verify_age_transactional(
            legal_name, zip_code, birthdate,
            address=address, city=city, state=state,
            reference=request.user_id
        )

        if result["verified"]:
            # Update profile with verification status
            update_age_verification(
                user_id=request.user_id,
                verified=True,
                method=result["method"],
                legal_name=legal_name,
                zip_code=zip_code,
                birthdate=birthdate
            )

            debug_log(f"[+] Age verified for {request.user_id}: {legal_name}, age={result['age']}")

            return jsonify({
                "verified": True,
                "message": "Age verification successful. Your account is now fully active.",
                "method": result["method"],
                "age": result["age"]
            }), 200
        else:
            debug_log(f"[-] Age verification failed for {request.user_id}: {result['reason']}")

            return jsonify({
                "verified": False,
                "message": result["reason"],
                "method": result["method"]
            }), 200

    except Exception as e:
        debug_log(f"[-] Age verification error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": "Age verification failed"}), 500


@app.route("/api/user/verification-status", methods=["GET"])
@supabase_auth_required
def verification_status():
    """
    Get user's age verification and account freeze status.
    Returns current verification state for frontend display.
    """
    try:
        from StudyFlow.backend.supabase_client import get_verification_status

        status = get_verification_status(request.user_id)

        if not status:
            return jsonify({
                "age_verified": False,
                "account_frozen": False,
                "needs_verification": True
            }), 200

        # Check if re-verification is needed (12-month cycle)
        needs_reverification = False
        if status.get('last_verified_at'):
            from datetime import datetime, timezone
            last_verified = datetime.fromisoformat(status['last_verified_at'].replace('Z', '+00:00'))
            months_since = (datetime.now(timezone.utc) - last_verified).days / 30
            needs_reverification = months_since >= 12

        return jsonify({
            "age_verified": status.get("age_verified", False),
            "age_verified_at": status.get("age_verified_at"),
            "age_verification_method": status.get("age_verification_method"),
            "last_verified_at": status.get("last_verified_at"),
            "account_frozen": status.get("account_frozen", False),
            "frozen_reason": status.get("frozen_reason"),
            "needs_reverification": needs_reverification
        }), 200

    except Exception as e:
        debug_log(f"[-] Verification status error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": "Failed to get verification status"}), 500


@app.route("/api/notes/<note_id>/download", methods=["GET"])
@supabase_auth_required
def download_note_endpoint(note_id):
    """
    Download a note file by ID (only if it belongs to current user).
    PDFs and images are flattened (rasterized) with watermarks.
    Every download is logged as a transaction.
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        from StudyFlow.backend.pdf_flatten import flatten_pdf, flatten_image, can_flatten, convert_to_pdf
        from flask import send_file
        from datetime import date
        import io
        import uuid

        # DAILY DOWNLOAD LIMIT CHECK (3 downloads/day for free users)
        # Fetch user profile to check subscription and download count
        profile_result = supabase.table("user_profiles").select(
            "subscription_tier, subscription_status, daily_downloads_count, daily_downloads_reset_date, good_standing, permanent_bad_standing, last_verified_upload_date"
        ).eq("id", request.user_id).single().execute()
        profile = profile_result.data

        # CHECK: Good standing expires after 30 days without a quality upload (free users only)
        from datetime import datetime, timedelta
        is_scholar_check = (
            profile.get('subscription_tier') == 'pro' and
            profile.get('subscription_status') == 'active'
        )

        if not is_scholar_check and profile.get('good_standing', False):
            last_upload = profile.get('last_verified_upload_date')
            if last_upload:
                try:
                    last_upload_date = datetime.fromisoformat(last_upload.replace('Z', '+00:00'))
                    days_since_upload = (datetime.utcnow().replace(tzinfo=last_upload_date.tzinfo) - last_upload_date).days

                    if days_since_upload > 30:
                        # Revoke good standing - hasn't uploaded in 30+ days
                        supabase.table("user_profiles").update({
                            "good_standing": False
                        }).eq("id", request.user_id).execute()
                        profile['good_standing'] = False
                        debug_log(f"[!] User {request.user_id} lost good standing (no upload for {days_since_upload} days)")
                except Exception as e:
                    debug_log(f"[-] Error checking last upload date: {e}")

        # Check if Scholar's Club member (unlimited downloads)
        is_scholar = (
            profile.get('subscription_tier') == 'pro' and
            profile.get('subscription_status') == 'active'
        )

        if not is_scholar:
            # Free user - enforce 3 downloads per day limit
            today = date.today()
            reset_date = profile.get('daily_downloads_reset_date')
            download_count = profile.get('daily_downloads_count', 0)

            # Reset counter if new day
            if not reset_date or str(reset_date) != str(today):
                supabase.table("user_profiles").update({
                    "daily_downloads_count": 0,
                    "daily_downloads_reset_date": str(today)
                }).eq("id", request.user_id).execute()
                download_count = 0
                debug_log(f"[+] Reset daily download count for user {request.user_id}")

            # Check if at limit
            if download_count >= 3:
                debug_log(f"[!] User {request.user_id} hit daily download limit ({download_count}/3)")
                return jsonify({
                    "error": "Daily download limit reached",
                    "message": "You've used all 3 downloads today. Join Scholar's Club for unlimited downloads!",
                    "limit_reached": True,
                    "downloads_used": download_count,
                    "downloads_limit": 3,
                    "subscribe_url": "https://unclephilburt.github.io/studyflowwebsite/account.html"
                }), 403

        # Get note metadata -- check own notes first, then public notes
        result = supabase.table("notes").select("*").eq("id", note_id).eq("user_id", request.user_id).execute()
        note_data = result.data[0] if result.data else None

        if not note_data:
            # Not the user's own note -- check if it's a public note
            result = supabase.table("notes").select("*").eq("id", note_id).eq("is_public", True).execute()
            note_data = result.data[0] if result.data else None

            # GOOD STANDING CHECK: Required for downloading public notes (not your own)
            # (Reuse profile fetched earlier for download limit check)
            if note_data:
                # Block if permanently banned
                if profile.get('permanent_bad_standing', False):
                    return jsonify({"error": "Account suspended due to DMCA violations"}), 403

                # Check good standing (Scholar's Club members are always in good standing)
                if not is_scholar and not profile.get('good_standing', False):
                    return jsonify({
                        "error": "Good Standing required to download notes",
                        "message": "Upload a verified note or subscribe to regain access",
                        "good_standing_required": True
                    }), 403

        if not note_data:
            return jsonify({"error": "Note not found or unauthorized"}), 404

        file_path = note_data.get('file_path')
        original_filename = note_data.get('original_filename')

        if not file_path:
            return jsonify({"error": "File not found in storage"}), 404

        # Generate transaction code
        transaction_code = "DL-" + uuid.uuid4().hex[:8]

        # Get username for watermark
        username = "user"
        try:
            profile_result = supabase.table("user_profiles").select("username").eq("id", request.user_id).execute()
            if profile_result.data and profile_result.data[0].get("username"):
                username = profile_result.data[0]["username"]
        except Exception:
            pass

        # Download file from Supabase Storage
        file_data = supabase.storage.from_('note-files').download(file_path)

        # Log download transaction
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip_address and ',' in ip_address:
            ip_address = ip_address.split(',')[0].strip()

        try:
            supabase.table("download_transactions").insert({
                "user_id": request.user_id,
                "note_id": note_id,
                "original_filename": original_filename,
                "transaction_code": transaction_code,
                "ip_address": ip_address,
                "user_agent": request.headers.get('User-Agent', '')
            }).execute()
            debug_log(f"[+] Download transaction logged: {transaction_code}")
        except Exception as tx_err:
            debug_log(f"[-] Failed to log download transaction: {tx_err}")

        # Flatten and watermark -- everything becomes a PDF
        flattenable, file_type = can_flatten(original_filename)
        name_base = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename

        if flattenable and file_type == 'pdf':
            file_data = flatten_pdf(file_data, username, transaction_code)
        elif flattenable and file_type == 'image':
            file_data = flatten_image(file_data, username, transaction_code)
        else:
            # Legacy file (txt, docx, etc.) -- convert to PDF first, then flatten
            pdf_data, _ = convert_to_pdf(file_data, original_filename)
            if pdf_data:
                file_data = flatten_pdf(pdf_data, username, transaction_code)

        download_name = f"{name_base}_studyflow.pdf"
        mimetype = 'application/pdf'

        # Increment download counter for free users
        if not is_scholar:
            try:
                new_count = (profile.get('daily_downloads_count', 0) or 0) + 1
                supabase.table("user_profiles").update({
                    "daily_downloads_count": new_count
                }).eq("id", request.user_id).execute()
                debug_log(f"[+] User {request.user_id} download count: {new_count}/3")
            except Exception as count_err:
                debug_log(f"[-] Failed to increment download count: {count_err}")

        return send_file(
            io.BytesIO(file_data),
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_name
        )

    except Exception as e:
        debug_log(f"[-] Download note error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/search", methods=["POST"])
@supabase_auth_required
def search_notes():
    """
    Search through ALL notes using vector similarity (pgvector + embeddings).

    COLLECTIVE BRAIN: Searches user's own notes + ALL public notes from ALL students.
    No course filtering - truly shared knowledge base across all subjects.

    Expects JSON:
    {
        "question": "What is photosynthesis?"
    }

    Returns:
    {
        "results": [
            {
                "source": "Biology_Chapter_3.pdf",
                "text": "Photosynthesis is the process by which...",
                "hint": "Look at the section about cellular processes...",
                "from_collective_brain": true,
                "similarity": 0.89
            }
        ]
    }
    """
    try:
        from StudyFlow.backend.supabase_client import search_notes_vector, get_user_profile, supabase
        from StudyFlow.backend.embedding_client import generate_embedding

        data = request.get_json()
        if not data or not data.get('question'):
            return jsonify({"error": "Missing question"}), 400

        question = data.get('question')

        # Get user profile (just to verify user exists)
        user_profile = get_user_profile(request.user_id)
        if not user_profile:
            return jsonify({"error": "User profile not found", "results": []}), 404

        # Generate embedding for the question
        query_embedding = generate_embedding(question)
        if not query_embedding:
            return jsonify({"error": "Failed to generate query embedding", "results": []}), 500

        debug_log(f"🔍 Searching ENTIRE collective brain for: '{question}'")

        # Search using pgvector - searches ALL public notes from ALL students
        search_results = search_notes_vector(
            query_embedding=query_embedding,
            user_id=request.user_id,
            university=None,  # No course filtering - true collective brain
            course_code=None,
            match_threshold=0.4,  # Only return results with >40% similarity
            match_count=5  # Top 5 results
        )

        print(f"🔎 Search returned {len(search_results) if search_results else 0} results")

        if not search_results:
            print("⚠️ No search results found, returning empty array")
            return jsonify({"results": []}), 200

        # Format results with hints
        formatted_results = []
        print(f"📝 Processing {len(search_results)} results...")

        for result in search_results:
            # Get note filename
            note_result = supabase.table("notes").select("original_filename").eq("id", result['note_id']).execute()
            filename = note_result.data[0]['original_filename'] if note_result.data else "Unknown"

            # Check if this is a Wikipedia source
            is_wikipedia = result.get('university') == 'Wikipedia'
            wikipedia_url = None

            if is_wikipedia and filename.endswith('.txt'):
                # Extract article title and create Wikipedia URL
                article_title = filename.replace('.txt', '')
                url_title = article_title.replace(' ', '_')
                wikipedia_url = f"https://en.wikipedia.org/wiki/{url_title}"

            # Decide which text to show
            text_to_show = result['content_summary'] if result['content_summary'] else result['chunk_text']

            # Generate a detailed answer using the text
            print(f"🔍 About to generate detailed answer for: {question[:50]}...")
            hint = generate_hint_from_text(question, text_to_show)
            print(f"💡 Generated answer: {hint[:100]}...")

            # Build source attribution
            if is_wikipedia:
                source_text = f"Wikipedia: {filename.replace('.txt', '')}"
            elif result['university']:
                source_text = f"{filename} ({result['university']} - {result['course_code']})"
            else:
                source_text = filename

            formatted_results.append({
                "source": source_text,
                "text": text_to_show[:300] + "..." if len(text_to_show) > 300 else text_to_show,
                "hint": hint,
                "from_collective_brain": not result['is_own_note'],
                "from_wikipedia": is_wikipedia,
                "wikipedia_url": wikipedia_url,
                "similarity": round(result['similarity'], 2)
            })

        debug_log(f"✅ Found {len(formatted_results)} results (similarity > 0.4)")

        return jsonify({"results": formatted_results}), 200

    except Exception as e:
        debug_log(f"❌ Search notes error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e), "results": []}), 500


def generate_hint_from_text(question, text):
    """
    Generate a detailed answer from the found text using Gemini.
    """
    try:
        import google.generativeai as genai

        # Check if API key exists
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            debug_log("❌ GEMINI_API_KEY not found in environment! Answer generation disabled.")
            return "Review this section carefully to find the answer."

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-3-flash-preview')

        prompt = f"""You are a knowledgeable study tutor. A student asked: "{question}"

I found this relevant excerpt from their notes:
"{text[:1000]}"

Generate a DETAILED, COMPREHENSIVE answer to their question using the information from the notes.

Your job:
- Answer the question completely and thoroughly
- Include all relevant facts, definitions, explanations, and examples
- Explain concepts clearly with context
- Be specific and detailed - don't hold back information
- Make it educational and easy to understand
- Use 2-4 paragraphs if needed to fully explain the topic

DO NOT say things like:
- "According to the notes..."
- "The excerpt mentions..."
- "Review the section..."

Just answer the question directly as if you're a tutor who knows this information.

Return your detailed answer:"""

        debug_log(f"🤖 Generating detailed answer for question: '{question[:50]}...'")
        response = model.generate_content(prompt)
        answer = response.text.strip()

        debug_log(f"✅ Generated answer: '{answer[:80]}...'")

        return answer if answer else "Review this section carefully to find the answer."

    except Exception as e:
        debug_log(f"❌ Error generating answer: {type(e).__name__}: {str(e)}")
        return "Review this section to find the answer."


@app.route("/api/notes/chat", methods=["POST"])
@supabase_auth_required
@account_not_frozen
def chat_with_notes():
    """
    Conversational AI chat with memory - students can have back-and-forth discussions

    Expects JSON:
    {
        "message": "How does DNA replicate?",
        "conversation_id": "optional-uuid" // omit to start new conversation
    }

    Returns:
    {
        "conversation_id": "uuid",
        "response": "DNA replicates through semiconservative replication...",
        "sources": [
            {
                "filename": "DNA.txt (Wikipedia - Biology)",
                "similarity": 0.89
            }
        ]
    }
    """
    try:
        from StudyFlow.backend.supabase_client import search_notes_vector, get_user_profile, supabase, log_ai_response
        from StudyFlow.backend.embedding_client import generate_embedding
        from StudyFlow.backend.conversational_noteflow import (
            create_conversation,
            get_conversation,
            get_conversation_messages,
            add_message,
            generate_conversational_response,
            generate_conversation_title,
            update_conversation_title
        )

        data = request.get_json()
        if not data or not data.get('message'):
            return jsonify({"error": "Missing message"}), 400

        message = data.get('message')
        conv_id = data.get('conversation_id')
        search_scope = data.get('search_scope', 'all')  # 'personal' or 'all'
        source = data.get('source', 'chat')  # 'chat' or 'plugin'

        # Get or create conversation
        if conv_id:
            conversation = get_conversation(conv_id, request.user_id)
            if not conversation:
                return jsonify({"error": "Conversation not found or access denied"}), 404
        else:
            conv_id = create_conversation(request.user_id, source=source)
            conversation = get_conversation(conv_id, request.user_id)

        debug_log(f"💬 Chat message in conversation {conv_id}: '{message[:50]}...'")

        # Get user's university from their account settings (MSU Lane prioritization)
        user_university = None
        try:
            # First, try to get university from user profile (account settings)
            from StudyFlow.backend.supabase_client import get_user_profile
            user_profile = get_user_profile(request.user_id)

            if user_profile and user_profile.get('university'):
                user_university = user_profile.get('university')
                debug_log(f"🎓 User's university from profile: {user_university}")
            else:
                # Fallback: Infer from their most common note university
                user_notes = supabase.table("notes").select("university").eq("user_id", request.user_id).execute()
                if user_notes.data:
                    from collections import Counter
                    universities = [n.get('university') for n in user_notes.data if n.get('university')]
                    if universities:
                        user_university = Counter(universities).most_common(1)[0][0]
                        debug_log(f"🎓 User's university inferred from notes: {user_university}")
        except Exception as e:
            debug_log(f"⚠️ Could not determine user university: {e}")

        # Generate embedding for the question
        query_embedding = generate_embedding(message)
        if not query_embedding:
            return jsonify({"error": "Failed to generate query embedding"}), 500

        # Search database for relevant content (increased count for consensus)
        search_results = search_notes_vector(
            query_embedding=query_embedding,
            user_id=request.user_id,
            university=None,  # Not filtering, just using for prioritization
            course_code=None,
            match_threshold=0.4,
            match_count=15  # Increased from 5 to show more sources for consensus
        )

        debug_log(f"🔍 Found {len(search_results) if search_results else 0} relevant chunks")

        # Prioritize results from same university (MSU Lane)
        if user_university and search_results:
            same_uni = [r for r in search_results if r.get('university') == user_university]
            diff_uni = [r for r in search_results if r.get('university') != user_university]
            search_results = same_uni + diff_uni
            debug_log(f"🎯 Prioritized {len(same_uni)} results from {user_university}")

        # Filter to personal notes only if requested
        if search_scope == 'personal' and search_results:
            note_ids = list(set(r['note_id'] for r in search_results))
            ownership = supabase.table("notes").select("id, user_id").in_("id", note_ids).execute()
            personal_note_ids = set(n['id'] for n in ownership.data if n['user_id'] == request.user_id)
            search_results = [r for r in search_results if r['note_id'] in personal_note_ids]
            debug_log(f"Filtered to {len(search_results)} personal chunks")

        # Apply voting-based ranking to boost helpful notes and demote unhelpful ones
        if search_results:
            from collections import defaultdict

            # Get all unique note IDs from search results
            note_ids_in_results = list(set(r['note_id'] for r in search_results))

            # Fetch all ratings for these notes
            ratings = supabase.table("ai_response_ratings").select("cited_note_ids, vote").execute()

            # Calculate helpfulness score for each note
            note_votes = defaultdict(lambda: {"upvotes": 0, "downvotes": 0})
            for rating in ratings.data:
                cited_note_ids = rating.get('cited_note_ids', [])
                vote = rating.get('vote', 0)

                for note_id in cited_note_ids:
                    if note_id in note_ids_in_results:
                        if vote == 1:
                            note_votes[note_id]["upvotes"] += 1
                        elif vote == -1:
                            note_votes[note_id]["downvotes"] += 1

            # Apply weighted ranking: Similarity (70%) + Helpfulness (30%)
            for result in search_results:
                note_id = result['note_id']
                votes = note_votes[note_id]
                upvotes = votes["upvotes"]
                downvotes = votes["downvotes"]

                # Helpfulness score: (upvotes - downvotes) / (total_votes + 5)
                # The +5 prevents new notes from being over-penalized
                total_votes = upvotes + downvotes
                if total_votes > 0:
                    helpfulness_score = (upvotes - downvotes) / (total_votes + 5)
                else:
                    helpfulness_score = 0  # Neutral for unvoted notes

                # Normalize helpfulness to 0-1 range (assuming score will be between -1 and 1)
                normalized_helpfulness = (helpfulness_score + 1) / 2

                # Combined score: 70% similarity + 30% helpfulness
                similarity = result.get('similarity', 0)
                combined_score = (similarity * 0.7) + (normalized_helpfulness * 0.3)

                result['combined_score'] = combined_score
                result['helpfulness_score'] = helpfulness_score
                result['vote_data'] = {"upvotes": upvotes, "downvotes": downvotes}

            # Re-sort by combined score
            search_results.sort(key=lambda x: x.get('combined_score', 0), reverse=True)

            debug_log(f"🎯 Applied voting-based ranking to {len(search_results)} results")
            for i, r in enumerate(search_results[:5]):
                debug_log(f"  #{i+1}: similarity={r.get('similarity', 0):.2f}, helpfulness={r.get('helpfulness_score', 0):.2f}, combined={r.get('combined_score', 0):.2f}, votes={r.get('vote_data')}")

        # Add search result metadata and enrich with missing fields (CONSENSUS: show all sources)
        sources = []
        seen_note_ids = set()
        if search_results:
            for result in search_results:  # Deduplicate by note_id, show ALL for consensus
                if result['note_id'] in seen_note_ids:
                    continue
                seen_note_ids.add(result['note_id'])
                # REMOVED 3-source limit to show consensus from multiple students
                note_result = supabase.table("notes").select("original_filename, user_id, university, course_code").eq("id", result['note_id']).execute()
                note_data = note_result.data[0] if note_result.data else {}
                filename = note_data.get('original_filename', 'Unknown')

                # Enrich result with username if missing from chunk
                if not result.get('username') and note_data.get('user_id'):
                    try:
                        profile_result = supabase.table("user_profiles").select("username").eq("id", note_data['user_id']).execute()
                        if profile_result.data and profile_result.data[0].get("username"):
                            result['username'] = profile_result.data[0]['username']
                    except Exception:
                        pass

                # Enrich university/course_code from notes table if missing from chunk
                if not result.get('university') and note_data.get('university'):
                    result['university'] = note_data['university']
                if not result.get('course_code') and note_data.get('course_code'):
                    result['course_code'] = note_data['course_code']

                # Detect Wikipedia sources and build URL
                is_wikipedia = result.get('university') == 'Wikipedia' or (note_data.get('university') == 'Wikipedia')
                wikipedia_url = None
                if is_wikipedia and filename.endswith('.txt'):
                    article_title = filename.replace('.txt', '')
                    wikipedia_url = f"https://en.wikipedia.org/wiki/{article_title.replace(' ', '_')}"

                sources.append({
                    "note_id": result['note_id'],
                    "filename": f"{filename} ({result['university']} - {result['course_code']})" if result.get('university') and not is_wikipedia else filename,
                    "similarity": round(result['similarity'], 2),
                    "username": result.get('username'),
                    "university": result.get('university'),
                    "course_code": result.get('course_code'),
                    "from_wikipedia": is_wikipedia,
                    "wikipedia_url": wikipedia_url
                })
                # Add original_filename to result for context
                result['original_filename'] = filename

        # Add user message to conversation
        add_message(conv_id, 'user', message)

        # Get conversation history from database
        conversation_history = get_conversation_messages(conv_id, request.user_id)

        # Generate conversational AI response
        ai_result = generate_conversational_response(
            question=message,
            search_results=search_results or [],
            conversation_history=conversation_history
        )

        ai_response = ai_result["response"]
        model_used = ai_result["model_used"]
        response_time_ms = ai_result["response_time_ms"]

        # Add AI response to conversation
        add_message(conv_id, 'assistant', ai_response, sources)

        # SB 1324 Provenance Logging - log every AI response for 7-year retention
        try:
            source_log_entries = []
            for s in sources:
                source_log_entries.append({
                    "note_id": s.get("note_id"),
                    "filename": s.get("filename"),
                    "similarity": s.get("similarity"),
                    "contributor_username": s.get("username"),
                    "source_type": "nexus_note"
                })

            client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
            if client_ip and ',' in client_ip:
                client_ip = client_ip.split(',')[0].strip()

            log_ai_response(
                user_id=request.user_id,
                conversation_id=conv_id,
                prompt_text=message,
                response_text=ai_response,
                sources_used=source_log_entries,
                model_used=model_used,
                response_time_ms=response_time_ms,
                ip_address=client_ip
            )
        except Exception as log_error:
            debug_log(f"[-] Provenance logging failed (non-blocking): {log_error}")

        # Notify note owners when their note is cited in chat
        try:
            from datetime import datetime, timedelta
            for src in sources:
                src_note_id = src.get("note_id")
                if not src_note_id:
                    continue
                # Look up the note owner
                note_row = supabase.table("notes").select("user_id, original_filename").eq("id", src_note_id).execute()
                if not note_row.data:
                    continue
                owner_id = note_row.data[0].get("user_id")
                if not owner_id or owner_id == request.user_id:
                    continue
                # Skip duplicate citation notifications within 24 hours
                cutoff = (datetime.utcnow() - timedelta(hours=24)).isoformat()
                existing = supabase.table("notifications") \
                    .select("id") \
                    .eq("user_id", owner_id) \
                    .eq("type", "note_cited") \
                    .eq("note_id", src_note_id) \
                    .gte("created_at", cutoff) \
                    .limit(1) \
                    .execute()
                if existing.data:
                    continue
                fname = note_row.data[0].get("original_filename", "your note")
                create_notification(
                    user_id=owner_id,
                    notif_type="note_cited",
                    title="Note Cited",
                    message=f"Your note {fname} was cited in a chat",
                    note_id=src_note_id,
                )
        except Exception as notif_err:
            debug_log(f"[-] Citation notification failed (non-blocking): {notif_err}")

        # Generate title for new conversations (if title is still None)
        if conversation and not conversation.get('title'):
            try:
                title = generate_conversation_title(message, ai_response)
                update_conversation_title(conv_id, title)
                debug_log(f"[+] Auto-generated title: {title}")
            except Exception as title_error:
                debug_log(f"[!] Failed to generate title: {title_error}")

        debug_log(f"[+] Generated conversational response ({len(ai_response)} chars, {response_time_ms}ms)")

        return jsonify({
            "conversation_id": conv_id,
            "response": ai_response,
            "sources": sources
        }), 200

    except Exception as e:
        debug_log(f"Chat error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/conversations", methods=["GET"])
@supabase_auth_required
def list_conversations():
    """
    List all conversations for the authenticated user

    Returns:
    {
        "conversations": [
            {
                "id": "uuid",
                "title": "First question snippet...",
                "created_at": "2026-03-21T10:00:00Z",
                "updated_at": "2026-03-21T10:05:00Z"
            }
        ]
    }
    """
    try:
        from StudyFlow.backend.conversational_noteflow import list_user_conversations

        conversations = list_user_conversations(request.user_id, limit=50)

        return jsonify({"conversations": conversations}), 200

    except Exception as e:
        debug_log(f"❌ Error listing conversations: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/conversations/<conversation_id>/messages", methods=["GET"])
@supabase_auth_required
def get_conversation_history(conversation_id):
    """
    Get all messages in a specific conversation

    Returns:
    {
        "messages": [
            {
                "id": "uuid",
                "role": "user",
                "content": "What is DNA?",
                "created_at": "2026-03-21T10:00:00Z"
            },
            {
                "id": "uuid",
                "role": "assistant",
                "content": "DNA is...",
                "sources": [...],
                "created_at": "2026-03-21T10:00:05Z"
            }
        ]
    }
    """
    try:
        from StudyFlow.backend.conversational_noteflow import get_conversation_messages

        # get_conversation_messages already verifies ownership
        messages = get_conversation_messages(conversation_id, request.user_id)

        if messages is None:
            return jsonify({"error": "Conversation not found or access denied"}), 404

        return jsonify({"messages": messages}), 200

    except Exception as e:
        debug_log(f"❌ Error getting conversation history: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/conversations/<conversation_id>", methods=["DELETE"])
@supabase_auth_required
def delete_conversation_endpoint(conversation_id):
    """
    Delete a conversation and all its messages

    Returns:
    {
        "success": true
    }
    """
    try:
        from StudyFlow.backend.conversational_noteflow import delete_conversation

        success = delete_conversation(conversation_id, request.user_id)

        if success:
            return jsonify({"success": True}), 200
        else:
            return jsonify({"error": "Conversation not found or access denied"}), 404

    except Exception as e:
        debug_log(f"❌ Error deleting conversation: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat/rate-response", methods=["POST", "OPTIONS"])
@supabase_auth_required
def rate_chat_response():
    """
    Rate the helpfulness of sources cited in an AI response

    Expects:
    {
        "message_id": "uuid",
        "conversation_id": "uuid",
        "vote": 1 or -1,  # 1 = helpful (upvote), -1 = not helpful (downvote)
        "cited_note_ids": ["note_id1", "note_id2", ...]  # Notes that were cited
    }

    Returns:
    {
        "success": true,
        "vote": 1
    }
    """
    # Handle OPTIONS preflight
    if request.method == 'OPTIONS':
        return '', 200

    try:
        data = request.get_json()
        message_id = data.get('message_id')
        conversation_id = data.get('conversation_id')
        vote = data.get('vote')  # 1 or -1
        cited_note_ids = data.get('cited_note_ids', [])

        if not all([message_id, conversation_id, vote in [1, -1]]):
            return jsonify({"error": "Missing required fields"}), 400

        # Check if user already voted on this response
        existing = supabase.table("ai_response_ratings").select("id, vote").eq("message_id", message_id).eq("user_id", request.user_id).execute()

        if existing.data:
            # Update existing vote
            supabase.table("ai_response_ratings").update({
                "vote": vote
            }).eq("id", existing.data[0]['id']).execute()

            debug_log(f"[+] Updated response rating: message={message_id}, user={request.user_id}, vote={vote}")
        else:
            # Create new vote
            supabase.table("ai_response_ratings").insert({
                "message_id": message_id,
                "conversation_id": conversation_id,
                "user_id": request.user_id,
                "vote": vote,
                "cited_note_ids": cited_note_ids
            }).execute()

            debug_log(f"[+] Created response rating: message={message_id}, user={request.user_id}, vote={vote}")

        return jsonify({"success": True, "vote": vote}), 200

    except Exception as e:
        debug_log(f"❌ Error rating response: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/chat/get-my-vote", methods=["GET", "OPTIONS"])
@supabase_auth_required
def get_my_response_vote():
    """
    Get user's existing vote for a message

    Query params: message_id

    Returns:
    {
        "vote": 1 or -1 or null
    }
    """
    # Handle OPTIONS preflight
    if request.method == 'OPTIONS':
        return '', 200

    try:
        message_id = request.args.get('message_id')
        if not message_id:
            return jsonify({"error": "Missing message_id"}), 400

        result = supabase.table("ai_response_ratings").select("vote").eq("message_id", message_id).eq("user_id", request.user_id).execute()

        if result.data:
            return jsonify({"vote": result.data[0]['vote']}), 200
        else:
            return jsonify({"vote": None}), 200

    except Exception as e:
        debug_log(f"❌ Error getting vote: {e}\n{traceback.format_exc()}")
        return jsonify({"vote": None}), 200


@app.route("/api/settings/collective-brain", methods=["GET"])
@supabase_auth_required
def get_collective_brain_setting():
    """
    Get the user's collective brain opt-in setting.
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        user = supabase.table("user_profiles").select("collective_brain_opt_in").eq("id", request.user_id).single().execute()

        if not user.data:
            return jsonify({"error": "User not found"}), 404

        return jsonify({"enabled": user.data.get('collective_brain_opt_in', True)}), 200

    except Exception as e:
        debug_log(f"Error getting collective brain setting: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/settings/collective-brain", methods=["POST"])
@supabase_auth_required
def update_collective_brain_setting():
    """
    Update the user's collective brain opt-in setting.

    If disabled (opt-out):
    - User can ONLY see their own notes
    - User's notes are NOT shared with others

    If enabled (opt-in):
    - User can see their own notes + everyone else's notes
    - User's notes are shared with everyone
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        data = request.get_json()
        enabled = data.get('enabled', True)

        # Update user setting
        supabase.table("user_profiles").update({
            "collective_brain_opt_in": enabled
        }).eq("id", request.user_id).execute()

        debug_log(f"✅ User {request.user_id} set collective_brain_opt_in to {enabled}")

        return jsonify({"success": True, "enabled": enabled}), 200

    except Exception as e:
        debug_log(f"❌ Error updating collective brain setting: {e}")
        return jsonify({"error": str(e)}), 500


# ============ FOLDER ENDPOINTS ============

@app.route("/api/folders/list", methods=["GET"])
@supabase_auth_required
def list_folders():
    """Get all folders for current user"""
    try:
        from StudyFlow.backend.supabase_client import get_user_folders

        folders = get_user_folders(request.user_id)
        return jsonify(folders), 200

    except Exception as e:
        debug_log(f"Error listing folders: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/folders/create", methods=["POST"])
@supabase_auth_required
def create_folder_endpoint():
    """
    Create a new folder.
    Request body: {
        "name": "Folder Name",
        "parent_id": "uuid" (optional),
        "color": "#7c9885" (optional),
        "position_data": {"x": 20, "y": 20} (optional)
    }
    """
    try:
        from StudyFlow.backend.supabase_client import create_folder

        data = request.get_json()
        name = data.get('name')

        if not name:
            return jsonify({"error": "Folder name is required"}), 400

        folder = create_folder(
            user_id=request.user_id,
            name=name,
            parent_id=data.get('parent_id'),
            color=data.get('color', '#7c9885'),
            position_data=data.get('position_data')
        )

        if folder:
            return jsonify(folder), 201
        else:
            return jsonify({"error": "Failed to create folder"}), 500

    except Exception as e:
        debug_log(f"Error creating folder: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/folders/<folder_id>", methods=["PUT"])
@supabase_auth_required
def update_folder_endpoint(folder_id):
    """
    Update a folder (rename, move, change color, update position).
    Request body: {
        "name": "New Name" (optional),
        "parent_id": "uuid" (optional),
        "color": "#7c9885" (optional),
        "position_data": {"x": 100, "y": 200} (optional)
    }
    """
    try:
        from StudyFlow.backend.supabase_client import update_folder

        data = request.get_json()

        # Build updates dict from provided fields
        updates = {}
        if 'name' in data:
            updates['name'] = data['name']
        if 'parent_id' in data:
            updates['parent_id'] = data['parent_id']
        if 'color' in data:
            updates['color'] = data['color']
        if 'position_data' in data:
            updates['position_data'] = data['position_data']

        if not updates:
            return jsonify({"error": "No updates provided"}), 400

        folder = update_folder(folder_id, request.user_id, updates)

        if folder:
            return jsonify(folder), 200
        else:
            return jsonify({"error": "Folder not found or unauthorized"}), 404

    except Exception as e:
        debug_log(f"Error updating folder: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/folders/<folder_id>", methods=["DELETE"])
@supabase_auth_required
def delete_folder_endpoint(folder_id):
    """Delete a folder (CASCADE moves children to parent)"""
    try:
        from StudyFlow.backend.supabase_client import delete_folder

        success = delete_folder(folder_id, request.user_id)

        if success:
            return jsonify({"success": True}), 200
        else:
            return jsonify({"error": "Folder not found or unauthorized"}), 404

    except Exception as e:
        debug_log(f"Error deleting folder: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/<note_id>/folder", methods=["PUT"])
@supabase_auth_required
def move_note_to_folder_endpoint(note_id):
    """
    Assign a note to a folder (or remove from folder).
    Request body: {
        "folder_id": "uuid" (or null to remove from folder)
    }
    """
    try:
        from StudyFlow.backend.supabase_client import update_note_folder

        data = request.get_json()
        folder_id = data.get('folder_id')  # Can be None

        success = update_note_folder(note_id, request.user_id, folder_id)

        if success:
            return jsonify({"success": True}), 200
        else:
            return jsonify({"error": "Note not found or unauthorized"}), 404

    except Exception as e:
        debug_log(f"Error moving note to folder: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500




@app.route("/api/notes/browse", methods=["GET"])
@supabase_auth_required
def browse_notes():
    """
    Browse public notes in the Nexus (requires .edu verification)

    Query params:
    - university: Filter by university
    - course_code: Filter by course
    - topic_tags: Comma-separated tags
    - sort: 'recent', 'popular', 'views'
    - limit: Default 50

    Returns:
    {
        "notes": [...]
    }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        user_id = request.user_id

        # Check .edu email verification requirement
        user_profile = supabase.table("user_profiles").select("edu_email_verified").eq("id", user_id).single().execute()
        if user_profile.data:
            edu_verified = user_profile.data.get('edu_email_verified', False)
            if not edu_verified:
                return jsonify({"error": "Browse requires a verified .edu email address"}), 403
        else:
            return jsonify({"error": "User profile not found"}), 404

        # Get query parameters
        university = request.args.get('university')
        course_code = request.args.get('course_code')
        topic_tags_str = request.args.get('topic_tags', '')
        topic_tags = [tag.strip() for tag in topic_tags_str.split(',') if tag.strip()] if topic_tags_str else []
        sort_by = request.args.get('sort', 'recent')
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))

        # Build query (removed username - use user_id instead)
        # Exclude Wikipedia notes (user_id is NULL)
        query = supabase.table("notes").select(
            "id, original_filename, university, course_code, user_id, topic_tags, page_count, uploaded_at"
        ).eq("is_public", True).not_.is_("user_id", "null")

        if university:
            query = query.eq("university", university)
        if course_code:
            query = query.eq("course_code", course_code)

        # Execute query with pagination
        response = query.order("uploaded_at", desc=True).range(offset, offset + limit - 1).execute()
        notes = response.data if response.data else []

        # Filter notes by user's Nexus setting and get usernames
        filtered_notes = []
        for note in notes:
            # Get username AND check if user has Nexus enabled
            try:
                user_profile = supabase.table("user_profiles").select("username, is_public").eq("id", note['user_id']).single().execute()

                if user_profile.data:
                    # Check if user has Nexus enabled (is_public defaults to True if not set)
                    user_is_public = user_profile.data.get('is_public', True)

                    # Only include note if user has Nexus enabled
                    if user_is_public:
                        note['username'] = user_profile.data.get('username') or 'Anonymous'
                        filtered_notes.append(note)
                    else:
                        # User has Nexus disabled, skip this note
                        debug_log(f"Skipping note {note['id']} - user has Nexus disabled")
                        continue
                else:
                    # No profile found, skip
                    continue
            except:
                # Error fetching profile, skip to be safe
                continue

            # Get view count
            try:
                view_count_response = supabase.table("note_views").select("id", count="exact").eq("note_id", note['id']).execute()
                note['view_count'] = view_count_response.count if view_count_response.count else 0
            except:
                note['view_count'] = 0

            # Download count from download_transactions table
            try:
                dl_count_response = supabase.table("download_transactions").select("id", count="exact").eq("note_id", note['id']).execute()
                note['usage_count'] = dl_count_response.count if dl_count_response.count else 0
            except:
                note['usage_count'] = 0

            # Rename original_filename to filename for frontend (with fallback)
            note['filename'] = note.pop('original_filename', note.pop('filename', 'Unknown'))

            # Remove user_id from response
            note.pop('user_id', None)

        # Replace notes with filtered list
        notes = filtered_notes

        # Filter by tags if specified
        if topic_tags:
            notes = [n for n in notes if n.get('topic_tags') and any(tag in n['topic_tags'] for tag in topic_tags)]

        # Sort
        if sort_by == 'popular':
            notes.sort(key=lambda x: x.get('usage_count', 0), reverse=True)
        elif sort_by == 'views':
            notes.sort(key=lambda x: x.get('view_count', 0), reverse=True)
        # 'recent' is already sorted by created_at desc

        debug_log(f"📚 Browse: Found {len(notes)} public notes")

        return jsonify({"notes": notes}), 200

    except Exception as e:
        error_trace = traceback.format_exc()
        debug_log(f"❌ Browse notes error: {e}\n{error_trace}")
        # Return detailed error for debugging
        return jsonify({
            "error": str(e),
            "traceback": error_trace,
            "type": type(e).__name__
        }), 500


@app.route("/api/notes/semantic-browse", methods=["POST"])
@supabase_auth_required
def semantic_browse_notes():
    """
    Semantic search for browse page - returns note metadata + matching paragraphs

    Expects JSON:
    {
        "question": "What is photosynthesis?"
    }

    Returns:
    [
        {
            "note_id": "...",
            "filename": "Biology_Chapter_3.pdf",
            "username": "john_doe",
            "university": "MIT",
            "course_code": "BIO101",
            "created_at": "2024-01-15",
            "content": "Photosynthesis is the process...",
            "similarity": 0.89
        }
    ]
    """
    try:
        from StudyFlow.backend.supabase_client import search_notes_vector, supabase
        from StudyFlow.backend.embedding_client import generate_embedding

        # Check .edu email verification requirement
        user_profile = supabase.table("user_profiles").select("edu_email_verified").eq("id", request.user_id).single().execute()
        if user_profile.data:
            edu_verified = user_profile.data.get('edu_email_verified', False)
            if not edu_verified:
                return jsonify({"error": "Browse requires a verified .edu email address"}), 403
        else:
            return jsonify({"error": "User profile not found"}), 404

        data = request.get_json()
        if not data or not data.get('question'):
            return jsonify({"error": "Missing question"}), 400

        question = data.get('question')
        university_filter = data.get('university')  # Optional university filter
        offset = data.get('offset', 0)  # Pagination offset

        # Generate embedding for the question
        query_embedding = generate_embedding(question)
        if not query_embedding:
            return jsonify({"error": "Failed to generate query embedding"}), 500

        debug_log(f"🔍 Semantic browse search for: '{question}'" + (f" (university: {university_filter})" if university_filter else "") + f" (offset: {offset})")

        # Extract query keywords for filename search
        query_words = set(question.lower().split())
        stopwords = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'what', 'how', 'where', 'when', 'why', 'which', 'who'}
        query_keywords = query_words - stopwords

        # PART 1: Search using pgvector (content similarity)
        search_results = search_notes_vector(
            query_embedding=query_embedding,
            user_id=request.user_id,
            university=university_filter,
            course_code=None,
            match_threshold=0.4,
            match_count=50
        )

        # PART 2: Search by filename (title matching)
        filename_results = []
        if query_keywords:
            try:
                # Build query to search filenames
                query_builder = supabase.table("notes").select("id, original_filename, university, course_code, user_id, uploaded_at")

                # Apply university filter if provided
                if university_filter:
                    query_builder = query_builder.eq("university", university_filter)

                # Get all public notes
                all_notes = query_builder.execute()

                # Filter by filename matching any query keyword
                for note_data in all_notes.data:
                    filename_lower = note_data['original_filename'].lower()
                    # Check if any keyword is in the filename
                    matches = sum(1 for keyword in query_keywords if keyword in filename_lower)
                    if matches > 0:
                        # Check if user has Nexus enabled
                        try:
                            user_profile = supabase.table("user_profiles").select("username, is_public").eq("id", note_data['user_id']).single().execute()
                            if user_profile.data and user_profile.data.get('is_public', True):
                                filename_results.append({
                                    'note_id': note_data['id'],
                                    'note_data': note_data,
                                    'username': user_profile.data.get('username') or 'Anonymous',
                                    'keyword_matches': matches
                                })
                        except:
                            continue

                debug_log(f"📁 Filename search: Found {len(filename_results)} notes with matching titles")
            except Exception as e:
                debug_log(f"⚠️ Filename search error: {e}")
                filename_results = []

        # Format results with note metadata
        formatted_results = []
        seen_notes = set()  # Track unique notes

        # Add vector search results
        for result in search_results:
            note_id = result['note_id']

            # Skip duplicates (same note, different chunks)
            if note_id in seen_notes:
                continue
            seen_notes.add(note_id)

            # Get note metadata
            note_data = supabase.table("notes").select(
                "id, original_filename, university, course_code, user_id, uploaded_at"
            ).eq("id", note_id).single().execute()

            if not note_data.data:
                continue

            note = note_data.data

            # Get username
            try:
                user_profile = supabase.table("user_profiles").select("username, is_public").eq("id", note['user_id']).single().execute()
                if not user_profile.data or not user_profile.data.get('is_public', True):
                    continue  # Skip if user has Nexus disabled
                username = user_profile.data.get('username') or 'Anonymous'
            except:
                continue

            # Use content_summary if available, otherwise chunk_text
            content = result.get('content_summary') or result.get('chunk_text', '')

            # Get upvote count from ai_response_ratings
            try:
                ratings = supabase.table("ai_response_ratings").select("vote, cited_note_ids").execute()
                upvotes = 0
                downvotes = 0

                if ratings.data:
                    for rating in ratings.data:
                        cited_note_ids = rating.get('cited_note_ids', [])
                        if note_id in cited_note_ids:
                            vote = rating.get('vote', 0)
                            if vote == 1:
                                upvotes += 1
                            elif vote == -1:
                                downvotes += 1

                net_upvotes = upvotes - downvotes
            except:
                net_upvotes = 0

            formatted_results.append({
                "note_id": note_id,
                "filename": note['original_filename'],
                "username": username,
                "university": note.get('university', 'Unknown'),
                "course_code": note.get('course_code', ''),
                "created_at": note.get('uploaded_at', ''),
                "content": content,
                "similarity": round(result['similarity'], 2),
                "upvotes": net_upvotes,
                "raw_upvotes": upvotes,
                "raw_downvotes": downvotes
            })

        # Add filename search results (not already in vector results)
        for filename_result in filename_results:
            note_id = filename_result['note_id']

            if note_id in seen_notes:
                continue  # Already got this note from vector search
            seen_notes.add(note_id)

            note_data = filename_result['note_data']

            # Get upvote count
            try:
                ratings = supabase.table("ai_response_ratings").select("vote, cited_note_ids").execute()
                upvotes = 0
                downvotes = 0

                if ratings.data:
                    for rating in ratings.data:
                        cited_note_ids = rating.get('cited_note_ids', [])
                        if note_id in cited_note_ids:
                            vote = rating.get('vote', 0)
                            if vote == 1:
                                upvotes += 1
                            elif vote == -1:
                                downvotes += 1

                net_upvotes = upvotes - downvotes
            except:
                net_upvotes = 0
                upvotes = 0
                downvotes = 0

            # Add to results with low similarity (since it didn't match content)
            formatted_results.append({
                "note_id": note_id,
                "filename": note_data['original_filename'],
                "username": filename_result['username'],
                "university": note_data.get('university', 'Unknown'),
                "course_code": note_data.get('course_code', ''),
                "created_at": note_data.get('uploaded_at', ''),
                "content": f"File matches your search: {note_data['original_filename']}",
                "similarity": 0.3,  # Low base similarity for title-only matches
                "upvotes": net_upvotes,
                "raw_upvotes": upvotes,
                "raw_downvotes": downvotes
            })

        debug_log(f"✅ Semantic browse: Found {len(formatted_results)} unique notes ({len(search_results)} from content, {len(filename_results)} from titles)")

        # Apply weighted ranking: similarity + upvote helpfulness + title match boost
        if formatted_results:

            for note in formatted_results:
                similarity = note['similarity']
                upvotes = note['raw_upvotes']
                downvotes = note['raw_downvotes']
                total_votes = upvotes + downvotes
                filename = note['filename'].lower()

                # Calculate helpfulness score
                # Normalize: (upvotes - downvotes) / (total_votes + 5)
                # The +5 prevents new notes from being penalized
                if total_votes > 0:
                    helpfulness_score = (upvotes - downvotes) / (total_votes + 5)
                else:
                    helpfulness_score = 0

                # Normalize to 0-1 range
                normalized_helpfulness = (helpfulness_score + 1) / 2

                # Calculate title match score
                title_match_count = 0
                for keyword in query_keywords:
                    if keyword in filename:
                        title_match_count += 1

                # Title match boost: percentage of query keywords found in title
                if query_keywords:
                    title_match_score = title_match_count / len(query_keywords)
                else:
                    title_match_score = 0

                # Combined score: 60% similarity + 25% helpfulness + 15% title match
                combined_score = (similarity * 0.6) + (normalized_helpfulness * 0.25) + (title_match_score * 0.15)
                note['combined_score'] = round(combined_score, 4)
                note['title_match_score'] = round(title_match_score, 2)

            # Re-sort by combined score
            formatted_results.sort(key=lambda x: x.get('combined_score', 0), reverse=True)

            debug_log(f"📊 Top 5 ranked notes:")
            for i, note in enumerate(formatted_results[:5], 1):
                debug_log(f"  {i}. {note['filename'][:40]} - Combined: {note['combined_score']:.3f} (Sim: {note['similarity']:.2f}, Upvotes: {note['upvotes']}, Title: {note['title_match_score']:.2f})")

        # Apply pagination
        page_size = 10
        start_idx = offset
        end_idx = offset + page_size

        paginated_results = formatted_results[start_idx:end_idx]
        has_more = len(formatted_results) > end_idx

        # Clean up response - remove internal fields
        for note in paginated_results:
            note.pop('raw_upvotes', None)
            note.pop('raw_downvotes', None)
            note.pop('combined_score', None)  # Keep internal ranking score hidden
            note.pop('title_match_score', None)  # Keep title match score hidden

        return jsonify({
            "notes": paginated_results,
            "has_more": has_more,
            "total": len(formatted_results)
        }), 200

    except Exception as e:
        debug_log(f"❌ Semantic browse error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/topic-tags", methods=["GET"])
@supabase_auth_required
def get_topic_tags():
    """
    Get all unique topic tags from public notes

    Returns:
    {
        "tags": ["Biology", "Chemistry", ...]
    }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        # Get all public notes with topic tags
        response = supabase.table("notes").select("topic_tags").eq("is_public", True).execute()
        notes = response.data if response.data else []

        # Extract unique tags
        all_tags = set()
        for note in notes:
            if note.get('topic_tags'):
                for tag in note['topic_tags']:
                    all_tags.add(tag)

        # Sort alphabetically
        tags = sorted(list(all_tags))

        debug_log(f"🏷️ Found {len(tags)} unique topic tags")

        return jsonify({"tags": tags}), 200

    except Exception as e:
        debug_log(f"❌ Get topic tags error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/dmca/takedown", methods=["POST"])
def submit_takedown_request():
    """
    Submit a DMCA takedown request (no auth required for public access)

    Body:
    {
        "requestor_name": "John Doe",
        "requestor_email": "john@example.com",
        "requestor_type": "professor",
        "note_filename": "Biology_Chapter_3.pdf",
        "complaint_description": "...",
        "evidence_urls": ["https://..."],
        "good_faith": true,
        "accuracy": true
    }

    Returns:
    {
        "success": true,
        "request_id": "DMCA-20260322-001"
    }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        from datetime import datetime

        data = request.json

        # Validate required fields
        required_fields = ['requestor_name', 'requestor_email', 'requestor_type', 'note_filename', 'complaint_description', 'good_faith', 'accuracy']
        for field in required_fields:
            if field not in data:
                return jsonify({"error": f"Missing required field: {field}"}), 400

        if not data['good_faith'] or not data['accuracy']:
            return jsonify({"error": "You must agree to the good faith and accuracy statements"}), 400

        # Generate unique request ID
        today = datetime.now().strftime("%Y%m%d")

        # Count today's requests to get next number
        count_response = supabase.table("dmca_takedown_requests").select("id", count="exact").like("request_id", f"DMCA-{today}-%").execute()
        next_num = (count_response.count if count_response.count else 0) + 1
        request_id = f"DMCA-{today}-{next_num:03d}"

        # Insert into database
        evidence_urls = data.get('evidence_urls', [])
        if isinstance(evidence_urls, str):
            evidence_urls = [url.strip() for url in evidence_urls.split('\n') if url.strip()]

        supabase.table("dmca_takedown_requests").insert({
            "request_id": request_id,
            "requestor_name": data['requestor_name'],
            "requestor_email": data['requestor_email'],
            "requestor_type": data['requestor_type'],
            "note_filename": data['note_filename'],
            "complaint_description": data['complaint_description'],
            "evidence_urls": evidence_urls,
            "copyright_claim": True,
            "status": "pending"
        }).execute()

        debug_log(f"📋 DMCA takedown request submitted: {request_id}")

        # Send email notification to admin
        send_dmca_report_notification_to_admin(
            takedown_id=request_id,
            note_filename=data['note_filename'],
            reporter_email=data['requestor_email'],
            reason=data['complaint_description'][:200]
        )

        return jsonify({
            "success": True,
            "request_id": request_id
        }), 200

    except Exception as e:
        debug_log(f"❌ DMCA takedown error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/newsletter/subscribe", methods=["POST"])
def newsletter_subscribe():
    """
    Subscribe an email to the newsletter (no auth required).

    Body: { "email": "user@example.com" }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        data = request.json
        email = data.get('email', '').strip().lower()

        if not email or '@' not in email:
            return jsonify({"error": "Valid email address required"}), 400

        # Upsert so duplicate emails don't cause errors
        supabase.table("newsletter_subscribers").upsert({
            "email": email
        }, on_conflict="email").execute()

        debug_log(f"Newsletter subscription: {email}")

        return jsonify({"success": True}), 200

    except Exception as e:
        debug_log(f"Newsletter subscribe error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/<note_id>/view", methods=["POST"])
@supabase_auth_required
def track_note_view(note_id):
    """
    Track when a user views a note (for analytics)

    Returns:
    {
        "success": true
    }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        user_id = request.user_id

        # Get IP address
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ',' in ip_address:
            ip_address = ip_address.split(',')[0].strip()

        # Insert view record
        supabase.table("note_views").insert({
            "user_id": user_id,
            "note_id": note_id,
            "ip_address": ip_address
        }).execute()

        debug_log(f"👁️ Note view tracked: {note_id}")

        return jsonify({"success": True}), 200

    except Exception as e:
        debug_log(f"❌ Track view error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/consent-log", methods=["POST"])
@supabase_auth_required
def log_consent():
    """
    Log a click-wrap consent receipt (Missouri HB 2271, SB 1324, DMCA compliance).
    Stores user_id, file_id, legal_version, timestamp, and IP for AG audit trail.
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        data = request.get_json()
        if not data:
            return jsonify({"error": "Missing request body"}), 400

        file_id = data.get('file_id', '')
        legal_version = data.get('legal_version', '')
        action = data.get('action', 'download_consent')

        if not file_id or not legal_version:
            return jsonify({"error": "file_id and legal_version are required"}), 400

        # Get IP address
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip_address and ',' in ip_address:
            ip_address = ip_address.split(',')[0].strip()

        user_agent = request.headers.get('User-Agent', '')

        supabase.table("consent_logs").insert({
            "user_id": request.user_id,
            "file_id": str(file_id),
            "legal_version": legal_version,
            "action": action,
            "ip_address": ip_address,
            "user_agent": user_agent
        }).execute()

        debug_log(f"[+] Consent logged: user={request.user_id}, file={file_id}, version={legal_version}")

        return jsonify({"status": "logged"}), 200

    except Exception as e:
        debug_log(f"[-] Consent log error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/<note_id>/metadata", methods=["GET"])
@supabase_auth_required
def get_note_metadata(note_id):
    """
    Get note metadata for viewing

    Returns:
    {
        "note": {
            "id": "...",
            "filename": "...",
            "file_type": "pdf|image|document|text|other",
            "university": "...",
            "course_code": "...",
            "username": "...",
            "page_count": 12
        }
    }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        import os

        # Get note details - check if public OR owned by current user
        note_response = supabase.table("notes").select(
            "id, original_filename, file_type, university, course_code, user_id, page_count, is_public"
        ).eq("id", note_id).execute()

        if not note_response.data:
            return jsonify({"error": "Note not found"}), 404

        note_data = note_response.data[0]

        # Check if user has access (either public or owns it)
        is_public = note_data.get('is_public', False)
        is_owner = note_data.get('user_id') == request.user_id

        if not is_public and not is_owner:
            return jsonify({"error": "Note not found or not public"}), 404

        # Get filename and file type
        filename = note_data.get('original_filename') or note_data.get('filename') or 'unknown.pdf'

        # Use stored file_type from database (more reliable than extension)
        stored_file_type = note_data.get('file_type', '').lower()

        # Map stored file_type to viewer format
        if stored_file_type == 'pdf':
            file_type = 'pdf'
        elif stored_file_type in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'image']:
            file_type = 'image'
        elif stored_file_type in ['doc', 'docx', 'odt', 'document']:
            file_type = 'document'
        elif stored_file_type in ['txt', 'md', 'markdown', 'text']:
            file_type = 'text'
        else:
            # Fallback to extension detection if file_type not set
            ext = os.path.splitext(filename)[1].lower()
            if ext in ['.pdf']:
                file_type = 'pdf'
            elif ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp']:
                file_type = 'image'
            elif ext in ['.doc', '.docx', '.odt']:
                file_type = 'document'
            elif ext in ['.txt', '.md', '.markdown']:
                file_type = 'text'
            else:
                file_type = 'other'

        # Get extension for response
        ext = os.path.splitext(filename)[1].lower() if '.' in filename else ''

        # Get username
        try:
            user_profile = supabase.table("user_profiles").select("username").eq("id", note_data['user_id']).single().execute()
            username = user_profile.data['username'] if user_profile.data else 'Anonymous'
        except:
            username = 'Anonymous'

        # Build response
        response_data = {
            "id": note_data['id'],
            "filename": filename,
            "file_type": file_type,
            "extension": ext,
            "university": note_data.get('university'),
            "course_code": note_data.get('course_code'),
            "username": username,
            "page_count": note_data.get('page_count', 0),
            "is_owner": is_owner  # Include ownership status for annotation access control
        }

        return jsonify({"note": response_data}), 200

    except Exception as e:
        debug_log(f"❌ Get note metadata error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/<note_id>/view-file", methods=["GET"])
def view_note_file(note_id):
    """
    Get the file for viewing (PDF, image, document, etc.)
    No auth required since notes are already public - iframes can't send headers
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        from flask import redirect, send_file
        import os

        # Verify note exists and is public
        note = supabase.table("notes").select("id, file_path, original_filename").eq("id", note_id).eq("is_public", True).single().execute()

        if not note.data:
            return jsonify({"error": "Note not found or not public"}), 404

        debug_log(f"View file for note {note_id}: {note.data}")

        # Get signed URL from file_path
        file_url = None
        if note.data.get('file_path'):
            try:
                # Generate signed URL (valid for 1 hour)
                signed_url_response = supabase.storage.from_("note-files").create_signed_url(
                    path=note.data['file_path'],
                    expires_in=3600  # 1 hour
                )
                file_url = signed_url_response['signedURL']
                debug_log(f"Generated signed URL for file_path: {note.data['file_path']}")
            except Exception as storage_error:
                debug_log(f"Storage error with file_path: {storage_error}")

        if file_url:
            debug_log(f"Redirecting to file: {file_url}")
            return redirect(file_url)
        else:
            debug_log(f"No file URL found for note {note_id}. Available fields: {note.data.keys()}")
            return jsonify({"error": "File URL not found", "available_fields": list(note.data.keys())}), 404

    except Exception as e:
        error_trace = traceback.format_exc()
        debug_log(f"❌ View file error: {e}\n{error_trace}")
        return jsonify({"error": str(e), "traceback": error_trace}), 500


@app.route("/api/notes/<note_id>/view-as-images", methods=["GET"])
def view_note_as_images(note_id):
    """
    Convert PDF/DOCX to images for secure viewing (prevents download/print)
    Returns JSON with base64-encoded images for each page
    Auth optional - works for public notes or user's own notes
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        import fitz  # PyMuPDF
        import base64
        from io import BytesIO

        # Check if user is authenticated
        auth_header = request.headers.get('Authorization')
        user_id = None
        if auth_header and auth_header.startswith('Bearer '):
            token = auth_header.split(' ')[1]
            try:
                user_response = supabase.auth.get_user(token)
                if user_response and user_response.user:
                    user_id = user_response.user.id
            except:
                pass

        # Fetch note - either public OR owned by authenticated user
        note_query = supabase.table("notes").select("id, file_path, original_filename, file_type, page_count, user_id, is_public").eq("id", note_id)
        note = note_query.single().execute()

        if not note.data:
            return jsonify({"error": "Note not found"}), 404

        # Check access: must be public OR owned by authenticated user
        is_public = note.data.get('is_public', False)
        note_owner_id = note.data.get('user_id')

        if not is_public and (not user_id or user_id != note_owner_id):
            return jsonify({"error": "Note not found or not public"}), 404

        # Only PDFs can be converted to images
        # Office documents (docx, xlsx, pptx) should be opened in Office editor instead
        file_type = note.data.get('file_type', '').lower()
        if file_type in ['docx', 'xlsx', 'pptx']:
            return jsonify({
                "error": "Office documents cannot be viewed as images",
                "suggestion": "Open this document in StudyFlow Office instead",
                "redirect": f"/office-editor.html?id={note_id}"
            }), 400

        if file_type != 'pdf':
            return jsonify({"error": "Only PDFs can be converted to images"}), 400

        # Download PDF from Supabase storage
        file_path = note.data.get('file_path')
        if not file_path:
            return jsonify({"error": "File path not found"}), 404

        file_data = supabase.storage.from_('note-files').download(file_path)

        # Convert PDF pages to images
        pdf_document = fitz.open(stream=file_data, filetype="pdf")
        images = []

        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            # Render page at 2x resolution for better quality
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_data = pix.tobytes("png")

            # Convert to base64
            img_base64 = base64.b64encode(img_data).decode('utf-8')
            images.append({
                "page": page_num + 1,
                "data": f"data:image/png;base64,{img_base64}"
            })

        pdf_document.close()

        return jsonify({
            "note_id": note_id,
            "filename": note.data.get('original_filename'),
            "total_pages": len(images),
            "images": images
        }), 200

    except Exception as e:
        error_trace = traceback.format_exc()
        debug_log(f"❌ PDF to image conversion error: {e}\n{error_trace}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/<note_id>/download", methods=["GET"])
@supabase_auth_required
def download_note_file(note_id):
    """
    Download a public note file with flattening and watermark.
    REQUIRES GOOD STANDING: Missouri HB 2271 compliance
    NOTE: This is a duplicate endpoint - the one at line 3474 takes precedence
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        from StudyFlow.backend.pdf_flatten import flatten_pdf, flatten_image, can_flatten, convert_to_pdf
        from flask import send_file
        from datetime import date
        import io
        import uuid

        # DAILY DOWNLOAD LIMIT CHECK (3 downloads/day for free users)
        # Fetch user profile to check subscription and download count
        profile_result = supabase.table("user_profiles").select(
            "subscription_tier, subscription_status, daily_downloads_count, daily_downloads_reset_date, good_standing, permanent_bad_standing, last_verified_upload_date"
        ).eq("id", request.user_id).single().execute()
        profile = profile_result.data

        # CHECK: Good standing expires after 30 days without a quality upload (free users only)
        from datetime import datetime, timedelta
        is_scholar_check = (
            profile.get('subscription_tier') == 'pro' and
            profile.get('subscription_status') == 'active'
        )

        if not is_scholar_check and profile.get('good_standing', False):
            last_upload = profile.get('last_verified_upload_date')
            if last_upload:
                try:
                    last_upload_date = datetime.fromisoformat(last_upload.replace('Z', '+00:00'))
                    days_since_upload = (datetime.utcnow().replace(tzinfo=last_upload_date.tzinfo) - last_upload_date).days

                    if days_since_upload > 30:
                        # Revoke good standing - hasn't uploaded in 30+ days
                        supabase.table("user_profiles").update({
                            "good_standing": False
                        }).eq("id", request.user_id).execute()
                        profile['good_standing'] = False
                        debug_log(f"[!] User {request.user_id} lost good standing (no upload for {days_since_upload} days)")
                except Exception as e:
                    debug_log(f"[-] Error checking last upload date: {e}")

        # Check if Scholar's Club member (unlimited downloads)
        is_scholar = (
            profile.get('subscription_tier') == 'pro' and
            profile.get('subscription_status') == 'active'
        )

        if not is_scholar:
            # Free user - enforce 3 downloads per day limit
            today = date.today()
            reset_date = profile.get('daily_downloads_reset_date')
            download_count = profile.get('daily_downloads_count', 0)

            # Reset counter if new day
            if not reset_date or str(reset_date) != str(today):
                supabase.table("user_profiles").update({
                    "daily_downloads_count": 0,
                    "daily_downloads_reset_date": str(today)
                }).eq("id", request.user_id).execute()
                download_count = 0
                debug_log(f"[+] Reset daily download count for user {request.user_id}")

            # Check if at limit
            if download_count >= 3:
                debug_log(f"[!] User {request.user_id} hit daily download limit ({download_count}/3)")
                return jsonify({
                    "error": "Daily download limit reached",
                    "message": "You've used all 3 downloads today. Join Scholar's Club for unlimited downloads!",
                    "limit_reached": True,
                    "downloads_used": download_count,
                    "downloads_limit": 3,
                    "subscribe_url": "https://unclephilburt.github.io/studyflowwebsite/account.html"
                }), 403

        # Verify note exists (check both own notes and public notes)
        result = supabase.table("notes").select("id, file_path, original_filename, user_id").eq("id", note_id).execute()
        note_data = result.data[0] if result.data else None

        if not note_data:
            return jsonify({"error": "Note not found"}), 404

        # Check if note belongs to current user or is public
        is_own_note = note_data.get('user_id') == request.user_id

        # GOOD STANDING CHECK: Only required for downloading OTHER people's notes
        # (Reuse profile fetched earlier for download limit check)
        if not is_own_note:
            # Block if permanently banned
            if profile.get('permanent_bad_standing', False):
                return jsonify({"error": "Account suspended due to DMCA violations"}), 403

            # Check good standing (Scholar's Club members are always in good standing)
            if not is_scholar and not profile.get('good_standing', False):
                return jsonify({
                    "error": "Good Standing required to download notes",
                    "message": "Upload a verified note or subscribe to regain access",
                    "good_standing_required": True
                }), 403

        print(f"[DOWNLOAD] User {request.user_id} downloading {'own' if is_own_note else 'public'} note {note_id}", flush=True)

        file_path = note_data.get('file_path')
        original_filename = note_data.get('original_filename', 'note')

        if not file_path:
            return jsonify({"error": "File not found in storage"}), 404

        # Generate transaction code
        transaction_code = "DL-" + uuid.uuid4().hex[:8]

        # Get uploader's username for watermark
        username = "Public"
        try:
            uploader_id = note_data.get('user_id')
            if uploader_id:
                profile_result = supabase.table("user_profiles").select("username").eq("id", uploader_id).execute()
                if profile_result.data and profile_result.data[0].get("username"):
                    username = profile_result.data[0]["username"]
        except Exception:
            pass

        # Download file from Supabase Storage
        file_data = supabase.storage.from_('note-files').download(file_path)

        # Log download transaction
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip_address and ',' in ip_address:
            ip_address = ip_address.split(',')[0].strip()

        try:
            supabase.table("download_transactions").insert({
                "user_id": request.user_id,
                "note_id": note_id,
                "original_filename": original_filename,
                "transaction_code": transaction_code,
                "ip_address": ip_address,
                "user_agent": request.headers.get('User-Agent', '')
            }).execute()
            debug_log(f"[+] Download transaction logged: {transaction_code}")
        except Exception as tx_err:
            debug_log(f"[-] Failed to log download transaction: {tx_err}")

        # Log HB 2271 certification (Missouri legal compliance)
        try:
            supabase.table("download_certifications").insert({
                "user_id": request.user_id,
                "note_id": note_id,
                "ip_address": ip_address,
                "user_agent": request.headers.get('User-Agent')
            }).execute()
            print(f"[HB 2271] Download certification logged for user {request.user_id}", flush=True)
        except Exception as cert_err:
            debug_log(f"[-] Failed to log download certification: {cert_err}")

        # Flatten and watermark -- everything becomes a PDF
        flattenable, file_type = can_flatten(original_filename)
        name_base = original_filename.rsplit('.', 1)[0] if '.' in original_filename else original_filename

        if flattenable and file_type == 'pdf':
            file_data = flatten_pdf(file_data, username, transaction_code)
        elif flattenable and file_type == 'image':
            file_data = flatten_image(file_data, username, transaction_code)
        else:
            # Legacy file (txt, docx, etc.) -- convert to PDF first, then flatten
            pdf_data, _ = convert_to_pdf(file_data, original_filename)
            if pdf_data:
                file_data = flatten_pdf(pdf_data, username, transaction_code)

        download_name = f"{name_base}_studyflow.pdf"
        mimetype = 'application/pdf'

        # Increment download counter for free users
        if not is_scholar:
            try:
                new_count = (profile.get('daily_downloads_count', 0) or 0) + 1
                supabase.table("user_profiles").update({
                    "daily_downloads_count": new_count
                }).eq("id", request.user_id).execute()
                debug_log(f"[+] User {request.user_id} download count: {new_count}/3")
            except Exception as count_err:
                debug_log(f"[-] Failed to increment download count: {count_err}")

        return send_file(
            io.BytesIO(file_data),
            mimetype=mimetype,
            as_attachment=True,
            download_name=download_name
        )

    except Exception as e:
        debug_log(f"[-] Download file error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ============ SYLLABUS & CALENDAR ENDPOINTS ============

@app.route("/api/syllabus/upload", methods=["POST"])
@supabase_auth_required
def upload_syllabus():
    """
    Upload a course syllabus (PDF/DOCX) and extract calendar events using AI

    Expects multipart/form-data:
    - file: Syllabus PDF or DOCX file
    - course_name: Course name (optional)
    - course_code: Course code (optional)
    - professor_name: Professor name (optional)
    - semester: Semester (optional, e.g., "Fall 2026")

    Returns:
    {
        "syllabus_id": "uuid",
        "events": [{...extracted calendar events...}],
        "message": "Syllabus uploaded and processed"
    }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        from StudyFlow.backend.syllabus_parser import extract_calendar_events, format_event_for_db, validate_event
        import PyPDF2
        import io

        # Get uploaded file
        if 'file' not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({"error": "No file selected"}), 400

        # Get form data
        course_name = request.form.get('course_name', 'Untitled Course')
        course_code = request.form.get('course_code')
        professor_name = request.form.get('professor_name')
        semester = request.form.get('semester')

        # Validate file type
        allowed_extensions = {'.pdf', '.docx', '.doc'}
        file_ext = os.path.splitext(file.filename)[1].lower()
        if file_ext not in allowed_extensions:
            return jsonify({"error": f"File type not supported. Please upload PDF or DOCX. Got: {file_ext}"}), 400

        # Read file content
        file_content = file.read()
        file_size = len(file_content)

        # Extract text from file with robust fallback handling
        extracted_text = ""

        if file_ext == '.pdf':
            try:
                pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_content))
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        extracted_text += page_text + "\n"

                debug_log(f"[PDF] PyPDF2 extracted {len(extracted_text)} chars")

            except Exception as e:
                debug_log(f"[PDF] Extraction error: {e}")
                import traceback
                debug_log(traceback.format_exc())
                return jsonify({
                    "error": f"Failed to process PDF file. Error: {str(e)}"
                }), 500

        elif file_ext in ['.docx', '.doc']:
            try:
                import docx
                doc = docx.Document(io.BytesIO(file_content))
                for paragraph in doc.paragraphs:
                    extracted_text += paragraph.text + "\n"
                # Also extract from tables
                for table in doc.tables:
                    for row in table.rows:
                        for cell in row.cells:
                            extracted_text += cell.text + "\n"
                debug_log(f"[DOCX] Extracted {len(extracted_text)} chars")
            except Exception as e:
                debug_log(f"[DOCX] Extraction error: {e}")
                return jsonify({
                    "error": f"Failed to process DOCX file. The file may be corrupted. Error: {str(e)}"
                }), 500

        # Validate we got meaningful text
        if not extracted_text.strip():
            return jsonify({
                "error": "Could not extract any text from the file. Please ensure the PDF contains text (not just images) or try uploading a DOCX file instead."
            }), 400

        debug_log(f"[VALIDATION] Extracted text length: {len(extracted_text.strip())} chars")

        # LEGAL COMPLIANCE LOGGING
        print(f"\n[LEGAL] Processing syllabus for Fair Use extraction (user: {request.user_id})", flush=True)
        print(f"[LEGAL] Extracting only factual data (dates, times, task names) per 17 USC 107", flush=True)

        # Insert syllabus record (metadata only - NO copyrighted content stored)
        syllabus_data = {
            "user_id": request.user_id,
            "course_name": course_name,
            "course_code": course_code,
            "professor_name": professor_name,
            "semester": semester,
            "file_path": None,  # SB 1324 Compliance: Do not store original file
            "original_filename": file.filename,
            "extracted_text": None,  # Copyright Compliance: Do not store copyrighted text
            "file_size": file_size
        }

        syllabus_result = supabase.table("syllabi").insert(syllabus_data).execute()
        syllabus_id = syllabus_result.data[0]['id']

        print(f"[LEGAL] Syllabus metadata saved: {syllabus_id}", flush=True)

        # Extract calendar events using AI (Fair Use - factual data only)
        print(f"\n[UPLOAD] Calling extract_calendar_events()...", flush=True)
        events = extract_calendar_events(extracted_text, course_name, course_code)
        print(f"[UPLOAD] extract_calendar_events() returned {len(events)} events", flush=True)

        # Insert events into database
        inserted_events = []
        for event in events:
            print(f"[UPLOAD] Validating event: {event.get('title', 'NO TITLE')}", flush=True)
            if validate_event(event):
                event_data = format_event_for_db(event, request.user_id, syllabus_id)
                result = supabase.table("calendar_events").insert(event_data).execute()
                if result.data:
                    inserted_events.append(result.data[0])
                    print(f"[UPLOAD] Inserted event: {event.get('title')}", flush=True)
            else:
                print(f"[UPLOAD] Event validation FAILED for: {event}", flush=True)

        print(f"\n[LEGAL] Extracted {len(inserted_events)} events (factual data only)", flush=True)
        print(f"[LEGAL] Original syllabus discarded per SB 1324 disclosure", flush=True)

        # File is NOT uploaded to storage - processing complete, file discarded
        # This satisfies: Copyright (Fair Use), Privacy (SB 1324), Academic Integrity (HB 2271)

        return jsonify({
            "success": True,
            "syllabus_id": syllabus_id,
            "events": inserted_events,
            "message": f"Syllabus uploaded and {len(inserted_events)} events extracted"
        }), 200

    except Exception as e:
        debug_log(f"❌ Syllabus upload error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/canvas/import", methods=["POST"])
@supabase_auth_required
def import_canvas_calendar():
    """
    Import calendar events from Canvas iCal feed

    Expects JSON:
    {
        "feed_url": "https://canvas.school.edu/feeds/calendars/user_xxx.ics",
        "auto_sync": true
    }

    Returns:
    {
        "success": true,
        "events_count": 15,
        "message": "Imported 15 events from Canvas"
    }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        from StudyFlow.backend.syllabus_parser import format_event_for_db, validate_event
        import requests
        from icalendar import Calendar
        from datetime import datetime

        data = request.get_json()
        feed_url = data.get('feed_url')
        auto_sync = data.get('auto_sync', False)

        if not feed_url:
            return jsonify({"error": "Missing feed_url"}), 400

        # Validate URL format
        if not feed_url.startswith('http'):
            return jsonify({"error": "Invalid feed URL"}), 400

        debug_log(f"[CANVAS] Fetching calendar feed: {feed_url}")

        # Fetch .ics file from Canvas
        try:
            response = requests.get(feed_url, timeout=30)
            response.raise_for_status()
            ics_content = response.text
        except requests.exceptions.RequestException as e:
            debug_log(f"[CANVAS] Failed to fetch feed: {e}")
            return jsonify({"error": f"Failed to fetch Canvas calendar: {str(e)}"}), 400

        # Parse iCal feed
        try:
            cal = Calendar.from_ical(ics_content)
        except Exception as e:
            debug_log(f"[CANVAS] Failed to parse iCal: {e}")
            return jsonify({"error": f"Failed to parse calendar feed: {str(e)}"}), 400

        # Extract events from iCal
        events = []
        for component in cal.walk():
            if component.name == "VEVENT":
                try:
                    # Extract event data
                    summary = str(component.get('summary', 'Untitled'))
                    description = str(component.get('description', '')) if component.get('description') else None
                    dtstart = component.get('dtstart').dt if component.get('dtstart') else None

                    # Skip if no date
                    if not dtstart:
                        continue

                    # Convert to date/time strings
                    if isinstance(dtstart, datetime):
                        due_date = dtstart.strftime('%Y-%m-%d')
                        due_time = dtstart.strftime('%H:%M:%S')
                    else:
                        due_date = dtstart.strftime('%Y-%m-%d')
                        due_time = None

                    # Detect event type from summary
                    event_type = 'other'
                    summary_lower = summary.lower()
                    if any(word in summary_lower for word in ['assignment', 'homework', 'hw']):
                        event_type = 'assignment'
                    elif any(word in summary_lower for word in ['exam', 'test', 'quiz', 'midterm', 'final']):
                        event_type = 'exam'
                    elif any(word in summary_lower for word in ['project', 'paper', 'essay', 'presentation']):
                        event_type = 'project'
                    elif any(word in summary_lower for word in ['reading', 'chapter', 'read']):
                        event_type = 'reading'

                    # Extract course name from summary or description
                    course_name = None
                    if ':' in summary:
                        course_name = summary.split(':')[0].strip()

                    event = {
                        'event_type': event_type,
                        'title': summary,
                        'description': description,
                        'due_date': due_date,
                        'due_time': due_time,
                        'course_name': course_name
                    }

                    events.append(event)
                except Exception as e:
                    debug_log(f"[CANVAS] Failed to parse event: {e}")
                    continue

        debug_log(f"[CANVAS] Parsed {len(events)} events from iCal feed")

        # Insert events into database
        inserted_events = []
        for event in events:
            if validate_event(event):
                event_data = format_event_for_db(event, request.user_id, syllabus_id=None)
                result = supabase.table("calendar_events").insert(event_data).execute()
                if result.data:
                    inserted_events.append(result.data[0])

        debug_log(f"[CANVAS] Inserted {len(inserted_events)} events")

        # Store Canvas feed URL for auto-sync if requested
        if auto_sync:
            try:
                supabase.table("user_profiles").update({
                    "canvas_feed_url": feed_url
                }).eq("id", request.user_id).execute()
                debug_log(f"[CANVAS] Saved feed URL for auto-sync")
            except Exception as e:
                debug_log(f"[CANVAS] Failed to save feed URL: {e}")

        return jsonify({
            "success": True,
            "events_count": len(inserted_events),
            "message": f"Imported {len(inserted_events)} events from Canvas"
        }), 200

    except Exception as e:
        debug_log(f"[CANVAS] Import error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500

    except Exception as e:
        debug_log(f"❌ Upload syllabus error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/calendar/events", methods=["GET"])
@supabase_auth_required
def get_calendar_events():
    """
    Get user's calendar events

    Query params:
    - start_date: Filter events after this date (YYYY-MM-DD)
    - end_date: Filter events before this date (YYYY-MM-DD)
    - course_code: Filter by course code
    - completed: Filter by completion status (true/false)
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        query = supabase.table("calendar_events").select("*").eq("user_id", request.user_id)

        # Apply filters
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        course_code = request.args.get('course_code')
        completed = request.args.get('completed')

        if start_date:
            query = query.gte('due_date', start_date)
        if end_date:
            query = query.lte('due_date', end_date)
        if course_code:
            query = query.eq('course_code', course_code)
        if completed is not None:
            query = query.eq('completed', completed.lower() == 'true')

        # Order by due date
        query = query.order('due_date', desc=False)

        result = query.execute()

        return jsonify({
            "success": True,
            "events": result.data
        }), 200

    except Exception as e:
        debug_log(f"❌ Get calendar events error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/calendar/events", methods=["POST"])
@supabase_auth_required
def create_calendar_event():
    """
    Manually create a calendar event

    Request body:
    {
        "event_type": "assignment",
        "title": "Lab Report 3",
        "description": "Write up lab 3 results",
        "due_date": "2026-04-15",
        "due_time": "23:59",
        "course_name": "Chemistry 101",
        "course_code": "CHEM101"
    }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        from StudyFlow.backend.syllabus_parser import format_event_for_db, validate_event

        data = request.get_json()

        if not validate_event(data):
            return jsonify({"error": "Missing required fields: event_type, title, due_date"}), 400

        event_data = format_event_for_db(data, request.user_id, syllabus_id=None)
        result = supabase.table("calendar_events").insert(event_data).execute()

        return jsonify({
            "success": True,
            "event": result.data[0]
        }), 201

    except Exception as e:
        debug_log(f"❌ Create calendar event error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/calendar/events/<event_id>", methods=["PUT"])
@supabase_auth_required
def update_calendar_event(event_id):
    """
    Update a calendar event (e.g., mark as completed, edit details)

    Request body:
    {
        "completed": true,
        "title": "Updated title",
        ...
    }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        data = request.get_json()

        # Update event (only if it belongs to user)
        result = supabase.table("calendar_events").update(data).eq("id", event_id).eq("user_id", request.user_id).execute()

        if not result.data:
            return jsonify({"error": "Event not found or unauthorized"}), 404

        return jsonify({
            "success": True,
            "event": result.data[0]
        }), 200

    except Exception as e:
        debug_log(f"❌ Update calendar event error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/calendar/events/<event_id>", methods=["DELETE"])
@supabase_auth_required
def delete_calendar_event(event_id):
    """Delete a calendar event"""
    try:
        from StudyFlow.backend.supabase_client import supabase

        result = supabase.table("calendar_events").delete().eq("id", event_id).eq("user_id", request.user_id).execute()

        if not result.data:
            return jsonify({"error": "Event not found or unauthorized"}), 404

        return jsonify({"success": True}), 200

    except Exception as e:
        debug_log(f"❌ Delete calendar event error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/syllabi", methods=["GET"])
@supabase_auth_required
def get_syllabi():
    """Get user's uploaded syllabi"""
    try:
        from StudyFlow.backend.supabase_client import supabase

        result = supabase.table("syllabi").select("*").eq("user_id", request.user_id).order('created_at', desc=True).execute()

        return jsonify({
            "success": True,
            "syllabi": result.data
        }), 200

    except Exception as e:
        debug_log(f"❌ Get syllabi error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ============ GOOD STANDING SYSTEM ENDPOINTS ============

@app.route("/api/good-standing/status", methods=["GET"])
@supabase_auth_required
def get_good_standing_status():
    """
    Check if user is in Good Standing (Missouri HB 2271 / DMCA compliance)

    Returns:
    {
        "good_standing": true/false,
        "reason": "active_subscription" | "recent_upload" | "no_recent_uploads" | "dmca_strikes",
        "days_until_expiry": 15,  # Days until they lose good standing
        "last_verified_upload": "2026-03-20T10:30:00Z",
        "dmca_strikes": 0,
        "permanent_bad_standing": false
    }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        from datetime import datetime, timedelta

        # Get user profile
        profile_result = supabase.table("user_profiles").select("*").eq("id", request.user_id).single().execute()
        if not profile_result.data:
            return jsonify({"error": "User profile not found"}), 404

        profile = profile_result.data

        # Check if permanently banned (3+ strikes)
        if profile.get('permanent_bad_standing', False):
            return jsonify({
                "good_standing": False,
                "reason": "dmca_strikes",
                "dmca_strikes": profile.get('dmca_strikes', 0),
                "permanent_bad_standing": True,
                "message": "Account permanently ineligible for Good Standing due to DMCA violations"
            }), 200

        # Check for active subscription (always good standing)
        # TODO: Add subscription check when Stripe integration is added
        # For now, assume no active subscription

        # Check last verified upload (30-day window)
        last_upload = profile.get('last_verified_upload_date')
        if last_upload:
            last_upload_dt = datetime.fromisoformat(last_upload.replace('Z', '+00:00'))
            days_since = (datetime.now(last_upload_dt.tzinfo) - last_upload_dt).days
            days_until_expiry = max(0, 30 - days_since)

            if days_since < 30:
                return jsonify({
                    "good_standing": True,
                    "reason": "recent_upload",
                    "days_until_expiry": days_until_expiry,
                    "last_verified_upload": last_upload,
                    "dmca_strikes": profile.get('dmca_strikes', 0),
                    "permanent_bad_standing": False
                }), 200

        # No recent uploads = bad standing
        return jsonify({
            "good_standing": False,
            "reason": "no_recent_uploads",
            "days_until_expiry": 0,
            "last_verified_upload": last_upload,
            "dmca_strikes": profile.get('dmca_strikes', 0),
            "permanent_bad_standing": False,
            "message": "Upload a verified note to regain Good Standing"
        }), 200

    except Exception as e:
        debug_log(f"Get good standing status error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/good-standing/verify-upload", methods=["POST"])
@supabase_auth_required
def verify_upload():
    """
    Verify if uploaded content is legitimate study material (not spam/blank)

    Request body:
    {
        "note_id": "uuid",
        "extracted_text": "text content from note"
    }

    Returns:
    {
        "verified": true/false,
        "confidence": 0.95,
        "rejection_reason": null | "spam" | "blank" | "invalid_format"
    }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        import google.generativeai as genai

        data = request.get_json()
        note_id = data.get('note_id')
        extracted_text = data.get('extracted_text', '')

        if not note_id:
            return jsonify({"error": "note_id required"}), 400

        # Quick validation: Minimum length check
        if len(extracted_text.strip()) < 50:
            # Log rejection
            supabase.table("upload_verifications").insert({
                "user_id": request.user_id,
                "note_id": note_id,
                "verification_status": "rejected",
                "rejection_reason": "blank",
                "ai_confidence": 0.0
            }).execute()

            return jsonify({
                "verified": False,
                "confidence": 0.0,
                "rejection_reason": "blank",
                "message": "Document appears to be blank or too short"
            }), 200

        # AI verification with Gemini
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model = genai.GenerativeModel('gemini-3.1-flash-lite-preview')

        prompt = f"""Analyze this document to determine if it's legitimate study material.

DOCUMENT TEXT (first 2000 chars):
{extracted_text[:2000]}

Respond with ONLY a JSON object:
{{
    "is_study_material": true/false,
    "confidence": 0.0-1.0,
    "reason": "brief explanation",
    "category": "notes" | "textbook" | "slides" | "homework" | "spam" | "blank" | "other"
}}

Study material includes: class notes, textbook chapters, lecture slides, study guides, homework, assignments, etc.
NOT study material: grocery lists, personal emails, blank pages, random text, advertisements."""

        response = model.generate_content(prompt)
        ai_text = response.text.strip()

        # Parse JSON response
        import json
        import re
        if ai_text.startswith("```"):
            ai_text = re.sub(r'^```json?\s*', '', ai_text)
            ai_text = re.sub(r'\s*```$', '', ai_text)

        result = json.loads(ai_text)

        is_verified = result.get('is_study_material', False)
        confidence = result.get('confidence', 0.5)
        category = result.get('category', 'other')

        # Determine rejection reason
        rejection_reason = None
        if not is_verified:
            if category == 'spam':
                rejection_reason = 'spam'
            elif category == 'blank':
                rejection_reason = 'blank'
            else:
                rejection_reason = 'invalid_format'

        # Log verification
        supabase.table("upload_verifications").insert({
            "user_id": request.user_id,
            "note_id": note_id,
            "verification_status": "verified" if is_verified else "rejected",
            "rejection_reason": rejection_reason,
            "ai_confidence": confidence
        }).execute()

        # If verified, update user's Good Standing status
        if is_verified:
            from datetime import datetime
            supabase.table("user_profiles").update({
                "good_standing": True,
                "last_verified_upload_date": datetime.utcnow().isoformat()
            }).eq("id", request.user_id).execute()

            print(f"[GOOD STANDING] User {request.user_id} verified upload, status updated", flush=True)

        return jsonify({
            "verified": is_verified,
            "confidence": confidence,
            "rejection_reason": rejection_reason,
            "message": f"Document {('verified' if is_verified else 'rejected')} as {category}"
        }), 200

    except Exception as e:
        debug_log(f"Verify upload error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/download/<note_id>", methods=["POST"])
@supabase_auth_required
def download_note_with_certification(note_id):
    """
    Download a note with Missouri HB 2271 certification

    Request body:
    {
        "certified": true  # User certifies they're using for academic research/tutorial only
    }

    Returns:
    {
        "download_url": "https://...",
        "filename": "Biology_Chapter_3.pdf"
    }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        data = request.get_json()
        certified = data.get('certified', False)

        if not certified:
            return jsonify({"error": "Academic integrity certification required"}), 400

        # Check if user is in Good Standing OR has active subscription
        profile_result = supabase.table("user_profiles").select("good_standing, permanent_bad_standing").eq("id", request.user_id).single().execute()
        profile = profile_result.data

        # Block if permanently banned
        if profile.get('permanent_bad_standing', False):
            return jsonify({"error": "Account suspended due to DMCA violations"}), 403

        # Check good standing
        if not profile.get('good_standing', False):
            return jsonify({
                "error": "Good Standing required to download notes",
                "message": "Upload a verified note or subscribe to regain access",
                "good_standing_required": True
            }), 403

        # Get note details
        note_result = supabase.table("notes").select("*").eq("id", note_id).single().execute()
        if not note_result.data:
            return jsonify({"error": "Note not found"}), 404

        note = note_result.data

        # Check if note is public or owned by user
        if not note.get('is_public', False) and note.get('user_id') != request.user_id:
            return jsonify({"error": "Unauthorized access to private note"}), 403

        # Record certification (HB 2271 compliance)
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip_address and ',' in ip_address:
            ip_address = ip_address.split(',')[0].strip()

        supabase.table("download_certifications").insert({
            "user_id": request.user_id,
            "note_id": note_id,
            "ip_address": ip_address,
            "user_agent": request.headers.get('User-Agent')
        }).execute()

        # Notify the uploader that their note was downloaded
        try:
            note_owner_id = note.get('user_id')
            if note_owner_id and note_owner_id != request.user_id:
                # Get downloader username
                dl_profile = supabase.table("user_profiles").select("username").eq("id", request.user_id).execute()
                dl_username = dl_profile.data[0].get("username", "Someone") if dl_profile.data else "Someone"
                fname = note.get('original_filename', 'a note')
                create_notification(
                    user_id=note_owner_id,
                    notif_type="note_downloaded",
                    title="Note Downloaded",
                    message=f"@{dl_username} downloaded your note {fname}",
                    note_id=note_id,
                    actor_username=dl_username,
                )
        except Exception as notif_err:
            debug_log(f"[-] Download notification failed (non-blocking): {notif_err}")

        # Generate signed URL for download
        file_path = note.get('file_path')
        if not file_path:
            return jsonify({"error": "Note file not found"}), 404

        download_url = supabase.storage.from_('notes').create_signed_url(file_path, 3600)  # 1 hour expiry

        return jsonify({
            "download_url": download_url,
            "filename": note.get('original_filename', 'note.pdf')
        }), 200

    except Exception as e:
        debug_log(f"Download note error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/dmca/report", methods=["POST"])
def submit_dmca_report():
    """
    Submit a DMCA takedown notice (does not require authentication)

    Request body:
    {
        "note_id": "uuid",
        "reporter_email": "professor@university.edu",
        "reporter_name": "Dr. John Doe",
        "reason": "This contains my copyrighted lecture slides from Fall 2025"
    }

    Returns:
    {
        "success": true,
        "message": "DMCA report submitted. Note will be reviewed within 24 hours."
    }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        data = request.get_json()
        note_id = data.get('note_id')
        reporter_email = data.get('reporter_email')
        reporter_name = data.get('reporter_name')
        reason = data.get('reason')

        if not all([note_id, reporter_email, reason]):
            return jsonify({"error": "note_id, reporter_email, and reason required"}), 400

        # Get note to find uploader and filename
        note_result = supabase.table("notes").select("user_id, original_filename").eq("id", note_id).single().execute()
        if not note_result.data:
            return jsonify({"error": "Note not found"}), 404

        uploader_id = note_result.data['user_id']
        note_filename = note_result.data.get('original_filename', 'Unknown file')

        # Insert DMCA report
        takedown_result = supabase.table("dmca_takedowns").insert({
            "note_id": note_id,
            "uploader_id": uploader_id,
            "reporter_email": reporter_email,
            "reporter_name": reporter_name,
            "takedown_reason": reason
        }).execute()

        takedown_id = takedown_result.data[0]['id'] if takedown_result.data else None

        print(f"[DMCA] Takedown report submitted for note {note_id} by {reporter_email}", flush=True)

        # Send email notification to admin
        if takedown_id:
            send_dmca_report_notification_to_admin(
                takedown_id=takedown_id,
                note_filename=note_filename,
                reporter_email=reporter_email,
                reason=reason
            )

        return jsonify({
            "success": True,
            "message": "DMCA report submitted. The note will be reviewed and removed if valid. You will receive an email confirmation within 24 hours."
        }), 200

    except Exception as e:
        debug_log(f"Submit DMCA report error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/dmca/reports", methods=["GET"])
def list_dmca_reports():
    """ADMIN ONLY: List all DMCA reports."""
    try:
        admin_key = request.args.get("key", "")
        if admin_key != os.getenv("ADMIN_KEY", "change_me_in_production"):
            return jsonify({"error": "Unauthorized"}), 403

        from StudyFlow.backend.supabase_client import supabase

        reports = supabase.table("dmca_takedowns").select("*").order("created_at", desc=True).execute()

        results = []
        for r in (reports.data or []):
            # Get note info
            note_info = {}
            if r.get("note_id"):
                note_resp = supabase.table("notes").select(
                    "original_filename, university, course_code, is_public"
                ).eq("id", r["note_id"]).execute()
                if note_resp.data:
                    note_info = note_resp.data[0]

            # Get uploader username
            uploader_name = "Unknown"
            if r.get("uploader_id"):
                profile = supabase.table("user_profiles").select("username, email").eq("id", r["uploader_id"]).execute()
                if profile.data:
                    uploader_name = profile.data[0].get("username") or profile.data[0].get("email", "Unknown")

            results.append({
                "id": r["id"],
                "note_id": r.get("note_id"),
                "note_filename": note_info.get("original_filename", "Unknown"),
                "note_university": note_info.get("university"),
                "note_course": note_info.get("course_code"),
                "note_is_public": note_info.get("is_public", True),
                "uploader_id": r.get("uploader_id"),
                "uploader_name": uploader_name,
                "reporter_email": r.get("reporter_email"),
                "reporter_name": r.get("reporter_name"),
                "reason": r.get("takedown_reason"),
                "status": r.get("status", "pending"),
                "created_at": r.get("created_at")
            })

        return jsonify({"reports": results}), 200

    except Exception as e:
        debug_log(f"List DMCA reports error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/dmca/process/<takedown_id>", methods=["POST"])
def process_dmca_takedown(takedown_id):
    """
    ADMIN ONLY: Process a DMCA takedown (apply strike, remove note)

    Request body:
    {
        "admin_key": "secret_key",
        "action": "approve" | "reject"
    }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        from datetime import datetime

        data = request.get_json()
        admin_key = data.get('admin_key')
        action = data.get('action')

        # Simple admin key check (replace with proper auth)
        if admin_key != os.getenv("ADMIN_KEY", "change_me_in_production"):
            return jsonify({"error": "Unauthorized"}), 403

        if action not in ['approve', 'reject']:
            return jsonify({"error": "Invalid action"}), 400

        # Get takedown record
        takedown_result = supabase.table("dmca_takedowns").select("*").eq("id", takedown_id).single().execute()
        if not takedown_result.data:
            return jsonify({"error": "Takedown not found"}), 404

        takedown = takedown_result.data
        note_id = takedown['note_id']
        uploader_id = takedown['uploader_id']
        reporter_email = takedown.get('reporter_email')
        reporter_name = takedown.get('reporter_name')

        # Get note filename
        note_result = supabase.table("notes").select("original_filename").eq("id", note_id).single().execute()
        note_filename = note_result.data.get('original_filename', 'Unknown file') if note_result.data else 'Unknown file'

        # Get uploader's email and username
        uploader_result = supabase.table("user_profiles").select("email, username, dmca_strikes").eq("id", uploader_id).single().execute()
        if not uploader_result.data:
            return jsonify({"error": "Uploader profile not found"}), 404

        uploader_email = uploader_result.data.get('email')
        uploader_name = uploader_result.data.get('username', 'User')
        current_strikes = uploader_result.data.get('dmca_strikes', 0)

        if action == 'approve':
            # Mark note as private (soft delete)
            supabase.table("notes").update({"is_public": False}).eq("id", note_id).execute()

            # Apply strike to uploader
            new_strikes = current_strikes + 1

            update_data = {"dmca_strikes": new_strikes}

            # Three strikes = permanent bad standing
            is_permanent_ban = new_strikes >= 3
            if is_permanent_ban:
                update_data["permanent_bad_standing"] = True
                update_data["good_standing"] = False

            supabase.table("user_profiles").update(update_data).eq("id", uploader_id).execute()

            # Mark takedown as processed
            supabase.table("dmca_takedowns").update({
                "processed_at": datetime.utcnow().isoformat(),
                "strike_applied": True
            }).eq("id", takedown_id).execute()

            print(f"[DMCA] Strike applied to user {uploader_id} ({new_strikes}/3)", flush=True)

            # Send email to user about strike
            if uploader_email:
                send_dmca_strike_notification_to_user(
                    user_email=uploader_email,
                    user_name=uploader_name,
                    strike_count=new_strikes,
                    note_filename=note_filename,
                    is_permanent_ban=is_permanent_ban
                )

            # Send confirmation to reporter
            if reporter_email:
                send_dmca_report_confirmation_to_reporter(
                    reporter_email=reporter_email,
                    reporter_name=reporter_name,
                    note_filename=note_filename,
                    action='approve'
                )

            return jsonify({
                "success": True,
                "message": f"Note removed, strike applied ({new_strikes}/3)",
                "permanent_ban": is_permanent_ban
            }), 200

        else:  # reject
            supabase.table("dmca_takedowns").update({
                "processed_at": datetime.utcnow().isoformat(),
                "strike_applied": False
            }).eq("id", takedown_id).execute()

            # Send rejection confirmation to reporter
            if reporter_email:
                send_dmca_report_confirmation_to_reporter(
                    reporter_email=reporter_email,
                    reporter_name=reporter_name,
                    note_filename=note_filename,
                    action='reject'
                )

            return jsonify({
                "success": True,
                "message": "DMCA report rejected, no action taken"
            }), 200

    except Exception as e:
        debug_log(f"Process DMCA takedown error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ============ SUBSCRIPTION ENDPOINTS ============

@app.route("/api/subscription/status", methods=["GET"])
@supabase_auth_required
def get_subscription_status():
    """
    Get user's current subscription status
    Returns subscription_tier and subscription_status from user_profiles
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        response = supabase.table("user_profiles").select(
            "subscription_tier, subscription_status, stripe_customer_id, stripe_subscription_id"
        ).eq("id", request.user_id).single().execute()

        if response.data:
            return jsonify(response.data), 200
        else:
            return jsonify({
                "subscription_tier": "free",
                "subscription_status": None,
                "stripe_customer_id": None,
                "stripe_subscription_id": None
            }), 200

    except Exception as e:
        debug_log(f"Get subscription status error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/downloads/daily-status", methods=["GET"])
@supabase_auth_required
def get_daily_download_status():
    """
    Get user's daily download count and limit
    Returns download count, limit, and whether user is Scholar's Club member
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        from datetime import date

        response = supabase.table("user_profiles").select(
            "subscription_tier, subscription_status, daily_downloads_count, daily_downloads_reset_date"
        ).eq("id", request.user_id).single().execute()

        if not response.data:
            return jsonify({"error": "User not found"}), 404

        profile = response.data

        # Check if Scholar's Club member (unlimited downloads)
        is_scholar = (
            profile.get('subscription_tier') == 'pro' and
            profile.get('subscription_status') == 'active'
        )

        # Reset counter if new day
        today = date.today()
        reset_date = profile.get('daily_downloads_reset_date')
        download_count = profile.get('daily_downloads_count', 0) or 0

        if not is_scholar and (not reset_date or str(reset_date) != str(today)):
            # Reset for new day
            supabase.table("user_profiles").update({
                "daily_downloads_count": 0,
                "daily_downloads_reset_date": str(today)
            }).eq("id", request.user_id).execute()
            download_count = 0

        return jsonify({
            "is_scholar": is_scholar,
            "downloads_used": download_count if not is_scholar else None,
            "downloads_limit": 3 if not is_scholar else None,
            "downloads_remaining": (3 - download_count) if not is_scholar else None,
            "reset_date": str(today) if not is_scholar else None
        }), 200

    except Exception as e:
        debug_log(f"Get daily download status error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/subscription/create-checkout", methods=["POST"])
@supabase_auth_required
def create_checkout_session():
    """
    Create a Stripe Checkout session for the Scholar's Club subscription ($4.99/mo)

    Request body:
    {
        "success_url": "https://...",
        "cancel_url": "https://..."
    }

    Returns:
    {
        "checkout_url": "https://checkout.stripe.com/..."
    }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        import stripe

        data = request.get_json()
        success_url = data.get('success_url')
        cancel_url = data.get('cancel_url')

        # Get user email
        user_email = request.user_email

        # Get or create Stripe customer
        response = supabase.table("user_profiles").select(
            "stripe_customer_id"
        ).eq("id", request.user_id).single().execute()

        stripe_customer_id = response.data.get('stripe_customer_id') if response.data else None

        if stripe_customer_id:
            # Retrieve existing customer
            customer = stripe.Customer.retrieve(stripe_customer_id)
        else:
            # Create new customer
            customer = stripe.Customer.create(
                email=user_email,
                metadata={'user_id': request.user_id}
            )
            stripe_customer_id = customer.id

            # Save customer ID to database
            supabase.table("user_profiles").update({
                "stripe_customer_id": stripe_customer_id
            }).eq("id", request.user_id).execute()

        # Create Stripe Checkout session for Scholar's Club ($4.99/mo)
        checkout_session = stripe.checkout.Session.create(
            customer=stripe_customer_id,
            payment_method_types=['card'],
            line_items=[{
                'price': 'price_1TEJOa9LWKaKRffVgNpExTIz',  # Scholar's Club - $4.99/month
                'quantity': 1,
            }],
            mode='subscription',
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={
                'user_id': request.user_id
            }
        )

        debug_log(f"Created checkout session for user {request.user_id}: {checkout_session.id}")

        return jsonify({
            "checkout_url": checkout_session.url
        }), 200

    except Exception as e:
        debug_log(f"Create checkout session error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/subscription/customer-portal", methods=["POST"])
@supabase_auth_required
def create_customer_portal():
    """
    Create a Stripe Customer Portal session for managing subscriptions

    Request body:
    {
        "return_url": "https://..."
    }

    Returns:
    {
        "portal_url": "https://billing.stripe.com/..."
    }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        import stripe

        data = request.get_json()
        return_url = data.get('return_url')

        # Get Stripe customer ID
        response = supabase.table("user_profiles").select(
            "stripe_customer_id"
        ).eq("id", request.user_id).single().execute()

        stripe_customer_id = response.data.get('stripe_customer_id') if response.data else None

        if not stripe_customer_id:
            return jsonify({"error": "No subscription found"}), 404

        # Create Customer Portal session
        portal_session = stripe.billing_portal.Session.create(
            customer=stripe_customer_id,
            return_url=return_url
        )

        debug_log(f"Created portal session for user {request.user_id}")

        return jsonify({
            "portal_url": portal_session.url
        }), 200

    except Exception as e:
        debug_log(f"Create customer portal error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ============ NOTIFICATION ENDPOINTS ============

def create_notification(user_id, notif_type, title, message, note_id=None, actor_username=None):
    """Helper to insert a notification row."""
    try:
        from StudyFlow.backend.supabase_client import supabase
        row = {
            "user_id": user_id,
            "type": notif_type,
            "title": title,
            "message": message,
            "is_read": False,
        }
        if note_id:
            row["note_id"] = note_id
        if actor_username:
            row["actor_username"] = actor_username
        supabase.table("notifications").insert(row).execute()
    except Exception as e:
        debug_log(f"[-] Failed to create notification: {e}")


@app.route("/api/notifications", methods=["GET"])
@supabase_auth_required
def get_notifications():
    """Return the last 50 notifications for the authenticated user."""
    try:
        from StudyFlow.backend.supabase_client import supabase
        result = supabase.table("notifications") \
            .select("*") \
            .eq("user_id", request.user_id) \
            .order("created_at", desc=True) \
            .limit(50) \
            .execute()
        return jsonify({"notifications": result.data or []}), 200
    except Exception as e:
        debug_log(f"Get notifications error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notifications/read", methods=["POST"])
@supabase_auth_required
def mark_notifications_read():
    """Mark a single notification or all notifications as read."""
    try:
        from StudyFlow.backend.supabase_client import supabase
        data = request.get_json()

        if data.get("all"):
            supabase.table("notifications") \
                .update({"is_read": True}) \
                .eq("user_id", request.user_id) \
                .eq("is_read", False) \
                .execute()
        elif data.get("notification_id"):
            supabase.table("notifications") \
                .update({"is_read": True}) \
                .eq("id", data["notification_id"]) \
                .eq("user_id", request.user_id) \
                .execute()
        else:
            return jsonify({"error": "Provide notification_id or all:true"}), 400

        return jsonify({"success": True}), 200
    except Exception as e:
        debug_log(f"Mark notifications read error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ============ NOTE FAVORITES ENDPOINTS ============

@app.route("/api/notes/favorite", methods=["POST"])
@supabase_auth_required
def favorite_note():
    """Add a note to the user's favorites."""
    try:
        from StudyFlow.backend.supabase_client import supabase
        data = request.get_json()
        note_id = data.get("note_id")
        if not note_id:
            return jsonify({"error": "Missing note_id"}), 400

        supabase.table("note_favorites").upsert({
            "user_id": request.user_id,
            "note_id": note_id
        }, on_conflict="user_id,note_id").execute()

        return jsonify({"success": True}), 200
    except Exception as e:
        debug_log(f"Favorite note error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/favorite", methods=["DELETE"])
@supabase_auth_required
def unfavorite_note():
    """Remove a note from the user's favorites."""
    try:
        from StudyFlow.backend.supabase_client import supabase
        data = request.get_json()
        note_id = data.get("note_id")
        if not note_id:
            return jsonify({"error": "Missing note_id"}), 400

        supabase.table("note_favorites") \
            .delete() \
            .eq("user_id", request.user_id) \
            .eq("note_id", note_id) \
            .execute()

        return jsonify({"success": True}), 200
    except Exception as e:
        debug_log(f"Unfavorite note error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/favorites", methods=["GET"])
@supabase_auth_required
def get_favorite_notes():
    """Get all favorited note IDs for the user."""
    try:
        from StudyFlow.backend.supabase_client import supabase
        result = supabase.table("note_favorites") \
            .select("note_id, created_at") \
            .eq("user_id", request.user_id) \
            .order("created_at", desc=True) \
            .execute()

        return jsonify({"favorites": result.data or []}), 200
    except Exception as e:
        debug_log(f"Get favorites error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/<note_id>/annotations", methods=["GET"])
@supabase_auth_required
def get_annotations(note_id):
    """Get all annotations for a note belonging to the current user."""
    try:
        from StudyFlow.backend.supabase_client import supabase
        result = supabase.table("note_annotations") \
            .select("page_number, annotations_json") \
            .eq("user_id", request.user_id) \
            .eq("note_id", note_id) \
            .order("page_number") \
            .execute()

        annotations = []
        for row in (result.data or []):
            annotations.append({
                "page_number": row["page_number"],
                "objects": row["annotations_json"].get("objects", []) if isinstance(row["annotations_json"], dict) else []
            })

        return jsonify({"annotations": annotations}), 200
    except Exception as e:
        debug_log(f"Get annotations error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/<note_id>/annotations", methods=["POST"])
@supabase_auth_required
def save_annotations(note_id):
    """Upsert annotations per page for a note. Deletes pages with empty objects.
    If save_as_new=true, duplicates the note first and saves annotations to the copy."""
    try:
        from StudyFlow.backend.supabase_client import supabase
        data = request.get_json()
        pages = data.get("annotations", [])
        save_as_new = data.get("save_as_new", False)

        if not isinstance(pages, list):
            return jsonify({"error": "annotations must be a list"}), 400

        target_note_id = note_id

        # If saving as a new note, create a new note record pointing to the SAME file
        # (annotations are stored separately, watermarks are applied during download)
        if save_as_new:
            try:
                # Fetch original note record
                original = supabase.table("notes") \
                    .select("*") \
                    .eq("id", note_id) \
                    .eq("user_id", request.user_id) \
                    .single() \
                    .execute()

                if not original.data:
                    return jsonify({"error": "Original note not found"}), 404

                orig = original.data

                # Create new note ID but reference the SAME file_path
                # This preserves the watermark (applied during download) and saves storage
                import uuid as uuid_lib
                new_note_id = str(uuid_lib.uuid4())

                # Build the new filename
                orig_filename = orig.get("original_filename", "Untitled")
                name_part = orig_filename.rsplit('.', 1)[0] if '.' in orig_filename else orig_filename
                new_filename = f"{name_part} (annotated).pdf"

                # Create new note record pointing to SAME file
                new_note_data = {
                    "id": new_note_id,
                    "user_id": request.user_id,
                    "original_filename": new_filename,
                    "file_type": orig.get("file_type", "pdf"),
                    "file_size": orig.get("file_size", 0),
                    "file_path": orig.get("file_path"),  # Same file path - no duplication
                    "page_count": orig.get("page_count", 1),
                    "processed": orig.get("processed", False),
                    "is_public": False,
                    "username": orig.get("username"),
                    "university": orig.get("university"),
                    "course_code": orig.get("course_code"),
                    "professor": orig.get("professor"),
                    "semester": orig.get("semester"),
                }
                supabase.table("notes").insert(new_note_data).execute()

                target_note_id = new_note_id
                debug_log(f"[+] Created annotated note {new_note_id} referencing original {note_id} (shared file)")

            except Exception as dup_err:
                debug_log(f"Save as new - creation error: {dup_err}\n{traceback.format_exc()}")
                return jsonify({"error": f"Failed to create annotated note: {str(dup_err)}"}), 500

        # Save annotations to the target note
        for page in pages:
            page_number = page.get("page_number")
            objects = page.get("objects", [])

            if page_number is None:
                continue

            if not objects:
                # Delete empty annotation rows
                supabase.table("note_annotations") \
                    .delete() \
                    .eq("user_id", request.user_id) \
                    .eq("note_id", target_note_id) \
                    .eq("page_number", page_number) \
                    .execute()
            else:
                # Upsert annotation data
                supabase.table("note_annotations").upsert({
                    "user_id": request.user_id,
                    "note_id": target_note_id,
                    "page_number": page_number,
                    "annotations_json": {"objects": objects},
                    "updated_at": "now()"
                }, on_conflict="user_id,note_id,page_number").execute()

        result = {"success": True}
        if save_as_new:
            result["new_note_id"] = target_note_id

        return jsonify(result), 200
    except Exception as e:
        debug_log(f"Save annotations error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/<note_id>/content", methods=["PUT"])
@supabase_auth_required
def update_note_content(note_id):
    """
    Update the text content of a note.
    Auth required, verifies note ownership.
    Accepts JSON body: { "content": "the new text" }
    Re-uploads text as bytes to existing file_path in Supabase Storage.
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        data = request.get_json()
        if not data or "content" not in data:
            return jsonify({"error": "Missing 'content' in request body"}), 400

        new_content = data["content"]

        # Get note and verify ownership
        note_response = supabase.table("notes").select(
            "id, user_id, file_path"
        ).eq("id", note_id).execute()

        if not note_response.data:
            return jsonify({"error": "Note not found"}), 404

        note_data = note_response.data[0]

        if note_data.get("user_id") != request.user_id:
            return jsonify({"error": "Not authorized to edit this note"}), 403

        file_path = note_data.get("file_path")
        if not file_path:
            return jsonify({"error": "No file path for this note"}), 404

        # Re-upload: delete old file then upload new content
        content_bytes = new_content.encode("utf-8")

        # Detect HTML content for proper content-type
        import re
        is_html = bool(re.search(r'<[a-z][\s\S]*>', new_content[:500], re.IGNORECASE))
        content_type = "text/html; charset=utf-8" if is_html else "text/plain; charset=utf-8"

        try:
            supabase.storage.from_("note-files").remove([file_path])
        except Exception as remove_err:
            debug_log(f"Warning: could not remove old file: {remove_err}")

        supabase.storage.from_("note-files").upload(
            path=file_path,
            file=content_bytes,
            file_options={"content-type": content_type}
        )

        # Update file_size in the notes table
        supabase.table("notes").update({
            "file_size": len(content_bytes)
        }).eq("id", note_id).execute()

        return jsonify({"success": True}), 200

    except Exception as e:
        debug_log(f"Update note content error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/upload-image", methods=["POST"])
@supabase_auth_required
def upload_note_image():
    """
    Upload an image for embedding in a rich-text note.
    Accepts multipart file upload. Returns a signed URL for the image.
    """
    try:
        import uuid as _uuid
        from StudyFlow.backend.supabase_client import supabase

        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if not file.filename:
            return jsonify({"error": "No filename"}), 400

        # Validate image type
        allowed = {"image/png", "image/jpeg", "image/gif", "image/webp"}
        content_type = file.content_type or ""
        if content_type not in allowed:
            return jsonify({"error": "Only PNG, JPEG, GIF, and WebP images are allowed"}), 400

        # 5MB limit
        file_bytes = file.read()
        if len(file_bytes) > 5 * 1024 * 1024:
            return jsonify({"error": "Image must be under 5MB"}), 400

        # Convert to WebP for smaller file sizes (skip GIFs to preserve animation)
        from PIL import Image
        from io import BytesIO

        if content_type != "image/gif":
            img = Image.open(BytesIO(file_bytes))
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGBA")
            else:
                img = img.convert("RGB")
            buf = BytesIO()
            img.save(buf, format="WEBP", quality=85)
            file_bytes = buf.getvalue()
            content_type = "image/webp"

        ext = "gif" if content_type == "image/gif" else "webp"
        image_id = str(_uuid.uuid4())
        storage_path = f"note-images/{request.user_id}/{image_id}.{ext}"

        supabase.storage.from_("note-files").upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": content_type}
        )

        # Generate a long-lived signed URL (7 days)
        signed = supabase.storage.from_("note-files").create_signed_url(
            path=storage_path,
            expires_in=604800
        )
        url = signed.get("signedURL") or signed.get("signedUrl")

        return jsonify({"success": True, "url": url}), 200

    except Exception as e:
        debug_log(f"Upload note image error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/<note_id>/raw-content", methods=["GET"])
@supabase_auth_required
def get_note_raw_content(note_id):
    """
    Get the raw file content of a note (authenticated, owner only).
    Returns the file bytes directly with appropriate content-type.
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        note_response = supabase.table("notes").select(
            "id, user_id, file_path, original_filename"
        ).eq("id", note_id).execute()

        if not note_response.data:
            return jsonify({"error": "Note not found"}), 404

        note_data = note_response.data[0]

        if note_data.get("user_id") != request.user_id:
            return jsonify({"error": "Not authorized"}), 403

        file_path = note_data.get("file_path")
        if not file_path:
            return jsonify({"error": "No file path"}), 404

        try:
            file_bytes = supabase.storage.from_("note-files").download(file_path)
        except Exception:
            # File might be empty (new note) -- return empty string
            return "", 200, {"Content-Type": "text/html; charset=utf-8"}

        content_type = "text/html; charset=utf-8" if file_path.endswith(".html") else "text/plain; charset=utf-8"
        return file_bytes, 200, {"Content-Type": content_type}

    except Exception as e:
        debug_log(f"Get note raw content error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/create", methods=["POST"])
@supabase_auth_required
def create_note():
    """
    Create a new empty rich-text note.
    Accepts optional JSON body: { "title": "My Note" }
    Defaults title to "Untitled" if not provided.
    """
    try:
        import uuid as _uuid
        from StudyFlow.backend.supabase_client import supabase

        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip() or "Untitled"

        note_id = str(_uuid.uuid4())
        user_id = request.user_id
        file_path = f"{user_id}/{note_id}.html"

        # Upload empty HTML file to Supabase Storage
        empty_html = b""
        supabase.storage.from_("note-files").upload(
            path=file_path,
            file=empty_html,
            file_options={"content-type": "text/html; charset=utf-8"}
        )

        # Insert row into notes table
        note_row = {
            "id": note_id,
            "user_id": user_id,
            "original_filename": title + ".html",
            "file_type": "txt",
            "file_path": file_path,
            "file_size": 0,
            "is_public": False,
            "page_count": 1,
        }
        supabase.table("notes").insert(note_row).execute()

        return jsonify({"success": True, "note_id": note_id}), 201

    except Exception as e:
        debug_log(f"Create note error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────
# ONLYOFFICE Private Office Endpoints
# ──────────────────────────────────────────────

ONLYOFFICE_URL = os.environ.get("ONLYOFFICE_URL", "")
ONLYOFFICE_JWT_SECRET = os.environ.get("ONLYOFFICE_JWT_SECRET", "")

OFFICE_CONTENT_TYPES = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}

OFFICE_DOCUMENT_TYPES = {
    "docx": "word",
    "xlsx": "cell",
    "pptx": "slide",
}


def _create_blank_document(file_type):
    """Generate a minimal blank office document and return bytes."""
    buf = BytesIO()
    if file_type == "docx":
        from docx import Document as DocxDocument
        doc = DocxDocument()
        doc.add_paragraph("")
        doc.save(buf)
    elif file_type == "xlsx":
        from openpyxl import Workbook
        wb = Workbook()
        wb.save(buf)
    elif file_type == "pptx":
        from pptx import Presentation
        prs = Presentation()
        prs.slide_layouts[6]  # blank layout reference
        prs.slides.add_slide(prs.slide_layouts[6])
        prs.save(buf)
    else:
        raise ValueError(f"Unsupported file type: {file_type}")
    buf.seek(0)
    return buf.read()


@app.route("/api/office/create", methods=["POST"])
@supabase_auth_required
def office_create():
    """Create a new blank office document (docx/xlsx/pptx)."""
    try:
        from StudyFlow.backend.supabase_client import supabase
        import uuid

        data = request.get_json()
        if not data or "title" not in data or "type" not in data:
            return jsonify({"error": "Missing 'title' or 'type'"}), 400

        file_type = data["type"].lower()
        if file_type not in OFFICE_CONTENT_TYPES:
            return jsonify({"error": f"Unsupported type: {file_type}. Use docx, xlsx, or pptx."}), 400

        title = data["title"].strip() or "Untitled"
        doc_id = str(uuid.uuid4())
        file_path = f"office-temp/{request.user_id}/{doc_id}.{file_type}"

        # Generate blank document
        file_bytes = _create_blank_document(file_type)

        # Upload to Supabase Storage (temporary location, not in notes table)
        supabase.storage.from_("note-files").upload(
            path=file_path,
            file=file_bytes,
            file_options={"content-type": OFFICE_CONTENT_TYPES[file_type]},
        )

        # Store in office_documents table (temporary documents, not notes)
        office_doc = {
            "id": doc_id,
            "user_id": request.user_id,
            "title": title,
            "file_path": file_path,
            "file_type": file_type,
            "file_size": len(file_bytes),
        }
        supabase.table("office_documents").insert(office_doc).execute()

        debug_log(f"[Office] Created temporary {file_type} doc '{title}' for user {request.user_id}")
        return jsonify({"success": True, "doc_id": doc_id}), 201

    except Exception as e:
        debug_log(f"Office create error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/office/<doc_id>/editor-config", methods=["GET"])
@supabase_auth_required
def office_editor_config(doc_id):
    """Return ONLYOFFICE editor config with signed JWT."""
    try:
        from StudyFlow.backend.supabase_client import supabase
        import jwt

        # Get office document and verify ownership
        doc_resp = supabase.table("office_documents").select(
            "id, user_id, file_path, file_type, file_size, title"
        ).eq("id", doc_id).execute()

        if not doc_resp.data:
            return jsonify({"error": "Document not found"}), 404

        doc = doc_resp.data[0]
        is_owner = doc["user_id"] == request.user_id
        share_permission = "edit"  # owners always get edit

        if not is_owner:
            share_resp = supabase.table("office_document_shares").select(
                "permission"
            ).eq("doc_id", doc_id).eq("shared_with_user_id", request.user_id).execute()
            if not share_resp.data:
                return jsonify({"error": "Not authorized"}), 403
            share_permission = share_resp.data[0]["permission"]

        file_type = doc["file_type"]
        title = doc.get("title", "Untitled")

        # Generate 1-hour signed URL
        signed = supabase.storage.from_("note-files").create_signed_url(
            doc["file_path"], 3600
        )
        doc_url = signed.get("signedURL") or signed.get("signedUrl", "")

        # Build document key (changes when file changes to bust ONLYOFFICE cache)
        doc_key = f"{doc_id}_{doc.get('file_size', 0)}"

        callback_url = f"{BACKEND_URL}/api/office/callback?doc_id={doc_id}"

        config = {
            "document": {
                "fileType": file_type,
                "key": doc_key,
                "title": f"{title}.{file_type}",
                "url": doc_url,
                "permissions": {
                    "edit": share_permission == "edit",
                    "download": True,
                    "print": True,
                    "chat": False,
                    "comment": False,
                },
            },
            "documentType": OFFICE_DOCUMENT_TYPES.get(file_type, "word"),
            "editorConfig": {
                "callbackUrl": callback_url,
                "user": {
                    "id": request.user_id,
                    "name": request.user_email or "User",
                },
                "customization": {
                    "autosave": True,
                    "forcesave": True,
                    "compactHeader": True,
                    "customer": {
                        "name": "StudyFlow",
                        "address": "StudyFlow Suite",
                        "mail": "info@studyflowsuite.com",
                        "www": "studyflowsuite.com",
                        "info": "StudyFlow Office",
                        "logo": "https://studyflowsuite.com/icon128.png",
                        "logoDark": "https://studyflowsuite.com/icon128.png",
                    },
                    "logo": {
                        "image": "https://studyflowsuite.com/icon128.png",
                        "imageDark": "https://studyflowsuite.com/icon128.png",
                        "imageEmbedded": "https://studyflowsuite.com/icon128.png",
                        "url": "https://studyflowsuite.com",
                    },
                    "feedback": {
                        "visible": False,
                    },
                    "goback": {
                        "url": "https://studyflowsuite.com/office.html",
                        "text": "Back to Office",
                    },
                },
                "mode": "edit" if share_permission == "edit" else "view",
            },
        }

        # Add StudyFlow Assistant plugin for word documents
        if config["documentType"] == "word":
            config["editorConfig"]["plugins"] = {
                "autostart": ["asc.{7C9885A0-0001-0001-0001-000000000001}"],
                "pluginsData": ["https://studyflowsuite.com/plugins/study-assistant/config.json"]
            }

        # Sign the config JWT for ONLYOFFICE
        token = ""
        if ONLYOFFICE_JWT_SECRET:
            token = jwt.encode(config, ONLYOFFICE_JWT_SECRET, algorithm="HS256")
            config["token"] = token

        debug_log(f"[Office] Editor config for doc {doc_id}, type={file_type}")
        return jsonify({
            "config": config,
            "token": token,
            "docServerUrl": ONLYOFFICE_URL,
        }), 200

    except Exception as e:
        debug_log(f"Office editor-config error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/office/callback", methods=["POST"])
def office_callback():
    """
    ONLYOFFICE callback handler (server-to-server, no Supabase auth).
    Called by ONLYOFFICE when document status changes.
    Status 2 = closed after editing, 6 = force save.
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        import jwt

        doc_id = request.args.get("doc_id")
        if not doc_id:
            return jsonify({"error": 0})

        body = request.get_json(force=True)
        debug_log(f"[Office Callback] doc_id={doc_id}, status={body.get('status')}")

        # Verify ONLYOFFICE JWT if secret is configured
        if ONLYOFFICE_JWT_SECRET:
            token = body.get("token")
            if not token:
                auth_header = request.headers.get("Authorization", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header[7:]
            if token:
                try:
                    jwt.decode(token, ONLYOFFICE_JWT_SECRET, algorithms=["HS256"])
                except jwt.InvalidTokenError as jwt_err:
                    debug_log(f"[Office Callback] JWT verification failed: {jwt_err}")
                    return jsonify({"error": 0})

        status = body.get("status")
        download_url = body.get("url")

        # Status 2 = closed after editing, 6 = force save
        if status in (2, 6) and download_url:
            # Download the saved file from ONLYOFFICE temp URL
            resp = requests.get(download_url, timeout=30)
            if resp.status_code == 200:
                file_bytes = resp.content

                # Get office document to find storage path
                doc_resp = supabase.table("office_documents").select(
                    "file_path"
                ).eq("id", doc_id).execute()

                if doc_resp.data:
                    file_path = doc_resp.data[0]["file_path"]
                    file_ext = file_path.rsplit(".", 1)[-1]
                    content_type = OFFICE_CONTENT_TYPES.get(file_ext, "application/octet-stream")

                    # Remove old file and upload new version
                    try:
                        supabase.storage.from_("note-files").remove([file_path])
                    except Exception as rm_err:
                        debug_log(f"[Office Callback] Remove old file warning: {rm_err}")

                    supabase.storage.from_("note-files").upload(
                        path=file_path,
                        file=file_bytes,
                        file_options={"content-type": content_type},
                    )

                    # Update file size in office_documents table
                    supabase.table("office_documents").update({
                        "file_size": len(file_bytes),
                        "updated_at": "now()"
                    }).eq("id", doc_id).execute()

                    debug_log(f"[Office Callback] Saved {len(file_bytes)} bytes for doc {doc_id}")
            else:
                debug_log(f"[Office Callback] Download failed: HTTP {resp.status_code}")

        return jsonify({"error": 0})

    except Exception as e:
        debug_log(f"Office callback error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": 0})


@app.route("/api/office/list", methods=["GET"])
@supabase_auth_required
def office_list():
    """List all office documents for the authenticated user."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        resp = supabase.table("office_documents").select(
            "id, title, file_type, file_size, created_at"
        ).eq("user_id", request.user_id).order("created_at", desc=True).execute()

        docs = []
        for row in resp.data:
            docs.append({
                "id": row["id"],
                "title": row.get("title", "Untitled"),
                "type": row["file_type"],
                "size": row.get("file_size", 0),
                "created_at": row.get("created_at", ""),
            })

        return jsonify({"documents": docs}), 200

    except Exception as e:
        debug_log(f"Office list error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/office/<doc_id>", methods=["DELETE"])
@supabase_auth_required
def office_delete(doc_id):
    """Delete an office document."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        doc_resp = supabase.table("office_documents").select(
            "id, user_id, file_path"
        ).eq("id", doc_id).execute()

        if not doc_resp.data:
            return jsonify({"error": "Document not found"}), 404

        doc = doc_resp.data[0]
        if doc["user_id"] != request.user_id:
            return jsonify({"error": "Not authorized"}), 403

        # Remove from storage
        try:
            supabase.storage.from_("note-files").remove([doc["file_path"]])
        except Exception as rm_err:
            debug_log(f"[Office] Storage remove warning: {rm_err}")

        # Delete row
        supabase.table("office_documents").delete().eq("id", doc_id).execute()

        debug_log(f"[Office] Deleted doc {doc_id}")
        return jsonify({"success": True}), 200

    except Exception as e:
        debug_log(f"Office delete error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/office/<doc_id>/rename", methods=["PATCH"])
@supabase_auth_required
def office_rename(doc_id):
    """Rename an office document."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        data = request.get_json()
        if not data or "title" not in data:
            return jsonify({"error": "Missing 'title'"}), 400

        doc_resp = supabase.table("office_documents").select(
            "id, user_id"
        ).eq("id", doc_id).execute()

        if not doc_resp.data:
            return jsonify({"error": "Document not found"}), 404

        if doc_resp.data[0]["user_id"] != request.user_id:
            return jsonify({"error": "Not authorized"}), 403

        supabase.table("office_documents").update({
            "title": data["title"].strip()
        }).eq("id", doc_id).execute()

        debug_log(f"[Office] Renamed doc {doc_id} to '{data['title']}'")
        return jsonify({"success": True}), 200

    except Exception as e:
        debug_log(f"Office rename error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────
# Office Document Sharing Endpoints
# ──────────────────────────────────────────────

@app.route("/api/office/search-users", methods=["GET"])
@supabase_auth_required
def office_search_users():
    """Search users by username for sharing documents."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        q = request.args.get("q", "").strip()
        if len(q) < 2:
            return jsonify({"users": []}), 200

        # Escape SQL wildcards
        safe_q = q.replace("%", "").replace("_", "")
        result = supabase.table("user_profiles").select(
            "username"
        ).ilike("username", f"%{safe_q}%").neq("id", request.user_id).not_.is_("username", "null").limit(10).execute()

        users = [{"username": u["username"]} for u in (result.data or [])]
        return jsonify({"users": users}), 200

    except Exception as e:
        debug_log(f"Office search-users error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/office/<doc_id>/share", methods=["POST"])
@supabase_auth_required
def office_share(doc_id):
    """Share a document with a user by username. Owner only."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        data = request.get_json()
        if not data or not data.get("username"):
            return jsonify({"error": "Missing username"}), 400

        username = data["username"].strip()
        permission = data.get("permission", "view")
        if permission not in ("view", "edit"):
            return jsonify({"error": "Permission must be 'view' or 'edit'"}), 400

        # Verify document ownership
        doc_resp = supabase.table("office_documents").select(
            "id, user_id"
        ).eq("id", doc_id).execute()

        if not doc_resp.data:
            return jsonify({"error": "Document not found"}), 404
        if doc_resp.data[0]["user_id"] != request.user_id:
            return jsonify({"error": "Only the document owner can share"}), 403

        # Look up target user
        user_resp = supabase.table("user_profiles").select(
            "id, username"
        ).eq("username", username).execute()

        if not user_resp.data:
            return jsonify({"error": "User not found"}), 404

        target_user_id = user_resp.data[0]["id"]
        if target_user_id == request.user_id:
            return jsonify({"error": "Cannot share with yourself"}), 400

        # Upsert share record
        supabase.table("office_document_shares").upsert({
            "doc_id": doc_id,
            "owner_id": request.user_id,
            "shared_with_user_id": target_user_id,
            "permission": permission
        }, on_conflict="doc_id,shared_with_user_id").execute()

        debug_log(f"[Office] Shared doc {doc_id} with @{username} ({permission})")

        # Notify the target user
        try:
            doc_title = doc_resp.data[0].get("title", "Untitled")
            # Get owner username
            owner_profile = supabase.table("user_profiles").select("username").eq("id", request.user_id).execute()
            owner_name = owner_profile.data[0]["username"] if owner_profile.data else "Someone"

            create_notification(
                user_id=target_user_id,
                notif_type="doc_shared",
                title="Document Shared",
                message=f"@{owner_name} shared '{doc_title}' with you ({permission})",
            )
        except Exception:
            pass  # Non-blocking

        return jsonify({"success": True, "shared_with": {"username": username, "permission": permission}}), 200

    except Exception as e:
        debug_log(f"Office share error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/office/<doc_id>/shares", methods=["GET"])
@supabase_auth_required
def office_list_shares(doc_id):
    """List all users a document is shared with. Owner only."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        # Verify ownership
        doc_resp = supabase.table("office_documents").select(
            "id, user_id"
        ).eq("id", doc_id).execute()

        if not doc_resp.data:
            return jsonify({"error": "Document not found"}), 404
        if doc_resp.data[0]["user_id"] != request.user_id:
            return jsonify({"error": "Not authorized"}), 403

        shares_resp = supabase.table("office_document_shares").select(
            "shared_with_user_id, permission, created_at"
        ).eq("doc_id", doc_id).execute()

        shares = []
        for s in (shares_resp.data or []):
            profile = supabase.table("user_profiles").select("username").eq("id", s["shared_with_user_id"]).execute()
            username = profile.data[0]["username"] if profile.data else "Unknown"
            shares.append({
                "user_id": s["shared_with_user_id"],
                "username": username,
                "permission": s["permission"],
                "created_at": s["created_at"]
            })

        return jsonify({"shares": shares}), 200

    except Exception as e:
        debug_log(f"Office list-shares error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/office/<doc_id>/share/<user_id>", methods=["DELETE"])
@supabase_auth_required
def office_revoke_share(doc_id, user_id):
    """Revoke a share. Owner only."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        # Verify ownership
        doc_resp = supabase.table("office_documents").select(
            "id, user_id"
        ).eq("id", doc_id).execute()

        if not doc_resp.data:
            return jsonify({"error": "Document not found"}), 404
        if doc_resp.data[0]["user_id"] != request.user_id:
            return jsonify({"error": "Not authorized"}), 403

        supabase.table("office_document_shares").delete().eq(
            "doc_id", doc_id
        ).eq("shared_with_user_id", user_id).execute()

        debug_log(f"[Office] Revoked share for doc {doc_id}, user {user_id}")
        return jsonify({"success": True}), 200

    except Exception as e:
        debug_log(f"Office revoke-share error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/office/shared-with-me", methods=["GET"])
@supabase_auth_required
def office_shared_with_me():
    """List documents shared with the current user."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        shares_resp = supabase.table("office_document_shares").select(
            "doc_id, permission, owner_id"
        ).eq("shared_with_user_id", request.user_id).order("created_at", desc=True).execute()

        if not shares_resp.data:
            return jsonify({"documents": []}), 200

        documents = []
        for s in shares_resp.data:
            doc_resp = supabase.table("office_documents").select(
                "id, title, file_type, file_size, created_at"
            ).eq("id", s["doc_id"]).execute()

            if not doc_resp.data:
                continue

            doc = doc_resp.data[0]

            # Get owner username
            owner_profile = supabase.table("user_profiles").select("username").eq("id", s["owner_id"]).execute()
            owner_username = owner_profile.data[0]["username"] if owner_profile.data else "Unknown"

            documents.append({
                "id": doc["id"],
                "title": doc.get("title", "Untitled"),
                "file_type": doc["file_type"],
                "file_size": doc.get("file_size", 0),
                "created_at": doc.get("created_at"),
                "permission": s["permission"],
                "owner_username": owner_username
            })

        return jsonify({"documents": documents}), 200

    except Exception as e:
        debug_log(f"Office shared-with-me error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────
# Study Groups Endpoints
# ──────────────────────────────────────────────

@app.route("/api/groups", methods=["POST"])
@supabase_auth_required
def create_group():
    """Create a new study group."""
    try:
        from StudyFlow.backend.supabase_client import supabase
        import secrets

        data = request.get_json()
        if not data or not data.get("name"):
            return jsonify({"error": "Missing group name"}), 400

        name = data["name"].strip()[:60]
        invite_code = secrets.token_urlsafe(8)
        group_id = str(uuid.uuid4())

        supabase.table("study_groups").insert({
            "id": group_id,
            "name": name,
            "owner_id": request.user_id,
            "invite_code": invite_code
        }).execute()

        # Add owner as member
        supabase.table("study_group_members").insert({
            "group_id": group_id,
            "user_id": request.user_id,
            "role": "owner"
        }).execute()

        debug_log(f"[Groups] Created group '{name}' ({group_id})")
        return jsonify({"success": True, "group": {"id": group_id, "name": name, "invite_code": invite_code}}), 200

    except Exception as e:
        debug_log(f"Create group error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups", methods=["GET"])
@supabase_auth_required
def list_groups():
    """List all groups the user is a member of."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        memberships = supabase.table("study_group_members").select(
            "group_id, role"
        ).eq("user_id", request.user_id).execute()

        if not memberships.data:
            return jsonify({"groups": []}), 200

        groups = []
        for m in memberships.data:
            g = supabase.table("study_groups").select("*").eq("id", m["group_id"]).execute()
            if g.data:
                group = g.data[0]
                # Get member count
                members = supabase.table("study_group_members").select("id", count="exact").eq("group_id", m["group_id"]).execute()
                group["member_count"] = members.count if members.count else 0
                group["role"] = m["role"]
                groups.append(group)

        return jsonify({"groups": groups}), 200

    except Exception as e:
        debug_log(f"List groups error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/<group_id>", methods=["GET"])
@supabase_auth_required
def get_group(group_id):
    """Get group details including members and notes."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        # Verify membership
        member_check = supabase.table("study_group_members").select("role").eq(
            "group_id", group_id
        ).eq("user_id", request.user_id).execute()
        if not member_check.data:
            return jsonify({"error": "Not a member"}), 403

        group = supabase.table("study_groups").select("*").eq("id", group_id).execute()
        if not group.data:
            return jsonify({"error": "Group not found"}), 404

        # Get members with usernames
        members_resp = supabase.table("study_group_members").select("user_id, role, joined_at").eq("group_id", group_id).execute()
        members = []
        for m in (members_resp.data or []):
            profile = supabase.table("user_profiles").select("username").eq("id", m["user_id"]).execute()
            members.append({
                "user_id": m["user_id"],
                "username": profile.data[0]["username"] if profile.data else "Unknown",
                "role": m["role"],
                "joined_at": m["joined_at"]
            })

        # Get shared notes (direct uploads)
        notes_resp = supabase.table("study_group_notes").select(
            "id, added_by, added_at, filename, file_path, file_size, file_type"
        ).eq("group_id", group_id).order("added_at", desc=True).execute()
        notes = []
        for n in (notes_resp.data or []):
            profile = supabase.table("user_profiles").select("username").eq("id", n["added_by"]).execute()
            notes.append({
                "id": n["id"],
                "filename": n.get("filename", "Unknown"),
                "file_size": n.get("file_size", 0),
                "file_type": n.get("file_type"),
                "added_by": profile.data[0]["username"] if profile.data else "Unknown",
                "added_at": n["added_at"]
            })

        result = group.data[0]
        result["members"] = members
        result["notes"] = notes
        result["role"] = member_check.data[0]["role"]

        return jsonify({"group": result}), 200

    except Exception as e:
        debug_log(f"Get group error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/<group_id>", methods=["DELETE"])
@supabase_auth_required
def delete_group(group_id):
    """Delete a study group. Owner only."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        group = supabase.table("study_groups").select("owner_id").eq("id", group_id).execute()
        if not group.data:
            return jsonify({"error": "Group not found"}), 404
        if group.data[0]["owner_id"] != request.user_id:
            return jsonify({"error": "Only the owner can delete this group"}), 403

        supabase.table("study_groups").delete().eq("id", group_id).execute()
        debug_log(f"[Groups] Deleted group {group_id}")
        return jsonify({"success": True}), 200

    except Exception as e:
        debug_log(f"Delete group error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/<group_id>/invite", methods=["POST"])
@supabase_auth_required
def invite_to_group(group_id):
    """Send a pending invite to a user. They must accept via notifications."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        # Verify caller is a member
        member_check = supabase.table("study_group_members").select("role").eq(
            "group_id", group_id).eq("user_id", request.user_id).execute()
        if not member_check.data:
            return jsonify({"error": "Not a member"}), 403

        data = request.get_json()
        username = data.get("username", "").strip()
        if not username:
            return jsonify({"error": "Missing username"}), 400

        user_resp = supabase.table("user_profiles").select("id, username").eq("username", username).execute()
        if not user_resp.data:
            return jsonify({"error": "User not found"}), 404

        target_id = user_resp.data[0]["id"]
        if target_id == request.user_id:
            return jsonify({"error": "You are already in this group"}), 400

        # Check not already a member
        existing = supabase.table("study_group_members").select("id").eq(
            "group_id", group_id).eq("user_id", target_id).execute()
        if existing.data:
            return jsonify({"error": "User is already a member"}), 400

        # Check for existing pending invite
        existing_invite = supabase.table("study_group_invites").select("id, status").eq(
            "group_id", group_id).eq("invited_user_id", target_id).execute()
        if existing_invite.data:
            if existing_invite.data[0]["status"] == "pending":
                return jsonify({"error": "Invite already pending"}), 400
            # Update declined invite back to pending
            supabase.table("study_group_invites").update({
                "status": "pending",
                "invited_by": request.user_id
            }).eq("id", existing_invite.data[0]["id"]).execute()
        else:
            supabase.table("study_group_invites").insert({
                "group_id": group_id,
                "invited_by": request.user_id,
                "invited_user_id": target_id,
                "status": "pending"
            }).execute()

        # Send notification
        group_resp = supabase.table("study_groups").select("name").eq("id", group_id).execute()
        group_name = group_resp.data[0]["name"] if group_resp.data else "a study group"
        inviter_profile = supabase.table("user_profiles").select("username").eq("id", request.user_id).execute()
        inviter_name = inviter_profile.data[0]["username"] if inviter_profile.data else "Someone"

        create_notification(
            user_id=target_id,
            notif_type="group_invite",
            title="Study Group Invite",
            message=f"@{inviter_name} invited you to '{group_name}'",
        )

        debug_log(f"[Groups] Invited @{username} to group {group_id}")
        return jsonify({"success": True}), 200

    except Exception as e:
        debug_log(f"Invite to group error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/invites", methods=["GET"])
@supabase_auth_required
def get_pending_invites():
    """Get all pending group invites for the current user."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        invites_resp = supabase.table("study_group_invites").select(
            "id, group_id, invited_by, created_at"
        ).eq("invited_user_id", request.user_id).eq("status", "pending").order("created_at", desc=True).execute()

        invites = []
        for inv in (invites_resp.data or []):
            group = supabase.table("study_groups").select("name").eq("id", inv["group_id"]).execute()
            inviter = supabase.table("user_profiles").select("username").eq("id", inv["invited_by"]).execute()
            invites.append({
                "id": inv["id"],
                "group_id": inv["group_id"],
                "group_name": group.data[0]["name"] if group.data else "Unknown",
                "invited_by": inviter.data[0]["username"] if inviter.data else "Unknown",
                "created_at": inv["created_at"]
            })

        return jsonify({"invites": invites}), 200

    except Exception as e:
        debug_log(f"Get invites error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/invites/<invite_id>/accept", methods=["POST"])
@supabase_auth_required
def accept_invite(invite_id):
    """Accept a group invite."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        invite = supabase.table("study_group_invites").select(
            "id, group_id, invited_user_id, status"
        ).eq("id", invite_id).execute()

        if not invite.data:
            return jsonify({"error": "Invite not found"}), 404
        if invite.data[0]["invited_user_id"] != request.user_id:
            return jsonify({"error": "Not your invite"}), 403
        if invite.data[0]["status"] != "pending":
            return jsonify({"error": "Invite already responded to"}), 400

        group_id = invite.data[0]["group_id"]

        # Add to group
        supabase.table("study_group_members").insert({
            "group_id": group_id,
            "user_id": request.user_id,
            "role": "member"
        }).execute()

        # Update invite status
        supabase.table("study_group_invites").update({
            "status": "accepted"
        }).eq("id", invite_id).execute()

        debug_log(f"[Groups] User {request.user_id} accepted invite to group {group_id}")
        return jsonify({"success": True, "group_id": group_id}), 200

    except Exception as e:
        debug_log(f"Accept invite error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/invites/<invite_id>/decline", methods=["POST"])
@supabase_auth_required
def decline_invite(invite_id):
    """Decline a group invite."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        invite = supabase.table("study_group_invites").select(
            "id, invited_user_id, status"
        ).eq("id", invite_id).execute()

        if not invite.data:
            return jsonify({"error": "Invite not found"}), 404
        if invite.data[0]["invited_user_id"] != request.user_id:
            return jsonify({"error": "Not your invite"}), 403

        supabase.table("study_group_invites").update({
            "status": "declined"
        }).eq("id", invite_id).execute()

        debug_log(f"[Groups] User {request.user_id} declined invite {invite_id}")
        return jsonify({"success": True}), 200

    except Exception as e:
        debug_log(f"Decline invite error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/join/<invite_code>", methods=["POST"])
@supabase_auth_required
def join_group(invite_code):
    """Join a group via invite code."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        group = supabase.table("study_groups").select("id, name").eq("invite_code", invite_code).execute()
        if not group.data:
            return jsonify({"error": "Invalid invite code"}), 404

        group_id = group.data[0]["id"]

        existing = supabase.table("study_group_members").select("id").eq(
            "group_id", group_id).eq("user_id", request.user_id).execute()
        if existing.data:
            return jsonify({"error": "Already a member", "group_id": group_id}), 400

        supabase.table("study_group_members").insert({
            "group_id": group_id,
            "user_id": request.user_id,
            "role": "member"
        }).execute()

        debug_log(f"[Groups] User {request.user_id} joined group {group_id} via invite")
        return jsonify({"success": True, "group_id": group_id, "group_name": group.data[0]["name"]}), 200

    except Exception as e:
        debug_log(f"Join group error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/<group_id>/members/<user_id>", methods=["DELETE"])
@supabase_auth_required
def remove_group_member(group_id, user_id):
    """Remove a member from a group. Owner or self only."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        group = supabase.table("study_groups").select("owner_id").eq("id", group_id).execute()
        if not group.data:
            return jsonify({"error": "Group not found"}), 404

        is_owner = group.data[0]["owner_id"] == request.user_id
        is_self = user_id == request.user_id

        if not is_owner and not is_self:
            return jsonify({"error": "Not authorized"}), 403

        if is_owner and is_self:
            return jsonify({"error": "Owner cannot leave. Delete the group instead."}), 400

        supabase.table("study_group_members").delete().eq(
            "group_id", group_id).eq("user_id", user_id).execute()

        debug_log(f"[Groups] Removed user {user_id} from group {group_id}")
        return jsonify({"success": True}), 200

    except Exception as e:
        debug_log(f"Remove member error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/<group_id>/notes/upload", methods=["POST"])
@supabase_auth_required
def upload_group_note(group_id):
    """Upload a file directly to the group. Does not appear in personal notes or Nexus."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        member_check = supabase.table("study_group_members").select("id").eq(
            "group_id", group_id).eq("user_id", request.user_id).execute()
        if not member_check.data:
            return jsonify({"error": "Not a member"}), 403

        if "file" not in request.files:
            return jsonify({"error": "No file provided"}), 400

        file = request.files["file"]
        if not file.filename:
            return jsonify({"error": "Empty filename"}), 400

        filename = file.filename
        file_bytes = file.read()
        file_size = len(file_bytes)

        # Determine file type
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        content_type = file.content_type or "application/octet-stream"

        # Upload to Supabase storage under group-notes path
        storage_path = f"group-notes/{group_id}/{uuid.uuid4()}_{filename}"
        supabase.storage.from_("note-files").upload(
            storage_path, file_bytes,
            file_options={"content-type": content_type}
        )

        # Save record
        supabase.table("study_group_notes").insert({
            "group_id": group_id,
            "added_by": request.user_id,
            "filename": filename,
            "file_path": storage_path,
            "file_size": file_size,
            "file_type": ext
        }).execute()

        debug_log(f"[Groups] Uploaded '{filename}' to group {group_id}")
        return jsonify({"success": True, "filename": filename}), 200

    except Exception as e:
        debug_log(f"Upload group note error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/<group_id>/notes/<note_id>", methods=["DELETE"])
@supabase_auth_required
def remove_group_note(group_id, note_id):
    """Remove a note from the group. Adder or owner only."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        group = supabase.table("study_groups").select("owner_id").eq("id", group_id).execute()
        if not group.data:
            return jsonify({"error": "Group not found"}), 404

        note_entry = supabase.table("study_group_notes").select("added_by, file_path").eq(
            "group_id", group_id).eq("id", note_id).execute()
        if not note_entry.data:
            return jsonify({"error": "Note not in group"}), 404

        is_owner = group.data[0]["owner_id"] == request.user_id
        is_adder = note_entry.data[0]["added_by"] == request.user_id

        if not is_owner and not is_adder:
            return jsonify({"error": "Not authorized"}), 403

        # Delete file from storage if it has a file_path
        file_path = note_entry.data[0].get("file_path")
        if file_path:
            try:
                supabase.storage.from_("note-files").remove([file_path])
            except Exception:
                pass

        supabase.table("study_group_notes").delete().eq(
            "group_id", group_id).eq("id", note_id).execute()

        return jsonify({"success": True}), 200

    except Exception as e:
        debug_log(f"Remove group note error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/<group_id>/notes/<note_id>/download", methods=["GET"])
@supabase_auth_required
def download_group_note(group_id, note_id):
    """Get a signed download URL for a group note."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        member_check = supabase.table("study_group_members").select("id").eq(
            "group_id", group_id).eq("user_id", request.user_id).execute()
        if not member_check.data:
            return jsonify({"error": "Not a member"}), 403

        note = supabase.table("study_group_notes").select("file_path, filename").eq(
            "group_id", group_id).eq("id", note_id).execute()
        if not note.data or not note.data[0].get("file_path"):
            return jsonify({"error": "Note not found"}), 404

        signed = supabase.storage.from_("note-files").create_signed_url(
            note.data[0]["file_path"], 3600
        )
        url = signed.get("signedURL") or signed.get("signedUrl", "")

        return jsonify({"url": url, "filename": note.data[0]["filename"]}), 200

    except Exception as e:
        debug_log(f"Download group note error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/<group_id>/chat", methods=["POST"])
@supabase_auth_required
def group_chat(group_id):
    """Send a message in the group chat. Users only, no AI."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        # Verify membership
        member_check = supabase.table("study_group_members").select("id").eq(
            "group_id", group_id).eq("user_id", request.user_id).execute()
        if not member_check.data:
            return jsonify({"error": "Not a member"}), 403

        data = request.get_json()
        message = data.get("message", "").strip()
        if not message:
            return jsonify({"error": "Missing message"}), 400

        # Get sender username
        sender_profile = supabase.table("user_profiles").select("username").eq("id", request.user_id).execute()
        sender_username = sender_profile.data[0]["username"] if sender_profile.data else "User"

        # Save user message
        supabase.table("study_group_messages").insert({
            "group_id": group_id,
            "user_id": request.user_id,
            "role": "user",
            "content": message
        }).execute()

        return jsonify({
            "success": True,
            "sender_username": sender_username
        }), 200

    except Exception as e:
        debug_log(f"Group chat error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/<group_id>/messages", methods=["GET"])
@supabase_auth_required
def get_group_messages(group_id):
    """Get chat history for a group."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        member_check = supabase.table("study_group_members").select("id").eq(
            "group_id", group_id).eq("user_id", request.user_id).execute()
        if not member_check.data:
            return jsonify({"error": "Not a member"}), 403

        messages_resp = supabase.table("study_group_messages").select(
            "id, user_id, role, content, sources, created_at, pinned"
        ).eq("group_id", group_id).order("created_at").limit(100).execute()

        messages = []
        username_cache = {}
        for m in (messages_resp.data or []):
            username = None
            if m["user_id"]:
                if m["user_id"] not in username_cache:
                    profile = supabase.table("user_profiles").select("username").eq("id", m["user_id"]).execute()
                    username_cache[m["user_id"]] = profile.data[0]["username"] if profile.data else "Unknown"
                username = username_cache[m["user_id"]]

            messages.append({
                "id": m["id"],
                "role": m["role"],
                "content": m["content"],
                "sources": m.get("sources", []),
                "username": username,
                "user_id": m["user_id"],
                "created_at": m["created_at"],
                "pinned": m.get("pinned", False)
            })

        return jsonify({"messages": messages}), 200

    except Exception as e:
        debug_log(f"Get group messages error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────
# Pinned Messages & Study Schedule
# ──────────────────────────────────────────────

@app.route("/api/groups/<group_id>/messages/<message_id>/pin", methods=["POST"])
@supabase_auth_required
def pin_message(group_id, message_id):
    """Pin or unpin a group message. Owner or message sender only."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        member_check = supabase.table("study_group_members").select("role").eq(
            "group_id", group_id).eq("user_id", request.user_id).execute()
        if not member_check.data:
            return jsonify({"error": "Not a member"}), 403

        msg = supabase.table("study_group_messages").select("id, user_id, pinned").eq(
            "id", message_id).eq("group_id", group_id).execute()
        if not msg.data:
            return jsonify({"error": "Message not found"}), 404

        is_owner = member_check.data[0]["role"] == "owner"
        is_sender = msg.data[0]["user_id"] == request.user_id
        if not is_owner and not is_sender:
            return jsonify({"error": "Not authorized"}), 403

        new_pinned = not msg.data[0].get("pinned", False)
        supabase.table("study_group_messages").update({
            "pinned": new_pinned,
            "pinned_by": request.user_id if new_pinned else None
        }).eq("id", message_id).execute()

        return jsonify({"success": True, "pinned": new_pinned}), 200

    except Exception as e:
        debug_log(f"Pin message error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/<group_id>/pinned", methods=["GET"])
@supabase_auth_required
def get_pinned_messages(group_id):
    """Get all pinned messages for a group."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        member_check = supabase.table("study_group_members").select("id").eq(
            "group_id", group_id).eq("user_id", request.user_id).execute()
        if not member_check.data:
            return jsonify({"error": "Not a member"}), 403

        pinned = supabase.table("study_group_messages").select(
            "id, user_id, content, created_at"
        ).eq("group_id", group_id).eq("pinned", True).order("created_at", desc=True).execute()

        messages = []
        cache = {}
        for m in (pinned.data or []):
            if m["user_id"] and m["user_id"] not in cache:
                p = supabase.table("user_profiles").select("username").eq("id", m["user_id"]).execute()
                cache[m["user_id"]] = p.data[0]["username"] if p.data else "Unknown"
            messages.append({
                "id": m["id"],
                "content": m["content"],
                "username": cache.get(m["user_id"], "Unknown"),
                "created_at": m["created_at"]
            })

        return jsonify({"pinned": messages}), 200

    except Exception as e:
        debug_log(f"Get pinned error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/<group_id>/events", methods=["GET"])
@supabase_auth_required
def get_group_events(group_id):
    """Get all events for a group, ordered by date."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        member_check = supabase.table("study_group_members").select("id").eq(
            "group_id", group_id).eq("user_id", request.user_id).execute()
        if not member_check.data:
            return jsonify({"error": "Not a member"}), 403

        events_resp = supabase.table("study_group_events").select(
            "id, title, description, event_date, event_time, created_by, created_at"
        ).eq("group_id", group_id).order("event_date").execute()

        events = []
        cache = {}
        for ev in (events_resp.data or []):
            if ev["created_by"] not in cache:
                p = supabase.table("user_profiles").select("username").eq("id", ev["created_by"]).execute()
                cache[ev["created_by"]] = p.data[0]["username"] if p.data else "Unknown"
            events.append({
                "id": ev["id"],
                "title": ev["title"],
                "description": ev.get("description"),
                "event_date": ev["event_date"],
                "event_time": ev.get("event_time"),
                "created_by": cache[ev["created_by"]],
                "created_by_id": ev["created_by"],
                "created_at": ev["created_at"]
            })

        return jsonify({"events": events}), 200

    except Exception as e:
        debug_log(f"Get events error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/<group_id>/events", methods=["POST"])
@supabase_auth_required
def create_group_event(group_id):
    """Create a study event."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        member_check = supabase.table("study_group_members").select("id").eq(
            "group_id", group_id).eq("user_id", request.user_id).execute()
        if not member_check.data:
            return jsonify({"error": "Not a member"}), 403

        data = request.get_json()
        title = data.get("title", "").strip()
        if not title:
            return jsonify({"error": "Missing title"}), 400
        event_date = data.get("event_date")
        if not event_date:
            return jsonify({"error": "Missing date"}), 400

        row = {
            "group_id": group_id,
            "title": title[:100],
            "event_date": event_date,
            "created_by": request.user_id
        }
        if data.get("description"):
            row["description"] = data["description"].strip()[:500]
        if data.get("event_time"):
            row["event_time"] = data["event_time"]

        supabase.table("study_group_events").insert(row).execute()

        debug_log(f"[Groups] Created event '{title}' in group {group_id}")
        return jsonify({"success": True}), 200

    except Exception as e:
        debug_log(f"Create event error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/groups/<group_id>/events/<event_id>", methods=["DELETE"])
@supabase_auth_required
def delete_group_event(group_id, event_id):
    """Delete a study event. Creator or group owner only."""
    try:
        from StudyFlow.backend.supabase_client import supabase

        group = supabase.table("study_groups").select("owner_id").eq("id", group_id).execute()
        if not group.data:
            return jsonify({"error": "Group not found"}), 404

        event = supabase.table("study_group_events").select("created_by").eq("id", event_id).eq("group_id", group_id).execute()
        if not event.data:
            return jsonify({"error": "Event not found"}), 404

        is_owner = group.data[0]["owner_id"] == request.user_id
        is_creator = event.data[0]["created_by"] == request.user_id
        if not is_owner and not is_creator:
            return jsonify({"error": "Not authorized"}), 403

        supabase.table("study_group_events").delete().eq("id", event_id).execute()
        return jsonify({"success": True}), 200

    except Exception as e:
        debug_log(f"Delete event error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


# ──────────────────────────────────────────────
# Admin: University Stats (Institutional License Prep)
# ──────────────────────────────────────────────

@app.route("/admin/review-queue", methods=["GET"])
def review_queue():
    """ADMIN: Get unreviewed notes for quality control."""
    try:
        admin_key = request.args.get("key", "")
        if admin_key != os.getenv("ADMIN_KEY", "change_me_in_production"):
            return jsonify({"error": "Unauthorized"}), 403

        from StudyFlow.backend.supabase_client import supabase

        # Get IDs of already-reviewed notes
        reviewed_resp = supabase.table("reviewed_notes").select("note_id").execute()
        reviewed_ids = set(r["note_id"] for r in (reviewed_resp.data or []))

        # Get all notes
        notes_resp = supabase.table("notes").select(
            "id, user_id, original_filename, file_size, university, course_code, file_path, uploaded_at, is_public"
        ).order("uploaded_at").limit(200).execute()

        # Filter out already reviewed
        unreviewed = [n for n in (notes_resp.data or []) if n["id"] not in reviewed_ids][:50]

        notes = []
        uploader_cache = {}
        for n in unreviewed:
            # Get uploader info (cached)
            uid = n["user_id"]
            if uid not in uploader_cache:
                try:
                    profile = supabase.table("user_profiles").select("username, email").eq("id", uid).execute()
                    uploader_cache[uid] = profile.data[0].get("username") or profile.data[0].get("email", "Unknown") if profile.data else "Unknown"
                except Exception:
                    uploader_cache[uid] = "Unknown"
            uploader = uploader_cache[uid]

            notes.append({
                "id": n["id"],
                "filename": n.get("original_filename", "Unknown"),
                "file_size": n.get("file_size", 0),
                "university": n.get("university"),
                "course_code": n.get("course_code"),
                "uploader": uploader,
                "uploader_id": n["user_id"],
                "is_public": n.get("is_public", True),
                "created_at": n.get("uploaded_at")
            })

        return jsonify({"notes": notes, "total": len(notes)}), 200

    except Exception as e:
        debug_log(f"Review queue error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/admin/review/<note_id>", methods=["POST"])
def review_note(note_id):
    """ADMIN: Approve or reject a note."""
    try:
        data = request.get_json()
        admin_key = data.get("key", "")
        if admin_key != os.getenv("ADMIN_KEY", "change_me_in_production"):
            return jsonify({"error": "Unauthorized"}), 403

        action = data.get("action")
        if action not in ("approve", "reject"):
            return jsonify({"error": "Action must be 'approve' or 'reject'"}), 400

        from StudyFlow.backend.supabase_client import supabase

        # Get note info
        note_resp = supabase.table("notes").select("user_id, original_filename, file_path").eq("id", note_id).execute()
        if not note_resp.data:
            return jsonify({"error": "Note not found"}), 404

        note = note_resp.data[0]

        if action == "approve":
            supabase.table("reviewed_notes").upsert({
                "note_id": note_id,
                "action": "approved"
            }).execute()
            debug_log(f"[Review] Approved note {note_id}")
        else:
            reason = data.get("reason", "Does not meet quality standards")
            filename = note.get("original_filename", "your note")

            # Delete file from storage
            if note.get("file_path"):
                try:
                    supabase.storage.from_("note-files").remove([note["file_path"]])
                except Exception:
                    pass

            # Delete note chunks
            try:
                supabase.table("note_chunks").delete().eq("note_id", note_id).execute()
            except Exception:
                pass

            # Delete note record
            supabase.table("notes").delete().eq("id", note_id).execute()

            # Notify the user
            create_notification(
                user_id=note["user_id"],
                notif_type="note_removed",
                title="Note Removed",
                message=f"Your note '{filename}' was removed: {reason}",
            )

            debug_log(f"[Review] Rejected and deleted note {note_id}: {reason}")

        return jsonify({"success": True, "action": action}), 200

    except Exception as e:
        debug_log(f"Review note error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/admin/note-preview/<note_id>", methods=["GET"])
def admin_note_preview(note_id):
    """ADMIN: Get a signed URL for previewing a note."""
    try:
        admin_key = request.args.get("key", "")
        if admin_key != os.getenv("ADMIN_KEY", "change_me_in_production"):
            return jsonify({"error": "Unauthorized"}), 403

        from StudyFlow.backend.supabase_client import supabase

        note = supabase.table("notes").select("file_path, original_filename").eq("id", note_id).execute()
        if not note.data or not note.data[0].get("file_path"):
            return jsonify({"error": "Note not found"}), 404

        signed = supabase.storage.from_("note-files").create_signed_url(note.data[0]["file_path"], 3600)
        url = signed.get("signedURL") or signed.get("signedUrl", "")

        return jsonify({"url": url, "filename": note.data[0].get("original_filename")}), 200

    except Exception as e:
        debug_log(f"Admin note preview error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/admin/university-stats", methods=["GET"])
def university_stats():
    """Per-university metrics for institutional license sales pitches."""
    try:
        admin_key = request.args.get("key", "")
        if admin_key != os.getenv("ADMIN_KEY", "change_me_in_production"):
            return jsonify({"error": "Unauthorized"}), 403

        from StudyFlow.backend.supabase_client import supabase

        # Get all verified users grouped by university
        profiles = supabase.table("user_profiles").select(
            "id, university, edu_email_verified"
        ).eq("edu_email_verified", True).not_.is_("university", "null").execute()

        uni_users = {}
        all_user_ids = set()
        for p in (profiles.data or []):
            uni = p["university"]
            if uni not in uni_users:
                uni_users[uni] = []
            uni_users[uni].append(p["id"])
            all_user_ids.add(p["id"])

        # Get note counts per university
        notes = supabase.table("notes").select(
            "user_id, university, course_code"
        ).not_.is_("university", "null").execute()

        uni_notes = {}
        uni_courses = {}
        for n in (notes.data or []):
            uni = n.get("university", "Unknown")
            if uni not in uni_notes:
                uni_notes[uni] = 0
                uni_courses[uni] = set()
            uni_notes[uni] += 1
            if n.get("course_code"):
                uni_courses[uni].add(n["course_code"])

        # Get AI query counts from provenance logs
        uni_queries = {}
        try:
            for uni, user_ids in uni_users.items():
                if not user_ids:
                    continue
                count_resp = supabase.table("ai_provenance_logs").select(
                    "id", count="exact"
                ).in_("user_id", user_ids[:50]).execute()
                uni_queries[uni] = count_resp.count or 0
        except Exception:
            pass  # Table might not exist yet

        # Get study group counts per university
        uni_groups = {}
        try:
            groups = supabase.table("study_groups").select(
                "institution"
            ).not_.is_("institution", "null").execute()
            for g in (groups.data or []):
                inst = g["institution"]
                uni_groups[inst] = uni_groups.get(inst, 0) + 1
        except Exception:
            pass

        # Build response
        universities = []
        all_unis = set(list(uni_users.keys()) + list(uni_notes.keys()))
        for uni in sorted(all_unis):
            universities.append({
                "university": uni,
                "verified_users": len(uni_users.get(uni, [])),
                "notes_uploaded": uni_notes.get(uni, 0),
                "courses_covered": len(uni_courses.get(uni, set())),
                "top_courses": sorted(list(uni_courses.get(uni, set())))[:10],
                "ai_queries": uni_queries.get(uni, 0),
                "study_groups": uni_groups.get(uni, 0)
            })

        # Totals
        totals = {
            "total_universities": len(all_unis),
            "total_verified_users": sum(len(v) for v in uni_users.values()),
            "total_notes": sum(uni_notes.values()),
            "total_courses": sum(len(v) for v in uni_courses.values()),
            "total_ai_queries": sum(uni_queries.values()),
            "total_study_groups": sum(uni_groups.values())
        }

        return jsonify({"totals": totals, "universities": universities}), 200

    except Exception as e:
        debug_log(f"University stats error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    try:
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port)
    except Exception as e:
        debug_log(f"Server startup error: {e}\n{traceback.format_exc()}")
