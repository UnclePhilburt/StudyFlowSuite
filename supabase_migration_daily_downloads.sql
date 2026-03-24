-- Migration: Add daily download tracking for free users
-- Run this in Supabase SQL Editor

-- Add columns to track daily downloads
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS daily_downloads_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS daily_downloads_reset_date DATE DEFAULT CURRENT_DATE;

-- Create index for faster queries on reset date
CREATE INDEX IF NOT EXISTS user_profiles_download_reset_idx
ON user_profiles(daily_downloads_reset_date);

-- Add comment explaining the columns
COMMENT ON COLUMN user_profiles.daily_downloads_count IS 'Number of downloads today (resets daily for free users)';
COMMENT ON COLUMN user_profiles.daily_downloads_reset_date IS 'Date when download count was last reset';
