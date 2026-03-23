-- Fix Wikipedia Search with Username Support
-- Problem: Wikipedia articles have user_id=NULL, but INNER JOIN with user_profiles excludes them
-- Solution: Use LEFT JOIN and treat NULL user_id as system-wide public content
-- Also: Keep username field in return type

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
            -- Show system notes (user_id = NULL) like Wikipedia if searcher has opted in
            (
                nc.user_id IS NULL
                AND nc.is_public = TRUE
                AND searcher_opted_in = TRUE
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
