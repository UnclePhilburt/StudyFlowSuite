-- Shared note links with optional expiry
CREATE TABLE IF NOT EXISTS shared_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    share_token TEXT UNIQUE NOT NULL,
    expires_at TIMESTAMPTZ,  -- NULL means no expiry
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_shared_notes_token ON shared_notes(share_token);
CREATE INDEX IF NOT EXISTS idx_shared_notes_user ON shared_notes(user_id);
CREATE INDEX IF NOT EXISTS idx_shared_notes_note ON shared_notes(note_id);
