import os
import logging
from typing import Dict, List, Any, Optional, Callable
from supabase.client import Client, create_client
from dotenv import load_dotenv

load_dotenv()

# Configure logging for RPC function monitoring
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SupabaseAdapter:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        
        self.client: Client = create_client(url, key)
        self.rpc_enabled = os.getenv("RPC_FUNCTIONS_ENABLED", "true").lower() == "true"
    
    def get_db(self):
        """Return the Supabase client for database operations"""
        return self.client
    
    def execute_rpc(self, function_name, params=None):
        """Execute a Supabase RPC function"""
        return self.client.rpc(function_name, params or {}).execute()
    
    def execute_rpc_with_fallback(self, function_name: str, params: Dict[str, Any], 
                                fallback_method: Callable[[], Any] = None) -> Any:
        """
        Execute RPC function. Fallback method is kept for API compatibility but ignored/logged if provided.
        """
        try:
            # logger.info(f"Executing RPC function: {function_name}")
            result = self.client.rpc(function_name, params).execute()
            # logger.info(f"RPC function {function_name} succeeded")
            return result
        except Exception as e:
            logger.error(f"RPC function {function_name} failed: {e}")
            if fallback_method:
                 logger.warning(f"Fallback method provided but fallback logic is deprecated/removed.")
            return None

    def get_module_filter_data_rpc(self, module_name: str, selected_topics: List[str] = None) -> Dict[str, List[Dict]]:
        """Get filter data using optimized RPC function"""
        try:
            result = self.execute_rpc_with_fallback(
                'get_module_filter_data',
                {
                    'module_name_param': module_name,
                    'selected_topics_param': selected_topics
                }
            )
            
            # Organize RPC results by filter type
            if hasattr(result, 'data') and result.data:
                filters = {'topics': [], 'subtopics': [], 'tags': []}
                
                for row in result.data:
                    filter_type = row['filter_type']
                    if filter_type == 'topic':
                        filters['topics'].append({
                            'name': row['name'],
                            'count': row['count']
                        })
                    elif filter_type == 'subtopic':
                        filters['subtopics'].append({
                            'name': row['name'],
                            'count': row['count']
                        })
                    elif filter_type == 'tag':
                        filters['tags'].append({
                            'name': row['name'],
                            'count': row['count']
                        })
                
                return filters
            else:
                return {'topics': [], 'subtopics': [], 'tags': []}
                
        except Exception as e:
            logger.error(f"Error processing RPC result: {e}")
            return {'topics': [], 'subtopics': [], 'tags': []}
    
    def get_filtered_questions_rpc(self, module_name: str, topics: List[str] = None, 
                                 subtopics: List[str] = None, tags: List[str] = None) -> List[Dict]:
        """Get filtered questions using optimized RPC function"""
        try:
            # Get module ID
            module_result = self.client.table('modules').select('id').eq('name', module_name).execute()
            if not module_result.data:
                return []
            
            module_id = module_result.data[0]['id']
            
            result = self.execute_rpc_with_fallback(
                'get_filtered_questions',
                {
                    'module_id_param': module_id,
                    'topic_names_param': topics,
                    'subtopic_names_param': subtopics,
                    'tag_names_param': tags
                }
            )
            
            return result.data if hasattr(result, 'data') else []
            
        except Exception as e:
            logger.error(f"Error in get_filtered_questions_rpc: {e}")
            return []
    
    def get_smart_distractors_rpc(self, question_id: str, limit: int = 3) -> List[Dict]:
        """Get smart distractors using database-computed similarity scoring"""
        try:
            result = self.execute_rpc_with_fallback(
                'get_smart_distractors',
                {
                    'question_id_param': question_id,
                    'limit_param': limit
                }
            )
            
            # Transform the RPC result to match expected format
            if hasattr(result, 'data') and result.data:
                transformed_data = []
                for row in result.data:
                    transformed_data.append({
                        'id': row['distractor_id'],  # Map distractor_id to id
                        'answer': row['distractor_answer'],  # Map distractor_answer to answer
                        'similarity_score': row.get('similarity_score', 0)
                    })
                return transformed_data
            else:
                return []
            
        except Exception as e:
            logger.error(f"Error in get_smart_distractors_rpc: {e}")
            return []
    
    def get_topic_suggestions_rpc(self, module_name: str, query: str = None, limit: int = 10) -> List[Dict]:
        """Get topic suggestions using RPC function"""
        try:
            result = self.execute_rpc_with_fallback(
                'get_topic_suggestions',
                {
                    'module_name_param': module_name,
                    'query_param': query,
                    'limit_param': limit
                }
            )
            
            if hasattr(result, 'data') and result.data:
                return [{'name': row['name'], 'count': row['count']} for row in result.data]
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error in get_topic_suggestions_rpc: {e}")
            return []
    
    def get_subtopic_suggestions_rpc(self, module_name: str, topic_name: str, query: str = None, limit: int = 10) -> List[Dict]:
        """Get subtopic suggestions using RPC function"""
        try:
            result = self.execute_rpc_with_fallback(
                'get_subtopic_suggestions',
                {
                    'module_name_param': module_name,
                    'topic_name_param': topic_name,
                    'query_param': query,
                    'limit_param': limit
                }
            )
            
            if hasattr(result, 'data') and result.data:
                return [{'name': row['name'], 'count': row['count']} for row in result.data]
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error in get_subtopic_suggestions_rpc: {e}")
            return []
    
    def get_tag_suggestions_rpc(self, module_name: str, query: str = None, limit: int = 10) -> List[Dict]:
        """Get tag suggestions using RPC function"""
        try:
            result = self.execute_rpc_with_fallback(
                'get_tag_suggestions',
                {
                    'module_name_param': module_name,
                    'query_param': query,
                    'limit_param': limit
                }
            )
            
            if hasattr(result, 'data') and result.data:
                return [{'name': row['name'], 'count': row['count']} for row in result.data]
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error in get_tag_suggestions_rpc: {e}")
            return []
    
    def process_answer_check_rpc(self, user_id: str, question_id: str, is_correct: bool, 
                                token: str, username: str = 'Unknown') -> Dict:
        """Process answer check using optimized RPC function"""
        try:
            result = self.execute_rpc_with_fallback(
                'process_answer_check',
                {
                    'user_id_param': user_id,
                    'question_id_param': question_id,
                    'is_correct_param': is_correct,
                    'token_param': token,
                    'username_param': username
                }
            )
            
            if hasattr(result, 'data') and result.data:
                # The RPC function returns JSON, parse it
                return result.data[0] if isinstance(result.data, list) else result.data
            else:
                return {'error': 'No data returned from RPC'}
                
        except Exception as e:
            logger.error(f"Error in process_answer_check_rpc: {e}")
            return {'error': str(e)}
    
    def check_answer_optimized_rpc(self, user_id: str, question_id: str, submitted_answer: str,
                                  token: str, username: str = 'Unknown') -> Dict:
        """
        Ultra-optimized answer check using single RPC call.
        """
        try:
            result = self.execute_rpc_with_fallback(
                'check_answer_optimized',
                {
                    'user_id_param': user_id,
                    'question_id_param': question_id,
                    'submitted_answer_param': submitted_answer,
                    'token_param': token,
                    'username_param': username
                }
            )
            
            if hasattr(result, 'data') and result.data:
                # The RPC function returns JSON, parse it
                return result.data[0] if isinstance(result.data, list) else result.data
            else:
                return {'error': 'No data returned from RPC'}
                
        except Exception as e:
            logger.error(f"Error in check_answer_optimized_rpc: {e}")
            return {'error': str(e)}
    
    def get_suggestions_rpc(self, suggestion_type: str, module_name: str, 
                          topic_name: str = None, query: str = None, limit: int = 10) -> List[Dict]:
        """Get optimized suggestions using RPC functions"""
        try:
            if suggestion_type == 'topics':
                function_name = 'get_topic_suggestions'
                params = {
                    'module_name_param': module_name,
                    'query_param': query,
                    'limit_param': limit
                }
            elif suggestion_type == 'subtopics':
                function_name = 'get_subtopic_suggestions'
                params = {
                    'module_name_param': module_name,
                    'topic_name_param': topic_name,
                    'query_param': query,
                    'limit_param': limit
                }
            elif suggestion_type == 'tags':
                function_name = 'get_tag_suggestions'
                params = {
                    'module_name_param': module_name,
                    'query_param': query,
                    'limit_param': limit
                }
            else:
                return []
            
            result = self.execute_rpc_with_fallback(function_name, params)
            
            if hasattr(result, 'data') and result.data:
                return [{'name': row['name'], 'count': row['count']} for row in result.data]
            else:
                return []
                
        except Exception as e:
            logger.error(f"Error in get_suggestions_rpc: {e}")
            return []

    
    def get_random_question_with_distractors_rpc(self, module_id: int, topic_names: List[str] = None, 
                                               subtopic_names: List[str] = None, tag_names: List[str] = None,
                                               specific_question_id: str = None, distractor_limit: int = 4) -> Dict:
        """
        Get a random question with all metadata and distractors using a single RPC call.
        """
        try:
            result = self.execute_rpc_with_fallback(
                'get_random_question_with_distractors',
                {
                    'module_id_param': module_id,
                    'topic_names_param': topic_names,
                    'subtopic_names_param': subtopic_names,
                    'tag_names_param': tag_names,
                    'specific_question_id_param': specific_question_id,
                    'distractor_limit_param': distractor_limit
                }
            )
            
            if hasattr(result, 'data') and result.data:
                # The RPC returns a list of rows (should be length 1)
                return result.data[0] if isinstance(result.data, list) and result.data else None
            else:
                return None
                
        except Exception as e:
            logger.error(f"Error in get_random_question_with_distractors_rpc: {e}")
            return None

    def real_time_channel(self, channel_name):
        """Create a real-time channel"""
        return self.client.channel(channel_name)

# Global instance
supabase_client = SupabaseAdapter()