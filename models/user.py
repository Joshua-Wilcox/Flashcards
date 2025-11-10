from models.supabase_adapter import supabase_client
from datetime import datetime
import json

def is_user_whitelisted(user_id, user_guilds):
    """Check if user is whitelisted for PDF access."""
    with open('whitelist.json', 'r', encoding='utf-8') as f:
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
    with open('whitelist.json', 'r', encoding='utf-8') as f:
        whitelist = json.load(f)
    return int(user_id) in whitelist.get('admin_ids', [])

def get_or_create_user_stats(user_id, username):
    """Get or create user stats entry."""
    client = supabase_client.get_db()
    
    # Check if user exists
    result = client.table('user_stats').select('*').eq('user_id', user_id).execute()
    
    if not result.data:
        # New user: create user_stats entry
        client.table('user_stats').insert({
            'user_id': user_id,
            'username': username,
            'correct_answers': 0,
            'total_answers': 0,
            'current_streak': 0,
            'approved_cards': 0
        }).execute()
        
        # Initialize module_stats entries
        modules_result = client.table('modules').select('*').execute()
        for module in modules_result.data:
            client.table('module_stats').insert({
                'user_id': user_id,
                'module_id': module['id'],
                'number_answered': 0,
                'number_correct': 0,
                'current_streak': 0,
                'approved_cards': 0
            }).execute()
    
    # Return user stats
    result = client.table('user_stats').select('*').eq('user_id', user_id).execute()
    return result.data[0] if result.data else None

def update_user_stats(user_id, module_id, is_correct, last_answer_time):
    """Update user statistics with real-time broadcasting."""
    client = supabase_client.get_db()
    
    # Update module stats
    try:
        # Get current module stats
        result = client.table('module_stats').select('*').eq('user_id', user_id).eq('module_id', module_id).execute()
        
        if result.data:
            # Update existing
            current = result.data[0]
            new_answered = current['number_answered'] + 1
            new_correct = current['number_correct'] + (1 if is_correct else 0)
            new_streak = current['current_streak'] + 1 if is_correct else 0
            
            client.table('module_stats').update({
                'number_answered': new_answered,
                'number_correct': new_correct,
                'current_streak': new_streak,
                'last_answered_time': datetime.fromtimestamp(last_answer_time).isoformat()
            }).eq('user_id', user_id).eq('module_id', module_id).execute()
        else:
            # Create new
            client.table('module_stats').insert({
                'user_id': user_id,
                'module_id': module_id,
                'number_answered': 1,
                'number_correct': 1 if is_correct else 0,
                'current_streak': 1 if is_correct else 0,
                'last_answered_time': datetime.fromtimestamp(last_answer_time).isoformat()
            }).execute()
        
        # Update global user stats
        result = client.table('user_stats').select('*').eq('user_id', user_id).execute()
        if result.data:
            current = result.data[0]
            new_correct = current['correct_answers'] + (1 if is_correct else 0)
            new_total = current['total_answers'] + 1
            new_streak = current['current_streak'] + 1 if is_correct else 0
            
            client.table('user_stats').update({
                'correct_answers': new_correct,
                'total_answers': new_total,
                'current_streak': new_streak,
                'last_answer_time': datetime.fromtimestamp(last_answer_time).isoformat()
            }).eq('user_id', user_id).execute()
    
    except Exception as e:
        print(f"Error updating user stats: {e}")
        raise

def user_has_enough_answers(user_id, minimum=10):
    """Check if a user has at least the minimum number of correct answers."""
    client = supabase_client.get_db()
    result = client.table('user_stats').select('correct_answers').eq('user_id', user_id).execute()
    
    if not result.data:
        return False
    
    correct_answers = result.data[0].get('correct_answers', 0) or 0
    return correct_answers >= minimum
def get_user_stats(user_id):
    """Get comprehensive user statistics."""
    client = supabase_client.get_db()
    
    # Get base user stats
    result = client.table('user_stats').select('*').eq('user_id', user_id).execute()
    
    if not result.data:
        return None
    
    base_stats = result.data[0]
    
    # Get module stats with module names
    module_stats_result = client.table('module_stats').select(
        '*, modules!inner(name)'
    ).eq('user_id', user_id).execute()
    
    # Get all modules to show complete list
    all_modules_result = client.table('modules').select('id, name').execute()
    
    # Initialize all modules with zero stats
    module_stats_dict = {}
    if all_modules_result.data:
        for module in all_modules_result.data:
            module_stats_dict[module['name']] = {
                'number_answered': 0,
                'number_correct': 0,
                'last_answered_time': None,
                'current_streak': 0,
                'approved_cards': 0
            }
    
    # Update with actual stats where they exist
    if module_stats_result.data:
        for row in module_stats_result.data:
            module_name = row['modules']['name']
            module_stats_dict[module_name] = {
                'number_answered': row['number_answered'] or 0,
                'number_correct': row['number_correct'] or 0,
                'last_answered_time': row['last_answered_time'],
                'current_streak': row['current_streak'] or 0,
                'approved_cards': row['approved_cards'] or 0
            }
    
    stats_dict = dict(base_stats)
    stats_dict['module_stats'] = module_stats_dict
    
    return stats_dict

