-- Add canvas_layout column to conversations table
-- Stores card positions and parent relationships as JSON
ALTER TABLE conversations ADD COLUMN IF NOT EXISTS canvas_layout JSONB;
