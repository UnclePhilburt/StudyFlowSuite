-- Pinned post on profile
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS is_pinned BOOLEAN DEFAULT FALSE;

-- Block/mute system
CREATE TABLE IF NOT EXISTS user_blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    blocked_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    block_type TEXT NOT NULL CHECK (block_type IN ('block', 'mute')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, blocked_id)
);

CREATE INDEX IF NOT EXISTS idx_blocks_user ON user_blocks(user_id);
CREATE INDEX IF NOT EXISTS idx_blocks_blocked ON user_blocks(blocked_id);
