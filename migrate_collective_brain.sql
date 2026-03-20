-- Migration: Add Collective Brain Two-Way Enforcement
-- Run this in Supabase SQL Editor to update the search function

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
    is_own_note BOOLEAN
)
LANGUAGE plpgsql
AS $$
DECLARE
    searcher_opted_in BOOLEAN;
BEGIN
    -- Check if the searching user has opted into collective brain
    SELECT COALESCE(collective_brain_opt_in, TRUE)
    INTO searcher_opted_in
    FROM users
    WHERE id = search_user_id;

    RETURN QUERY
    SELECT
        nc.id,
        nc.note_id,
        nc.chunk_text,
        nc.content_summary,
        1 - (nc.embedding <=> query_embedding) AS similarity,
        nc.university,
        nc.course_code,
        (nc.user_id = search_user_id) AS is_own_note
    FROM note_chunks nc
    INNER JOIN users note_owner ON nc.user_id = note_owner.id
    WHERE
        (
            -- Always show user's own notes
            nc.user_id = search_user_id
            OR
            -- Show other users' notes ONLY if:
            -- 1. Searcher has opted in
            -- 2. Note owner has opted in
            -- 3. Note is public
            (
                searcher_opted_in = TRUE
                AND COALESCE(note_owner.collective_brain_opt_in, TRUE) = TRUE
                AND nc.is_public = TRUE
            )
        )
        AND 1 - (nc.embedding <=> query_embedding) > match_threshold
    ORDER BY nc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
