-- Polls on social posts
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS poll_options JSONB;  -- [{text, votes}]
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS poll_ends_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS poll_votes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    post_id UUID NOT NULL REFERENCES social_posts(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    option_index INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(post_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_poll_votes_post ON poll_votes(post_id);
