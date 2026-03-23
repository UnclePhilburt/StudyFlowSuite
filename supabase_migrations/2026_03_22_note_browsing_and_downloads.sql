-- Migration: Note Browsing and Download Tracking
-- Enables students to search/browse raw notes with DMCA-compliant download tracking

-- =====================================================
-- 1. Add .edu email verification to user_profiles
-- =====================================================

ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS edu_email_verified BOOLEAN DEFAULT FALSE;

COMMENT ON COLUMN user_profiles.edu_email_verified IS 'Whether user has verified a .edu email address (required for browsing raw notes)';


-- =====================================================
-- 2. Add topic tags to notes for browsing/filtering
-- =====================================================

ALTER TABLE notes
ADD COLUMN IF NOT EXISTS topic_tags TEXT[] DEFAULT '{}';

COMMENT ON COLUMN notes.topic_tags IS 'AI-generated topic tags for browsing (e.g., Biology, Cell Division, Mitosis)';


-- =====================================================
-- 3. Create download_transactions table
-- Tracks every download for DMCA compliance and daily limits
-- =====================================================

CREATE TABLE IF NOT EXISTS download_transactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id TEXT UNIQUE NOT NULL,  -- Format: #99281
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    downloaded_at TIMESTAMPTZ DEFAULT NOW(),
    purpose TEXT,  -- Why they downloaded it (from pop-up)
    watermark_data JSONB,  -- Stores username, transaction ID, SynthID metadata
    ip_address INET,
    user_agent TEXT,

    -- Indexes for querying
    CONSTRAINT fk_user FOREIGN KEY (user_id) REFERENCES auth.users(id),
    CONSTRAINT fk_note FOREIGN KEY (note_id) REFERENCES notes(id)
);

-- Index for daily download limit checks
CREATE INDEX IF NOT EXISTS idx_downloads_user_date ON download_transactions (user_id, downloaded_at);

-- Index for DMCA tracking
CREATE INDEX IF NOT EXISTS idx_downloads_transaction ON download_transactions (transaction_id);

COMMENT ON TABLE download_transactions IS 'DMCA-compliant download tracking - retains for 7 years per Missouri SB 1324';


-- =====================================================
-- 4. Create note_views table
-- Tracks when users view notes in browser (non-download)
-- =====================================================

CREATE TABLE IF NOT EXISTS note_views (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    viewed_at TIMESTAMPTZ DEFAULT NOW(),
    ip_address INET,

    CONSTRAINT fk_view_user FOREIGN KEY (user_id) REFERENCES auth.users(id),
    CONSTRAINT fk_view_note FOREIGN KEY (note_id) REFERENCES notes(id)
);

CREATE INDEX IF NOT EXISTS idx_note_views_note ON note_views (note_id, viewed_at);
CREATE INDEX IF NOT EXISTS idx_note_views_user ON note_views (user_id, viewed_at);

COMMENT ON TABLE note_views IS 'Tracks note views for analytics and popular notes ranking';


-- =====================================================
-- 5. Create dmca_takedown_requests table
-- Handles copyright takedown requests
-- =====================================================

CREATE TABLE IF NOT EXISTS dmca_takedown_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id TEXT UNIQUE NOT NULL,  -- Human-readable ID like DMCA-20260322-001
    submitted_at TIMESTAMPTZ DEFAULT NOW(),

    -- Requestor info
    requestor_name TEXT NOT NULL,
    requestor_email TEXT NOT NULL,
    requestor_type TEXT,  -- 'student', 'professor', 'university', 'copyright_holder'

    -- Complaint details
    note_id UUID REFERENCES notes(id) ON DELETE SET NULL,
    note_filename TEXT,  -- Preserve even if note deleted
    complaint_description TEXT NOT NULL,
    copyright_claim BOOLEAN DEFAULT FALSE,

    -- Status tracking
    status TEXT DEFAULT 'pending',  -- pending, reviewing, removed, rejected
    reviewed_at TIMESTAMPTZ,
    reviewed_by UUID REFERENCES auth.users(id),
    resolution_notes TEXT,

    -- Evidence
    evidence_urls TEXT[],  -- Links to proof of ownership

    CONSTRAINT valid_status CHECK (status IN ('pending', 'reviewing', 'removed', 'rejected'))
);

CREATE INDEX IF NOT EXISTS idx_dmca_status ON dmca_takedown_requests (status, submitted_at);

COMMENT ON TABLE dmca_takedown_requests IS 'DMCA Section 512 takedown request tracking - required for safe harbor protection';


-- =====================================================
-- 6. Function to check daily download limit
-- =====================================================

CREATE OR REPLACE FUNCTION check_download_limit(check_user_id UUID)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    downloads_today INTEGER;
BEGIN
    -- Count downloads in last 24 hours
    SELECT COUNT(*)
    INTO downloads_today
    FROM download_transactions
    WHERE user_id = check_user_id
    AND downloaded_at > NOW() - INTERVAL '24 hours';

    RETURN downloads_today;
END;
$$;

COMMENT ON FUNCTION check_download_limit IS 'Returns number of downloads in last 24 hours for rate limiting';


-- =====================================================
-- 7. Function to generate unique transaction ID
-- =====================================================

CREATE OR REPLACE FUNCTION generate_transaction_id()
RETURNS TEXT
LANGUAGE plpgsql
AS $$
DECLARE
    new_id TEXT;
    id_exists BOOLEAN;
BEGIN
    LOOP
        -- Generate random 5-digit number
        new_id := '#' || LPAD(FLOOR(RANDOM() * 99999)::TEXT, 5, '0');

        -- Check if it exists
        SELECT EXISTS(SELECT 1 FROM download_transactions WHERE transaction_id = new_id)
        INTO id_exists;

        -- If unique, return it
        IF NOT id_exists THEN
            RETURN new_id;
        END IF;
    END LOOP;
END;
$$;

COMMENT ON FUNCTION generate_transaction_id IS 'Generates unique 5-digit transaction ID like #99281';


-- =====================================================
-- Migration Complete
-- =====================================================
