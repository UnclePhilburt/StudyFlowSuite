-- Social Groups (separate from Study Groups)
CREATE TABLE IF NOT EXISTS social_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    cover_url TEXT,
    owner_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    is_public BOOLEAN DEFAULT TRUE,
    member_count INTEGER DEFAULT 1,
    category TEXT DEFAULT 'general',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS social_group_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID NOT NULL REFERENCES social_groups(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'admin', 'member')),
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(group_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_social_group_members_group ON social_group_members(group_id);
CREATE INDEX IF NOT EXISTS idx_social_group_members_user ON social_group_members(user_id);
CREATE INDEX IF NOT EXISTS idx_social_groups_public ON social_groups(is_public, member_count DESC);

-- Social posts already have a group_id column referencing study_groups.
-- Add a social_group_id column for social groups.
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS social_group_id UUID REFERENCES social_groups(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_posts_social_group ON social_posts(social_group_id);
