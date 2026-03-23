# Note Browsing Feature - Implementation Guide

## ✅ COMPLETED (Ready to Deploy)

### 1. Database Schema
**File:** `supabase_migrations/2026_03_22_note_browsing_and_downloads.sql`

**What it does:**
- Adds `.edu_email_verified` field to user_profiles
- Adds `topic_tags` array to notes
- Creates `download_transactions` table for DMCA compliance
- Creates `note_views` table for analytics
- Creates `dmca_takedown_requests` table
- Helper functions for download limits and transaction IDs

**To deploy:**
1. Go to https://supabase.com/dashboard/project/mxddgbpxjoltaimftpmn/sql/new
2. Copy the SQL from the migration file
3. Run it in Supabase SQL Editor

### 2. DMCA Compliance Page
**File:** `studyflowsuitewebsite/dmca.html`

**Features:**
- DMCA Safe Harbor information
- Designated Agent contact info
- Takedown request form
- Federal law warnings (DMCA § 1202)
- Student upload protections

**Status:** Complete, ready to push to website

### 3. Terms of Service Update
**File:** `studyflowsuitewebsite/terms.html`

**Changes:**
- Added Section 12: "DMCA Compliance and Watermark Protection"
- Federal law warning about watermark removal ($25,000 penalties)
- Watermark requirements
- Copyright infringement process
- Counter-notification process

**Status:** Complete, ready to push to website

### 4. Browse Interface
**File:** `studyflowsuitewebsite/browse.html`

**Features:**
- .edu verification gate (restricts access to verified students only)
- Keyword search box
- University and Course filters
- Topic tag filtering
- Sort by: Recent, Popular, Most Viewed
- Note cards showing: title, university, course, username, tags, stats
- Click to view note

**Status:** Complete, needs backend API to function

---

## 🔨 IN PROGRESS / NEEDS COMPLETION

### 5. Backend API Endpoints
**File:** `StudyFlow/backend/app.py` (needs additions)

**Required endpoints:**

```python
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
        "notes": [
            {
                "id": "uuid",
                "filename": "Biology_Chapter_3.pdf",
                "university": "Missouri State University",
                "course_code": "BIO 121",
                "username": "BiologyBear",
                "topic_tags": ["Biology", "Cell Division"],
                "view_count": 42,
                "usage_count": 15,
                "page_count": 12,
                "created_at": "2026-03-15T10:30:00Z"
            }
        ]
    }
    """
    # 1. Check if user has edu_email_verified = TRUE
    # 2. Query notes table where is_public = TRUE
    # 3. Apply filters
    # 4. Return results


@app.route("/api/notes/topic-tags", methods=["GET"])
@supabase_auth_required
def get_topic_tags():
    """
    Get all unique topic tags from public notes

    Returns:
    {
        "tags": ["Biology", "Chemistry", "Physics", "Calculus", ...]
    }
    """
    # Query all public notes and extract unique tags


@app.route("/api/dmca/takedown", methods=["POST"])
def submit_takedown_request():
    """
    Submit a DMCA takedown request

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
    # 1. Generate unique request_id
    # 2. Insert into dmca_takedown_requests table
    # 3. Send confirmation email
    # 4. Alert admin


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
    # Insert into note_views table


@app.route("/api/notes/<note_id>/download", methods=["POST"])
@supabase_auth_required
def download_note_with_watermark(note_id):
    """
    Download a note with watermark (premium feature with guardrails)

    Body:
    {
        "purpose": "I am downloading this for personal study only"
    }

    Returns:
    - Watermarked PDF file

    Checks:
    1. User has verified .edu email
    2. User has uploaded at least 5 notes
    3. User hasn't exceeded 3 downloads/day
    4. Note exists and is public

    Then:
    1. Generate unique transaction_id
    2. Add watermark with: username, transaction_id, StudyFlow branding
    3. Record download in download_transactions table
    4. Return watermarked file
    """
```

**Implementation priority:**
1. `/api/notes/browse` - Critical for browse.html to work
2. `/api/notes/topic-tags` - Critical for tag filtering
3. `/api/dmca/takedown` - Required for legal compliance
4. `/api/notes/<note_id>/view` - Nice to have (analytics)
5. `/api/notes/<note_id>/download` - Premium feature (can be added later)

