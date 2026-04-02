"""
Supabase client for StudyFlow
Handles database, storage, and auth operations
"""

import os
from supabase import create_client, Client
from StudyFlow.logging_utils import debug_log

# Load .env file if it exists (for local development)
try:
    from dotenv import load_dotenv
    import pathlib
    env_path = pathlib.Path(__file__).parent.parent.parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"[+] Loaded .env from {env_path}")
except ImportError:
    pass  # python-dotenv not installed, use system env vars

# Initialize Supabase client
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

# Debug: Print what we actually got
print(f"[*] SUPABASE_URL = {SUPABASE_URL}")
print(f"[*] SUPABASE_SERVICE_KEY = {'[PRESENT]' if SUPABASE_SERVICE_KEY else '[MISSING]'}")
print(f"[*] All env vars with 'SUPABASE': {[k for k in os.environ.keys() if 'SUPABASE' in k]}")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print(f"[-] ERROR: SUPABASE_URL={SUPABASE_URL}, SERVICE_KEY={'[PRESENT]' if SUPABASE_SERVICE_KEY else '[MISSING]'}")
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY environment variables")

# Service role client (for backend operations)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

debug_log(f"[+] Supabase client initialized: {SUPABASE_URL}")


def get_user_profile(user_id: str) -> dict:
    """Get user profile from Supabase"""
    try:
        response = supabase.table("user_profiles").select("*").eq("id", user_id).single().execute()
        return response.data
    except Exception as e:
        debug_log(f"[-] Error fetching user profile: {e}")
        return None


def create_user_profile(user_id: str, email: str, full_name: str = None, username: str = None, collective_brain_opt_in: bool = True) -> dict:
    """Create a new user profile (Nexus enabled by default)"""
    try:
        response = supabase.table("user_profiles").insert({
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "username": username,
            "collective_brain_opt_in": collective_brain_opt_in,
            "subscription_tier": "free",
            "pages_uploaded_this_month": 0
        }).execute()
        debug_log(f"[+] Created user profile: {email} (@{username}) (Nexus: {collective_brain_opt_in})")
        return response.data[0]
    except Exception as e:
        debug_log(f"[-] Error creating user profile: {e}")
        return None


def check_page_limit(user_id: str, pages_to_add: int) -> tuple[bool, str]:
    """
    Check if user has exceeded their monthly page limit
    Returns: (allowed: bool, message: str)
    """
    try:
        profile = get_user_profile(user_id)
        if not profile:
            return False, "User profile not found"

        tier = profile.get("subscription_tier", "free")
        current_pages = profile.get("pages_uploaded_this_month", 0)

        # Define limits
        limits = {
            "free": 50,
            "pro": 500,
            "enterprise": float('inf')
        }

        limit = limits.get(tier, 50)

        if current_pages + pages_to_add > limit:
            return False, f"Monthly limit reached ({current_pages}/{limit} pages). Upgrade to Pro for more!"

        return True, f"OK ({current_pages + pages_to_add}/{limit} pages used this month)"

    except Exception as e:
        debug_log(f"[-] Error checking page limit: {e}")
        return False, "Error checking limits"


def increment_page_count(user_id: str, pages: int) -> bool:
    """Increment user's monthly page count"""
    try:
        # Get current count
        profile = get_user_profile(user_id)
        if not profile:
            return False

        new_count = profile.get("pages_uploaded_this_month", 0) + pages

        # Update
        supabase.table("user_profiles").update({
            "pages_uploaded_this_month": new_count
        }).eq("id", user_id).execute()

        debug_log(f"[+] Incremented page count for user {user_id}: +{pages} pages (total: {new_count})")
        return True

    except Exception as e:
        debug_log(f"[-] Error incrementing page count: {e}")
        return False


def upload_file_to_storage(file_content: bytes, file_path: str, content_type: str) -> str:
    """
    Upload file to Supabase Storage
    Returns: public URL or signed URL
    """
    try:
        # Upload to 'note-files' bucket
        response = supabase.storage.from_("note-files").upload(
            path=file_path,
            file=file_content,
            file_options={"content-type": content_type}
        )

        debug_log(f"[+] Uploaded file to storage: {file_path}")

        # Generate signed URL (valid for 1 year)
        signed_url = supabase.storage.from_("note-files").create_signed_url(
            path=file_path,
            expires_in=31536000  # 1 year in seconds
        )

        return signed_url['signedURL']

    except Exception as e:
        debug_log(f"[-] Error uploading file to storage: {e}")
        return None


