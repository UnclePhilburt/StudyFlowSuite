-- Migration: Add Canvas calendar feed URL for auto-sync
-- Run this in Supabase SQL Editor

-- Add column to store Canvas calendar feed URL
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS canvas_feed_url TEXT;

-- Add comment explaining the column
COMMENT ON COLUMN user_profiles.canvas_feed_url IS 'Canvas iCal feed URL for auto-syncing calendar events';
