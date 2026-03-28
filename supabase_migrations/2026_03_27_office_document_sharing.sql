-- Office Document Sharing
-- Allows document owners to share with other users (view or edit)
-- Enables real-time co-editing via OnlyOffice when multiple users open the same document

CREATE TABLE IF NOT EXISTS office_document_shares (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_id UUID NOT NULL REFERENCES office_documents(id) ON DELETE CASCADE,
    owner_id UUID NOT NULL REFERENCES auth.users(id),
    shared_with_user_id UUID NOT NULL REFERENCES auth.users(id),
    permission TEXT NOT NULL DEFAULT 'view' CHECK (permission IN ('view', 'edit')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(doc_id, shared_with_user_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_shares_doc ON office_document_shares(doc_id);
CREATE INDEX IF NOT EXISTS idx_shares_shared_with ON office_document_shares(shared_with_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_shares_owner ON office_document_shares(owner_id);

-- RLS
ALTER TABLE office_document_shares ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Owners can view shares for their docs"
    ON office_document_shares FOR SELECT
    USING (auth.uid() = owner_id);

CREATE POLICY "Shared users can view their shares"
    ON office_document_shares FOR SELECT
    USING (auth.uid() = shared_with_user_id);

CREATE POLICY "Owners can create shares"
    ON office_document_shares FOR INSERT
    WITH CHECK (auth.uid() = owner_id);

CREATE POLICY "Owners can update shares"
    ON office_document_shares FOR UPDATE
    USING (auth.uid() = owner_id);

CREATE POLICY "Owners can delete shares"
    ON office_document_shares FOR DELETE
    USING (auth.uid() = owner_id);
