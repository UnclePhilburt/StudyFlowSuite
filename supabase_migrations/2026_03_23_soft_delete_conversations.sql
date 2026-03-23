-- Soft-delete for conversations (Missouri SB 1324 -- 7-year retention)
-- Instead of deleting conversations, mark them with a timestamp.
-- Messages are retained via the conversation_messages table.

ALTER TABLE conversations ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ DEFAULT NULL;

CREATE INDEX IF NOT EXISTS idx_conversations_deleted_at ON conversations(deleted_at);