### 6. Note Viewer
**File:** `studyflowsuitewebsite/note-viewer.html` (needs creation)

**Features:**
- Watermark overlay showing: username, transaction ID, "For Reference Only"
- Read-only view (disable copy-paste with CSS)
- Download button (triggers purpose pop-up)
- Source attribution (@username, university, course)
- Report button (link to DMCA page)

**Implementation:**
```html
<!-- Watermark overlay -->
<div class="watermark-overlay">
  <div class="watermark-diagonal">
    StudyFlow Suite - For Reference Only
    <br>
    Source: @BiologyBear - ID: #99281
    <br>
    Not for Submission
  </div>
</div>

<!-- CSS to disable text selection -->
<style>
.note-content {
  user-select: none;
  -webkit-user-select: none;
  -moz-user-select: none;
  -ms-user-select: none;
}
</style>
```

### 7. .edu Email Verification
**File:** `studyflowsuitewebsite/settings.html` (needs creation or update)

**Flow:**
1. User enters .edu email address
2. Backend sends verification email with 6-digit code
3. User enters code
4. Backend sets `edu_email_verified = TRUE`
5. User can now browse notes

**Backend endpoint needed:**
```python
@app.route("/api/auth/send-edu-verification", methods=["POST"])
@supabase_auth_required
def send_edu_verification():
    """
    Send verification code to .edu email

    Body:
    {
        "edu_email": "student@university.edu"
    }
    """
    # 1. Validate email ends with .edu
    # 2. Generate 6-digit code
    # 3. Store code in database (expires in 15 minutes)
    # 4. Send email via SendGrid


@app.route("/api/auth/verify-edu-code", methods=["POST"])
@supabase_auth_required
def verify_edu_code():
    """
    Verify the 6-digit code

    Body:
    {
        "code": "123456"
    }
    """
    # 1. Check code matches
    # 2. Set edu_email_verified = TRUE
    # 3. Return success
```

### 8. PII Scrubbing Pipeline
**File:** `StudyFlow/backend/pii_scrubber.py` (needs creation)

