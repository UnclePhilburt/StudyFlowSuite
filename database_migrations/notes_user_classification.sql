-- User-specified classification for notes (note vs photo)
-- Used by the social hybrid classification system: user marks images as notes,
-- Gemini verifies in the background, admin reviews mismatches.
ALTER TABLE notes ADD COLUMN IF NOT EXISTS user_classification TEXT;

-- Username column for image notes (helps admin queue display)
ALTER TABLE notes ADD COLUMN IF NOT EXISTS username TEXT;

-- Index for finding mismatches in admin queue
CREATE INDEX IF NOT EXISTS idx_notes_classification_mismatch
  ON notes(ai_classification)
  WHERE ai_classification LIKE 'personal (mismatch%';
