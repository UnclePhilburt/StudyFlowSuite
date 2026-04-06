-- Stories support (24-hour disappearing posts)
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS is_story BOOLEAN DEFAULT FALSE;
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS story_bg TEXT;  -- gradient/color for text stories
CREATE INDEX IF NOT EXISTS idx_posts_stories ON social_posts(is_story, created_at DESC) WHERE is_story = TRUE;
