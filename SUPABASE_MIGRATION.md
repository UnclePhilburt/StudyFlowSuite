# StudyFlow Supabase Migration - Progress Report

## ✅ COMPLETED (Backend Infrastructure)

### 1. Database Schema (Supabase)
- **File**: `supabase_schema.sql`
- Created `user_profiles`, `notes`, and `note_chunks` tables
- Added pgvector extension for semantic search
- Created vector similarity search function
- Implemented Row Level Security (RLS) policies
- **Status**: ✅ Deployed to Supabase

### 2. Dependencies
- **File**: `requirements.txt`
- Added `supabase>=2.0.0`
- Added `pgvector`
- **Status**: ✅ Ready for Render deployment

### 3. Core Backend Files Created

#### `StudyFlow/backend/supabase_client.py`
- Supabase initialization
- Helper functions for all database operations
- User profile management
- Page limit checking (50 pages/month for free tier)
- File upload to Supabase Storage
- Vector search integration

#### `StudyFlow/backend/text_chunking.py`
- 500-word chunks with 50-word overlap
- Smart chunking (respects paragraph boundaries)
- Word count estimation

#### `StudyFlow/backend/embedding_client.py`
- OpenAI text-embedding-3-small integration
- Batch embedding generation (efficient)
- Cost estimation ($0.02 per 1M tokens)
- Cosine similarity calculation

#### `StudyFlow/backend/tasks.py` (Updated)
- New Celery task: `process_note_async`
- Background processing: chunking → embedding → anonymization
- Gemini-based anonymization for Collective Brain
- Automatically marks notes public if user opted in

### 4. API Endpoints (Updated)

#### `POST /api/notes/upload`
- ✅ Checks 50-page/month limit before upload
- ✅ Accepts course metadata (university, course_code, professor, semester)
- ✅ Uploads file to Supabase Storage
- ✅ Extracts text (PDF/Image/TXT)
- ✅ Creates note record in Supabase
- ✅ Triggers background processing (chunking, embeddings, anonymization)
- ✅ Increments user's monthly page count

#### `POST /api/notes/search`
- ✅ Generates embedding for user's question
- ✅ Performs pgvector similarity search
- ✅ Returns user's own notes + Collective Brain (public notes from same course)
- ✅ Generates study hints (not direct answers)
- ✅ Shows similarity scores

#### `GET /api/notes/list`
- ✅ Uses Supabase client
- ✅ Returns processing status, course metadata

#### `DELETE /api/notes/<note_id>`
- ✅ Uses Supabase client
- ✅ Cascades to delete chunks automatically

---

## 🚧 TODO - Next Steps

### 1. Migration Script (CRITICAL)
**File to create**: `migration_script.py`

Move existing data from Render PostgreSQL to Supabase:
- Migrate `users` table → Supabase Auth + `user_profiles`
- Migrate `notes` table (if any exist)
- Preserve user IDs and relationships

**Command to run** (after creating):
```bash
python migration_script.py
```

### 2. Add Course Metadata Forms

#### Website Upload Page
**File**: `C:\Users\CodyW\OneDrive\Documents\studyflowsuitewebsite\upload.html`

Add form fields:
- University (text input)
- Course Code (text input, e.g., "BIO 101")
- Professor (text input, optional)
- Semester (text input, e.g., "Fall 2024", optional)

#### Browser Extension (if applicable)
**File**: `browser-extension/popup-tutor.html`

Add same fields to note upload interface.

### 3. Supabase Auth Integration
Replace custom JWT system with Supabase Auth:

#### Backend Changes:
- Replace `@token_required` decorator with Supabase Auth verification
- Update login/register endpoints to use `supabase.auth.sign_up()` and `supabase.auth.sign_in_with_password()`
- Remove bcrypt/pyjwt dependencies

#### Frontend Changes:
- Update login flow to use Supabase Auth
- Store Supabase session token instead of custom JWT

---

## 🎯 Deployment Checklist

### Before Pushing to GitHub/Render:

1. ✅ Supabase environment variables added to Render:
   - `SUPABASE_URL`
   - `SUPABASE_ANON_KEY`
   - `SUPABASE_SERVICE_KEY`

2. ⚠️ **CRITICAL**: Keep existing environment variables:
   - `DATABASE_URL` (needed temporarily for migration)
   - `OPENAI_API_KEY`
   - `GEMINI_API_KEY`
   - `STRIPE_SECRET_KEY`
   - `SENDGRID_API_KEY`
   - All other existing keys

3. 📦 Dependencies will auto-install on Render from `requirements.txt`

4. ⏱️ **Expect 2-3 minute deployment** (new dependencies need to install)

---

## 🧪 Testing Plan

### After Deployment:

1. **Test Upload**:
   ```bash
   curl -X POST https://studyflowsuite.onrender.com/api/notes/upload \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -F "file=@test.pdf" \
     -F "university=Michigan State University" \
     -F "course_code=BIO 101"
   ```

2. **Check Background Processing**:
   - Upload should return immediately with `"processing": true`
   - Check Celery logs to see chunking/embedding progress
   - After ~30 seconds, note should be `"processed": true`

3. **Test Search**:
   ```bash
   curl -X POST https://studyflowsuite.onrender.com/api/notes/search \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"question": "What is photosynthesis?"}'
   ```

4. **Verify Page Limit**:
   - Free user uploads 51st page → should get 403 error with "limit_exceeded: true"

---

## 💰 Cost Analysis

### Current Costs (per 1,000 users):

**Embeddings** (text-embedding-3-small):
- 50 pages/month/user × 500 words/page = 25,000 words/user/month
- 1,000 users = 25M words = ~33M tokens
- Cost: 33M tokens × $0.02 / 1M = **$0.66/month**

**Gemini** (anonymization for Collective Brain):
- Only runs for users who opt-in (assume 30%)
- 300 users × 50 pages = 15,000 pages
- Gemini 2.0 Flash is FREE (for now)

**Supabase**:
- Free tier: 500MB database, 1GB storage, 50GB bandwidth
- Should handle first 100-200 users for FREE
- Pro tier: $25/month (8GB database, unlimited storage*)

**Total estimated cost for 1,000 users**: ~$25-50/month (mostly Supabase)

---

## 🚀 Ready to Deploy?

**Option 1: Deploy Now (Recommended)**
```bash
git add .
git commit -m "Migrate to Supabase with pgvector RAG system"
git push origin main
```

This will deploy the new backend. Old endpoints still work (users/auth), but notes now use Supabase.

**Option 2: Wait for Migration Script**
If you have existing notes in Render PostgreSQL, wait for me to create the migration script first.

---

## Questions?

- **Do you have existing notes/users in production?** → Need migration script
- **Want to test locally first?** → Install: `pip install -r requirements.txt`
- **Ready to deploy?** → Just say "push to GitHub"
