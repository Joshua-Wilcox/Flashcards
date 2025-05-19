from flask import Flask, render_template, jsonify, request, session, redirect, url_for, send_from_directory, flash, render_template_string
from flask_discord import DiscordOAuth2Session
import json
import random
from collections import defaultdict
import sqlite3
from datetime import datetime
import pytz
from dotenv import load_dotenv
import os
import time
import secrets  # For generating secure tokens
import hashlib  # For creating secure hashes
import threading
import difflib
import base64
import hmac

load_dotenv()  # Load variables from .env

app = Flask(__name__)

# --- Testing/Production Discord App Selection ---
IS_TESTING = os.getenv("IS_TESTING", "no").lower() in ("yes", "true", "1")
if IS_TESTING:
    app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key")
    app.config["DISCORD_CLIENT_ID"] = os.getenv("TEST_CLIENT_ID")
    app.config["DISCORD_CLIENT_SECRET"] = os.getenv("TEST_SECRET")
    app.config["DISCORD_REDIRECT_URI"] = os.getenv("TEST_REDIRECT_URI", "http://127.0.0.1:2456/callback")
else:
    app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key")
    app.config["DISCORD_CLIENT_ID"] = os.getenv("DISCORD_CLIENT_ID")
    app.config["DISCORD_CLIENT_SECRET"] = os.getenv("DISCORD_CLIENT_SECRET")
    app.config["DISCORD_REDIRECT_URI"] = os.getenv("DISCORD_REDIRECT_URI")
app.config["DISCORD_OAUTH2_SCOPE"] = ["identify, guilds"]
discord = DiscordOAuth2Session(app)

SESSION_VERSION = 4  # Increment this when you change scopes or session structure
NUMBER_OF_DISTRACTORS = 4

# Database functions
def get_db():
    db = sqlite3.connect('flashcards_normalized.db')  # Changed from flashcards.db to normalized version
    db.row_factory = sqlite3.Row
    return db

def get_all_modules():
    db = get_db()
    rows = db.execute('SELECT id, name FROM modules ORDER BY name').fetchall()
    return [{'id': row['id'], 'name': row['name']} for row in rows]

def get_module_id_by_name(db, module_name):
    row = db.execute('SELECT id FROM modules WHERE name = ?', (module_name,)).fetchone()
    if row:
        return row['id']
    db.execute('INSERT INTO modules (name) VALUES (?)', (module_name,))
    return db.execute('SELECT id FROM modules WHERE name = ?', (module_name,)).fetchone()['id']

def get_module_name_by_id(db, module_id):
    row = db.execute('SELECT name FROM modules WHERE id = ?', (module_id,)).fetchone()
    return row['name'] if row else None

def get_unique_values(key):
    db = get_db()
    if key == 'topic':
        rows = db.execute('SELECT DISTINCT name FROM topics').fetchall()
    elif key == 'subtopic':
        rows = db.execute('SELECT DISTINCT name FROM subtopics').fetchall()
    else:
        # Fallback for other columns if needed
        rows = db.execute(f'SELECT DISTINCT {key} FROM questions').fetchall()
    return sorted([row[0] for row in rows if row[0]])

def get_tags_for_question(question_id):
    db = get_db()
    rows = db.execute('''
        SELECT t.name FROM tags t
        JOIN question_tags qt ON t.id = qt.tag_id
        WHERE qt.question_id = ?
    ''', (question_id,)).fetchall()
    return [row['name'] for row in rows]

def get_topics_for_question(question_id):
    db = get_db()
    rows = db.execute('''
        SELECT tp.name FROM topics tp
        JOIN question_topics qt ON tp.id = qt.topic_id
        WHERE qt.question_id = ?
    ''', (question_id,)).fetchall()
    return [row['name'] for row in rows]

def get_subtopics_for_question(question_id):
    db = get_db()
    rows = db.execute('''
        SELECT st.name FROM subtopics st
        JOIN question_subtopics qs ON st.id = qs.subtopic_id
        WHERE qs.question_id = ?
    ''', (question_id,)).fetchall()
    return [row['name'] for row in rows]

def get_pdfs_for_tags(tag_names):
    db = get_db()
    if not tag_names:
        return []
    placeholders = ','.join('?' * len(tag_names))
    rows = db.execute(f'''
        SELECT p.path, SUM(pt.count) as tag_count
        FROM pdfs p
        JOIN pdf_tags pt ON p.id = pt.pdf_id
        JOIN tags t ON pt.tag_id = t.id
        WHERE t.name IN ({placeholders})
        GROUP BY p.id
        ORDER BY tag_count DESC
    ''', tag_names).fetchall()
    return [{'path': row['path'], 'name': os.path.basename(row['path'])} for row in rows]

def add_tags_and_link_question(db, question_id, tag_names):
    for tag in tag_names:
        tag = tag.strip()
        if not tag:
            continue
        tag_row = db.execute('SELECT id FROM tags WHERE name = ?', (tag,)).fetchone()
        if not tag_row:
            db.execute('INSERT INTO tags (name) VALUES (?)', (tag,))
            tag_id = db.execute('SELECT id FROM tags WHERE name = ?', (tag,)).fetchone()['id']
        else:
            tag_id = tag_row['id']
        db.execute('INSERT OR IGNORE INTO question_tags (question_id, tag_id) VALUES (?, ?)', (question_id, tag_id))

