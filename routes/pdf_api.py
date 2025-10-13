"""
PDF API routes for backend PDF management
Provides endpoints for uploading, managing, and retrieving PDFs
"""

from flask import Blueprint, request, jsonify
from werkzeug.datastructures import FileStorage
from services.pdf_storage import PDFStorageService
from models.supabase_adapter import supabase_client
from utils.security import verify_ingest_token

pdf_api_bp = Blueprint('pdf_api', __name__, url_prefix='/api/pdfs')

def api_token_required(f):
    """Decorator for API routes that require n8n ingest token authentication"""
    def decorated_function(*args, **kwargs):
        # Check for API token authentication
        token = None
        auth_header = request.headers.get('Authorization', '')
        if auth_header.lower().startswith('bearer '):
            token = auth_header.split(' ', 1)[1]
        else:
            token = request.headers.get('X-API-Key')
        
        if not verify_ingest_token(token):
            return jsonify({'error': 'Invalid or missing API token'}), 401
        
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function


@pdf_api_bp.route('/upload', methods=['POST'])
@api_token_required
def upload_pdf():
    """Upload a new PDF file with metadata"""
    try:
        # Check if file is in request
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        # Get form data - support both names and IDs for backward compatibility
        module_name = request.form.get('module_name', '').strip()
        module_id = request.form.get('module_id', type=int)
        
        topic_names_str = request.form.get('topic_names', '')
        topic_name = request.form.get('topic_name', '').strip()
        topic_id = request.form.get('topic_id', type=int) if request.form.get('topic_id') else None
        
        subtopic_names_str = request.form.get('subtopic_names', '')
        subtopic_name = request.form.get('subtopic_name', '').strip()
        subtopic_id = request.form.get('subtopic_id', type=int) if request.form.get('subtopic_id') else None
        
        tag_names_str = request.form.get('tag_names', '')
        tag_ids_str = request.form.get('tag_ids', '')
        
        # Parse multiple names from comma-separated strings
        topic_names = []
        if topic_names_str:
            topic_names = [name.strip() for name in topic_names_str.split(',') if name.strip()]
        elif topic_name:
            topic_names = [topic_name]
            
        subtopic_names = []
        if subtopic_names_str:
            subtopic_names = [name.strip() for name in subtopic_names_str.split(',') if name.strip()]
        elif subtopic_name:
            subtopic_names = [subtopic_name]
            
        tag_names = []
        if tag_names_str:
            tag_names = [name.strip() for name in tag_names_str.split(',') if name.strip()]
        
        # Legacy support for ID-based parameters
        tag_ids = []
        if tag_ids_str:
            try:
                tag_ids = [int(x.strip()) for x in tag_ids_str.split(',') if x.strip().isdigit()]
            except ValueError:
                return jsonify({'error': 'Invalid tag IDs format'}), 400
        
        # Validate required fields
        if not module_name and not module_id:
            return jsonify({'error': 'Module name or module ID is required'}), 400
        
        # Additional metadata
        metadata = {
            'uploaded_via': 'n8n_api',
            'user_agent': request.headers.get('User-Agent', ''),
        }
        
        # Use PDF storage service
        pdf_service = PDFStorageService()
        
        # Use name-based upload if names are provided, otherwise use legacy ID-based
        if module_name or topic_names or subtopic_names or tag_names:
            result = pdf_service.upload_pdf_by_names(
                file=file,
                filename=file.filename,
                module_name=module_name,
                topic_names=topic_names,
                subtopic_names=subtopic_names,
                tag_names=tag_names,
                uploaded_by='n8n_workflow',
                metadata=metadata
            )
        else:
            # Convert single IDs to lists for backward compatibility
            topic_ids_list = [topic_id] if topic_id else None
            subtopic_ids_list = [subtopic_id] if subtopic_id else None
            
            result = pdf_service.upload_pdf(
                file=file,
                filename=file.filename,
                module_id=module_id,
                topic_ids=topic_ids_list,
                subtopic_ids=subtopic_ids_list,
                tag_ids=tag_ids,
                uploaded_by='n8n_workflow',
                metadata=metadata
            )
        
        if result['success']:
            return jsonify({
                'success': True,
                'message': 'PDF uploaded successfully',
                'pdf_id': result['pdf_id'],
                'filename': result['filename']
            }), 201
        else:
            return jsonify({'error': result['error']}), 400
            
    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500


