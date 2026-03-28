-- Separate table to track reviewed notes (bypasses PostgREST schema cache issues)
CREATE TABLE IF NOT EXISTS reviewed_notes (
    note_id UUID PRIMARY KEY REFERENCES notes(id) ON DELETE CASCADE,
    reviewed_at TIMESTAMPTZ DEFAULT NOW(),
    action TEXT NOT NULL CHECK (action IN ('approved', 'rejected'))
);