def add_topic_and_link_question(db, question_id, topic_name):
    topic_name = topic_name.strip()
    if not topic_name:
        return
    topic_row = db.execute('SELECT id FROM topics WHERE name = ?', (topic_name,)).fetchone()
    if not topic_row:
        db.execute('INSERT INTO topics (name) VALUES (?)', (topic_name,))
        topic_id = db.execute('SELECT id FROM topics WHERE name = ?', (topic_name,)).fetchone()['id']
    else:
        topic_id = topic_row['id']
    db.execute('INSERT OR IGNORE INTO question_topics (question_id, topic_id) VALUES (?, ?)', (question_id, topic_id))

def add_subtopic_and_link_question(db, question_id, subtopic_name):
    subtopic_name = subtopic_name.strip()
    if not subtopic_name:
        return
    subtopic_row = db.execute('SELECT id FROM subtopics WHERE name = ?', (subtopic_name,)).fetchone()
    if not subtopic_row:
        db.execute('INSERT INTO subtopics (name) VALUES (?)', (subtopic_name,))
        subtopic_id = db.execute('SELECT id FROM subtopics WHERE name = ?', (subtopic_name,)).fetchone()['id']
    else:
        subtopic_id = subtopic_row['id']
    db.execute('INSERT OR IGNORE INTO question_subtopics (question_id, subtopic_id) VALUES (?, ?)', (question_id, subtopic_id))

def populate_questions_table():
    db = get_db()
    # Check if table exists, create if not
    db.execute('''CREATE TABLE IF NOT EXISTS questions (
        id TEXT PRIMARY KEY,
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        module_id INTEGER,
        FOREIGN KEY (module_id) REFERENCES modules(id)
    )''')
    db.commit()

    # Load questions from JSON
    with open('flashcards.json', 'r') as file:
        flashcards = json.load(file)
    
    for card in flashcards:
        question_text = card.get('Question', '')
        answer = card.get('Answer', '')
        module = card.get('Module', '')
        topic = card.get('Topic', '')
        subtopic = card.get('Sub-Topic', '')
        tags = card.get('Tags', [])
        
        question_id = hashlib.sha256(question_text.encode('utf-8')).hexdigest()
        module_id = get_module_id_by_name(db, module)
        
        # Insert question with only normalized fields
        db.execute('''INSERT OR IGNORE INTO questions (id, question, answer, module_id)
                      VALUES (?, ?, ?, ?)''',
                   (question_id, question_text, answer, module_id))
        
        # Add all relationships using normalized tables
        add_tags_and_link_question(db, question_id, tags)
        add_topic_and_link_question(db, question_id, topic)
        add_subtopic_and_link_question(db, question_id, subtopic)
    
    db.commit()

