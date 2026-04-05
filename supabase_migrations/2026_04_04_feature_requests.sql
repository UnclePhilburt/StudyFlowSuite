-- Feature Request System for StudyFlow Suite
-- Allows users to submit, vote on, and track feature requests
-- Admin can update status and manage requests

-- Main feature requests table
CREATE TABLE feature_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    username TEXT,  -- Cached for display (from users table)
    title TEXT NOT NULL CHECK (char_length(title) >= 5 AND char_length(title) <= 200),
    description TEXT NOT NULL CHECK (char_length(description) >= 10 AND char_length(description) <= 2000),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'reviewing', 'in-progress', 'completed', 'rejected')),
    vote_count INTEGER DEFAULT 0,
    admin_response TEXT,  -- Optional admin comment
    completed_at TIMESTAMPTZ,  -- When status changed to 'completed'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Votes tracking table (one vote per user per request)
CREATE TABLE feature_request_votes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    request_id UUID NOT NULL REFERENCES feature_requests(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, request_id)  -- Prevent duplicate votes
);

-- Indexes for performance
CREATE INDEX idx_requests_status ON feature_requests (status, created_at DESC);
CREATE INDEX idx_requests_votes ON feature_requests (vote_count DESC, created_at DESC);
CREATE INDEX idx_requests_user ON feature_requests (user_id, created_at DESC);
CREATE INDEX idx_votes_request ON feature_request_votes (request_id);
CREATE INDEX idx_votes_user ON feature_request_votes (user_id);

-- Trigger to update vote_count when votes are added/removed
CREATE OR REPLACE FUNCTION update_request_vote_count()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        UPDATE feature_requests
        SET vote_count = vote_count + 1, updated_at = NOW()
        WHERE id = NEW.request_id;
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        UPDATE feature_requests
        SET vote_count = vote_count - 1, updated_at = NOW()
        WHERE id = OLD.request_id;
        RETURN OLD;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_vote_count
    AFTER INSERT OR DELETE ON feature_request_votes
    FOR EACH ROW
    EXECUTE FUNCTION update_request_vote_count();

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_feature_request_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    IF NEW.status = 'completed' AND OLD.status != 'completed' THEN
        NEW.completed_at = NOW();
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_request_timestamp
    BEFORE UPDATE ON feature_requests
    FOR EACH ROW
    EXECUTE FUNCTION update_feature_request_timestamp();

-- Row Level Security (RLS) policies
ALTER TABLE feature_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE feature_request_votes ENABLE ROW LEVEL SECURITY;

-- Anyone authenticated can view all feature requests
CREATE POLICY "Authenticated users can view feature requests"
    ON feature_requests FOR SELECT
    USING (auth.role() = 'authenticated');

-- Users can create their own feature requests
CREATE POLICY "Users can create feature requests"
    ON feature_requests FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Users can update their own requests (only title/description, not status)
CREATE POLICY "Users can update own requests"
    ON feature_requests FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (
        auth.uid() = user_id
        AND status = OLD.status  -- Cannot change status
        AND admin_response = OLD.admin_response  -- Cannot change admin response
    );

-- Service role (backend/admin) can update any request
CREATE POLICY "Service role can update any request"
    ON feature_requests FOR UPDATE
    USING (true)  -- Service role bypasses RLS but this makes it explicit
    WITH CHECK (true);

-- Anyone authenticated can view votes
CREATE POLICY "Authenticated users can view votes"
    ON feature_request_votes FOR SELECT
    USING (auth.role() = 'authenticated');

-- Users can add their own votes
CREATE POLICY "Users can add votes"
    ON feature_request_votes FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Users can remove their own votes
CREATE POLICY "Users can remove own votes"
    ON feature_request_votes FOR DELETE
    USING (auth.uid() = user_id);

-- Service role can manage all votes
CREATE POLICY "Service role can manage votes"
    ON feature_request_votes FOR ALL
    USING (true)
    WITH CHECK (true);
