-- Add hashtags and mentions to social posts
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS hashtags TEXT[] DEFAULT '{}';
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS mentions TEXT[] DEFAULT '{}';

-- Index for hashtag search
CREATE INDEX IF NOT EXISTS idx_posts_hashtags ON social_posts USING GIN (hashtags);
