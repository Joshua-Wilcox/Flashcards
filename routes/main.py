from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for, flash, send_file
import io
from models.supabase_adapter import supabase_client, SupabaseAdapter
from models.database import (get_all_modules, get_unique_values,
                             group_modules_by_year)
from models.question import get_pdfs_for_question
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
    filters_applied = bool(topics or subtopics or tags)
    filters_relaxed = False

    # Try optimized RPC first
    rpc_result = adapter.get_random_question_with_distractors_rpc(
        module_id, 
        topic_names=topics if topics else None, 
        subtopic_names=subtopics if subtopics else None, 
        tag_names=tags if tags else None,
        specific_question_id=specific_question_id, 
        distractor_limit=Config.NUMBER_OF_DISTRACTORS
    )

    if rpc_result and rpc_result.get('question_data'):
        q_data = rpc_result['question_data']
        d_data = rpc_result['distractors']
        
        # Start with correct answer
        answers = [q_data['answer']]
        answer_ids = [q_data['id']]
        answer_types = ['question']
        answer_metadata = [None]
        
        # Add manual distractors
        manual_distractors = d_data.get('manual_distractors', [])
        for md in manual_distractors:
            answers.append(md['answer'])
            answer_ids.append(None)
            answer_types.append('manual_distractor')
            answer_metadata.append(md['id'])
            
        # Add smart distractors
        smart_distractors = d_data.get('smart_distractors', [])
        for sd in smart_distractors:
            answers.append(sd['answer'])
            answer_ids.append(sd['id'])
            answer_types.append('question')
            answer_metadata.append(None)
            
        # Shuffle answers
        combined = list(zip(answers, answer_ids, answer_types, answer_metadata))
        random.shuffle(combined)
        shuffled_answers, shuffled_answer_ids, shuffled_answer_types, shuffled_answer_metadata = zip(*combined)
        
        # Generate token and get PDFs
        token = generate_signed_token(q_data['id'], session['user_id'])
        pdfs = get_pdfs_for_question(q_data['id'])
        
        return jsonify({
            'question': q_data['question'],
            'answers': list(shuffled_answers),
            'answer_ids': list(shuffled_answer_ids),
            'answer_types': list(shuffled_answer_types),
            'answer_metadata': list(shuffled_answer_metadata),
            'module': module,  # Use the module name from request
            'topic': ', '.join(q_data.get('topics', [])),
            'subtopic': ', '.join(q_data.get('subtopics', [])),
            'tags': q_data.get('tags', []),
            'pdfs': pdfs,
            'question_id': q_data['id'],
            'token': token,
            'is_admin': is_user_admin(session['user_id']),
            'filters_applied': filters_applied,
            'filters_relaxed': False,  # RPC handles exact matches
            'total_filtered_questions': 1 # approximate since we don't count in optimization
        })
    else:
        return jsonify({'error': 'No questions found matching the criteria.'})

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
    
    # Validate token signature (local operation, no DB call)
    question_id, valid = verify_signed_token(token, user_id)
    if not valid:
        return jsonify({'error': 'Invalid or expired token'}), 400
    
    # Use ultra-optimized RPC function for entire answer check (reduces 3-4 calls to 1)
    try:
        result = adapter.check_answer_optimized_rpc(
            user_id, 
            question_id, 
            submitted_answer,
            token, 
            session.get('username', 'Unknown')
        )
        
        if 'error' in result:
            return jsonify({'error': result['error']}), 400
        
        return jsonify({'correct': result.get('correct', False)})
        
    except Exception as e:
        logger.error(f"RPC answer check failed: {e}")
        return jsonify({'error': 'An error occurred while checking the answer.'}), 500

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
        
        logger.info(f"Flashcard submission attempt by user {user.id}: module={module}, topic={topic}, subtopic={subtopic}, tags={tags}")
        
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
                logger.error(f'Error submitting flashcard: {str(e)}', exc_info=True)
                flash(f'Error submitting flashcard: {str(e)}')
                return render_template('submit_flashcard.html', modules=[m['name'] for m in modules], selected_module=module, clear_fields=False,
                                       prev_question=question, prev_answer=answer, prev_topic=topic, prev_subtopic=subtopic, prev_tags=tags)
        else:
            logger.warning(f"Flashcard submission missing required fields: question={bool(question)}, answer={bool(answer)}, module={bool(module)}, topic={bool(topic)}, subtopic={bool(subtopic)}, tags={bool(tags)}")
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
        
        # Collect IDs for batch fetching
        question_distractor_ids = []
        manual_distractor_ids = []
        
        for i, (d_id, d_type) in enumerate(zip(distractor_id_list, distractor_type_list)):
            d_metadata = distractor_metadata_list[i] if i < len(distractor_metadata_list) else ''
            
            if d_type == 'question' and d_id and d_id != str(question_id):
                question_distractor_ids.append(d_id)
            elif d_type == 'manual_distractor' and d_metadata:
                manual_distractor_ids.append(d_metadata)
        
        # Batch fetch question distractors
        if question_distractor_ids:
            q_results = client.table('questions').select('id, question, answer').in_('id', question_distractor_ids).execute()
            for d_row in q_results.data:
                distractors.append({
                    'id': d_row['id'],
                    'question': d_row['question'],
                    'answer': d_row['answer'],
                    'type': 'question'
                })
        
        # Batch fetch manual distractors
        if manual_distractor_ids:
            m_results = client.table('manual_distractors').select('id, distractor_text').in_('id', manual_distractor_ids).execute()
            for d_row in m_results.data:
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
        
        # Check if this is an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
            return jsonify({'success': True, 'message': 'Your report has been submitted!'})
        
        return redirect(url_for('main.index'))
    
    # Convert distractors to JSON for the form
    distractors_json = json.dumps(distractors)
    
    # Always use the inline component template
    return render_template('components/report_form.html', question=question, answer=answer, distractors_json=distractors_json)

@main_bp.route('/submit_distractor', methods=['GET', 'POST'])
def submit_distractor():
    """Submit new distractors for a question."""
    if 'user_id' not in session:
        return redirect(url_for('auth.login'))
    
    if request.method == 'GET':
        question_id = request.args.get('question_id')
        
        if not question_id:
            return jsonify({'success': False, 'message': 'No question specified.'})
        
        client = supabase_client.get_db()
        question_result = client.table('questions').select('*').eq('id', question_id).execute()
        if not question_result.data:
            return jsonify({'success': False, 'message': 'Question not found.'})
        
        question = question_result.data[0]
        
        # Always use the inline component template
        return render_template('components/distractor_form.html', 
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
            # Check if this is an AJAX request
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
                return jsonify({'success': False, 'message': 'Please provide at least one distractor.'})
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
        
        # Check if this is an AJAX request
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Accept') == 'application/json':
            return jsonify({'success': True, 'message': f'Thank you! Your {len(distractors)} distractor(s) have been submitted for review.'})
        
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