def init_db():
    with app.app_context():
        db = get_db()
        # Execute schema.sql to create/update all tables
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()
        # Add current_streak column if missing
        try:
            db.execute('ALTER TABLE user_stats ADD COLUMN current_streak INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass  # Column already exists
        db.commit()
        # Add module_stats column if missing
        try:
            db.execute('ALTER TABLE user_stats ADD COLUMN module_stats TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
        db.commit()

def is_user_whitelisted(user_id, user_guilds):
    with open('whitelist.json', 'r') as f:
        whitelist = json.load(f)
    if int(user_id) in whitelist.get('user_ids', []):
        return True
    if user_guilds:
        whitelist_guilds = set(int(gid) for gid in whitelist.get('guild_ids', []))
        for guild in user_guilds:
            if int(guild.id) in whitelist_guilds:
                return True
    return False

def generate_question_token(question_id, user_id):
    """Generate a secure token for a question attempt"""
    token = secrets.token_hex(16)
    # Create a unique hash combining the token, question, and user
    hash_input = f"{token}:{question_id}:{user_id}".encode('utf-8')
    token_hash = hashlib.sha256(hash_input).hexdigest()
    return token, token_hash

@app.route('/pdf/<path:pdf_path>')
def serve_pdf(pdf_path):
    if not discord.authorized:
        return redirect(url_for('login', next=request.url))
    user = discord.fetch_user()
    user_id = user.id
    user_guilds = discord.fetch_guilds()
    if is_user_whitelisted(user_id, user_guilds):
        # Only serve files from the static/pdfs directory
        safe_path = os.path.normpath(pdf_path)
        base_dir = os.path.abspath('static/pdfs')
        abs_path = os.path.abspath(os.path.join(base_dir, safe_path))
        if not abs_path.startswith(base_dir):
            return "Invalid file path", 403
        return send_from_directory(base_dir, safe_path)
    else:
        return redirect(url_for('request_pdf_access'))

@app.route('/request_pdf_access', methods=['GET', 'POST'])
def request_pdf_access():
    if not discord.authorized:
        return redirect(url_for('login', next=request.url))
    user = discord.fetch_user()
    if request.method == 'POST':
        message = request.form.get('message', '')
        db = get_db()
        db.execute(
            'INSERT INTO requests_to_access (discord_id, username, message, timestamp) VALUES (?, ?, ?, ?)',
            (user.id, user.username, message, int(datetime.utcnow().timestamp()))
        )
        db.commit()
        flash('Your request has been submitted!')
        return redirect(url_for('index'))
    return render_template('request_pdf_access.html')

@app.route('/')
def index():
    modules = get_all_modules()
    return render_template('index.html',
        modules=[m['name'] for m in modules],
        topics=get_unique_values('topic'),
        subtopics=get_unique_values('subtopic'), NUMBER_OF_DISTRACTORS=NUMBER_OF_DISTRACTORS)

@app.route('/get_filters', methods=['POST'])
def get_filters():
    selected_module = request.json.get('module')
    selected_topics = request.json.get('topics', [])
    db = get_db()
    module_id = None
    if selected_module:
        row = db.execute('SELECT id FROM modules WHERE name = ?', (selected_module,)).fetchone()
        if row:
            module_id = row['id']
    
    # Get topics for selected module using normalized schema
    topics_query = '''
        SELECT DISTINCT t.name 
        FROM topics t
        JOIN question_topics qt ON t.id = qt.topic_id
        JOIN questions q ON qt.question_id = q.id
        WHERE q.module_id = ?
        ORDER BY t.name
    '''
    topics = db.execute(topics_query, (module_id,)).fetchall()

    # Get subtopics for selected module and topics using normalized schema
    if selected_topics:
        placeholders = ','.join('?' * len(selected_topics))
        subtopics_query = f'''
            SELECT DISTINCT st.name 
            FROM subtopics st
            JOIN question_subtopics qs ON st.id = qs.subtopic_id
            JOIN questions q ON qs.question_id = q.id
            JOIN question_topics qt ON q.id = qt.question_id
            JOIN topics t ON qt.topic_id = t.id
            WHERE q.module_id = ?
            AND t.name IN ({placeholders})
            ORDER BY st.name
        '''
        params = [module_id] + selected_topics
        subtopics = db.execute(subtopics_query, params).fetchall()
    else:
        # All subtopics for the selected module
        subtopics_query = '''
            SELECT DISTINCT st.name 
            FROM subtopics st
            JOIN question_subtopics qs ON st.id = qs.subtopic_id
            JOIN questions q ON qs.question_id = q.id
            WHERE q.module_id = ?
            ORDER BY st.name
        '''
        subtopics = db.execute(subtopics_query, (module_id,)).fetchall()

    return jsonify({
        'topics': sorted([row[0] for row in topics if row[0]]),
        'subtopics': sorted([row[0] for row in subtopics if row[0]])
    })

@app.route('/get_question', methods=['POST'])
def get_question():
    if 'user_id' not in session:
        return jsonify({'error': 'You must be logged in'}), 401
    
    data = request.get_json()
    module_name = data.get('module')
    topics = data.get('topics', [])
    subtopics = data.get('subtopics', [])
    question_id = data.get('question_id')
    
    db = get_db()
    module_id = None
    if module_name:
        row = db.execute('SELECT id FROM modules WHERE name = ?', (module_name,)).fetchone()
        if row:
            module_id = row['id']

    # Build the query using the normalized schema
    query = '''
        SELECT DISTINCT q.* 
        FROM questions q
    '''
    params = []

    if module_id:
        query += ' WHERE q.module_id = ?'
        params.append(module_id)
    
    if topics:
        placeholders = ','.join('?' * len(topics))
        query += f'''
            AND EXISTS (
                SELECT 1 FROM question_topics qt
                JOIN topics t ON qt.topic_id = t.id
                WHERE qt.question_id = q.id
                AND t.name IN ({placeholders})
            )
        '''
        params.extend(topics)
    
    if subtopics:
        placeholders = ','.join('?' * len(subtopics))
        query += f'''
            AND EXISTS (
                SELECT 1 FROM question_subtopics qs
                JOIN subtopics s ON qs.subtopic_id = s.id
                WHERE qs.question_id = q.id
                AND s.name IN ({placeholders})
            )
        '''
        params.extend(subtopics)

    if question_id:
        query += ' AND q.id = ?'
        params.append(question_id)

    rows = db.execute(query, params).fetchall()
    if not rows:
        return jsonify({'error': 'No questions found matching these criteria'})

    row = rows[0] if question_id else random.choice(rows)
    qid = row['id']
    tags = get_tags_for_question(qid)
    pdfs = get_pdfs_for_tags(tags)
    topics_list = get_topics_for_question(qid)
    subtopics_list = get_subtopics_for_question(qid)
    module_display = get_module_name_by_id(db, row['module_id'])
    correct_answer = row['answer']
    answers = [correct_answer]
    answer_ids = [qid]
    # Distractor logic: pick random answers from other questions in the same module
    distractors_needed = NUMBER_OF_DISTRACTORS
    distractor_rows = db.execute(
        'SELECT id, answer FROM questions WHERE module_id = ? AND id != ? ORDER BY RANDOM() LIMIT ?',
        (row['module_id'], qid, distractors_needed)
    ).fetchall()
    for dr in distractor_rows:
        answers.append(dr['answer'])
        answer_ids.append(dr['id'])
    combined = list(zip(answers, answer_ids))
    random.shuffle(combined)
    answers, answer_ids = zip(*combined)
    answers = list(answers)
    answer_ids = list(answer_ids)
    token = generate_signed_token(qid, session['user_id'])
    if 'used_tokens' not in session:
        session['used_tokens'] = []
    response = {
        'question': row['question'],
        'answers': answers,
        'answer_ids': answer_ids,
        'module': module_display,
        'topic': topics_list[0] if topics_list else '',
        'subtopic': subtopics_list[0] if subtopics_list else '',
        'tags': tags,
        'pdfs': pdfs,
        'token': token,
        'question_id': qid,
        'is_admin': is_user_admin(session.get('user_id')) if 'user_id' in session else False
    }
    return jsonify(response)

@app.route('/submit_flashcard', methods=['GET', 'POST'])
def submit_flashcard():
    if not discord.authorized:
        return redirect(url_for('login', next=request.url))
    user = discord.fetch_user()
    db = get_db()
    modules = get_all_modules()
    if request.method == 'POST':
        question = request.form.get('question', '').strip()
        answer = request.form.get('answer', '').strip()
        module = request.form.get('module', '').strip()
        topic = request.form.get('topic', '').strip()
        subtopic = request.form.get('subtopic', '').strip()
        tags = request.form.get('tags', '').strip()
        if question and answer and module and topic and subtopic and tags:
            db.execute('''INSERT INTO submitted_flashcards 
                (user_id, username, timestamp, submitted_question, submitted_answer, module, submitted_topic, submitted_subtopic, submitted_tags_comma_separated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (user.id, user.username, int(datetime.utcnow().timestamp()), question, answer, module, topic, subtopic, tags))
            db.commit()
            flash('Flashcard submitted for review! Thank you.')
            return render_template('submit_flashcard.html', modules=[m['name'] for m in modules], selected_module=module, clear_fields=True,
                                   prev_topic=topic, prev_subtopic=subtopic, prev_tags=tags)
        else:
            flash('Please fill in all required fields (question, answer, module, topic, subtopic, tags).')
            return render_template('submit_flashcard.html', modules=[m['name'] for m in modules], selected_module=module, clear_fields=False,
                                   prev_question=question, prev_answer=answer, prev_topic=topic, prev_subtopic=subtopic, prev_tags=tags)
    return render_template('submit_flashcard.html', modules=[m['name'] for m in modules], selected_module=None, clear_fields=False)

@app.route('/admin_review_flashcard/<int:submission_id>', methods=['GET', 'POST'])
def admin_review_flashcard(submission_id):
    if 'user_id' not in session or not is_user_admin(session['user_id']):
        return redirect(url_for('index'))
    db = get_db()
    submission = db.execute('SELECT * FROM submitted_flashcards WHERE id = ?', (submission_id,)).fetchone()
    modules = get_all_modules()
    if not submission:
        flash('Submission not found.')
        return redirect(url_for('admin_review_flashcards'))
    if request.method == 'POST':
        action = request.form.get('action')
        question = request.form.get('question', '').strip()
        answer = request.form.get('answer', '').strip()
        module = request.form.get('module', '').strip()
        topic = request.form.get('topic', '').strip()
        subtopic = request.form.get('subtopic', '').strip()
        tags = request.form.get('tags', '').strip()
        if action == 'approve':
            module_id = get_module_id_by_name(db, module)
            question_id = hashlib.sha256(question.encode('utf-8')).hexdigest()
            db.execute('''INSERT OR IGNORE INTO questions (id, question, answer, module_id)
                          VALUES (?, ?, ?, ?)''',
                       (question_id, question, answer, module_id))
            tag_list = [t.strip() for t in tags.split(',') if t.strip()]
            add_tags_and_link_question(db, question_id, tag_list)
            add_topic_and_link_question(db, question_id, topic)
            add_subtopic_and_link_question(db, question_id, subtopic)
            db.execute('DELETE FROM submitted_flashcards WHERE id = ?', (submission_id,))
            db.commit()
            flash('Flashcard approved and added to the database.')
            return redirect(url_for('admin_review_flashcards'))
        elif action == 'reject':
            db.execute('DELETE FROM submitted_flashcards WHERE id = ?', (submission_id,))
            db.commit()
            flash('Flashcard submission rejected and removed.')
            return redirect(url_for('admin_review_flashcards'))
    return render_template('admin_review_flashcard.html', submission=submission, modules=[m['name'] for m in modules])

@app.route('/report_question', methods=['GET', 'POST'])
def report_question():
    if not discord.authorized:
        return redirect(url_for('login', next=request.url))
    user = discord.fetch_user()
    question = request.args.get('question', '')
    answer = request.args.get('answer', '')
    distractor_ids = request.args.get('distractor_ids', '')
    db = get_db()
    question_id = None
    if question:
        row = db.execute('SELECT id FROM questions WHERE question = ?', (question,)).fetchone()
        if row:
            question_id = row['id']
    
    # Fetch distractor information if we have IDs
    distractors = []
    if distractor_ids:
        distractor_id_list = distractor_ids.split(',')
        for d_id in distractor_id_list:
            if d_id and d_id != question_id:  # Skip the main question if it's in the list
                d_row = db.execute('SELECT id, question, answer FROM questions WHERE id = ?', (d_id,)).fetchone()
                if d_row:
                    distractors.append({
                        'id': d_row['id'],
                        'question': d_row['question'],
                        'answer': d_row['answer']
                    })
    
    if request.method == 'POST':
        message = request.form.get('message', '')
        question_text = request.form.get('question_text', '')
        answer_text = request.form.get('answer_text', '')
        qid = question_id
        if not qid and question_text:
            row = db.execute('SELECT id FROM questions WHERE question = ?', (question_text,)).fetchone()
            if row:
                qid = row['id']
        
        # Store distractors as JSON string
        distractors_json = request.form.get('distractors_json', '[]')
        
        db.execute(
            'INSERT INTO reported_questions (user_id, username, question, question_id, message, timestamp, distractors) VALUES (?, ?, ?, ?, ?, ?, ?)',
            (user.id, user.username, f"Q: {question_text}\nA: {answer_text}", qid, message, int(datetime.utcnow().timestamp()), distractors_json)
        )
        db.commit()
        flash('Your report has been submitted!')
        return redirect(url_for('index'))
    
    # Convert distractors to JSON for the form
    distractors_json = json.dumps(distractors)
    
    return render_template('report_question.html', question=question, answer=answer, distractors_json=distractors_json)

@app.route('/edit_answer', methods=['POST'])
def edit_answer():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    if not is_user_admin(session['user_id']):
        return jsonify({'error': 'Unauthorized'}), 403
    data = request.get_json()
    question_id = data.get('question_id')
    new_text = data.get('new_text')
    if not question_id or new_text is None:
        return jsonify({'error': 'Missing required data'}), 400
    db = get_db()
    try:
        db.execute('UPDATE questions SET answer = ? WHERE id = ?', (new_text, question_id))
        db.commit()
        return jsonify({'success': True})
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500

@app.route('/check_answer', methods=['POST'])
def check_answer():
    if 'user_id' not in session:
        return jsonify({'error': 'You must be logged in'}), 401
    
    data = request.get_json()
    token = data.get('token')
    submitted_answer = data.get('answer')
    if not token or not submitted_answer:
        return jsonify({'error': 'Missing token or answer'}), 400
    user_id = session['user_id']
    db = get_db()
    # --- Token validation ---
    row = db.execute('SELECT 1 FROM used_tokens WHERE user_id = ? AND token = ?', (user_id, token)).fetchone()
    if row:
        return jsonify({'error': 'Token already used for a correct answer'}), 400
    question_id, valid = verify_signed_token(token, user_id)
    if not valid:
        return jsonify({'error': 'Invalid or expired token'}), 400
    qrow = db.execute('SELECT answer, module_id FROM questions WHERE id = ?', (question_id,)).fetchone()
    if not qrow:
        return jsonify({'error': 'Question not found'}), 400
    correct_answer = qrow['answer']
    module_id = qrow['module_id']
    is_correct = submitted_answer == correct_answer

    # Always increment total_answers
    stats = db.execute('SELECT correct_answers, total_answers, current_streak, module_stats FROM user_stats WHERE user_id = ?', (user_id,)).fetchone()
    if stats:
        correct = stats['correct_answers'] or 0
        total = stats['total_answers'] or 0
        streak = stats['current_streak'] if 'current_streak' in stats.keys() else 0
        module_stats = json.loads(stats['module_stats']) if stats['module_stats'] else {}
    else:
        correct = 0
        total = 0
        streak = 0
        module_stats = {}
    total += 1
    # Use Europe/London timezone for last_answer_time
    london_tz = pytz.timezone('Europe/London')
    now_london = datetime.now(london_tz)
    last_answer_time = int(now_london.timestamp())
    # --- Update per-module stats ---
    if module_id not in module_stats:
        module_stats[module_id] = {
            "last_answered_time": None,
            "number_answered": 0,
            "number_correct": 0,
            "current_streak": 0
        }
    # Ensure current_streak key exists for all modules
    if "current_streak" not in module_stats[module_id]:
        module_stats[module_id]["current_streak"] = 0
    module_stats[module_id]["last_answered_time"] = last_answer_time
    module_stats[module_id]["number_answered"] = module_stats[module_id].get("number_answered", 0) + 1
    if is_correct:
        correct += 1
        streak += 1
        module_stats[module_id]["number_correct"] = module_stats[module_id].get("number_correct", 0) + 1
        module_stats[module_id]["current_streak"] = module_stats[module_id].get("current_streak", 0) + 1
        db.execute('INSERT OR IGNORE INTO used_tokens (user_id, token, used_at) VALUES (?, ?, ?)', (user_id, token, last_answer_time))
    else:
        streak = 0
        module_stats[module_id]["current_streak"] = 0
    # Update user stats
    db.execute('''UPDATE user_stats 
                  SET correct_answers = ?, 
                      total_answers = ?, 
                      last_answer_time = ?, 
                      current_streak = ?,
                      module_stats = ? 
                  WHERE user_id = ?''',
               (correct, total, last_answer_time, streak, json.dumps(module_stats), user_id))
    
    # Update stats in normalized tables
    db.execute('''INSERT OR REPLACE INTO module_stats
                  (user_id, module_id, number_answered, number_correct, last_answered_time, current_streak)
                  VALUES (?, ?, 
                         COALESCE((SELECT number_answered + 1 FROM module_stats WHERE user_id = ? AND module_id = ?), 1),
                         COALESCE((SELECT number_correct + ? FROM module_stats WHERE user_id = ? AND module_id = ?), ?),
                         ?, 
                         CASE WHEN ? THEN COALESCE((SELECT current_streak + 1 FROM module_stats WHERE user_id = ? AND module_id = ?), 1)
                              ELSE 0 END)''',
               (user_id, module_id, 
                user_id, module_id,
                1 if is_correct else 0, user_id, module_id, 1 if is_correct else 0,
                last_answer_time,
                is_correct, user_id, module_id))

    # Update overall stats
    db.execute('''UPDATE user_stats 
                  SET correct_answers = (SELECT SUM(number_correct) FROM module_stats WHERE user_id = ?),
                      total_answers = (SELECT SUM(number_answered) FROM module_stats WHERE user_id = ?),
                      last_answer_time = ?,
                      current_streak = CASE WHEN ? THEN current_streak + 1 ELSE 0 END
                  WHERE user_id = ?''',
               (user_id, user_id, last_answer_time, is_correct, user_id))

    db.commit()
    return jsonify({'correct': is_correct})

@app.route('/login')
def login():
    return discord.create_session(scope=["identify", "guilds"])

@app.route("/callback")
def callback():
    try:
        discord.callback()
        user = discord.fetch_user()
        session['user_id'] = user.id
        session['username'] = f"{user.name}"
        session['session_version'] = SESSION_VERSION
        db = get_db()
        row = db.execute('SELECT * FROM user_stats WHERE user_id = ?', (user.id,)).fetchone()
        modules = get_all_modules()
        if not row:
            # New user: create user_stats entry
            db.execute('''INSERT INTO user_stats 
                         (user_id, username, correct_answers, total_answers, current_streak) 
                         VALUES (?, ?, 0, 0, 0)''', 
                      (user.id, session['username']))
            # Initialize module_stats entries
            for module in modules:
                module_id = get_module_id_by_name(db, module['name'])
                db.execute('''INSERT INTO module_stats 
                            (user_id, module_id, number_answered, number_correct, current_streak)
                            VALUES (?, ?, 0, 0, 0)''',
                         (user.id, module_id))
        db.commit()
        return redirect(url_for('index'))
    except Exception as e:
        return f"An error occurred: {str(e)}"

@app.route("/logout")
def logout():
    discord.revoke()
    session.clear()
    return redirect(url_for('index'))

@app.route('/leaderboard')
def leaderboard():
    sort = request.args.get('sort', 'correct_answers')
    order = request.args.get('order', 'desc')
    module_filter = request.args.get('module', None)
    allowed = {
        'correct_answers': 'correct_answers',
        'total_answers': 'total_answers',
        'accuracy': '(CASE WHEN total_answers > 0 THEN 1.0 * correct_answers / total_answers ELSE 0 END)',
        'current_streak': 'current_streak',
        'last_answer_time': 'last_answer_time'
    }
    sort_col = allowed.get(sort, 'correct_answers')
    order_sql = 'DESC' if order == 'desc' else 'ASC'
    db = get_db()
    if not module_filter:
        # Use SQL sorting for global stats
        users = db.execute(f'''
            SELECT user_id, username, correct_answers, total_answers, current_streak, last_answer_time,
                (CASE WHEN total_answers > 0 THEN 1.0 * correct_answers / total_answers ELSE 0 END) as accuracy
            FROM user_stats
            ORDER BY {sort_col} {order_sql}, total_answers DESC
            LIMIT 50
        ''').fetchall()
    else:
        # Get stats for specific module
        users = db.execute(f'''
            SELECT us.user_id, us.username, 
                   ms.number_correct as correct_answers,
                   ms.number_answered as total_answers,
                   ms.current_streak,
                   ms.last_answered_time as last_answer_time,
                   (CASE WHEN ms.number_answered > 0 
                         THEN 1.0 * ms.number_correct / ms.number_answered 
                         ELSE 0 END) as accuracy
            FROM user_stats us
            LEFT JOIN modules m ON m.name = ?
            LEFT JOIN module_stats ms ON ms.user_id = us.user_id AND ms.module_id = m.id
            ORDER BY {sort_col} {order_sql}, ms.number_answered DESC
            LIMIT 50
        ''', (module_filter,)).fetchall()

    leaderboard = []
    for row in users:
        user = dict(row)
        # If module filter is active, override stats with per-module
        if module_filter and user.get('module_stats'):
            try:
                ms = json.loads(user['module_stats'])
                modstats = ms.get(module_filter, {})
                user['correct_answers'] = modstats.get('number_correct', 0)
                user['total_answers'] = modstats.get('number_answered', 0)
                user['accuracy'] = (modstats.get('number_correct', 0) / modstats.get('number_answered', 1)) if modstats.get('number_answered', 0) else 0
                user['current_streak'] = modstats.get('current_streak', 0)
                user['last_answer_time'] = modstats.get('last_answered_time', None)
            except Exception:
                user['correct_answers'] = 0
                user['total_answers'] = 0
                user['accuracy'] = 0
                user['current_streak'] = 0
                user['last_answer_time'] = None
        leaderboard.append(user)
    # --- Sort leaderboard in Python if module filter is active ---
    if module_filter:
        def sort_key(user):
            if sort == 'accuracy':
                return user['accuracy']
            elif sort == 'last_answer_time':
                val = user.get('last_answer_time')
                if val is None:
                    return 0 if order == 'asc' else float('-inf')
                return val
            return user.get(sort, 0)
        leaderboard = sorted(
            leaderboard,
            key=sort_key,
            reverse=(order == 'desc')
        )
        # For tie-breaking, sort by total_answers descending
        if sort != 'total_answers':
            leaderboard = sorted(
                leaderboard,
                key=lambda u: (sort_key(u), u.get('total_answers', 0)),
                reverse=(order == 'desc')
            )
    else:
        # Already sorted by SQL for global stats
        pass
    modules = get_all_modules()
    return render_template('leaderboard.html', leaderboard=leaderboard, sort=sort, order=order, modules=modules, active_module=module_filter)

@app.route('/user_stats/<user_id>')
def user_stats(user_id):
    module_filter = request.args.get('module', None)
    db = get_db()
    
    # Get base user stats
    base_stats = db.execute('''
        SELECT user_id, username, correct_answers, total_answers, 
               last_answer_time, current_streak
        FROM user_stats 
        WHERE user_id = ?
    ''', (user_id,)).fetchone()
    
    if not base_stats:
        return redirect(url_for('index'))
    
    # Get module stats
    module_stats = db.execute('''
        SELECT m.name, ms.number_answered, ms.number_correct, 
               ms.last_answered_time, ms.current_streak
        FROM modules m
        LEFT JOIN module_stats ms ON ms.module_id = m.id 
        AND ms.user_id = ?
    ''', (user_id,)).fetchall()
    
    # Convert to dictionary format expected by template
    stats_dict = dict(base_stats)
    stats_dict['module_stats'] = {
        row['name']: {
            'number_answered': row['number_answered'] or 0,
            'number_correct': row['number_correct'] or 0,
            'last_answered_time': row['last_answered_time'],
            'current_streak': row['current_streak'] or 0
        } for row in module_stats
    }
    stats_dict['active_module'] = module_filter
    
    modules = get_all_modules()
    return render_template('stats.html', stats=stats_dict, 
                         is_other_user=True, modules=modules)

@app.route('/stats')
def stats():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    module_filter = request.args.get('module', None)
    db = get_db()
    
    # Get base user stats
    base_stats = db.execute('''
        SELECT user_id, username, correct_answers, total_answers, 
               last_answer_time, current_streak
        FROM user_stats 
        WHERE user_id = ?
    ''', (session['user_id'],)).fetchone()
    
    # Get module stats
    module_stats = db.execute('''
        SELECT m.name, ms.number_answered, ms.number_correct, 
               ms.last_answered_time, ms.current_streak
        FROM modules m
        LEFT JOIN module_stats ms ON ms.module_id = m.id 
        AND ms.user_id = ?
    ''', (session['user_id'],)).fetchall()
    
    # Convert to dictionary format expected by template
    stats_dict = dict(base_stats)
    stats_dict['module_stats'] = {
        row['name']: {
            'number_answered': row['number_answered'] or 0,
            'number_correct': row['number_correct'] or 0,
            'last_answered_time': row['last_answered_time'],
            'current_streak': row['current_streak'] or 0
        } for row in module_stats
    }
    stats_dict['active_module'] = module_filter
    
    modules = get_all_modules()
    return render_template('stats.html', stats=stats_dict, 
                         is_other_user=False, modules=modules)

@app.route('/admin_review_flashcards')
def admin_review_flashcards():
    if 'user_id' not in session or not is_user_admin(session['user_id']):
        return redirect(url_for('index'))
    db = get_db()
    rows = db.execute('SELECT * FROM submitted_flashcards ORDER BY timestamp ASC').fetchall()
    reports = db.execute('SELECT * FROM reported_questions ORDER BY timestamp ASC').fetchall()
    pdf_requests = db.execute('SELECT * FROM requests_to_access ORDER BY timestamp ASC').fetchall()
    return render_template('admin_review_flashcards.html', submissions=rows, reports=reports, pdf_requests=pdf_requests)

@app.route('/admin_review_report/<int:report_id>', methods=['GET', 'POST'])
def admin_review_report(report_id):
    if 'user_id' not in session or not is_user_admin(session['user_id']):
        return redirect(url_for('index'))
    db = get_db()
    report = db.execute('SELECT * FROM reported_questions WHERE id = ?', (report_id,)).fetchone()
    if not report:
        flash('Report not found.')
        return redirect(url_for('admin_review_flashcards'))
    
    # Try to get the original question row
    question_row = None
    if report['question_id']:
        question_row = db.execute('SELECT * FROM questions WHERE id = ?', (report['question_id'],)).fetchone()
    
    # Parse distractors from JSON
    distractors = []
    if report['distractors']:
        try:
            distractors = json.loads(report['distractors'])
        except:
            # Handle potential JSON parsing error
            pass
    
    # If POST, handle update or discard
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'discard':
            db.execute('DELETE FROM reported_questions WHERE id = ?', (report_id,))
            db.commit()
            flash('Report discarded.')
            return redirect(url_for('admin_review_flashcards'))
        elif action == 'update':
            # Main question update
            new_question = request.form.get('question', '').strip()
            new_answer = request.form.get('answer', '').strip()
            delete_main = request.form.get('delete_question') == '1'
            
            if question_row:
                # Check if the main question should be deleted
                if delete_main:
                    db.execute('DELETE FROM questions WHERE id = ?', (question_row['id'],))
                    flash('Main question has been deleted.')
                else:
                    # Update the main question if not deleting
                    db.execute('UPDATE questions SET question = ?, answer = ? WHERE id = ?', 
                              (new_question, new_answer, question_row['id']))
            
            # Distractor updates
            for i in range(len(distractors)):
                distractor_id = request.form.get(f'distractor_id_{i}', '')
                delete_distractor = request.form.get(f'delete_distractor_{i}') == '1'
                
                if distractor_id:
                    if delete_distractor:
                        # Delete this distractor
                        db.execute('DELETE FROM questions WHERE id = ?', (distractor_id,))
                        flash(f'Distractor {i+1} has been deleted.')
                    else:
                        # Update this distractor
                        distractor_question = request.form.get(f'distractor_question_{i}', '').strip()
                        distractor_answer = request.form.get(f'distractor_answer_{i}', '').strip()
                        db.execute('UPDATE questions SET question = ?, answer = ? WHERE id = ?', 
                                  (distractor_question, distractor_answer, distractor_id))
            
            db.execute('DELETE FROM reported_questions WHERE id = ?', (report_id,))
            db.commit()
            flash('Changes have been applied and report resolved.')
            return redirect(url_for('admin_review_flashcards'))
    
    return render_template('admin_review_report.html', report=report, question_row=question_row, distractors=distractors)

@app.route('/admin_review_pdf_request/<int:request_id>', methods=['GET', 'POST'])
def admin_review_pdf_request(request_id):
    if 'user_id' not in session or not is_user_admin(session['user_id']):
        return redirect(url_for('index'))
    db = get_db()
    req = db.execute('SELECT * FROM requests_to_access WHERE id = ?', (request_id,)).fetchone()
    if not req:
        flash('PDF access request not found.')
        return redirect(url_for('admin_review_flashcards'))
    if request.method == 'POST':
        action = request.form.get('action')
        discord_id = req['discord_id']
        # Remove the request from the DB
        db.execute('DELETE FROM requests_to_access WHERE id = ?', (request_id,))
        db.commit()
        if action == 'approve':
            # Add to whitelist.json user_ids if not already present
            whitelist_path = os.path.join(os.path.dirname(__file__), 'whitelist.json')
            with open(whitelist_path, 'r') as f:
                whitelist = json.load(f)
            user_ids = set(whitelist.get('user_ids', []))
            if int(discord_id) not in user_ids:
                user_ids.add(int(discord_id))
                whitelist['user_ids'] = list(user_ids)
                with open(whitelist_path, 'w') as f:
                    json.dump(whitelist, f, indent=2)
            flash('Request approved and user added to whitelist.')
        else:
            flash('Request denied and deleted.')
        return redirect(url_for('admin_review_flashcards'))
    return render_template('admin_review_pdf_request.html', req=req)

@app.template_filter('datetimeformat')
def datetimeformat_filter(value):
    try:
        return datetime.utcfromtimestamp(int(value)).strftime('%Y-%m-%d %H:%M')
    except Exception:
        return value

@app.before_request
def enforce_session_version():
    if 'session_version' not in session or session['session_version'] != SESSION_VERSION:
        session.clear()
        # Only clear once, then set version to avoid infinite loop
        session['session_version'] = SESSION_VERSION

def is_user_admin(user_id):
    with open('whitelist.json', 'r') as f:
        whitelist = json.load(f)
    return int(user_id) in whitelist.get('admin_ids', [])


# Add this after your is_user_admin definition (or anywhere after app = Flask(__name__))
@app.context_processor
def inject_is_user_admin():
    return dict(is_user_admin=is_user_admin)

# --- Token Signing Utilities ---
SECRET_TOKEN_KEY = os.getenv('TOKEN_SECRET_KEY', 'dev_token_secret')
TOKEN_EXPIRY_SECONDS = 600  # 10 minutes

def generate_signed_token(question_id, user_id):
    """Generate a signed token containing question_id, user_id, and timestamp."""
    timestamp = int(time.time())
    payload = f"{question_id}:{user_id}:{timestamp}"
    signature = hmac.new(SECRET_TOKEN_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode()
    return token

def verify_signed_token(token, user_id):
    """Verify the token's signature and expiry. Returns (question_id, valid)"""
    try:
        decoded = base64.urlsafe_b64decode(token.encode()).decode()
        parts = decoded.split(":")
        if len(parts) != 4:
            return None, False
        question_id, token_user_id, timestamp, signature = parts
        if str(user_id) != token_user_id:
            return None, False
        payload = f"{question_id}:{token_user_id}:{timestamp}"
        expected_sig = hmac.new(SECRET_TOKEN_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None, False
        # If you care about expiry
        # if int(time.time()) - int(timestamp) > TOKEN_EXPIRY_SECONDS:
        #     return None, False
        return question_id, True
    except Exception:
        return None, False


if __name__ == '__main__':
    init_db()
    # Enable HTTP for local development
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    app.run(host='127.0.0.1', debug=True, port=2456)