def get_leaderboard(sort='correct_answers', order='desc', module_filter=None):
    """Get leaderboard data with real-time capability."""
    client = supabase_client.get_db()
    
    # Map frontend sort parameters to database column names
    sort_mapping = {
        'correct_answers': 'number_correct',
        'total_answers': 'number_answered',
        'current_streak': 'current_streak',
        'approved_cards': 'approved_cards',
        'last_answer_time': 'last_answered_time'
    }
    
    # Get the actual database column name
    db_sort_column = sort_mapping.get(sort, 'number_correct')
    order_direction = order == 'desc'
    
    # Special handling for accuracy - we'll sort in Python after calculation
    sort_by_accuracy = sort == 'accuracy'
    
    if module_filter and module_filter != 'all':
        # Module-specific leaderboard - need to do manual join since no FK relationship
        # First get the module ID
        module_result = client.table('modules').select('id').eq('name', module_filter).execute()
        if not module_result.data:
            return []
        
        module_id = module_result.data[0]['id']
        
        # Get module stats for this module
        # If sorting by accuracy, don't apply database sort - we'll sort in Python
        if sort_by_accuracy:
            result = client.table('module_stats').select(
                'user_id, number_correct, number_answered, current_streak, approved_cards, last_answered_time'
            ).eq('module_id', module_id).execute()  # pylint: disable=no-member
        else:
            result = client.table('module_stats').select(
                'user_id, number_correct, number_answered, current_streak, approved_cards, last_answered_time'
            ).eq('module_id', module_id).order(db_sort_column, desc=order_direction).execute()  # pylint: disable=no-member
        
        # Get all usernames at once for efficiency
        user_ids = [row['user_id'] for row in result.data]
        if user_ids:
            users_result = client.table('user_stats').select('user_id, username').in_('user_id', user_ids).execute()  # pylint: disable=no-member
            username_lookup = {user['user_id']: user['username'] for user in users_result.data}
        else:
            username_lookup = {}
        
        leaderboard = []
        for row in result.data:
            username = username_lookup.get(row['user_id'], row['user_id'])
            
            total_answers = row['number_answered'] or 0
            correct_answers = row['number_correct'] or 0
            accuracy = correct_answers / total_answers if total_answers > 0 else 0
            
            leaderboard.append({
                'user_id': row['user_id'],
                'username': username,
                'correct_answers': correct_answers,
                'total_answers': total_answers,
                'accuracy': accuracy,
                'current_streak': row['current_streak'],
                'approved_cards': row['approved_cards'],
                'last_answer_time': row['last_answered_time']
            })
        
        # Sort by accuracy in Python if needed
        if sort_by_accuracy:
            leaderboard.sort(key=lambda x: x['accuracy'], reverse=order_direction)
    else:
        # Global leaderboard - user_stats table has different column names
        global_sort_mapping = {
            'correct_answers': 'correct_answers',
            'total_answers': 'total_answers', 
            'current_streak': 'current_streak',
            'last_answer_time': 'last_answer_time'
        }
        global_db_sort_column = global_sort_mapping.get(sort, 'correct_answers')
        
        # If sorting by accuracy, don't apply database sort - we'll sort in Python
        if sort_by_accuracy:
            result = client.table('user_stats').select('*').execute()  # pylint: disable=no-member
        else:
            result = client.table('user_stats').select('*').order(global_db_sort_column, desc=order_direction).execute()  # pylint: disable=no-member
        
        leaderboard = []
        for row in result.data:
            total_answers = row['total_answers'] or 0
            correct_answers = row['correct_answers'] or 0
            accuracy = correct_answers / total_answers if total_answers > 0 else 0
            
            leaderboard.append({
                'user_id': row['user_id'],
                'username': row['username'],
                'correct_answers': correct_answers,
                'total_answers': total_answers,
                'accuracy': accuracy,
                'current_streak': row.get('current_streak', 0),
                'approved_cards': row.get('approved_cards', 0),
                'last_answer_time': row.get('last_answer_time')
            })
        
        # Sort by accuracy in Python if needed
        if sort_by_accuracy:
            leaderboard.sort(key=lambda x: x['accuracy'], reverse=order_direction)
    
    return leaderboard
