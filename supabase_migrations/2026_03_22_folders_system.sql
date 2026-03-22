-- =====================================================
-- StudyFlow Folders System
-- Move folders from localStorage to database
-- Created: March 22, 2026
-- =====================================================

-- 1. Create folders table
CREATE TABLE IF NOT EXISTS folders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES user_profiles(id) ON DELETE CASCADE NOT NULL,
    name TEXT NOT NULL,
    parent_id UUID REFERENCES folders(id) ON DELETE CASCADE,
    color TEXT DEFAULT '#7c9885',

    -- Free-form mode position (JSON: {x: number, y: number})
    position_data JSONB DEFAULT '{}',

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

-- 2. Add folder_id to notes table
ALTER TABLE notes
ADD COLUMN IF NOT EXISTS folder_id UUID REFERENCES folders(id) ON DELETE SET NULL;

-- 3. Create indexes
CREATE INDEX IF NOT EXISTS idx_folders_user ON folders(user_id);
CREATE INDEX IF NOT EXISTS idx_folders_parent ON folders(parent_id);
CREATE INDEX IF NOT EXISTS idx_notes_folder ON notes(folder_id);

-- 4. Enable RLS on folders table
ALTER TABLE folders ENABLE ROW LEVEL SECURITY;

-- 5. RLS Policies for folders

-- Users can view their own folders
DROP POLICY IF EXISTS "Users can view own folders" ON folders;
CREATE POLICY "Users can view own folders" ON folders
    FOR SELECT USING (auth.uid() = user_id);

-- Users can create their own folders
DROP POLICY IF EXISTS "Users can insert own folders" ON folders;
CREATE POLICY "Users can insert own folders" ON folders
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Users can update their own folders
DROP POLICY IF EXISTS "Users can update own folders" ON folders;
CREATE POLICY "Users can update own folders" ON folders
    FOR UPDATE USING (auth.uid() = user_id);

-- Users can delete their own folders
DROP POLICY IF EXISTS "Users can delete own folders" ON folders;
CREATE POLICY "Users can delete own folders" ON folders
    FOR DELETE USING (auth.uid() = user_id);

-- 6. Service role can do everything (for backend operations)
DROP POLICY IF EXISTS "Service role full access to folders" ON folders;
CREATE POLICY "Service role full access to folders" ON folders
    FOR ALL USING (true);

-- =====================================================
-- Migration Complete
--
-- Next steps:
-- 1. Run this SQL in Supabase SQL Editor
-- 2. Update backend with folder API endpoints
-- 3. Update frontend to use API instead of localStorage
-- =====================================================
