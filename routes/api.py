from flask import Blueprint, jsonify, request
from config import Config
from models.supabase_adapter import supabase_client, SupabaseAdapter
from models.question import find_semantic_duplicates
from utils.security import verify_ingest_token

api_bp = Blueprint('api', __name__)

# Initialize the adapter instance
adapter = SupabaseAdapter()

def parse_similarity_threshold():
    """
    Parse the X-Similarity-Threshold header and return the threshold value.
    Returns a tuple of (threshold_value, error_response).
    If error_response is not None, it should be returned to the client.
    """
    similarity_threshold = 0.3  # Default threshold
    threshold_header = request.headers.get('X-Similarity-Threshold')
    
    if threshold_header:
        try:
            threshold_value = float(threshold_header)
            # Validate threshold is between 0 and 1
            if 0.0 <= threshold_value <= 1.0:
                similarity_threshold = threshold_value
            else:
                return None, (jsonify({'error': 'X-Similarity-Threshold must be between 0.0 and 1.0'}), 400)
        except ValueError:
            return None, (jsonify({'error': 'X-Similarity-Threshold must be a valid number'}), 400)
    
    return similarity_threshold, None

@api_bp.route('/api/suggest/topics', methods=['POST'])
def suggest_topics():
    from app import discord
    if not discord.authorized:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    module_name = data.get('module', '')
    query = data.get('query', '').lower()
    
    if not module_name:
        return jsonify({'suggestions': []})
    
    # Use RPC function for optimized topic suggestions
    suggestions = adapter.get_topic_suggestions_rpc(module_name, query)
    
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
    
    # Use RPC function for optimized subtopic suggestions
    suggestions = adapter.get_subtopic_suggestions_rpc(module_name, topic_name, query)
    
    return jsonify({'suggestions': suggestions})


@api_bp.route('/api/suggest/tags', methods=['POST'])
def suggest_tags():
    from app import discord
    if not discord.authorized:
        return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    module_name = data.get('module', '')
    query = data.get('query', '').lower()
    
    if not module_name:
        return jsonify({'suggestions': []})
    
    # Use RPC function for optimized tag suggestions
    suggestions = adapter.get_tag_suggestions_rpc(module_name, query)
    
    return jsonify({'suggestions': suggestions})

@api_bp.route('/api/check_duplicates', methods=['POST'])
def check_duplicates():
    """
    Check for potential duplicate questions in the same module using semantic similarity.
    Returns a list of similar questions if any are found.
    Supports X-Similarity-Threshold header to control sensitivity.
    """
    # Check for API token authentication first
    token = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.lower().startswith('bearer '):
        token = auth_header.split(' ', 1)[1]
    else:
        token = request.headers.get('X-API-Key')

    # If token is provided, verify it; otherwise fall back to Discord auth
    if token:
        if not verify_ingest_token(token):
            return jsonify({'error': 'Unauthorized'}), 401
    else:
        from app import discord
        if not discord.authorized:
            return jsonify({'error': 'Unauthorized'}), 401
    
    data = request.get_json()
    question_text = data.get('question', '').strip()
    module_name = data.get('module', '')
    
    if not question_text or not module_name or len(question_text) < 10:
        return jsonify({'duplicates': []})
    
    # Parse similarity threshold from header
    similarity_threshold, error_response = parse_similarity_threshold()
    if error_response:
        return error_response
    
    client = supabase_client.get_db()
    
    # Get module ID
    module_result = client.table('modules').select('id').eq('name', module_name).execute()
    if not module_result.data:
        return jsonify({'duplicates': []})
    
    module_id = module_result.data[0]['id']
    
    # Find semantically similar questions with custom threshold
    potential_duplicates = find_semantic_duplicates(question_text, module_id, threshold=similarity_threshold)
    
    return jsonify({'duplicates': potential_duplicates})


