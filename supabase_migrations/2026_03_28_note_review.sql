-- Add reviewed flag to notes for manual quality control
ALTER TABLE notes ADD COLUMN IF NOT EXISTS reviewed BOOLEAN NOT NULL DEFAULT false;
CREATE INDEX IF NOT EXISTS idx_notes_reviewed ON notes(reviewed) WHERE reviewed = false;
