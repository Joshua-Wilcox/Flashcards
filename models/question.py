from models.database import get_db
import json
import os

def get_tags_for_question(question_id):
    """Get tags associated with a question."""
    db = get_db()
    rows = db.execute('''
        SELECT t.name FROM tags t
        JOIN question_tags qt ON t.id = qt.tag_id
        WHERE qt.question_id = ?
    ''', (question_id,)).fetchall()
    return [row['name'] for row in rows]

def get_topics_for_question(question_id):
    """Get topics associated with a question."""
    db = get_db()
    rows = db.execute('''
        SELECT tp.name FROM topics tp
        JOIN question_topics qt ON tp.id = qt.topic_id
        WHERE qt.question_id = ?
    ''', (question_id,)).fetchall()
    return [row['name'] for row in rows]

def get_subtopics_for_question(question_id):
    """Get subtopics associated with a question."""
    db = get_db()
    rows = db.execute('''
        SELECT st.name FROM subtopics st
        JOIN question_subtopics qs ON st.id = qs.subtopic_id
        WHERE qs.question_id = ?
    ''', (question_id,)).fetchall()
    return [row['name'] for row in rows]

def get_pdfs_for_tags(tag_names):
    """Get PDFs for given tag names."""
    if not tag_names:
        return []
    
    base_path = os.path.abspath('static/pdfs')
    matched_pdfs = []
    
    for root, dirs, files in os.walk(base_path):
        for file in files:
            if file.lower().endswith('.pdf'):
                relative_path = os.path.relpath(os.path.join(root, file), base_path)
                path_parts = relative_path.lower().split(os.sep)
                
                for tag in tag_names:
                    tag_lower = tag.lower()
                    if any(tag_lower in part for part in path_parts):
                        matched_pdfs.append(relative_path.replace(os.sep, '/'))
                        break
    
    return list(set(matched_pdfs))[:3]