def create_note_record(user_id: str, filename: str, file_type: str, file_size: int,
                       file_path: str, page_count: int, course_metadata: dict = None, username: str = None) -> dict:
    """Create a note record in the database"""
    try:
        note_data = {
            "user_id": user_id,
            "original_filename": filename,
            "file_type": file_type,
            "file_size": file_size,
            "file_path": file_path,
            "page_count": page_count,
            "processed": False,
            "is_public": True,  # Default to public for note sharing
            "username": username
        }

        # Add course metadata if provided
        if course_metadata:
            note_data.update({
                "university": course_metadata.get("university"),
                "course_code": course_metadata.get("course_code"),
                "professor": course_metadata.get("professor"),
                "semester": course_metadata.get("semester")
            })

        response = supabase.table("notes").insert(note_data).execute()
        debug_log(f"[+] Created note record: {filename} (@{username})")
        return response.data[0]

    except Exception as e:
        debug_log(f"[-] Error creating note record: {e}")
        return None


def create_note_chunk(note_id: str, user_id: str, chunk_text: str, chunk_index: int,
                      embedding: list, course_metadata: dict = None, is_public: bool = False, username: str = None) -> dict:
    """Create a note chunk with embedding"""
    try:
        chunk_data = {
            "note_id": note_id,
            "user_id": user_id,
            "chunk_text": chunk_text,
            "chunk_index": chunk_index,
            "embedding": embedding,
            "is_public": is_public,
            "username": username
        }

        # Add course metadata if provided
        if course_metadata:
            chunk_data.update({
                "university": course_metadata.get("university"),
                "course_code": course_metadata.get("course_code"),
                "professor": course_metadata.get("professor")
            })

        response = supabase.table("note_chunks").insert(chunk_data).execute()
        return response.data[0]

    except Exception as e:
        debug_log(f"[-] Error creating note chunk: {e}")
        return None


def mark_note_as_processed(note_id: str) -> bool:
    """Mark a note as fully processed"""
    try:
        supabase.table("notes").update({"processed": True}).eq("id", note_id).execute()
        debug_log(f"[+] Marked note {note_id} as processed")
        return True
    except Exception as e:
        debug_log(f"[-] Error marking note as processed: {e}")
        return False


def make_note_public(note_id: str, user_id: str) -> bool:
    """Make a note and all its chunks public (for Nexus)"""
    try:
        # Update note
        supabase.table("notes").update({"is_public": True}).eq("id", note_id).eq("user_id", user_id).execute()

        # Update all chunks
        supabase.table("note_chunks").update({"is_public": True}).eq("note_id", note_id).execute()

        debug_log(f"[+] Made note {note_id} public")
        return True
    except Exception as e:
        debug_log(f"[-] Error making note public: {e}")
        return False


