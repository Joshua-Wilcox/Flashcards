from flask import Flask, render_template, jsonify, request, session, redirect, url_for, send_from_directory, flash, render_template_string
from flask_discord import DiscordOAuth2Session
import json
import random
from collections import defaultdict
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
import os
import time
import secrets  # For generating secure tokens
import hashlib  # For creating secure hashes
import threading
import difflib

load_dotenv()  # Load variables from .env

app = Flask(__name__)

# Discord OAuth2 Config
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key")
app.config["DISCORD_CLIENT_ID"] = os.getenv("DISCORD_CLIENT_ID")
app.config["DISCORD_CLIENT_SECRET"] = os.getenv("DISCORD_CLIENT_SECRET")
app.config["DISCORD_REDIRECT_URI"] = os.getenv("DISCORD_REDIRECT_URI")
app.config["DISCORD_OAUTH2_SCOPE"] = ["identify, guilds"]
discord = DiscordOAuth2Session(app)

SESSION_VERSION = 2  # Increment this when you change scopes or session structure


# Database functions
def get_db():
    db = sqlite3.connect('flashcards.db')
    db.row_factory = sqlite3.Row
    return db

def populate_questions_table():
    db = get_db()
    # Check if table exists, create if not
    db.execute('''CREATE TABLE IF NOT EXISTS questions (
        id TEXT PRIMARY KEY, -- hash of the question text
        question TEXT NOT NULL,
        answer TEXT NOT NULL,
        module TEXT,
        topic TEXT,
        subtopic TEXT,
        tags TEXT, -- JSON array
        pdfs TEXT -- JSON array
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
        tags = json.dumps(card.get('Tags', []))
        # Correctly extract PDFs from TexMeta if present
        pdfs = json.dumps(card.get('TexMeta', {}).get('RelatedPDFs', []))
        # Use the same hash as question_id everywhere
        question_id = hashlib.sha256(question_text.encode('utf-8')).hexdigest()
        db.execute('''INSERT OR IGNORE INTO questions (id, question, answer, module, topic, subtopic, tags, pdfs)
                      VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                   (question_id, question_text, answer, module, topic, subtopic, tags, pdfs))
    db.commit()

def init_db():
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()
        populate_questions_table()  # Populate questions table on first run

def get_unique_values(key):
    db = get_db()
    rows = db.execute(f'SELECT DISTINCT {key} FROM questions').fetchall()
    return sorted([row[0] for row in rows if row[0]])

# Helper to get a question row as dict
def question_row_to_dict(row):
    return {
        'id': row['id'],
        'Question': row['question'],
        'Answer': row['answer'],
        'Module': row['module'],
        'Topic': row['topic'],
        'Sub-Topic': row['subtopic'],
        'Tags': json.loads(row['tags']) if row['tags'] else [],
        'PDFs': json.loads(row['pdfs']) if row['pdfs'] else []
    }

# --- PDF Access Control ---

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
    return render_template('index.html',
                         modules=get_unique_values('module'),
                         topics=get_unique_values('topic'),
                         subtopics=get_unique_values('subtopic'))

@app.route('/get_filters', methods=['POST'])
def get_filters():
    selected_module = request.json.get('module')
    selected_topics = request.json.get('topics', [])
    
    db = get_db()
    topics = db.execute('SELECT DISTINCT topic FROM questions WHERE module = ? OR ? IS NULL', (selected_module, selected_module)).fetchall()
    subtopics = db.execute('SELECT DISTINCT subtopic FROM questions WHERE (module = ? OR ? IS NULL) AND (topic IN (%s) OR ? IS NULL)' % ','.join(['?']*len(selected_topics)), [selected_module, selected_module] + selected_topics + [None]).fetchall()
    
    return jsonify({
        'topics': sorted([row[0] for row in topics if row[0]]),
        'subtopics': sorted([row[0] for row in subtopics if row[0]])
    })

