-- Migration: Syllabus Upload and Calendar Events
-- Allows students to upload syllabi and automatically extract assignments/exams into a calendar

-- =====================================================
-- 1. Create syllabi table to store uploaded course syllabi
-- =====================================================

CREATE TABLE IF NOT EXISTS syllabi (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(id) ON DELETE CASCADE NOT NULL,
    course_name TEXT NOT NULL,
    course_code TEXT,
    professor_name TEXT,
    semester TEXT,
    file_path TEXT NOT NULL,  -- Path in Supabase Storage
    original_filename TEXT NOT NULL,
    extracted_text TEXT,  -- Full text extracted from PDF/DOCX
    file_size INTEGER,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Index for user's syllabi
CREATE INDEX IF NOT EXISTS syllabi_user_idx ON syllabi (user_id);

-- Index for course lookups
CREATE INDEX IF NOT EXISTS syllabi_course_idx ON syllabi (course_code);

COMMENT ON TABLE syllabi IS 'Stores uploaded course syllabi for calendar extraction';


-- =====================================================
-- 2. Create calendar_events table to store assignments, exams, etc.
-- =====================================================

CREATE TABLE IF NOT EXISTS calendar_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(id) ON DELETE CASCADE NOT NULL,
    syllabus_id UUID REFERENCES syllabi(id) ON DELETE CASCADE,  -- NULL if manually added
    event_type TEXT NOT NULL CHECK (event_type IN (
        'assignment', 'exam', 'quiz', 'reading', 'lecture',
        'project', 'presentation', 'discussion', 'lab', 'other'
    )),
    title TEXT NOT NULL,
    description TEXT,
    due_date DATE NOT NULL,
    due_time TIME,  -- Optional specific time
    course_name TEXT,
    course_code TEXT,
    completed BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Index for user's calendar events
CREATE INDEX IF NOT EXISTS calendar_events_user_idx ON calendar_events (user_id);

-- Index for date queries (show upcoming events)
CREATE INDEX IF NOT EXISTS calendar_events_date_idx ON calendar_events (due_date);

-- Index for syllabus events (cascade delete)
CREATE INDEX IF NOT EXISTS calendar_events_syllabus_idx ON calendar_events (syllabus_id);

COMMENT ON TABLE calendar_events IS 'Stores calendar events extracted from syllabi or manually added';


-- =====================================================
-- 3. Enable Row Level Security (RLS)
-- =====================================================

ALTER TABLE syllabi ENABLE ROW LEVEL SECURITY;
ALTER TABLE calendar_events ENABLE ROW LEVEL SECURITY;

-- Users can only view/edit their own syllabi
DROP POLICY IF EXISTS "Users can view own syllabi" ON syllabi;
CREATE POLICY "Users can view own syllabi" ON syllabi
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own syllabi" ON syllabi;
CREATE POLICY "Users can insert own syllabi" ON syllabi
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own syllabi" ON syllabi;
CREATE POLICY "Users can update own syllabi" ON syllabi
    FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own syllabi" ON syllabi;
CREATE POLICY "Users can delete own syllabi" ON syllabi
    FOR DELETE USING (auth.uid() = user_id);

-- Users can only view/edit their own calendar events
DROP POLICY IF EXISTS "Users can view own calendar events" ON calendar_events;
CREATE POLICY "Users can view own calendar events" ON calendar_events
    FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert own calendar events" ON calendar_events;
CREATE POLICY "Users can insert own calendar events" ON calendar_events
    FOR INSERT WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own calendar events" ON calendar_events;
CREATE POLICY "Users can update own calendar events" ON calendar_events
    FOR UPDATE USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own calendar events" ON calendar_events;
CREATE POLICY "Users can delete own calendar events" ON calendar_events
    FOR DELETE USING (auth.uid() = user_id);
