-- =====================================================
-- StudyFlow GUARD Act Age Verification System
-- Missouri SB 1455 Compliance
-- Transactional Data Verification + Account Freeze
-- Created: March 23, 2026
-- =====================================================

-- 1. Add age verification columns to user_profiles
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS birthdate DATE,
ADD COLUMN IF NOT EXISTS legal_name TEXT,
ADD COLUMN IF NOT EXISTS zip_code TEXT,
ADD COLUMN IF NOT EXISTS age_verified BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS age_verified_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS age_verification_method TEXT,
ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS account_frozen BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS frozen_at TIMESTAMP WITH TIME ZONE,
ADD COLUMN IF NOT EXISTS frozen_reason TEXT;

-- 2. Index for quickly finding unverified/frozen accounts
CREATE INDEX IF NOT EXISTS idx_user_profiles_age_verified ON user_profiles(age_verified);
CREATE INDEX IF NOT EXISTS idx_user_profiles_account_frozen ON user_profiles(account_frozen);
CREATE INDEX IF NOT EXISTS idx_user_profiles_last_verified ON user_profiles(last_verified_at);

-- 3. Function to freeze all unverified accounts (run on Aug 28, 2026)
CREATE OR REPLACE FUNCTION freeze_unverified_accounts()
RETURNS INTEGER AS $$
DECLARE
    frozen_count INTEGER;
BEGIN
    UPDATE user_profiles
    SET account_frozen = TRUE,
        frozen_at = NOW(),
        frozen_reason = 'guard_act_unverified'
    WHERE age_verified = FALSE
      AND account_frozen = FALSE;

    GET DIAGNOSTICS frozen_count = ROW_COUNT;
    RETURN frozen_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 4. Function to flag accounts needing re-verification (12-month cycle)
CREATE OR REPLACE FUNCTION flag_stale_verifications()
RETURNS INTEGER AS $$
DECLARE
    flagged_count INTEGER;
BEGIN
    UPDATE user_profiles
    SET account_frozen = TRUE,
        frozen_at = NOW(),
        frozen_reason = 'reverification_required'
    WHERE age_verified = TRUE
      AND last_verified_at < NOW() - INTERVAL '12 months'
      AND account_frozen = FALSE;

    GET DIAGNOSTICS flagged_count = ROW_COUNT;
    RETURN flagged_count;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 5. Compliance view for age verification status
CREATE OR REPLACE VIEW age_verification_summary AS
SELECT
    COUNT(*) AS total_users,
    COUNT(*) FILTER (WHERE age_verified = TRUE) AS verified_users,
    COUNT(*) FILTER (WHERE age_verified = FALSE) AS unverified_users,
    COUNT(*) FILTER (WHERE account_frozen = TRUE) AS frozen_accounts,
    COUNT(*) FILTER (WHERE frozen_reason = 'guard_act_unverified') AS frozen_guard_act,
    COUNT(*) FILTER (WHERE frozen_reason = 'reverification_required') AS frozen_reverification,
    COUNT(*) FILTER (WHERE age_verification_method = 'transactional_data') AS verified_transactional,
    COUNT(*) FILTER (WHERE age_verification_method = 'edu_email') AS verified_edu,
    COUNT(*) FILTER (WHERE last_verified_at > NOW() - INTERVAL '12 months') AS verified_current
FROM user_profiles;

-- 6. Grant permissions
GRANT SELECT ON age_verification_summary TO authenticated;

-- =====================================================
-- Migration Complete
--
-- New columns on user_profiles:
--   birthdate, legal_name, zip_code,
--   age_verified, age_verified_at, age_verification_method,
--   last_verified_at, account_frozen, frozen_at, frozen_reason
--
-- Functions:
--   freeze_unverified_accounts() - Run on Aug 28, 2026
--   flag_stale_verifications() - Run monthly via cron
--
-- Next steps:
-- 1. Run this SQL in Supabase SQL Editor
-- 2. Deploy backend with verification endpoints
-- 3. Set up Supabase cron to run flag_stale_verifications() monthly
-- =====================================================
