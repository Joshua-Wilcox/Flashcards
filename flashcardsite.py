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

SESSION_VERSION = 4  # Increment this when you change scopes or session structure
NUMBER_OF_DISTRACTORS = 4

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
        db.execute('''CREATE TABLE IF NOT EXISTS used_tokens (
            user_id TEXT,
            token TEXT,
            used_at INTEGER,
            PRIMARY KEY (user_id, token)
        )''')
        # --- Add module_stats column if missing ---
        try:
            db.execute('ALTER TABLE user_stats ADD COLUMN module_stats TEXT')
        except sqlite3.OperationalError:
            pass  # Already exists
        # --- Create submitted_flashcards table if missing ---
        db.execute('''CREATE TABLE IF NOT EXISTS submitted_flashcards (
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
        )''')
        # Add username column if missing
        try:
            db.execute('ALTER TABLE submitted_flashcards ADD COLUMN username TEXT')
        except sqlite3.OperationalError:
            pass
        db.commit()
        populate_questions_table()  # Populate questions table on first run

        # --- Initialize module_stats for users where it is NULL or empty ---
        modules = get_all_modules()
        num_modules = len(modules) if modules else 1
        users = db.execute('SELECT user_id, correct_answers, total_answers, current_streak, last_answer_time, module_stats FROM user_stats').fetchall()
        for user in users:
            # Only initialize if module_stats is NULL or empty string
            if not user['module_stats']:
                correct = user['correct_answers'] or 0
                total = user['total_answers'] or 0
                streak = user['current_streak'] or 0
                last_time = user['last_answer_time'] or None
                module_stats = {}
                for m in modules:
                    module_stats[m] = {
                        "last_answered_time": last_time,
                        "number_answered": total // num_modules,
                        "number_correct": correct // num_modules,
                        "current_streak": streak // num_modules
                    }
                # Distribute any remainder to the first modules
                for i, m in enumerate(modules):
                    if i < (total % num_modules):
                        module_stats[m]["number_answered"] += 1
                    if i < (correct % num_modules):
                        module_stats[m]["number_correct"] += 1
                    if i < (streak % num_modules):
                        module_stats[m]["current_streak"] += 1
                db.execute('UPDATE user_stats SET module_stats = ? WHERE user_id = ?', (json.dumps(module_stats), user['user_id']))
        db.commit()

def get_all_modules():
    db = get_db()
    rows = db.execute('SELECT DISTINCT module FROM questions').fetchall()
    return sorted([row[0] for row in rows if row[0]])

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
                         subtopics=get_unique_values('subtopic'), NUMBER_OF_DISTRACTORS=NUMBER_OF_DISTRACTORS)

