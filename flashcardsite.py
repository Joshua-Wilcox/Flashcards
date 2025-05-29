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
import stripe

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
    
    # Get PDFs by tags
    placeholders = ','.join('?' * len(tag_names))
    tag_rows = db.execute(f'''
        SELECT p.path, SUM(pt.count) as tag_count, p.module_id, p.topic_id, p.subtopic_id
        FROM pdfs p
        JOIN pdf_tags pt ON p.id = pt.pdf_id
        JOIN tags t ON pt.tag_id = t.id
        WHERE t.name IN ({placeholders})
        GROUP BY p.id
        ORDER BY tag_count DESC
    ''', tag_names).fetchall()
    
    # Get module, topic, and subtopic names to enhance the results
    results = []
    for row in tag_rows:
        pdf_info = {'path': row['path'], 'name': os.path.basename(row['path'])}
        
        # Add module name if available
        if row['module_id']:
            module_row = db.execute('SELECT name FROM modules WHERE id = ?', (row['module_id'],)).fetchone()
            if module_row:
                pdf_info['module'] = module_row['name']
        
        # Add topic name if available
        if row['topic_id']:
            topic_row = db.execute('SELECT name FROM topics WHERE id = ?', (row['topic_id'],)).fetchone()
            if topic_row:
                pdf_info['topic'] = topic_row['name']
        
        # Add subtopic name if available
        if row['subtopic_id']:
            subtopic_row = db.execute('SELECT name FROM subtopics WHERE id = ?', (row['subtopic_id'],)).fetchone()
            if subtopic_row:
                pdf_info['subtopic'] = subtopic_row['name']
        
        results.append(pdf_info)
        
    return results

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
    show_payment_widget = False
    
    # Only check for payment eligibility if the user is logged in
    if 'user_id' in session:
        show_payment_widget = user_has_enough_answers(session['user_id'], minimum=10)
    
    return render_template('index.html',
        modules=[m['name'] for m in modules],
        topics=get_unique_values('topic'),
        subtopics=get_unique_values('subtopic'), 
        NUMBER_OF_DISTRACTORS=NUMBER_OF_DISTRACTORS,
        payment_options=[1, 3, 5],  # Add payment options to template context
        default_payment=1,  # Set default to £1
        show_payment_widget=show_payment_widget)  # Pass this to template

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

