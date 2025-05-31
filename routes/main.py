from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for, flash
from models.database import get_db, get_all_modules, get_module_name_by_id, get_unique_values
from models.question import (get_tags_for_question, get_topics_for_question, 
                           get_subtopics_for_question, get_pdfs_for_question)
from models.user import update_user_stats, user_has_enough_answers, is_user_admin
from utils.security import generate_signed_token, verify_signed_token
from config import Config
import time
import json
from datetime import datetime
import pytz
import random
main_bp = Blueprint('main', __name__)

@main_bp.route('/')
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
        NUMBER_OF_DISTRACTORS=Config.NUMBER_OF_DISTRACTORS,
        payment_options=[1, 3, 5],  # Add payment options to template context
        default_payment=1,  # Set default to £1
        show_payment_widget=show_payment_widget)  # Pass this to template

@main_bp.route('/get_filters', methods=['POST'])
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

@main_bp.route('/get_question', methods=['POST'])
def get_question():
    if 'user_id' not in session:
        return jsonify({'error': 'Please log in to access flashcards.'}), 401
    
    data = request.get_json()
    module = data.get('module')
    topics = data.get('topics', [])
    subtopics = data.get('subtopics', [])
    tags = data.get('tags', [])
    specific_question_id = data.get('question_id')
    
    if not module:
        return jsonify({'error': 'Module is required'})
    
    db = get_db()
    
    # Get module ID
    module_row = db.execute('SELECT id FROM modules WHERE name = ?', (module,)).fetchone()
    if not module_row:
        return jsonify({'error': 'Module not found'})
    
    module_id = module_row['id']
    
    # Build the query for the normalized schema
    base_query = '''
        SELECT DISTINCT q.id, q.question, q.answer, q.module_id
        FROM questions q
        WHERE q.module_id = ?
    '''
    params = [module_id]
    
    # Add topic filters if specified
    if topics:
        topic_placeholders = ','.join(['?' for _ in topics])
        base_query += f'''
            AND EXISTS (
                SELECT 1 FROM question_topics qt
                JOIN topics t ON qt.topic_id = t.id
                WHERE qt.question_id = q.id AND t.name IN ({topic_placeholders})
            )
        '''
        params.extend(topics)
    
    # Add subtopic filters if specified
    if subtopics:
        subtopic_placeholders = ','.join(['?' for _ in subtopics])
        base_query += f'''
            AND EXISTS (
                SELECT 1 FROM question_subtopics qs
                JOIN subtopics s ON qs.subtopic_id = s.id
                WHERE qs.question_id = q.id AND s.name IN ({subtopic_placeholders})
            )
        '''
        params.extend(subtopics)
    
    # Add tag filters if specified
    if tags:
        tag_placeholders = ','.join(['?' for _ in tags])
        base_query += f'''
            AND EXISTS (
                SELECT 1 FROM question_tags qtg
                JOIN tags tg ON qtg.tag_id = tg.id
                WHERE qtg.question_id = q.id AND tg.name IN ({tag_placeholders})
            )
        '''
        params.extend(tags)
    
    # Get question (either specific or random)
    if specific_question_id:
        question = db.execute(base_query + ' AND q.id = ?', params + [specific_question_id]).fetchone()
    else:
        question = db.execute(base_query + ' ORDER BY RANDOM() LIMIT 1', params).fetchone()
    
    if not question:
        return jsonify({'error': 'No questions found for the selected criteria.'})
    
    # Get the question's topics, subtopics, and tags for display
    question_topics = get_topics_for_question(question['id'])
    question_subtopics = get_subtopics_for_question(question['id'])
    question_tags = get_tags_for_question(question['id'])
    
    # Get module name
    module_name = get_module_name_by_id(db, question['module_id'])
    
    # First, get manual distractors for this question
    manual_distractors = db.execute('''
        SELECT id, distractor_text 
        FROM manual_distractors 
        WHERE question_id = ?
        ORDER BY created_at ASC
    ''', (question['id'],)).fetchall()
    
    # Start building our answer list with the correct answer first
    answers = [question['answer']]
    answer_ids = [question['id']]  # Track which question each answer belongs to
    answer_types = ['question']  # Track the type of each answer (question or manual_distractor)
    answer_metadata = [None]  # Track metadata for manual distractors (manual_distractor_id)
    
    # Add manual distractors
    for distractor in manual_distractors:
        if len(answers) <= Config.NUMBER_OF_DISTRACTORS:  # Don't exceed total number of answers
            answers.append(distractor['distractor_text'])
            answer_ids.append(None)  # Manual distractors don't have question IDs
            answer_types.append('manual_distractor')
            answer_metadata.append(distractor['id'])  # Store the manual distractor ID
    
    # If we need more distractors, get them using the existing scoring system
    remaining_needed = Config.NUMBER_OF_DISTRACTORS + 1 - len(answers)  # +1 for correct answer
    
    if remaining_needed > 0:
        # Get additional distractors using scoring based on module, topic, subtopic matches
        primary_topic = question_topics[0] if question_topics else ''
        primary_subtopic = question_subtopics[0] if question_subtopics else ''
        
        scored_distractors = db.execute('''
        SELECT q.id, q.answer,
            (CASE WHEN q.module_id = ? THEN 3 ELSE 0 END) +
            (CASE WHEN EXISTS (
                SELECT 1 FROM question_topics qt JOIN topics t ON qt.topic_id = t.id 
                WHERE qt.question_id = q.id AND t.name = ?
            ) THEN 2 ELSE 0 END) +
            (CASE WHEN EXISTS (
                SELECT 1 FROM question_subtopics qs JOIN subtopics s ON qs.subtopic_id = s.id 
                WHERE qs.question_id = q.id AND s.name = ?
            ) THEN 1 ELSE 0 END) as score
        FROM questions q
        WHERE q.id != ? AND q.module_id = ?
        ORDER BY score DESC, RANDOM()
        LIMIT ?
    ''', (module_id, primary_topic, primary_subtopic, question['id'], module_id, remaining_needed)).fetchall()
        
        # Add the scored distractors
        for distractor in scored_distractors:
            answers.append(distractor['answer'])
            answer_ids.append(distractor['id'])
            answer_types.append('question')
            answer_metadata.append(None)
    
    # Remove all the complex duplicate detection logic that was causing issues
    # Just filter out empty answers and shuffle
    valid_answers = []
    valid_answer_ids = []
    valid_answer_types = []
    valid_answer_metadata = []
    
    for i in range(len(answers)):
        if answers[i] and answers[i].strip():
            valid_answers.append(answers[i])
            valid_answer_ids.append(answer_ids[i])
            valid_answer_types.append(answer_types[i])
            valid_answer_metadata.append(answer_metadata[i])
    
    # Ensure we have at least the correct answer
    if not valid_answers:
        valid_answers = [question['answer']]
        valid_answer_ids = [question['id']]
        valid_answer_types = ['question']
        valid_answer_metadata = [None]
    
    # Shuffle the answers
    combined = list(zip(valid_answers, valid_answer_ids, valid_answer_types, valid_answer_metadata))
    random.shuffle(combined)
    shuffled_answers, shuffled_answer_ids, shuffled_answer_types, shuffled_answer_metadata = zip(*combined)
    
    # Generate signed token
    token = generate_signed_token(question['id'], session['user_id'])
    
    # Get PDFs for this question
    pdfs = get_pdfs_for_question(question['id'])
    
    return jsonify({
        'question': question['question'],
        'answers': list(shuffled_answers),
        'answer_ids': list(shuffled_answer_ids),
        'answer_types': list(shuffled_answer_types),
        'answer_metadata': list(shuffled_answer_metadata),
        'module': module_name,
        'topic': ', '.join(question_topics),
        'subtopic': ', '.join(question_subtopics),
        'tags': question_tags,
        'pdfs': pdfs,
        'question_id': question['id'],
        'token': token,
        'is_admin': is_user_admin(session['user_id'])
    })

