-- Prep for institutional licenses
-- Optional institution_id on study groups for future school-level grouping

ALTER TABLE study_groups ADD COLUMN IF NOT EXISTS institution TEXT;
CREATE INDEX IF NOT EXISTS idx_study_groups_institution ON study_groups(institution);
