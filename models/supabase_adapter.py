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
                                fallback_method: Callable[[], Any]) -> Any:
        """
        Execute RPC function with automatic fallback to existing method
        
        Args:
            function_name: Name of the RPC function to call
            params: Parameters for the RPC function
            fallback_method: Fallback method to call if RPC fails
            
        Returns:
            Result from RPC function or fallback method
        """
        if not self.rpc_enabled:
            logger.info(f"RPC functions disabled, using fallback for {function_name}")
            return fallback_method()
        
        try:
            logger.info(f"Executing RPC function: {function_name}")
            result = self.client.rpc(function_name, params).execute()
            logger.info(f"RPC function {function_name} succeeded")
            return result
        except Exception as e:
            logger.warning(f"RPC function {function_name} failed: {e}, using fallback")
            return fallback_method()
    
    def get_module_filter_data_rpc(self, module_name: str, selected_topics: List[str] = None) -> Dict[str, List[Dict]]:
        """Get filter data using optimized RPC function"""
        def fallback():
            return self._get_module_filter_data_fallback(module_name, selected_topics)
        
        try:
            result = self.execute_rpc_with_fallback(
                'get_module_filter_data',
                {
                    'module_name_param': module_name,
                    'selected_topics_param': selected_topics
                },
                fallback
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
                return fallback()
                
        except Exception as e:
            logger.error(f"Error processing RPC result: {e}")
            return fallback()
    
    def get_filtered_questions_rpc(self, module_name: str, topics: List[str] = None, 
                                 subtopics: List[str] = None, tags: List[str] = None) -> List[Dict]:
        """Get filtered questions using optimized RPC function"""
        def fallback():
            return self._get_filtered_questions_fallback(module_name, topics, subtopics, tags)
        
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
                },
                fallback
            )
            
            return result.data if hasattr(result, 'data') else fallback()
            
        except Exception as e:
            logger.error(f"Error in get_filtered_questions_rpc: {e}")
            return fallback()
    
    def get_smart_distractors_rpc(self, question_id: str, limit: int = 3) -> List[Dict]:
        """Get smart distractors using database-computed similarity scoring"""
        def fallback():
            return self._get_smart_distractors_fallback(question_id, limit)
        
        try:
            result = self.execute_rpc_with_fallback(
                'get_smart_distractors',
                {
                    'question_id_param': question_id,
                    'limit_param': limit
                },
                fallback
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
                return fallback()
            
        except Exception as e:
            logger.error(f"Error in get_smart_distractors_rpc: {e}")
            return fallback()
    
    def get_topic_suggestions_rpc(self, module_name: str, query: str = None, limit: int = 10) -> List[Dict]:
        """Get topic suggestions using RPC function"""
        def fallback():
            return self._get_suggestions_fallback('topics', module_name, None, query, limit)
        
        try:
            result = self.execute_rpc_with_fallback(
                'get_topic_suggestions',
                {
                    'module_name_param': module_name,
                    'query_param': query,
                    'limit_param': limit
                },
                fallback
            )
            
            if hasattr(result, 'data') and result.data:
                return [{'name': row['name'], 'count': row['count']} for row in result.data]
            else:
                return fallback()
                
        except Exception as e:
            logger.error(f"Error in get_topic_suggestions_rpc: {e}")
            return fallback()
    
    def get_subtopic_suggestions_rpc(self, module_name: str, topic_name: str, query: str = None, limit: int = 10) -> List[Dict]:
        """Get subtopic suggestions using RPC function"""
        def fallback():
            return self._get_suggestions_fallback('subtopics', module_name, topic_name, query, limit)
        
        try:
            result = self.execute_rpc_with_fallback(
                'get_subtopic_suggestions',
                {
                    'module_name_param': module_name,
                    'topic_name_param': topic_name,
                    'query_param': query,
                    'limit_param': limit
                },
                fallback
            )
            
            if hasattr(result, 'data') and result.data:
                return [{'name': row['name'], 'count': row['count']} for row in result.data]
            else:
                return fallback()
                
        except Exception as e:
            logger.error(f"Error in get_subtopic_suggestions_rpc: {e}")
            return fallback()
    
    def get_tag_suggestions_rpc(self, module_name: str, query: str = None, limit: int = 10) -> List[Dict]:
        """Get tag suggestions using RPC function"""
        def fallback():
            return self._get_suggestions_fallback('tags', module_name, None, query, limit)
        
        try:
            result = self.execute_rpc_with_fallback(
                'get_tag_suggestions',
                {
                    'module_name_param': module_name,
                    'query_param': query,
                    'limit_param': limit
                },
                fallback
            )
            
            if hasattr(result, 'data') and result.data:
                return [{'name': row['name'], 'count': row['count']} for row in result.data]
            else:
                return fallback()
                
        except Exception as e:
            logger.error(f"Error in get_tag_suggestions_rpc: {e}")
            return fallback()
    
    def process_answer_check_rpc(self, user_id: str, question_id: str, is_correct: bool, 
                               token: str, username: str = 'Unknown') -> Dict:
        """Process answer check using optimized RPC function - reduces 6-7 calls to 2-3"""
        def fallback():
            return self._process_answer_check_fallback(user_id, question_id, is_correct, token, username)
        
        try:
            result = self.execute_rpc_with_fallback(
                'process_answer_check',
                {
                    'user_id_param': user_id,
                    'question_id_param': question_id,
                    'is_correct_param': is_correct,
                    'token_param': token,
                    'username_param': username
                },
                fallback
            )
            
            if hasattr(result, 'data') and result.data:
                # The RPC function returns JSON, parse it
                return result.data[0] if isinstance(result.data, list) else result.data
            else:
                return fallback()
                
        except Exception as e:
            logger.error(f"Error in process_answer_check_rpc: {e}")
            return fallback()
    
    def get_suggestions_rpc(self, suggestion_type: str, module_name: str, 
                          topic_name: str = None, query: str = None, limit: int = 10) -> List[Dict]:
        """Get optimized suggestions using RPC functions"""
        def fallback():
            return self._get_suggestions_fallback(suggestion_type, module_name, topic_name, query, limit)
        
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
                return fallback()
            
            result = self.execute_rpc_with_fallback(function_name, params, fallback)
            
            if hasattr(result, 'data') and result.data:
                return [{'name': row['name'], 'count': row['count']} for row in result.data]
            else:
                return fallback()
                
        except Exception as e:
            logger.error(f"Error in get_suggestions_rpc: {e}")
            return fallback()
    
    def _get_module_filter_data_fallback(self, module_name: str, selected_topics: List[str] = None) -> Dict[str, List[Dict]]:
        """Fallback method for filter data retrieval"""
        # Import here to avoid circular imports
        from models.database import get_all_modules
        
        try:
            # Get module ID
            module_result = self.client.table('modules').select('id').eq('name', module_name).execute()
            if not module_result.data:
                return {'topics': [], 'subtopics': [], 'tags': []}
            
            module_id = module_result.data[0]['id']
            
            # Get all questions in this module
            questions_result = self.client.table('questions').select('id').eq('module_id', module_id).execute()
            if not questions_result.data:
                return {'topics': [], 'subtopics': [], 'tags': []}
            
            question_ids = [q['id'] for q in questions_result.data]
            
            from models.question import get_comprehensive_question_metadata
            metadata = get_comprehensive_question_metadata(question_ids)
            
            # Aggregate unique values with counts
            topics_dict = {}
            subtopics_dict = {}
            tags_dict = {}
            
            for qid, meta in metadata.items():
                for topic in meta.get('topics', []):
                    topics_dict[topic] = topics_dict.get(topic, 0) + 1
                for subtopic in meta.get('subtopics', []):
                    subtopics_dict[subtopic] = subtopics_dict.get(subtopic, 0) + 1
                for tag in meta.get('tags', []):
                    tags_dict[tag] = tags_dict.get(tag, 0) + 1
            
            return {
                'topics': [{'name': name, 'count': count} for name, count in sorted(topics_dict.items())],
                'subtopics': [{'name': name, 'count': count} for name, count in sorted(subtopics_dict.items())],
                'tags': [{'name': name, 'count': count} for name, count in sorted(tags_dict.items())]
            }
            
        except Exception as e:
            logger.error(f"Error in filter data fallback: {e}")
            return {'topics': [], 'subtopics': [], 'tags': []}
    
    def _get_filtered_questions_fallback(self, module_name: str, topics: List[str] = None, 
                                       subtopics: List[str] = None, tags: List[str] = None) -> List[Dict]:
        """Fallback method for filtered questions"""
        try:
            module_result = self.client.table('modules').select('id').eq('name', module_name).execute()
            if not module_result.data:
                return []
            
            module_id = module_result.data[0]['id']
            questions_result = self.client.table('questions').select('id, question, answer, module_id').eq('module_id', module_id).execute()
            
            return questions_result.data if questions_result.data else []
            
        except Exception as e:
            logger.error(f"Error in filtered questions fallback: {e}")
            return []
    
    def _get_smart_distractors_fallback(self, question_id: str, limit: int = 3) -> List[Dict]:
        """Fallback method for smart distractors"""
        try:
            question_result = self.client.table('questions').select('module_id').eq('id', question_id).execute()
            if not question_result.data:
                return []
            
            module_id = question_result.data[0]['module_id']
            distractors_result = self.client.table('questions').select('id, answer').eq('module_id', module_id).neq('id', question_id).limit(limit).execute()
            
            return [
                {
                    'distractor_id': row['id'],
                    'distractor_answer': row['answer'],
                    'similarity_score': 1  # Default score for fallback
                }
                for row in (distractors_result.data or [])
            ]
            
        except Exception as e:
            logger.error(f"Error in smart distractors fallback: {e}")
            return []
    
    def _get_suggestions_fallback(self, suggestion_type: str, module_name: str, 
                                topic_name: str = None, query: str = None, limit: int = 10) -> List[Dict]:
        """Fallback method for suggestions"""
        try:
            if suggestion_type == 'topics':
                table = 'topics'
                join_table = 'question_topics'
                join_field = 'topic_id'
            elif suggestion_type == 'subtopics':
                table = 'subtopics'
                join_table = 'question_subtopics'
                join_field = 'subtopic_id'
            elif suggestion_type == 'tags':
                table = 'tags'
                join_table = 'question_tags'
                join_field = 'tag_id'
            else:
                return []
            
            query_builder = self.client.table(table).select('name')
            if query and query.strip():
                query_builder = query_builder.ilike('name', f'%{query}%')
            
            result = query_builder.limit(limit).execute()
            
            return [{'name': row['name'], 'count': 1} for row in (result.data or [])]
            
        except Exception as e:
            logger.error(f"Error in suggestions fallback: {e}")
            return []
    
    def _process_answer_check_fallback(self, user_id: str, question_id: str, is_correct: bool, 
                                     token: str, username: str = 'Unknown') -> Dict:
        """Fallback method for answer checking - matches original logic"""
        try:
            # Get question details
            question_result = self.client.table('questions').select('answer, module_id').eq('id', question_id).execute()
            if not question_result.data:
                return {'error': 'Question not found'}
            
            question = question_result.data[0]
            
            # Get user stats
            stats_result = self.client.table('user_stats').select('correct_answers, total_answers, current_streak').eq('user_id', user_id).execute()
            if stats_result.data:
                stats = stats_result.data[0]
                correct = stats.get('correct_answers', 0) or 0
                total = stats.get('total_answers', 0) or 0
                streak = stats.get('current_streak', 0) or 0
            else:
                correct = 0
                total = 0
                streak = 0
            
            # Calculate new values
            total += 1
            if is_correct:
                correct += 1
                streak += 1
            else:
                streak = 0
            
            # Get current time
            from datetime import datetime
            import pytz
            london_tz = pytz.timezone('Europe/London')
            now_london = datetime.now(london_tz)
            last_answer_time = now_london.isoformat()
            
            # Update module stats
            module_stats_result = self.client.table('module_stats').select('number_answered, number_correct, current_streak').eq('user_id', user_id).eq('module_id', question['module_id']).execute()
            
            if module_stats_result.data:
                module_stats = module_stats_result.data[0]
                new_answered = (module_stats.get('number_answered', 0) or 0) + 1
                new_correct = (module_stats.get('number_correct', 0) or 0) + (1 if is_correct else 0)
                new_streak = (module_stats.get('current_streak', 0) or 0) + 1 if is_correct else 0
                
                self.client.table('module_stats').update({
                    'number_answered': new_answered,
                    'number_correct': new_correct,
                    'last_answered_time': last_answer_time,
                    'current_streak': new_streak
                }).eq('user_id', user_id).eq('module_id', question['module_id']).execute()
            else:
                self.client.table('module_stats').insert({
                    'user_id': user_id,
                    'module_id': question['module_id'],
                    'number_answered': 1,
                    'number_correct': 1 if is_correct else 0,
                    'last_answered_time': last_answer_time,
                    'current_streak': 1 if is_correct else 0
                }).execute()
            
            # Insert used token if correct
            if is_correct:
                self.client.table('used_tokens').insert({
                    'user_id': user_id,
                    'token': token
                }).execute()
            
            # Update user stats
            self.client.table('user_stats').upsert({
                'user_id': user_id,
                'username': username,
                'correct_answers': correct,
                'total_answers': total,
                'last_answer_time': last_answer_time,
                'current_streak': streak
            }, on_conflict='user_id').execute()
            
            return {
                'success': True,
                'correct_answer': question['answer'],
                'module_id': question['module_id']
            }
            
        except Exception as e:
            logger.error(f"Error in answer check fallback: {e}")
            return {'error': str(e)}
    
    def real_time_channel(self, channel_name):
        """Create a real-time channel"""
        return self.client.channel(channel_name)

# Global instance
supabase_client = SupabaseAdapter()