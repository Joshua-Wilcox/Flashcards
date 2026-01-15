from models.supabase_adapter import supabase_client
import os

def get_comprehensive_question_metadata(question_ids):
    """
    Fetch all metadata (topics, subtopics, tags) for multiple questions in a single query.
    
    Args:
        question_ids: List of question IDs or single question ID (string or list)
        
    Returns:
        Dict mapping question_id -> {
            'topics': [list of topic names],
            'subtopics': [list of subtopic names], 
            'tags': [list of tag names]
        }
    """
    client = supabase_client.get_db()
    
    # Handle single question ID by converting to list
    if isinstance(question_ids, str):
        question_ids = [question_ids]
    
    if not question_ids:
        return {}
    
    try:
        # Use the optimized RPC function for bulk metadata fetching
        result = client.rpc('get_question_metadata_bulk', {
            'question_ids_param': question_ids
        }).execute()
        
        if result.data:
            # Process RPC function results
            metadata = {}
            for row in result.data:
                question_id = row['question_id']
                metadata[question_id] = {
                    'topics': sorted(row.get('topics', [])),
                    'subtopics': sorted(row.get('subtopics', [])),
                    'tags': sorted(row.get('tags', []))
                }
            
            # Ensure all requested question IDs have metadata (even if empty)
            for qid in question_ids:
                if qid not in metadata:
                    metadata[qid] = {'topics': [], 'subtopics': [], 'tags': []}
            
            return metadata
        else:
            # If RPC function doesn't exist or returns no data, use fallback method
            return _get_metadata_fallback(question_ids, client)
        
    except Exception as e:
        print(f"Error with RPC function, using fallback method: {e}")
        return _get_metadata_fallback(question_ids, client)

def _get_metadata_fallback(question_ids, client):
    """
    Fallback method for metadata fetching using Supabase nested queries.
    Used when RPC function is not available. Implements batching to avoid URI too long errors.
    """
    try:
        # Implement batching to avoid URI too long errors
        BATCH_SIZE = 50  # Supabase can handle ~50 IDs in a single query safely
        all_metadata = {}
        
        # Process question IDs in batches
        for i in range(0, len(question_ids), BATCH_SIZE):
            batch_ids = question_ids[i:i + BATCH_SIZE]
            
            # Use nested query approach for this batch
            query_result = client.table('questions').select('''
                id,
                question_topics!left(topics!inner(name)),
                question_subtopics!left(subtopics!inner(name)),
                question_tags!left(tags!inner(name))
            ''').in_('id', batch_ids).execute()
            
            # Process the nested results for this batch
            for question in query_result.data:
                question_id = question['id']
                all_metadata[question_id] = {
                    'topics': sorted(list(set([rel['topics']['name'] for rel in question['question_topics'] if rel.get('topics')]))),
                    'subtopics': sorted(list(set([rel['subtopics']['name'] for rel in question['question_subtopics'] if rel.get('subtopics')]))),
                    'tags': sorted(list(set([rel['tags']['name'] for rel in question['question_tags'] if rel.get('tags')])))
                }
        
        # Ensure all requested question IDs have metadata (even if empty)
        for qid in question_ids:
            if qid not in all_metadata:
                all_metadata[qid] = {'topics': [], 'subtopics': [], 'tags': []}
                
        return all_metadata
        
    except Exception as e:
        print(f"Error in fallback metadata fetch: {e}")
        # Return empty metadata for all questions to prevent crashes
        return {qid: {'topics': [], 'subtopics': [], 'tags': []} for qid in question_ids}


def get_pdfs_for_question(question_id, max_pdfs=3):
    """
    Find relevant PDFs for a question using the new storage bucket system.
    Uses the optimized RPC function for better performance.
    
    Returns a maximum of max_pdfs PDFs with match percentages.
    """
    try:
        # Try to use the PDF storage service first
        from services.pdf_storage import PDFStorageService
        pdf_service = PDFStorageService()
        pdfs = pdf_service.get_pdfs_for_question(question_id, max_pdfs)
        
        if pdfs:
            # Convert to the expected format for backward compatibility
            formatted_pdfs = []
            for pdf in pdfs:
                formatted_pdf = {
                    'path': pdf.get('url', ''),  # Use application PDF serving route
                    'name': pdf.get('original_filename', pdf.get('name', '')),
                    'module': pdf.get('module_name', ''),
                    'topic': pdf.get('topic_name', ''),
                    'subtopic': pdf.get('subtopic_name', ''),
                    'tags': pdf.get('tags', []),
                    'match_percent': float(pdf.get('match_percent', 0)),
                    'match_reasons': pdf.get('match_reasons', [])
                }
                formatted_pdfs.append(formatted_pdf)
            
            return formatted_pdfs
        
        # Fallback to legacy system if no PDFs found in new system
        return get_pdfs_from_filesystem_legacy(question_id, max_pdfs)
        
    except ImportError:
        # If PDF storage service is not available, fallback to legacy
        return get_pdfs_from_filesystem_legacy(question_id, max_pdfs)
    except Exception as e:
        print(f"Error in get_pdfs_for_question: {e}")
        # Fallback to legacy system on any error
        return get_pdfs_from_filesystem_legacy(question_id, max_pdfs)
