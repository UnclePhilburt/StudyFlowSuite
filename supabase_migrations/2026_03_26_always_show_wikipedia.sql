-- Always show Wikipedia content regardless of collective_brain_opt_in
-- Problem: Wikipedia (user_id = NULL) was gated behind searcher_opted_in,
-- so users who haven't opted into the Nexus can't see Wikipedia results.
-- Fix: Wikipedia content is public educational material and should always be included.

DROP FUNCTION IF EXISTS search_notes_with_vector(vector, uuid, text, text, double precision, integer);

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
    LEFT JOIN user_profiles note_owner ON nc.user_id = note_owner.id
    WHERE
        (
            -- Always show user's own notes
            nc.user_id = search_user_id
            OR
            -- ALWAYS show Wikipedia/system notes (user_id = NULL, is_public = TRUE)
            -- Wikipedia is public educational content, not gated behind opt-in
            (
                nc.user_id IS NULL
                AND nc.is_public = TRUE
            )
            OR
            -- Show other users' notes ONLY if:
            -- 1. Searcher has opted in
            -- 2. Note owner has opted in
            -- 3. Note is public
            (
                nc.user_id IS NOT NULL
                AND searcher_opted_in = TRUE
                AND COALESCE(note_owner.collective_brain_opt_in, TRUE) = TRUE
                AND nc.is_public = TRUE
            )
        )
        AND 1 - (nc.embedding <=> query_embedding) > match_threshold
    ORDER BY nc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
