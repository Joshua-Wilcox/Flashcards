-- Admin Performance Optimization Migration
-- This migration adds RPC functions to improve admin route performance
-- Expected performance improvement: 60-70% reduction in database calls for admin operations

-- 1. increment_user_approved_cards - Atomically increment approved cards for user and module stats
CREATE OR REPLACE FUNCTION increment_user_approved_cards(
    user_id_param BIGINT,
    username_param TEXT,
    module_id_param INTEGER
) RETURNS VOID AS $$
BEGIN
    -- Upsert user_stats and increment approved_cards atomically
    INSERT INTO user_stats (user_id, username, approved_cards)
    VALUES (user_id_param, username_param, 1)
    ON CONFLICT (user_id) 
    DO UPDATE SET 
        approved_cards = user_stats.approved_cards + 1,
        username = EXCLUDED.username;
    
    -- Upsert module_stats and increment approved_cards atomically
    INSERT INTO module_stats (user_id, module_id, number_answered, number_correct, last_answered_time, current_streak, approved_cards)
    VALUES (user_id_param, module_id_param, 0, 0, NULL, 0, 1)
    ON CONFLICT (user_id, module_id)
    DO UPDATE SET 
        approved_cards = module_stats.approved_cards + 1;
END;
$$ LANGUAGE plpgsql;

-- 2. batch_update_distractor_question_id - Update multiple distractor submissions in one call
CREATE OR REPLACE FUNCTION batch_update_distractor_question_id(
    distractor_ids_param INTEGER[],
    new_question_id_param TEXT
) RETURNS INTEGER AS $$
DECLARE
    updated_count INTEGER;
BEGIN
    UPDATE submitted_distractors 
    SET question_id = new_question_id_param
    WHERE id = ANY(distractor_ids_param);
    
    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RETURN updated_count;
END;
$$ LANGUAGE plpgsql;

-- 3. get_cached_modules - Cached module retrieval (can be used with application-level caching)
CREATE OR REPLACE FUNCTION get_cached_modules()
RETURNS TABLE (
    id INTEGER,
    name TEXT,
    year INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT m.id, m.name, m.year
    FROM modules m
    ORDER BY 
        CASE WHEN m.year IS NULL THEN 1 ELSE 0 END,
        m.year ASC,
        m.name ASC;
END;
$$ LANGUAGE plpgsql;

-- 4. admin_approve_flashcard - Single RPC to handle entire approval process
CREATE OR REPLACE FUNCTION admin_approve_flashcard(
    submission_id_param INTEGER,
    question_param TEXT,
    answer_param TEXT,
    module_id_param INTEGER,
    topic_param TEXT DEFAULT NULL,
    subtopic_param TEXT DEFAULT NULL,
    tags_param TEXT[] DEFAULT NULL
) RETURNS JSON AS $$
DECLARE
    user_id_var BIGINT;
    username_var TEXT;
    question_id_var TEXT;
    pending_distractors_count INTEGER := 0;
    result JSON;
BEGIN
    -- Get submission details
    SELECT user_id, username INTO user_id_var, username_var
    FROM submitted_flashcards 
    WHERE id = submission_id_param;
    
    IF user_id_var IS NULL THEN
        RETURN json_build_object('success', false, 'error', 'Submission not found');
    END IF;
    
    -- Generate question ID
    question_id_var := encode(digest(question_param, 'sha256'), 'hex');
    
    -- Insert question
    INSERT INTO questions (id, question, answer, module_id)
    VALUES (question_id_var, question_param, answer_param, module_id_param)
    ON CONFLICT (id) DO UPDATE SET
        question = EXCLUDED.question,
        answer = EXCLUDED.answer,
        module_id = EXCLUDED.module_id;
    
    -- Handle topic if provided
    IF topic_param IS NOT NULL AND length(trim(topic_param)) > 0 THEN
        INSERT INTO topics (name) VALUES (trim(topic_param)) ON CONFLICT (name) DO NOTHING;
        INSERT INTO question_topics (question_id, topic_id)
        SELECT question_id_var, id FROM topics WHERE name = trim(topic_param)
        ON CONFLICT (question_id, topic_id) DO NOTHING;
    END IF;
    
    -- Handle subtopic if provided
    IF subtopic_param IS NOT NULL AND length(trim(subtopic_param)) > 0 THEN
        INSERT INTO subtopics (name) VALUES (trim(subtopic_param)) ON CONFLICT (name) DO NOTHING;
        INSERT INTO question_subtopics (question_id, subtopic_id)
        SELECT question_id_var, id FROM subtopics WHERE name = trim(subtopic_param)
        ON CONFLICT (question_id, subtopic_id) DO NOTHING;
    END IF;
    
    -- Handle tags if provided
    IF tags_param IS NOT NULL AND array_length(tags_param, 1) > 0 THEN
        -- Insert all tags
        INSERT INTO tags (name)
        SELECT DISTINCT trim(unnest) FROM unnest(tags_param) WHERE length(trim(unnest)) > 0
        ON CONFLICT (name) DO NOTHING;
        
        -- Link tags to question
        INSERT INTO question_tags (question_id, tag_id)
        SELECT question_id_var, t.id 
        FROM tags t 
        WHERE t.name = ANY(
            SELECT trim(unnest) FROM unnest(tags_param) WHERE length(trim(unnest)) > 0
        )
        ON CONFLICT (question_id, tag_id) DO NOTHING;
    END IF;
    
    -- Update associated distractor submissions
    UPDATE submitted_distractors 
    SET question_id = question_id_var
    WHERE question_id = 'flashcard_' || submission_id_param;
    
    GET DIAGNOSTICS pending_distractors_count = ROW_COUNT;
    
    -- Update user stats atomically
    PERFORM increment_user_approved_cards(user_id_var, username_var, module_id_param);
    
    -- Delete the submission
    DELETE FROM submitted_flashcards WHERE id = submission_id_param;
    
    -- Return success with metadata
    result := json_build_object(
        'success', true,
        'question_id', question_id_var,
        'pending_distractors_count', pending_distractors_count,
        'user_id', user_id_var
    );
    
    RETURN result;
    
EXCEPTION WHEN OTHERS THEN
    -- Return error information
    RETURN json_build_object(
        'success', false, 
        'error', SQLERRM,
        'sqlstate', SQLSTATE
    );
END;
$$ LANGUAGE plpgsql;

-- 5. admin_reject_flashcard - Single RPC to handle entire rejection process
CREATE OR REPLACE FUNCTION admin_reject_flashcard(
    submission_id_param INTEGER
) RETURNS JSON AS $$
DECLARE
    rejected_count INTEGER := 0;
    result JSON;
BEGIN
    -- Count and delete associated distractor submissions
    SELECT COUNT(*) INTO rejected_count
    FROM submitted_distractors 
    WHERE question_id = 'flashcard_' || submission_id_param;
    
    DELETE FROM submitted_distractors 
    WHERE question_id = 'flashcard_' || submission_id_param;
    
    -- Delete the submission
    DELETE FROM submitted_flashcards WHERE id = submission_id_param;
    
    -- Return success with metadata
    result := json_build_object(
        'success', true,
        'rejected_distractors_count', rejected_count
    );
    
    RETURN result;
    
EXCEPTION WHEN OTHERS THEN
    -- Return error information
    RETURN json_build_object(
        'success', false, 
        'error', SQLERRM,
        'sqlstate', SQLSTATE
    );
END;
$$ LANGUAGE plpgsql;