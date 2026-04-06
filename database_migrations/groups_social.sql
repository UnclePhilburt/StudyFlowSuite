-- Extend study_groups for Facebook-style social groups
ALTER TABLE study_groups ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE study_groups ADD COLUMN IF NOT EXISTS cover_url TEXT;
ALTER TABLE study_groups ADD COLUMN IF NOT EXISTS is_public BOOLEAN DEFAULT TRUE;
ALTER TABLE study_groups ADD COLUMN IF NOT EXISTS member_count INTEGER DEFAULT 1;
ALTER TABLE study_groups ADD COLUMN IF NOT EXISTS category TEXT DEFAULT 'general';
