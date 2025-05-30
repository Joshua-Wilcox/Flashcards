from flask import Blueprint, render_template, request, session, redirect, url_for
from models.user import get_user_stats, get_leaderboard
from models.database import get_all_modules, get_db

user_bp = Blueprint('user', __name__)

@user_bp.route('/stats')
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

@user_bp.route('/user_stats/<user_id>')
def user_stats(user_id):
    """Display another user's statistics."""
    module_filter = request.args.get('module', None)
    stats_dict = get_user_stats(user_id)
    
    if not stats_dict:
        return redirect(url_for('main.index'))
    
    stats_dict['active_module'] = module_filter
    modules = get_all_modules()
    
    return render_template('stats.html', stats=stats_dict, 
                         is_other_user=True, modules=modules)

@user_bp.route('/leaderboard')
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
