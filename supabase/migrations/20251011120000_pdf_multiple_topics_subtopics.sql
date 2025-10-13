-- PDF Multiple Topics and Subtopics Migration
-- This migration adds support for multiple topics and subtopics per PDF
-- by creating junction tables similar to question_topics and question_subtopics

-- Create junction tables for PDF topics and subtopics
CREATE TABLE pdf_topics (
    pdf_id integer NOT NULL,
    topic_id integer NOT NULL,
    CONSTRAINT pdf_topics_pkey PRIMARY KEY (pdf_id, topic_id),
    CONSTRAINT pdf_topics_pdf_id_fkey FOREIGN KEY (pdf_id) REFERENCES pdfs(id) ON DELETE CASCADE,
    CONSTRAINT pdf_topics_topic_id_fkey FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
);

CREATE TABLE pdf_subtopics (
    pdf_id integer NOT NULL,
    subtopic_id integer NOT NULL,
    CONSTRAINT pdf_subtopics_pkey PRIMARY KEY (pdf_id, subtopic_id),
    CONSTRAINT pdf_subtopics_pdf_id_fkey FOREIGN KEY (pdf_id) REFERENCES pdfs(id) ON DELETE CASCADE,
    CONSTRAINT pdf_subtopics_subtopic_id_fkey FOREIGN KEY (subtopic_id) REFERENCES subtopics(id) ON DELETE CASCADE
);

-- Migrate existing data from pdfs table to junction tables
INSERT INTO pdf_topics (pdf_id, topic_id)
SELECT id, topic_id 
FROM pdfs 
WHERE topic_id IS NOT NULL;

INSERT INTO pdf_subtopics (pdf_id, subtopic_id)
SELECT id, subtopic_id 
FROM pdfs 
WHERE subtopic_id IS NOT NULL;

-- Drop the old foreign key constraints
ALTER TABLE pdfs DROP CONSTRAINT IF EXISTS pdfs_topic_id_fkey;
ALTER TABLE pdfs DROP CONSTRAINT IF EXISTS pdfs_subtopic_id_fkey;

-- Remove the old columns
ALTER TABLE pdfs DROP COLUMN IF EXISTS topic_id;
ALTER TABLE pdfs DROP COLUMN IF EXISTS subtopic_id;

-- Add indexes for better performance
CREATE INDEX idx_pdf_topics_pdf_id ON pdf_topics(pdf_id);
CREATE INDEX idx_pdf_topics_topic_id ON pdf_topics(topic_id);
CREATE INDEX idx_pdf_subtopics_pdf_id ON pdf_subtopics(pdf_id);
CREATE INDEX idx_pdf_subtopics_subtopic_id ON pdf_subtopics(subtopic_id);

-- Drop the existing RPC function first to avoid return type conflicts
DROP FUNCTION IF EXISTS get_pdfs_for_question_v3(text, integer);

