import sqlite3
import json

OLD_DB = 'flashcards.db'
NEW_DB = 'flashcards_normalized.db'

def get_or_create_id(cursor, table, name):
    cursor.execute(f"SELECT id FROM {table} WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute(f"INSERT INTO {table} (name) VALUES (?)", (name,))
    return cursor.lastrowid

def get_or_create_pdf(cursor, path, module_id=None, topic_id=None, subtopic_id=None):
    cursor.execute("SELECT id FROM pdfs WHERE path = ?", (path,))
    row = cursor.fetchone()
    if row:
        # If PDF exists but IDs are provided now, update it if they were null
        if module_id is not None or topic_id is not None or subtopic_id is not None:
            cursor.execute("""
                UPDATE pdfs SET 
                module_id = COALESCE(module_id, ?),
                topic_id = COALESCE(topic_id, ?),
                subtopic_id = COALESCE(subtopic_id, ?)
                WHERE id = ?
            """, (module_id, topic_id, subtopic_id, row[0]))
        return row[0]
    cursor.execute("INSERT INTO pdfs (path, module_id, topic_id, subtopic_id) VALUES (?, ?, ?, ?)", 
                  (path, module_id, topic_id, subtopic_id))
    return cursor.lastrowid

def get_or_create_module(cursor, name):
    cursor.execute("SELECT id FROM modules WHERE name = ?", (name,))
    row = cursor.fetchone()
    if row:
        return row[0]
    cursor.execute("INSERT INTO modules (name) VALUES (?)", (name,))
    return cursor.lastrowid

def migrate_questions_and_related(old_db, new_db):
    new_cursor = new_db.cursor()
    for row in old_db.execute("SELECT * FROM questions"):
        qid = row['id']
        question = row['question']
        answer = row['answer']
        module = row['module']
        topic = row['topic']
        subtopic = row['subtopic']
        tags = json.loads(row['tags']) if row['tags'] else []
        pdfs = json.loads(row['pdfs']) if row['pdfs'] else []

        module_id = get_or_create_module(new_cursor, module)
        new_cursor.execute("INSERT OR IGNORE INTO questions (id, question, answer, module_id) VALUES (?, ?, ?, ?)",
                           (qid, question, answer, module_id))

        # Tags
        tag_ids = []
        for tag in tags:
            tag_id = get_or_create_id(new_cursor, 'tags', tag)
            tag_ids.append(tag_id)
            new_cursor.execute("INSERT OR IGNORE INTO question_tags (question_id, tag_id) VALUES (?, ?)", (qid, tag_id))

        # Topic
        topic_id = None
        if topic:
            topic_id = get_or_create_id(new_cursor, 'topics', topic)
            new_cursor.execute("INSERT OR IGNORE INTO question_topics (question_id, topic_id) VALUES (?, ?)", (qid, topic_id))

        # Subtopic
        subtopic_id = None
        if subtopic:
            subtopic_id = get_or_create_id(new_cursor, 'subtopics', subtopic)
            new_cursor.execute("INSERT OR IGNORE INTO question_subtopics (question_id, subtopic_id) VALUES (?, ?)", (qid, subtopic_id))

        # PDFs and pdf_tags
        for pdf_path in pdfs:
            pdf_id = get_or_create_pdf(new_cursor, pdf_path, module_id, topic_id, subtopic_id)
            for tag_id in tag_ids:
                cur = new_cursor.execute("SELECT count FROM pdf_tags WHERE pdf_id = ? AND tag_id = ?", (pdf_id, tag_id))
                row2 = cur.fetchone()
                if row2:
                    new_cursor.execute("UPDATE pdf_tags SET count = count + 1 WHERE pdf_id = ? AND tag_id = ?", (pdf_id, tag_id))
                else:
                    new_cursor.execute("INSERT INTO pdf_tags (pdf_id, tag_id, count) VALUES (?, ?, 1)", (pdf_id, tag_id))
    new_db.commit()

def migrate_user_stats(old_db, new_db):
    """Explicitly migrate user_stats with all columns"""
    old_cursor = old_db.cursor()
    new_cursor = new_db.cursor()
    
    # First create the table with all required columns (without module_stats)
    new_cursor.execute('''CREATE TABLE IF NOT EXISTS user_stats (
        user_id TEXT PRIMARY KEY,
        username TEXT NOT NULL,
        correct_answers INTEGER DEFAULT 0,
        total_answers INTEGER DEFAULT 0,
        last_answer_time INTEGER,
        current_streak INTEGER DEFAULT 0
    )''')
    new_db.commit()

    # Migrate each user with explicit column mapping (excluding module_stats)
    old_cursor.execute('SELECT * FROM user_stats')
    for row in old_cursor.fetchall():
        new_cursor.execute('''
            INSERT OR REPLACE INTO user_stats 
            (user_id, username, correct_answers, total_answers, last_answer_time, current_streak)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            row['user_id'],
            row['username'],
            row['correct_answers'],
            row['total_answers'],
            row['last_answer_time'],
            row['current_streak']
        ))
    new_db.commit()

def migrate_module_stats(old_db, new_db):
    """Migrate module stats from JSON to normalized table"""
    old_cursor = old_db.cursor()
    new_cursor = new_db.cursor()
    
    old_cursor.execute('SELECT user_id, module_stats FROM user_stats WHERE module_stats IS NOT NULL')
    for row in old_cursor.fetchall():
        user_id = row['user_id']
        try:
            module_stats = json.loads(row['module_stats'])
            for module_name, stats in module_stats.items():
                # Get or create module ID
                module_row = new_cursor.execute('SELECT id FROM modules WHERE name = ?', (module_name,)).fetchone()
                if not module_row:
                    continue
                module_id = module_row[0]
                
                # Insert or replace normalized stats
                new_cursor.execute('''
                    INSERT OR REPLACE INTO module_stats 
                    (user_id, module_id, number_answered, number_correct, last_answered_time, current_streak)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    user_id,
                    module_id,
                    stats.get('number_answered', 0),
                    stats.get('number_correct', 0),
                    stats.get('last_answered_time'),
                    stats.get('current_streak', 0)
                ))
        except (json.JSONDecodeError, KeyError):
            continue
    new_db.commit()

