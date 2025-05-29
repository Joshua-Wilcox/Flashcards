import sqlite3
import json
import hashlib
import os

DB_PATH = 'flashcards_normalized.db'
JSON_PATH = 'flashcards.json'

def get_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    return db

def get_module_id_by_name(db, module_name):
    row = db.execute('SELECT id FROM modules WHERE name = ?', (module_name,)).fetchone()
    if row:
        return row['id']
    db.execute('INSERT INTO modules (name) VALUES (?)', (module_name,))
    db.commit()
    return db.execute('SELECT id FROM modules WHERE name = ?', (module_name,)).fetchone()['id']

def add_topic_and_link_question(db, question_id, topic_name):
    topic_name = topic_name.strip()
    if not topic_name:
        return
    topic_row = db.execute('SELECT id FROM topics WHERE name = ?', (topic_name,)).fetchone()
    if not topic_row:
        db.execute('INSERT INTO topics (name) VALUES (?)', (topic_name,))
        db.commit()
        topic_id = db.execute('SELECT id FROM topics WHERE name = ?', (topic_name,)).fetchone()['id']
    else:
        topic_id = topic_row['id']
    db.execute('INSERT OR IGNORE INTO question_topics (question_id, topic_id) VALUES (?, ?)', (question_id, topic_id))
    db.commit()

def add_subtopic_and_link_question(db, question_id, subtopic_name):
    subtopic_name = subtopic_name.strip()
    if not subtopic_name:
        return
    subtopic_row = db.execute('SELECT id FROM subtopics WHERE name = ?', (subtopic_name,)).fetchone()
    if not subtopic_row:
        db.execute('INSERT INTO subtopics (name) VALUES (?)', (subtopic_name,))
        db.commit()
        subtopic_id = db.execute('SELECT id FROM subtopics WHERE name = ?', (subtopic_name,)).fetchone()['id']
    else:
        subtopic_id = subtopic_row['id']
    db.execute('INSERT OR IGNORE INTO question_subtopics (question_id, subtopic_id) VALUES (?, ?)', (question_id, subtopic_id))
    db.commit()

def add_tags_and_link_question(db, question_id, tag_names):
    for tag in tag_names:
        tag = tag.strip()
        if not tag:
            continue
        tag_row = db.execute('SELECT id FROM tags WHERE name = ?', (tag,)).fetchone()
        if not tag_row:
            db.execute('INSERT INTO tags (name) VALUES (?)', (tag,))
            db.commit()
            tag_id = db.execute('SELECT id FROM tags WHERE name = ?', (tag,)).fetchone()['id']
        else:
            tag_id = tag_row['id']
        db.execute('INSERT OR IGNORE INTO question_tags (question_id, tag_id) VALUES (?, ?)', (question_id, tag_id))
    db.commit()

def main():
    db = get_db()
    with open(JSON_PATH, 'r') as f:
        flashcards = json.load(f)
    for card in flashcards:
        question_text = card.get('Question', '').strip()
        answer = card.get('Answer', '').strip()
        module = card.get('Module', '').strip()
        topic = card.get('Topic', '').strip()
        subtopic = card.get('Sub-Topic', '').strip()
        tags = card.get('Tags', [])
        if not (question_text and answer and module):
            print(f"Skipping incomplete card: {card}")
            continue
        question_id = hashlib.sha256(question_text.encode('utf-8')).hexdigest()
        module_id = get_module_id_by_name(db, module)
        db.execute('''INSERT OR IGNORE INTO questions (id, question, answer, module_id) VALUES (?, ?, ?, ?)''',
                   (question_id, question_text, answer, module_id))
        db.commit()
        add_topic_and_link_question(db, question_id, topic)
        add_subtopic_and_link_question(db, question_id, subtopic)
        add_tags_and_link_question(db, question_id, tags)
        print(f"Imported: {question_text[:60]}...")
    print("Import complete.")

if __name__ == '__main__':
    main()
