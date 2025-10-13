"""
Admin routes for flashcard application.
Handles all administrative operations including reviewing submissions,
managing reports, and handling PDF access requests.
"""

import json
import os
import time
import hashlib
import io
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify, make_response, send_file
from models.supabase_adapter import supabase_client
from models.question import get_all_modules, get_module_id_by_name, add_tags_and_link_question, add_topic_and_link_question, add_subtopic_and_link_question

admin_bp = Blueprint('admin', __name__)

# Module-level cache for modules list
_modules_cache = None
_cache_timestamp = 0
CACHE_DURATION = 300  # 5 minutes

def get_cached_modules():
    """Get modules with caching to avoid repeated database calls."""
    global _modules_cache, _cache_timestamp
    current_time = time.time()
    
    if _modules_cache is None or (current_time - _cache_timestamp) > CACHE_DURATION:
        _modules_cache = get_all_modules()
        _cache_timestamp = current_time
    
    return _modules_cache

def is_user_admin(user_id):
    """Check if a user has admin privileges."""
    try:
        with open('whitelist.json', 'r', encoding='utf-8') as f:
            whitelist = json.load(f)
        return int(user_id) in whitelist.get('admin_ids', [])
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return False

def is_user_whitelisted(user_id, user_guilds=None):
    """Check if a user is whitelisted for PDF access."""
    try:
        with open('whitelist.json', 'r', encoding='utf-8') as f:
            whitelist = json.load(f)
        return int(user_id) in whitelist.get('user_ids', [])
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return False