def migrate_basic_table(old_db, new_db, table_name, columns):
    """Migrate a table with explicit column names"""
    old_cursor = old_db.cursor()
    new_cursor = new_db.cursor()
    
    placeholders = ','.join('?' * len(columns))
    col_str = ','.join(columns)
    
    old_cursor.execute(f'SELECT {col_str} FROM {table_name}')
    for row in old_cursor.fetchall():
        new_cursor.execute(
            f'INSERT OR REPLACE INTO {table_name} ({col_str}) VALUES ({placeholders})',
            tuple(row[col] for col in columns)
        )
    new_db.commit()

def main():
    old_db = sqlite3.connect(OLD_DB)
    old_db.row_factory = sqlite3.Row
    new_db = sqlite3.connect(NEW_DB)
    new_db.row_factory = sqlite3.Row

    # First create the new schema
    with open('schema.sql', 'r', encoding='utf-8') as f:
        new_db.executescript(f.read())
    new_db.commit()

    # Migrate questions and all normalized relations
    migrate_questions_and_related(old_db, new_db)

    # Migrate user_stats with special handling
    migrate_user_stats(old_db, new_db)

    # Migrate module_stats
    migrate_module_stats(old_db, new_db)

    # Migrate other tables with explicit columns
    migrate_basic_table(old_db, new_db, 'requests_to_access', 
                       ['id', 'discord_id', 'username', 'message', 'timestamp'])
    
    migrate_basic_table(old_db, new_db, 'reported_questions',
                       ['id', 'user_id', 'username', 'question', 'question_id', 'message', 'timestamp'])
    
    migrate_basic_table(old_db, new_db, 'used_tokens',
                       ['user_id', 'token', 'used_at'])
    
    migrate_basic_table(old_db, new_db, 'submitted_flashcards',
                       ['id', 'user_id', 'username', 'timestamp', 'submitted_question', 
                        'submitted_answer', 'module', 'submitted_topic', 'submitted_subtopic',
                        'submitted_tags_comma_separated'])

    print("Migration complete.")

if __name__ == "__main__":
    main()
