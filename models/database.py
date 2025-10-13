from collections import defaultdict
from models.supabase_adapter import supabase_client

def get_all_modules():
    """Get all modules from Supabase."""
    client = supabase_client.get_db()
    result = (client
              .table('modules')  # pylint: disable=no-member
              .select('id, name, year')  # pylint: disable=no-member
              .order('year', nullsfirst=False)  # pylint: disable=no-member
              .order('name'))  # pylint: disable=no-member

    result = result.execute()  # pylint: disable=no-member
    return [
        {
            'id': row['id'],
            'name': row['name'],
            'year': row.get('year')
        }
        for row in result.data
    ]


def get_module_id_by_name(module_name, year=None):
    """Get module ID by name, creating if it doesn't exist."""
    client = supabase_client.get_db()
    
    # Try to find existing module
    result = client.table('modules').select('id').eq('name', module_name).execute()  # pylint: disable=no-member
    if result.data:
        return result.data[0]['id']
    
    # Create new module
    insert_payload = {'name': module_name}
    if year is not None:
        insert_payload['year'] = year

    result = client.table('modules').insert(insert_payload).execute()  # pylint: disable=no-member
    return result.data[0]['id']

def get_module_name_by_id(module_id):
    """Get module name by ID."""
    client = supabase_client.get_db()
    result = client.table('modules').select('name').eq('id', module_id).execute()  # pylint: disable=no-member
    return result.data[0]['name'] if result.data else None

def get_unique_values(key):
    """Get unique values for a given field."""
    client = supabase_client.get_db()
    if key == 'topic':
        result = client.table('topics').select('name').execute()
    elif key == 'subtopic':
        result = client.table('subtopics').select('name').execute()
    else:
        # Fallback for other columns
        result = client.table('questions').select(key).execute()
    
    return sorted(list(set([row['name'] if 'name' in row else row[key] 
                           for row in result.data if row.get('name') or row.get(key)])))

# Database query helpers for Supabase
def execute_query(table, select_fields="*", filters=None, order_by=None, limit=None):
    """Generic query helper for Supabase."""
    client = supabase_client.get_db()
    query = client.table(table).select(select_fields)  # pylint: disable=no-member
    
    if filters:
        for field, operator, value in filters:
            if operator == 'eq':
                query = query.eq(field, value)  # pylint: disable=no-member
            elif operator == 'neq':
                query = query.neq(field, value)  # pylint: disable=no-member
            elif operator == 'like':
                query = query.like(field, value)  # pylint: disable=no-member
            elif operator == 'in':
                query = query.in_(field, value)  # pylint: disable=no-member
    
    if order_by:
        for field, direction in order_by:
            query = query.order(field, desc=(direction.lower() == 'desc'))  # pylint: disable=no-member
    
    if limit:
        query = query.limit(limit)  # pylint: disable=no-member
    
    result = query.execute()  # pylint: disable=no-member
    return result.data

def insert_record(table, data):
    """Insert a record into a Supabase table."""
    client = supabase_client.get_db()
    result = client.table(table).insert(data).execute()  # pylint: disable=no-member
    return result.data[0] if result.data else None

def update_record(table, data, filters):
    """Update records in a Supabase table."""
    client = supabase_client.get_db()
    query = client.table(table)  # pylint: disable=no-member
    
    for field, operator, value in filters:
        if operator == 'eq':
            query = query.eq(field, value)  # pylint: disable=no-member
    
    result = query.update(data).execute()  # pylint: disable=no-member
    return result.data

def delete_record(table, filters):
    """Delete records from a Supabase table."""
    client = supabase_client.get_db()
    query = client.table(table)  # pylint: disable=no-member
    
    for field, operator, value in filters:
        if operator == 'eq':
            query = query.eq(field, value)  # pylint: disable=no-member
    
    result = query.delete().execute()  # pylint: disable=no-member
    return result.data


def group_modules_by_year(modules):
    """Group modules by academic year for UI purposes."""
    grouped = defaultdict(list)

    for module in modules:
        raw_year = module.get('year') if isinstance(module, dict) else None
        year_value = None

        if isinstance(raw_year, int):
            year_value = raw_year
        elif isinstance(raw_year, str):
            try:
                year_value = int(raw_year)
            except ValueError:
                year_value = None

        key = ('year', year_value) if year_value is not None else ('other', None)

        # Ensure module has consistent dict structure
        if not isinstance(module, dict):
            module = {'name': str(module), 'id': None, 'year': None}
        else:
            module = {
                'id': module.get('id'   ),
                'name': module.get('name'),
                'year': year_value if year_value is not None else None
            }

        grouped[key].append(module)

    groups = []
    for key, items in grouped.items():
        group_type, year_value = key
        items.sort(key=lambda x: (x.get('name') or '').lower())

        if group_type == 'year' and year_value is not None:
            label = f"Year {year_value}"
            display_key = f"year-{year_value}"
        else:
            label = 'Other Modules'
            display_key = 'other'

        groups.append({
            'key': display_key,
            'label': label,
            'year': year_value,
            'modules': items
        })

    # Sort groups: numbered years ascending, "Other" last
    groups.sort(key=lambda g: (g['year'] is None, g['year'] if g['year'] is not None else float('inf')))
    return groups