def get_pdfs_for_question(question_id, max_pdfs=3):
    """
    Find relevant PDFs for a question, prioritizing by:
    1. Module + Topic + Subtopic match (95%)
    2. Module + Topic match (80%)
    3. Module match (60%)
    4. Tag matches (20-50% based on tag overlap)
    Returns a maximum of max_pdfs PDFs with match percentages.
    """
    db = get_db()
    question = db.execute('SELECT module_id FROM questions WHERE id = ?', (question_id,)).fetchone()
    if not question:
        return []
    
    module_id = question['module_id']
    
    # Get topic and subtopic for the question
    topic_rows = db.execute('''
        SELECT topic_id FROM question_topics WHERE question_id = ?
    ''', (question_id,)).fetchall()
    topic_ids = [row['topic_id'] for row in topic_rows]
    
    subtopic_rows = db.execute('''
        SELECT subtopic_id FROM question_subtopics WHERE question_id = ?
    ''', (question_id,)).fetchall()
    subtopic_ids = [row['subtopic_id'] for row in subtopic_rows]
    
    results = []
    
    # Priority 1: Module + Topic + Subtopic match (100% match)
    if topic_ids and subtopic_ids:
        for topic_id in topic_ids:
            for subtopic_id in subtopic_ids:
                pdfs = db.execute('''
                    SELECT p.id, p.path, p.module_id, p.topic_id, p.subtopic_id, 
                           m.name as module_name, t.name as topic_name, s.name as subtopic_name
                    FROM pdfs p
                    LEFT JOIN modules m ON p.module_id = m.id
                    LEFT JOIN topics t ON p.topic_id = t.id
                    LEFT JOIN subtopics s ON p.subtopic_id = s.id
                    WHERE p.module_id = ? AND p.topic_id = ? AND p.subtopic_id = ?
                    LIMIT ?
                ''', (module_id, topic_id, subtopic_id, max_pdfs)).fetchall()
                
                for pdf in pdfs:
                    pdf_info = {
                        'path': pdf['path'],
                        'name': os.path.basename(pdf['path']),
                        'module': pdf['module_name'],
                        'topic': pdf['topic_name'],
                        'subtopic': pdf['subtopic_name'],
                        'match_percent': 100  # Exact module, topic, subtopic match
                    }
                    if pdf_info not in results:
                        results.append(pdf_info)
                        if len(results) >= max_pdfs:
                            return sorted(results, key=lambda x: x.get('match_percent', 0), reverse=True)
    
    # Priority 2: Module + Topic match (80% match)
    if topic_ids and len(results) < max_pdfs:
        for topic_id in topic_ids:
            pdfs = db.execute('''
                SELECT p.id, p.path, p.module_id, p.topic_id, p.subtopic_id,
                       m.name as module_name, t.name as topic_name, s.name as subtopic_name
                FROM pdfs p
                LEFT JOIN modules m ON p.module_id = m.id
                LEFT JOIN topics t ON p.topic_id = t.id
                LEFT JOIN subtopics s ON p.subtopic_id = s.id
                WHERE p.module_id = ? AND p.topic_id = ? AND p.subtopic_id IS NULL
                LIMIT ?
            ''', (module_id, topic_id, max_pdfs - len(results))).fetchall()
            
            for pdf in pdfs:
                pdf_info = {
                    'path': pdf['path'],
                    'name': os.path.basename(pdf['path']),
                    'module': pdf['module_name'],
                    'topic': pdf['topic_name'],
                    'subtopic': pdf['subtopic_name'],
                    'match_percent': 80  # Module and topic match
                }
                if not any(r['path'] == pdf_info['path'] for r in results):
                    results.append(pdf_info)
                    if len(results) >= max_pdfs:
                        return sorted(results, key=lambda x: x.get('match_percent', 0), reverse=True)
    
    # Priority 3: Module match (70% match)
    if len(results) < max_pdfs:
        pdfs = db.execute('''
            SELECT p.id, p.path, p.module_id, p.topic_id, p.subtopic_id,
                   m.name as module_name, t.name as topic_name, s.name as subtopic_name
            FROM pdfs p
            LEFT JOIN modules m ON p.module_id = m.id
            LEFT JOIN topics t ON p.topic_id = t.id
            LEFT JOIN subtopics s ON p.subtopic_id = s.id
            WHERE p.module_id = ? AND p.topic_id IS NULL
            LIMIT ?
        ''', (module_id, max_pdfs - len(results))).fetchall()
        
        for pdf in pdfs:
            pdf_info = {
                'path': pdf['path'],
                'name': os.path.basename(pdf['path']),
                'module': pdf['module_name'],
                'topic': pdf['topic_name'],
                'subtopic': pdf['subtopic_name'],
                'match_percent': 70  # Only module matches
            }
            if not any(r['path'] == pdf_info['path'] for r in results):
                results.append(pdf_info)
                if len(results) >= max_pdfs:
                    return sorted(results, key=lambda x: x.get('match_percent', 0), reverse=True)
    
    # Priority 4: Tag matches (20-50% match based on tag overlap)
    if len(results) < max_pdfs:
        tag_names = get_tags_for_question(question_id)
        
        if tag_names:
            # Get all PDFs with tag matches and their tag counts
            placeholders = ','.join('?' * len(tag_names))
            tag_pdfs = db.execute(f'''
                SELECT p.id, p.path, p.module_id, p.topic_id, p.subtopic_id,
                       m.name as module_name, t.name as topic_name, s.name as subtopic_name,
                       COUNT(pt.tag_id) as matching_tags,
                       (SELECT COUNT(*) FROM pdf_tags WHERE pdf_id = p.id) as total_pdf_tags
                FROM pdfs p
                JOIN pdf_tags pt ON p.id = pt.pdf_id
                JOIN tags tag ON pt.tag_id = tag.id
                LEFT JOIN modules m ON p.module_id = m.id
                LEFT JOIN topics t ON p.topic_id = t.id
                LEFT JOIN subtopics s ON p.subtopic_id = s.id
                WHERE tag.name IN ({placeholders})
                GROUP BY p.id
                ORDER BY matching_tags DESC
                LIMIT ?
            ''', tag_names + [max_pdfs - len(results)]).fetchall()
            
            # Get total number of question tags for calculating match percentage
            total_question_tags = len(tag_names)
            
            for pdf in tag_pdfs:
                # Calculate tag match percentage: 40% base + up to 30% based on tag overlap
                matching_tags = pdf['matching_tags']
                total_pdf_tags = max(pdf['total_pdf_tags'], 1) # Avoid division by zero
                
                # Calculate tag overlap ratio (matching tags / total tags across both)
                tag_overlap = matching_tags / (total_question_tags + total_pdf_tags - matching_tags)
                
                # Calculate match percentage: 40% base + up to 30% based on tag overlap
                match_percent = 40 + min(30, int(60 * tag_overlap))
                
                pdf_info = {
                    'path': pdf['path'],
                    'name': os.path.basename(pdf['path']),
                    'module': pdf['module_name'],
                    'topic': pdf['topic_name'],
                    'subtopic': pdf['subtopic_name'],
                    'match_percent': match_percent,  # Tag-based match
                    'matching_tags': matching_tags
                }
                
                if not any(r['path'] == pdf_info['path'] for r in results):
                    results.append(pdf_info)
                    if len(results) >= max_pdfs:
                        break
    
    # Sort by match percentage (highest first)
    return sorted(results, key=lambda x: x.get('match_percent', 0), reverse=True)


