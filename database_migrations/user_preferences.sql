-- Add preferences JSONB column to user_profiles for theme, wallpaper, etc.
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS preferences JSONB DEFAULT '{}';
