-- Add dashboard_layout column to user_profiles table
-- Stores user's widget preferences as JSON array

ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS dashboard_layout JSONB DEFAULT '["quickLaunch", "recentConversations", "quickStats"]'::jsonb;

-- Add index for faster queries
CREATE INDEX IF NOT EXISTS idx_user_profiles_dashboard_layout ON user_profiles(id) WHERE dashboard_layout IS NOT NULL;

-- Add comment
COMMENT ON COLUMN user_profiles.dashboard_layout IS 'User dashboard widget layout stored as JSON array of widget IDs';
