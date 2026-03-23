-- Missouri Legal Compliance: Consent Receipt Logging
-- Tracks every click-wrap agreement (download consent) for AG audit trail
-- Covers HB 2271 (Academic Integrity), SB 1324 (AI Provenance), DMCA

CREATE TABLE IF NOT EXISTS consent_logs (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID NOT NULL,
  file_id TEXT NOT NULL,
  legal_version TEXT NOT NULL,
  action TEXT NOT NULL DEFAULT 'download_consent',
  ip_address TEXT,
  user_agent TEXT,
  created_at TIMESTAMPTZ DEFAULT now() NOT NULL
);

-- Indexes for AG audit queries
CREATE INDEX idx_consent_logs_user_id ON consent_logs(user_id);
CREATE INDEX idx_consent_logs_file_id ON consent_logs(file_id);
CREATE INDEX idx_consent_logs_created_at ON consent_logs(created_at);
CREATE INDEX idx_consent_logs_legal_version ON consent_logs(legal_version);

-- RLS policies
ALTER TABLE consent_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can insert own consent logs"
  ON consent_logs FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can view own consent logs"
  ON consent_logs FOR SELECT
  USING (auth.uid() = user_id);

-- Service role can read all (for admin/audit)
CREATE POLICY "Service role full access"
  ON consent_logs FOR ALL
  USING (auth.role() = 'service_role');

-- Compliance summary view
CREATE OR REPLACE VIEW consent_log_summary AS
SELECT
  user_id,
  file_id,
  legal_version,
  action,
  ip_address,
  created_at
FROM consent_logs
ORDER BY created_at DESC;