@main_bp.route('/check_answer', methods=['POST'])
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

@main_bp.route('/load_pdfs_by_tags', methods=['POST'])
def load_pdfs_by_tags():
    """Load PDFs for a question on demand."""
    if 'user_id' not in session:
        return jsonify({'error': 'You must be logged in'}), 401
    
    data = request.get_json()
    question_id = data.get('question_id')
    
    if not question_id:
        return jsonify({'error': 'Missing question ID'}), 400
    
    # Get PDFs for the question (max 3)
    pdfs = get_pdfs_for_question(question_id, max_pdfs=3)
    
    return jsonify({'pdfs': pdfs})

@main_bp.route('/request_pdf_access', methods=['GET', 'POST'])
def request_pdf_access():
    """Allow users to request PDF access."""
    from app import discord
    
    if not discord.authorized:
        return redirect(url_for('auth.login', next=request.url))
    
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
        return redirect(url_for('main.index'))
    
    return render_template('request_pdf_access.html')

@main_bp.route('/submit_flashcard', methods=['GET', 'POST'])
def submit_flashcard():
    """Allow users to submit flashcards for review."""
    from app import discord
    if not discord.authorized:
        return redirect(url_for('auth.login', next=request.url))
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

@main_bp.route('/report_question', methods=['GET', 'POST'])
def report_question():
    """Allow users to report problematic questions."""
    from app import discord
    if not discord.authorized:
        return redirect(url_for('auth.login', next=request.url))
    user = discord.fetch_user()
    
    question = request.args.get('question', '')
    answer = request.args.get('answer', '')
    distractor_ids = request.args.get('distractor_ids', '')
    distractor_types = request.args.get('distractor_types', '')
    distractor_metadata = request.args.get('distractor_metadata', '')
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
    if distractor_ids and distractor_types:
        distractor_id_list = distractor_ids.split(',')
        distractor_type_list = distractor_types.split(',')
        distractor_metadata_list = distractor_metadata.split(',') if distractor_metadata else [''] * len(distractor_id_list)
        
        for i, (d_id, d_type) in enumerate(zip(distractor_id_list, distractor_type_list)):
            d_metadata = distractor_metadata_list[i] if i < len(distractor_metadata_list) else ''
            
            if d_type == 'question' and d_id and d_id != str(question_id):
                # Regular question distractor
                d_row = db.execute('SELECT id, question, answer FROM questions WHERE id = ?', (d_id,)).fetchone()
                if d_row:
                    distractors.append({
                        'id': d_row['id'],
                        'question': d_row['question'],
                        'answer': d_row['answer'],
                        'type': 'question'
                    })
            elif d_type == 'manual_distractor' and d_metadata:
                # Manual distractor
                d_row = db.execute('SELECT id, distractor_text FROM manual_distractors WHERE id = ?', (d_metadata,)).fetchone()
                if d_row:
                    distractors.append({
                        'id': d_row['id'],
                        'question': question,  # Same question as main
                        'answer': d_row['distractor_text'],
                        'type': 'manual_distractor'
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
        return redirect(url_for('main.index'))
    
    # Convert distractors to JSON for the form
    distractors_json = json.dumps(distractors)
    
    return render_template('report_question.html', question=question, answer=answer, distractors_json=distractors_json)

@main_bp.route('/submit_distractor', methods=['GET', 'POST'])
def submit_distractor():
    """Submit new distractors for a question."""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'GET':
        question_id = request.args.get('question_id')
        if not question_id:
            flash('No question specified.')
            return redirect(url_for('main.index'))
        
        db = get_db()
        question = db.execute('SELECT * FROM questions WHERE id = ?', (question_id,)).fetchone()
        if not question:
            flash('Question not found.')
            return redirect(url_for('main.index'))
        
        return render_template('submit_distractor.html', 
                             question=question, 
                             NUMBER_OF_DISTRACTORS=Config.NUMBER_OF_DISTRACTORS)
    
    if request.method == 'POST':
        question_id = request.form.get('question_id')
        distractors = []
        
        # Collect non-empty distractors
        for i in range(Config.NUMBER_OF_DISTRACTORS):
            distractor = request.form.get(f'distractor_{i}', '').strip()
            if distractor:
                distractors.append(distractor)
        
        if not distractors:
            flash('Please provide at least one distractor.')
            return redirect(request.url)
        
        db = get_db()
        
        # Insert submission
        for distractor in distractors:
            db.execute('''
                INSERT INTO submitted_distractors 
                (user_id, username, question_id, distractor_text, timestamp)
                VALUES (?, ?, ?, ?, ?)
            ''', (session['user_id'], session.get('username', ''), 
                  question_id, distractor, int(time.time())))
        
        db.commit()
        flash(f'Thank you! Your {len(distractors)} distractor(s) have been submitted for review.')
        return redirect(url_for('main.index'))
