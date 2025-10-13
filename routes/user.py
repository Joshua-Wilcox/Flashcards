from flask import Blueprint, render_template, request, session, redirect, url_for
from models.user import get_user_stats, get_leaderboard
from models.supabase_adapter import supabase_client
from models.database import get_all_modules, group_modules_by_year

user_bp = Blueprint('user', __name__)

@user_bp.route('/stats')
def stats():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    module_filter = request.args.get('module', None)
    client = supabase_client.get_db()
    
    # Get base user stats
    base_stats_result = client.table('user_stats').select('''
        user_id, username, correct_answers, total_answers, 
        last_answer_time, current_streak, approved_cards
    ''').eq('user_id', session['user_id']).execute()
    
    base_stats = base_stats_result.data[0] if base_stats_result.data else {}
    
    module_stats_result = client.table('module_stats').select('''
        number_answered, number_correct, 
        last_answered_time, current_streak, approved_cards,
        modules!inner(name)
    ''').eq('user_id', session['user_id']).execute()
    
    # Convert to the expected format
    module_stats_dict = {}
    
    # First, get all modules to ensure we show all of them
    all_modules_result = client.table('modules').select('name').execute()
    
    # Initialize all modules with zero stats
    if all_modules_result.data:
        for module in all_modules_result.data:
            module_name = module['name']
            module_stats_dict[module_name] = {
                'number_answered': 0,
                'number_correct': 0,
                'last_answered_time': None,
                'current_streak': 0,
                'approved_cards': 0
            }
    
    # Update with actual stats where they exist
    if module_stats_result.data:
        for stat in module_stats_result.data:
            module_name = stat['modules']['name']
            module_stats_dict[module_name] = {
                'number_answered': stat.get('number_answered', 0) or 0,
                'number_correct': stat.get('number_correct', 0) or 0,
                'last_answered_time': stat.get('last_answered_time'),
                'current_streak': stat.get('current_streak', 0) or 0,
                'approved_cards': stat.get('approved_cards', 0) or 0
            }
    
    stats_dict = dict(base_stats) if base_stats else {}
    stats_dict['module_stats'] = module_stats_dict
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
    
    # Use the existing get_leaderboard function from models.user
    leaderboard_data = get_leaderboard(sort, order, module_filter)
    
    modules = get_all_modules()
    module_groups = group_modules_by_year(modules)
    return render_template('leaderboard.html', 
                         leaderboard=leaderboard_data, 
                         sort=sort, 
                         order=order, 
                         modules=modules,
                         module_groups=module_groups, 
                         active_module=module_filter)