def search_notes_vector(query_embedding: list, user_id: str, university: str = None,
                       course_code: str = None, match_threshold: float = 0.7, match_count: int = 5) -> list:
    """
    Search notes using vector similarity. Results cached in Redis for 10 min.
    Returns chunks from user's own notes + ALL public notes (collective brain)
    """
    import json, hashlib

    # Build cache key from embedding hash + filters
    emb_hash = hashlib.md5(json.dumps(query_embedding[:8]).encode()).hexdigest()[:12]
    cache_key = f"vsearch:{emb_hash}:{university or ''}:{course_code or ''}:{match_threshold}:{match_count}"

    # Check Redis cache
    try:
        import redis as redis_lib
        url = os.getenv("CELERY_BROKER_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
        r = redis_lib.from_url(url, decode_responses=True)
        cached = r.get(cache_key)
        if cached:
            debug_log(f"[+] Vector search cache HIT ({cache_key[:30]}...)")
            return json.loads(cached)
    except:
        r = None

    try:
        # Call the PostgreSQL function
        debug_log(f"🔍 VECTOR SEARCH PARAMS: user_id={user_id}, university={university}, course={course_code}, threshold={match_threshold}, count={match_count}")

        response = supabase.rpc("search_notes_with_vector", {
            "query_embedding": query_embedding,
            "search_user_id": user_id,
            "search_university": university,
            "search_course_code": course_code,
            "match_threshold": match_threshold,
            "match_count": match_count
        }).execute()

        debug_log(f"[+] Vector search found {len(response.data)} results")

        # DEBUG: Show first few results with similarity scores
        if response.data:
            for i, result in enumerate(response.data[:3]):
                debug_log(f"  Result #{i+1}: similarity={result.get('similarity', 'N/A')}, note_id={result.get('note_id')}, content_preview={str(result.get('chunk_text', ''))[:80]}...")
        else:
            debug_log(f"  ⚠️ Database returned empty array - no matches above threshold {match_threshold}")

        # Cache results for 10 minutes
        if r and response.data:
            try:
                r.setex(cache_key, 600, json.dumps(response.data))
            except:
                pass

        return response.data

    except Exception as e:
        debug_log(f"[-] Error searching notes with vector: {e}")
        import traceback
        debug_log(f"Full error traceback: {traceback.format_exc()}")
        return []


def get_user_notes(user_id: str) -> list:
    """Get all notes for a user"""
    try:
        debug_log(f"[*] Querying notes for user_id: {user_id}")
        response = supabase.table("notes").select("*").eq("user_id", user_id).order("uploaded_at", desc=True).execute()
        debug_log(f"[*] Query returned {len(response.data)} notes")

        # Debug: Log first note's user_id to verify filtering
        if response.data:
            debug_log(f"[*] First note user_id: {response.data[0].get('user_id')}")

        return response.data
    except Exception as e:
        debug_log(f"[-] Error fetching user notes: {e}")
        return []


def delete_note(note_id: str, user_id: str) -> bool:
    """Delete a note and all its chunks"""
    try:
        # Supabase CASCADE will automatically delete chunks
        supabase.table("notes").delete().eq("id", note_id).eq("user_id", user_id).execute()
        debug_log(f"[+] Deleted note {note_id}")
        return True
    except Exception as e:
        debug_log(f"[-] Error deleting note: {e}")
        return False


def log_upload(user_id: str, file_name: str, file_hash: str, file_size: int,
               shared_with_nexus: bool, ip_address: str = None,
               university: str = None, course_code: str = None) -> dict:
    """
    Log an upload to the upload_logs table (Missouri SB 1324 compliance - 7-year retention).

    Args:
        user_id: User ID who uploaded the file
        file_name: Original filename
        file_hash: SHA-256 hash of file content (for tamper verification)
        file_size: File size in bytes
        shared_with_nexus: Whether user chose to share with Nexus
        ip_address: User's IP address (for security/blocking)
        university: Optional university name
        course_code: Optional course code

    Returns:
        Upload log record
    """
    try:
        log_data = {
            "user_id": user_id,
            "file_name": file_name,
            "file_hash": file_hash,
            "file_size": file_size,
            "shared_with_nexus": shared_with_nexus,
            "ip_address": ip_address,
            "ai_processed": False,  # Will be updated after processing
            "university": university,
            "course_code": course_code
        }

        response = supabase.table("upload_logs").insert(log_data).execute()
        debug_log(f"[+] Logged upload: {file_name} (hash: {file_hash[:16]}..., nexus: {shared_with_nexus})")
        return response.data[0]

    except Exception as e:
        debug_log(f"[-] Error logging upload: {e}")
        # Non-critical error - don't block upload
        return None


def mark_upload_as_processed(file_hash: str) -> bool:
    """Mark an upload log as AI-processed"""
    try:
        supabase.table("upload_logs").update({
            "ai_processed": True
        }).eq("file_hash", file_hash).execute()

        debug_log(f"[+] Marked upload as processed: {file_hash[:16]}...")
        return True
    except Exception as e:
        debug_log(f"[-] Error marking upload as processed: {e}")
        return False


# ============================================================================
# FOLDER MANAGEMENT
# ============================================================================

def get_user_folders(user_id: str) -> list:
    """Get all folders for a user"""
    try:
        response = supabase.table("folders").select("*").eq("user_id", user_id).order("created_at").execute()
        return response.data
    except Exception as e:
        debug_log(f"[-] Error fetching user folders: {e}")
        return []


def create_folder(user_id: str, name: str, parent_id: str = None, color: str = "#7c9885", position_data: dict = None) -> dict:
    """Create a new folder"""
    try:
        folder_data = {
            "user_id": user_id,
            "name": name,
            "parent_id": parent_id,
            "color": color,
            "position_data": position_data or {}
        }

        response = supabase.table("folders").insert(folder_data).execute()
        debug_log(f"[+] Created folder: {name}")
        return response.data[0]

    except Exception as e:
        debug_log(f"[-] Error creating folder: {e}")
        return None


def update_folder(folder_id: str, user_id: str, updates: dict) -> dict:
    """Update a folder (name, parent_id, color, position_data)"""
    try:
        # Add updated_at timestamp
        updates['updated_at'] = 'NOW()'

        response = supabase.table("folders").update(updates).eq("id", folder_id).eq("user_id", user_id).execute()
        debug_log(f"[+] Updated folder {folder_id}")
        return response.data[0] if response.data else None

    except Exception as e:
        debug_log(f"[-] Error updating folder: {e}")
        return None


def delete_folder(folder_id: str, user_id: str) -> bool:
    """Delete a folder (CASCADE will move children to parent)"""
    try:
        # Supabase CASCADE will automatically handle child folders
        supabase.table("folders").delete().eq("id", folder_id).eq("user_id", user_id).execute()
        debug_log(f"[+] Deleted folder {folder_id}")
        return True

    except Exception as e:
        debug_log(f"[-] Error deleting folder: {e}")
        return False


def log_ai_response(user_id: str, conversation_id: str, prompt_text: str,
                    response_text: str, sources_used: list, model_used: str,
                    response_time_ms: int = None, provenance_signature: str = None,
                    ip_address: str = None) -> dict:
    """
    Log an AI response to ai_response_logs table (Missouri SB 1324 compliance - 7-year retention).

    Args:
        user_id: User who triggered the AI response
        conversation_id: Conversation context
        prompt_text: The student's question/prompt
        response_text: The full AI response (used for hash + length, not stored in full)
        sources_used: List of source dicts [{note_id, filename, similarity, username, source_type}]
        model_used: AI model identifier
        response_time_ms: How long generation took in milliseconds
        provenance_signature: Zero-width encoded signature embedded in response
        ip_address: User's IP address

    Returns:
        Log record or None on error
    """
    import hashlib

    try:
        response_hash = hashlib.sha256(response_text.encode('utf-8')).hexdigest()

        log_data = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "prompt_text": prompt_text,
            "prompt_length": len(prompt_text),
            "response_length": len(response_text),
            "response_hash": response_hash,
            "sources_used": sources_used or [],
            "model_used": model_used,
            "response_time_ms": response_time_ms,
            "provenance_signature": provenance_signature,
            "ip_address": ip_address
        }

        response = supabase.table("ai_response_logs").insert(log_data).execute()
        debug_log(f"[+] Logged AI response: conv={conversation_id}, hash={response_hash[:16]}..., {len(response_text)} chars")
        return response.data[0] if response.data else None

    except Exception as e:
        debug_log(f"[-] Error logging AI response: {e}")
        # Non-critical - don't block the chat response
        return None


