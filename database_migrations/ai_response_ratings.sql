-- AI Response Ratings Table
-- Stores user votes on the helpfulness of sources cited in AI chat responses

CREATE TABLE IF NOT EXISTS ai_response_ratings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id TEXT NOT NULL,  -- Unique message identifier (not a UUID)
    conversation_id UUID NOT NULL,  -- Links to conversations table
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    vote SMALLINT NOT NULL CHECK (vote IN (-1, 1)),  -- -1 = downvote, 1 = upvote
    cited_note_ids UUID[] NOT NULL DEFAULT '{}',  -- Array of note IDs that were cited
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Ensure user can only vote once per message
    UNIQUE(message_id, user_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_ai_response_ratings_message_id ON ai_response_ratings(message_id);
CREATE INDEX IF NOT EXISTS idx_ai_response_ratings_user_id ON ai_response_ratings(user_id);
CREATE INDEX IF NOT EXISTS idx_ai_response_ratings_cited_note_ids ON ai_response_ratings USING GIN(cited_note_ids);

-- RLS Policies
ALTER TABLE ai_response_ratings ENABLE ROW LEVEL SECURITY;

-- Users can read all ratings (for aggregation)
CREATE POLICY "Users can read all ratings" ON ai_response_ratings
    FOR SELECT
    USING (true);

-- Users can only insert/update their own ratings
CREATE POLICY "Users can manage own ratings" ON ai_response_ratings
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Trigger to auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_ai_response_ratings_updated_at BEFORE UPDATE
    ON ai_response_ratings FOR EACH ROW
    EXECUTE PROCEDURE update_updated_at_column();

-- Comments
COMMENT ON TABLE ai_response_ratings IS 'User votes on helpfulness of AI response sources';
COMMENT ON COLUMN ai_response_ratings.vote IS '-1 for downvote (not helpful), 1 for upvote (helpful)';
COMMENT ON COLUMN ai_response_ratings.cited_note_ids IS 'Array of note UUIDs that were cited in this response';