@app.route('/get_question', methods=['POST'])
def get_question():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    selected_module = request.json.get('module')
    selected_topics = request.json.get('topics', [])
    selected_subtopics = request.json.get('subtopics', [])

    db = get_db()
    query = 'SELECT * FROM questions WHERE 1=1'
    params = []
    if selected_module:
        query += ' AND module = ?'
        params.append(selected_module)
    if selected_topics:
        query += ' AND topic IN (%s)' % (','.join(['?']*len(selected_topics)))
        params.extend(selected_topics)
    if selected_subtopics:
        query += ' AND subtopic IN (%s)' % (','.join(['?']*len(selected_subtopics)))
        params.extend(selected_subtopics)
    rows = db.execute(query, params).fetchall()
    if not rows:
        return jsonify({'error': 'No cards match the selected filters'})
    question_row = random.choice(rows)
    question_card = question_row_to_dict(question_row)

    # Get similar answers (from DB) with similarity check
    def get_similar_answers_db(correct_card, count=3):
        module_rows = db.execute('SELECT * FROM questions WHERE module = ? AND id != ?', (correct_card['Module'], correct_card['id'])).fetchall()
        # Helper to filter by similarity
        def filter_by_similarity(candidates, already, max_count):
            filtered = []
            for card in candidates:
                ans = card['Answer']
                if all(difflib.SequenceMatcher(None, ans, x).ratio() < 0.8 for x in already):
                    filtered.append(card)
                if len(filtered) == max_count:
                    break
            return filtered
        # 1. Tag matches
        tag_matches = [question_row_to_dict(row) for row in module_rows if set(question_row_to_dict(row)['Tags']) & set(correct_card['Tags'])]
        tag_matches = filter_by_similarity(tag_matches, [correct_card['Answer']], count)
        # 2. Subtopic matches (excluding already chosen)
        if len(tag_matches) < count:
            subtopic_matches = [question_row_to_dict(row) for row in module_rows if question_row_to_dict(row)['Sub-Topic'] == correct_card['Sub-Topic'] and question_row_to_dict(row) not in tag_matches]
            subtopic_matches = filter_by_similarity(subtopic_matches, [correct_card['Answer']] + [c['Answer'] for c in tag_matches], count - len(tag_matches))
            tag_matches.extend(subtopic_matches)
        # 3. Topic matches (excluding already chosen)
        if len(tag_matches) < count:
            topic_matches = [question_row_to_dict(row) for row in module_rows if question_row_to_dict(row)['Topic'] == correct_card['Topic'] and question_row_to_dict(row) not in tag_matches and question_row_to_dict(row) not in subtopic_matches]
            topic_matches = filter_by_similarity(topic_matches, [correct_card['Answer']] + [c['Answer'] for c in tag_matches], count - len(tag_matches))
            tag_matches.extend(topic_matches)
        # 4. Fill with randoms if needed
        attempts = 0
        while len(tag_matches) < count and attempts < 20 and module_rows:
            random_card = question_row_to_dict(random.choice(module_rows))
            ans = random_card['Answer']
            if random_card not in tag_matches and ans != correct_card['Answer']:
                if all(difflib.SequenceMatcher(None, ans, x).ratio() < 0.8 for x in [correct_card['Answer']] + [c['Answer'] for c in tag_matches]):
                    tag_matches.append(random_card)
            attempts += 1
        return [c['Answer'] for c in tag_matches[:count]]

    wrong_answers = get_similar_answers_db(question_card)
    all_answers = wrong_answers + [question_card['Answer']]
    random.shuffle(all_answers)

    # Generate a secure token for this question attempt
    question_hash = question_card['id']
    token, token_hash = generate_question_token(question_hash, session['user_id'])

    # Store the token in the database
    db.execute(
        'INSERT INTO question_tokens (token_hash, user_id, question_id, created_at) VALUES (?, ?, ?, ?)',
        (token_hash, session['user_id'], question_hash, int(time.time()))
    )
    db.commit()

    # Store the current question in the session for answer validation
    session['current_question'] = {
        'question': question_card['Question'],
        'answer': question_card['Answer'],
        'module': question_card['Module'],
        'topic': question_card['Topic'],
        'subtopic': question_card['Sub-Topic'],
        'token': token,
        'id': question_card['id']
    }

    return jsonify({
        'question': question_card['Question'],
        'answers': all_answers,
        'module': question_card['Module'],
        'topic': question_card['Topic'],
        'subtopic': question_card['Sub-Topic'],
        'tags': question_card['Tags'],
        'pdfs': question_card.get('PDFs', []),
        'token': token
    })

@app.route('/check_answer', methods=['POST'])
def check_answer():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'}), 401

    current = session.get('current_question')
    if not current:
        return jsonify({'error': 'No active question'}), 400

    user_answer = request.json.get('answer')
    token = request.json.get('token')  # Get the token from the request
    
    if user_answer is None or token is None:
        return jsonify({'error': 'Missing answer or token'}), 400

    # Verify the token
    if token != current.get('token'):
        return jsonify({'error': 'Invalid token'}), 400

    # Generate the token hash to look up in the database
    question_hash = current['id']
    hash_input = f"{token}:{question_hash}:{session['user_id']}".encode('utf-8')
    token_hash = hashlib.sha256(hash_input).hexdigest()

    # Check if token is valid and unused
    db = get_db()
    token_record = db.execute(
        'SELECT used FROM question_tokens WHERE token_hash = ? AND user_id = ? AND used = 0',
        (token_hash, session['user_id'])
    ).fetchone()

    if not token_record:
        return jsonify({'error': 'Invalid or already used token'}), 400

    is_correct = (user_answer == current['answer'])

    # Only mark the token as used if the answer is correct
    if is_correct:
        db.execute('UPDATE question_tokens SET used = 1 WHERE token_hash = ?', (token_hash,))
        db.execute('''UPDATE user_stats 
                    SET correct_answers = correct_answers + 1,
                        total_answers = total_answers + 1,
                        last_answer_time = ?
                    WHERE user_id = ?''', 
                (int(time.time()), session['user_id']))
        db.commit()
        session.pop('current_question', None)  # Only pop if correct
    else:
        db.execute('''UPDATE user_stats 
                    SET total_answers = total_answers + 1,
                        last_answer_time = ?
                    WHERE user_id = ?''', 
                (int(time.time()), session['user_id']))
        db.commit()
        # Do NOT mark token as used or pop current_question if incorrect

    return jsonify({'correct': is_correct})