@api_bp.route('/api/ingest_flashcards', methods=['POST'])
def ingest_flashcards():
    """
    Ingest flashcards generated by the n8n workflow, skipping semantic duplicates.
    
    Supports optional X-Similarity-Threshold header (0.0-1.0) to control duplicate detection sensitivity.
    Lower values (e.g., 0.2) = more strict duplicate detection, fewer false positives
    Higher values (e.g., 0.8) = more lenient duplicate detection, more false positives
    Default: 0.3
    """
    token = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.lower().startswith('bearer '):
        token = auth_header.split(' ', 1)[1]
    else:
        token = request.headers.get('X-API-Key')

    if not verify_ingest_token(token):
        return jsonify({'error': 'Unauthorized'}), 401

    # Parse similarity threshold from header
    similarity_threshold, error_response = parse_similarity_threshold()
    if error_response:
        return error_response

    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({'error': 'Invalid JSON payload'}), 400

    flashcards = payload if isinstance(payload, list) else payload.get('flashcards')
    if not flashcards:
        return jsonify({'error': 'No flashcards provided'}), 400

    client = supabase_client.get_db()

    results = {
        'accepted': [],
        'duplicates': [],
        'errors': []
    }

    seen_questions = set()

    def normalize_keys(entry: dict) -> dict:
        """Return a new dict with standard keys derived from a variety of possible inputs."""
        key_map = {
            'question': 'question',
            'answer': 'answer',
            'module': 'module',
            'topic': 'topic',
            'subtopic': 'subtopic',
            'sub_topic': 'subtopic',
            'sub-topic': 'subtopic',
            'sub topic': 'subtopic',
            'tags': 'tags',
            'distractors': 'distractors',
            'user_id': 'user_id',
            'username': 'username'
        }

        normalised = {}

        for key, value in entry.items():
            key_sanitised = ''.join(ch for ch in key.lower() if ch.isalnum() or ch in {'_', ' '})
            if key_sanitised in key_map:
                normalised[key_map[key_sanitised]] = value
            else:
                # Attempt to match by removing spaces entirely
                key_compact = key_sanitised.replace(' ', '').replace('_', '')
                for candidate, canonical in key_map.items():
                    compare = candidate.replace('-', '').replace(' ', '').replace('_', '')
                    if key_compact == compare:
                        normalised[canonical] = value
                        break

        return normalised

    for index, raw_flashcard in enumerate(flashcards):
        try:
            if not isinstance(raw_flashcard, dict):
                raise ValueError('Each flashcard must be an object')

            flashcard = normalize_keys(raw_flashcard)

            question = (flashcard.get('question') or '').strip()
            answer = (flashcard.get('answer') or '').strip()
            module = (flashcard.get('module') or '').strip()
            topic = (flashcard.get('topic') or '').strip()
            subtopic = (flashcard.get('subtopic') or '').strip()
            tags_field = flashcard.get('tags') or []

            if not question or not answer or not module:
                raise ValueError('question, answer, and module are required fields')

            # Normalise tags into a comma-separated string
            if isinstance(tags_field, str):
                tags_list = [t.strip() for t in tags_field.split(',') if t.strip()]
            else:
                tags_list = [str(t).strip() for t in tags_field if str(t).strip()]

            tags_csv = ', '.join(tags_list)

            duplicate_matches = []

            seen_key = (module.lower(), question.lower())

            # Skip duplicate detection if we've already processed this question in the same batch
            if seen_key in seen_questions:
                duplicate_matches.append({'reason': 'duplicate-in-batch'})
            else:
                module_result = None
                if module:
                    module_result = client.table('modules').select('id').eq('name', module).execute()

                if module_result and module_result.data:
                    module_id = module_result.data[0]['id']
                    semantic_matches = find_semantic_duplicates(question, module_id, threshold=similarity_threshold)
                    for match in semantic_matches:
                        duplicate_matches.append({
                            'reason': 'semantic-match',
                            'id': match.get('id'),
                            'question': match.get('question'),
                            'answer': match.get('answer'),
                            'similarity': match.get('similarity')
                        })

                if not duplicate_matches:
                    # Check for exact duplicates already pending review
                    pending = client.table('submitted_flashcards').select('id').eq('submitted_question', question).eq('module', module).execute()
                    if pending.data:
                        for row in pending.data:
                            duplicate_matches.append({
                                'reason': 'duplicate-in-submissions',
                                'id': row['id']
                            })

            if duplicate_matches:
                results['duplicates'].append({
                    'index': index,
                    'question': question,
                    'module': module,
                    'matches': duplicate_matches
                })
                continue

            insert_payload = {
                'user_id': flashcard.get('user_id', Config.N8N_DEFAULT_USER_ID),
                'username': flashcard.get('username', Config.N8N_DEFAULT_USERNAME),
                'submitted_question': question,
                'submitted_answer': answer,
                'module': module,
                'submitted_topic': topic or None,
                'submitted_subtopic': subtopic or None,
                'submitted_tags_comma_separated': tags_csv if tags_csv else None
            }

            insert_result = client.table('submitted_flashcards').insert(insert_payload).execute()

            submission_id = None
            if insert_result and insert_result.data:
                submission_id = insert_result.data[0].get('id')

            # Optional distractor ingestion if provided
            distractors = flashcard.get('distractors') or []
            if distractors and isinstance(distractors, list):
                if submission_id:
                    for distractor in distractors[:Config.NUMBER_OF_DISTRACTORS]:
                        text = (str(distractor) or '').strip()
                        if not text:
                            continue
                        client.table('submitted_distractors').insert({
                            'user_id': insert_payload['user_id'],
                            'username': insert_payload['username'],
                            'question_id': f"flashcard_{submission_id}",
                            'distractor_text': text
                        }).execute()

            seen_questions.add(seen_key)

            results['accepted'].append({
                'index': index,
                'question': question,
                'module': module
            })

        except Exception as exc:
            results['errors'].append({
                'index': index,
                'error': str(exc)
            })

    status_code = 207 if results['errors'] or results['duplicates'] else 201
    return jsonify(results), status_code

