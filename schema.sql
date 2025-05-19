CREATE TABLE IF NOT EXISTS user_stats (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    correct_answers INTEGER DEFAULT 0,
    total_answers INTEGER DEFAULT 0,
    last_answer_time INTEGER,  -- store as Unix timestamp (seconds)
    current_streak INTEGER DEFAULT 0  -- Add missing comma here
);

CREATE TABLE IF NOT EXISTS requests_to_access (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id TEXT NOT NULL,
    username TEXT NOT NULL,
    message TEXT,
    timestamp INTEGER,
    FOREIGN KEY (discord_id) REFERENCES user_stats(user_id)
);

CREATE TABLE IF NOT EXISTS modules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    module_id INTEGER,
    FOREIGN KEY (module_id) REFERENCES modules(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS question_tags (
    question_id TEXT NOT NULL,
    tag_id INTEGER NOT NULL,
    PRIMARY KEY (question_id, tag_id),
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS question_topics (
    question_id TEXT NOT NULL,
    topic_id INTEGER NOT NULL,
    PRIMARY KEY (question_id, topic_id),
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS subtopics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

CREATE TABLE IF NOT EXISTS question_subtopics (
    question_id TEXT NOT NULL,
    subtopic_id INTEGER NOT NULL,
    PRIMARY KEY (question_id, subtopic_id),
    FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
    FOREIGN KEY (subtopic_id) REFERENCES subtopics(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS pdfs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT UNIQUE NOT NULL,
    module_id INTEGER,
    topic_id INTEGER,
    subtopic_id INTEGER,
    FOREIGN KEY (module_id) REFERENCES modules(id) ON DELETE SET NULL,
    FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE SET NULL,
    FOREIGN KEY (subtopic_id) REFERENCES subtopics(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS pdf_tags (
    pdf_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    count INTEGER DEFAULT 0,
    PRIMARY KEY (pdf_id, tag_id),
    FOREIGN KEY (pdf_id) REFERENCES pdfs(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reported_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    question TEXT NOT NULL,
    question_id TEXT, -- reference to questions.id
    message TEXT,
    timestamp INTEGER,
    distractors TEXT, -- JSON string containing distractor questions and answers
    FOREIGN KEY (user_id) REFERENCES user_stats(user_id),
    FOREIGN KEY (question_id) REFERENCES questions(id)
);

CREATE TABLE IF NOT EXISTS used_tokens (
    user_id TEXT,
    token TEXT,
    used_at INTEGER,
    PRIMARY KEY (user_id, token)
);

CREATE TABLE IF NOT EXISTS submitted_flashcards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    username TEXT,
    timestamp INTEGER NOT NULL,
    submitted_question TEXT NOT NULL,
    submitted_answer TEXT NOT NULL,
    module TEXT NOT NULL,
    submitted_topic TEXT,
    submitted_subtopic TEXT,
    submitted_tags_comma_separated TEXT
);

CREATE TABLE IF NOT EXISTS module_stats (
    user_id TEXT NOT NULL,
    module_id INTEGER NOT NULL,
    number_answered INTEGER DEFAULT 0,
    number_correct INTEGER DEFAULT 0,
    last_answered_time INTEGER,
    current_streak INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, module_id),
    FOREIGN KEY (user_id) REFERENCES user_stats(user_id) ON DELETE CASCADE,
    FOREIGN KEY (module_id) REFERENCES modules(id) ON DELETE CASCADE
);