def get_pdfs_for_question(question_id, max_pdfs=3):
    """
    Find relevant PDFs for a question, prioritizing by:
    1. Module + Topic + Subtopic match (95%)
    2. Module + Topic match (80%)
    3. Module match (60%)
    4. Tag matches (20-50% based on tag overlap)
    Returns a maximum of max_pdfs PDFs with match percentages.
    """
    db = get_db()
    question = db.execute('SELECT module_id FROM questions WHERE id = ?', (question_id,)).fetchone()
    if not question:
        return []
    
    module_id = question['module_id']
    
    # Get topic and subtopic for the question
    topic_rows = db.execute('''
        SELECT topic_id FROM question_topics WHERE question_id = ?
    ''', (question_id,)).fetchall()
    topic_ids = [row['topic_id'] for row in topic_rows]
    
    subtopic_rows = db.execute('''
        SELECT subtopic_id FROM question_subtopics WHERE question_id = ?
    ''', (question_id,)).fetchall()
    subtopic_ids = [row['subtopic_id'] for row in subtopic_rows]
    
    results = []
    
    # Priority 1: Module + Topic + Subtopic match (100% match)
    if topic_ids and subtopic_ids:
        for topic_id in topic_ids:
            for subtopic_id in subtopic_ids:
                pdfs = db.execute('''
                    SELECT p.id, p.path, p.module_id, p.topic_id, p.subtopic_id, 
                           m.name as module_name, t.name as topic_name, s.name as subtopic_name
                    FROM pdfs p
                    LEFT JOIN modules m ON p.module_id = m.id
                    LEFT JOIN topics t ON p.topic_id = t.id
                    LEFT JOIN subtopics s ON p.subtopic_id = s.id
                    WHERE p.module_id = ? AND p.topic_id = ? AND p.subtopic_id = ?
                    LIMIT ?
                ''', (module_id, topic_id, subtopic_id, max_pdfs)).fetchall()
                
                for pdf in pdfs:
                    pdf_info = {
                        'path': pdf['path'],
                        'name': os.path.basename(pdf['path']),
                        'module': pdf['module_name'],
                        'topic': pdf['topic_name'],
                        'subtopic': pdf['subtopic_name'],
                        'match_percent': 100  # Exact module, topic, subtopic match
                    }
                    if pdf_info not in results:
                        results.append(pdf_info)
                        if len(results) >= max_pdfs:
                            return sorted(results, key=lambda x: x.get('match_percent', 0), reverse=True)
    
    # Priority 2: Module + Topic match (80% match)
    if topic_ids and len(results) < max_pdfs:
        for topic_id in topic_ids:
            pdfs = db.execute('''
                SELECT p.id, p.path, p.module_id, p.topic_id, p.subtopic_id,
                       m.name as module_name, t.name as topic_name, s.name as subtopic_name
                FROM pdfs p
                LEFT JOIN modules m ON p.module_id = m.id
                LEFT JOIN topics t ON p.topic_id = t.id
                LEFT JOIN subtopics s ON p.subtopic_id = s.id
                WHERE p.module_id = ? AND p.topic_id = ? AND p.subtopic_id IS NULL
                LIMIT ?
            ''', (module_id, topic_id, max_pdfs - len(results))).fetchall()
            
            for pdf in pdfs:
                pdf_info = {
                    'path': pdf['path'],
                    'name': os.path.basename(pdf['path']),
                    'module': pdf['module_name'],
                    'topic': pdf['topic_name'],
                    'subtopic': pdf['subtopic_name'],
                    'match_percent': 80  # Module and topic match
                }
                if not any(r['path'] == pdf_info['path'] for r in results):
                    results.append(pdf_info)
                    if len(results) >= max_pdfs:
                        return sorted(results, key=lambda x: x.get('match_percent', 0), reverse=True)
    
    # Priority 3: Module match (70% match)
    if len(results) < max_pdfs:
        pdfs = db.execute('''
            SELECT p.id, p.path, p.module_id, p.topic_id, p.subtopic_id,
                   m.name as module_name, t.name as topic_name, s.name as subtopic_name
            FROM pdfs p
            LEFT JOIN modules m ON p.module_id = m.id
            LEFT JOIN topics t ON p.topic_id = t.id
            LEFT JOIN subtopics s ON p.subtopic_id = s.id
            WHERE p.module_id = ? AND p.topic_id IS NULL
            LIMIT ?
        ''', (module_id, max_pdfs - len(results))).fetchall()
        
        for pdf in pdfs:
            pdf_info = {
                'path': pdf['path'],
                'name': os.path.basename(pdf['path']),
                'module': pdf['module_name'],
                'topic': pdf['topic_name'],
                'subtopic': pdf['subtopic_name'],
                'match_percent': 70  # Only module matches
            }
            if not any(r['path'] == pdf_info['path'] for r in results):
                results.append(pdf_info)
                if len(results) >= max_pdfs:
                    return sorted(results, key=lambda x: x.get('match_percent', 0), reverse=True)
    
    # Priority 4: Tag matches (20-50% match based on tag overlap)
    if len(results) < max_pdfs:
        tag_names = get_tags_for_question(question_id)
        
        if tag_names:
            # Get all PDFs with tag matches and their tag counts
            placeholders = ','.join('?' * len(tag_names))
            tag_pdfs = db.execute(f'''
                SELECT p.id, p.path, p.module_id, p.topic_id, p.subtopic_id,
                       m.name as module_name, t.name as topic_name, s.name as subtopic_name,
                       COUNT(pt.tag_id) as matching_tags,
                       (SELECT COUNT(*) FROM pdf_tags WHERE pdf_id = p.id) as total_pdf_tags
                FROM pdfs p
                JOIN pdf_tags pt ON p.id = pt.pdf_id
                JOIN tags tag ON pt.tag_id = tag.id
                LEFT JOIN modules m ON p.module_id = m.id
                LEFT JOIN topics t ON p.topic_id = t.id
                LEFT JOIN subtopics s ON p.subtopic_id = s.id
                WHERE tag.name IN ({placeholders})
                GROUP BY p.id
                ORDER BY matching_tags DESC
                LIMIT ?
            ''', tag_names + [max_pdfs - len(results)]).fetchall()
            
            # Get total number of question tags for calculating match percentage
            total_question_tags = len(tag_names)
            
            for pdf in tag_pdfs:
                # Calculate tag match percentage: 40% base + up to 30% based on tag overlap
                matching_tags = pdf['matching_tags']
                total_pdf_tags = max(pdf['total_pdf_tags'], 1) # Avoid division by zero
                
                # Calculate tag overlap ratio (matching tags / total tags across both)
                tag_overlap = matching_tags / (total_question_tags + total_pdf_tags - matching_tags)
                
                # Calculate match percentage: 40% base + up to 30% based on tag overlap
                match_percent = 40 + min(30, int(60 * tag_overlap))
                
                pdf_info = {
                    'path': pdf['path'],
                    'name': os.path.basename(pdf['path']),
                    'module': pdf['module_name'],
                    'topic': pdf['topic_name'],
                    'subtopic': pdf['subtopic_name'],
                    'match_percent': match_percent,  # Tag-based match
                    'matching_tags': matching_tags
                }
                
                if not any(r['path'] == pdf_info['path'] for r in results):
                    results.append(pdf_info)
                    if len(results) >= max_pdfs:
                        break
    
    # Sort by match percentage (highest first)
    return sorted(results, key=lambda x: x.get('match_percent', 0), reverse=True)

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
    
    # Get initial PDFs for the question (max 3)
    pdfs = get_pdfs_for_question(qid, max_pdfs=3)
    
    topics_list = get_topics_for_question(qid)
    subtopics_list = get_subtopics_for_question(qid)
    module_display = get_module_name_by_id(db, row['module_id'])
    correct_answer = row['answer']
    answers = [correct_answer]
    answer_ids = [qid]
    # Distractor logic: pick random answers from other questions in the same module
    distractors_needed = NUMBER_OF_DISTRACTORS
    # Get all possible distractors in the same module (excluding this question)
    distractor_candidates = db.execute('''
        SELECT q.id, q.answer
        FROM questions q
        WHERE q.module_id = ? AND q.id != ?
    ''', (row['module_id'], qid)).fetchall()

    # Gather metadata for the current question
    question_tags = set(tags)
    question_subtopics = set(subtopics_list)
    question_topics = set(topics_list)
    correct_answer = row['answer']

    # Build metadata for all candidates
    scored_candidates = []
    used_answers = set([correct_answer])
    for cand in distractor_candidates:
        cand_id = cand['id']
        cand_answer = cand['answer']
        if not cand_answer or cand_answer in used_answers:
            continue  # No duplicates
        cand_tags = set(get_tags_for_question(cand_id))
        cand_subtopics = set(get_subtopics_for_question(cand_id))
        cand_topics = set(get_topics_for_question(cand_id))
        # Score: tags (weight 3), subtopic (weight 2), topic (weight 1)
        tag_score = len(question_tags & cand_tags)
        subtopic_score = len(question_subtopics & cand_subtopics)
        topic_score = len(question_topics & cand_topics)
        total_score = tag_score * 3 + subtopic_score * 2 + topic_score
        scored_candidates.append({
            'id': cand_id,
            'answer': cand_answer,
            'score': total_score,
            'tag_score': tag_score,
            'subtopic_score': subtopic_score,
            'topic_score': topic_score
        })

    # Sort by score (desc), then randomize within ties
    random.shuffle(scored_candidates)
    scored_candidates.sort(key=lambda x: (x['score'], x['tag_score'], x['subtopic_score'], x['topic_score']), reverse=True)

    # Select top N unique distractors
    distractor_answers = []
    distractor_ids = []
    for cand in scored_candidates:
        if len(distractor_answers) >= distractors_needed:
            break
        if cand['answer'] not in used_answers:
            distractor_answers.append(cand['answer'])
            distractor_ids.append(cand['id'])
            used_answers.add(cand['answer'])

    # If not enough, fill with random (but unique) from module
    if len(distractor_answers) < distractors_needed:
        remaining = [c for c in distractor_candidates if c['answer'] not in used_answers and c['answer']]
        random.shuffle(remaining)
        for cand in remaining:
            if len(distractor_answers) >= distractors_needed:
                break
            distractor_answers.append(cand['answer'])
            distractor_ids.append(cand['id'])
            used_answers.add(cand['answer'])

    # Final answer list: correct + distractors, shuffled
    answers = [correct_answer] + distractor_answers
    answer_ids = [qid] + distractor_ids
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