def get_pdfs_from_filesystem_legacy(question_id, max_pdfs=3):
    """
    Legacy fallback method to find PDFs from filesystem.
    """
    # Get question metadata first
    question_metadata = get_comprehensive_question_metadata([question_id])
    current_metadata = question_metadata.get(question_id, {'topics': [], 'subtopics': [], 'tags': []})
    question_topics = current_metadata['topics']
    question_subtopics = current_metadata['subtopics']
    question_tags = current_metadata['tags']
    
    return get_pdfs_from_filesystem(question_id, question_topics, question_subtopics, question_tags, max_pdfs)


def get_pdfs_from_filesystem(question_id, question_topics, question_subtopics, question_tags, max_pdfs=3):
    """
    Fallback method to find PDFs from filesystem when database is not populated.
    Searches the static/pdfs directory structure and matches based on folder names.
    """
    base_path = os.path.abspath('static/pdfs')
    if not os.path.exists(base_path):
        return []
    
    # Get question's module
    client = supabase_client.get_db()
    question_result = client.table('questions').select('''
        module_id,
        modules!inner(name)
    ''').eq('id', question_id).execute()
    
    if not question_result.data:
        return []
    
    module_name = question_result.data[0]['modules']['name']
    
    scored_pdfs = []
    
    # Walk through the PDF directory
    for root, _, files in os.walk(base_path):
        for file in files:
            if file.lower().endswith('.pdf'):
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, base_path)
                
                # Get path components for matching
                path_parts = relative_path.replace('\\', '/').split('/')
                path_parts_lower = [part.lower() for part in path_parts]
                
                match_score = 0
                match_reasons = []
                
                # Check for module match in path
                module_match = False
                for part in path_parts_lower:
                    if module_name.lower() in part or part in module_name.lower():
                        module_match = True
                        break
                
                if module_match:
                    match_score = 40  # Base module match
                    match_reasons.append("Module in path")
                
                # Check for topic matches
                topic_matches = 0
                for topic in question_topics:
                    topic_lower = topic.lower()
                    for part in path_parts_lower:
                        if topic_lower in part or part in topic_lower:
                            topic_matches += 1
                            break
                
                if topic_matches > 0:
                    topic_bonus = min(30, topic_matches * 15)
                    match_score += topic_bonus
                    match_reasons.append(f"Topic match ({topic_matches})")
                
                # Check for subtopic matches
                subtopic_matches = 0
                for subtopic in question_subtopics:
                    subtopic_lower = subtopic.lower()
                    for part in path_parts_lower:
                        if subtopic_lower in part or part in subtopic_lower:
                            subtopic_matches += 1
                            break
                
                if subtopic_matches > 0:
                    subtopic_bonus = min(20, subtopic_matches * 10)
                    match_score += subtopic_bonus
                    match_reasons.append(f"Subtopic match ({subtopic_matches})")
                
                # Check for tag matches
                tag_matches = 0
                for tag in question_tags:
                    tag_lower = tag.lower()
                    for part in path_parts_lower:
                        if tag_lower in part or part in tag_lower:
                            tag_matches += 1
                            break
                
                if tag_matches > 0:
                    tag_bonus = min(15, tag_matches * 5)
                    match_score += tag_bonus
                    match_reasons.append(f"Tag match ({tag_matches})")
                
                # Only include files with some relevance
                if match_score >= 20:  # Minimum threshold
                    pdf_info = {
                        'path': relative_path.replace('\\', '/'),
                        'name': file,
                        'module': module_name if module_match else '',
                        'topic': ', '.join([t for t in question_topics if any(t.lower() in part for part in path_parts_lower)]),
                        'subtopic': ', '.join([st for st in question_subtopics if any(st.lower() in part for part in path_parts_lower)]),
                        'tags': [tag for tag in question_tags if any(tag.lower() in part for part in path_parts_lower)],
                        'match_percent': min(95, round(match_score, 1)),
                        'match_reasons': match_reasons
                    }
                    scored_pdfs.append(pdf_info)
    
    # Sort by match score and return top results
    scored_pdfs.sort(key=lambda x: x['match_percent'], reverse=True)
    return scored_pdfs[:max_pdfs]


