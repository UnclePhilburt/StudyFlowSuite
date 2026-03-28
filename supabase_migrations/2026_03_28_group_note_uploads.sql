-- Add direct file upload columns to study_group_notes
-- Group notes are uploaded directly and don't appear in personal notes or Nexus

ALTER TABLE study_group_notes ALTER COLUMN note_id DROP NOT NULL;
ALTER TABLE study_group_notes DROP CONSTRAINT IF EXISTS study_group_notes_note_id_fkey;

ALTER TABLE study_group_notes ADD COLUMN IF NOT EXISTS filename TEXT;
ALTER TABLE study_group_notes ADD COLUMN IF NOT EXISTS file_path TEXT;
ALTER TABLE study_group_notes ADD COLUMN IF NOT EXISTS file_size BIGINT;
ALTER TABLE study_group_notes ADD COLUMN IF NOT EXISTS file_type TEXT;
