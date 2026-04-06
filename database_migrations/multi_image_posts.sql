-- Multi-image posts
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS images TEXT[] DEFAULT '{}';