@api_bp.route('/api/leaderboard', methods=['GET'])
def api_leaderboard():
    """API endpoint for real-time leaderboard updates."""
    from app import discord
    from models.user import get_leaderboard
    
    if not discord.authorized:
        return jsonify({'error': 'Unauthorized'}), 401
    
    sort = request.args.get('sort', 'correct_answers')
    order = request.args.get('order', 'desc')
    module_filter = request.args.get('module', None)
    
    leaderboard = get_leaderboard(sort, order, module_filter)
    return jsonify({'leaderboard': leaderboard})


@api_bp.route('/api/approve_flashcard', methods=['POST'])
def approve_flashcard():
    """
    API endpoint to approve a flashcard submission.
    Supports API token authentication for n8n workflows.
    """
    # Check for API token authentication first
    token = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.lower().startswith('bearer '):
        token = auth_header.split(' ', 1)[1]
    else:
        token = request.headers.get('X-API-Key')

    # If token is provided, verify it; otherwise fall back to Discord auth
    if token:
        if not verify_ingest_token(token):
            return jsonify({'error': 'Unauthorized'}), 401
    else:
        from app import discord
        if not discord.authorized:
            return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    # Required fields
    submission_id = data.get('submission_id')
    question = data.get('question', '').strip()
    answer = data.get('answer', '').strip()
    module = data.get('module', '').strip()

    # Optional fields
    topic = data.get('topic', '').strip() or None
    subtopic = data.get('subtopic', '').strip() or None
    tags = data.get('tags', [])

    if not all([submission_id, question, answer, module]):
        return jsonify({'error': 'submission_id, question, answer, and module are required'}), 400

    try:
        from models.question import get_module_id_by_name
        
        client = supabase_client.get_db()
        
        # Get module ID
        module_id = get_module_id_by_name(client, module)
        if not module_id:
            return jsonify({'error': 'Invalid module specified'}), 400

        # Prepare tags list
        tag_list = tags if isinstance(tags, list) else [t.strip() for t in str(tags).split(',') if t.strip()] if tags else []

        # Use comprehensive RPC function for entire approval process
        result = client.rpc('admin_approve_flashcard', {
            'submission_id_param': submission_id,
            'question_param': question,
            'answer_param': answer,
            'module_id_param': module_id,
            'topic_param': topic,
            'subtopic_param': subtopic,
            'tags_param': tag_list if tag_list else None
        }).execute()

        if result.data and result.data.get('success'):
            pending_count = result.data.get('pending_distractors_count', 0)
            return jsonify({
                'success': True,
                'message': 'Flashcard approved and added to the database.',
                'pending_distractors_count': pending_count
            }), 200
        else:
            error_msg = result.data.get('error', 'Unknown error occurred') if result.data else 'RPC call failed'
            return jsonify({'error': f'Error approving flashcard: {error_msg}'}), 500

    except Exception as e:
        return jsonify({'error': f'Error approving flashcard: {str(e)}'}), 500


@api_bp.route('/api/reject_flashcard', methods=['POST'])
def reject_flashcard():
    """
    API endpoint to reject a flashcard submission.
    Supports API token authentication for n8n workflows.
    """
    # Check for API token authentication first
    token = None
    auth_header = request.headers.get('Authorization', '')
    if auth_header.lower().startswith('bearer '):
        token = auth_header.split(' ', 1)[1]
    else:
        token = request.headers.get('X-API-Key')

    # If token is provided, verify it; otherwise fall back to Discord auth
    if token:
        if not verify_ingest_token(token):
            return jsonify({'error': 'Unauthorized'}), 401
    else:
        from app import discord
        if not discord.authorized:
            return jsonify({'error': 'Unauthorized'}), 401

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No JSON data provided'}), 400

    submission_id = data.get('submission_id')
    if not submission_id:
        return jsonify({'error': 'submission_id is required'}), 400

    try:
        client = supabase_client.get_db()
        
        # Use RPC for atomic rejection operation
        result = client.rpc('admin_reject_flashcard', {
            'submission_id_param': submission_id
        }).execute()

        if result.data and result.data.get('success'):
            rejected_count = result.data.get('rejected_distractors_count', 0)
            return jsonify({
                'success': True,
                'message': 'Flashcard submission rejected and removed.',
                'rejected_distractors_count': rejected_count
            }), 200
        else:
            # Fallback to individual operations
            flashcard_distractor_key = f"flashcard_{submission_id}"
            rejected_distractors_result = client.table('submitted_distractors').select('id').eq('question_id', flashcard_distractor_key).execute()
            rejected_count = len(rejected_distractors_result.data) if rejected_distractors_result.data else 0
            
            client.table('submitted_flashcards').delete().eq('id', submission_id).execute()
            client.table('submitted_distractors').delete().eq('question_id', flashcard_distractor_key).execute()
            
            return jsonify({
                'success': True,
                'message': 'Flashcard submission rejected and removed.',
                'rejected_distractors_count': rejected_count
            }), 200

    except Exception as e:
        return jsonify({'error': f'Error rejecting flashcard: {str(e)}'}), 500
