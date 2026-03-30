-- Add pre-computed view and download count columns to notes table
-- Updated by Celery task every 30 minutes, avoiding count queries on every browse request

ALTER TABLE notes ADD COLUMN IF NOT EXISTS view_count INTEGER DEFAULT 0;
ALTER TABLE notes ADD COLUMN IF NOT EXISTS download_count INTEGER DEFAULT 0;
