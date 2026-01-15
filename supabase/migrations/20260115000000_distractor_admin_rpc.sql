-- Admin Distractor Management RPCs
-- This migration adds RPC functions to allow API access for approving/rejecting distractors

-- 1. admin_approve_distractor - Atomically approve a distractor submission
CREATE OR REPLACE FUNCTION admin_approve_distractor(
    submission_id_param INTEGER
) RETURNS JSON AS $$
DECLARE
    submission_record RECORD;
    new_distractor_id INTEGER;
    result JSON;
BEGIN
    -- Get submission details
    SELECT * INTO submission_record
    FROM submitted_distractors 
    WHERE id = submission_id_param;
    
    IF submission_record IS NULL THEN
        RETURN json_build_object('success', false, 'error', 'Submission not found');
    END IF;
    
    -- Insert into manual_distractors
    INSERT INTO manual_distractors (question_id, distractor_text, created_by)
    VALUES (submission_record.question_id, submission_record.distractor_text, submission_record.user_id)
    RETURNING id INTO new_distractor_id;

    -- Upsert user_stats to ensure record exists
    INSERT INTO user_stats (user_id, username, approved_cards)
    VALUES (submission_record.user_id, COALESCE(submission_record.username, 'Unknown'), 1)
    ON CONFLICT (user_id) 
    DO UPDATE SET 
        approved_cards = user_stats.approved_cards + 1,
        username = EXCLUDED.username;

    -- Delete the submission
    DELETE FROM submitted_distractors WHERE id = submission_id_param;
    
    -- Return success with metadata
    result := json_build_object(
        'success', true,
        'distractor_id', new_distractor_id,
        'user_id', submission_record.user_id
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

-- 2. admin_reject_distractor - Atomically reject a distractor submission
CREATE OR REPLACE FUNCTION admin_reject_distractor(
    submission_id_param INTEGER
) RETURNS JSON AS $$
DECLARE
    submission_record RECORD;
    result JSON;
BEGIN
    -- Check if submission exists
    SELECT * INTO submission_record
    FROM submitted_distractors 
    WHERE id = submission_id_param;
    
    IF submission_record IS NULL THEN
        RETURN json_build_object('success', false, 'error', 'Submission not found');
    END IF;

    -- Delete the submission
    DELETE FROM submitted_distractors WHERE id = submission_id_param;
    
    -- Return success
    result := json_build_object(
        'success', true
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
