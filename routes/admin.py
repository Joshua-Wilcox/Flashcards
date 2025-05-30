"""
Admin routes for flashcard application.
Handles all administrative operations including reviewing submissions,
managing reports, and handling PDF access requests.
"""

import json
import os
import time
import hashlib
import sqlite3
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify
from models.database import get_db
from models.question import get_all_modules, get_module_id_by_name, add_tags_and_link_question, add_topic_and_link_question, add_subtopic_and_link_question

admin_bp = Blueprint('admin', __name__)

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
    # user_guilds parameter kept for compatibility but not used
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
    db = get_db()
    rows = db.execute('SELECT * FROM submitted_flashcards ORDER BY timestamp ASC').fetchall()
    reports = db.execute('SELECT * FROM reported_questions ORDER BY timestamp ASC').fetchall()
    pdf_requests = db.execute('SELECT * FROM requests_to_access ORDER BY timestamp ASC').fetchall()
    distractor_submissions = db.execute('''
        SELECT sd.*, q.question 
        FROM submitted_distractors sd
        JOIN questions q ON sd.question_id = q.id
        ORDER BY sd.timestamp ASC
    ''').fetchall()
    return render_template('admin_review_flashcards.html', 
                         submissions=rows, 
                         reports=reports, 
                         pdf_requests=pdf_requests,
                         distractor_submissions=distractor_submissions)

@admin_bp.route('/admin_review_flashcard/<int:submission_id>', methods=['GET', 'POST'])
@admin_required
def admin_review_flashcard(submission_id):
    if 'user_id' not in session or not is_user_admin(session['user_id']):
        return redirect(url_for('index'))
    db = get_db()
    submission = db.execute('SELECT * FROM submitted_flashcards WHERE id = ?', (submission_id,)).fetchone()
    modules = get_all_modules()
    if not submission:
        flash('Submission not found.')
        return redirect(url_for('admin.admin_review_flashcards'))
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
            return redirect(url_for('admin.admin_review_flashcards'))
        elif action == 'reject':
            db.execute('DELETE FROM submitted_flashcards WHERE id = ?', (submission_id,))
            db.commit()
            flash('Flashcard submission rejected and removed.')
            return redirect(url_for('admin.admin_review_flashcards'))
    return render_template('admin_review_flashcard.html', submission=submission, modules=[m['name'] for m in modules])

@admin_bp.route('/admin_review_report/<int:report_id>', methods=['GET', 'POST'])
@admin_required
def admin_review_report(report_id):
    if 'user_id' not in session or not is_user_admin(session['user_id']):
        return redirect(url_for('index'))
    db = get_db()
    report = db.execute('SELECT * FROM reported_questions WHERE id = ?', (report_id,)).fetchone()
    if not report:
        flash('Report not found.')
        return redirect(url_for('admin.admin_review_flashcards'))
    
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
            return redirect(url_for('admin.admin_review_flashcards'))
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
            return redirect(url_for('admin.admin_review_flashcards'))
    
    return render_template('admin_review_report.html', report=report, question_row=question_row, distractors=distractors)

@admin_bp.route('/admin_review_distractor/<int:submission_id>', methods=['GET', 'POST'])
@admin_required
def admin_review_distractor(submission_id):
    if 'user_id' not in session or not is_user_admin(session['user_id']):
        return redirect(url_for('index'))
    
    db = get_db()
    submission = db.execute('''
        SELECT sd.*, q.question, q.answer 
        FROM submitted_distractors sd
        JOIN questions q ON sd.question_id = q.id
        WHERE sd.id = ?
    ''', (submission_id,)).fetchone()
    
    if not submission:
        flash('Distractor submission not found.')
        return redirect(url_for('admin.admin_review_flashcards'))
    
    if request.method == 'POST':
        action = request.form.get('action')
        
        if action == 'approve':
            # Add to manual_distractors table
            db.execute('''
                INSERT INTO manual_distractors 
                (question_id, distractor_text, created_by, created_at)
                VALUES (?, ?, ?, ?)
            ''', (submission['question_id'], submission['distractor_text'], 
                  submission['user_id'], int(time.time())))
            
            # Update user stats for approved cards
            db.execute('''
                UPDATE user_stats 
                SET approved_cards = COALESCE(approved_cards, 0) + 1
                WHERE user_id = ?
            ''', (submission['user_id'],))
            
            # Remove from submissions
            db.execute('DELETE FROM submitted_distractors WHERE id = ?', (submission_id,))
            db.commit()
            
            flash('Distractor approved and added!')
            
        elif action == 'reject':
            db.execute('DELETE FROM submitted_distractors WHERE id = ?', (submission_id,))
            db.commit()
            flash('Distractor submission rejected.')
        
        return redirect(url_for('admin.admin_review_flashcards'))
    
    return render_template('admin_review_distractor.html', submission=submission)

@admin_bp.route('/admin_review_pdf_request/<int:request_id>', methods=['GET', 'POST'])
@admin_required
def admin_review_pdf_request(request_id):
    if 'user_id' not in session or not is_user_admin(session['user_id']):
        return redirect(url_for('index'))
    db = get_db()
    req = db.execute('SELECT * FROM requests_to_access WHERE id = ?', (request_id,)).fetchone()
    if not req:
        flash('PDF access request not found.')
        return redirect(url_for('admin.admin_review_flashcards'))
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
        return redirect(url_for('admin.admin_review_flashcards'))
    return render_template('admin_review_pdf_request.html', req=req)

@admin_bp.route('/pdf/<path:pdf_path>')
def serve_pdf(pdf_path):
    from app import discord
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

# Template filter for formatting timestamps
@admin_bp.app_template_filter('datetimeformat')
def datetimeformat_filter(value):
    """Format timestamp for display in templates."""
    try:
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
