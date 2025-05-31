import sqlite3
from config import Config

def get_db():
    """Get database connection with row factory."""
    db = sqlite3.connect(Config.DATABASE_PATH)
    db.row_factory = sqlite3.Row
    # Enable foreign key constraints
    db.execute('PRAGMA foreign_keys = ON')
    return db

def init_db():
    """Initialize database with schema."""
    from flask import current_app
    
    with current_app.app_context():
        db = get_db()
        # Execute schema.sql to create/update all tables
        with current_app.open_resource('schema.sql', mode='r') as f:
            db.cursor().executescript(f.read())
        db.commit()
        
        # Add current_streak column if missing
        try:
            db.execute('ALTER TABLE user_stats ADD COLUMN current_streak INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass  # Column already exists
        db.commit()

def get_all_modules():
    """Get all modules from database."""
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

def get_unique_values(key):
    """Get unique values for a given field."""
    db = get_db()
    if key == 'topic':
        rows = db.execute('SELECT DISTINCT name FROM topics').fetchall()
    elif key == 'subtopic':
        rows = db.execute('SELECT DISTINCT name FROM subtopics').fetchall()
    else:
        # Fallback for other columns if needed
        rows = db.execute(f'SELECT DISTINCT {key} FROM questions').fetchall()
    return sorted([row[0] for row in rows if row[0]])
