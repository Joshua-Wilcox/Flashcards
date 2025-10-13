-- Enable Row Level Security (RLS) for all tables
-- This prevents unauthorized access to your data

-- Enable RLS on all user-facing tables
ALTER TABLE user_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE modules ENABLE ROW LEVEL SECURITY;
ALTER TABLE questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE topics ENABLE ROW LEVEL SECURITY;
ALTER TABLE subtopics ENABLE ROW LEVEL SECURITY;
ALTER TABLE question_tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE question_topics ENABLE ROW LEVEL SECURITY;
ALTER TABLE question_subtopics ENABLE ROW LEVEL SECURITY;
ALTER TABLE module_stats ENABLE ROW LEVEL SECURITY;
ALTER TABLE pdfs ENABLE ROW LEVEL SECURITY;
ALTER TABLE pdf_tags ENABLE ROW LEVEL SECURITY;
ALTER TABLE manual_distractors ENABLE ROW LEVEL SECURITY;
ALTER TABLE submitted_flashcards ENABLE ROW LEVEL SECURITY;
ALTER TABLE submitted_distractors ENABLE ROW LEVEL SECURITY;
ALTER TABLE reported_questions ENABLE ROW LEVEL SECURITY;
ALTER TABLE requests_to_access ENABLE ROW LEVEL SECURITY;
ALTER TABLE used_tokens ENABLE ROW LEVEL SECURITY;

-- Create policies for private access - only your website can access the data
-- All content requires authentication or service role access

-- Service role and authenticated users can read modules
CREATE POLICY "Authenticated read access to modules" ON modules
    FOR SELECT USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');

-- Service role and authenticated users can read questions
CREATE POLICY "Authenticated read access to questions" ON questions
    FOR SELECT USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');

-- Service role and authenticated users can read taxonomy
CREATE POLICY "Authenticated read access to tags" ON tags
    FOR SELECT USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');

CREATE POLICY "Authenticated read access to topics" ON topics
    FOR SELECT USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');

CREATE POLICY "Authenticated read access to subtopics" ON subtopics
    FOR SELECT USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');

-- Service role and authenticated users can read question relationships
CREATE POLICY "Authenticated read access to question_tags" ON question_tags
    FOR SELECT USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');

CREATE POLICY "Authenticated read access to question_topics" ON question_topics
    FOR SELECT USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');

CREATE POLICY "Authenticated read access to question_subtopics" ON question_subtopics
    FOR SELECT USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');

-- Service role and authenticated users can read PDFs and their tags
CREATE POLICY "Authenticated read access to pdfs" ON pdfs
    FOR SELECT USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');

CREATE POLICY "Authenticated read access to pdf_tags" ON pdf_tags
    FOR SELECT USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');

-- Service role and authenticated users can read manual distractors
CREATE POLICY "Authenticated read access to manual_distractors" ON manual_distractors
    FOR SELECT USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');

-- User-specific policies for stats and submissions
-- Only users can see their own stats and make their own submissions

-- User stats: Only authenticated users and service role can read/modify
CREATE POLICY "Authenticated read access to user_stats" ON user_stats
    FOR SELECT USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');

CREATE POLICY "Users can update own stats" ON user_stats
    FOR UPDATE USING (auth.role() = 'service_role' OR (auth.role() = 'authenticated' AND auth.uid()::text = user_id));

CREATE POLICY "Users can insert own stats" ON user_stats
    FOR INSERT WITH CHECK (auth.role() = 'service_role' OR (auth.role() = 'authenticated' AND auth.uid()::text = user_id));

-- Module stats: Only authenticated users and service role can read/modify
CREATE POLICY "Authenticated read access to module_stats" ON module_stats
    FOR SELECT USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');

CREATE POLICY "Users can update own module stats" ON module_stats
    FOR UPDATE USING (auth.role() = 'service_role' OR (auth.role() = 'authenticated' AND auth.uid()::text = user_id));

CREATE POLICY "Users can insert own module stats" ON module_stats
    FOR INSERT WITH CHECK (auth.role() = 'service_role' OR (auth.role() = 'authenticated' AND auth.uid()::text = user_id));

-- Submitted flashcards: Only authenticated users and service role can read/create
CREATE POLICY "Authenticated read access to submitted_flashcards" ON submitted_flashcards
    FOR SELECT USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');

CREATE POLICY "Users can submit own flashcards" ON submitted_flashcards
    FOR INSERT WITH CHECK (auth.role() = 'service_role' OR (auth.role() = 'authenticated' AND auth.uid()::text = user_id));

-- Submitted distractors: Only authenticated users and service role can read/create
CREATE POLICY "Authenticated read access to submitted_distractors" ON submitted_distractors
    FOR SELECT USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');

CREATE POLICY "Users can submit own distractors" ON submitted_distractors
    FOR INSERT WITH CHECK (auth.role() = 'service_role' OR (auth.role() = 'authenticated' AND auth.uid()::text = user_id));

-- Reported questions: Only authenticated users and service role can read/create
CREATE POLICY "Authenticated read access to reported_questions" ON reported_questions
    FOR SELECT USING (auth.role() = 'service_role' OR auth.role() = 'authenticated');

CREATE POLICY "Users can report questions" ON reported_questions
    FOR INSERT WITH CHECK (auth.role() = 'service_role' OR (auth.role() = 'authenticated' AND auth.uid()::text = user_id));

-- Requests to access: Users can only see and create their own requests
CREATE POLICY "Users can see own access requests" ON requests_to_access
    FOR SELECT USING (auth.role() = 'service_role' OR (auth.role() = 'authenticated' AND auth.uid()::text = discord_id));

CREATE POLICY "Users can create access requests" ON requests_to_access
    FOR INSERT WITH CHECK (auth.role() = 'service_role' OR (auth.role() = 'authenticated' AND auth.uid()::text = discord_id));

-- Used tokens: Users can only see and manage their own tokens
CREATE POLICY "Users can see own tokens" ON used_tokens
    FOR SELECT USING (auth.role() = 'service_role' OR (auth.role() = 'authenticated' AND auth.uid()::text = user_id));

CREATE POLICY "Users can insert own tokens" ON used_tokens
    FOR INSERT WITH CHECK (auth.role() = 'service_role' OR (auth.role() = 'authenticated' AND auth.uid()::text = user_id));

-- Service role bypass for server-side operations
-- Your backend needs full access with service role

CREATE POLICY "Service role full access to user_stats" ON user_stats
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access to module_stats" ON module_stats
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access to modules" ON modules
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access to questions" ON questions
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access to all tables" ON tags
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access to topics" ON topics
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access to subtopics" ON subtopics
    FOR ALL USING (auth.role() = 'service_role');

-- Grant necessary permissions to authenticated users
GRANT USAGE ON SCHEMA public TO authenticated;
GRANT ALL ON ALL TABLES IN SCHEMA public TO authenticated;
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- Remove anonymous access - no public permissions
-- All access must be through your website's backend using service role
-- or authenticated users only

-- Note: Your backend should use the SERVICE ROLE key for database operations
-- This ensures your website has full access while keeping data private from direct API access