**Uses Gemini 3.1 Flash-Lite to detect:**
- Phone numbers (redact)
- Social security numbers (redact)
- Physical addresses (redact)
- Email addresses (evaluate - keep if .edu, redact personal)
- Names (keep - they're the authors)

**Integration point:**
- Add to `process_note_async()` in `tasks.py`
- Run before chunking and embedding
- Store original (private) and scrubbed (public) versions

### 9. Footer Links
**Files:** All HTML pages

**Add to footer:**
```html
<footer>
  <div class="footer-links">
    <a href="terms.html">Terms</a>
    <a href="privacy.html">Privacy</a>
    <a href="dmca.html">DMCA / Copyright</a>
    <a href="guidelines.html">Community Guidelines</a>
  </div>
</footer>
```

---

## 📊 DEPLOYMENT CHECKLIST

### Frontend (Website)
- [ ] Run database migration in Supabase
- [ ] Push dmca.html to website
- [ ] Push updated terms.html to website
- [ ] Push browse.html to website
- [ ] Create note-viewer.html
- [ ] Create/update settings.html for .edu verification
- [ ] Add footer links to all pages

### Backend (Render)
- [ ] Add `/api/notes/browse` endpoint
- [ ] Add `/api/notes/topic-tags` endpoint
- [ ] Add `/api/dmca/takedown` endpoint
- [ ] Add `/api/notes/<note_id>/view` endpoint
- [ ] Add `/api/auth/send-edu-verification` endpoint
- [ ] Add `/api/auth/verify-edu-code` endpoint
- [ ] Add `/api/notes/<note_id>/download` endpoint (premium)
- [ ] Create `pii_scrubber.py` module
- [ ] Integrate PII scrubbing into upload pipeline
- [ ] Push to GitHub (triggers Render deployment)

### Legal Compliance
- [ ] Register Designated DMCA Agent with U.S. Copyright Office ($6 fee)
- [ ] Update actual contact info in dmca.html
- [ ] Set up `dmca@studyflowsuite.com` email address
- [ ] Create internal DMCA response procedure document

### Testing
- [ ] Test .edu verification flow
- [ ] Test note browsing with filters
- [ ] Test note viewer
- [ ] Test download limits (3/day, 5 uploads required)
- [ ] Test DMCA takedown form submission
- [ ] Test watermark generation
- [ ] Verify PII scrubbing works correctly

---

## 🎯 NEXT STEPS (Recommended Order)

1. **Run database migration** (5 minutes)
   - Adds all necessary tables and fields

2. **Create backend API endpoints** (2-3 hours)
   - Start with `/api/notes/browse` and `/api/notes/topic-tags`
   - These are required for browse.html to work

3. **Push frontend files** (15 minutes)
   - dmca.html, terms.html, browse.html to website

4. **Test browsing** (30 minutes)
   - Verify browse page loads
   - Test search and filters
   - Fix any bugs

5. **Add .edu verification** (1-2 hours)
   - Create settings page
   - Add backend endpoints
   - Test email sending

6. **Create note viewer** (1-2 hours)
   - Build note-viewer.html
   - Add watermark overlay
   - Connect to backend

7. **Implement downloads** (2-3 hours)
   - Add download endpoint
   - Generate watermarked PDFs
   - Test guardrails

8. **Add PII scrubbing** (2-3 hours)
   - Create pii_scrubber.py
   - Integrate into upload pipeline
   - Test with sample notes

9. **Legal registration** (1 hour)
   - Register DMCA agent
   - Set up email
   - Update contact info

---

## 💡 TIPS FOR COMPLETION

**Use this migration first:**
The database migration is the foundation. Everything else depends on it.

**Test incrementally:**
After adding each endpoint, test it immediately with Postman or the frontend.

**Start simple:**
Get basic browsing working first. Add premium features (downloads, watermarks) later.

**Legal compliance is critical:**
The DMCA registration and proper attribution are what protect you legally. Don't skip these steps.

**User experience matters:**
The .edu gate makes this defensible as an "educational sandbox" rather than a public note-sharing site.

---

## 📝 CODE SNIPPETS

### Example: /api/notes/browse endpoint

```python
@app.route("/api/notes/browse", methods=["GET"])
@supabase_auth_required
def browse_notes():
    try:
        from StudyFlow.backend.supabase_client import supabase

        user_id = request.user_id

        # Check .edu verification
        profile = supabase.table("user_profiles").select("edu_email_verified").eq("id", user_id).single().execute()

        if not profile.data or not profile.data.get('edu_email_verified'):
            return jsonify({"error": "Requires .edu email verification"}), 403

        # Get query parameters
        university = request.args.get('university')
        course_code = request.args.get('course_code')
        topic_tags = request.args.get('topic_tags', '').split(',') if request.args.get('topic_tags') else []
        sort_by = request.args.get('sort', 'recent')
        limit = int(request.args.get('limit', 50))

        # Build query
        query = supabase.table("notes").select(
            "id, original_filename, university, course_code, username, topic_tags, page_count, created_at"
        ).eq("is_public", True)

        if university:
            query = query.eq("university", university)
        if course_code:
            query = query.eq("course_code", course_code)

        # Execute query
        response = query.order("created_at", desc=True).limit(limit).execute()
        notes = response.data if response.data else []

        # Get view counts and usage counts
        for note in notes:
            # Get view count
            view_count = supabase.table("note_views").select("id", count="exact").eq("note_id", note['id']).execute()
            note['view_count'] = view_count.count if view_count.count else 0

            # Get usage count (from conversation sources)
            usage_count = supabase.table("conversation_messages").select("id", count="exact").contains("sources", [{"note_id": note['id']}]).execute()
            note['usage_count'] = usage_count.count if usage_count.count else 0

        # Filter by tags if specified
        if topic_tags and topic_tags[0]:  # Check if first element is not empty
            notes = [n for n in notes if n.get('topic_tags') and any(tag in n['topic_tags'] for tag in topic_tags)]

        # Sort
        if sort_by == 'popular':
            notes.sort(key=lambda x: x.get('usage_count', 0), reverse=True)
        elif sort_by == 'views':
            notes.sort(key=lambda x: x.get('view_count', 0), reverse=True)

        return jsonify({"notes": notes}), 200

    except Exception as e:
        debug_log(f"❌ Browse notes error: {e}\\n{traceback.format_exc()}")
        return jsonify({"error": str(e)}), 500
```

This guide provides everything needed to complete the note browsing feature!
