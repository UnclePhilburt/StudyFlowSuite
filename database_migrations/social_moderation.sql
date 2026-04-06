-- Add moderation status to social posts (default approved so posts go live immediately)
ALTER TABLE social_posts ADD COLUMN IF NOT EXISTS moderation_status TEXT DEFAULT 'approved';
