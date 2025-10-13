-- Smart PDF Scoring System
-- Creates a more dynamic scoring system based on topic, subtopic, and tag matches
-- Module is assumed to always match (PDFs are filtered by module first)

CREATE OR REPLACE FUNCTION get_pdfs_for_question_v3(
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
    question_tags_raw text[];
    question_tags_split text[];
    question_topics_norm text[];
    question_subtopics_norm text[];
    question_tags_norm text[];
    weight_topic double precision := 30;
    weight_subtopic double precision := 50;
    weight_tags double precision := 20;
BEGIN
    -- Get question metadata
    SELECT 
        q.module_id,
        COALESCE(array_agg(DISTINCT t.name) FILTER (WHERE t.name IS NOT NULL), '{}'),
        COALESCE(array_agg(DISTINCT st.name) FILTER (WHERE st.name IS NOT NULL), '{}'),
        COALESCE(array_agg(DISTINCT tag.name) FILTER (WHERE tag.name IS NOT NULL), '{}')
    INTO question_module_id, question_topics, question_subtopics, question_tags_raw
    FROM questions q
    LEFT JOIN question_topics qt ON q.id = qt.question_id
    LEFT JOIN topics t ON qt.topic_id = t.id
    LEFT JOIN question_subtopics qst ON q.id = qst.question_id
    LEFT JOIN subtopics st ON qst.subtopic_id = st.id
    LEFT JOIN question_tags qtag ON q.id = qtag.question_id
    LEFT JOIN tags tag ON qtag.tag_id = tag.id
    WHERE q.id = question_id_param
    GROUP BY q.module_id;

    -- Split comma-separated tags and normalise the array
    SELECT array_agg(DISTINCT TRIM(split_tag))
    INTO question_tags_split
    FROM unnest(question_tags_raw) as tag_item,
         unnest(string_to_array(tag_item, ',')) as split_tag
    WHERE TRIM(split_tag) != '';

    question_topics := COALESCE(question_topics, ARRAY[]::text[]);
    question_subtopics := COALESCE(question_subtopics, ARRAY[]::text[]);
    question_tags_split := COALESCE(question_tags_split, ARRAY[]::text[]);

    -- Normalised lower-case arrays for case-insensitive matching
    SELECT array_agg(DISTINCT LOWER(item))
    INTO question_topics_norm
    FROM unnest(question_topics) AS item;

    SELECT array_agg(DISTINCT LOWER(item))
    INTO question_subtopics_norm
    FROM unnest(question_subtopics) AS item;

    SELECT array_agg(DISTINCT LOWER(item))
    INTO question_tags_norm
    FROM unnest(question_tags_split) AS item;

    question_topics_norm := COALESCE(question_topics_norm, ARRAY[]::text[]);
    question_subtopics_norm := COALESCE(question_subtopics_norm, ARRAY[]::text[]);
    question_tags_norm := COALESCE(question_tags_norm, ARRAY[]::text[]);

    IF question_module_id IS NULL THEN
        RETURN;
    END IF;

    -- Return matching PDFs with weighted scores
    RETURN QUERY
    WITH question_data AS (
        SELECT 
            question_module_id AS module_id,
            question_topics AS topics,
            question_subtopics AS subtopics,
            question_tags_split AS tags,
            question_topics_norm AS topics_norm,
            question_subtopics_norm AS subtopics_norm,
            question_tags_norm AS tags_norm,
            COALESCE(array_length(question_topics_norm, 1), 0) AS topic_count,
            COALESCE(array_length(question_subtopics_norm, 1), 0) AS subtopic_count,
            COALESCE(array_length(question_tags_norm, 1), 0) AS tag_count
    ),
    pdf_analysis AS (
        SELECT 
            p.id,
            p.storage_path,
            p.original_filename,
            m.name AS module_name,
            topic.name AS topic_name,
            subtopic.name AS subtopic_name,
            qd.topic_count,
            qd.subtopic_count,
            qd.tag_count,
            qd.topics,
            qd.subtopics,
            qd.tags,
            qd.topics_norm,
            qd.subtopics_norm,
            qd.tags_norm,
            COALESCE(array_agg(DISTINCT pdf_tag.name) FILTER (WHERE pdf_tag.name IS NOT NULL), '{}') AS pdf_tags,
            COALESCE(array_agg(DISTINCT LOWER(pdf_tag.name)) FILTER (WHERE pdf_tag.name IS NOT NULL), '{}') AS pdf_tags_norm,
            CASE 
                WHEN qd.topic_count > 0 AND topic.name IS NOT NULL THEN
                    (SELECT COUNT(*) FROM unnest(qd.topics_norm) q_topic WHERE q_topic = LOWER(topic.name))
                ELSE 0
            END AS topic_matches,
            CASE 
                WHEN qd.subtopic_count > 0 AND subtopic.name IS NOT NULL THEN
                    (SELECT COUNT(*) FROM unnest(qd.subtopics_norm) q_subtopic WHERE q_subtopic = LOWER(subtopic.name))
                ELSE 0
            END AS subtopic_matches,
            CASE 
                WHEN qd.tag_count > 0 THEN
                    (SELECT COUNT(*) FROM unnest(qd.tags_norm) q_tag 
                     WHERE q_tag = ANY(COALESCE(array_agg(DISTINCT LOWER(pdf_tag.name)) FILTER (WHERE pdf_tag.name IS NOT NULL), '{}')))
                ELSE 0
            END AS tag_matches
        FROM question_data qd
        JOIN pdfs p ON p.module_id = qd.module_id
        JOIN modules m ON p.module_id = m.id
        LEFT JOIN topics topic ON p.topic_id = topic.id
        LEFT JOIN subtopics subtopic ON p.subtopic_id = subtopic.id
        LEFT JOIN pdf_tags pt ON p.id = pt.pdf_id
        LEFT JOIN tags pdf_tag ON pt.tag_id = pdf_tag.id
        WHERE p.is_active = true
    GROUP BY p.id, p.storage_path, p.original_filename, m.name, topic.name, subtopic.name,
         qd.topic_count, qd.subtopic_count, qd.tag_count, qd.topics, qd.subtopics, qd.tags,
         qd.topics_norm, qd.subtopics_norm, qd.tags_norm
    ),
    scored_pdfs AS (
        SELECT 
            pa.*,
            CASE WHEN pa.topic_count > 0 THEN weight_topic ELSE 0 END AS topic_weight_available,
            CASE WHEN pa.subtopic_count > 0 THEN weight_subtopic ELSE 0 END AS subtopic_weight_available,
            CASE WHEN pa.tag_count > 0 THEN weight_tags ELSE 0 END AS tag_weight_available,
            CASE 
                WHEN pa.topic_count > 0 THEN weight_topic * LEAST(pa.topic_matches::double precision / NULLIF(pa.topic_count, 0), 1)
                ELSE 0
            END AS topic_weight_earned,
            CASE 
                WHEN pa.subtopic_count > 0 THEN weight_subtopic * LEAST(pa.subtopic_matches::double precision / NULLIF(pa.subtopic_count, 0), 1)
                ELSE 0
            END AS subtopic_weight_earned,
            CASE 
                WHEN pa.tag_count > 0 THEN weight_tags * LEAST(pa.tag_matches::double precision / NULLIF(pa.tag_count, 0), 1)
                ELSE 0
            END AS tag_weight_earned
        FROM pdf_analysis pa
    ),
    final_scores AS (
        SELECT 
            sp.*,
            (sp.topic_weight_available + sp.subtopic_weight_available + sp.tag_weight_available) AS available_weight,
            (sp.topic_weight_earned + sp.subtopic_weight_earned + sp.tag_weight_earned) AS earned_weight
        FROM scored_pdfs sp
    )
    SELECT 
        fs.id AS pdf_id,
        fs.storage_path,
        fs.original_filename,
        fs.module_name,
        fs.topic_name,
        fs.subtopic_name,
        fs.pdf_tags AS tags,
        CASE 
            WHEN fs.available_weight > 0 THEN ROUND(((fs.earned_weight / fs.available_weight) * 100)::numeric, 2)::double precision
            ELSE 0::double precision
        END AS match_percent,
        COALESCE(
            ARRAY_REMOVE(ARRAY[
                CASE WHEN fs.topic_count > 0 AND fs.topic_matches > 0 THEN 
                    format('Topic overlap (%s%%)', ROUND((LEAST(fs.topic_matches::double precision / NULLIF(fs.topic_count, 0), 1) * 100)::numeric))
                END,
                CASE WHEN fs.subtopic_count > 0 AND fs.subtopic_matches > 0 THEN 
                    format('Subtopic overlap (%s%%)', ROUND((LEAST(fs.subtopic_matches::double precision / NULLIF(fs.subtopic_count, 0), 1) * 100)::numeric))
                END,
                CASE WHEN fs.tag_count > 0 AND fs.tag_matches > 0 THEN 
                    format('Tag overlap (%s/%s)', fs.tag_matches, fs.tag_count)
                END
            ], NULL), ARRAY[]::text[]
        ) AS match_reasons
    FROM final_scores fs
    WHERE (
        fs.available_weight > 0 AND fs.earned_weight > 0
    )
    ORDER BY match_percent DESC, original_filename
    LIMIT max_pdfs_param;

END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_pdfs_for_question_v3(text, integer) IS 
'Weighted PDF matching across subtopics, topics, and tags. Returns a 0-100 score based on proportional overlap of available metadata, with subtopics weighted most heavily.';

-- Update the existing RPC to use the new version
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
BEGIN
    -- Delegate to the new enhanced version
    RETURN QUERY SELECT * FROM get_pdfs_for_question_v3(question_id_param, max_pdfs_param);
END;
$$ LANGUAGE plpgsql;
