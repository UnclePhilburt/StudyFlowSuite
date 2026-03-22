-- =====================================================
-- StudyFlow Upload Logging System
-- Missouri SB 1324 Compliance (7-year retention)
-- Created: March 22, 2026
-- =====================================================

-- 1. Create upload_logs table
-- This table logs EVERY upload (shared or private) for legal compliance
CREATE TABLE IF NOT EXISTS upload_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Timestamp (UTC) - Required for 7-year retention
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

    -- User identification
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,

    -- File information
    file_name TEXT NOT NULL,
    file_hash TEXT NOT NULL,  -- SHA-256 hash for tamper verification
    file_size INTEGER,        -- Size in bytes

    -- Consent tracking
    shared_with_nexus BOOLEAN DEFAULT FALSE NOT NULL,

    -- Network security
    ip_address TEXT,          -- For blocking bad actors

    -- AI processing flag
    ai_processed BOOLEAN DEFAULT FALSE,

    -- Metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

    -- Course context (optional)
    university TEXT,
    course_code TEXT
);

-- 2. Create indexes for fast querying
-- Index for 7-year retention queries (by timestamp)
CREATE INDEX idx_upload_logs_timestamp ON upload_logs(timestamp DESC);

-- Index for user history lookups
CREATE INDEX idx_upload_logs_user ON upload_logs(user_id);

-- Index for finding duplicate uploads by hash
CREATE INDEX idx_upload_logs_hash ON upload_logs(file_hash);

-- Index for IP-based security queries
CREATE INDEX idx_upload_logs_ip ON upload_logs(ip_address);

-- 3. Enable Row Level Security (RLS)
ALTER TABLE upload_logs ENABLE ROW LEVEL SECURITY;

-- 4. RLS Policies

-- Policy: Users can view their own upload logs
CREATE POLICY "Users can view own upload logs"
    ON upload_logs
    FOR SELECT
    USING (auth.uid() = user_id);

-- Policy: Service role can insert logs (backend only)
CREATE POLICY "Service role can insert upload logs"
    ON upload_logs
    FOR INSERT
    WITH CHECK (true);  -- Backend uses service role key

-- Policy: Service role can view all logs (for admin/compliance)
CREATE POLICY "Service role can view all logs"
    ON upload_logs
    FOR SELECT
    USING (true);  -- Backend admin queries

-- 5. Add has_seen_upload_modal to user_profiles
-- Tracks if user has seen the first-time upload modal
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS has_seen_upload_modal BOOLEAN DEFAULT FALSE;

-- 6. Create view for compliance reporting (7-year data)
CREATE OR REPLACE VIEW upload_compliance_summary AS
SELECT
    DATE_TRUNC('month', timestamp) AS month,
    COUNT(*) AS total_uploads,
    COUNT(*) FILTER (WHERE shared_with_nexus = true) AS nexus_uploads,
    COUNT(*) FILTER (WHERE shared_with_nexus = false) AS private_uploads,
    COUNT(DISTINCT user_id) AS unique_users,
    SUM(file_size) AS total_bytes
FROM upload_logs
GROUP BY DATE_TRUNC('month', timestamp)
ORDER BY month DESC;

-- 7. Function to clean up logs older than 7 years (Missouri compliance)
CREATE OR REPLACE FUNCTION cleanup_old_upload_logs()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM upload_logs
    WHERE timestamp < NOW() - INTERVAL '7 years';

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 8. Grant permissions
GRANT SELECT ON upload_compliance_summary TO authenticated;

-- =====================================================
-- Migration Complete
--
-- Next steps:
-- 1. Run this SQL in Supabase SQL Editor
-- 2. Verify tables created: upload_logs, user_profiles updated
-- 3. Test insert: INSERT INTO upload_logs (user_id, file_name, file_hash) VALUES ('[your-uuid]', 'test.pdf', 'abc123');
-- 4. Update backend to log all uploads
-- =====================================================
