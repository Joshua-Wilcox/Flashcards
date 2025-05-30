from models.database import get_db, get_all_modules, get_module_id_by_name
import json
import os

def is_user_whitelisted(user_id, user_guilds):
    """Check if user is whitelisted for PDF access."""
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

def is_user_admin(user_id):
    """Check if user is an admin."""
    with open('whitelist.json', 'r') as f:
        whitelist = json.load(f)
    return int(user_id) in whitelist.get('admin_ids', [])

def get_or_create_user_stats(user_id, username):
    """Get or create user stats entry."""
    db = get_db()
    row = db.execute('SELECT * FROM user_stats WHERE user_id = ?', (user_id,)).fetchone()
    
    if not row:
        # New user: create user_stats entry
        db.execute('''INSERT INTO user_stats 
                     (user_id, username, correct_answers, total_answers, current_streak) 
                     VALUES (?, ?, 0, 0, 0)''', 
                  (user_id, username))
        
        # Initialize module_stats entries
        modules = get_all_modules()
        for module in modules:
            module_id = get_module_id_by_name(db, module['name'])
            db.execute('''INSERT INTO module_stats 
                        (user_id, module_id, number_answered, number_correct, current_streak)
                        VALUES (?, ?, 0, 0, 0)''',
                     (user_id, module_id))
        db.commit()
    
    return db.execute('SELECT * FROM user_stats WHERE user_id = ?', (user_id,)).fetchone()

def update_user_stats(user_id, module_id, is_correct, last_answer_time):
    """Update user statistics after answering a question."""
    db = get_db()
    
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

    # Update overall user stats based on aggregated module stats
    db.execute('''UPDATE user_stats 
                  SET correct_answers = (SELECT SUM(number_correct) FROM module_stats WHERE user_id = ?),
                      total_answers = (SELECT SUM(number_answered) FROM module_stats WHERE user_id = ?),
                      last_answer_time = ?,
                      current_streak = CASE WHEN ? THEN current_streak + 1 ELSE 0 END
                  WHERE user_id = ?''',
               (user_id, user_id, last_answer_time, is_correct, user_id))

    db.commit()

def user_has_enough_answers(user_id, minimum=10):
    """Check if a user has at least the minimum number of correct answers."""
    db = get_db()
    row = db.execute('SELECT correct_answers FROM user_stats WHERE user_id = ?', (user_id,)).fetchone()
    return row and row['correct_answers'] >= minimum

def get_user_stats(user_id):
    """Get comprehensive user statistics."""
    db = get_db()
    
    # Get base user stats
    base_stats = db.execute('''
        SELECT user_id, username, correct_answers, total_answers, 
               last_answer_time, current_streak, approved_cards
        FROM user_stats 
        WHERE user_id = ?
    ''', (user_id,)).fetchone()
    
    if not base_stats:
        return None
    
    # Get module stats
    module_stats = db.execute('''
        SELECT m.name, ms.number_answered, ms.number_correct, 
               ms.last_answered_time, ms.current_streak, ms.approved_cards
        FROM modules m
        LEFT JOIN module_stats ms ON ms.module_id = m.id 
        AND ms.user_id = ?
    ''', (user_id,)).fetchall()
    
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
    
    return stats_dict

def get_leaderboard(sort='correct_answers', order='desc', module_filter=None):
    """Get leaderboard data."""
    db = get_db()
    order_sql = 'DESC' if order == 'desc' else 'ASC'
    
    # Check if the approved_cards column exists in the user_stats table
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
    
    if module_filter and module_filter != 'all':
        # Module-specific leaderboard
        users = db.execute(f'''
            SELECT ms.user_id, us.username, 
                   ms.number_correct as correct_answers, 
                   ms.number_answered as total_answers,
                   ms.current_streak, ms.approved_cards,
                   us.last_answer_time
            FROM module_stats ms
            JOIN user_stats us ON ms.user_id = us.user_id
            JOIN modules m ON ms.module_id = m.id
            WHERE m.name = ?
            ORDER BY {sort} {order_sql}
        ''', (module_filter,)).fetchall()
    else:
        # Overall leaderboard
        users = db.execute(f'''
            SELECT user_id, username, correct_answers, total_answers, 
                   current_streak, approved_cards, last_answer_time
            FROM user_stats 
            ORDER BY {sort} {order_sql}
        ''').fetchall()

    # Convert DB rows to dictionaries for the template
    return [dict(row) for row in users]
