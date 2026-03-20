-- StudyFlow Supabase Database Schema
-- Run this in Supabase SQL Editor

-- Enable pgvector extension (if not already enabled)
CREATE EXTENSION IF NOT EXISTS vector;

-- Users table (managed by Supabase Auth, but we add custom fields)
CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT UNIQUE NOT NULL,
    full_name TEXT,
    subscription_tier TEXT DEFAULT 'free' CHECK (subscription_tier IN ('free', 'pro', 'enterprise')),
    stripe_customer_id TEXT,
    pages_uploaded_this_month INTEGER DEFAULT 0,
    month_reset_date TIMESTAMP DEFAULT NOW(),
    collective_brain_opt_in BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Notes metadata table
CREATE TABLE IF NOT EXISTS notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(id) ON DELETE CASCADE,
    original_filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    file_size INTEGER,
    file_path TEXT, -- Path in Supabase Storage
    page_count INTEGER DEFAULT 1,
    uploaded_at TIMESTAMP DEFAULT NOW(),
    processed BOOLEAN DEFAULT FALSE,
    is_public BOOLEAN DEFAULT FALSE,

    -- Course metadata
    university TEXT,
    course_code TEXT,
    professor TEXT,
    semester TEXT,

    -- Create index for faster lookups
    CONSTRAINT notes_user_id_idx UNIQUE (user_id, id)
);

-- Note chunks table (for RAG)
CREATE TABLE IF NOT EXISTS note_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    note_id UUID REFERENCES notes(id) ON DELETE CASCADE,
    user_id UUID REFERENCES user_profiles(id) ON DELETE CASCADE,

    -- Content
    chunk_text TEXT NOT NULL,
    content_summary TEXT, -- AI-anonymized version for Collective Brain
    chunk_index INTEGER NOT NULL, -- Position in original document

    -- Course metadata (denormalized for faster search)
    university TEXT,
    course_code TEXT,
    professor TEXT,

    -- Vector embedding
    embedding VECTOR(1536), -- OpenAI text-embedding-3-small dimension

    -- Privacy
    is_public BOOLEAN DEFAULT FALSE,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    anonymized_at TIMESTAMP
);

-- Create indexes for fast vector search
CREATE INDEX IF NOT EXISTS note_chunks_embedding_idx ON note_chunks
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Index for course-specific searches
CREATE INDEX IF NOT EXISTS note_chunks_course_idx ON note_chunks
(university, course_code, is_public);

-- Index for user's own notes
CREATE INDEX IF NOT EXISTS note_chunks_user_idx ON note_chunks (user_id);

-- Function to search notes with vector similarity
CREATE OR REPLACE FUNCTION search_notes_with_vector(
    query_embedding VECTOR(1536),
    search_user_id UUID,
    search_university TEXT DEFAULT NULL,
    search_course_code TEXT DEFAULT NULL,
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    note_id UUID,
    chunk_text TEXT,
    content_summary TEXT,
    similarity FLOAT,
    university TEXT,
    course_code TEXT,
    is_own_note BOOLEAN
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        nc.id,
        nc.note_id,
        nc.chunk_text,
        nc.content_summary,
        1 - (nc.embedding <=> query_embedding) AS similarity,
        nc.university,
        nc.course_code,
        (nc.user_id = search_user_id) AS is_own_note
    FROM note_chunks nc
    WHERE
        -- User's own notes OR public notes from same course
        (nc.user_id = search_user_id OR
         (nc.is_public = TRUE AND
          nc.university = search_university AND
          nc.course_code = search_course_code))
        AND 1 - (nc.embedding <=> query_embedding) > match_threshold
    ORDER BY nc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- Function to reset monthly page count (run via cron job)
CREATE OR REPLACE FUNCTION reset_monthly_page_limits()
RETURNS void
LANGUAGE plpgsql
AS $$
BEGIN
    UPDATE user_profiles
    SET
        pages_uploaded_this_month = 0,
        month_reset_date = NOW()
    WHERE month_reset_date < NOW() - INTERVAL '30 days';
END;
$$;

-- Row Level Security (RLS) Policies

-- Users can only see/update their own profile
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own profile" ON user_profiles;
CREATE POLICY "Users can view own profile" ON user_profiles
    FOR SELECT USING (auth.uid() = id);

DROP POLICY IF EXISTS "Users can update own profile" ON user_profiles;
CREATE POLICY "Users can update own profile" ON user_profiles
    FOR UPDATE USING (auth.uid() = id);

-- Users can see their own notes + public notes
ALTER TABLE notes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own notes" ON notes;
CREATE POLICY "Users can view own notes" ON notes
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own notes" ON notes;
CREATE POLICY "Users can insert own notes" ON notes
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own notes" ON notes;
CREATE POLICY "Users can update own notes" ON notes
    FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own notes" ON notes;
CREATE POLICY "Users can delete own notes" ON notes
    FOR DELETE USING (auth.uid() = user_id);

-- Chunks: users can see their own + public from same course
ALTER TABLE note_chunks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can view own chunks" ON note_chunks;
CREATE POLICY "Users can view own chunks" ON note_chunks
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can view public chunks" ON note_chunks;
CREATE POLICY "Users can view public chunks" ON note_chunks
    FOR SELECT USING (is_public = TRUE);

DROP POLICY IF EXISTS "Users can insert own chunks" ON note_chunks;
CREATE POLICY "Users can insert own chunks" ON note_chunks
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Storage bucket policy (note-files)
-- Run this in Supabase Storage UI:
-- Bucket: note-files
-- Public: NO
-- File size limit: 50MB
-- Allowed MIME types: application/pdf, image/jpeg, image/png, text/plain, application/msword, application/vnd.openxmlformats-officedocument.wordprocessingml.document

-- Migration: Enable Collective Brain for all existing users
-- This allows students to share notes with each other automatically
UPDATE user_profiles SET collective_brain_opt_in = TRUE WHERE collective_brain_opt_in = FALSE;
