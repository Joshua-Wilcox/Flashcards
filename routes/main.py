from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for, flash, send_file
import io
from models.supabase_adapter import supabase_client, SupabaseAdapter
from models.database import (get_all_modules, get_module_name_by_id, get_unique_values,
                             group_modules_by_year)
from models.question import (get_tags_for_question, get_topics_for_question, 
                           get_subtopics_for_question, get_pdfs_for_question,
                           get_comprehensive_question_metadata, get_question_with_distractors)
from models.user import update_user_stats, user_has_enough_answers, is_user_admin
from utils.security import generate_signed_token, verify_signed_token
from config import Config
import time
import json
import logging
from datetime import datetime
import pytz
import random

logger = logging.getLogger(__name__)
main_bp = Blueprint('main', __name__)

# Initialize the adapter instance
adapter = SupabaseAdapter()

def get_bulk_question_metadata(question_ids, client=None):
    """
    Efficiently fetch topics, subtopics, and tags for multiple questions in bulk.
    Returns a dict mapping question_id -> {'topics': [...], 'subtopics': [...], 'tags': [...]}
    """
    return get_comprehensive_question_metadata(question_ids)

def calculate_distractor_similarity_score(current_topics, current_subtopics, current_tags,
                                        distractor_topics, distractor_subtopics, distractor_tags):
    """
    Calculate similarity score between current question and potential distractor.
    Higher score = more similar = better distractor.
    
    Scoring weights:
    - Topic overlap: 3 points per shared topic
    - Subtopic overlap: 2 points per shared subtopic  
    - Tag overlap: 1 point per shared tag
    """
    score = 0
    
    # Convert to sets for easier intersection operations
    current_topics_set = set(current_topics)
    current_subtopics_set = set(current_subtopics)
    current_tags_set = set(current_tags)
    
    distractor_topics_set = set(distractor_topics)
    distractor_subtopics_set = set(distractor_subtopics)
    distractor_tags_set = set(distractor_tags)
    
    # Score topic overlap (highest weight - topics are most important)
    topic_overlap = len(current_topics_set.intersection(distractor_topics_set))
    score += topic_overlap * 3
    
    # Score subtopic overlap (medium weight)
    subtopic_overlap = len(current_subtopics_set.intersection(distractor_subtopics_set))
    score += subtopic_overlap * 2
    
    # Score tag overlap (lower weight)
    tag_overlap = len(current_tags_set.intersection(distractor_tags_set))
    score += tag_overlap * 1
    
    # Bonus points for having any overlap at all (encourages some similarity)
    if topic_overlap > 0:
        score += 2  # Bonus for having at least one shared topic
    if subtopic_overlap > 0:
        score += 1  # Bonus for having at least one shared subtopic
        
    return score

@main_bp.route('/')
def index():
    modules = get_all_modules()
    module_groups = group_modules_by_year(modules)
    show_payment_widget = False
    
    # Only check for payment eligibility if the user is logged in
    if 'user_id' in session:
        show_payment_widget = user_has_enough_answers(session['user_id'], minimum=10)
    
    return render_template('index.html',
        modules=modules,
        module_groups=module_groups,
        topics=get_unique_values('topic'),
        subtopics=get_unique_values('subtopic'), 
        NUMBER_OF_DISTRACTORS=Config.NUMBER_OF_DISTRACTORS,
        payment_options=[1, 3, 5],
        default_payment=1,
        show_payment_widget=show_payment_widget)