@pdf_api_bp.route('/batch-upload', methods=['POST'])
@api_token_required
def batch_upload_pdfs():
    """Upload multiple PDF files with shared metadata"""
    try:
        files = request.files.getlist('files')
        if not files or all(f.filename == '' for f in files):
            return jsonify({'error': 'No files provided'}), 400
        
        # Get shared metadata - support both names and IDs
        module_name = request.form.get('module_name', '').strip()
        module_id = request.form.get('module_id', type=int)
        
        topic_names_str = request.form.get('topic_names', '')
        topic_name = request.form.get('topic_name', '').strip()
        topic_id = request.form.get('topic_id', type=int) if request.form.get('topic_id') else None
        
        subtopic_names_str = request.form.get('subtopic_names', '')
        subtopic_name = request.form.get('subtopic_name', '').strip()
        subtopic_id = request.form.get('subtopic_id', type=int) if request.form.get('subtopic_id') else None
        
        tag_names_str = request.form.get('tag_names', '')
        tag_ids_str = request.form.get('tag_ids', '')
        
        # Parse multiple names from comma-separated strings
        topic_names = []
        if topic_names_str:
            topic_names = [name.strip() for name in topic_names_str.split(',') if name.strip()]
        elif topic_name:
            topic_names = [topic_name]
            
        subtopic_names = []
        if subtopic_names_str:
            subtopic_names = [name.strip() for name in subtopic_names_str.split(',') if name.strip()]
        elif subtopic_name:
            subtopic_names = [subtopic_name]
            
        tag_names = []
        if tag_names_str:
            tag_names = [name.strip() for name in tag_names_str.split(',') if name.strip()]
        
        # Legacy support for ID-based parameters
        tag_ids = []
        if tag_ids_str:
            try:
                tag_ids = [int(x.strip()) for x in tag_ids_str.split(',') if x.strip().isdigit()]
            except ValueError:
                return jsonify({'error': 'Invalid tag IDs format'}), 400
        
        if not module_name and not module_id:
            return jsonify({'error': 'Module name or module ID is required'}), 400
        
        pdf_service = PDFStorageService()
        results = []
        
        for file in files:
            if file.filename == '':
                continue
                
            metadata = {
                'uploaded_via': 'n8n_batch_api',
                'batch_upload': True,
                'user_agent': request.headers.get('User-Agent', ''),
            }
            
            # Use name-based or ID-based upload
            if module_name or topic_names or subtopic_names or tag_names:
                result = pdf_service.upload_pdf_by_names(
                    file=file,
                    filename=file.filename,
                    module_name=module_name,
                    topic_names=topic_names,
                    subtopic_names=subtopic_names,
                    tag_names=tag_names,
                    uploaded_by='n8n_workflow',
                    metadata=metadata
                )
            else:
                # Convert single IDs to lists for backward compatibility
                topic_ids_list = [topic_id] if topic_id else None
                subtopic_ids_list = [subtopic_id] if subtopic_id else None
                
                result = pdf_service.upload_pdf(
                    file=file,
                    filename=file.filename,
                    module_id=module_id,
                    topic_ids=topic_ids_list,
                    subtopic_ids=subtopic_ids_list,
                    tag_ids=tag_ids,
                    uploaded_by='n8n_workflow',
                    metadata=metadata
                )
            
            results.append({
                'filename': file.filename,
                'success': result['success'],
                'pdf_id': result.get('pdf_id'),
                'error': result.get('error')
            })
        
        successful_uploads = sum(1 for r in results if r['success'])
        
        return jsonify({
            'success': True,
            'message': f'Batch upload completed: {successful_uploads}/{len(results)} files uploaded',
            'results': results
        }), 201 if successful_uploads > 0 else 400
        
    except Exception as e:
        return jsonify({'error': f'Batch upload failed: {str(e)}'}), 500


@pdf_api_bp.route('/<int:pdf_id>', methods=['GET'])
@api_token_required
def get_pdf_info(pdf_id):
    """Get detailed information about a specific PDF"""
    try:
        client = supabase_client.get_db()
        
        result = client.table('pdfs').select("""
            id, storage_path, original_filename, file_size, mime_type, 
            uploaded_by, metadata, is_active, created_at,
            modules!inner(id, name),
            pdf_topics!left(topics!inner(id, name)),
            pdf_subtopics!left(subtopics!inner(id, name)),
            pdf_tags!left(tags!inner(id, name))
        """).eq('id', pdf_id).execute()
        
        if not result.data:
            return jsonify({'error': 'PDF not found'}), 404
        
        pdf_data = result.data[0]
        
        # Format response
        response = {
            'id': pdf_data['id'],
            'filename': pdf_data['original_filename'],
            'file_size': pdf_data['file_size'],
            'mime_type': pdf_data['mime_type'],
            'uploaded_by': pdf_data['uploaded_by'],
            'metadata': pdf_data['metadata'],
            'is_active': pdf_data['is_active'],
            'created_at': pdf_data['created_at'],
            'module': pdf_data['modules'],
            'topics': [topic_rel['topics'] for topic_rel in pdf_data.get('pdf_topics', [])],
            'subtopics': [subtopic_rel['subtopics'] for subtopic_rel in pdf_data.get('pdf_subtopics', [])],
            'tags': [tag_rel['tags'] for tag_rel in pdf_data.get('pdf_tags', [])]
        }
        
        # Add application PDF serving URL for download
        response['download_url'] = f"/pdf/{pdf_id}"
        
        return jsonify(response)
        
    except Exception as e:
        return jsonify({'error': f'Failed to get PDF info: {str(e)}'}), 500


