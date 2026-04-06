-- Track Gemini's classification of uploaded notes
ALTER TABLE notes ADD COLUMN IF NOT EXISTS ai_classification TEXT;
