-- Pinned messages: add pinned flag to group messages
ALTER TABLE study_group_messages ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE study_group_messages ADD COLUMN IF NOT EXISTS pinned_by UUID REFERENCES auth.users(id);

-- Study schedule events
CREATE TABLE IF NOT EXISTS study_group_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id UUID NOT NULL REFERENCES study_groups(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    event_date DATE NOT NULL,
    event_time TIME,
    created_by UUID NOT NULL REFERENCES auth.users(id),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sg_events_group ON study_group_events(group_id, event_date);

ALTER TABLE study_group_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Members can view group events" ON study_group_events FOR SELECT
    USING (group_id IN (SELECT group_id FROM study_group_members WHERE user_id = auth.uid()));

CREATE POLICY "Members can create events" ON study_group_events FOR INSERT
    WITH CHECK (group_id IN (SELECT group_id FROM study_group_members WHERE user_id = auth.uid()));

CREATE POLICY "Creator or owner can delete events" ON study_group_events FOR DELETE
    USING (created_by = auth.uid() OR group_id IN (SELECT id FROM study_groups WHERE owner_id = auth.uid()));
