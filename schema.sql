CREATE TABLE IF NOT EXISTS user_stats (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    correct_answers INTEGER DEFAULT 0,
    total_answers INTEGER DEFAULT 0,
    last_answer_time INTEGER  -- store as Unix timestamp (seconds)
);

CREATE TABLE IF NOT EXISTS requests_to_access (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    discord_id TEXT NOT NULL,
    username TEXT NOT NULL,
    message TEXT,
    timestamp INTEGER,
    FOREIGN KEY (discord_id) REFERENCES user_stats(user_id)
);

CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY, -- hash of the question text
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    module TEXT,
    topic TEXT,
    subtopic TEXT,
    tags TEXT, -- JSON array
    pdfs TEXT -- JSON array
);

CREATE TABLE IF NOT EXISTS reported_questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    question TEXT NOT NULL,
    question_id TEXT, -- reference to questions.id
    message TEXT,
    timestamp INTEGER,
    FOREIGN KEY (user_id) REFERENCES user_stats(user_id),
    FOREIGN KEY (question_id) REFERENCES questions(id)
);

CREATE TABLE IF NOT EXISTS question_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    question_id TEXT NOT NULL,  -- hash of the question content
    created_at INTEGER NOT NULL,
    used INTEGER DEFAULT 0,
    FOREIGN KEY (user_id) REFERENCES user_stats(user_id),
    FOREIGN KEY (question_id) REFERENCES questions(id)
);
