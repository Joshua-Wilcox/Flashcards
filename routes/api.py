from flask import Blueprint, jsonify, request
from flask_discord import DiscordOAuth2Session
from models.database import get_db
from models.question import find_semantic_duplicates

api_bp = Blueprint('api', __name__)

@api_bp.route('/api/suggest/topics', methods=['POST'])
# Add these new API routes for auto-suggestions
def suggest_topics():
    from app import discord
    if not discord.authorized:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    module_name = data.get('module', '')
    query = data.get('query', '').lower()
    
    if not module_name:
        return jsonify({'suggestions': []})
    
    db = get_db()
    
    # Get module ID
    module_row = db.execute('SELECT id FROM modules WHERE name = ?', (module_name,)).fetchone()
    if not module_row:
        return jsonify({'suggestions': []})
    
    module_id = module_row['id']
    
    # Get topics for this module with occurrence count
    if query:
        topics = db.execute('''
            SELECT t.name, COUNT(qt.question_id) as count
            FROM topics t
            JOIN question_topics qt ON t.id = qt.topic_id
            JOIN questions q ON qt.question_id = q.id
            WHERE q.module_id = ? AND LOWER(t.name) LIKE ?
            GROUP BY t.name
            ORDER BY count DESC, t.name
            LIMIT 10
        ''', (module_id, f'%{query}%')).fetchall()
    else:
        topics = db.execute('''
            SELECT t.name, COUNT(qt.question_id) as count
            FROM topics t
            JOIN question_topics qt ON t.id = qt.topic_id
            JOIN questions q ON qt.question_id = q.id
            WHERE q.module_id = ?
            GROUP BY t.name
            ORDER BY count DESC, t.name
            LIMIT 10
        ''', (module_id,)).fetchall()
    
    suggestions = [{'name': row['name'], 'count': row['count']} for row in topics]
    return jsonify({'suggestions': suggestions})


@api_bp.route('/api/suggest/subtopics', methods=['POST'])
def suggest_subtopics():
    from app import discord
    if not discord.authorized:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    module_name = data.get('module', '')
    topic_name = data.get('topic', '')
    query = data.get('query', '').lower()
    
    if not module_name or not topic_name:
        return jsonify({'suggestions': []})
    
    db = get_db()
    
    # Get module ID
    module_row = db.execute('SELECT id FROM modules WHERE name = ?', (module_name,)).fetchone()
    if not module_row:
        return jsonify({'suggestions': []})
    
    module_id = module_row['id']
    
    # Get topic ID
    topic_row = db.execute('SELECT id FROM topics WHERE name = ?', (topic_name,)).fetchone()
    if not topic_row:
        return jsonify({'suggestions': []})
    
    topic_id = topic_row['id']
    
    # Get subtopics for this module and topic with occurrence count
    if query:
        subtopics = db.execute('''
            SELECT s.name, COUNT(qs.question_id) as count
            FROM subtopics s
            JOIN question_subtopics qs ON s.id = qs.subtopic_id
            JOIN questions q ON qs.question_id = q.id
            JOIN question_topics qt ON q.id = qt.question_id
            WHERE q.module_id = ? AND qt.topic_id = ? AND LOWER(s.name) LIKE ?
            GROUP BY s.name
            ORDER BY count DESC, s.name
            LIMIT 10
        ''', (module_id, topic_id, f'%{query}%')).fetchall()
    else:
        subtopics = db.execute('''
            SELECT s.name, COUNT(qs.question_id) as count
            FROM subtopics s
            JOIN question_subtopics qs ON s.id = qs.subtopic_id
            JOIN questions q ON qs.question_id = q.id
            JOIN question_topics qt ON q.id = qt.question_id
            WHERE q.module_id = ? AND qt.topic_id = ?
            GROUP BY s.name
            ORDER BY count DESC, s.name
            LIMIT 10
        ''', (module_id, topic_id)).fetchall()
    
    suggestions = [{'name': row['name'], 'count': row['count']} for row in subtopics]
    return jsonify({'suggestions': suggestions})

@api_bp.route('/api/suggest/tags', methods=['POST'])
def suggest_tags():
    from app import discord
    if not discord.authorized:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    module_name = data.get('module', '')
    topic_name = data.get('topic', '')
    subtopic_name = data.get('subtopic', '')
    query = data.get('query', '').lower()
    
    if not module_name:
        return jsonify({'suggestions': []})
    
    db = get_db()
    
    # Get module ID
    module_row = db.execute('SELECT id FROM modules WHERE name = ?', (module_name,)).fetchone()
    if not module_row:
        return jsonify({'suggestions': []})
    
    module_id = module_row['id']
    
    # Base query to get tags for this module
    sql = '''
        SELECT t.name, COUNT(qt.question_id) as count
        FROM tags t
        JOIN question_tags qt ON t.id = qt.tag_id
        JOIN questions q ON qt.question_id = q.id
        WHERE q.module_id = ?
    '''
    params = [module_id]
    
    # Add topic filter if provided
    if topic_name:
        sql += '''
            AND EXISTS (
                SELECT 1 FROM question_topics qtop
                JOIN topics top ON qtop.topic_id = top.id
                WHERE qtop.question_id = q.id AND top.name = ?
            )
        '''
        params.append(topic_name)
    
    # Add subtopic filter if provided
    if subtopic_name:
        sql += '''
            AND EXISTS (
                SELECT 1 FROM question_subtopics qsub
                JOIN subtopics sub ON qsub.subtopic_id = sub.id
                WHERE qsub.question_id = q.id AND sub.name = ?
            )
        '''
        params.append(subtopic_name)
    
    # Add query filter if provided
    if query:
        sql += ' AND LOWER(t.name) LIKE ?'
        params.append(f'%{query}%')
    
    # Finalize the query
    sql += '''
        GROUP BY t.name
        ORDER BY count DESC, t.name
        LIMIT 10
    '''
    
    tags = db.execute(sql, params).fetchall()
    suggestions = [{'name': row['name'], 'count': row['count']} for row in tags]
    return jsonify({'suggestions': suggestions})

@api_bp.route('/api/check_duplicates', methods=['POST'])
def check_duplicates():
    """
    Check for potential duplicate questions in the same module using semantic similarity.
    Returns a list of similar questions if any are found.
    """
    from app import discord
    if not discord.authorized:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    question_text = data.get('question', '').strip()
    module_name = data.get('module', '')
    
    if not question_text or not module_name or len(question_text) < 10:
        return jsonify({'duplicates': []})
    
    db = get_db()
    
    # Get module ID
    module_row = db.execute('SELECT id FROM modules WHERE name = ?', (module_name,)).fetchone()
    if not module_row:
        return jsonify({'duplicates': []})
    
    module_id = module_row['id']
    
    # Find semantically similar questions
    potential_duplicates = find_semantic_duplicates(db, question_text, module_id)
    
    return jsonify({'duplicates': potential_duplicates})