@pdf_api_bp.route('/<int:pdf_id>', methods=['PUT'])
@api_token_required
def update_pdf_metadata(pdf_id):
    """Update PDF metadata and associations"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        pdf_service = PDFStorageService()
        result = pdf_service.update_pdf_metadata(
            pdf_id=pdf_id,
            module_id=data.get('module_id'),
            topic_ids=data.get('topic_ids'),
            subtopic_ids=data.get('subtopic_ids'),
            tag_ids=data.get('tag_ids'),
            metadata=data.get('metadata')
        )
        
        if result['success']:
            return jsonify({'message': result['message']})
        else:
            return jsonify({'error': result['error']}), 400
            
    except Exception as e:
        return jsonify({'error': f'Update failed: {str(e)}'}), 500


@pdf_api_bp.route('/<int:pdf_id>', methods=['DELETE'])
@api_token_required
def delete_pdf(pdf_id):
    """Soft delete a PDF (mark as inactive)"""
    try:
        pdf_service = PDFStorageService()
        result = pdf_service.delete_pdf(pdf_id)
        
        if result['success']:
            return jsonify({'message': result['message']})
        else:
            return jsonify({'error': result['error']}), 400
            
    except Exception as e:
        return jsonify({'error': f'Delete failed: {str(e)}'}), 500


@pdf_api_bp.route('/<int:pdf_id>/hard-delete', methods=['DELETE'])
@api_token_required
def hard_delete_pdf(pdf_id):
    """Permanently delete a PDF from storage and database"""
    try:
        pdf_service = PDFStorageService()
        result = pdf_service.hard_delete_pdf(pdf_id)
        
        if result['success']:
            return jsonify({'message': result['message']})
        else:
            return jsonify({'error': result['error']}), 400
            
    except Exception as e:
        return jsonify({'error': f'Hard delete failed: {str(e)}'}), 500


@pdf_api_bp.route('/list', methods=['GET'])
@api_token_required
def list_pdfs():
    """List PDFs with optional filtering"""
    try:
        module_id = request.args.get('module_id', type=int)
        is_active = request.args.get('is_active', 'true').lower() == 'true'
        limit = min(request.args.get('limit', 50, type=int), 100)
        offset = request.args.get('offset', 0, type=int)
        
        pdf_service = PDFStorageService()
        result = pdf_service.list_pdfs(
            module_id=module_id,
            is_active=is_active,
            limit=limit,
            offset=offset
        )
        
        if result['success']:
            return jsonify(result)
        else:
            return jsonify({'error': result['error']}), 400
            
    except Exception as e:
        return jsonify({'error': f'List failed: {str(e)}'}), 500


@pdf_api_bp.route('/question/<question_id>', methods=['GET'])
def get_pdfs_for_question(question_id):
    """Get relevant PDFs for a specific question (public endpoint)"""
    try:
        max_pdfs = min(request.args.get('max_pdfs', 3, type=int), 10)
        
        pdf_service = PDFStorageService()
        pdfs = pdf_service.get_pdfs_for_question(question_id, max_pdfs)
        
        return jsonify({
            'success': True,
            'question_id': question_id,
            'pdfs': pdfs
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get PDFs: {str(e)}'}), 500


# Helper endpoints for form data
@pdf_api_bp.route('/modules', methods=['GET'])
@api_token_required
def get_modules():
    """Get all modules for form selection"""
    try:
        client = supabase_client.get_db()
        result = client.table('modules').select('id, name, year').order('year', nullsfirst=False).order('name').execute()
        
        return jsonify({
            'success': True,
            'modules': result.data or []
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get modules: {str(e)}'}), 500


@pdf_api_bp.route('/topics', methods=['GET'])
@api_token_required
def get_topics():
    """Get all topics for form selection"""
    try:
        client = supabase_client.get_db()
        result = client.table('topics').select('id, name').order('name').execute()
        
        return jsonify({
            'success': True,
            'topics': result.data or []
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get topics: {str(e)}'}), 500


@pdf_api_bp.route('/subtopics', methods=['GET'])
@api_token_required
def get_subtopics():
    """Get all subtopics for form selection"""
    try:
        client = supabase_client.get_db()
        result = client.table('subtopics').select('id, name').order('name').execute()
        
        return jsonify({
            'success': True,
            'subtopics': result.data or []
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get subtopics: {str(e)}'}), 500


@pdf_api_bp.route('/tags', methods=['GET'])
@api_token_required
def get_tags():
    """Get all tags for form selection"""
    try:
        client = supabase_client.get_db()
        result = client.table('tags').select('id, name').order('name').execute()
        
        return jsonify({
            'success': True,
            'tags': result.data or []
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to get tags: {str(e)}'}), 500