#!/usr/bin/env python3
"""
Migration script to add CASCADE DELETE for distractor tables.
When a question is deleted, all associated distractors (both manual and submitted) will be automatically deleted.
"""

import sqlite3
import os
import shutil
from datetime import datetime

def backup_database(db_path):
    """Create a backup of the database before migration"""
    backup_path = f"{db_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(db_path, backup_path)
    print(f"Database backed up to: {backup_path}")
    return backup_path

def migrate_distractor_tables(db_path):
    """Add CASCADE DELETE to distractor tables"""
    print(f"Starting migration for: {db_path}")
    
    # Create backup
    backup_path = backup_database(db_path)
    
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA foreign_keys = OFF")
        
        # Start transaction
        conn.execute("BEGIN TRANSACTION")
        
        # 1. Migrate manual_distractors table
        print("Migrating manual_distractors table...")
        
        # Create new table with CASCADE DELETE
        conn.execute("""
            CREATE TABLE manual_distractors_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id TEXT NOT NULL,
                distractor_text TEXT NOT NULL,
                created_by TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE,
                FOREIGN KEY (created_by) REFERENCES user_stats (user_id)
            )
        """)
        
        # Copy data from old table
        conn.execute("""
            INSERT INTO manual_distractors_new 
            SELECT id, question_id, distractor_text, created_by, created_at 
            FROM manual_distractors
        """)
        
        # Drop old table and rename new one
        conn.execute("DROP TABLE manual_distractors")
        conn.execute("ALTER TABLE manual_distractors_new RENAME TO manual_distractors")
        
        # Recreate index
        conn.execute("CREATE INDEX IF NOT EXISTS idx_manual_distractors_question_id ON manual_distractors (question_id)")
        
        # 2. Migrate submitted_distractors table
        print("Migrating submitted_distractors table...")
        
        # Create new table with CASCADE DELETE
        conn.execute("""
            CREATE TABLE submitted_distractors_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                username TEXT,
                question_id TEXT NOT NULL,
                distractor_text TEXT NOT NULL,
                timestamp INTEGER NOT NULL,
                FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE
            )
        """)
        
        # Copy data from old table
        conn.execute("""
            INSERT INTO submitted_distractors_new 
            SELECT id, user_id, username, question_id, distractor_text, timestamp 
            FROM submitted_distractors
        """)
        
        # Drop old table and rename new one
        conn.execute("DROP TABLE submitted_distractors")
        conn.execute("ALTER TABLE submitted_distractors_new RENAME TO submitted_distractors")
        
        # Recreate index
        conn.execute("CREATE INDEX IF NOT EXISTS idx_submitted_distractors_timestamp ON submitted_distractors (timestamp)")
        
        # Commit transaction
        conn.execute("COMMIT")
        conn.execute("PRAGMA foreign_keys = ON")
        
        # Verify the changes
        print("Verifying migration...")
        cursor = conn.execute("PRAGMA table_info(manual_distractors)")
        print("manual_distractors columns:", [row[1] for row in cursor.fetchall()])
        
        cursor = conn.execute("PRAGMA foreign_key_list(manual_distractors)")
        fks = cursor.fetchall()
        print("manual_distractors foreign keys:")
        for fk in fks:
            print(f"  Column {fk[3]} -> {fk[2]}.{fk[4]} (ON DELETE: {fk[6]})")
        
        cursor = conn.execute("PRAGMA foreign_key_list(submitted_distractors)")
        fks = cursor.fetchall()
        print("submitted_distractors foreign keys:")
        for fk in fks:
            print(f"  Column {fk[3]} -> {fk[2]}.{fk[4]} (ON DELETE: {fk[6]})")
        
        conn.close()
        print("Migration completed successfully!")
        print(f"Backup saved at: {backup_path}")
        
    except Exception as e:
        print(f"Migration failed: {e}")
        print(f"Restoring from backup: {backup_path}")
        shutil.copy2(backup_path, db_path)
        raise

def main():
    """Main migration function"""
    # Get the database path
    db_path = "flashcards_normalized.db"
    
    if not os.path.exists(db_path):
        print(f"Database file not found: {db_path}")
        print("Please run this script from the project root directory.")
        return
    
    print("="*50)
    print("CASCADE DELETE Migration for Distractor Tables")
    print("="*50)
    print()
    print("This will modify the database to automatically delete")
    print("associated distractors when a question is deleted.")
    print()
    
    response = input("Do you want to proceed? (y/N): ").strip().lower()
    if response != 'y':
        print("Migration cancelled.")
        return
    
    migrate_distractor_tables(db_path)
    
    print()
    print("="*50)
    print("Migration completed! Distractors will now be automatically")
    print("deleted when their associated question is deleted.")
    print("="*50)

if __name__ == "__main__":
    main()
