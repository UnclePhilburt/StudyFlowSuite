-- Sticky notes on the canvas (per folder or home level)
CREATE TABLE IF NOT EXISTS canvas_sticky_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    folder_id UUID REFERENCES chat_folders(id) ON DELETE CASCADE,
    content TEXT DEFAULT '',
    position_x FLOAT DEFAULT 0,
    position_y FLOAT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sticky_user ON canvas_sticky_notes(user_id, folder_id);

ALTER TABLE canvas_sticky_notes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage own sticky notes" ON canvas_sticky_notes
    FOR ALL USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);
