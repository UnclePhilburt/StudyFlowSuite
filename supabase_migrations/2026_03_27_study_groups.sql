-- Study Groups
-- Students can create named groups, invite members, share notes, and chat with AI together

CREATE TABLE IF NOT EXISTS study_groups (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    owner_id UUID NOT NULL REFERENCES auth.users(id),
    invite_code TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS study_group_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES auth.users(id),
    role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'member')),
    joined_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(group_id, user_id)
);

-- Shared notes: links a user's uploaded note to a group
CREATE TABLE IF NOT EXISTS study_group_notes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
    note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    added_by UUID NOT NULL REFERENCES auth.users(id),
    added_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(group_id, note_id)
);

-- Group chat messages (separate from personal conversations)
CREATE TABLE IF NOT EXISTS study_group_messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
    user_id UUID REFERENCES auth.users(id),
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    sources JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_study_groups_owner ON study_groups(owner_id);
CREATE INDEX IF NOT EXISTS idx_study_groups_invite ON study_groups(invite_code);
CREATE INDEX IF NOT EXISTS idx_sg_members_group ON study_group_members(group_id);
CREATE INDEX IF NOT EXISTS idx_sg_members_user ON study_group_members(user_id);
CREATE INDEX IF NOT EXISTS idx_sg_notes_group ON study_group_notes(group_id);
CREATE INDEX IF NOT EXISTS idx_sg_messages_group ON study_group_messages(group_id, created_at);

-- Update timestamp trigger
CREATE OR REPLACE FUNCTION update_study_group_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE study_groups SET updated_at = NOW() WHERE id = NEW.group_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_sg_timestamp_on_message ON study_group_messages;
CREATE TRIGGER update_sg_timestamp_on_message
    AFTER INSERT ON study_group_messages
    FOR EACH ROW EXECUTE FUNCTION update_study_group_timestamp();

-- RLS
ALTER TABLE study_groups ENABLE ROW LEVEL SECURITY;
ALTER TABLE study_group_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE study_group_notes ENABLE ROW LEVEL SECURITY;
ALTER TABLE study_group_messages ENABLE ROW LEVEL SECURITY;

-- study_groups: members can view, owners can modify
CREATE POLICY "Members can view their groups" ON study_groups FOR SELECT
    USING (id IN (SELECT group_id FROM study_group_members WHERE user_id = auth.uid()));

CREATE POLICY "Users can create groups" ON study_groups FOR INSERT
    WITH CHECK (auth.uid() = owner_id);

CREATE POLICY "Owners can update groups" ON study_groups FOR UPDATE
    USING (auth.uid() = owner_id);

CREATE POLICY "Owners can delete groups" ON study_groups FOR DELETE
    USING (auth.uid() = owner_id);

-- study_group_members: members can view, owners can manage
CREATE POLICY "Members can view group members" ON study_group_members FOR SELECT
    USING (group_id IN (SELECT group_id FROM study_group_members WHERE user_id = auth.uid()));

CREATE POLICY "Can join groups" ON study_group_members FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Owners can remove members" ON study_group_members FOR DELETE
    USING (group_id IN (SELECT id FROM study_groups WHERE owner_id = auth.uid()) OR user_id = auth.uid());

-- study_group_notes: members can view and add
CREATE POLICY "Members can view group notes" ON study_group_notes FOR SELECT
    USING (group_id IN (SELECT group_id FROM study_group_members WHERE user_id = auth.uid()));

CREATE POLICY "Members can add notes" ON study_group_notes FOR INSERT
    WITH CHECK (group_id IN (SELECT group_id FROM study_group_members WHERE user_id = auth.uid()));

CREATE POLICY "Note adder or owner can remove" ON study_group_notes FOR DELETE
    USING (added_by = auth.uid() OR group_id IN (SELECT id FROM study_groups WHERE owner_id = auth.uid()));

-- study_group_messages: members can view and send
CREATE POLICY "Members can view messages" ON study_group_messages FOR SELECT
    USING (group_id IN (SELECT group_id FROM study_group_members WHERE user_id = auth.uid()));

CREATE POLICY "Members can send messages" ON study_group_messages FOR INSERT
    WITH CHECK (group_id IN (SELECT group_id FROM study_group_members WHERE user_id = auth.uid()));

-- Enable realtime for group messages
ALTER PUBLICATION supabase_realtime ADD TABLE study_group_messages;
