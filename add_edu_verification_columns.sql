-- Add .edu email verification columns to user_profiles table
-- Run this in your Supabase SQL editor

ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS edu_email_verified BOOLEAN DEFAULT false;

ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS edu_email TEXT;

ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS pending_edu_email TEXT;

ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS edu_verification_token TEXT;

-- Add index on verification token for faster lookups
CREATE INDEX IF NOT EXISTS idx_user_profiles_edu_verification_token
ON user_profiles(edu_verification_token);
