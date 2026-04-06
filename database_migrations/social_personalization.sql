-- Social interests (onboarding picks)
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS social_interests JSONB DEFAULT '{}';

-- Engagement tracking for feed algorithm
CREATE TABLE IF NOT EXISTS social_engagement (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    post_id UUID NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
    author_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    action TEXT NOT NULL CHECK (action IN ('view', 'upvote', 'comment', 'click')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_engagement_user ON social_engagement(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_engagement_author ON social_engagement(author_id);
CREATE INDEX IF NOT EXISTS idx_engagement_action ON social_engagement(user_id, action);
