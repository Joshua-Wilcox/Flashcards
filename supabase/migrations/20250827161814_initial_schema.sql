-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create custom types (only if they don't exist)
DO $$ BEGIN
    CREATE TYPE user_role AS ENUM ('user', 'admin');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

-- User stats table with real-time support
CREATE TABLE user_stats (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT UNIQUE NOT NULL,
    username TEXT NOT NULL,
    correct_answers INTEGER DEFAULT 0,
    total_answers INTEGER DEFAULT 0,
    last_answer_time TIMESTAMPTZ,
    current_streak INTEGER DEFAULT 0,
    approved_cards INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable real-time for user_stats
ALTER TABLE user_stats REPLICA IDENTITY FULL;
ALTER PUBLICATION supabase_realtime ADD TABLE user_stats;

-- Modules table
CREATE TABLE modules (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Questions table (keeping text IDs for compatibility)
CREATE TABLE questions (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    module_id INTEGER REFERENCES modules(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Tags, topics, subtopics
CREATE TABLE tags (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE topics (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE subtopics (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL
);

-- Junction tables
CREATE TABLE question_tags (
    question_id TEXT REFERENCES questions(id) ON DELETE CASCADE,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (question_id, tag_id)
);

CREATE TABLE question_topics (
    question_id TEXT REFERENCES questions(id) ON DELETE CASCADE,
    topic_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
    PRIMARY KEY (question_id, topic_id)
);

CREATE TABLE question_subtopics (
    question_id TEXT REFERENCES questions(id) ON DELETE CASCADE,
    subtopic_id INTEGER REFERENCES subtopics(id) ON DELETE CASCADE,
    PRIMARY KEY (question_id, subtopic_id)
);

-- Module stats with real-time support
CREATE TABLE module_stats (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT NOT NULL,
    module_id INTEGER REFERENCES modules(id) ON DELETE CASCADE,
    number_answered INTEGER DEFAULT 0,
    number_correct INTEGER DEFAULT 0,
    last_answered_time TIMESTAMPTZ,
    current_streak INTEGER DEFAULT 0,
    approved_cards INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, module_id)
);

-- Enable real-time for module_stats
ALTER TABLE module_stats REPLICA IDENTITY FULL;
ALTER PUBLICATION supabase_realtime ADD TABLE module_stats;

-- PDFs table
CREATE TABLE pdfs (
    id SERIAL PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    module_id INTEGER REFERENCES modules(id) ON DELETE SET NULL,
    topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
    subtopic_id INTEGER REFERENCES subtopics(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- PDF tags junction
CREATE TABLE pdf_tags (
    pdf_id INTEGER REFERENCES pdfs(id) ON DELETE CASCADE,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    count INTEGER DEFAULT 0,
    PRIMARY KEY (pdf_id, tag_id)
);

-- Manual distractors
CREATE TABLE manual_distractors (
    id SERIAL PRIMARY KEY,
    question_id TEXT REFERENCES questions(id) ON DELETE CASCADE,
    distractor_text TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Submission tables
CREATE TABLE submitted_flashcards (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    username TEXT,
    submitted_question TEXT NOT NULL,
    submitted_answer TEXT NOT NULL,
    module TEXT NOT NULL,
    submitted_topic TEXT,
    submitted_subtopic TEXT,
    submitted_tags_comma_separated TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE submitted_distractors (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    username TEXT,
    question_id TEXT NOT NULL,
    distractor_text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Reporting and access tables
CREATE TABLE reported_questions (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    question TEXT NOT NULL,
    question_id TEXT REFERENCES questions(id) ON DELETE CASCADE,
    message TEXT,
    distractors JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE requests_to_access (
    id SERIAL PRIMARY KEY,
    discord_id TEXT NOT NULL,
    username TEXT NOT NULL,
    message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Security table
CREATE TABLE used_tokens (
    user_id TEXT,
    token TEXT,
    used_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, token)
);

-- Create indexes for performance
CREATE INDEX idx_questions_module_id ON questions(module_id);
CREATE INDEX idx_user_stats_user_id ON user_stats(user_id);
CREATE INDEX idx_module_stats_user_module ON module_stats(user_id, module_id);
CREATE INDEX idx_manual_distractors_question_id ON manual_distractors(question_id);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Add updated_at triggers
CREATE TRIGGER update_user_stats_updated_at
    BEFORE UPDATE ON user_stats
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_module_stats_updated_at
    BEFORE UPDATE ON module_stats
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_questions_updated_at
    BEFORE UPDATE ON questions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();