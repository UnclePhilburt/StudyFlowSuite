-- =====================================================
-- Add Usernames to StudyFlow
-- Allows users to choose a display name for Nexus citations
-- Created: March 22, 2026
-- =====================================================

-- 1. Add username to user_profiles
ALTER TABLE user_profiles
ADD COLUMN IF NOT EXISTS username TEXT UNIQUE;

-- 2. Add username to note_chunks (denormalized for fast lookups)
ALTER TABLE note_chunks
ADD COLUMN IF NOT EXISTS username TEXT;

-- 3. Add username to notes table
ALTER TABLE notes
ADD COLUMN IF NOT EXISTS username TEXT;

-- 4. Create index for username lookups
CREATE INDEX IF NOT EXISTS idx_user_profiles_username ON user_profiles(username);

-- 5. Add constraint: username must be 3-20 characters, alphanumeric + underscores
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'username_format'
    ) THEN
        ALTER TABLE user_profiles
        ADD CONSTRAINT username_format
        CHECK (username ~ '^[a-zA-Z0-9_]{3,20}$');
    END IF;
END $$;

-- 6. Backfill existing users with placeholder usernames (optional - can be NULL until they set one)
-- Note: We'll allow NULL for now so existing users aren't forced to set a username immediately

-- 7. Create function to auto-create user profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.user_profiles (id, email, full_name, username, collective_brain_opt_in)
  VALUES (
    NEW.id,
    NEW.email,
    NEW.raw_user_meta_data->>'full_name',
    NEW.raw_user_meta_data->>'username',
    COALESCE((NEW.raw_user_meta_data->>'collective_brain_opt_in')::boolean, true)
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- 8. Create trigger to run on new user signups
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_user();

-- 9. Update search_notes_with_vector function to return username
-- First drop the old function
DROP FUNCTION IF EXISTS search_notes_with_vector(vector, uuid, text, text, double precision, integer);

-- Then create the new version with username
CREATE OR REPLACE FUNCTION search_notes_with_vector(
    query_embedding VECTOR(1536),
    search_user_id UUID,
    search_university TEXT DEFAULT NULL,
    search_course_code TEXT DEFAULT NULL,
    match_threshold FLOAT DEFAULT 0.7,
    match_count INT DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    note_id UUID,
    chunk_text TEXT,
    content_summary TEXT,
    similarity FLOAT,
    university TEXT,
    course_code TEXT,
    is_own_note BOOLEAN,
    username TEXT
)
LANGUAGE plpgsql
AS $$
DECLARE
    searcher_opted_in BOOLEAN;
BEGIN
    -- Check if the searching user has opted into collective brain
    SELECT COALESCE(collective_brain_opt_in, TRUE)
    INTO searcher_opted_in
    FROM user_profiles
    WHERE user_profiles.id = search_user_id;

    RETURN QUERY
    SELECT
        nc.id,
        nc.note_id,
        nc.chunk_text,
        nc.content_summary,
        1 - (nc.embedding <=> query_embedding) AS similarity,
        nc.university,
        nc.course_code,
        (nc.user_id = search_user_id) AS is_own_note,
        nc.username
    FROM note_chunks nc
    INNER JOIN user_profiles note_owner ON nc.user_id = note_owner.id
    WHERE
        -- Include user's own notes OR public notes from opted-in users
        (nc.user_id = search_user_id OR
         (nc.is_public = TRUE AND note_owner.collective_brain_opt_in = TRUE))
        AND 1 - (nc.embedding <=> query_embedding) > match_threshold
    ORDER BY nc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- =====================================================
-- Migration Complete
--
-- Next steps:
-- 1. Run this SQL in Supabase SQL Editor
-- 2. Update signup flow to collect username (DONE)
-- 3. Update note chunk creation to include username (DONE)
-- 4. Update AI answer generation to cite contributors (DONE)
-- 5. Test the full flow!
-- =====================================================
