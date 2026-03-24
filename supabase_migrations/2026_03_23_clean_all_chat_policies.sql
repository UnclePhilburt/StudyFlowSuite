-- Clean up ALL conversation policies and recreate from scratch
-- This removes duplicate policies that may be causing conflicts
-- Date: 2026-03-23

-- =====================================================
-- Drop ALL existing policies (including duplicates)
-- =====================================================

-- Conversations table - drop ALL policies
DROP POLICY IF EXISTS "Users can view own conversations" ON conversations;
DROP POLICY IF EXISTS "Users can insert own conversations" ON conversations;
DROP POLICY IF EXISTS "Users can create own conversations" ON conversations;
DROP POLICY IF EXISTS "Users can update own conversations" ON conversations;
DROP POLICY IF EXISTS "Users can delete own conversations" ON conversations;

-- Conversation messages table - drop ALL policies
DROP POLICY IF EXISTS "Users can view own conversation messages" ON conversation_messages;
DROP POLICY IF EXISTS "Users can insert own conversation messages" ON conversation_messages;
DROP POLICY IF EXISTS "Users can create messages in own conversations" ON conversation_messages;
DROP POLICY IF EXISTS "Users can update own conversation messages" ON conversation_messages;
DROP POLICY IF EXISTS "Users can delete own conversation messages" ON conversation_messages;
DROP POLICY IF EXISTS "Users can delete messages in own conversations" ON conversation_messages;

-- =====================================================
-- Recreate clean policies
-- =====================================================

-- Conversations: SELECT
CREATE POLICY "Users can view own conversations"
    ON conversations
    FOR SELECT
    USING (auth.uid() = user_id);

-- Conversations: INSERT
CREATE POLICY "Users can insert own conversations"
    ON conversations
    FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Conversations: UPDATE
CREATE POLICY "Users can update own conversations"
    ON conversations
    FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Conversations: DELETE (soft delete via UPDATE)
CREATE POLICY "Users can delete own conversations"
    ON conversations
    FOR UPDATE
    USING (auth.uid() = user_id AND deleted_at IS NULL)
    WITH CHECK (auth.uid() = user_id);

-- Conversation Messages: SELECT
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

-- Conversation Messages: INSERT
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

-- Conversation Messages: UPDATE
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

-- Conversation Messages: DELETE
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
-- Add comments
-- =====================================================

COMMENT ON POLICY "Users can view own conversations" ON conversations IS 'Users can only view their own conversations';
COMMENT ON POLICY "Users can insert own conversations" ON conversations IS 'Users can create new conversations for themselves';
COMMENT ON POLICY "Users can update own conversations" ON conversations IS 'Users can update their own conversations (title, summary)';
COMMENT ON POLICY "Users can delete own conversations" ON conversations IS 'Users can soft-delete their own conversations';

COMMENT ON POLICY "Users can view own conversation messages" ON conversation_messages IS 'Users can view messages from their own conversations';
COMMENT ON POLICY "Users can insert own conversation messages" ON conversation_messages IS 'Users can add messages to their own conversations';
COMMENT ON POLICY "Users can update own conversation messages" ON conversation_messages IS 'Users can edit messages in their own conversations';
COMMENT ON POLICY "Users can delete own conversation messages" ON conversation_messages IS 'Users can delete messages from their own conversations';