def update_note_folder(note_id: str, user_id: str, folder_id: str = None) -> bool:
    """Assign a note to a folder (or remove from folder if folder_id is None)"""
    try:
        supabase.table("notes").update({
            "folder_id": folder_id
        }).eq("id", note_id).eq("user_id", user_id).execute()

        debug_log(f"[+] Moved note {note_id} to folder {folder_id}")
        return True

    except Exception as e:
        debug_log(f"[-] Error updating note folder: {e}")
        return False


# ============================================================================
# AGE VERIFICATION (Missouri SB 1455 / GUARD Act)
# ============================================================================

def update_age_verification(user_id: str, verified: bool, method: str,
                            legal_name: str = None, zip_code: str = None,
                            birthdate: str = None) -> bool:
    """Update user's age verification status"""
    try:
        from datetime import datetime, timezone

        update_data = {
            "age_verified": verified,
            "age_verification_method": method
        }

        if verified:
            now = datetime.now(timezone.utc).isoformat()
            update_data["age_verified_at"] = now
            update_data["last_verified_at"] = now
            update_data["account_frozen"] = False
            update_data["frozen_at"] = None
            update_data["frozen_reason"] = None

        if legal_name:
            update_data["legal_name"] = legal_name
        if zip_code:
            update_data["zip_code"] = zip_code
        if birthdate:
            update_data["birthdate"] = birthdate

        supabase.table("user_profiles").update(update_data).eq("id", user_id).execute()
        debug_log(f"[+] Age verification updated for {user_id}: verified={verified}, method={method}")
        return True

    except Exception as e:
        debug_log(f"[-] Error updating age verification: {e}")
        return False


def freeze_account(user_id: str, reason: str) -> bool:
    """Freeze a user account (GUARD Act compliance)"""
    try:
        from datetime import datetime, timezone

        supabase.table("user_profiles").update({
            "account_frozen": True,
            "frozen_at": datetime.now(timezone.utc).isoformat(),
            "frozen_reason": reason
        }).eq("id", user_id).execute()

        debug_log(f"[+] Account frozen: {user_id} (reason: {reason})")
        return True

    except Exception as e:
        debug_log(f"[-] Error freezing account: {e}")
        return False


def unfreeze_account(user_id: str) -> bool:
    """Unfreeze a user account after successful verification"""
    try:
        supabase.table("user_profiles").update({
            "account_frozen": False,
            "frozen_at": None,
            "frozen_reason": None
        }).eq("id", user_id).execute()

        debug_log(f"[+] Account unfrozen: {user_id}")
        return True

    except Exception as e:
        debug_log(f"[-] Error unfreezing account: {e}")
        return False


def get_verification_status(user_id: str) -> dict:
    """Get user's age verification and account freeze status"""
    try:
        response = supabase.table("user_profiles").select(
            "age_verified, age_verified_at, age_verification_method, "
            "last_verified_at, account_frozen, frozen_at, frozen_reason"
        ).eq("id", user_id).single().execute()

        return response.data if response.data else None

    except Exception as e:
        debug_log(f"[-] Error getting verification status: {e}")
        return None
