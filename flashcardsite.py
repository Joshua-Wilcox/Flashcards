from flask import Flask, render_template, jsonify, request, session, redirect, url_for
from flask_discord import DiscordOAuth2Session
import json
import random
from collections import defaultdict
import sqlite3
from datetime import datetime
from dotenv import load_dotenv
import os
import time

load_dotenv()  # Load variables from .env

app = Flask(__name__)

# Discord OAuth2 Config
app.secret_key = os.getenv("SECRET_KEY", "dev_secret_key")
app.config["DISCORD_CLIENT_ID"] = os.getenv("DISCORD_CLIENT_ID")
app.config["DISCORD_CLIENT_SECRET"] = os.getenv("DISCORD_CLIENT_SECRET")
app.config["DISCORD_REDIRECT_URI"] = os.getenv("DISCORD_REDIRECT_URI")
discord = DiscordOAuth2Session(app)

# Database functions
def get_db():
    db = sqlite3.connect('flashcards.db')
    db.row_factory = sqlite3.Row
    return db

def init_db():
    with app.app_context():
        db = get_db()
        with app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()

# Load flashcards data
with open('flashcards.json', 'r') as file:
    FLASHCARDS = json.load(file)

# Create indices for quick filtering
MODULE_INDEX = defaultdict(list)
TOPIC_INDEX = defaultdict(list)
SUBTOPIC_INDEX = defaultdict(list)
TAG_INDEX = defaultdict(list)

# Build indices
for idx, card in enumerate(FLASHCARDS):
    MODULE_INDEX[card['Module']].append(idx)
    TOPIC_INDEX[card['Topic']].append(idx)
    SUBTOPIC_INDEX[card['Sub-Topic']].append(idx)
    for tag in card['Tags']:
        TAG_INDEX[tag].append(idx)

def get_unique_values(key):
    return sorted(list(set(card[key] for card in FLASHCARDS)))

def get_similar_answers(correct_card, count=3):
    similar_answers = []
    module_cards = [FLASHCARDS[idx] for idx in MODULE_INDEX[correct_card['Module']]]
    
    # Try matching by tags first
    tag_matches = []
    for card in module_cards:
        if card != correct_card:
            common_tags = set(card['Tags']) & set(correct_card['Tags'])
            if common_tags:
                tag_matches.append((len(common_tags), card))
    
    # Try matching by sub-topic if we need more
    if len(tag_matches) < count:
        subtopic_matches = [
            card for card in module_cards
            if card != correct_card 
            and card['Sub-Topic'] == correct_card['Sub-Topic']
            and card not in [m[1] for m in tag_matches]
        ]
        tag_matches.extend((0, card) for card in subtopic_matches)
    
    # Try matching by topic if we still need more
    if len(tag_matches) < count:
        topic_matches = [
            card for card in module_cards
            if card != correct_card 
            and card['Topic'] == correct_card['Topic']
            and card not in [m[1] for m in tag_matches]
            and card not in subtopic_matches
        ]
        tag_matches.extend((0, card) for card in topic_matches)
    
    # Sort by number of matching tags and select top matches
    tag_matches.sort(key=lambda x: x[0], reverse=True)
    similar_answers = [m[1]['Answer'] for m in tag_matches[:count]]
    
    # If we still need more, add random answers from the same module
    while len(similar_answers) < count:
        random_card = random.choice(module_cards)
        if random_card['Answer'] not in similar_answers and random_card != correct_card:
            similar_answers.append(random_card['Answer'])
    
    return similar_answers

@app.route('/')
def index():
    return render_template('index.html',
                         modules=get_unique_values('Module'),
                         topics=get_unique_values('Topic'),
                         subtopics=get_unique_values('Sub-Topic'))

@app.route('/get_filters', methods=['POST'])
def get_filters():
    selected_module = request.json.get('module')
    selected_topics = request.json.get('topics', [])
    
    # Get all topics for the selected module
    topics = sorted(list(set(card['Topic'] for card in FLASHCARDS 
                          if not selected_module or card['Module'] == selected_module)))
    
    # Get subtopics for all selected topics
    subtopics = sorted(list(set(card['Sub-Topic'] for card in FLASHCARDS 
                              if (not selected_module or card['Module'] == selected_module) and
                                 (not selected_topics or card['Topic'] in selected_topics))))
    
    return jsonify({
        'topics': topics,
        'subtopics': subtopics
    })

@app.route('/get_question', methods=['POST'])
def get_question():
    selected_module = request.json.get('module')
    selected_topics = request.json.get('topics', [])
    selected_subtopics = request.json.get('subtopics', [])
    
    # Filter cards based on selections
    filtered_cards = [card for card in FLASHCARDS 
                     if (not selected_module or card['Module'] == selected_module) and
                        (not selected_topics or card['Topic'] in selected_topics) and
                        (not selected_subtopics or card['Sub-Topic'] in selected_subtopics)]
    
    if not filtered_cards:
        return jsonify({'error': 'No cards match the selected filters'})
    
    # Select random card
    question_card = random.choice(filtered_cards)
    
    # Get similar answers
    wrong_answers = get_similar_answers(question_card)
    
    # Combine and shuffle answers
    all_answers = wrong_answers + [question_card['Answer']]
    random.shuffle(all_answers)
    
    return jsonify({
        'question': question_card['Question'],
        'correct_answer': question_card['Answer'],
        'answers': all_answers,
        'module': question_card['Module'],
        'topic': question_card['Topic'],
        'subtopic': question_card['Sub-Topic'],
        'tags': question_card['Tags']
    })

@app.route("/login")
def login():
    return discord.create_session()

@app.route("/callback")
def callback():
    try:
        discord.callback()
        user = discord.fetch_user()
        session['user_id'] = user.id
        session['username'] = f"{user.name}#{user.discriminator}"
        
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

@app.route('/check_answer', methods=['POST'])
def check_answer():
    if 'user_id' not in session:
        return jsonify({'error': 'Not logged in'})
        
    data = request.json
    correct = data.get('correct', False)
    
    db = get_db()
    now_ts = int(time.time())
    db.execute('''UPDATE user_stats 
                  SET correct_answers = correct_answers + ?,
                      total_answers = total_answers + 1,
                      last_answer_time = ?
                  WHERE user_id = ?''', 
               (1 if correct else 0, now_ts, session['user_id']))
    db.commit()
    
    return jsonify({'success': True})

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

if __name__ == '__main__':
    init_db()
    # Enable HTTP for local development
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    app.run(host='127.0.0.1', debug=True, port=2456)
