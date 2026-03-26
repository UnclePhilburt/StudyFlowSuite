-- Note favorites system
-- Allows users to bookmark/favorite notes from the Nexus browser

CREATE TABLE note_favorites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, note_id)
);

CREATE INDEX idx_favorites_user ON note_favorites (user_id, created_at DESC);

-- RLS policies
ALTER TABLE note_favorites ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own favorites"
    ON note_favorites FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own favorites"
    ON note_favorites FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can delete own favorites"
    ON note_favorites FOR DELETE
    USING (auth.uid() = user_id);

-- Service role can manage all favorites
CREATE POLICY "Service role can manage favorites"
    ON note_favorites FOR ALL
    WITH CHECK (true);