@app.route("/login")
def login():
    return discord.create_session(scope=["identify", "guilds"])

@app.route("/callback")
def callback():
    try:
        discord.callback()
        user = discord.fetch_user()
        session['user_id'] = user.id
        session['username'] = f"{user.name}"
        session['session_version'] = SESSION_VERSION  # Set version on login
        # Initialize user in database if not exists
        db = get_db()
        db.execute('''INSERT OR IGNORE INTO user_stats (user_id, username) 
                      VALUES (?, ?)''', (user.id, session['username']))
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
    # Only allow certain columns to be sorted
    allowed = {
        'correct_answers': 'correct_answers',
        'total_answers': 'total_answers',
        'accuracy': '(CASE WHEN total_answers > 0 THEN 1.0 * correct_answers / total_answers ELSE 0 END)'
    }
    sort_col = allowed.get(sort, 'correct_answers')
    order_sql = 'DESC' if order == 'desc' else 'ASC'
    db = get_db()
    users = db.execute(f'''
        SELECT user_id, username, correct_answers, total_answers,
            (CASE WHEN total_answers > 0 THEN 1.0 * correct_answers / total_answers ELSE 0 END) as accuracy
        FROM user_stats
        ORDER BY {sort_col} {order_sql}, total_answers DESC
        LIMIT 50
    ''').fetchall()
    leaderboard = [dict(row) for row in users]
    return render_template('leaderboard.html', leaderboard=leaderboard, sort=sort, order=order)

@app.route('/user_stats/<user_id>')
def user_stats(user_id):
    db = get_db()
    stats = db.execute('''SELECT * FROM user_stats WHERE user_id = ?''', (user_id,)).fetchone()
    stats_dict = dict(stats) if stats else {}
    return render_template('stats.html', stats=stats_dict, is_other_user=True)

@app.route('/stats')
def stats():
    if 'user_id' not in session:
        return redirect(url_for('login'))
        
    db = get_db()
    stats = db.execute('''SELECT * FROM user_stats WHERE user_id = ?''', 
                      (session['user_id'],)).fetchone()
    stats_dict = dict(stats) if stats else {}
    return render_template('stats.html', stats=stats_dict, is_other_user=False)

@app.route('/report_question', methods=['GET', 'POST'])
def report_question():
    if not discord.authorized:
        return redirect(url_for('login', next=request.url))
    user = discord.fetch_user()
    question = request.args.get('question', '')
    answer = request.args.get('answer', '')
    # Try to get the question_id from the DB
    db = get_db()
    question_id = None
    if question:
        row = db.execute('SELECT id FROM questions WHERE question = ?', (question,)).fetchone()
        if row:
            question_id = row['id']
    if request.method == 'POST':
        message = request.form.get('message', '')
        question_text = request.form.get('question_text', '')
        answer_text = request.form.get('answer_text', '')
        # Get question_id again for POST
        qid = question_id
        if not qid and question_text:
            row = db.execute('SELECT id FROM questions WHERE question = ?', (question_text,)).fetchone()
            if row:
                qid = row['id']
        db.execute(
            'INSERT INTO reported_questions (user_id, username, question, question_id, message, timestamp) VALUES (?, ?, ?, ?, ?, ?)',
            (user.id, user.username, f"Q: {question_text}\nA: {answer_text}", qid, message, int(datetime.utcnow().timestamp()))
        )
        db.commit()
        flash('Your report has been submitted!')
        return redirect(url_for('index'))
    return render_template('report_question.html', question=question, answer=answer)

@app.before_request
def enforce_session_version():
    if 'session_version' not in session or session['session_version'] != SESSION_VERSION:
        session.clear()
        # Only clear once, then set version to avoid infinite loop
        session['session_version'] = SESSION_VERSION


if __name__ == '__main__':
    init_db()
    # Enable HTTP for local development
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    app.run(host='127.0.0.1', debug=True, port=2456)