# Add a new route for on-demand PDF loading
@app.route('/load_pdfs_by_tags', methods=['POST'])
def load_pdfs_by_tags():
    if 'user_id' not in session:
        return jsonify({'error': 'You must be logged in'}), 401
    
    data = request.get_json()
    question_id = data.get('question_id')
    
    if not question_id:
        return jsonify({'error': 'Missing question ID'}), 400
    
    # Get PDFs for the question (max 3)
    pdfs = get_pdfs_for_question(question_id, max_pdfs=3)
    
    return jsonify({'pdfs': pdfs})

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
            
            # Increment the user's approved cards counter
            user_id = submission['user_id']
            
            # Update global approved cards counter
            db.execute('''
                UPDATE user_stats 
                SET approved_cards = COALESCE(approved_cards, 0) + 1 
                WHERE user_id = ?
            ''', (user_id,))
            
            # First check if the module_stats entry exists
            row = db.execute('SELECT 1 FROM module_stats WHERE user_id = ? AND module_id = ?', 
                            (user_id, module_id)).fetchone()
            
            if row:
                # Update existing entry - increment the approved_cards counter
                db.execute('''
                    UPDATE module_stats
                    SET approved_cards = COALESCE(approved_cards, 0) + 1
                    WHERE user_id = ? AND module_id = ?
                ''', (user_id, module_id))
            else:
                # Insert new entry with approved_cards = 1
                db.execute('''
                    INSERT INTO module_stats
                    (user_id, module_id, number_answered, number_correct, last_answered_time, current_streak, approved_cards)
                    VALUES (?, ?, 0, 0, NULL, 0, 1)
                ''', (user_id, module_id))
            
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
    
    # Get the correct answer from the database based on the question text
    if question:
        row = db.execute('SELECT id, answer FROM questions WHERE question = ?', (question,)).fetchone()
        if row:
            question_id = row['id']
            # Override the provided answer with the actual correct answer from the database
            answer = row['answer']
    
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
    stats = db.execute('SELECT correct_answers, total_answers, current_streak FROM user_stats WHERE user_id = ?', (user_id,)).fetchone()
    if stats:
        correct = stats['correct_answers'] or 0
        total = stats['total_answers'] or 0
        streak = stats['current_streak'] if 'current_streak' in stats.keys() else 0
    else:
        correct = 0
        total = 0
        streak = 0
    
    total += 1
    # Use Europe/London timezone for last_answer_time
    london_tz = pytz.timezone('Europe/London')
    now_london = datetime.now(london_tz)
    last_answer_time = int(now_london.timestamp())
    
    # Update module stats in normalized table only
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

    # Update overall stats based on aggregated module stats
    if is_correct:
        correct += 1
        streak += 1
        db.execute('INSERT OR IGNORE INTO used_tokens (user_id, token, used_at) VALUES (?, ?, ?)', (user_id, token, last_answer_time))
    else:
        streak = 0
        
    # Update overall user stats
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
    order_sql = 'DESC' if order == 'desc' else 'ASC'
    db = get_db()
    
    # Check if the approved_cards column exists in the user_stats table
    # If not, we need to execute the schema update first
    cursor = db.cursor()
    columns = [column[1] for column in cursor.execute('PRAGMA table_info(user_stats)').fetchall()]
    if 'approved_cards' not in columns:
        db.execute('ALTER TABLE user_stats ADD COLUMN approved_cards INTEGER DEFAULT 0')
        db.commit()
    
    # Also check module_stats table and add the column if it doesn't exist
    columns = [column[1] for column in cursor.execute('PRAGMA table_info(module_stats)').fetchall()]
    if 'approved_cards' not in columns:
        db.execute('ALTER TABLE module_stats ADD COLUMN approved_cards INTEGER DEFAULT 0')
        db.commit()
    
    if not module_filter:
        # Define sort columns for global stats
        allowed = {
            'correct_answers': 'correct_answers',
            'total_answers': 'total_answers',
            'accuracy': '(CASE WHEN total_answers > 0 THEN 1.0 * correct_answers / total_answers ELSE 0 END)',
            'current_streak': 'current_streak',
            'last_answer_time': 'last_answer_time',
            'approved_cards': 'approved_cards'
        }
        sort_col = allowed.get(sort, 'correct_answers')
        
        # Use SQL sorting for global stats
        users = db.execute(f'''
            SELECT user_id, username, correct_answers, total_answers, current_streak, last_answer_time,
                (CASE WHEN total_answers > 0 THEN 1.0 * correct_answers / total_answers ELSE 0 END) as accuracy,
                COALESCE(approved_cards, 0) as approved_cards
            FROM user_stats
            WHERE total_answers != 0
            ORDER BY {sort_col} {order_sql}, total_answers DESC
        ''').fetchall()
    else:
        # Define sort columns for module-specific stats - using the correct field names
        allowed = {
            'correct_answers': 'COALESCE(ms.number_correct, 0)',
            'total_answers': 'COALESCE(ms.number_answered, 0)',
            'accuracy': '(CASE WHEN COALESCE(ms.number_answered, 0) > 0 THEN 1.0 * COALESCE(ms.number_correct, 0) / COALESCE(ms.number_answered, 1) ELSE 0 END)',
            'current_streak': 'COALESCE(ms.current_streak, 0)',
            'last_answer_time': 'ms.last_answered_time',
            'approved_cards': 'COALESCE(ms.approved_cards, 0)'
        }
        sort_col = allowed.get(sort, 'COALESCE(ms.number_correct, 0)')
        
        # Get stats for specific module directly from module_stats table
        users = db.execute(f'''
            SELECT us.user_id, us.username, 
               COALESCE(ms.number_correct, 0) as correct_answers,
               COALESCE(ms.number_answered, 0) as total_answers,
               COALESCE(ms.current_streak, 0) as current_streak,
               ms.last_answered_time as last_answer_time,
               (CASE WHEN COALESCE(ms.number_answered, 0) > 0 
                 THEN 1.0 * COALESCE(ms.number_correct, 0) / COALESCE(ms.number_answered, 1) 
                 ELSE 0 END) as accuracy,
               COALESCE(ms.approved_cards, 0) as approved_cards
            FROM user_stats us
            LEFT JOIN modules m ON m.name = ?
            LEFT JOIN module_stats ms ON ms.user_id = us.user_id AND ms.module_id = m.id
            WHERE COALESCE(ms.number_answered, 0) != 0
            ORDER BY {sort_col} {order_sql}, COALESCE(ms.number_answered, 0) DESC
        ''', (module_filter,)).fetchall()


    # Convert DB rows to dictionaries for the template
    leaderboard = [dict(row) for row in users]
    
    modules = get_all_modules()
    return render_template('leaderboard.html', leaderboard=leaderboard, sort=sort, order=order, modules=modules, active_module=module_filter)