-- Update the existing RPC function to handle multiple topics and subtopics
CREATE OR REPLACE FUNCTION get_pdfs_for_question_v3(
    question_id_param text,
    max_pdfs_param integer DEFAULT 3
) RETURNS TABLE (
    pdf_id integer,
    storage_path text,
    original_filename text,
    module_name text,
    topic_names text[],
    subtopic_names text[],
    tags text[],
    match_percent double precision,
    match_reasons text[]
) AS $$
DECLARE
    question_module_id integer;
    question_topics text[];
    question_subtopics text[];
    question_tags text[];
    question_tag_count integer := 0;
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

    question_tag_count := COALESCE(array_length(question_tags, 1), 0);

    -- Return matching PDFs with weighted scores
    RETURN QUERY
    WITH pdf_metadata AS (
        SELECT 
            p.id,
            p.storage_path,
            p.original_filename,
            m.name as module_name,
            COALESCE(array_agg(DISTINCT pt_topic.name) FILTER (WHERE pt_topic.name IS NOT NULL), '{}') as pdf_topic_names,
            COALESCE(array_agg(DISTINCT pst_subtopic.name) FILTER (WHERE pst_subtopic.name IS NOT NULL), '{}') as pdf_subtopic_names,
            COALESCE(array_agg(DISTINCT pdf_tag.name) FILTER (WHERE pdf_tag.name IS NOT NULL), '{}') as pdf_tags
        FROM pdfs p
        INNER JOIN modules m ON p.module_id = m.id
        LEFT JOIN pdf_topics pt ON p.id = pt.pdf_id
        LEFT JOIN topics pt_topic ON pt.topic_id = pt_topic.id
        LEFT JOIN pdf_subtopics pst ON p.id = pst.pdf_id
        LEFT JOIN subtopics pst_subtopic ON pst.subtopic_id = pst_subtopic.id
        LEFT JOIN pdf_tags ptag ON p.id = ptag.pdf_id
        LEFT JOIN tags pdf_tag ON ptag.tag_id = pdf_tag.id
        WHERE p.is_active = true
          AND p.module_id = question_module_id
        GROUP BY p.id, p.storage_path, p.original_filename, m.name
    ),
    scored_pdfs AS (
        SELECT 
            pm.id,
            pm.storage_path,
            pm.original_filename,
            pm.module_name,
            pm.pdf_topic_names,
            pm.pdf_subtopic_names,
            pm.pdf_tags,
            matches.matching_topics,
            matches.matching_subtopics,
            matches.matching_tags,
            CASE
                WHEN array_length(matches.matching_topics, 1) > 0
                     AND array_length(matches.matching_subtopics, 1) > 0
                     AND (question_tag_count = 0 OR array_length(matches.matching_tags, 1) = question_tag_count)
                THEN 100::double precision
                ELSE (
                    (CASE WHEN array_length(matches.matching_subtopics, 1) > 0 THEN 45 ELSE 0 END) +
                    (CASE WHEN array_length(matches.matching_topics, 1) > 0 THEN 35 ELSE 0 END) +
                    (CASE 
                         WHEN question_tag_count = 0 THEN 20
                         ELSE ROUND(LEAST(1, COALESCE(array_length(matches.matching_tags, 1)::numeric / NULLIF(question_tag_count, 0), 0)) * 20, 2)
                     END)
                )::double precision
            END AS match_percent
        FROM pdf_metadata pm
        CROSS JOIN LATERAL (
            SELECT 
                COALESCE(ARRAY(
                    SELECT DISTINCT topic
                    FROM unnest(pm.pdf_topic_names) AS topic
                    WHERE question_topics IS NOT NULL AND topic = ANY(question_topics)
                ), ARRAY[]::text[]) AS matching_topics,
                COALESCE(ARRAY(
                    SELECT DISTINCT subtopic
                    FROM unnest(pm.pdf_subtopic_names) AS subtopic
                    WHERE question_subtopics IS NOT NULL AND subtopic = ANY(question_subtopics)
                ), ARRAY[]::text[]) AS matching_subtopics,
                COALESCE(ARRAY(
                    SELECT DISTINCT tag
                    FROM unnest(pm.pdf_tags) AS tag
                    WHERE question_tags IS NOT NULL AND tag = ANY(question_tags)
                ), ARRAY[]::text[]) AS matching_tags
        ) matches
    )
    SELECT 
        sp.id,
        sp.storage_path,
        sp.original_filename,
        sp.module_name,
        sp.pdf_topic_names,
        sp.pdf_subtopic_names,
        sp.pdf_tags,
        sp.match_percent,
        ARRAY_REMOVE(ARRAY[
            CASE WHEN array_length(sp.matching_subtopics, 1) > 0 THEN 'Subtopics matched: ' || array_to_string(sp.matching_subtopics, ', ') ELSE NULL END,
            CASE WHEN array_length(sp.matching_topics, 1) > 0 THEN 'Topics matched: ' || array_to_string(sp.matching_topics, ', ') ELSE NULL END,
            CASE WHEN array_length(sp.matching_tags, 1) > 0 THEN 'Tags matched: ' || array_to_string(sp.matching_tags, ', ') ||
                CASE WHEN question_tag_count > 0 THEN format(' (%s/%s)', array_length(sp.matching_tags, 1), question_tag_count) ELSE '' END
            ELSE NULL END
        ], NULL) AS match_reasons
    FROM scored_pdfs sp
    WHERE sp.match_percent > 0
    ORDER BY sp.match_percent DESC, sp.original_filename
    LIMIT max_pdfs_param;
