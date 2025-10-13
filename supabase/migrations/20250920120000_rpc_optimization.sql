-- RPC Functions Optimization Migration
-- This migration adds optimized RPC functions to replace N+1 query patterns
-- Expected performance improvement: 70-80% reduction in database calls

-- 1. get_module_filter_data - Replace inefficient filter loading
-- Replaces 6-12 separate queries with single optimized query
CREATE OR REPLACE FUNCTION get_module_filter_data(
    module_name_param TEXT,
    selected_topics_param TEXT[] DEFAULT NULL
) RETURNS TABLE (
    filter_type TEXT,
    name TEXT,
    count BIGINT
) AS $$
DECLARE
    module_id_var INTEGER;
    topic_question_ids TEXT[];
BEGIN
    -- Get module ID
    SELECT m.id INTO module_id_var FROM modules m WHERE m.name = module_name_param;
    
    IF module_id_var IS NULL THEN
        RETURN;
    END IF;
    
    -- If no topics selected, return all filter options for module
    IF selected_topics_param IS NULL OR array_length(selected_topics_param, 1) IS NULL THEN
        -- Get topics with counts
        RETURN QUERY
        SELECT 
            'topic'::TEXT as filter_type,
            t.name,
            COUNT(DISTINCT q.id) as count
        FROM topics t
        JOIN question_topics qt ON t.id = qt.topic_id
        JOIN questions q ON qt.question_id = q.id
        WHERE q.module_id = module_id_var
        GROUP BY t.id, t.name
        ORDER BY t.name;
        
        -- Get subtopics with counts
        RETURN QUERY
        SELECT 
            'subtopic'::TEXT as filter_type,
            st.name,
            COUNT(DISTINCT q.id) as count
        FROM subtopics st
        JOIN question_subtopics qst ON st.id = qst.subtopic_id
        JOIN questions q ON qst.question_id = q.id
        WHERE q.module_id = module_id_var
        GROUP BY st.id, st.name
        ORDER BY st.name;
        
        -- Get tags with counts
        RETURN QUERY
        SELECT 
            'tag'::TEXT as filter_type,
            tag.name,
            COUNT(DISTINCT q.id) as count
        FROM tags tag
        JOIN question_tags qtag ON tag.id = qtag.tag_id
        JOIN questions q ON qtag.question_id = q.id
        WHERE q.module_id = module_id_var
        GROUP BY tag.id, tag.name
        ORDER BY tag.name;
    ELSE
        -- Filter subtopics and tags based on selected topics
        -- Get question IDs for selected topics
        SELECT ARRAY_AGG(DISTINCT qt.question_id) INTO topic_question_ids
        FROM question_topics qt
        JOIN topics t ON qt.topic_id = t.id
        JOIN questions q ON qt.question_id = q.id
        WHERE t.name = ANY(selected_topics_param)
        AND q.module_id = module_id_var;
        
        -- Return all topics (for consistency)
        RETURN QUERY
        SELECT 
            'topic'::TEXT as filter_type,
            t.name,
            COUNT(DISTINCT q.id) as count
        FROM topics t
        JOIN question_topics qt ON t.id = qt.topic_id
        JOIN questions q ON qt.question_id = q.id
        WHERE q.module_id = module_id_var
        GROUP BY t.id, t.name
        ORDER BY t.name;
        
        -- Return filtered subtopics
        IF topic_question_ids IS NOT NULL THEN
            RETURN QUERY
            SELECT 
                'subtopic'::TEXT as filter_type,
                st.name,
                COUNT(DISTINCT qst.question_id) as count
            FROM subtopics st
            JOIN question_subtopics qst ON st.id = qst.subtopic_id
            WHERE qst.question_id = ANY(topic_question_ids)
            GROUP BY st.id, st.name
            ORDER BY st.name;
            
            -- Return filtered tags
            RETURN QUERY
            SELECT 
                'tag'::TEXT as filter_type,
                tag.name,
                COUNT(DISTINCT qtag.question_id) as count
            FROM tags tag
            JOIN question_tags qtag ON tag.id = qtag.tag_id
            WHERE qtag.question_id = ANY(topic_question_ids)
            GROUP BY tag.id, tag.name
            ORDER BY tag.name;
        END IF;
    END IF;
