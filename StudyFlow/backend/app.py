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
import requests
import stripe


from StudyFlow.backend.image_processing import preprocess_image
from StudyFlow.config import TESSERACT_PATH
from StudyFlow.logging_utils import debug_log
from StudyFlow.backend.submit_button_storage import register_submit_button_upload
from StudyFlow.backend.tasks import process_question_async, celery_app
from StudyFlow.backend import tasks  # 🧠 registers the Celery task
from StudyFlow.backend.supabase_auth import supabase_auth_required  # Supabase Auth decorator
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
CORS(app,
     resources={r"/api/*": {"origins": [
         "https://unclephilburt.github.io",
         "http://localhost:*",
         "http://127.0.0.1:*"
     ]}},
     allow_headers=["Content-Type", "Authorization"],
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     supports_credentials=True,
     expose_headers=["Content-Type", "Authorization"]
)

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
        cur.execute("SELECT stripe_customer_id FROM user_profiles WHERE email = %s", (email,))
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
        if file_ext not in ['pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx', 'txt']:
            return jsonify({"error": "Unsupported file type. Allowed: PDF, JPG, PNG, DOC, DOCX, TXT"}), 400

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
        model = genai.GenerativeModel('gemini-2.0-flash-exp')

        if file_ext in ['jpg', 'jpeg', 'png']:
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

        else:
            # Word docs
            ocr_text = f"[{file_ext.upper()} document]"
            page_count = 1

        # Check page limit BEFORE uploading
        allowed, message = check_page_limit(request.user_id, page_count)
        if not allowed:
            return jsonify({"error": message, "limit_exceeded": True}), 403

        # Upload file to Supabase Storage
        import uuid
        unique_filename = f"{request.user_id}/{uuid.uuid4()}_{original_filename}"

        content_type_map = {
            'pdf': 'application/pdf',
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'txt': 'text/plain',
            'doc': 'application/msword',
            'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        }
        content_type = content_type_map.get(file_ext, 'application/octet-stream')

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

        return jsonify({
            "success": True,
            "note_id": note_id,
            "filename": original_filename,
            "pages": page_count,
            "processing": True,
            "message": "Note uploaded! Processing in background..."
        }), 200

    except Exception as e:
        debug_log(f"❌ Upload error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/list", methods=["GET"])
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

        for note_id in user_notes.keys():
            # Count total usage using JSONB containment operator
            # This checks if the sources array contains an object with this note_id
            total_count_response = supabase.table("conversation_messages").select("id", count="exact").contains("sources", [{"note_id": note_id}]).execute()
            count = total_count_response.count if total_count_response.count else 0

            if count > 0:
                note_usage[note_id] = count
                total_usage += count

            # Count weekly usage
            weekly_count_response = supabase.table("conversation_messages").select("id", count="exact").contains("sources", [{"note_id": note_id}]).gte("created_at", week_ago).execute()
            weekly_count = weekly_count_response.count if weekly_count_response.count else 0
            weekly_usage += weekly_count

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
    Request body: { "filename": "new_name.pdf" }
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        data = request.get_json()
        new_filename = data.get("filename", "").strip()

        if not new_filename:
            return jsonify({"error": "Filename is required"}), 400

        # Verify ownership and update filename
        response = supabase.table("notes").update({
            "filename": new_filename
        }).eq("id", note_id).eq("user_id", request.user_id).execute()

        if response.data:
            debug_log(f"Renamed note {note_id} to {new_filename}")
            return jsonify({"success": True, "filename": new_filename}), 200
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
        verification_url = f"https://unclephilburt.github.io/studyflowsuitewebsite/verify-edu.html?token={verification_token}"

        message = Mail(
            from_email=Email("info@studyflowsuite.com", "StudyFlow Suite"),
            to_emails=edu_email,
            subject="Verify your university email - StudyFlow Suite"
        )

        message.dynamic_template_data = {
            'verification_url': verification_url,
            'email': edu_email
        }

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

        message.content = html_content
        message.mail_settings = MailSettings(sandbox_mode=SandBoxMode(enable=False))

        sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
        response = sg.send(message)

        debug_log(f"Verification email sent to {edu_email}")
        return jsonify({"success": True, "message": "Verification email sent"}), 200

    except Exception as e:
        debug_log(f"❌ Send .edu verification error: {e}\n{traceback.format_exc()}")
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
        debug_log(f"❌ Verify .edu email error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/notes/<note_id>/download", methods=["GET"])
@supabase_auth_required
def download_note_endpoint(note_id):
    """
    Download a note file by ID (only if it belongs to current user).
    """
    try:
        from StudyFlow.backend.supabase_client import supabase

        # Get note metadata to verify ownership and get file path
        note = supabase.table("notes").select("*").eq("id", note_id).eq("user_id", request.user_id).single().execute()

        if not note.data:
            return jsonify({"error": "Note not found or unauthorized"}), 404

        file_path = note.data.get('file_path')
        original_filename = note.data.get('original_filename')

        if not file_path:
            return jsonify({"error": "File not found in storage"}), 404

        # Download file from Supabase Storage
        file_data = supabase.storage.from_('note-files').download(file_path)

        # Return file as download
        from flask import send_file
        import io

        return send_file(
            io.BytesIO(file_data),
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=original_filename
        )

    except Exception as e:
        debug_log(f"❌ Download note error: {e}\n{traceback.format_exc()}")
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
            note = supabase.table("notes").select("original_filename").eq("id", result['note_id']).single().execute()
            filename = note.data['original_filename'] if note.data else "Unknown"

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
        from StudyFlow.backend.supabase_client import search_notes_vector, get_user_profile, supabase
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

        # Get or create conversation
        if conv_id:
            conversation = get_conversation(conv_id, request.user_id)
            if not conversation:
                return jsonify({"error": "Conversation not found or access denied"}), 404
        else:
            conv_id = create_conversation(request.user_id)
            conversation = get_conversation(conv_id, request.user_id)

        debug_log(f"💬 Chat message in conversation {conv_id}: '{message[:50]}...'")

        # Generate embedding for the question
        query_embedding = generate_embedding(message)
        if not query_embedding:
            return jsonify({"error": "Failed to generate query embedding"}), 500

        # Search database for relevant content
        search_results = search_notes_vector(
            query_embedding=query_embedding,
            user_id=request.user_id,
            university=None,
            course_code=None,
            match_threshold=0.4,
            match_count=5
        )

        debug_log(f"🔍 Found {len(search_results) if search_results else 0} relevant chunks")

        # Add search result metadata
        sources = []
        if search_results:
            for result in search_results[:3]:  # Top 3 sources
                note = supabase.table("notes").select("original_filename").eq("id", result['note_id']).single().execute()
                filename = note.data['original_filename'] if note.data else "Unknown"
                sources.append({
                    "note_id": result['note_id'],  # Include note_id for usage tracking
                    "filename": f"{filename} ({result['university']} - {result['course_code']})" if result['university'] else filename,
                    "similarity": round(result['similarity'], 2)
                })
                # Add original_filename to result for context
                result['original_filename'] = filename

        # Add user message to conversation
        add_message(conv_id, 'user', message)

        # Get conversation history from database
        conversation_history = get_conversation_messages(conv_id, request.user_id)

        # Generate conversational AI response
        ai_response = generate_conversational_response(
            question=message,
            search_results=search_results or [],
            conversation_history=conversation_history
        )

        # Add AI response to conversation
        add_message(conv_id, 'assistant', ai_response, sources)

        # Generate title for new conversations (if title is still None)
        if conversation and not conversation.get('title'):
            try:
                title = generate_conversation_title(message, ai_response)
                update_conversation_title(conv_id, title)
                debug_log(f"📝 Auto-generated title: {title}")
            except Exception as title_error:
                debug_log(f"⚠️ Failed to generate title: {title_error}")

        debug_log(f"✅ Generated conversational response ({len(ai_response)} chars)")

        return jsonify({
            "conversation_id": conv_id,
            "response": ai_response,
            "sources": sources
        }), 200

    except Exception as e:
        debug_log(f"❌ Chat error: {e}\n{traceback.format_exc()}")
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

        # Build query (removed username - use user_id instead)
        # Exclude Wikipedia notes (user_id is NULL)
        query = supabase.table("notes").select(
            "id, original_filename, university, course_code, user_id, topic_tags, page_count, uploaded_at"
        ).eq("is_public", True).not_.is_("user_id", "null")

        if university:
            query = query.eq("university", university)
        if course_code:
            query = query.eq("course_code", course_code)

        # Execute query
        response = query.order("uploaded_at", desc=True).limit(limit).execute()
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

            # Usage count - simplified for now (TODO: fix JSONB query)
            note['usage_count'] = 0

            # Rename original_filename to filename for frontend
            note['filename'] = note.pop('original_filename')

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

        # TODO: Send email notification to admin and confirmation to requestor

        return jsonify({
            "success": True,
            "request_id": request_id
        }), 200

    except Exception as e:
        debug_log(f"❌ DMCA takedown error: {e}\n{traceback.format_exc()}")
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

        # Get note details
        note = supabase.table("notes").select(
            "id, original_filename, university, course_code, user_id, page_count"
        ).eq("id", note_id).eq("is_public", True).single().execute()

        if not note.data:
            return jsonify({"error": "Note not found or not public"}), 404

        # Detect file type from extension
        filename = note.data['original_filename']
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

        # Get username
        try:
            user_profile = supabase.table("user_profiles").select("username").eq("id", note.data['user_id']).single().execute()
            username = user_profile.data['username'] if user_profile.data else 'Anonymous'
        except:
            username = 'Anonymous'

        # Build response
        note_data = {
            "id": note.data['id'],
            "filename": filename,
            "file_type": file_type,
            "extension": ext,
            "university": note.data.get('university'),
            "course_code": note.data.get('course_code'),
            "username": username,
            "page_count": note.data.get('page_count', 0)
        }

        return jsonify({"note": note_data}), 200

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


@app.route("/api/notes/<note_id>/download", methods=["GET"])
def download_note_file(note_id):
    """
    Download a note file directly (for non-viewable formats)
    No auth required since notes are already public
    """
    try:
        from StudyFlow.backend.supabase_client import supabase
        from flask import redirect

        # Verify note exists and is public
        note = supabase.table("notes").select("id, s3_key, pdf_url, file_url, original_filename").eq("id", note_id).eq("is_public", True).single().execute()

        if not note.data:
            return jsonify({"error": "Note not found or not public"}), 404

        # Try different URL fields
        file_url = None
        if note.data.get('pdf_url'):
            file_url = note.data['pdf_url']
        elif note.data.get('file_url'):
            file_url = note.data['file_url']
        elif note.data.get('s3_key'):
            try:
                file_url = supabase.storage.from_('notes').get_public_url(note.data['s3_key'])
            except:
                pass

        if file_url:
            # Add download headers
            response = redirect(file_url)
            response.headers['Content-Disposition'] = f'attachment; filename="{note.data["original_filename"]}"'
            return response
        else:
            return jsonify({"error": "File URL not found"}), 404

    except Exception as e:
        debug_log(f"❌ Download file error: {e}\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    try:
        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port)
    except Exception as e:
        debug_log(f"Server startup error: {e}\n{traceback.format_exc()}")