def add_tags_and_link_question(db, question_id, tag_names):
    """Add tags and link them to a question."""
    for tag in tag_names:
        tag = tag.strip()
        if tag:
            # Insert tag if it doesn't exist
            db.execute('INSERT OR IGNORE INTO tags (name) VALUES (?)', (tag,))
            # Get tag ID
            tag_row = db.execute('SELECT id FROM tags WHERE name = ?', (tag,)).fetchone()
            tag_id = tag_row['id']
            # Link tag to question
            db.execute('INSERT OR IGNORE INTO question_tags (question_id, tag_id) VALUES (?, ?)', 
                      (question_id, tag_id))

def add_topic_and_link_question(db, question_id, topic_name):
    """Add topic and link it to a question."""
    topic_name = topic_name.strip()
    if topic_name:
        # Insert topic if it doesn't exist
        db.execute('INSERT OR IGNORE INTO topics (name) VALUES (?)', (topic_name,))
        # Get topic ID
        topic_row = db.execute('SELECT id FROM topics WHERE name = ?', (topic_name,)).fetchone()
        topic_id = topic_row['id']
        # Link topic to question
        db.execute('INSERT OR IGNORE INTO question_topics (question_id, topic_id) VALUES (?, ?)', 
                  (question_id, topic_id))

def add_subtopic_and_link_question(db, question_id, subtopic_name):
    """Add subtopic and link it to a question."""
    subtopic_name = subtopic_name.strip()
    if subtopic_name:
        # Insert subtopic if it doesn't exist
        db.execute('INSERT OR IGNORE INTO subtopics (name) VALUES (?)', (subtopic_name,))
        # Get subtopic ID
        subtopic_row = db.execute('SELECT id FROM subtopics WHERE name = ?', (subtopic_name,)).fetchone()
        subtopic_id = subtopic_row['id']
        # Link subtopic to question
        db.execute('INSERT OR IGNORE INTO question_subtopics (question_id, subtopic_id) VALUES (?, ?)', 
                  (question_id, subtopic_id))

def find_semantic_duplicates(db, question_text, module_id, limit=5, threshold=0.3):
    """
    Enhanced semantic duplicate detection using TF-IDF and cosine similarity
    to better understand the meaning behind questions.
    
    Args:
        db: Database connection
        question_text: The question to check for duplicates
        module_id: The module to search within
        limit: Maximum number of duplicates to return
        threshold: Minimum similarity score to consider a match
    
    Returns:
        List of potential duplicate questions with similarity scores
    """
    from collections import Counter
    import math
    
    # Step 1: Get all questions in the same module
    rows = db.execute('''
        SELECT id, question, answer
        FROM questions
        WHERE module_id = ?
    ''', (module_id,)).fetchall()
    
    if not rows:
        return []
    
    # Create a list of all documents (questions) to process
    docs = [row['question'] for row in rows]
    
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
            row = rows[idx]
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
    db = get_db()
    rows = db.execute('SELECT id, name FROM modules ORDER BY name').fetchall()
    return [{'id': row['id'], 'name': row['name']} for row in rows]

def get_module_id_by_name(db, module_name):
    """Get module ID by name, creating if it doesn't exist."""
    row = db.execute('SELECT id FROM modules WHERE name = ?', (module_name,)).fetchone()
    if row:
        return row['id']
    db.execute('INSERT INTO modules (name) VALUES (?)', (module_name,))
    return db.execute('SELECT id FROM modules WHERE name = ?', (module_name,)).fetchone()['id']

def get_module_name_by_id(db, module_id):
    """Get module name by ID."""
    row = db.execute('SELECT name FROM modules WHERE id = ?', (module_id,)).fetchone()
    return row['name'] if row else None
