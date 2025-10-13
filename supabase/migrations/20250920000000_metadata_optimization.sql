-- Migration to add optimized metadata fetching function
-- This replaces N+1 query patterns with a single optimized query

-- Function to get question metadata in bulk with optimal performance
CREATE OR REPLACE FUNCTION get_question_metadata_bulk(question_ids_param text[])
RETURNS TABLE (
    question_id text,
    topics text[],
    subtopics text[],
    tags text[]
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        q.id as question_id,
        COALESCE(array_agg(DISTINCT t.name) FILTER (WHERE t.name IS NOT NULL), '{}') as topics,
        COALESCE(array_agg(DISTINCT st.name) FILTER (WHERE st.name IS NOT NULL), '{}') as subtopics,
        COALESCE(array_agg(DISTINCT tag.name) FILTER (WHERE tag.name IS NOT NULL), '{}') as tags
    FROM questions q
    LEFT JOIN question_topics qt ON q.id = qt.question_id
    LEFT JOIN topics t ON qt.topic_id = t.id
    LEFT JOIN question_subtopics qst ON q.id = qst.question_id
    LEFT JOIN subtopics st ON qst.subtopic_id = st.id  
    LEFT JOIN question_tags qtag ON q.id = qtag.question_id
    LEFT JOIN tags tag ON qtag.tag_id = tag.id
    WHERE q.id = ANY(question_ids_param)
    GROUP BY q.id;
END;
$$ LANGUAGE plpgsql;

-- Add comments for documentation
COMMENT ON FUNCTION get_question_metadata_bulk(text[]) IS 
'Optimized function to fetch topics, subtopics, and tags for multiple questions in a single query. 
Replaces N+1 query pattern that was causing performance issues.';