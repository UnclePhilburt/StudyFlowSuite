-- Fix RLS policies for conversations and conversation_messages
-- Allow users to create and manage their own conversations and messages
-- Date: 2026-03-23

-- =====================================================
-- Drop existing policies (if any)
-- =====================================================

DROP POLICY IF EXISTS "Users can view own conversations" ON conversations;
DROP POLICY IF EXISTS "Users can insert own conversations" ON conversations;
DROP POLICY IF EXISTS "Users can update own conversations" ON conversations;
DROP POLICY IF EXISTS "Users can delete own conversations" ON conversations;

DROP POLICY IF EXISTS "Users can view own conversation messages" ON conversation_messages;
DROP POLICY IF EXISTS "Users can insert own conversation messages" ON conversation_messages;
DROP POLICY IF EXISTS "Users can update own conversation messages" ON conversation_messages;
DROP POLICY IF EXISTS "Users can delete own conversation messages" ON conversation_messages;

-- =====================================================
-- Conversations table RLS policies
-- =====================================================

-- Users can view their own conversations
CREATE POLICY "Users can view own conversations"
    ON conversations
    FOR SELECT
    USING (auth.uid() = user_id);

-- Users can insert their own conversations
CREATE POLICY "Users can insert own conversations"
    ON conversations
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Users can update their own conversations
CREATE POLICY "Users can update own conversations"
    ON conversations
    FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Users can soft-delete their own conversations
CREATE POLICY "Users can delete own conversations"
    ON conversations
    FOR UPDATE
    USING (auth.uid() = user_id AND deleted_at IS NULL)
    WITH CHECK (auth.uid() = user_id);

-- =====================================================
-- Conversation messages table RLS policies
-- =====================================================

-- Users can view messages from their own conversations
CREATE POLICY "Users can view own conversation messages"
    ON conversation_messages
    FOR SELECT
    USING (
        EXISTS (
            SELECT 1 FROM conversations
            WHERE conversations.id = conversation_messages.conversation_id
            AND conversations.user_id = auth.uid()
        )
    );

-- Users can insert messages to their own conversations
CREATE POLICY "Users can insert own conversation messages"
    ON conversation_messages
    FOR INSERT
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM conversations
            WHERE conversations.id = conversation_messages.conversation_id
            AND conversations.user_id = auth.uid()
        )
    );

-- Users can update messages in their own conversations
CREATE POLICY "Users can update own conversation messages"
    ON conversation_messages
    FOR UPDATE
    USING (
        EXISTS (
            SELECT 1 FROM conversations
            WHERE conversations.id = conversation_messages.conversation_id
            AND conversations.user_id = auth.uid()
        )
    )
    WITH CHECK (
        EXISTS (
            SELECT 1 FROM conversations
            WHERE conversations.id = conversation_messages.conversation_id
            AND conversations.user_id = auth.uid()
        )
    );

-- Users can delete messages from their own conversations
CREATE POLICY "Users can delete own conversation messages"
    ON conversation_messages
    FOR DELETE
    USING (
        EXISTS (
            SELECT 1 FROM conversations
            WHERE conversations.id = conversation_messages.conversation_id
            AND conversations.user_id = auth.uid()
        )
    );

-- =====================================================
-- Comments for documentation
-- =====================================================

COMMENT ON POLICY "Users can view own conversations" ON conversations IS 'Users can only view their own conversations';
COMMENT ON POLICY "Users can insert own conversations" ON conversations IS 'Users can create new conversations for themselves';
COMMENT ON POLICY "Users can update own conversations" ON conversations IS 'Users can update their own conversations (title, summary)';
COMMENT ON POLICY "Users can delete own conversations" ON conversations IS 'Users can soft-delete their own conversations';

COMMENT ON POLICY "Users can view own conversation messages" ON conversation_messages IS 'Users can view messages from their own conversations';
COMMENT ON POLICY "Users can insert own conversation messages" ON conversation_messages IS 'Users can add messages to their own conversations';
COMMENT ON POLICY "Users can update own conversation messages" ON conversation_messages IS 'Users can edit messages in their own conversations';
COMMENT ON POLICY "Users can delete own conversation messages" ON conversation_messages IS 'Users can delete messages from their own conversations';