@app.route('/user_stats/<user_id>')
def user_stats(user_id):
    module_filter = request.args.get('module', None)
    db = get_db()
    
    # Get base user stats
    base_stats = db.execute('''
        SELECT user_id, username, correct_answers, total_answers, 
               last_answer_time, current_streak, approved_cards
        FROM user_stats 
        WHERE user_id = ?
    ''', (user_id,)).fetchone()
    
    if not base_stats:
        return redirect(url_for('index'))
    
    # Get module stats
    module_stats = db.execute('''
        SELECT m.name, ms.number_answered, ms.number_correct, 
               ms.last_answered_time, ms.current_streak, ms.approved_cards
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
            'current_streak': row['current_streak'] or 0,
            'approved_cards': row['approved_cards'] or 0
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
               last_answer_time, current_streak, approved_cards
        FROM user_stats 
        WHERE user_id = ?
    ''', (session['user_id'],)).fetchone()
    
    # Get module stats
    module_stats = db.execute('''
        SELECT m.name, ms.number_answered, ms.number_correct, 
               ms.last_answered_time, ms.current_streak, ms.approved_cards
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
            'current_streak': row['current_streak'] or 0,
            'approved_cards': row['approved_cards'] or 0
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


# Add these new API routes for auto-suggestions
@app.route('/api/suggest/topics', methods=['POST'])
def suggest_topics():
    if not discord.authorized:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    module_name = data.get('module', '')
    query = data.get('query', '').lower()
    
    if not module_name:
        return jsonify({'suggestions': []})
    
    db = get_db()
    
    # Get module ID
    module_row = db.execute('SELECT id FROM modules WHERE name = ?', (module_name,)).fetchone()
    if not module_row:
        return jsonify({'suggestions': []})
    
    module_id = module_row['id']
    
    # Get topics for this module with occurrence count
    if query:
        topics = db.execute('''
            SELECT t.name, COUNT(qt.question_id) as count
            FROM topics t
            JOIN question_topics qt ON t.id = qt.topic_id
            JOIN questions q ON qt.question_id = q.id
            WHERE q.module_id = ? AND LOWER(t.name) LIKE ?
            GROUP BY t.name
            ORDER BY count DESC, t.name
            LIMIT 10
        ''', (module_id, f'%{query}%')).fetchall()
    else:
        topics = db.execute('''
            SELECT t.name, COUNT(qt.question_id) as count
            FROM topics t
            JOIN question_topics qt ON t.id = qt.topic_id
            JOIN questions q ON qt.question_id = q.id
            WHERE q.module_id = ?
            GROUP BY t.name
            ORDER BY count DESC, t.name
            LIMIT 10
        ''', (module_id,)).fetchall()
    
    suggestions = [{'name': row['name'], 'count': row['count']} for row in topics]
    return jsonify({'suggestions': suggestions})

@app.route('/api/suggest/subtopics', methods=['POST'])
def suggest_subtopics():
    if not discord.authorized:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    module_name = data.get('module', '')
    topic_name = data.get('topic', '')
    query = data.get('query', '').lower()
    
    if not module_name or not topic_name:
        return jsonify({'suggestions': []})
    
    db = get_db()
    
    # Get module ID
    module_row = db.execute('SELECT id FROM modules WHERE name = ?', (module_name,)).fetchone()
    if not module_row:
        return jsonify({'suggestions': []})
    
    module_id = module_row['id']
    
    # Get topic ID
    topic_row = db.execute('SELECT id FROM topics WHERE name = ?', (topic_name,)).fetchone()
    if not topic_row:
        return jsonify({'suggestions': []})
    
    topic_id = topic_row['id']
    
    # Get subtopics for this module and topic with occurrence count
    if query:
        subtopics = db.execute('''
            SELECT s.name, COUNT(qs.question_id) as count
            FROM subtopics s
            JOIN question_subtopics qs ON s.id = qs.subtopic_id
            JOIN questions q ON qs.question_id = q.id
            JOIN question_topics qt ON q.id = qt.question_id
            WHERE q.module_id = ? AND qt.topic_id = ? AND LOWER(s.name) LIKE ?
            GROUP BY s.name
            ORDER BY count DESC, s.name
            LIMIT 10
        ''', (module_id, topic_id, f'%{query}%')).fetchall()
    else:
        subtopics = db.execute('''
            SELECT s.name, COUNT(qs.question_id) as count
            FROM subtopics s
            JOIN question_subtopics qs ON s.id = qs.subtopic_id
            JOIN questions q ON qs.question_id = q.id
            JOIN question_topics qt ON q.id = qt.question_id
            WHERE q.module_id = ? AND qt.topic_id = ?
            GROUP BY s.name
            ORDER BY count DESC, s.name
            LIMIT 10
        ''', (module_id, topic_id)).fetchall()
    
    suggestions = [{'name': row['name'], 'count': row['count']} for row in subtopics]
    return jsonify({'suggestions': suggestions})

@app.route('/api/suggest/tags', methods=['POST'])
def suggest_tags():
    if not discord.authorized:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    module_name = data.get('module', '')
    topic_name = data.get('topic', '')
    subtopic_name = data.get('subtopic', '')
    query = data.get('query', '').lower()
    
    if not module_name:
        return jsonify({'suggestions': []})
    
    db = get_db()
    
    # Get module ID
    module_row = db.execute('SELECT id FROM modules WHERE name = ?', (module_name,)).fetchone()
    if not module_row:
        return jsonify({'suggestions': []})
    
    module_id = module_row['id']
    
    # Base query to get tags for this module
    sql = '''
        SELECT t.name, COUNT(qt.question_id) as count
        FROM tags t
        JOIN question_tags qt ON t.id = qt.tag_id
        JOIN questions q ON qt.question_id = q.id
        WHERE q.module_id = ?
    '''
    params = [module_id]
    
    # Add topic filter if provided
    if topic_name:
        sql += '''
            AND EXISTS (
                SELECT 1 FROM question_topics qtop
                JOIN topics top ON qtop.topic_id = top.id
                WHERE qtop.question_id = q.id AND top.name = ?
            )
        '''
        params.append(topic_name)
    
    # Add subtopic filter if provided
    if subtopic_name:
        sql += '''
            AND EXISTS (
                SELECT 1 FROM question_subtopics qsub
                JOIN subtopics sub ON qsub.subtopic_id = sub.id
                WHERE qsub.question_id = q.id AND sub.name = ?
            )
        '''
        params.append(subtopic_name)
    
    # Add query filter if provided
    if query:
        sql += ' AND LOWER(t.name) LIKE ?'
        params.append(f'%{query}%')
    
    # Finalize the query
    sql += '''
        GROUP BY t.name
        ORDER BY count DESC, t.name
        LIMIT 10
    '''
    
    tags = db.execute(sql, params).fetchall()
    suggestions = [{'name': row['name'], 'count': row['count']} for row in tags]
    return jsonify({'suggestions': suggestions})

# Update the check_duplicates endpoint to use the enhanced method
@app.route('/api/check_duplicates', methods=['POST'])
def check_duplicates():
    """
    Check for potential duplicate questions in the same module using semantic similarity.
    Returns a list of similar questions if any are found.
    """
    if not discord.authorized:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    question_text = data.get('question', '').strip()
    module_name = data.get('module', '')
    
    if not question_text or not module_name or len(question_text) < 10:
        return jsonify({'duplicates': []})
    
    db = get_db()
    
    # Get module ID
    module_row = db.execute('SELECT id FROM modules WHERE name = ?', (module_name,)).fetchone()
    if not module_row:
        return jsonify({'duplicates': []})
    
    module_id = module_row['id']
    
    # Find semantically similar questions
    potential_duplicates = find_semantic_duplicates(db, question_text, module_id)
    
    return jsonify({'duplicates': potential_duplicates})

def find_semantic_duplicates(db, question_text, module_id, limit=5, threshold=0.3):
    """
    Enhanced semantic duplicate detection using TF-IDF and cosine similarity
    to better understand the meaning behind questions.
    
    Args:
        db: Database connection
        question_text: The question to check for duplicates
        module_id: The module to search within
        limit: Maximum number of duplicates to return
        threshold: Minimum similarity score to consider a match
    
    Returns:
        List of potential duplicate questions with similarity scores
    """
    from collections import Counter
    import math
    
    # Step 1: Get all questions in the same module
    rows = db.execute('''
        SELECT id, question, answer
        FROM questions
        WHERE module_id = ?
    ''', (module_id,)).fetchall()
    
    if not rows:
        return []
    
    # Create a list of all documents (questions) to process
    docs = [row['question'] for row in rows]
    
    # Add the input question to the end
    docs.append(question_text)
    
    # Step 2: Preprocess all documents
    processed_docs = []
    stop_words = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'about', 
                 'as', 'of', 'and', 'or', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 
                 'have', 'has', 'had', 'do', 'does', 'did', 'what', 'when', 'where', 'why', 
                 'how', 'which', 'who', 'whom', 'this', 'that', 'these', 'those'}
    
    for doc in docs:
        # Convert to lowercase
        doc_lower = doc.lower()
        
        # Remove punctuation
        for char in '.,?!;:()[]{}""\'':
            doc_lower = doc_lower.replace(char, ' ')
        
        # Tokenize and remove stop words and short words
        tokens = [word for word in doc_lower.split() if word not in stop_words and len(word) > 2]
        
        # Stem words (simple implementation - just take first 6 chars)
        # This isn't as good as a real stemmer but helps with basic word forms
        stemmed = [word[:6] for word in tokens if len(word) > 3]
        
        processed_docs.append(stemmed)
    
    # Step 3: Calculate TF-IDF vectors
    # First, get document frequency for each term
    term_doc_freq = Counter()
    all_terms = set()
    
    for doc in processed_docs:
        terms = set(doc)  # Unique terms in this document
        for term in terms:
            term_doc_freq[term] += 1
            all_terms.add(term)
    
    num_docs = len(processed_docs)
    
    # Calculate IDF for each term
    idf = {term: math.log(num_docs / (1 + term_doc_freq[term])) for term in all_terms}
    
    # Calculate TF-IDF vector for each document
    tfidf_vectors = []
    
    for doc in processed_docs:
        # Calculate term frequency in this document
        tf = Counter(doc)
        # Normalize by document length
        doc_len = len(doc) or 1  # Avoid division by zero
        
        # Calculate TF-IDF for each term
        doc_vector = {term: (tf[term] / doc_len) * idf.get(term, 0) for term in all_terms}
        tfidf_vectors.append(doc_vector)
    
    # Step 4: Calculate cosine similarity between the input question and all others
    input_vector = tfidf_vectors[-1]  # The last one is our input question
    input_magnitude = math.sqrt(sum(val**2 for val in input_vector.values()))
    
    similarities = []
    
    for i, doc_vector in enumerate(tfidf_vectors[:-1]):  # Skip the last one (input question)
        # Calculate dot product
        dot_product = sum(input_vector.get(term, 0) * doc_vector.get(term, 0) for term in all_terms)
        
        # Calculate magnitude of document vector
        doc_magnitude = math.sqrt(sum(val**2 for val in doc_vector.values()))
        
        # Calculate cosine similarity
        similarity = 0
        if input_magnitude > 0 and doc_magnitude > 0:  # Avoid division by zero
            similarity = dot_product / (input_magnitude * doc_magnitude)
        
        similarities.append((i, similarity))
    
    # Step 5: Return the top matches above the threshold
    top_matches = sorted(similarities, key=lambda x: x[1], reverse=True)[:limit]
    
    results = []
    for idx, score in top_matches:
        if score >= threshold:  # Only include matches above the threshold
            row = rows[idx]
            results.append({
                'id': row['id'],
                'question': row['question'],
                'answer': row['answer'],
                'similarity': score
            })
    
    return results

# Add a text similarity function for more holistic comparison
def get_text_similarity(text1, text2):
    """
    Calculate text similarity using a combination of:
    1. Character n-gram overlap (catches typos and small rewrites)
    2. Word overlap (semantic meaning)
    3. Word order similarity (sentence structure)
    
    Returns a similarity score between 0 and 1
    """
    if not text1 or not text2:
        return 0.0
        
    # Normalize both texts
    text1 = text1.lower().strip()
    text2 = text2.lower().strip()
    
    # Quick equality check
    if text1 == text2:
        return 1.0
        
    # Remove punctuation
    for char in '.,?!;:()[]{}""\'':
        text1 = text1.replace(char, ' ')
        text2 = text2.replace(char, ' ')
    
    # Split into words
    words1 = [w for w in text1.split() if len(w) > 2]
    words2 = [w for w in text2.split() if len(w) > 2]
    
    if not words1 or not words2:
        return 0.0
    
    # 1. Word set similarity (Jaccard)
    set1 = set(words1)
    set2 = set(words2)
    jaccard = len(set1.intersection(set2)) / len(set1.union(set2)) if set1 or set2 else 0
    
    # 2. Character trigram similarity
    def get_trigrams(text):
        return [text[i:i+3] for i in range(len(text)-2) if len(text[i:i+3].strip()) == 3]
        
    trigrams1 = set(get_trigrams(' '.join(words1)))
    trigrams2 = set(get_trigrams(' '.join(words2)))
    trigram_sim = len(trigrams1.intersection(trigrams2)) / len(trigrams1.union(trigrams2)) if trigrams1 or trigrams2 else 0
    
    # 3. Sequence similarity (difflib)
    seq_sim = difflib.SequenceMatcher(None, text1, text2).ratio()
    
    # 4. Word order similarity using difflib on words
    word_order_sim = difflib.SequenceMatcher(None, words1, words2).ratio()
    
    # Weight and combine the similarities
    # Adjust weights based on importance
    final_sim = (jaccard * 0.3) + (trigram_sim * 0.2) + (seq_sim * 0.2) + (word_order_sim * 0.3)
    
    return final_sim

# After your app configuration, set your Stripe API key
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY")
# Remove explicit API version setting as it may be causing compatibility issues

# Add this context processor to make the Stripe publishable key available in templates
@app.context_processor
def inject_stripe_key():
    return dict(stripe_publishable_key=STRIPE_PUBLISHABLE_KEY)

# Update this route to handle creating Stripe checkout sessions with better error handling
@app.route('/create-checkout-session', methods=['POST'])
def create_checkout_session():
    if 'user_id' not in session:
        return jsonify({'error': 'You must be logged in'}), 401
    
    try:
        data = request.json
        
        # Validate amount is provided and is a positive number
        if not data or 'amount' not in data:
            return jsonify({'error': 'Amount is required'}), 400
            
        # Parse amount and ensure it's an integer
        try:
            amount = int(data.get('amount', 1))
        except (ValueError, TypeError):
            # If amount can't be parsed as an integer, default to £1
            amount = 1
        
        # Enforce minimum amount of £1
        amount = max(1, amount)
        
        # Log the request to help with debugging
        print(f"Creating checkout session for amount: £{amount}")
        
        # Create a checkout session with only the card payment method for maximum compatibility
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card', 'klarna', 'pay_by_bank', 'samsung_pay', 'afterpay_clearpay', 'revolut_pay', 'paypal'],
            line_items=[{
                'price_data': {
                    'currency': 'gbp',
                    'product_data': {
                        'name': f'Support flashcards.112000000.xyz',
                        'description': 'Thank you so much for considering supporting! This is an indie site so any proceeds will really be appreciated. We support multiple payment methods. Please note that PayPal may apply higher transaction fees on small payments, which reduces the amount we receive.',
                    },
                    'unit_amount': int(amount * 100),  # Convert to pence
                },
                'quantity': 1,
            }],
            mode='payment',
            success_url=request.url_root + 'payment-success',
            cancel_url=request.url_root,
        )
        
        print(f"Checkout session created with ID: {checkout_session.id}")
        return jsonify({'id': checkout_session.id})
    except stripe.error.StripeError as e:
        # These are Stripe-specific errors
        error_msg = str(e)
        print(f"Stripe error occurred: {error_msg}")
        return jsonify({'error': error_msg}), 400
    except Exception as e:
        # For any other unexpected errors
        error_msg = str(e)
        print(f"Unexpected error creating checkout session: {error_msg}")
        return jsonify({'error': error_msg}), 500

# Add a success page route
@app.route('/payment-success')
def payment_success():
    return render_template('payment_success.html')

def user_has_enough_answers(user_id, minimum=10):
    """Check if a user has at least the minimum number of correct answers"""
    if not user_id:
        return False
    
    db = get_db()
    row = db.execute('SELECT correct_answers FROM user_stats WHERE user_id = ?', (user_id,)).fetchone()
    if not row:
        return False
    
    return (row['correct_answers'] or 0) >= minimum

if __name__ == '__main__':
    init_db()
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    app.run(host='127.0.0.1', debug=True, port=2456)