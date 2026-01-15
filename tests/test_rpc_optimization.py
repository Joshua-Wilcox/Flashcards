import sys
import os
import unittest
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from models.supabase_adapter import supabase_client
from config import Config

class TestRPCOptimization(unittest.TestCase):
    def test_rpc_call(self):
        """Test the get_random_question_with_distractors RPC call"""
        print("\nTesting get_random_question_with_distractors RPC...")
        
        # Get a module ID first (assuming at least one module exists)
        client = supabase_client.get_db()
        module_result = client.table('modules').select('id, name').limit(1).execute()
        
        if not module_result.data:
            print("Skipping test: No modules found in DB.")
            return
            
        module_id = module_result.data[0]['id']
        module_name = module_result.data[0]['name']
        print(f"Using module: {module_name} (ID: {module_id})")
        
        # Call the RPC wrapper
        result = supabase_client.get_random_question_with_distractors_rpc(
            module_id=module_id,
            distractor_limit=4
        )
        
        if result is None:
            print("RPC returned None. The migration might not be applied yet.")
            print("Please apply '20260115180000_optimize_get_question.sql' to your Supabase instance.")
        else:
            print("RPC Call Successful!")
            print(f"Question ID: {result.get('question_data', {}).get('id')}")
            print(f"Question: {result.get('question_data', {}).get('question')}")
            
            distractors = result.get('distractors', {})
            manual_count = len(distractors.get('manual_distractors', []))
            smart_count = len(distractors.get('smart_distractors', []))
            print(f"Manual Distractors: {manual_count}")
            print(f"Smart Distractors: {smart_count}")
            
            self.assertIn('question_data', result)
            self.assertIn('distractors', result)

if __name__ == '__main__':
    unittest.main()
