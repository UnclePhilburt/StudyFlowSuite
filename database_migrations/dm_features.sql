-- DM feature enhancements

-- Read receipts
ALTER TABLE dm_messages ADD COLUMN IF NOT EXISTS read_at TIMESTAMPTZ;

-- Online status / last seen
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMPTZ;

-- Message reactions
CREATE TABLE IF NOT EXISTS dm_reactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL REFERENCES dm_messages(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    emoji TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(message_id, user_id)
);

-- Image support in DMs
ALTER TABLE dm_messages ADD COLUMN IF NOT EXISTS image_url TEXT;