def add_tags_and_link_question(tags, question_id):
    """Add tags to the database and link them to a question"""
    client = supabase_client.get_db()
    
    for tag_name in tags:
        if tag_name and tag_name.strip():
            tag_name = tag_name.strip()
            try:
                # Check if tag already exists
                existing_tag = client.table('tags').select('id').eq('name', tag_name).execute()
                
                if existing_tag.data:
                    # Tag exists, use its ID
                    tag_id = existing_tag.data[0]['id']
                else:
                    # Create new tag
                    new_tag = client.table('tags').insert({'name': tag_name}).execute()
                    tag_id = new_tag.data[0]['id']
                
                # Link tag to question (avoid duplicates)
                existing_link = client.table('question_tags').select('id').eq('question_id', question_id).eq('tag_id', tag_id).execute()
                if not existing_link.data:
                    client.table('question_tags').insert({
                        'question_id': question_id,
                        'tag_id': tag_id
                    }).execute()
                    
            except Exception as e:
                print(f"Error processing tag '{tag_name}': {e}")
                continue

def add_topic_and_link_question(question_id, topic_name):
    """Add topic and link it to a question."""
    client = supabase_client.get_db()
    
    topic_name = topic_name.strip()
    if not topic_name:
        return
        
    try:
        # Check if topic already exists
        existing_topic = client.table('topics').select('id').eq('name', topic_name).execute()
        
        if existing_topic.data:
            # Topic exists, use existing ID
            topic_id = existing_topic.data[0]['id']
            print(f"Using existing topic '{topic_name}' with ID {topic_id}")
        else:
            # Topic doesn't exist, create new one
            print(f"Creating new topic: '{topic_name}'")
            new_topic = client.table('topics').insert({'name': topic_name}).execute()
            topic_id = new_topic.data[0]['id']
            print(f"Created topic '{topic_name}' with ID {topic_id}")
        
        # Link topic to question (ignore if already exists)
        client.table('question_topics').upsert({
            'question_id': question_id,
            'topic_id': topic_id
        }).execute()
        print(f"Linked topic '{topic_name}' to question {question_id[:8]}...")
        
    except Exception as e:
        print(f"ERROR in add_topic_and_link_question: {e}")
        print(f"Failed to add topic '{topic_name}' to question {question_id[:8]}...")
        raise

def add_subtopic_and_link_question(question_id, subtopic_name):
    """Add subtopic and link it to a question."""
    client = supabase_client.get_db()
    
    subtopic_name = subtopic_name.strip()
    if not subtopic_name:
        return
        
    try:
        # Check if subtopic already exists
        existing_subtopic = client.table('subtopics').select('id').eq('name', subtopic_name).execute()
        
        if existing_subtopic.data:
            # Subtopic exists, use existing ID
            subtopic_id = existing_subtopic.data[0]['id']
            print(f"Using existing subtopic '{subtopic_name}' with ID {subtopic_id}")
        else:
            # Subtopic doesn't exist, create new one
            print(f"Creating new subtopic: '{subtopic_name}'")
            new_subtopic = client.table('subtopics').insert({'name': subtopic_name}).execute()
            subtopic_id = new_subtopic.data[0]['id']
            print(f"Created subtopic '{subtopic_name}' with ID {subtopic_id}")
        
        # Link subtopic to question (ignore if already exists)
        client.table('question_subtopics').upsert({
            'question_id': question_id,
            'subtopic_id': subtopic_id
        }).execute()
        print(f"Linked subtopic '{subtopic_name}' to question {question_id[:8]}...")
        
    except Exception as e:
        print(f"ERROR in add_subtopic_and_link_question: {e}")
        print(f"Failed to add subtopic '{subtopic_name}' to question {question_id[:8]}...")
        raise

