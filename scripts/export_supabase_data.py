import json
from datetime import datetime
from models.supabase_adapter import supabase_client

def export_all_data():
    client = supabase_client.get_db()
    
    # Export all tables
    tables = ['user_stats', 'modules', 'questions', 'module_stats', 'tags', 'topics', 'subtopics']
    export_data = {}
    
    for table in tables:
        try:
            result = client.table(table).select('*').execute()
            export_data[table] = result.data
            print(f"Exported {len(result.data)} records from {table}")
        except Exception as e:
            print(f"Error exporting {table}: {e}")
            export_data[table] = []
    
    # Save to file
    filename = f'supabase_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json'
    with open(filename, 'w') as f:
        json.dump(export_data, f, indent=2, default=str)
    
    print(f"Data exported successfully to {filename}!")

if __name__ == "__main__":
    export_all_data()
