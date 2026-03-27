-- Add source column to conversations table
-- Allows distinguishing between chat page conversations and OnlyOffice plugin conversations
-- Plugin conversations are retained for SB 1324 compliance but hidden from the chat list

ALTER TABLE conversations ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'chat';

-- Index for filtering by source
CREATE INDEX IF NOT EXISTS idx_conversations_source ON conversations(source);