def admin_required(f):
    """Decorator to require admin privileges for a route."""
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or not is_user_admin(session['user_id']):
            return redirect(url_for('main.index'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function

@admin_bp.route('/admin_review_flashcards')
@admin_required
def admin_review_flashcards():
    if 'user_id' not in session or not is_user_admin(session['user_id']):
        return redirect(url_for('index'))
    
    client = supabase_client.get_db()
    
    # Get submitted flashcards
    rows = client.table('submitted_flashcards').select('*').order('created_at').execute()
    submissions = rows.data if rows.data else []
    
    # Get reported questions
    reports_result = client.table('reported_questions').select('*').order('created_at').execute()
    reports = reports_result.data if reports_result.data else []
    
    # Get PDF access requests
    pdf_requests_result = client.table('requests_to_access').select('*').order('created_at').execute()
    pdf_requests = pdf_requests_result.data if pdf_requests_result.data else []
    
    # Get distractor submissions without join (since no FK relationship exists)
    distractor_result = client.table('submitted_distractors').select('*').order('created_at').execute()
    distractor_submissions = distractor_result.data if distractor_result.data else []
    
    # Enhance distractor submissions with question text if needed
    for distractor in distractor_submissions:
        question_id = distractor.get('question_id')
        if question_id:
            # Try to get question text for display
            question_result = client.table('questions').select('question').eq('id', question_id).execute()
            if question_result.data:
                distractor['question_text'] = question_result.data[0]['question']
            else:
                distractor['question_text'] = f"Question ID: {question_id}"
    
    return render_template('admin_review_flashcards.html', 
                         submissions=submissions, 
                         reports=reports, 
                         pdf_requests=pdf_requests,
                         distractor_submissions=distractor_submissions)

@admin_bp.route('/admin_review_flashcard/<int:submission_id>', methods=['GET', 'POST'])
@admin_required
def admin_review_flashcard(submission_id):
    if 'user_id' not in session or not is_user_admin(session['user_id']):
        return redirect(url_for('index'))
    
    client = supabase_client.get_db()
    
    # Get submission
    submission_result = client.table('submitted_flashcards').select('*').eq('id', submission_id).execute()
    if not submission_result.data:
        flash('Submission not found.')
        return redirect(url_for('admin.admin_review_flashcards'))
    
    submission = submission_result.data[0]
    modules = get_cached_modules()
    
    if request.method == 'POST':
        action = request.form.get('action')
        question = request.form.get('question', '').strip()
        answer = request.form.get('answer', '').strip()
        module = request.form.get('module', '').strip()
        topic = request.form.get('topic', '').strip()
        subtopic = request.form.get('subtopic', '').strip()
        tags = request.form.get('tags', '').strip()
        
        if action == 'approve':
            # Validate inputs early
            if not all([question, answer, module]):
                flash('Question, answer, and module are required.')
                return redirect(url_for('admin.admin_review_flashcards'))
            
            module_id = get_module_id_by_name(client, module)
            if not module_id:
                flash('Invalid module selected.')
                return redirect(url_for('admin.admin_review_flashcards'))
            
            try:
                # Prepare tags list
                tag_list = [t.strip() for t in tags.split(',') if t.strip()] if tags else []
                
                # Use comprehensive RPC function for entire approval process
                result = client.rpc('admin_approve_flashcard', {
                    'submission_id_param': submission_id,
                    'question_param': question,
                    'answer_param': answer,
                    'module_id_param': module_id,
                    'topic_param': topic.strip() if topic else None,
                    'subtopic_param': subtopic.strip() if subtopic else None,
                    'tags_param': tag_list if tag_list else None
                }).execute()
                
                if result.data and result.data.get('success'):
                    pending_count = result.data.get('pending_distractors_count', 0)
                    if pending_count > 0:
                        flash(f'Flashcard approved and added to the database. {pending_count} associated distractor(s) are now available for review in the "Distractor Submissions" section.')
                    else:
                        flash('Flashcard approved and added to the database.')
                else:
                    error_msg = result.data.get('error', 'Unknown error occurred') if result.data else 'RPC call failed'
                    flash(f'Error approving flashcard: {error_msg}')
                    return redirect(url_for('admin.admin_review_flashcards'))
                    
            except Exception as e:
                flash(f'Error approving flashcard: {str(e)}')
                return redirect(url_for('admin.admin_review_flashcards'))
                
            return redirect(url_for('admin.admin_review_flashcards'))
            
        elif action == 'reject':
            try:
                # Use RPC for atomic rejection operation
                result = client.rpc('admin_reject_flashcard', {
                    'submission_id_param': submission_id
                }).execute()
                
                if result.data and result.data.get('success'):
                    rejected_count = result.data.get('rejected_distractors_count', 0)
                    if rejected_count > 0:
                        flash(f'Flashcard submission rejected and removed. {rejected_count} associated distractor(s) also removed.')
                    else:
                        flash('Flashcard submission rejected and removed.')
                else:
                    # Fallback to individual operations
                    flashcard_distractor_key = f"flashcard_{submission_id}"
                    rejected_distractors_result = client.table('submitted_distractors').select('id').eq('question_id', flashcard_distractor_key).execute()
                    rejected_count = len(rejected_distractors_result.data) if rejected_distractors_result.data else 0
                    
                    client.table('submitted_flashcards').delete().eq('id', submission_id).execute()
                    client.table('submitted_distractors').delete().eq('question_id', flashcard_distractor_key).execute()
                    
                    if rejected_count > 0:
                        flash(f'Flashcard submission rejected and removed. {rejected_count} associated distractor(s) also removed.')
                    else:
                        flash('Flashcard submission rejected and removed.')
            except Exception as e:
                flash(f'Error rejecting flashcard: {str(e)}')
                
            return redirect(url_for('admin.admin_review_flashcards'))
            
    return render_template('admin_review_flashcard.html', submission=submission, modules=[m['name'] for m in modules])

@admin_bp.route('/admin_review_report/<int:report_id>', methods=['GET', 'POST'])
@admin_required
def admin_review_report(report_id):
    if 'user_id' not in session or not is_user_admin(session['user_id']):
        return redirect(url_for('index'))
    
    client = supabase_client.get_db()
    
    # Get report
    report_result = client.table('reported_questions').select('*').eq('id', report_id).execute()
    if not report_result.data:
        flash('Report not found.')
        return redirect(url_for('admin.admin_review_flashcards'))
    
    report = report_result.data[0]
    
    # Try to get the original question row
    question_row = None
    if report['question_id']:
        question_result = client.table('questions').select('*').eq('id', report['question_id']).execute()
        if question_result.data:
            question_row = question_result.data[0]
    
    # Parse distractors from JSON
    distractors = []
    if report['distractors']:
        try:
            parsed_distractors = json.loads(report['distractors'])
            for d in parsed_distractors:
                if d.get('type') == 'manual_distractor':
                    # Fetch current manual distractor data
                    manual_d_result = client.table('manual_distractors').select('id, distractor_text').eq('id', d['id']).execute()
                    if manual_d_result.data:
                        manual_d = manual_d_result.data[0]
                        distractors.append({
                            'id': manual_d['id'],
                            'question': d['question'],
                            'answer': manual_d['distractor_text'],
                            'type': 'manual_distractor'
                        })
                else:
                    # Regular question distractor
                    question_d_result = client.table('questions').select('id, question, answer').eq('id', d['id']).execute()
                    if question_d_result.data:
                        question_d = question_d_result.data[0]
                        distractors.append({
                            'id': question_d['id'],
                            'question': question_d['question'],
                            'answer': question_d['answer'],
                            'type': 'question'
                        })
        except:
            # Handle potential JSON parsing error
            pass
    
    # If POST, handle update or discard
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'discard':
            client.table('reported_questions').delete().eq('id', report_id).execute()
            flash('Report discarded.')
            return redirect(url_for('admin.admin_review_flashcards'))
            
        elif action == 'update':
            # Main question update
            new_question = request.form.get('question', '').strip()
            new_answer = request.form.get('answer', '').strip()
            delete_main = request.form.get('delete_question') == '1'
            
            if question_row:
                # Check if the main question should be deleted
                if delete_main:
                    client.table('questions').delete().eq('id', question_row['id']).execute()
                    flash('Main question has been deleted.')
                else:
                    # Update the main question if not deleting
                    client.table('questions').update({
                        'question': new_question,
                        'answer': new_answer
                    }).eq('id', question_row['id']).execute()
            
            # Distractor updates
            for i in range(len(distractors)):
                distractor = distractors[i]
                delete_distractor = request.form.get(f'delete_distractor_{i}') == '1'
                
                if delete_distractor:
                    # Delete this distractor
                    if distractor['type'] == 'manual_distractor':
                        client.table('manual_distractors').delete().eq('id', distractor['id']).execute()
                        flash(f'Manual distractor {i+1} has been deleted.')
                    else:
                        client.table('questions').delete().eq('id', distractor['id']).execute()
                        flash(f'Distractor {i+1} has been deleted.')
                else:
                    # Update this distractor
                    distractor_question = request.form.get(f'distractor_question_{i}', '').strip()
                    distractor_answer = request.form.get(f'distractor_answer_{i}', '').strip()
                    
                    if distractor['type'] == 'manual_distractor':
                        # Only update the distractor text for manual distractors
                        client.table('manual_distractors').update({
                            'distractor_text': distractor_answer
                        }).eq('id', distractor['id']).execute()
                    else:
                        # Update both question and answer for regular questions
                        client.table('questions').update({
                            'question': distractor_question,
                            'answer': distractor_answer
                        }).eq('id', distractor['id']).execute()
            
            client.table('reported_questions').delete().eq('id', report_id).execute()
            flash('Changes have been applied and report resolved.')
            return redirect(url_for('admin.admin_review_flashcards'))
    
    return render_template('admin_review_report.html', report=report, question_row=question_row, distractors=distractors)

@admin_bp.route('/admin_review_distractor/<int:submission_id>', methods=['GET', 'POST'])
@admin_required
def admin_review_distractor(submission_id):
    if 'user_id' not in session or not is_user_admin(session['user_id']):
        return redirect(url_for('index'))
    
    client = supabase_client.get_db()
    
    # Get submission without join (since no FK relationship exists)
    submission_result = client.table('submitted_distractors').select('*').eq('id', submission_id).execute()
    
    if not submission_result.data:
        flash('Distractor submission not found.')
        return redirect(url_for('admin.admin_review_flashcards'))
    
    submission = submission_result.data[0]
    
    # Get question details separately
    question_id = submission.get('question_id')
    if question_id:
        question_result = client.table('questions').select('question, answer').eq('id', question_id).execute()
        if question_result.data:
            submission['question_details'] = question_result.data[0]
        else:
            submission['question_details'] = {'question': f'Question ID: {question_id}', 'answer': 'Not found'}
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'approve':
            # Add distractor to manual_distractors table
            try:
                client.table('manual_distractors').insert({
                    'question_id': submission['question_id'],
                    'distractor_text': submission['distractor_text'],
                    'created_by': submission['user_id']
                }).execute()
                
                # Upsert user_stats
                client.table('user_stats').upsert({
                    'user_id': submission['user_id'],
                    'username': submission.get('username', 'Unknown'),  # Get username from submission
                    'approved_cards': 0
                }, on_conflict='user_id').execute()
                
                # Update user stats for approved cards
                existing_stats = client.table('user_stats').select('approved_cards').eq('user_id', submission['user_id']).execute()
                current_approved = existing_stats.data[0]['approved_cards'] if existing_stats.data else 0
                
                client.table('user_stats').update({
                    'approved_cards': current_approved + 1
                }).eq('user_id', submission['user_id']).execute()
                
                # Remove from submissions
                client.table('submitted_distractors').delete().eq('id', submission_id).execute()
                
                flash('Distractor approved and added!')
                
            except Exception as e:
                flash(f'Error approving distractor: {str(e)}')
        
        elif action == 'reject':
            client.table('submitted_distractors').delete().eq('id', submission_id).execute()
            flash('Distractor submission rejected.')
        
        return redirect(url_for('admin.admin_review_flashcards'))
    
    return render_template('admin_review_distractor.html', submission=submission)

@admin_bp.route('/admin_review_pdf_request/<int:request_id>', methods=['GET', 'POST'])
@admin_required
def admin_review_pdf_request(request_id):
    if 'user_id' not in session or not is_user_admin(session['user_id']):
        return redirect(url_for('index'))
    
    client = supabase_client.get_db()
    
    # Get request
    req_result = client.table('requests_to_access').select('*').eq('id', request_id).execute()
    if not req_result.data:
        flash('PDF access request not found.')
        return redirect(url_for('admin.admin_review_flashcards'))
    
    req = req_result.data[0]
    
    if request.method == 'POST':
        action = request.form.get('action')
        discord_id = req['discord_id']
        
        # Remove the request from the DB
        client.table('requests_to_access').delete().eq('id', request_id).execute()
        
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
        return redirect(url_for('admin.admin_review_flashcards'))
        
    return render_template('admin_review_pdf_request.html', req=req)

@admin_bp.route('/pdf/<int:pdf_id>')
def serve_pdf_by_id(pdf_id):
    """Serve PDF by database ID with access control"""
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



@admin_bp.route('/pdf-management')
@admin_required
def pdf_management():
    """PDF management interface for admins"""
    return render_template('admin_pdf_management.html')


# Template filter for formatting timestamps
@admin_bp.app_template_filter('datetimeformat')
def datetimeformat_filter(value):
    """Format timestamp for display in templates."""
    try:
        # Handle Supabase TIMESTAMPTZ format
        if isinstance(value, str):
            # Parse ISO format timestamp from Supabase
            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            return dt.strftime('%Y-%m-%d %H:%M')
        else:
            # Fallback for integer timestamps
            return datetime.utcfromtimestamp(int(value)).strftime('%Y-%m-%d %H:%M')
    except (ValueError, TypeError):
        return value

# Context processor to make admin check available in templates
@admin_bp.app_context_processor
def inject_admin_functions():
    """Make admin utility functions available in templates."""
    return dict(is_user_admin=is_user_admin)

@admin_bp.route('/edit_answer', methods=['POST'])
def edit_answer():
    if 'user_id' not in session:
        return jsonify({'error': 'Unauthorized'}), 401
    if not is_user_admin(session['user_id']):
        return jsonify({'error': 'Unauthorized'}), 403
    
    data = request.get_json()
    question_id = data.get('question_id')
    new_text = data.get('new_text')
    edit_type = data.get('edit_type', 'question')  # 'question' or 'manual_distractor'
    manual_distractor_id = data.get('manual_distractor_id')
    
    if not new_text:
        return jsonify({'error': 'Missing required data'}), 400
    
    client = supabase_client.get_db()
    try:
        if edit_type == 'manual_distractor' and manual_distractor_id:
            # Edit manual distractor
            client.table('manual_distractors').update({
                'distractor_text': new_text
            }).eq('id', manual_distractor_id).execute()
        elif edit_type == 'question' and question_id:
            # Edit regular question answer
            client.table('questions').update({
                'answer': new_text
            }).eq('id', question_id).execute()
        else:
            return jsonify({'error': 'Invalid edit type or missing ID'}), 400
            
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'error': str(e)}), 500
