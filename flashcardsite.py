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

# Discord OAuth2 Config
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key")
app.config["DISCORD_CLIENT_ID"] = os.getenv("DISCORD_CLIENT_ID")
app.config["DISCORD_CLIENT_SECRET"] = os.getenv("DISCORD_CLIENT_SECRET")
app.config["DISCORD_REDIRECT_URI"] = os.getenv("DISCORD_REDIRECT_URI")
app.config["DISCORD_OAUTH2_SCOPE"] = ["identify, guilds"]
discord = DiscordOAuth2Session(app)

SESSION_VERSION = 3  # Increment this when you change scopes or session structure


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
        # Ensure used_tokens table exists for replay protection
        db.execute('''CREATE TABLE IF NOT EXISTS used_tokens (
            user_id TEXT,
            token TEXT,
            used_at INTEGER,
            PRIMARY KEY (user_id, token)
        )''')
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
        return jsonify({'error': 'You must be logged in'}), 401

    data = request.get_json()
    module = data.get('module')
    topics = data.get('topics', [])
    subtopics = data.get('subtopics', [])
    question_id = data.get('question_id')  # New parameter for specific question requests

    db = get_db()
    query = '''SELECT * FROM questions WHERE module = ?'''
    params = [module]

    if topics:
        query += ' AND topic IN (' + ','.join('?' * len(topics)) + ')'
        params.extend(topics)

    if subtopics:
        query += ' AND subtopic IN (' + ','.join('?' * len(subtopics)) + ')'
        params.extend(subtopics)

    # If a specific question is requested, add it to the query
    if question_id:
        query += ' AND id = ?'
        params.append(question_id)
    
    # Get matching questions
    rows = db.execute(query, params).fetchall()
    if not rows:
        return jsonify({'error': 'No questions found matching these criteria'})

    # Pick either the requested question or a random one
    row = rows[0] if question_id else random.choice(rows)
    
    # Create list of answers (correct + distractors)
    correct_answer = row['answer']
    answers = [correct_answer]
    answer_ids = [row['id']]
    # Get distractors for both new questions and specific questions
    similar_rows = db.execute(
        '''SELECT id, answer FROM questions 
           WHERE module = ? AND answer != ? 
           ORDER BY RANDOM() LIMIT 3''', 
        [module, correct_answer]
    ).fetchall()
    for r in similar_rows:
        answers.append(r['answer'])
        answer_ids.append(r['id'])
    # Only shuffle for new questions, maintain order for edited ones
    if not question_id:
        combined = list(zip(answers, answer_ids))
        random.shuffle(combined)
        answers, answer_ids = zip(*combined)
        answers = list(answers)
        answer_ids = list(answer_ids)
    # Generate signed token for this question attempt
    token = generate_signed_token(row['id'], session['user_id'])
    # Store a blacklist of used tokens in session to prevent re-use after correct answer
    if 'used_tokens' not in session:
        session['used_tokens'] = []
    response = {
        'question': row['question'],
        'answers': answers,
        'answer_ids': answer_ids,
        'module': row['module'],
        'topic': row['topic'],
        'subtopic': row['subtopic'],
        'tags': json.loads(row['tags']) if row['tags'] else [],
        'pdfs': json.loads(row['pdfs']) if row['pdfs'] else [],
        'token': token,
        'question_id': row['id'],
        'is_admin': is_user_admin(session.get('user_id')) if 'user_id' in session else False
    }
    return jsonify(response)

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
    # 1. Check if token is blacklisted (already used for a correct answer) in the DB, not session
    row = db.execute('SELECT 1 FROM used_tokens WHERE user_id = ? AND token = ?', (user_id, token)).fetchone()
    if row:
        return jsonify({'error': 'Token already used for a correct answer'}), 400
    # 2. Verify token signature and expiry
    question_id, valid = verify_signed_token(token, user_id)
    if not valid:
        return jsonify({'error': 'Invalid or expired token'}), 400
    # 3. Get the correct answer from the DB (no session storage needed)
    qrow = db.execute('SELECT answer FROM questions WHERE id = ?', (question_id,)).fetchone()
    if not qrow:
        return jsonify({'error': 'Question not found'}), 400
    correct_answer = qrow['answer']
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
    if is_correct:
        correct += 1
        streak += 1
        # Blacklist the token in the DB so it cannot be reused, even if the user resends the request
        db.execute('INSERT OR IGNORE INTO used_tokens (user_id, token, used_at) VALUES (?, ?, ?)', (user_id, token, last_answer_time))
        # This ensures the user can retry until correct, but cannot re-submit after correct (prevents replay/cheat)
    else:
        streak = 0
    db.execute('''UPDATE user_stats SET correct_answers = ?, total_answers = ?, last_answer_time = ?, current_streak = ? WHERE user_id = ?''',
               (correct, total, last_answer_time, streak, user_id))
    db.commit()

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
        'accuracy': '(CASE WHEN total_answers > 0 THEN 1.0 * correct_answers / total_answers ELSE 0 END)',
        'current_streak': 'current_streak',
        'last_answer_time': 'last_answer_time'
    }
    sort_col = allowed.get(sort, 'correct_answers')
    order_sql = 'DESC' if order == 'desc' else 'ASC'
    db = get_db()
    users = db.execute(f'''
        SELECT user_id, username, correct_answers, total_answers, current_streak, last_answer_time,
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
        if int(time.time()) - int(timestamp) > TOKEN_EXPIRY_SECONDS:
            return None, False
        return question_id, True
    except Exception:
        return None, False


if __name__ == '__main__':
    init_db()
    # Enable HTTP for local development
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    app.run(host='127.0.0.1', debug=True, port=2456)

