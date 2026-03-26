-- Note annotations system
-- Allows users to highlight, draw, and add text notes on PDF pages

CREATE TABLE note_annotations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    note_id UUID NOT NULL,
    page_number INTEGER NOT NULL,
    annotations_json JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(user_id, note_id, page_number)
);

CREATE INDEX idx_annotations_user_note ON note_annotations (user_id, note_id);

-- RLS policies
ALTER TABLE note_annotations ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own annotations"
    ON note_annotations FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own annotations"
    ON note_annotations FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own annotations"
    ON note_annotations FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own annotations"
    ON note_annotations FOR DELETE
    USING (auth.uid() = user_id);

-- Service role can manage all annotations
CREATE POLICY "Service role can manage annotations"
    ON note_annotations FOR ALL
    WITH CHECK (true);
