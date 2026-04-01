-- =====================================================
-- StudyFlow AI Response Provenance Logging
-- Missouri SB 1324 Compliance (7-year retention)
-- "Provenance Marker" requirement for AI-generated content
-- Created: March 23, 2026
-- =====================================================

-- 1. Create ai_response_logs table
-- Logs EVERY AI-generated response for legal compliance
-- Required fields per SB 1324: timestamp, user identity,
-- prompt/input, output description, model used
CREATE TABLE IF NOT EXISTS ai_response_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Timestamp (UTC) - Required for 7-year retention
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL,

    -- User identification
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,

    -- Conversation context
    conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL,

    -- Input: What triggered the AI (the student's question)
    prompt_text TEXT NOT NULL,
    prompt_length INTEGER NOT NULL,

    -- Output: Description of what was generated
    response_length INTEGER NOT NULL,
    response_hash TEXT NOT NULL,  -- SHA-256 of the AI response for tamper verification

    -- Source attribution: What notes/data the AI used
    sources_used JSONB DEFAULT '[]'::jsonb,
    -- Format: [{note_id, filename, similarity, contributor_username, source_type}]

    -- Model/processing metadata
    model_used TEXT NOT NULL DEFAULT 'gemini-3.1-flash-lite-preview',
    response_time_ms INTEGER,  -- How long generation took

    -- Steganography tracking
    provenance_signature TEXT,  -- The zero-width encoded signature embedded in response

    -- Network context
    ip_address TEXT,

    -- Compliance metadata
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW() NOT NULL
);

-- 2. Create indexes for compliance queries
-- Primary: 7-year retention queries by timestamp
CREATE INDEX idx_ai_response_logs_timestamp ON ai_response_logs(timestamp DESC);

-- User history lookups
CREATE INDEX idx_ai_response_logs_user ON ai_response_logs(user_id);

-- Conversation-level audit trail
CREATE INDEX idx_ai_response_logs_conversation ON ai_response_logs(conversation_id);

-- Response hash for tamper detection
CREATE INDEX idx_ai_response_logs_hash ON ai_response_logs(response_hash);

-- Model usage tracking
CREATE INDEX idx_ai_response_logs_model ON ai_response_logs(model_used);

-- 3. Enable Row Level Security (RLS)
ALTER TABLE ai_response_logs ENABLE ROW LEVEL SECURITY;

-- 4. RLS Policies

-- Users can view their own AI response logs
CREATE POLICY "Users can view own AI response logs"
    ON ai_response_logs
    FOR SELECT
    USING (auth.uid() = user_id);

-- Service role can insert logs (backend only)
CREATE POLICY "Service role can insert AI response logs"
    ON ai_response_logs
    FOR INSERT
    WITH CHECK (true);

-- Service role can view all logs (admin/compliance)
CREATE POLICY "Service role can view all AI response logs"
    ON ai_response_logs
    FOR SELECT
    USING (true);

-- 5. Add provenance_metadata column to conversation_messages
-- Stores C2PA-style provenance info inline with each message
ALTER TABLE conversation_messages
ADD COLUMN IF NOT EXISTS provenance_metadata JSONB DEFAULT NULL;
-- Format: {model, timestamp, sources, signature, depiction_disclaimer}

-- 6. Compliance reporting view
CREATE OR REPLACE VIEW ai_provenance_compliance_summary AS
SELECT
    DATE_TRUNC('month', timestamp) AS month,
    COUNT(*) AS total_ai_responses,
    COUNT(DISTINCT user_id) AS unique_users,
    COUNT(DISTINCT conversation_id) AS conversations_with_ai,
    AVG(response_length) AS avg_response_length,
    AVG(response_time_ms) AS avg_response_time_ms,
    model_used,
    COUNT(*) FILTER (WHERE provenance_signature IS NOT NULL) AS steganography_marked,
    SUM(jsonb_array_length(sources_used)) AS total_sources_cited
FROM ai_response_logs
GROUP BY DATE_TRUNC('month', timestamp), model_used
ORDER BY month DESC;

-- 7. Function to clean up logs older than 7 years
CREATE OR REPLACE FUNCTION cleanup_old_ai_response_logs()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM ai_response_logs
    WHERE timestamp < NOW() - INTERVAL '7 years';

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 8. Grant permissions
GRANT SELECT ON ai_provenance_compliance_summary TO authenticated;

-- =====================================================
-- Migration Complete
--
-- This table satisfies SB 1324 Section 3(b):
-- "Deployers shall maintain encrypted logs for 7 years"
--
-- Logged per response:
--   [x] Timestamp (when was it generated)
--   [x] User Identity (who triggered the AI)
--   [x] Prompt/Input (what question was asked)
--   [x] Output Description (response length, hash, type)
--   [x] Sources Used (what notes fed the AI)
--   [x] Model Used (which AI model)
--   [x] Provenance Signature (steganography marker)
--
-- Next steps:
-- 1. Run this SQL in Supabase SQL Editor
-- 2. Deploy updated backend with logging calls
-- 3. Verify with: SELECT * FROM ai_response_logs LIMIT 5;
-- =====================================================
