"""
Supabase client for StudyFlow
Handles database, storage, and auth operations
"""

import os
from supabase import create_client, Client
from StudyFlow.logging_utils import debug_log

# Initialize Supabase client
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")

# Debug: Print what we actually got
print(f"🔍 SUPABASE_URL = {SUPABASE_URL}")
print(f"🔍 SUPABASE_SERVICE_KEY = {'[PRESENT]' if SUPABASE_SERVICE_KEY else '[MISSING]'}")
print(f"🔍 All env vars with 'SUPABASE': {[k for k in os.environ.keys() if 'SUPABASE' in k]}")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print(f"❌ ERROR: SUPABASE_URL={SUPABASE_URL}, SERVICE_KEY={'[PRESENT]' if SUPABASE_SERVICE_KEY else '[MISSING]'}")
    raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY environment variables")

# Service role client (for backend operations)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

debug_log(f"✅ Supabase client initialized: {SUPABASE_URL}")


def get_user_profile(user_id: str) -> dict:
    """Get user profile from Supabase"""
    try:
        response = supabase.table("user_profiles").select("*").eq("id", user_id).single().execute()
        return response.data
    except Exception as e:
        debug_log(f"❌ Error fetching user profile: {e}")
        return None


def create_user_profile(user_id: str, email: str, full_name: str = None, collective_brain_opt_in: bool = True) -> dict:
    """Create a new user profile (Collective Brain enabled by default)"""
    try:
        response = supabase.table("user_profiles").insert({
            "id": user_id,
            "email": email,
            "full_name": full_name,
            "collective_brain_opt_in": collective_brain_opt_in,
            "subscription_tier": "free",
            "pages_uploaded_this_month": 0
        }).execute()
        debug_log(f"✅ Created user profile: {email} (Collective Brain: {collective_brain_opt_in})")
        return response.data[0]
    except Exception as e:
        debug_log(f"❌ Error creating user profile: {e}")
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
        debug_log(f"❌ Error checking page limit: {e}")
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

        debug_log(f"✅ Incremented page count for user {user_id}: +{pages} pages (total: {new_count})")
        return True

    except Exception as e:
        debug_log(f"❌ Error incrementing page count: {e}")
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

        debug_log(f"✅ Uploaded file to storage: {file_path}")

        # Generate signed URL (valid for 1 year)
        signed_url = supabase.storage.from_("note-files").create_signed_url(
            path=file_path,
            expires_in=31536000  # 1 year in seconds
        )

        return signed_url['signedURL']

    except Exception as e:
        debug_log(f"❌ Error uploading file to storage: {e}")
        return None


def create_note_record(user_id: str, filename: str, file_type: str, file_size: int,
                       file_path: str, page_count: int, course_metadata: dict = None) -> dict:
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
            "is_public": False
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
        debug_log(f"✅ Created note record: {filename}")
        return response.data[0]

    except Exception as e:
        debug_log(f"❌ Error creating note record: {e}")
        return None


def create_note_chunk(note_id: str, user_id: str, chunk_text: str, chunk_index: int,
                      embedding: list, course_metadata: dict = None, is_public: bool = False) -> dict:
    """Create a note chunk with embedding"""
    try:
        chunk_data = {
            "note_id": note_id,
            "user_id": user_id,
            "chunk_text": chunk_text,
            "chunk_index": chunk_index,
            "embedding": embedding,
            "is_public": is_public
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
        debug_log(f"❌ Error creating note chunk: {e}")
        return None


def mark_note_as_processed(note_id: str) -> bool:
    """Mark a note as fully processed"""
    try:
        supabase.table("notes").update({"processed": True}).eq("id", note_id).execute()
        debug_log(f"✅ Marked note {note_id} as processed")
        return True
    except Exception as e:
        debug_log(f"❌ Error marking note as processed: {e}")
        return False


def make_note_public(note_id: str, user_id: str) -> bool:
    """Make a note and all its chunks public (for Collective Brain)"""
    try:
        # Update note
        supabase.table("notes").update({"is_public": True}).eq("id", note_id).eq("user_id", user_id).execute()

        # Update all chunks
        supabase.table("note_chunks").update({"is_public": True}).eq("note_id", note_id).execute()

        debug_log(f"✅ Made note {note_id} public")
        return True
    except Exception as e:
        debug_log(f"❌ Error making note public: {e}")
        return False


def search_notes_vector(query_embedding: list, user_id: str, university: str = None,
                       course_code: str = None, match_threshold: float = 0.7, match_count: int = 5) -> list:
    """
    Search notes using vector similarity
    Returns chunks from user's own notes + ALL public notes (collective brain)
    University and course_code parameters are ignored - searches all public notes
    """
    try:
        # Call the PostgreSQL function we defined
        response = supabase.rpc("search_notes_with_vector", {
            "query_embedding": query_embedding,
            "search_user_id": user_id,
            "search_university": university,
            "search_course_code": course_code,
            "match_threshold": match_threshold,
            "match_count": match_count
        }).execute()

        debug_log(f"✅ Vector search found {len(response.data)} results")
        return response.data

    except Exception as e:
        debug_log(f"❌ Error searching notes with vector: {e}")
        return []


def get_user_notes(user_id: str) -> list:
    """Get all notes for a user"""
    try:
        response = supabase.table("notes").select("*").eq("user_id", user_id).order("uploaded_at", desc=True).execute()
        return response.data
    except Exception as e:
        debug_log(f"❌ Error fetching user notes: {e}")
        return []


def delete_note(note_id: str, user_id: str) -> bool:
    """Delete a note and all its chunks"""
    try:
        # Supabase CASCADE will automatically delete chunks
        supabase.table("notes").delete().eq("id", note_id).eq("user_id", user_id).execute()
        debug_log(f"✅ Deleted note {note_id}")
        return True
    except Exception as e:
        debug_log(f"❌ Error deleting note: {e}")
        return False