def find_semantic_duplicates(question_text, module_id, limit=5, threshold=0.3):
    """
    Enhanced semantic duplicate detection using TF-IDF and cosine similarity
    to better understand the meaning behind questions.
    
    Args:
        question_text: The question to check for duplicates
        module_id: The module to search within
        limit: Maximum number of duplicates to return
        threshold: Minimum similarity score to consider a match
    
    Returns:
        List of potential duplicate questions with similarity scores
    """
    from collections import Counter
    import math
    
    client = supabase_client.get_db()
    
    # Step 1: Get all questions in the same module
    result = client.table('questions').select('id, question, answer').eq('module_id', module_id).execute()
    
    if not result.data:
        return []
    
    # Create a list of all documents (questions) to process
    docs = [row['question'] for row in result.data]
    
    # Add the input question to the end
    docs.append(question_text)
    
    # Step 2: Preprocess all documents
    processed_docs = []
    stop_words = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'about', 
                 'as', 'of', 'and', 'or', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 
                 'have', 'has', 'had', 'do', 'does', 'did', 'what', 'when', 'where', 'why', 
                 'how', 'which', 'who', 'whom', 'this', 'that', 'these', 'those'}
    
    for doc in docs:
        # Convert to lowercase
        doc_lower = doc.lower()
        
        # Remove punctuation
        for char in '.,?!;:()[]{}""\'':
            doc_lower = doc_lower.replace(char, ' ')
        
        # Tokenize and remove stop words and short words
        tokens = [word for word in doc_lower.split() if word not in stop_words and len(word) > 2]
        
        # Stem words (simple implementation - just take first 6 chars)
        # This isn't as good as a real stemmer but helps with basic word forms
        stemmed = [word[:6] for word in tokens if len(word) > 3]
        
        processed_docs.append(stemmed)
    
    # Step 3: Calculate TF-IDF vectors
    # First, get document frequency for each term
    term_doc_freq = Counter()
    all_terms = set()
    
    for doc in processed_docs:
        terms = set(doc)  # Unique terms in this document
        for term in terms:
            term_doc_freq[term] += 1
            all_terms.add(term)
    
    num_docs = len(processed_docs)
    
    # Calculate IDF for each term
    idf = {term: math.log(num_docs / (1 + term_doc_freq[term])) for term in all_terms}
    
    # Calculate TF-IDF vector for each document
    tfidf_vectors = []
    
    for doc in processed_docs:
        # Calculate term frequency in this document
        tf = Counter(doc)
        # Normalize by document length
        doc_len = len(doc) or 1  # Avoid division by zero
        
        # Calculate TF-IDF for each term
        doc_vector = {term: (tf[term] / doc_len) * idf.get(term, 0) for term in all_terms}
        tfidf_vectors.append(doc_vector)
    
    # Step 4: Calculate cosine similarity between the input question and all others
    input_vector = tfidf_vectors[-1]  # The last one is our input question
    input_magnitude = math.sqrt(sum(val**2 for val in input_vector.values()))
    
    similarities = []
    
    for i, doc_vector in enumerate(tfidf_vectors[:-1]):  # Skip the last one (input question)
        # Calculate dot product
        dot_product = sum(input_vector.get(term, 0) * doc_vector.get(term, 0) for term in all_terms)
        
        # Calculate magnitude of document vector
        doc_magnitude = math.sqrt(sum(val**2 for val in doc_vector.values()))
        
        # Calculate cosine similarity
        similarity = 0
        if input_magnitude > 0 and doc_magnitude > 0:  # Avoid division by zero
            similarity = dot_product / (input_magnitude * doc_magnitude)
        
        similarities.append((i, similarity))
    
    # Step 5: Return the top matches above the threshold
    top_matches = sorted(similarities, key=lambda x: x[1], reverse=True)[:limit]
    
    results = []
    for idx, score in top_matches:
        if score >= threshold:  # Only include matches above the threshold
            row = result.data[idx]
            results.append({
                'id': row['id'],
                'question': row['question'],
                'answer': row['answer'],
                'similarity': score
            })
    
    return results


def get_text_similarity(text1, text2):
    """Calculate text similarity between two strings."""
    import difflib
    return difflib.SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

def get_all_modules():
    """Get all modules from the database."""
    client = supabase_client.get_db()
    result = (client
              .table('modules')
              .select('id, name, year')
              .order('year', nullsfirst=False)
              .order('name')
              .execute())

    if not result.data:
        return []

    return [{
        'id': row['id'],
        'name': row['name'],
        'year': row.get('year')
    } for row in result.data]


def get_module_id_by_name(client, module_name, year=None):
    """Get module ID by name, creating if it doesn't exist."""
    result = client.table('modules').select('id').eq('name', module_name).execute()
    if result.data:
        return result.data[0]['id']
    
    # Insert new module
    insert_payload = {'name': module_name}
    if year is not None:
        insert_payload['year'] = year

    insert_result = client.table('modules').insert(insert_payload).execute()
    return insert_result.data[0]['id'] if insert_result.data else None

def get_module_name_by_id(module_id):
    """Get module name by ID."""
    client = supabase_client.get_db()
    result = client.table('modules').select('name').eq('id', module_id).execute()
    return result.data[0]['name'] if result.data else None

