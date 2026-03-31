-- Add reactions column to study group messages
ALTER TABLE study_group_messages ADD COLUMN IF NOT EXISTS reactions JSONB DEFAULT '{}';
