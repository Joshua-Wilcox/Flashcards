-- Create live_activity_logs table
CREATE TABLE IF NOT EXISTS public.live_activity_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    module_name TEXT NOT NULL,
    streak INTEGER NOT NULL,
    answered_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- Foreign key to user_stats (optional, but good for integrity if user deletes account)
    CONSTRAINT fk_live_activity_user FOREIGN KEY (user_id) REFERENCES public.user_stats(user_id) ON DELETE CASCADE
);

-- Enable RLS (and allow public read for live activity?)
-- Since we want anyone to see the live activity, we allow public SELECT.
ALTER TABLE public.live_activity_logs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Enable read access for all users" ON public.live_activity_logs
    FOR SELECT USING (true);

-- Enable Realtime
ALTER PUBLICATION supabase_realtime ADD TABLE public.live_activity_logs;

-- Clean up old logs periodically (optional, can be done via cron or manual, 
-- but for now we just let it grow or add a trigger if needed later. 
-- Let's keep it simple.)

-- Update check_answer_optimized to insert into logs
CREATE OR REPLACE FUNCTION check_answer_optimized(
    user_id_param TEXT,
    question_id_param TEXT,
    submitted_answer_param TEXT,
    token_param TEXT,
    username_param TEXT DEFAULT 'Unknown'
)
RETURNS JSON AS $$
DECLARE
    question_record RECORD;
    user_stats_record RECORD;
    module_stats_record RECORD;
    module_name_text TEXT;
    token_used BOOLEAN;
    is_correct BOOLEAN;
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
    
    -- Check if token was already used (in one query)
    SELECT EXISTS(
        SELECT 1 FROM used_tokens 
        WHERE user_id = user_id_param AND token = token_param
    ) INTO token_used;
    
    IF token_used THEN
        RETURN json_build_object('error', 'Token already used for a correct answer');
    END IF;
    
    -- Get question details (answer, module_id) AND Module Name
    SELECT q.answer, q.module_id, m.name as module_name
    INTO question_record
    FROM questions q 
    JOIN modules m ON m.id = q.module_id
    WHERE q.id = question_id_param;
    
    IF NOT FOUND THEN
        RETURN json_build_object('error', 'Question not found');
    END IF;
    
    -- Store module name for logging
    module_name_text := question_record.module_name;
    
    -- Check if answer is correct
    is_correct := (submitted_answer_param = question_record.answer);
    
    -- Get current user stats
    SELECT correct_answers, total_answers, current_streak
    INTO user_stats_record
    FROM user_stats 
    WHERE user_id = user_id_param;
    
    -- Initialize stats if user doesn't exist
    IF NOT FOUND THEN
        new_correct := CASE WHEN is_correct THEN 1 ELSE 0 END;
        new_total := 1;
        new_streak := CASE WHEN is_correct THEN 1 ELSE 0 END;
    ELSE
        new_correct := COALESCE(user_stats_record.correct_answers, 0) + 
                      CASE WHEN is_correct THEN 1 ELSE 0 END;
        new_total := COALESCE(user_stats_record.total_answers, 0) + 1;
        new_streak := CASE 
                     WHEN is_correct THEN COALESCE(user_stats_record.current_streak, 0) + 1 
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
        new_module_correct := CASE WHEN is_correct THEN 1 ELSE 0 END;
        new_module_streak := CASE WHEN is_correct THEN 1 ELSE 0 END;
    ELSE
        new_module_answered := COALESCE(module_stats_record.number_answered, 0) + 1;
        new_module_correct := COALESCE(module_stats_record.number_correct, 0) + 
                             CASE WHEN is_correct THEN 1 ELSE 0 END;
        new_module_streak := CASE 
                           WHEN is_correct THEN COALESCE(module_stats_record.current_streak, 0) + 1 
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
    IF is_correct THEN
        INSERT INTO used_tokens (user_id, token) 
        VALUES (user_id_param, token_param);
        
        -- INSERT INTO LIVE ACTIVITY LOGS
        -- We only log correct answers? Or all answers? 
        -- "it should show their current streak... strictly implying correct answers usually"
        -- Let's log if is_correct is TRUE. 
        INSERT INTO live_activity_logs (
            user_id, username, module_name, streak, answered_at
        ) VALUES (
            user_id_param, username_param, module_name_text, new_streak, answer_time
        );
        
    END IF;
    
    -- Return result
    RETURN json_build_object(
        'success', true,
        'correct', is_correct,
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
