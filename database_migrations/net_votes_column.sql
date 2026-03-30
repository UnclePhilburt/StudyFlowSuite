-- Add net_votes column to notes table for pre-computed vote counts
-- Updated by Celery task when users vote, avoiding expensive aggregation on every search

ALTER TABLE notes ADD COLUMN IF NOT EXISTS net_votes INTEGER DEFAULT 0;

-- Index for sorting by popularity
CREATE INDEX IF NOT EXISTS idx_notes_net_votes ON notes(net_votes DESC);
