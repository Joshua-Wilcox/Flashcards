-- PDF Storage Refactor Migration
-- This migration updates the PDF system to use Supabase storage buckets
-- and adds necessary fields for full database-driven PDF management

-- Update pdfs table to support storage buckets
ALTER TABLE pdfs 
DROP COLUMN IF EXISTS path;

ALTER TABLE pdfs 
ADD COLUMN storage_path text NOT NULL,
ADD COLUMN original_filename text NOT NULL,
ADD COLUMN file_size bigint,
ADD COLUMN mime_type text DEFAULT 'application/pdf',
ADD COLUMN uploaded_by text,
ADD COLUMN metadata jsonb DEFAULT '{}',
ADD COLUMN is_active boolean DEFAULT true;

-- Add index for better performance
CREATE INDEX IF NOT EXISTS idx_pdfs_storage_path ON pdfs(storage_path);
CREATE INDEX IF NOT EXISTS idx_pdfs_module_id ON pdfs(module_id);
CREATE INDEX IF NOT EXISTS idx_pdfs_is_active ON pdfs(is_active);

-- Create RPC function for PDF matching (optimized version)
CREATE OR REPLACE FUNCTION get_pdfs_for_question_v2(
    question_id_param text,
    max_pdfs_param integer DEFAULT 3
) RETURNS TABLE (
    pdf_id integer,
    storage_path text,
    original_filename text,
    module_name text,
    topic_name text,
    subtopic_name text,
    tags text[],
    match_percent double precision,
    match_reasons text[]
) AS $$
DECLARE
    question_module_id integer;
    question_topics text[];
    question_subtopics text[];
    question_tags text[];
