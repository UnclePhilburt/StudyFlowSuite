-- Migration: Good Standing System for Legal Compliance
-- Implements Missouri HB 2271 compliance and DMCA Safe Harbor protections
-- Date: 2026-03-23

-- =====================================================
-- Add Good Standing fields to user_profiles
-- =====================================================

-- Add good_standing status (default TRUE for new users)
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS good_standing BOOLEAN DEFAULT TRUE;

-- Add last verified upload date (30-day rolling window)
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS last_verified_upload_date TIMESTAMP WITH TIME ZONE;

-- Add DMCA strike counter (three strikes = permanent loss of good standing)
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS dmca_strikes INTEGER DEFAULT 0;

-- Add permanent ban flag (for users who hit 3 strikes)
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS permanent_bad_standing BOOLEAN DEFAULT FALSE;

-- =====================================================
-- Create upload_verifications table
-- Tracks AI verification of uploads for "Good Standing" metric
-- =====================================================

CREATE TABLE IF NOT EXISTS upload_verifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    verified_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    verification_status TEXT NOT NULL, -- 'verified', 'rejected', 'pending'
    rejection_reason TEXT, -- 'spam', 'blank', 'invalid_format', etc.
    ai_confidence FLOAT, -- 0.0 to 1.0
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_upload_verifications_user_id ON upload_verifications(user_id);
CREATE INDEX IF NOT EXISTS idx_upload_verifications_verified_at ON upload_verifications(verified_at);

-- =====================================================
-- Create dmca_takedowns table
-- Tracks DMCA takedown notices for strike system
-- =====================================================

CREATE TABLE IF NOT EXISTS dmca_takedowns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    uploader_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    reporter_email TEXT NOT NULL,
    reporter_name TEXT,
    takedown_reason TEXT NOT NULL,
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    processed_at TIMESTAMP WITH TIME ZONE,
    strike_applied BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_dmca_takedowns_uploader_id ON dmca_takedowns(uploader_id);
CREATE INDEX IF NOT EXISTS idx_dmca_takedowns_note_id ON dmca_takedowns(note_id);

-- =====================================================
-- Create download_certifications table
-- Tracks user certifications for Missouri HB 2271 compliance
-- =====================================================

CREATE TABLE IF NOT EXISTS download_certifications (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    note_id UUID NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
    certified_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    ip_address TEXT, -- For legal records
    user_agent TEXT, -- For legal records
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_download_certifications_user_id ON download_certifications(user_id);
CREATE INDEX IF NOT EXISTS idx_download_certifications_note_id ON download_certifications(note_id);

-- =====================================================
-- Add RLS policies for new tables
-- =====================================================

-- upload_verifications: Users can only see their own verifications
ALTER TABLE upload_verifications ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own upload verifications"
    ON upload_verifications FOR SELECT
    USING (auth.uid() = user_id);

-- dmca_takedowns: Only admins can view (sensitive legal data)
ALTER TABLE dmca_takedowns ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Only admins can view DMCA takedowns"
    ON dmca_takedowns FOR SELECT
    USING (FALSE); -- Disable public access, admin uses service role

-- download_certifications: Users can only see their own certifications
ALTER TABLE download_certifications ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own download certifications"
    ON download_certifications FOR SELECT
    USING (auth.uid() = user_id);

-- =====================================================
-- Add comments for documentation
-- =====================================================

COMMENT ON COLUMN user_profiles.good_standing IS 'TRUE if user has uploaded verified content in last 30 days OR has active subscription';
COMMENT ON COLUMN user_profiles.last_verified_upload_date IS 'Date of most recent AI-verified upload (used for 30-day rolling window)';
COMMENT ON COLUMN user_profiles.dmca_strikes IS 'Number of DMCA takedown strikes (3 strikes = permanent bad standing)';
COMMENT ON COLUMN user_profiles.permanent_bad_standing IS 'TRUE if user has 3+ DMCA strikes (cannot regain good standing)';

COMMENT ON TABLE upload_verifications IS 'Tracks AI verification of note uploads for Good Standing status (Missouri HB 2271 compliance)';
COMMENT ON TABLE dmca_takedowns IS 'Tracks DMCA takedown notices for three-strikes policy (Safe Harbor compliance)';
COMMENT ON TABLE download_certifications IS 'Tracks user certifications for academic integrity (Missouri HB 2271 click-wrap requirement)';

-- =====================================================
-- Seed data: Set all existing users to good standing
-- (They get 30 days to upload their first verified note)
-- =====================================================

UPDATE user_profiles
SET good_standing = TRUE,
    last_verified_upload_date = NOW()
WHERE good_standing IS NULL;
