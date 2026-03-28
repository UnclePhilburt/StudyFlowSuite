-- Pending group invites
-- Members must accept invites before being added to groups

CREATE TABLE IF NOT EXISTS study_group_invites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
    invited_by UUID NOT NULL REFERENCES auth.users(id),
    invited_user_id UUID NOT NULL REFERENCES auth.users(id),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'declined')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(group_id, invited_user_id)
);

CREATE INDEX IF NOT EXISTS idx_sg_invites_user ON study_group_invites(invited_user_id, status);
CREATE INDEX IF NOT EXISTS idx_sg_invites_group ON study_group_invites(group_id);

ALTER TABLE study_group_invites ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Invited users can view their invites" ON study_group_invites FOR SELECT
    USING (auth.uid() = invited_user_id);

CREATE POLICY "Members can create invites" ON study_group_invites FOR INSERT
    WITH CHECK (auth.uid() = invited_by);

CREATE POLICY "Invited users can update their invites" ON study_group_invites FOR UPDATE
    USING (auth.uid() = invited_user_id);
