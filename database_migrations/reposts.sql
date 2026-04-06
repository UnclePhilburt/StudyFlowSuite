-- Repost support
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS repost_of UUID REFERENCES social_posts(id) ON DELETE CASCADE;
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS repost_text TEXT;  -- optional quote text
CREATE INDEX IF NOT EXISTS idx_posts_repost ON social_posts(repost_of);
