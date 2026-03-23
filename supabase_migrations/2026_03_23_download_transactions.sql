-- Download Transaction Logging
-- Tracks every file download with user, note, transaction code, IP
-- For DMCA compliance and audit trail

CREATE TABLE IF NOT EXISTS download_transactions (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID,
  note_id UUID NOT NULL,
  original_filename TEXT,
  transaction_code TEXT NOT NULL,
  ip_address TEXT,
  user_agent TEXT,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- Indexes for audit queries
CREATE INDEX idx_download_tx_user_id ON download_transactions(user_id);
CREATE INDEX idx_download_tx_note_id ON download_transactions(note_id);
CREATE INDEX idx_download_tx_created_at ON download_transactions(created_at);
CREATE INDEX idx_download_tx_code ON download_transactions(transaction_code);

-- RLS
ALTER TABLE download_transactions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own download transactions"
  ON download_transactions FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Insert download transactions"
  ON download_transactions FOR INSERT
  WITH CHECK (true);

CREATE POLICY "Service role full access"
  ON download_transactions FOR ALL
  USING (auth.role() = 'service_role');
