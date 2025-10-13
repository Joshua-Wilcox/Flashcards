"""
PDF Storage Service for Supabase Storage Bucket Management
Handles PDF uploads, metadata management, and file operations
"""

import os
import uuid
from typing import Optional, List, Dict, Any
from werkzeug.utils import secure_filename
from models.supabase_adapter import supabase_client
import mimetypes

class PDFStorageService:
    """Service for managing PDFs in Supabase storage buckets"""
    
    BUCKET_NAME = "pdfs"
    ALLOWED_EXTENSIONS = {'.pdf'}
    MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
    
    def __init__(self):
        self.client = supabase_client.get_db()
        self._ensure_bucket_exists()
    
    def _ensure_bucket_exists(self):
        """Ensure the PDF storage bucket exists"""
        try:
            # Try to get bucket info
            self.client.storage.get_bucket(self.BUCKET_NAME)
        except Exception:
            # Create bucket if it doesn't exist
            try:
                self.client.storage.create_bucket(
                    self.BUCKET_NAME,
                    options={"public": False}  # Private bucket, access controlled by RLS
                )
            except Exception as e:
                print(f"Warning: Could not create/verify bucket {self.BUCKET_NAME}: {e}")
    
    def _validate_file(self, file, filename: str) -> tuple[bool, str]:
        """Validate uploaded file"""
        if not filename:
            return False, "No filename provided"
        
        # Check file extension
        _, ext = os.path.splitext(filename.lower())
        if ext not in self.ALLOWED_EXTENSIONS:
            return False, f"File type {ext} not allowed. Only PDF files are supported."
        
        # Check file size if file object has seek/tell methods
        if hasattr(file, 'seek') and hasattr(file, 'tell'):
            file.seek(0, 2)  # Seek to end
            size = file.tell()
            file.seek(0)  # Reset to beginning
            
            if size > self.MAX_FILE_SIZE:
                return False, f"File too large. Maximum size is {self.MAX_FILE_SIZE // (1024*1024)}MB"
        
        return True, ""
    
    def upload_pdf(self, 
                   file, 
                   filename: str,
                   module_id: int,
                   topic_ids: Optional[List[int]] = None,
                   subtopic_ids: Optional[List[int]] = None,
                   tag_ids: Optional[List[int]] = None,
                   uploaded_by: Optional[str] = None,
                   metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Upload a PDF file and create database record
        
        Args:
            file: File object to upload
            filename: Original filename
            module_id: ID of the module this PDF belongs to
            topic_ids: List of topic IDs to associate with this PDF
            subtopic_ids: List of subtopic IDs to associate with this PDF 
            tag_ids: List of tag IDs to associate with this PDF
            uploaded_by: User who uploaded the file
            metadata: Additional metadata dictionary
            
        Returns:
            Dict with success status and PDF info or error message
        """
        try:
            # Validate file
            is_valid, error_msg = self._validate_file(file, filename)
            if not is_valid:
                return {"success": False, "error": error_msg}
            
            # Generate unique storage path
            secure_name = secure_filename(filename)
            unique_id = str(uuid.uuid4())
            storage_path = f"{unique_id}/{secure_name}"
            
            # Get file size and mime type
            file_size = None
            if hasattr(file, 'seek') and hasattr(file, 'tell'):
                file.seek(0, 2)
                file_size = file.tell()
                file.seek(0)
            
            mime_type = mimetypes.guess_type(filename)[0] or 'application/pdf'
            
            # Read file data from FileStorage object or use as-is for other types
            if hasattr(file, 'read'):
                file_data = file.read()
                file.seek(0)  # Reset for any subsequent operations
            else:
                file_data = file
            
            # Upload to storage bucket
            result = self.client.storage.from_(self.BUCKET_NAME).upload(
                path=storage_path,
                file=file_data,
                file_options={"content-type": mime_type}
            )
            
            if hasattr(result, 'error') and result.error:
                return {"success": False, "error": f"Upload failed: {result.error}"}
            
            # Use the new RPC function to create database record with multiple topics/subtopics
            rpc_result = self.client.rpc('upsert_pdf_with_metadata', {
                'storage_path_param': storage_path,
                'original_filename_param': secure_name,
                'module_id_param': module_id,
                'topic_ids_param': topic_ids,
                'subtopic_ids_param': subtopic_ids,
                'tag_ids_param': tag_ids,
                'uploaded_by_param': uploaded_by,
                'metadata_param': metadata or {},
                'file_size_param': file_size,
                'mime_type_param': mime_type
            }).execute()
            
            if not rpc_result.data or not rpc_result.data[0]['success']:
                # If database insert failed, try to clean up uploaded file
                try:
                    self.client.storage.from_(self.BUCKET_NAME).remove([storage_path])
                except:
                    pass
                error_msg = rpc_result.data[0]['message'] if rpc_result.data else "Failed to create database record"
                return {"success": False, "error": error_msg}
            
            pdf_id = rpc_result.data[0]['pdf_id']
            
            return {
                "success": True,
                "pdf_id": pdf_id,
                "storage_path": storage_path,
                "filename": secure_name
            }
            
        except Exception as e:
            return {"success": False, "error": f"Upload error: {str(e)}"}
    
    def get_pdf_url(self, storage_path: str, expires_in: int = 3600) -> Optional[str]:
        """Get a signed URL for accessing a PDF"""
        try:
            result = self.client.storage.from_(self.BUCKET_NAME).create_signed_url(
                path=storage_path,
                expires_in=expires_in
            )
            return result.get('signedURL') if result else None
        except Exception as e:
            print(f"Error creating signed URL: {e}")
            return None
    
    def download_pdf_content(self, storage_path: str) -> Optional[bytes]:
        """Download PDF content from storage bucket"""
        try:
            result = self.client.storage.from_(self.BUCKET_NAME).download(storage_path)
            return result if result else None
        except Exception as e:
            print(f"Error downloading PDF content: {e}")
            return None
    
    def delete_pdf(self, pdf_id: int) -> Dict[str, Any]:
        """Soft delete a PDF (mark as inactive)"""
        try:
            # Get PDF info
            pdf_result = self.client.table('pdfs').select('storage_path').eq('id', pdf_id).execute()
            if not pdf_result.data:
                return {"success": False, "error": "PDF not found"}
            
            # Mark as inactive in database
            update_result = self.client.table('pdfs').update({"is_active": False}).eq('id', pdf_id).execute()
            
            if update_result.data:
                return {"success": True, "message": "PDF marked as inactive"}
            else:
                return {"success": False, "error": "Failed to update database"}
                
        except Exception as e:
            return {"success": False, "error": f"Delete error: {str(e)}"}
    
    def hard_delete_pdf(self, pdf_id: int) -> Dict[str, Any]:
        """Permanently delete a PDF from storage and database"""
        try:
            # Get PDF info
            pdf_result = self.client.table('pdfs').select('storage_path').eq('id', pdf_id).execute()
            if not pdf_result.data:
                return {"success": False, "error": "PDF not found"}
            
            storage_path = pdf_result.data[0]['storage_path']
            
            # Delete from storage
            self.client.storage.from_(self.BUCKET_NAME).remove([storage_path])
            
            # Delete from database (will cascade to pdf_tags)
            delete_result = self.client.table('pdfs').delete().eq('id', pdf_id).execute()
            
            if delete_result.data:
                return {"success": True, "message": "PDF permanently deleted"}
            else:
                return {"success": False, "error": "Failed to delete from database"}
                
        except Exception as e:
            return {"success": False, "error": f"Delete error: {str(e)}"}
    
    def update_pdf_metadata(self, 
                           pdf_id: int,
                           module_id: Optional[int] = None,
                           topic_ids: Optional[List[int]] = None,
                           subtopic_ids: Optional[List[int]] = None,
                           tag_ids: Optional[List[int]] = None,
                           metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Update PDF metadata and associations"""
        try:
            update_data = {}
            
            if module_id is not None:
                update_data['module_id'] = module_id
            if metadata is not None:
                update_data['metadata'] = metadata
            
            if update_data:
                pdf_result = self.client.table('pdfs').update(update_data).eq('id', pdf_id).execute()
                if not pdf_result.data:
                    return {"success": False, "error": "Failed to update PDF"}
            
            # Update topic associations if provided
            if topic_ids is not None:
                # Remove existing topic associations
                self.client.table('pdf_topics').delete().eq('pdf_id', pdf_id).execute()
                
                # Add new associations
                if topic_ids:
                    topic_associations = [
                        {"pdf_id": pdf_id, "topic_id": topic_id}
                        for topic_id in topic_ids
                    ]
                    self.client.table('pdf_topics').insert(topic_associations).execute()
            
            # Update subtopic associations if provided
            if subtopic_ids is not None:
                # Remove existing subtopic associations
                self.client.table('pdf_subtopics').delete().eq('pdf_id', pdf_id).execute()
                
                # Add new associations
                if subtopic_ids:
                    subtopic_associations = [
                        {"pdf_id": pdf_id, "subtopic_id": subtopic_id}
                        for subtopic_id in subtopic_ids
                    ]
                    self.client.table('pdf_subtopics').insert(subtopic_associations).execute()
            
            # Update tag associations if provided
            if tag_ids is not None:
                # Remove existing tag associations
                self.client.table('pdf_tags').delete().eq('pdf_id', pdf_id).execute()
                
                # Add new associations
                if tag_ids:
                    tag_associations = [
                        {"pdf_id": pdf_id, "tag_id": tag_id, "count": 1}
                        for tag_id in tag_ids
                    ]
                    self.client.table('pdf_tags').insert(tag_associations).execute()
            
            return {"success": True, "message": "PDF metadata updated"}
            
        except Exception as e:
            return {"success": False, "error": f"Update error: {str(e)}"}
    
    def get_pdfs_for_question(self, question_id: str, max_pdfs: int = 3) -> List[Dict[str, Any]]:
        """Get relevant PDFs for a question using the optimized RPC function"""
        try:
            result = self.client.rpc('get_pdfs_for_question_v3', {
                'question_id_param': question_id,
                'max_pdfs_param': max_pdfs
            }).execute()
            
            if result.data:
                # Use application's PDF serving route instead of signed URLs
                pdfs = []
                for pdf in result.data:
                    pdf_data = dict(pdf)
                    # Return just the PDF ID, let frontend handle the /pdf/ prefix
                    pdf_data['url'] = str(pdf['pdf_id'])
                    pdf_data['name'] = pdf['original_filename']
                    pdfs.append(pdf_data)
                return pdfs
            
            return []
            
        except Exception as e:
            print(f"Error getting PDFs for question {question_id}: {e}")
            return []
    
    def list_pdfs(self, 
                  module_id: Optional[int] = None,
                  is_active: bool = True,
                  limit: int = 50,
                  offset: int = 0) -> Dict[str, Any]:
        """List PDFs with optional filtering"""
        try:
            query = self.client.table('pdfs').select("""
                id, storage_path, original_filename, file_size, created_at,
                modules!inner(name),
                pdf_topics!left(topics!inner(name)),
                pdf_subtopics!left(subtopics!inner(name))
            """)
            
            if module_id:
                query = query.eq('module_id', module_id)
            
            query = query.eq('is_active', is_active)
            query = query.order('created_at', desc=True)
            query = query.range(offset, offset + limit - 1)
            
            result = query.execute()
            
            return {
                "success": True,
                "pdfs": result.data or [],
                "count": len(result.data or [])
            }
            
        except Exception as e:
            return {"success": False, "error": f"List error: {str(e)}"}
    
    def _resolve_names_to_ids(self, 
                              module_name: Optional[str] = None,
                              topic_names: Optional[List[str]] = None,
                              subtopic_names: Optional[List[str]] = None,
                              tag_names: Optional[List[str]] = None) -> Dict[str, Any]:
        """Resolve entity names to their database IDs, creating them if they don't exist"""
        try:
            resolved = {
                "module_id": None,
                "topic_ids": [],
                "subtopic_ids": [],
                "tag_ids": []
            }
            
            # Resolve module
            if module_name:
                result = self.client.table('modules').select('id').eq('name', module_name).execute()
                if result.data:
                    resolved["module_id"] = result.data[0]['id']
                else:
                    # Create new module
                    new_module = self.client.table('modules').insert({"name": module_name}).execute()
                    if new_module.data:
                        resolved["module_id"] = new_module.data[0]['id']
                    else:
                        return {"success": False, "error": f"Failed to create module: {module_name}"}
            
            # Resolve topics
            if topic_names:
                for topic_name in topic_names:
                    result = self.client.table('topics').select('id').eq('name', topic_name).execute()
                    if result.data:
                        resolved["topic_ids"].append(result.data[0]['id'])
                    else:
                        # Create new topic
                        new_topic = self.client.table('topics').insert({"name": topic_name}).execute()
                        if new_topic.data:
                            resolved["topic_ids"].append(new_topic.data[0]['id'])
                        else:
                            return {"success": False, "error": f"Failed to create topic: {topic_name}"}
            
            # Resolve subtopics
            if subtopic_names:
                for subtopic_name in subtopic_names:
                    result = self.client.table('subtopics').select('id').eq('name', subtopic_name).execute()
                    if result.data:
                        resolved["subtopic_ids"].append(result.data[0]['id'])
                    else:
                        # Create new subtopic
                        new_subtopic = self.client.table('subtopics').insert({"name": subtopic_name}).execute()
                        if new_subtopic.data:
                            resolved["subtopic_ids"].append(new_subtopic.data[0]['id'])
                        else:
                            return {"success": False, "error": f"Failed to create subtopic: {subtopic_name}"}
            
            # Resolve tags
            if tag_names:
                for tag_name in tag_names:
                    result = self.client.table('tags').select('id').eq('name', tag_name).execute()
                    if result.data:
                        resolved["tag_ids"].append(result.data[0]['id'])
                    else:
                        # Create new tag
                        new_tag = self.client.table('tags').insert({"name": tag_name}).execute()
                        if new_tag.data:
                            resolved["tag_ids"].append(new_tag.data[0]['id'])
                        else:
                            return {"success": False, "error": f"Failed to create tag: {tag_name}"}
            
            return {"success": True, "resolved": resolved}
            
        except Exception as e:
            return {"success": False, "error": f"Name resolution error: {str(e)}"}
    
    def upload_pdf_by_names(self, 
                            file, 
                            filename: str,
                            module_name: str,
                            topic_names: Optional[List[str]] = None,
                            subtopic_names: Optional[List[str]] = None,
                            tag_names: Optional[List[str]] = None,
                            uploaded_by: Optional[str] = None,
                            metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Upload a PDF file using entity names instead of IDs
        
        Args:
            file: File object to upload
            filename: Original filename  
            module_name: Name of the module this PDF belongs to
            topic_names: List of topic names to associate
            subtopic_names: List of subtopic names to associate
            tag_names: List of tag names to associate
            uploaded_by: User who uploaded the file
            metadata: Additional metadata dictionary
            
        Returns:
            Dict with success status and PDF info or error message
        """
        try:
            # Resolve names to IDs
            resolution_result = self._resolve_names_to_ids(
                module_name=module_name,
                topic_names=topic_names or [],
                subtopic_names=subtopic_names or [],
                tag_names=tag_names or []
            )
            
            if not resolution_result["success"]:
                return resolution_result
            
            resolved = resolution_result["resolved"]
            
            # Validate file
            is_valid, error_msg = self._validate_file(file, filename)
            if not is_valid:
                return {"success": False, "error": error_msg}
            
            # Check for existing PDF with same filename and module
            secure_name = secure_filename(filename)
            existing_pdf = self.client.table('pdfs').select('id, storage_path').eq(
                'original_filename', secure_name
            ).eq('module_id', resolved["module_id"]).eq('is_active', True).execute()
            
            if existing_pdf.data:
                # Replace existing PDF file and update metadata
                existing_pdf_id = existing_pdf.data[0]['id']
                existing_storage_path = existing_pdf.data[0]['storage_path']
                
                # Get file size and mime type for the new PDF
                file_size = None
                if hasattr(file, 'seek') and hasattr(file, 'tell'):
                    file.seek(0, 2)
                    file_size = file.tell()
                    file.seek(0)
                
                mime_type = mimetypes.guess_type(filename)[0] or 'application/pdf'
                
                # Read file data from FileStorage object or use as-is for other types
                if hasattr(file, 'read'):
                    file_data = file.read()
                    file.seek(0)  # Reset for any subsequent operations
                else:
                    file_data = file
                
                # Replace the file in storage (same path, new content)
                storage_result = self.client.storage.from_(self.BUCKET_NAME).update(
                    path=existing_storage_path,
                    file=file_data,
                    file_options={"content-type": mime_type, "upsert": True}
                )
                
                if hasattr(storage_result, 'error') and storage_result.error:
                    return {"success": False, "error": f"Failed to update PDF file: {storage_result.error}"}
                
                # Use ID-based RPC function to update existing PDF with new metadata
                rpc_result = self.client.rpc('upsert_pdf_with_metadata', {
                    'storage_path_param': existing_storage_path,
                    'original_filename_param': secure_name,
                    'module_id_param': resolved["module_id"],
                    'topic_ids_param': resolved["topic_ids"],
                    'subtopic_ids_param': resolved["subtopic_ids"],
                    'tag_ids_param': resolved["tag_ids"],
                    'uploaded_by_param': uploaded_by,
                    'metadata_param': metadata or {},
                    'file_size_param': file_size,
                    'mime_type_param': mime_type
                }).execute()
                
                if not rpc_result.data or not rpc_result.data[0]['success']:
                    error_msg = rpc_result.data[0]['message'] if rpc_result.data else "Failed to update PDF record"
                    return {"success": False, "error": error_msg}
                
                return {
                    "success": True,
                    "pdf_id": existing_pdf_id,
                    "filename": secure_name,
                    "storage_path": existing_storage_path,
                    "message": "Updated existing PDF with new content and metadata",
                    "resolved_entities": {
                        "module_id": resolved["module_id"],
                        "topic_ids": resolved["topic_ids"],
                        "subtopic_ids": resolved["subtopic_ids"], 
                        "tag_ids": resolved["tag_ids"]
                    }
                }
            
            # Generate unique storage path for new upload
            unique_id = str(uuid.uuid4())
            storage_path = f"{unique_id}/{secure_name}"
            
            # Get file size and mime type
            file_size = None
            if hasattr(file, 'seek') and hasattr(file, 'tell'):
                file.seek(0, 2)
                file_size = file.tell()
                file.seek(0)
            
            mime_type = mimetypes.guess_type(filename)[0] or 'application/pdf'
            
            # Read file data from FileStorage object or use as-is for other types
            if hasattr(file, 'read'):
                file_data = file.read()
                file.seek(0)  # Reset for any subsequent operations
            else:
                file_data = file
            
            # Upload to storage bucket
            result = self.client.storage.from_(self.BUCKET_NAME).upload(
                path=storage_path,
                file=file_data,
                file_options={"content-type": mime_type}
            )
            
            if hasattr(result, 'error') and result.error:
                return {"success": False, "error": f"Upload failed: {result.error}"}
            
            # Use RPC function to create database record with names (not IDs)
            rpc_result = self.client.rpc('upsert_pdf_with_metadata', {
                'p_storage_path': storage_path,
                'p_original_filename': secure_name,
                'p_file_size': file_size,
                'p_mime_type': mime_type,
                'p_uploaded_by': uploaded_by,
                'p_metadata': metadata or {},
                'p_module_name': module_name,
                'p_topic_names': topic_names,
                'p_subtopic_names': subtopic_names,
                'p_tag_names': tag_names
            }).execute()
            
            if not rpc_result.data or rpc_result.data[0] is None:
                # If database insert failed, try to clean up uploaded file
                try:
                    self.client.storage.from_(self.BUCKET_NAME).remove([storage_path])
                except:
                    pass
                return {"success": False, "error": "Failed to create database record"}
            
            pdf_id = rpc_result.data[0]
            
            return {
                "success": True,
                "pdf_id": pdf_id,
                "filename": secure_name,
                "storage_path": storage_path,
                "resolved_entities": {
                    "module_id": resolved["module_id"],
                    "topic_ids": resolved["topic_ids"],
                    "subtopic_ids": resolved["subtopic_ids"], 
                    "tag_ids": resolved["tag_ids"]
                }
            }
            
        except Exception as e:
            return {"success": False, "error": f"Upload error: {str(e)}"}