END;
$$ LANGUAGE plpgsql;

-- 2. get_filtered_questions - Replace sequential filtering logic
-- Replaces O(n) queries with single compound query
CREATE OR REPLACE FUNCTION get_filtered_questions(
    module_id_param INTEGER,
    topic_names_param TEXT[] DEFAULT NULL,
    subtopic_names_param TEXT[] DEFAULT NULL,
    tag_names_param TEXT[] DEFAULT NULL
) RETURNS TABLE (
    id TEXT,
    question TEXT,
    answer TEXT,
    module_id INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT DISTINCT
        q.id,
        q.question,
        q.answer,
        q.module_id
    FROM questions q
    LEFT JOIN question_topics qt ON q.id = qt.question_id
    LEFT JOIN topics t ON qt.topic_id = t.id
    LEFT JOIN question_subtopics qst ON q.id = qst.question_id
    LEFT JOIN subtopics st ON qst.subtopic_id = st.id
    LEFT JOIN question_tags qtag ON q.id = qtag.question_id
    LEFT JOIN tags tag ON qtag.tag_id = tag.id
    WHERE q.module_id = module_id_param
    AND (
        topic_names_param IS NULL 
        OR array_length(topic_names_param, 1) IS NULL
        OR t.name = ANY(topic_names_param)
    )
    AND (
        subtopic_names_param IS NULL
        OR array_length(subtopic_names_param, 1) IS NULL
        OR st.name = ANY(subtopic_names_param)
    )
    AND (
        tag_names_param IS NULL
        OR array_length(tag_names_param, 1) IS NULL
        OR tag.name = ANY(tag_names_param)
    );
END;
$$ LANGUAGE plpgsql;

-- 3. get_smart_distractors - Replace client-side distractor scoring
-- Replaces fetching all questions + client-side scoring with database-computed similarity
CREATE OR REPLACE FUNCTION get_smart_distractors(
    question_id_param TEXT,
    limit_param INTEGER DEFAULT 3
) RETURNS TABLE (
    distractor_id TEXT,
    distractor_answer TEXT,
    similarity_score INTEGER
) AS $$
DECLARE
    current_module_id INTEGER;
    current_topics TEXT[];
    current_subtopics TEXT[];
    current_tags TEXT[];
BEGIN
    -- Get current question's module and metadata
    SELECT 
        q.module_id,
        COALESCE(array_agg(DISTINCT t.name) FILTER (WHERE t.name IS NOT NULL), '{}'),
        COALESCE(array_agg(DISTINCT st.name) FILTER (WHERE st.name IS NOT NULL), '{}'),
        COALESCE(array_agg(DISTINCT tag.name) FILTER (WHERE tag.name IS NOT NULL), '{}')
    INTO current_module_id, current_topics, current_subtopics, current_tags
    FROM questions q
    LEFT JOIN question_topics qt ON q.id = qt.question_id
    LEFT JOIN topics t ON qt.topic_id = t.id
    LEFT JOIN question_subtopics qst ON q.id = qst.question_id
    LEFT JOIN subtopics st ON qst.subtopic_id = st.id
    LEFT JOIN question_tags qtag ON q.id = qtag.question_id
    LEFT JOIN tags tag ON qtag.tag_id = tag.id
    WHERE q.id = question_id_param
    GROUP BY q.id, q.module_id;
    
    IF current_module_id IS NULL THEN
        RETURN;
    END IF;
    
    -- Calculate similarity scores for other questions in the same module
    RETURN QUERY
    SELECT 
        q.id,
        q.answer,
        (
            -- Topic overlap: 3 points per shared topic
            (SELECT COUNT(*) FROM unnest(current_topics) ct 
             WHERE ct = ANY(COALESCE(array_agg(DISTINCT t.name) FILTER (WHERE t.name IS NOT NULL), '{}'))) * 3 +
            -- Subtopic overlap: 2 points per shared subtopic
            (SELECT COUNT(*) FROM unnest(current_subtopics) cs 
             WHERE cs = ANY(COALESCE(array_agg(DISTINCT st.name) FILTER (WHERE st.name IS NOT NULL), '{}'))) * 2 +
            -- Tag overlap: 1 point per shared tag
            (SELECT COUNT(*) FROM unnest(current_tags) ctag 
             WHERE ctag = ANY(COALESCE(array_agg(DISTINCT tag.name) FILTER (WHERE tag.name IS NOT NULL), '{}'))) * 1 +
            -- Bonus points for having any overlap
            CASE WHEN EXISTS(SELECT 1 FROM unnest(current_topics) ct 
                           WHERE ct = ANY(COALESCE(array_agg(DISTINCT t.name) FILTER (WHERE t.name IS NOT NULL), '{}'))) 
                 THEN 2 ELSE 0 END +
            CASE WHEN EXISTS(SELECT 1 FROM unnest(current_subtopics) cs 
                           WHERE cs = ANY(COALESCE(array_agg(DISTINCT st.name) FILTER (WHERE st.name IS NOT NULL), '{}'))) 
                 THEN 1 ELSE 0 END
        )::INTEGER as similarity_score
    FROM questions q
    LEFT JOIN question_topics qt ON q.id = qt.question_id
    LEFT JOIN topics t ON qt.topic_id = t.id
    LEFT JOIN question_subtopics qst ON q.id = qst.question_id
    LEFT JOIN subtopics st ON qst.subtopic_id = st.id
    LEFT JOIN question_tags qtag ON q.id = qtag.question_id
    LEFT JOIN tags tag ON qtag.tag_id = tag.id
    WHERE q.module_id = current_module_id
    AND q.id != question_id_param
    AND q.answer IS NOT NULL
    AND q.answer != ''
    GROUP BY q.id, q.answer
    ORDER BY similarity_score DESC, RANDOM()
    LIMIT limit_param;
END;
$$ LANGUAGE plpgsql;

-- 4. get_topic_suggestions - Optimize API suggestion endpoints
-- Replaces complex nested queries with single optimized query
CREATE OR REPLACE FUNCTION get_topic_suggestions(
    module_name_param TEXT,
    query_param TEXT DEFAULT NULL,
    limit_param INTEGER DEFAULT 10
) RETURNS TABLE (
    name TEXT,
    count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        t.name,
        COUNT(DISTINCT q.id) as count
    FROM topics t
    JOIN question_topics qt ON t.id = qt.topic_id
    JOIN questions q ON qt.question_id = q.id
    JOIN modules m ON q.module_id = m.id
    WHERE m.name = module_name_param
    AND (
        query_param IS NULL 
        OR query_param = ''
        OR t.name ILIKE '%' || query_param || '%'
    )
    GROUP BY t.id, t.name
    ORDER BY count DESC, t.name
    LIMIT limit_param;
END;
$$ LANGUAGE plpgsql;

-- 5. get_subtopic_suggestions - Optimize subtopic suggestions
CREATE OR REPLACE FUNCTION get_subtopic_suggestions(
    module_name_param TEXT,
    topic_name_param TEXT DEFAULT NULL,
    query_param TEXT DEFAULT NULL,
    limit_param INTEGER DEFAULT 10
) RETURNS TABLE (
    name TEXT,
    count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        st.name,
        COUNT(DISTINCT q.id) as count
    FROM subtopics st
    JOIN question_subtopics qst ON st.id = qst.subtopic_id
    JOIN questions q ON qst.question_id = q.id
    JOIN modules m ON q.module_id = m.id
    LEFT JOIN question_topics qt ON q.id = qt.question_id
    LEFT JOIN topics t ON qt.topic_id = t.id
    WHERE m.name = module_name_param
    AND (
        topic_name_param IS NULL 
        OR topic_name_param = ''
        OR t.name = topic_name_param
    )
    AND (
        query_param IS NULL 
        OR query_param = ''
        OR st.name ILIKE '%' || query_param || '%'
    )
    GROUP BY st.id, st.name
    ORDER BY count DESC, st.name
    LIMIT limit_param;
END;
$$ LANGUAGE plpgsql;

-- 6. get_tag_suggestions - Optimize tag suggestions
CREATE OR REPLACE FUNCTION get_tag_suggestions(
    module_name_param TEXT,
    query_param TEXT DEFAULT NULL,
    limit_param INTEGER DEFAULT 10
) RETURNS TABLE (
    name TEXT,
    count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        tag.name,
        COUNT(DISTINCT q.id) as count
    FROM tags tag
    JOIN question_tags qtag ON tag.id = qtag.tag_id
    JOIN questions q ON qtag.question_id = q.id
    JOIN modules m ON q.module_id = m.id
    WHERE m.name = module_name_param
    AND (
        query_param IS NULL 
        OR query_param = ''
        OR tag.name ILIKE '%' || query_param || '%'
    )
    GROUP BY tag.id, tag.name
    ORDER BY count DESC, tag.name
    LIMIT limit_param;
END;
$$ LANGUAGE plpgsql;

-- Add performance indexes for RPC function optimization
CREATE INDEX IF NOT EXISTS idx_question_topics_performance 
ON question_topics (topic_id, question_id);

CREATE INDEX IF NOT EXISTS idx_question_subtopics_performance 
ON question_subtopics (subtopic_id, question_id);

CREATE INDEX IF NOT EXISTS idx_question_tags_performance 
ON question_tags (tag_id, question_id);

CREATE INDEX IF NOT EXISTS idx_questions_module_performance 
ON questions (module_id, id);

CREATE INDEX IF NOT EXISTS idx_topics_name_performance 
ON topics (name);

CREATE INDEX IF NOT EXISTS idx_subtopics_name_performance 
ON subtopics (name);

CREATE INDEX IF NOT EXISTS idx_tags_name_performance 
ON tags (name);

-- Add comprehensive documentation
COMMENT ON FUNCTION get_module_filter_data(TEXT, TEXT[]) IS 
'Optimized filter data retrieval. Replaces 6-12 separate queries with single compound query. 
Returns topics, subtopics, and tags with counts, optionally filtered by selected topics.';

COMMENT ON FUNCTION get_filtered_questions(INTEGER, TEXT[], TEXT[], TEXT[]) IS 
'Optimized question filtering with compound WHERE conditions. Replaces O(n) queries with single query.
Supports filtering by topics, subtopics, and tags simultaneously.';

COMMENT ON FUNCTION get_smart_distractors(TEXT, INTEGER) IS 
'Database-computed distractor similarity scoring. Replaces client-side scoring of all module questions.
Calculates similarity based on topic (3pts), subtopic (2pts), and tag (1pt) overlap with bonus points.';

COMMENT ON FUNCTION get_topic_suggestions(TEXT, TEXT, INTEGER) IS 
'Optimized topic suggestions with search and count. Replaces complex nested queries.
Returns topics for specified module, optionally filtered by search query.';

COMMENT ON FUNCTION get_subtopic_suggestions(TEXT, TEXT, TEXT, INTEGER) IS 
'Optimized subtopic suggestions with topic filtering and search. 
Returns subtopics for specified module and optionally filtered by topic and search query.';

COMMENT ON FUNCTION get_tag_suggestions(TEXT, TEXT, INTEGER) IS 
'Optimized tag suggestions with search and count. 
Returns tags for specified module, optionally filtered by search query.';

-- ============================================================================
-- 7. OPTIMIZED ANSWER CHECKING RPC FUNCTION
-- ============================================================================
-- Reduces answer checking from 6-7 database calls to 2-3 calls
-- Combines question lookup, stats retrieval, and stats updates

CREATE OR REPLACE FUNCTION process_answer_check(
    user_id_param TEXT,
    question_id_param TEXT,
    is_correct_param BOOLEAN,
    token_param TEXT,
    username_param TEXT DEFAULT 'Unknown'
)
RETURNS JSON AS $$
DECLARE
    question_record RECORD;
    user_stats_record RECORD;
    module_stats_record RECORD;
    new_total INTEGER;
    new_correct INTEGER;
    new_streak INTEGER;
    new_module_answered INTEGER;
    new_module_correct INTEGER;
    new_module_streak INTEGER;
    answer_time TIMESTAMPTZ;
BEGIN
    -- Get current timestamp
    answer_time := NOW();
    
    -- Get question details (answer and module_id)
    SELECT q.answer, q.module_id 
    INTO question_record
    FROM questions q 
    WHERE q.id = question_id_param;
    
    IF NOT FOUND THEN
        RETURN json_build_object('error', 'Question not found');
    END IF;
    
    -- Get current user stats
    SELECT correct_answers, total_answers, current_streak
    INTO user_stats_record
    FROM user_stats 
    WHERE user_id = user_id_param;
    
    -- Initialize stats if user doesn't exist
    IF NOT FOUND THEN
        new_correct := CASE WHEN is_correct_param THEN 1 ELSE 0 END;
        new_total := 1;
        new_streak := CASE WHEN is_correct_param THEN 1 ELSE 0 END;
    ELSE
        new_correct := COALESCE(user_stats_record.correct_answers, 0) + 
                      CASE WHEN is_correct_param THEN 1 ELSE 0 END;
        new_total := COALESCE(user_stats_record.total_answers, 0) + 1;
        new_streak := CASE 
                     WHEN is_correct_param THEN COALESCE(user_stats_record.current_streak, 0) + 1 
                     ELSE 0 
                     END;
    END IF;
    
    -- Get current module stats
    SELECT number_answered, number_correct, current_streak
    INTO module_stats_record
    FROM module_stats 
    WHERE user_id = user_id_param AND module_id = question_record.module_id;
    
    -- Calculate new module stats
    IF NOT FOUND THEN
        new_module_answered := 1;
        new_module_correct := CASE WHEN is_correct_param THEN 1 ELSE 0 END;
        new_module_streak := CASE WHEN is_correct_param THEN 1 ELSE 0 END;
    ELSE
        new_module_answered := COALESCE(module_stats_record.number_answered, 0) + 1;
        new_module_correct := COALESCE(module_stats_record.number_correct, 0) + 
                             CASE WHEN is_correct_param THEN 1 ELSE 0 END;
        new_module_streak := CASE 
                           WHEN is_correct_param THEN COALESCE(module_stats_record.current_streak, 0) + 1 
                           ELSE 0 
                           END;
    END IF;
    
    -- Update user stats (upsert)
    INSERT INTO user_stats (
        user_id, username, correct_answers, total_answers, 
        current_streak, last_answer_time
    ) VALUES (
        user_id_param, username_param, new_correct, new_total, 
        new_streak, answer_time
    )
    ON CONFLICT (user_id) 
    DO UPDATE SET
        correct_answers = EXCLUDED.correct_answers,
        total_answers = EXCLUDED.total_answers,
        current_streak = EXCLUDED.current_streak,
        last_answer_time = EXCLUDED.last_answer_time,
        username = EXCLUDED.username;
    
    -- Update module stats (upsert)
    INSERT INTO module_stats (
        user_id, module_id, number_answered, number_correct, 
        current_streak, last_answered_time
    ) VALUES (
        user_id_param, question_record.module_id, new_module_answered, 
        new_module_correct, new_module_streak, answer_time
    )
    ON CONFLICT (user_id, module_id) 
    DO UPDATE SET
        number_answered = EXCLUDED.number_answered,
        number_correct = EXCLUDED.number_correct,
        current_streak = EXCLUDED.current_streak,
        last_answered_time = EXCLUDED.last_answered_time;
    
    -- Insert used token if correct answer
    IF is_correct_param THEN
        INSERT INTO used_tokens (user_id, token) 
        VALUES (user_id_param, token_param);
    END IF;
    
    -- Return the question answer and success status
    RETURN json_build_object(
        'success', true,
        'correct_answer', question_record.answer,
        'module_id', question_record.module_id,
        'user_stats', json_build_object(
            'correct_answers', new_correct,
            'total_answers', new_total,
            'current_streak', new_streak
        ),
        'module_stats', json_build_object(
            'number_answered', new_module_answered,
            'number_correct', new_module_correct,
            'current_streak', new_module_streak
        )
    );
    
EXCEPTION
    WHEN OTHERS THEN
        RETURN json_build_object('error', SQLERRM);
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION process_answer_check(TEXT, TEXT, BOOLEAN, TEXT, TEXT) IS 
'Optimized answer checking that combines question lookup, stats retrieval, and stats updates.
Reduces answer checking from 6-7 database calls to 2-3 calls.
Handles user stats and module stats updates atomically with proper upsert logic.';