@main_bp.route('/get_filters', methods=['POST'])
def get_filters():
    """Optimized filter data retrieval using RPC function"""
    try:
        # Get data from JSON body for POST request
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid request data'}), 400
            
        module_name = data.get('module')
        selected_topics = data.get('topics', [])  # Get currently selected topics
        if not module_name:
            return jsonify({'error': 'Module name required'}), 400
        
        # Use optimized RPC function - single database call instead of 6-12 queries
        filters = supabase_client.get_module_filter_data_rpc(module_name, selected_topics)
        
        # Transform the data to match frontend expectations (arrays of strings, not objects)
        response = {
            'topics': [item['name'] for item in sorted(filters['topics'], key=lambda x: x['name'])],
            'subtopics': [item['name'] for item in sorted(filters['subtopics'], key=lambda x: x['name'])],
            'tags': [item['name'] for item in sorted(filters['tags'], key=lambda x: x['name'])]
        }
        
        return jsonify(response)
        
    except Exception as e:
        print(f"Error in get_filters: {e}")
        return jsonify({'error': 'Internal server error'}), 500

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
    
    client = supabase_client.get_db()
    
    # Get module ID
    module_result = client.table('modules').select('id').eq('name', module).execute()
    if not module_result.data:
        return jsonify({'error': 'Module not found'})
    
    module_id = module_result.data[0]['id']
    
    # Get filtered question IDs based on topics, subtopics, and tags
    filtered_question_ids = None
    filters_applied = bool(topics or subtopics or tags)
    filters_relaxed = False
    
    if specific_question_id:
        # If specific question requested, just use that
        filtered_question_ids = [specific_question_id]
    elif not filters_applied:
        # No filters applied - get all questions from module and pick randomly
        questions_result = client.table('questions').select('id, question, answer, module_id').eq('module_id', module_id).execute()
        if not questions_result.data:
            return jsonify({'error': 'No questions found in the selected module.'})
        
        # Pick a random question immediately
        question = random.choice(questions_result.data)
        
        # Get the question's topics, subtopics, and tags for display using optimized function
        question_metadata = get_comprehensive_question_metadata([question['id']])
        current_metadata = question_metadata.get(question['id'], {'topics': [], 'subtopics': [], 'tags': []})
        question_topics = current_metadata['topics']
        question_subtopics = current_metadata['subtopics']
        question_tags = current_metadata['tags']
        
        # Get module name
        module_name = get_module_name_by_id(question['module_id'])
        
        # Get manual distractors for this question
        manual_distractors_result = client.table('manual_distractors').select('id, distractor_text').eq('question_id', question['id']).order('created_at').execute()
        manual_distractors = manual_distractors_result.data if manual_distractors_result.data else []
        
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
        
        # If we need more distractors, get them from other questions with intelligent scoring
        remaining_needed = Config.NUMBER_OF_DISTRACTORS + 1 - len(answers)  # +1 for correct answer
        
        if remaining_needed > 0:
            # Get all other questions from the same module for distractor scoring
            distractor_questions_result = client.table('questions').select('id, answer').eq('module_id', module_id).neq('id', question['id']).execute()
            
            if distractor_questions_result.data:
                # Get all question IDs for batch metadata lookup (include current question to reuse metadata)
                distractor_question_ids = [q['id'] for q in distractor_questions_result.data]
                all_question_ids = [question['id']] + distractor_question_ids
                
                # Batch fetch all topics, subtopics, and tags for ALL questions (current + distractors)
                all_metadata = get_bulk_question_metadata(all_question_ids)
                
                # Get current question metadata from bulk result (reuse instead of individual calls)
                current_metadata = all_metadata.get(question['id'], {'topics': [], 'subtopics': [], 'tags': []})
                
                # Score each potential distractor question using cached metadata
                scored_distractors = []
                
                for distractor_q in distractor_questions_result.data:
                    qid = distractor_q['id']
                    metadata = all_metadata.get(qid, {'topics': [], 'subtopics': [], 'tags': []})
                    
                    # Calculate similarity score
                    score = calculate_distractor_similarity_score(
                        current_metadata['topics'], current_metadata['subtopics'], current_metadata['tags'],
                        metadata['topics'], metadata['subtopics'], metadata['tags']
                    )
                    
                    scored_distractors.append({
                        'question': distractor_q,
                        'score': score
                    })
                
                # Sort by score (highest first) and take the best matches
                scored_distractors.sort(key=lambda x: x['score'], reverse=True)
                best_distractors = scored_distractors[:remaining_needed]
                
                for distractor_info in best_distractors:
                    distractor_q = distractor_info['question']
                    answers.append(distractor_q['answer'])
                    answer_ids.append(distractor_q['id'])
                    answer_types.append('question')
                    answer_metadata.append(None)
        
        # Filter out empty answers and shuffle
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
            'is_admin': is_user_admin(session['user_id']),
            'filters_applied': filters_applied,
            'filters_relaxed': filters_relaxed,
            'total_filtered_questions': len(questions_result.data)
        })
    else:
        # Use optimized RPC function for filtering - single query instead of O(n) queries
        questions = supabase_client.get_filtered_questions_rpc(module, topics, subtopics, tags)
        
        if not questions:
            # Fallback: try with relaxed filters (no filters applied)
            filters_relaxed = True
            questions = supabase_client.get_filtered_questions_rpc(module)
            if not questions:
                return jsonify({'error': 'No questions found in the selected module.'})
        
        questions_result = type('obj', (object,), {'data': questions})()
        if not questions_result.data:
            return jsonify({'error': 'No questions found in the selected module.'})
    
    # If not specific question, pick random one from filtered results
    if specific_question_id:
        question = questions_result.data[0]
    else:
        question = random.choice(questions_result.data)
    
    # Get module name
    module_name = get_module_name_by_id(question['module_id'])
    
    # Get the question's topics, subtopics, and tags for display using optimized function
    question_metadata = get_comprehensive_question_metadata([question['id']])
    current_metadata = question_metadata.get(question['id'], {'topics': [], 'subtopics': [], 'tags': []})
    question_topics = current_metadata['topics']
    question_subtopics = current_metadata['subtopics']
    question_tags = current_metadata['tags']
    
    # Get manual distractors for this question
    manual_distractors_result = client.table('manual_distractors').select('id, distractor_text').eq('question_id', question['id']).order('created_at').execute()
    manual_distractors = manual_distractors_result.data if manual_distractors_result.data else []
    
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
    
    # If we need more distractors, get them using RPC function for intelligent scoring
    remaining_needed = Config.NUMBER_OF_DISTRACTORS + 1 - len(answers)  # +1 for correct answer
    
    if remaining_needed > 0:
        # Use RPC function to get smart distractors
        smart_distractors = adapter.get_smart_distractors_rpc(question['id'], remaining_needed)
        
        if smart_distractors:
            for distractor in smart_distractors:
                answers.append(distractor['answer'])
                answer_ids.append(distractor['id'])
                answer_types.append('question')
                answer_metadata.append(None)
    
    # Filter out empty answers and shuffle
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
        'is_admin': is_user_admin(session['user_id']),
        'filters_applied': filters_applied,
        'filters_relaxed': filters_relaxed,
        'total_filtered_questions': len(questions_result.data)
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
    client = supabase_client.get_db()
    
    # --- Token validation (still needed) ---
    used_token_result = client.table('used_tokens').select('*').eq('user_id', user_id).eq('token', token).execute()
    if used_token_result.data:
        return jsonify({'error': 'Token already used for a correct answer'}), 400
    
    question_id, valid = verify_signed_token(token, user_id)
    if not valid:
        return jsonify({'error': 'Invalid or expired token'}), 400
    
    # Use optimized RPC function for answer processing
    try:
        # First, get the correct answer to check if submission is correct
        question_result = client.table('questions').select('answer').eq('id', question_id).execute()
        if not question_result.data:
            return jsonify({'error': 'Question not found'}), 400
        
        correct_answer = question_result.data[0]['answer']
        is_correct = submitted_answer == correct_answer
        
        # Use RPC function to process the answer check (reduces 6-7 calls to 1-2)
        result = adapter.process_answer_check_rpc(
            user_id, 
            question_id, 
            is_correct, 
            token, 
            session.get('username', 'Unknown')
        )
        
        if 'error' in result:
            return jsonify({'error': result['error']}), 400
        
        return jsonify({'correct': is_correct})
        
    except Exception as e:
        logger.error(f"RPC answer check failed, using fallback: {e}")
        
        # Get question details
        question_result = client.table('questions').select('answer, module_id').eq('id', question_id).execute()
        if not question_result.data:
            return jsonify({'error': 'Question not found'}), 400
        
        question = question_result.data[0]
        correct_answer = question['answer']
        module_id = question['module_id']
        is_correct = submitted_answer == correct_answer

        # Get current user stats
        stats_result = client.table('user_stats').select('correct_answers, total_answers, current_streak').eq('user_id', user_id).execute()
        if stats_result.data:
            stats = stats_result.data[0]
            correct = stats.get('correct_answers', 0) or 0
            total = stats.get('total_answers', 0) or 0
            streak = stats.get('current_streak', 0) or 0
        else:
            correct = 0
            total = 0
            streak = 0
        
        total += 1
        
        # Use Europe/London timezone for last_answer_time
        london_tz = pytz.timezone('Europe/London')
        now_london = datetime.now(london_tz)
        last_answer_time = now_london.isoformat()  # Convert to ISO format for TIMESTAMPTZ
        
        # Update module stats
        module_stats_result = client.table('module_stats').select('number_answered, number_correct, current_streak').eq('user_id', user_id).eq('module_id', module_id).execute()
        
        if module_stats_result.data:
            # Update existing module stats
            module_stats = module_stats_result.data[0]
            new_answered = (module_stats.get('number_answered', 0) or 0) + 1
            new_correct = (module_stats.get('number_correct', 0) or 0) + (1 if is_correct else 0)
            new_streak = (module_stats.get('current_streak', 0) or 0) + 1 if is_correct else 0
            
            client.table('module_stats').update({
                'number_answered': new_answered,
                'number_correct': new_correct,
                'last_answered_time': last_answer_time,
                'current_streak': new_streak
            }).eq('user_id', user_id).eq('module_id', module_id).execute()
        else:
            # Insert new module stats
            client.table('module_stats').insert({
                'user_id': user_id,
                'module_id': module_id,
                'number_answered': 1,
                'number_correct': 1 if is_correct else 0,
                'last_answered_time': last_answer_time,
                'current_streak': 1 if is_correct else 0
            }).execute()

        # Update overall stats
        if is_correct:
            correct += 1
            streak += 1
            # Record the used token
            client.table('used_tokens').insert({
                'user_id': user_id,
                'token': token
            }).execute()
        else:
            streak = 0
            
        # Update overall user stats
        client.table('user_stats').upsert({
            'user_id': user_id,
            'username': session.get('username', 'Unknown'),  # Get username from session
            'correct_answers': correct,
            'total_answers': total,
            'last_answer_time': last_answer_time,
            'current_streak': streak
        }, on_conflict='user_id').execute()

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
        client = supabase_client.get_db()
        
        client.table('requests_to_access').insert({
            'discord_id': user.id,
            'username': user.username,
            'message': message
        }).execute()
        
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
    client = supabase_client.get_db()
    modules = get_all_modules()
    
    if request.method == 'POST':
        question = request.form.get('question', '').strip()
        answer = request.form.get('answer', '').strip()
        module = request.form.get('module', '').strip()
        topic = request.form.get('topic', '').strip()
        subtopic = request.form.get('subtopic', '').strip()
        tags = request.form.get('tags', '').strip()
        
        if question and answer and module and topic and subtopic and tags:
            try:
                # Insert the flashcard submission
                flashcard_result = client.table('submitted_flashcards').insert({
                    'user_id': user.id,
                    'username': user.username,
                    'submitted_question': question,
                    'submitted_answer': answer,
                    'module': module,
                    'submitted_topic': topic,
                    'submitted_subtopic': subtopic,
                    'submitted_tags_comma_separated': tags
                }).execute()
                
                if flashcard_result.data:
                    flashcard_id = flashcard_result.data[0]['id']
                    
                    # Check for distractor submissions
                    distractors = []
                    for i in range(Config.NUMBER_OF_DISTRACTORS):
                        distractor = request.form.get(f'distractor_{i}', '').strip()
                        if distractor:
                            distractors.append(distractor)
                    
                    # If distractors were provided, handle them
                    if distractors:
                        for distractor in distractors:
                            client.table('submitted_distractors').insert({
                                'user_id': user.id,
                                'username': user.username,
                                'question_id': f"flashcard_{flashcard_id}",
                                'distractor_text': distractor
                            }).execute()
                        
                        flash(f'Flashcard and {len(distractors)} distractor(s) submitted for review! Thank you.')
                    else:
                        flash('Flashcard submitted for review! Thank you.')
                    
                    return render_template('submit_flashcard.html', modules=[m['name'] for m in modules], selected_module=module, clear_fields=True,
                                           prev_topic=topic, prev_subtopic=subtopic, prev_tags=tags)
                
            except Exception as e:
                flash(f'Error submitting flashcard: {str(e)}')
                return render_template('submit_flashcard.html', modules=[m['name'] for m in modules], selected_module=module, clear_fields=False,
                                       prev_question=question, prev_answer=answer, prev_topic=topic, prev_subtopic=subtopic, prev_tags=tags)
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
    
    client = supabase_client.get_db()
    question_id = None
    
    # Get the correct answer from the database based on the question text
    if question:
        question_result = client.table('questions').select('id, answer').eq('question', question).execute()
        if question_result.data:
            question_row = question_result.data[0]
            question_id = question_row['id']
            # Override the provided answer with the actual correct answer from the database
            answer = question_row['answer']
    
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
                d_result = client.table('questions').select('id, question, answer').eq('id', d_id).execute()
                if d_result.data:
                    d_row = d_result.data[0]
                    distractors.append({
                        'id': d_row['id'],
                        'question': d_row['question'],
                        'answer': d_row['answer'],
                        'type': 'question'
                    })
            elif d_type == 'manual_distractor' and d_metadata:
                # Manual distractor
                d_result = client.table('manual_distractors').select('id, distractor_text').eq('id', d_metadata).execute()
                if d_result.data:
                    d_row = d_result.data[0]
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
            q_result = client.table('questions').select('id').eq('question', question_text).execute()
            if q_result.data:
                qid = q_result.data[0]['id']
        
        # Store distractors as JSON string
        distractors_json = request.form.get('distractors_json', '[]')
        
        client.table('reported_questions').insert({
            'user_id': user.id,
            'username': user.username,
            'question': f"Q: {question_text}\nA: {answer_text}",
            'question_id': qid,
            'message': message,
            'distractors': distractors_json
        }).execute()
        
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
        
        client = supabase_client.get_db()
        question_result = client.table('questions').select('*').eq('id', question_id).execute()
        if not question_result.data:
            flash('Question not found.')
            return redirect(url_for('main.index'))
        
        question = question_result.data[0]
        
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
        
        client = supabase_client.get_db()
        
        # Insert submissions
        for distractor in distractors:
            client.table('submitted_distractors').insert({
                'user_id': session['user_id'],
                'username': session.get('username', ''),
                'question_id': question_id,
                'distractor_text': distractor
            }).execute()
        
        flash(f'Thank you! Your {len(distractors)} distractor(s) have been submitted for review.')
        return redirect(url_for('main.index'))