BEGIN
    -- Get question metadata
    SELECT 
        q.module_id,
        COALESCE(array_agg(DISTINCT t.name) FILTER (WHERE t.name IS NOT NULL), '{}'),
        COALESCE(array_agg(DISTINCT st.name) FILTER (WHERE st.name IS NOT NULL), '{}'),
        COALESCE(array_agg(DISTINCT tag.name) FILTER (WHERE tag.name IS NOT NULL), '{}')
    INTO question_module_id, question_topics, question_subtopics, question_tags
    FROM questions q
    LEFT JOIN question_topics qt ON q.id = qt.question_id
    LEFT JOIN topics t ON qt.topic_id = t.id
    LEFT JOIN question_subtopics qst ON q.id = qst.question_id
    LEFT JOIN subtopics st ON qst.subtopic_id = st.id
    LEFT JOIN question_tags qtag ON q.id = qtag.question_id
    LEFT JOIN tags tag ON qtag.tag_id = tag.id
    WHERE q.id = question_id_param
    GROUP BY q.module_id;
    
    IF question_module_id IS NULL THEN
        RETURN;
    END IF;
    
    -- Return matching PDFs with scores
    RETURN QUERY
    WITH pdf_scores AS (
        SELECT 
            p.id,
            p.storage_path,
            p.original_filename,
            m.name as module_name,
            topic.name as topic_name,
            subtopic.name as subtopic_name,
            COALESCE(array_agg(DISTINCT pdf_tag.name) FILTER (WHERE pdf_tag.name IS NOT NULL), '{}') as pdf_tags,
            
            -- Calculate match score
            CASE 
                -- Module + Topic + Subtopic match (95%)
                WHEN p.module_id = question_module_id 
                     AND topic.name = ANY(question_topics) 
                     AND subtopic.name = ANY(question_subtopics) THEN 95
                -- Module + Topic match (80%)
                WHEN p.module_id = question_module_id 
                     AND topic.name = ANY(question_topics) THEN 80
                -- Module match (60%)
                WHEN p.module_id = question_module_id THEN 60
                -- Tag overlap calculation (20-50%)
                ELSE 
                    CASE 
                        WHEN array_length(question_tags, 1) > 0 THEN
                            LEAST(50, GREATEST(20, 
                                20 + (30 * (
                                    SELECT COUNT(*)::float / 
                                           (array_length(question_tags, 1) + 
                                            COALESCE(array_length(COALESCE(array_agg(DISTINCT pdf_tag.name) FILTER (WHERE pdf_tag.name IS NOT NULL), '{}'), 1), 0) -
                                            (SELECT COUNT(*) FROM unnest(question_tags) q_tag 
                                             WHERE q_tag = ANY(COALESCE(array_agg(DISTINCT pdf_tag.name) FILTER (WHERE pdf_tag.name IS NOT NULL), '{}')))
                                           )
                                    FROM unnest(question_tags) q_tag 
                                    WHERE q_tag = ANY(COALESCE(array_agg(DISTINCT pdf_tag.name) FILTER (WHERE pdf_tag.name IS NOT NULL), '{}'))
                                ))
                            ))
                        ELSE 0
                    END
            END as match_score,
            
            -- Generate match reasons
            ARRAY(
                SELECT reason FROM (
                    SELECT 'Module + Topic + Subtopic match' as reason, 1 as priority
                    WHERE p.module_id = question_module_id 
                          AND topic.name = ANY(question_topics) 
                          AND subtopic.name = ANY(question_subtopics)
                    UNION ALL
                    SELECT 'Module + Topic match' as reason, 2 as priority
                    WHERE p.module_id = question_module_id 
                          AND topic.name = ANY(question_topics)
                          AND NOT (topic.name = ANY(question_topics) AND subtopic.name = ANY(question_subtopics))
                    UNION ALL
                    SELECT 'Module match' as reason, 3 as priority
                    WHERE p.module_id = question_module_id
                          AND NOT topic.name = ANY(question_topics)
                    UNION ALL
                    SELECT format('Tag overlap (%s tags)', 
                           (SELECT COUNT(*) FROM unnest(question_tags) q_tag 
                            WHERE q_tag = ANY(COALESCE(array_agg(DISTINCT pdf_tag.name) FILTER (WHERE pdf_tag.name IS NOT NULL), '{}')))
                          ) as reason, 4 as priority
                    WHERE array_length(question_tags, 1) > 0
                          AND (SELECT COUNT(*) FROM unnest(question_tags) q_tag 
                               WHERE q_tag = ANY(COALESCE(array_agg(DISTINCT pdf_tag.name) FILTER (WHERE pdf_tag.name IS NOT NULL), '{}'))) > 0
                ) reasons ORDER BY priority
            ) as reasons
            
        FROM pdfs p
        LEFT JOIN modules m ON p.module_id = m.id
        LEFT JOIN topics topic ON p.topic_id = topic.id
        LEFT JOIN subtopics subtopic ON p.subtopic_id = subtopic.id
        LEFT JOIN pdf_tags pt ON p.id = pt.pdf_id
        LEFT JOIN tags pdf_tag ON pt.tag_id = pdf_tag.id
        WHERE p.is_active = true
        GROUP BY p.id, p.storage_path, p.original_filename, m.name, topic.name, subtopic.name, p.module_id
        HAVING 
            -- Module + Topic + Subtopic match
            (p.module_id = question_module_id AND topic.name = ANY(question_topics) AND subtopic.name = ANY(question_subtopics))
            OR
            -- Module + Topic match  
            (p.module_id = question_module_id AND topic.name = ANY(question_topics))
            OR
            -- Module match
            (p.module_id = question_module_id)
            OR
            -- Tag overlap
            (array_length(question_tags, 1) > 0 AND 
             (SELECT COUNT(*) FROM unnest(question_tags) q_tag 
              WHERE q_tag = ANY(COALESCE(array_agg(DISTINCT pdf_tag.name) FILTER (WHERE pdf_tag.name IS NOT NULL), '{}'))) > 0)
    )
    SELECT 
        ps.id,
        ps.storage_path,
        ps.original_filename,
        ps.module_name,
        ps.topic_name,
        ps.subtopic_name,
        ps.pdf_tags,
        ps.match_score,
        ps.reasons
    FROM pdf_scores ps
    WHERE ps.match_score > 0
    ORDER BY ps.match_score DESC, RANDOM()
    LIMIT max_pdfs_param;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_pdfs_for_question_v2(text, integer) IS 
'Optimized PDF matching function that returns relevant PDFs for a question with match scoring.
Uses storage bucket paths and supports comprehensive matching algorithm.';