-- RPC Function Optimization: get_random_question_with_distractors
-- This migration adds a comprehensive RPC function to fetch a random question
-- along with its metadata, manual distractors, and smart distractors in a single call.

CREATE OR REPLACE FUNCTION get_random_question_with_distractors(
    module_id_param INTEGER,
    topic_names_param TEXT[] DEFAULT NULL,
    subtopic_names_param TEXT[] DEFAULT NULL,
    tag_names_param TEXT[] DEFAULT NULL,
    specific_question_id_param TEXT DEFAULT NULL,
    distractor_limit_param INTEGER DEFAULT 4
) RETURNS TABLE (
    question_data JSON,
    distractors JSON
) AS $$
DECLARE
    selected_question RECORD;
    manual_distractors JSON;
    smart_distractors JSON;
    topic_list TEXT[];
    subtopic_list TEXT[];
    tag_list TEXT[];
    
    -- Variables for smart distractor calculation
    current_similarity_scores RECORD;
BEGIN
    -- 1. Select a random question based on filters
    SELECT 
        q.id,
        q.question,
        q.answer,
        q.module_id
    INTO selected_question
    FROM questions q
    LEFT JOIN question_topics qt ON q.id = qt.question_id
    LEFT JOIN topics t ON qt.topic_id = t.id
    LEFT JOIN question_subtopics qst ON q.id = qst.question_id
    LEFT JOIN subtopics st ON qst.subtopic_id = st.id
    LEFT JOIN question_tags qtag ON q.id = qtag.question_id
    LEFT JOIN tags tag ON qtag.tag_id = tag.id
    WHERE q.module_id = module_id_param
    -- Optional specific question ID override
    AND (
        specific_question_id_param IS NULL 
        OR q.id = specific_question_id_param
    )
    -- Filter by topics
    AND (
        topic_names_param IS NULL 
        OR array_length(topic_names_param, 1) IS NULL
        OR t.name = ANY(topic_names_param)
    )
    -- Filter by subtopics
    AND (
        subtopic_names_param IS NULL
        OR array_length(subtopic_names_param, 1) IS NULL
        OR st.name = ANY(subtopic_names_param)
    )
    -- Filter by tags
    AND (
        tag_names_param IS NULL
        OR array_length(tag_names_param, 1) IS NULL
        OR tag.name = ANY(tag_names_param)
    )
    ORDER BY RANDOM()
    LIMIT 1;
    
    -- If no question found, return empty
    IF selected_question.id IS NULL THEN
        RETURN;
    END IF;

    -- 2. Get metadata for this question
    -- Topics
    SELECT ARRAY_AGG(DISTINCT t.name) INTO topic_list
    FROM question_topics qt
    JOIN topics t ON qt.topic_id = t.id
    WHERE qt.question_id = selected_question.id;
    
    -- Subtopics
    SELECT ARRAY_AGG(DISTINCT st.name) INTO subtopic_list
    FROM question_subtopics qst
    JOIN subtopics st ON qst.subtopic_id = st.id
    WHERE qst.question_id = selected_question.id;
    
    -- Tags
    SELECT ARRAY_AGG(DISTINCT tag.name) INTO tag_list
    FROM question_tags qtag
    JOIN tags tag ON qtag.tag_id = tag.id
    WHERE qtag.question_id = selected_question.id;

    -- 3. Get manual distractors
    SELECT JSON_AGG(json_build_object(
        'id', md.id,
        'answer', md.distractor_text,
        'type', 'manual_distractor'
    )) INTO manual_distractors
    FROM manual_distractors md
    WHERE md.question_id = selected_question.id;

    -- 4. Get smart distractors (if needed)
    -- We'll calculate how many smart distractors we need
    -- total_needed = distractor_limit_param - (number of manual distractors)
    -- Note: We fetch more than we technically need to ensure variety, handled mostly in SQL
    
    -- Reuse logic from get_smart_distractors but integrated here
    SELECT JSON_AGG(sd) INTO smart_distractors
    FROM (
        SELECT 
            q.id,
            q.answer,
            'question' as type,
            (
                -- Topic overlap: 3 points
                (SELECT COUNT(*) FROM unnest(COALESCE(topic_list, '{}'::text[])) ct 
                 WHERE ct = ANY(COALESCE(array_agg(DISTINCT t.name) FILTER (WHERE t.name IS NOT NULL), '{}'))) * 3 +
                -- Subtopic overlap: 2 points
                (SELECT COUNT(*) FROM unnest(COALESCE(subtopic_list, '{}'::text[])) cs 
                 WHERE cs = ANY(COALESCE(array_agg(DISTINCT st.name) FILTER (WHERE st.name IS NOT NULL), '{}'))) * 2 +
                -- Tag overlap: 1 point
                (SELECT COUNT(*) FROM unnest(COALESCE(tag_list, '{}'::text[])) ctag 
                 WHERE ctag = ANY(COALESCE(array_agg(DISTINCT tag.name) FILTER (WHERE tag.name IS NOT NULL), '{}'))) * 1 +
                 -- Bonus points
                CASE WHEN EXISTS(SELECT 1 FROM unnest(COALESCE(topic_list, '{}'::text[])) ct 
                               WHERE ct = ANY(COALESCE(array_agg(DISTINCT t.name) FILTER (WHERE t.name IS NOT NULL), '{}'))) 
                     THEN 2 ELSE 0 END
            )::INTEGER as similarity_score
        FROM questions q
        LEFT JOIN question_topics qt ON q.id = qt.question_id
        LEFT JOIN topics t ON qt.topic_id = t.id
        LEFT JOIN question_subtopics qst ON q.id = qst.question_id
        LEFT JOIN subtopics st ON qst.subtopic_id = st.id
        LEFT JOIN question_tags qtag ON q.id = qtag.question_id
        LEFT JOIN tags tag ON qtag.tag_id = tag.id
        WHERE q.module_id = module_id_param
        AND q.id != selected_question.id
        AND q.answer IS NOT NULL
        AND q.answer != ''
        GROUP BY q.id, q.answer
        ORDER BY similarity_score DESC, RANDOM()
        LIMIT distractor_limit_param -- Get enough candidates
    ) sd;

    -- 5. Construct Result
    RETURN QUERY SELECT 
        json_build_object(
            'id', selected_question.id,
            'question', selected_question.question,
            'answer', selected_question.answer,
            'module_id', selected_question.module_id,
            'topics', COALESCE(topic_list, '{}'::text[]),
            'subtopics', COALESCE(subtopic_list, '{}'::text[]),
            'tags', COALESCE(tag_list, '{}'::text[])
        ) as question_data,
        json_build_object(
            'manual_distractors', COALESCE(manual_distractors, '[]'::json),
            'smart_distractors', COALESCE(smart_distractors, '[]'::json)
        ) as distractors;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_random_question_with_distractors(INTEGER, TEXT[], TEXT[], TEXT[], TEXT, INTEGER) IS 
'Fetches a random question with all associated metadata and distractors in a single RPC call. 
Replaces 4-5 sequential API calls for significant latency reduction.';