END;
$$ LANGUAGE plpgsql;

-- Create a helper RPC function to upsert PDFs with multiple topics/subtopics
CREATE OR REPLACE FUNCTION upsert_pdf_with_metadata(
    storage_path_param text,
    original_filename_param text,
    module_id_param integer,
    topic_ids_param integer[] DEFAULT NULL,
    subtopic_ids_param integer[] DEFAULT NULL,
    tag_ids_param integer[] DEFAULT NULL,
    uploaded_by_param text DEFAULT NULL,
    metadata_param jsonb DEFAULT '{}'::jsonb,
    file_size_param bigint DEFAULT NULL,
    mime_type_param text DEFAULT 'application/pdf'
) RETURNS TABLE (
    success boolean,
    pdf_id integer,
    message text
) AS $$
DECLARE
    existing_pdf_id integer;
    new_pdf_id integer;
    topic_id integer;
    subtopic_id integer;
    tag_id integer;
BEGIN
    -- Check for existing PDF with same filename and module
    SELECT id INTO existing_pdf_id
    FROM pdfs 
    WHERE original_filename = original_filename_param 
      AND module_id = module_id_param 
      AND is_active = true;
    
    IF existing_pdf_id IS NOT NULL THEN
        -- Update existing PDF
        UPDATE pdfs SET
            storage_path = storage_path_param,
            file_size = COALESCE(file_size_param, file_size),
            mime_type = COALESCE(mime_type_param, mime_type),
            metadata = metadata_param,
            uploaded_by = COALESCE(uploaded_by_param, uploaded_by)
        WHERE id = existing_pdf_id;
        
        new_pdf_id := existing_pdf_id;
        
        -- Clear existing associations
        DELETE FROM pdf_topics WHERE pdf_id = existing_pdf_id;
        DELETE FROM pdf_subtopics WHERE pdf_id = existing_pdf_id;
        DELETE FROM pdf_tags WHERE pdf_id = existing_pdf_id;
        
    ELSE
        -- Insert new PDF
        INSERT INTO pdfs (
            storage_path, original_filename, module_id, file_size, 
            mime_type, uploaded_by, metadata, is_active
        ) VALUES (
            storage_path_param, original_filename_param, module_id_param, 
            file_size_param, mime_type_param, uploaded_by_param, metadata_param, true
        ) RETURNING id INTO new_pdf_id;
    END IF;
    
    -- Insert topic associations
    IF topic_ids_param IS NOT NULL THEN
        FOREACH topic_id IN ARRAY topic_ids_param
        LOOP
            INSERT INTO pdf_topics (pdf_id, topic_id) 
            VALUES (new_pdf_id, topic_id)
            ON CONFLICT DO NOTHING;
        END LOOP;
    END IF;
    
    -- Insert subtopic associations
    IF subtopic_ids_param IS NOT NULL THEN
        FOREACH subtopic_id IN ARRAY subtopic_ids_param
        LOOP
            INSERT INTO pdf_subtopics (pdf_id, subtopic_id) 
            VALUES (new_pdf_id, subtopic_id)
            ON CONFLICT DO NOTHING;
        END LOOP;
    END IF;
    
    -- Insert tag associations
    IF tag_ids_param IS NOT NULL THEN
        FOREACH tag_id IN ARRAY tag_ids_param
        LOOP
            INSERT INTO pdf_tags (pdf_id, tag_id, count) 
            VALUES (new_pdf_id, tag_id, 1)
            ON CONFLICT (pdf_id, tag_id) DO UPDATE SET count = pdf_tags.count + 1;
        END LOOP;
    END IF;
    
    RETURN QUERY SELECT 
        true as success, 
        new_pdf_id as pdf_id, 
        CASE 
            WHEN existing_pdf_id IS NOT NULL THEN 'PDF updated successfully'
            ELSE 'PDF created successfully'
        END as message;
        
EXCEPTION WHEN OTHERS THEN
    RETURN QUERY SELECT 
        false as success, 
        NULL::integer as pdf_id, 
        SQLERRM as message;
END;
$$ LANGUAGE plpgsql;