def is_user_whitelisted(user_id, user_guilds=None):
    """Check if a user is whitelisted for PDF access."""
    try:
        with open('whitelist.json', 'r', encoding='utf-8') as f:
            whitelist = json.load(f)
        return int(user_id) in whitelist.get('user_ids', [])
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return False


@main_bp.route('/pdf/<int:pdf_id>')
def serve_pdf(pdf_id):
    """Serve PDF by database ID with access control for regular users"""
    from app import discord
    if not discord.authorized:
        return redirect(url_for('auth.login', next=request.url))
    
    user = discord.fetch_user()
    user_id = user.id
    user_guilds = discord.fetch_guilds()
    
    if is_user_whitelisted(user_id, user_guilds):
        try:
            # Get PDF info from database
            client = supabase_client.get_db()
            pdf_result = client.table('pdfs').select('storage_path, original_filename, is_active, mime_type').eq('id', pdf_id).execute()
            
            if not pdf_result.data or not pdf_result.data[0]['is_active']:
                flash('PDF not found or no longer available.')
                return redirect(url_for('main.index'))
            
            pdf_data = pdf_result.data[0]
            
            # Download PDF content from Supabase storage
            from services.pdf_storage import PDFStorageService
            pdf_service = PDFStorageService()
            pdf_content = pdf_service.download_pdf_content(pdf_data['storage_path'])
            
            if pdf_content:
                # Create a file-like object from the content
                pdf_file = io.BytesIO(pdf_content)
                mime_type = pdf_data.get('mime_type', 'application/pdf')
                
                # Serve the PDF directly
                return send_file(
                    pdf_file,
                    mimetype=mime_type,
                    as_attachment=False,  # Display in browser, not force download
                    download_name=pdf_data['original_filename']
                )
            else:
                flash('Unable to access PDF at this time.')
                return redirect(url_for('main.index'))
                
        except Exception as e:
            print(f"Error serving PDF {pdf_id}: {e}")
            flash('Error accessing PDF.')
            return redirect(url_for('main.index'))
    else:
        return redirect(url_for('main.request_pdf_access'))
