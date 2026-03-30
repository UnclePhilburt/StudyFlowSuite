"""
Supabase Auth for StudyFlow
Replaces custom JWT system with Supabase Auth.
Sessions cached in Redis to avoid Supabase network call on every request.
"""

import os
import json
import hashlib
from functools import wraps
from flask import request, jsonify
from StudyFlow.backend.supabase_client import supabase
from StudyFlow.logging_utils import debug_log

# Redis session cache
_session_redis = None
SESSION_CACHE_TTL = 300  # 5 minutes -- short enough for security, long enough to help

def _get_session_redis():
    global _session_redis
    if _session_redis is None:
        try:
            import redis
            url = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
            _session_redis = redis.from_url(url, decode_responses=True)
            _session_redis.ping()
        except:
            _session_redis = False
    return _session_redis if _session_redis else None


def supabase_auth_required(f):
    """
    Decorator to protect routes with Supabase Auth.

    Expects Authorization header: "Bearer <supabase_jwt>"

    Sets request.user_id and request.user_email for use in route handlers.

    Sessions are cached in Redis for 5 minutes to avoid hitting Supabase
    on every request. Token hash is used as key (not the token itself).
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Allow OPTIONS requests (CORS preflight) without authentication
        if request.method == 'OPTIONS':
            return f(*args, **kwargs)

        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')

        if not auth_header:
            return jsonify({"error": "Missing Authorization header"}), 401

        # Extract token (format: "Bearer <token>")
        parts = auth_header.split()
        if len(parts) != 2 or parts[0].lower() != 'bearer':
            return jsonify({"error": "Invalid Authorization header format"}), 401

        token = parts[1]

        # Check Redis session cache first
        token_hash = hashlib.sha256(token.encode()).hexdigest()[:32]
        cache_key = f"session:{token_hash}"
        r = _get_session_redis()

        if r:
            try:
                cached = r.get(cache_key)
                if cached:
                    session_data = json.loads(cached)
                    request.user_id = session_data["user_id"]
                    request.user_email = session_data["user_email"]
                    return f(*args, **kwargs)
            except:
                pass

        try:
            # Verify token with Supabase (network call)
            user = supabase.auth.get_user(token)

            if not user or not user.user:
                return jsonify({"error": "Invalid or expired token"}), 401

            # Set user info on request object
            request.user_id = user.user.id
            request.user_email = user.user.email

            # Cache in Redis
            if r:
                try:
                    r.setex(cache_key, SESSION_CACHE_TTL, json.dumps({
                        "user_id": user.user.id,
                        "user_email": user.user.email
                    }))
                except:
                    pass

            return f(*args, **kwargs)

        except Exception as e:
            debug_log(f"[-] Auth error: {e}")
            return jsonify({"error": "Authentication failed", "details": str(e)}), 401

    return decorated_function


def account_not_frozen(f):
    """
    Decorator to block frozen accounts from AI features (Missouri SB 1455 / GUARD Act).

    Must be used AFTER @supabase_auth_required so request.user_id is set.
    Returns 403 with verification instructions if account is frozen.
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        try:
            from StudyFlow.backend.supabase_client import get_verification_status

            status = get_verification_status(request.user_id)

            if status and status.get('account_frozen'):
                reason = status.get('frozen_reason', 'age_verification_required')
                debug_log(f"[!] Blocked frozen account: {request.user_id} (reason: {reason})")
                return jsonify({
                    "error": "Account frozen - age verification required",
                    "frozen": True,
                    "reason": reason,
                    "verify_url": "https://unclephilburt.github.io/studyflowwebsite/verify-age.html"
                }), 403

        except Exception as e:
            debug_log(f"[-] Error checking freeze status: {e}")
            # Don't block on error -- fail open for now
            pass

        return f(*args, **kwargs)

    return decorated_function


def create_user_with_metadata(email: str, password: str, full_name: str = None, collective_brain_opt_in: bool = False):
    """
    Sign up a new user with Supabase Auth and create their profile.

    Returns: (user_data, error)
    """
    try:
        # Sign up with Supabase Auth
        auth_response = supabase.auth.sign_up({
            "email": email,
            "password": password
        })

        if not auth_response.user:
            return None, "Failed to create user"

        user_id = auth_response.user.id
        debug_log(f"✅ Created Supabase Auth user: {email} ({user_id})")

        # Create user profile in our custom table
        from StudyFlow.backend.supabase_client import create_user_profile
        profile = create_user_profile(
            user_id=user_id,
            email=email,
            full_name=full_name,
            collective_brain_opt_in=collective_brain_opt_in
        )

        if not profile:
            # Rollback - delete the auth user
            # Note: Supabase doesn't provide easy rollback, so we just log it
            debug_log(f"⚠️ Failed to create profile for {email}, but auth user exists")

        return {
            "user": auth_response.user,
            "session": auth_response.session
        }, None

    except Exception as e:
        debug_log(f"❌ Sign up error: {e}")
        return None, str(e)


def sign_in_user(email: str, password: str):
    """
    Sign in a user with Supabase Auth.

    Returns: (session_data, error)
    """
    try:
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })

        if not response.session:
            return None, "Invalid credentials"

        debug_log(f"✅ User signed in: {email}")

        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "user": response.user,
            "expires_in": response.session.expires_in
        }, None

    except Exception as e:
        debug_log(f"❌ Sign in error: {e}")
        return None, "Invalid email or password"


def refresh_access_token(refresh_token: str):
    """
    Refresh an expired access token using a refresh token.

    Returns: (new_session_data, error)
    """
    try:
        response = supabase.auth.refresh_session(refresh_token)

        if not response.session:
            return None, "Invalid refresh token"

        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "expires_in": response.session.expires_in
        }, None

    except Exception as e:
        debug_log(f"❌ Refresh token error: {e}")
        return None, "Failed to refresh token"


def sign_out_user(token: str):
    """
    Sign out a user (invalidate their session).

    Returns: (success, error)
    """
    try:
        supabase.auth.sign_out(token)
        debug_log(f"✅ User signed out")
        return True, None

    except Exception as e:
        debug_log(f"❌ Sign out error: {e}")
        return False, str(e)


def reset_password_email(email: str):
    """
    Send password reset email via Supabase Auth.

    Returns: (success, error)
    """
    try:
        supabase.auth.reset_password_for_email(email, {
            "redirect_to": "https://studyflowsuite.com/reset-password.html"
        })
        debug_log(f"✅ Password reset email sent to {email}")
        return True, None

    except Exception as e:
        debug_log(f"❌ Password reset error: {e}")
        return False, str(e)


def update_user_password(token: str, new_password: str):
    """
    Update user's password (requires valid token).

    Returns: (success, error)
    """
    try:
        user = supabase.auth.get_user(token)
        if not user or not user.user:
            return False, "Invalid token"

        supabase.auth.update_user(token, {"password": new_password})
        debug_log(f"✅ Password updated for user {user.user.email}")
        return True, None

    except Exception as e:
        debug_log(f"❌ Update password error: {e}")
        return False, str(e)
