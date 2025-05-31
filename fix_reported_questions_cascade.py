#!/usr/bin/env python3
"""
Fix the reported_questions table to add ON DELETE CASCADE for question_id foreign key.
"""

import sqlite3
import shutil
from datetime import datetime

DATABASE_PATH = 'flashcards_normalized.db'

def backup_database():
    """Create a backup of the database before migration."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f'{DATABASE_PATH}.backup_{timestamp}'
    shutil.copy2(DATABASE_PATH, backup_path)
    print(f"Database backed up to: {backup_path}")
    return backup_path

def fix_reported_questions_cascade():
    """Fix the reported_questions table to add CASCADE DELETE."""
    
    # Create backup first
    backup_path = backup_database()
    
    # Connect to database
    conn = sqlite3.connect(DATABASE_PATH)
    conn.execute('PRAGMA foreign_keys = OFF')  # Disable foreign keys during migration
    
    try:
        cursor = conn.cursor()
        
        print("Starting migration to fix reported_questions CASCADE DELETE...")
        
        # Step 1: Create new table with correct foreign key constraints
        cursor.execute('''
            CREATE TABLE reported_questions_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                question TEXT NOT NULL,
                question_id TEXT,
                message TEXT,
                timestamp INTEGER,
                distractors TEXT,
                FOREIGN KEY (user_id) REFERENCES user_stats(user_id),
                FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE
            )
        ''')
        
        # Step 2: Copy data from old table to new table
        cursor.execute('''
            INSERT INTO reported_questions_new 
            SELECT * FROM reported_questions
        ''')
        
        # Step 3: Drop old table
        cursor.execute('DROP TABLE reported_questions')
        
        # Step 4: Rename new table to original name
        cursor.execute('ALTER TABLE reported_questions_new RENAME TO reported_questions')
        
        # Step 5: Re-enable foreign keys and test
        conn.execute('PRAGMA foreign_keys = ON')
        
        # Verify the foreign key constraints
        cursor.execute('PRAGMA foreign_key_check(reported_questions)')
        violations = cursor.fetchall()
        
        if violations:
            print(f"⚠️  Found foreign key violations: {violations}")
            raise Exception("Foreign key violations found")
        
        conn.commit()
        print("✅ Migration completed successfully!")
        print("reported_questions table now has ON DELETE CASCADE for question_id")
        
    except Exception as e:
        conn.rollback()
        print(f"❌ Migration failed: {e}")
        print(f"Database backup is available at: {backup_path}")
        raise
    
    finally:
        conn.close()

if __name__ == '__main__':
    fix_reported_questions_cascade()