@app.route('/get_filters', methods=['POST'])
def get_filters():
    selected_module = request.json.get('module')
    selected_topics = request.json.get('topics', [])

    db = get_db()
    # Get all topics for the selected module
    topics = db.execute(
        'SELECT DISTINCT topic FROM questions WHERE module = ? AND topic IS NOT NULL AND topic != ""',
        (selected_module,)
    ).fetchall()

    # Get all subtopics for the selected module and selected topics (if any)
    if selected_topics:
        # Only subtopics for the selected module and selected topics
        placeholders = ','.join('?' * len(selected_topics))
        query = f'''
            SELECT DISTINCT subtopic FROM questions
            WHERE module = ?
              AND topic IN ({placeholders})
              AND subtopic IS NOT NULL AND subtopic != ""
        '''
        params = [selected_module] + selected_topics
        subtopics = db.execute(query, params).fetchall()
    else:
        # All subtopics for the selected module
        subtopics = db.execute(
            'SELECT DISTINCT subtopic FROM questions WHERE module = ? AND subtopic IS NOT NULL AND subtopic != ""',
            (selected_module,)
        ).fetchall()

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
    question_id = data.get('question_id')  # For specific question requests

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

    # Get tags for the current question
    current_tags = json.loads(row['tags']) if row['tags'] else []
    
    # Try to get distractors in order of relevance
    distractors_needed = NUMBER_OF_DISTRACTORS
    similar_rows = []

    # 1. First try: Same tags (if any) - but limit to distractors_needed-1
    if current_tags:
        tag_conditions = ' OR '.join(['tags LIKE ?' for _ in current_tags])
        tag_params = ['%' + tag + '%' for tag in current_tags]
        tag_query = f'''
            SELECT id, answer FROM questions 
            WHERE module = ? AND id != ? AND ({tag_conditions})
            AND answer != ? ORDER BY RANDOM()
            LIMIT {distractors_needed - 1}
        '''
        similar_rows = db.execute(tag_query, [module, row['id']] + tag_params + [correct_answer]).fetchall()

    # 2. Get remaining from same subtopic/topic
    remaining_needed = distractors_needed - len(similar_rows)
    if remaining_needed > 0:
        hierarchy_query = '''
            SELECT id, answer FROM questions 
            WHERE module = ? AND id != ? 
            AND answer != ? AND id NOT IN ({})
            AND (subtopic = ? OR topic = ?)
            ORDER BY (subtopic = ?) DESC, RANDOM()
            LIMIT ?
        '''
        exclude_ids = ','.join('?' * len(similar_rows)) if similar_rows else 'NULL'
        exclude_params = [r['id'] for r in similar_rows]
        hierarchy_rows = db.execute(hierarchy_query.format(exclude_ids),
            [module, row['id'], correct_answer] + exclude_params + 
            [row['subtopic'], row['topic'], row['subtopic'], remaining_needed]).fetchall()
        similar_rows.extend(hierarchy_rows)

    # 3. If still need more, get random ones from the same module
    if len(similar_rows) < distractors_needed:
        module_query = '''
            SELECT id, answer FROM questions 
            WHERE module = ? AND id != ? 
            AND answer != ? AND id NOT IN ({})
            ORDER BY RANDOM()
            LIMIT ?
        '''
        exclude_ids = ','.join('?' * len(similar_rows)) if similar_rows else 'NULL'
        exclude_params = [r['id'] for r in similar_rows]
        remaining_needed = distractors_needed - len(similar_rows)
        module_rows = db.execute(module_query.format(exclude_ids),
            [module, row['id'], correct_answer] + exclude_params + [remaining_needed]).fetchall()
        similar_rows.extend(module_rows)

    # 4. If still need more, get random ones from the same module
    if len(similar_rows) < distractors_needed:
        module_query = '''
            SELECT id, answer FROM questions 
            WHERE module = ? AND id != ? 
            AND answer != ? AND id NOT IN ({})
            ORDER BY RANDOM()
        '''
        exclude_ids = ','.join('?' * len(similar_rows)) if similar_rows else 'NULL'
        exclude_params = [r['id'] for r in similar_rows]
        module_rows = db.execute(module_query.format(exclude_ids),
            [module, row['id'], correct_answer] + exclude_params).fetchall()
        similar_rows.extend(module_rows)

    # Take only the number of distractors needed
    for r in similar_rows[:distractors_needed]:
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
    row = db.execute('SELECT 1 FROM used_tokens WHERE user_id = ? AND token = ?', (user_id, token)).fetchone()
    if row:
        return jsonify({'error': 'Token already used for a correct answer'}), 400
    question_id, valid = verify_signed_token(token, user_id)
    if not valid:
        return jsonify({'error': 'Invalid or expired token'}), 400
    qrow = db.execute('SELECT answer, module FROM questions WHERE id = ?', (question_id,)).fetchone()
    if not qrow:
        return jsonify({'error': 'Question not found'}), 400
    correct_answer = qrow['answer']
    module = qrow['module']
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
    if module not in module_stats:
        module_stats[module] = {
            "last_answered_time": None,
            "number_answered": 0,
            "number_correct": 0,
            "current_streak": 0
        }
    # Ensure current_streak key exists for all modules
    if "current_streak" not in module_stats[module]:
        module_stats[module]["current_streak"] = 0
    module_stats[module]["last_answered_time"] = last_answer_time
    module_stats[module]["number_answered"] = module_stats[module].get("number_answered", 0) + 1
    if is_correct:
        correct += 1
        streak += 1
        module_stats[module]["number_correct"] = module_stats[module].get("number_correct", 0) + 1
        module_stats[module]["current_streak"] = module_stats[module].get("current_streak", 0) + 1
        db.execute('INSERT OR IGNORE INTO used_tokens (user_id, token, used_at) VALUES (?, ?, ?)', (user_id, token, last_answer_time))
    else:
        streak = 0
        module_stats[module]["current_streak"] = 0
    db.execute('''UPDATE user_stats SET correct_answers = ?, total_answers = ?, last_answer_time = ?, current_streak = ?, module_stats = ? WHERE user_id = ?''',
               (correct, total, last_answer_time, streak, json.dumps(module_stats), user_id))
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
        session['session_version'] = SESSION_VERSION
        db = get_db()
        row = db.execute('SELECT * FROM user_stats WHERE user_id = ?', (user.id,)).fetchone()
        modules = get_all_modules()
        num_modules = len(modules) if modules else 1
        if not row:
            # New user: evenly distribute zeros (all stats zero)
            module_stats = {}
            for m in modules:
                module_stats[m] = {
                    "last_answered_time": None,
                    "number_answered": 0,
                    "number_correct": 0,
                    "current_streak": 0
                }
            db.execute('''INSERT INTO user_stats (user_id, username, module_stats) 
                          VALUES (?, ?, ?)''', (user.id, session['username'], json.dumps(module_stats)))
        else:
            if not row['module_stats']:
                # Existing user with stats but no module_stats: distribute their stats evenly
                correct = row['correct_answers'] or 0
                total = row['total_answers'] or 0
                streak = row['current_streak'] or 0
                last_time = row['last_answer_time'] or None
                module_stats = {}
                for m in modules:
                    module_stats[m] = {
                        "last_answered_time": last_time,
                        "number_answered": total // num_modules,
                        "number_correct": correct // num_modules,
                        "current_streak": streak // num_modules
                    }
                # Distribute any remainder to the first modules
                for i, m in enumerate(modules):
                    if i < (total % num_modules):
                        module_stats[m]["number_answered"] += 1
                    if i < (correct % num_modules):
                        module_stats[m]["number_correct"] += 1
                    if i < (streak % num_modules):
                        module_stats[m]["current_streak"] += 1
                db.execute('UPDATE user_stats SET module_stats = ? WHERE user_id = ?', (json.dumps(module_stats), user.id))
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
                (CASE WHEN total_answers > 0 THEN 1.0 * correct_answers / total_answers ELSE 0 END) as accuracy,
                module_stats
            FROM user_stats
            ORDER BY {sort_col} {order_sql}, total_answers DESC
            LIMIT 50
        ''').fetchall()
    else:
        # No ORDER BY for per-module, will sort in Python
        users = db.execute(f'''
            SELECT user_id, username, correct_answers, total_answers, current_streak, last_answer_time,
                (CASE WHEN total_answers > 0 THEN 1.0 * correct_answers / total_answers ELSE 0 END) as accuracy,
                module_stats
            FROM user_stats
            LIMIT 50
        ''').fetchall()
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
    stats = db.execute('''SELECT * FROM user_stats WHERE user_id = ?''', (user_id,)).fetchone()
    stats_dict = dict(stats) if stats else {}
    if stats and stats['module_stats']:
        stats_dict['module_stats'] = json.loads(stats['module_stats'])
        # Ensure current_streak key exists for all modules
        for m in stats_dict['module_stats'].values():
            if "current_streak" not in m:
                m["current_streak"] = 0
    else:
        stats_dict['module_stats'] = {}
    modules = get_all_modules()
    stats_dict['active_module'] = module_filter
    return render_template('stats.html', stats=stats_dict, is_other_user=True, modules=modules)

@app.route('/stats')
def stats():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    module_filter = request.args.get('module', None)
    db = get_db()
    stats = db.execute('''SELECT * FROM user_stats WHERE user_id = ?''', 
                      (session['user_id'],)).fetchone()
    stats_dict = dict(stats) if stats else {}
    if stats and stats['module_stats']:
        stats_dict['module_stats'] = json.loads(stats['module_stats'])
        for m in stats_dict['module_stats'].values():
            if "current_streak" not in m:
                m["current_streak"] = 0
    else:
        stats_dict['module_stats'] = {}
    modules = get_all_modules()
    stats_dict['active_module'] = module_filter
    return render_template('stats.html', stats=stats_dict, is_other_user=False, modules=modules)

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
        # Require topic, subtopic, tags
        if question and answer and module and topic and subtopic and tags:
            db.execute('''INSERT INTO submitted_flashcards 
                (user_id, username, timestamp, submitted_question, submitted_answer, module, submitted_topic, submitted_subtopic, submitted_tags_comma_separated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (user.id, user.username, int(datetime.utcnow().timestamp()), question, answer, module, topic, subtopic, tags))
            db.commit()
            flash('Flashcard submitted for review! Thank you.')
            return render_template('submit_flashcard.html', modules=modules, selected_module=module, clear_fields=True)
        else:
            flash('Please fill in all required fields (question, answer, module, topic, subtopic, tags).')
            return render_template('submit_flashcard.html', modules=modules, selected_module=module, clear_fields=False,
                                   prev_question=question, prev_answer=answer, prev_topic=topic, prev_subtopic=subtopic, prev_tags=tags)
    return render_template('submit_flashcard.html', modules=modules, selected_module=None, clear_fields=False)

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
    # If POST, handle update or discard
    if request.method == 'POST':
        action = request.form.get('action')
        new_question = request.form.get('question', '').strip()
        new_answer = request.form.get('answer', '').strip()
        if action == 'discard':
            db.execute('DELETE FROM reported_questions WHERE id = ?', (report_id,))
            db.commit()
            flash('Report discarded.')
            return redirect(url_for('admin_review_flashcards'))
        elif action == 'update':
            if not question_row:
                flash('Original question not found, cannot update.')
                return redirect(url_for('admin_review_report', report_id=report_id))
            db.execute('UPDATE questions SET question = ?, answer = ? WHERE id = ?', (new_question, new_answer, question_row['id']))
            db.execute('DELETE FROM reported_questions WHERE id = ?', (report_id,))
            db.commit()
            flash('Question updated and report resolved.')
            return redirect(url_for('admin_review_flashcards'))
    return render_template('admin_review_report.html', report=report, question_row=question_row)

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
            # Insert into questions table
            question_id = hashlib.sha256(question.encode('utf-8')).hexdigest()
            db.execute('''INSERT OR IGNORE INTO questions (id, question, answer, module, topic, subtopic, tags, pdfs)
                          VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                       (question_id, question, answer, module, topic, subtopic, json.dumps([t.strip() for t in tags.split(',') if t.strip()]), json.dumps([])))
            db.execute('DELETE FROM submitted_flashcards WHERE id = ?', (submission_id,))
            db.commit()
            flash('Flashcard approved and added to the database.')
            return redirect(url_for('admin_review_flashcards'))
        elif action == 'reject':
            db.execute('DELETE FROM submitted_flashcards WHERE id = ?', (submission_id,))
            db.commit()
            flash('Flashcard submission rejected and removed.')
            return redirect(url_for('admin_review_flashcards'))
    return render_template('admin_review_flashcard.html', submission=submission, modules=modules)

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

