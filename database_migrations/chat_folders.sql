-- Chat folders for canvas navigation
CREATE TABLE IF NOT EXISTS chat_folders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT 'New Folder',
    color TEXT DEFAULT '#7c9885',
    icon TEXT DEFAULT 'folder',
    position_x FLOAT DEFAULT 0,
    position_y FLOAT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_folders_user ON chat_folders(user_id);

-- Add folder_id to conversations
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS folder_id UUID REFERENCES chat_folders(id) ON DELETE SET NULL;

-- RLS
ALTER TABLE chat_folders ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own folders" ON chat_folders
    FOR ALL USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
