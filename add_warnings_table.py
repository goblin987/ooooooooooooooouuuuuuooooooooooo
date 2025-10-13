#!/usr/bin/env python3
"""
Migration: Add warnings table to database
"""
import sqlite3
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate():
    """Add warnings table"""
    try:
        conn = sqlite3.connect('bot_data.db')
        
        # Create warnings table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                chat_id INTEGER NOT NULL,
                warned_by INTEGER NOT NULL,
                warned_by_username TEXT,
                reason TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active BOOLEAN DEFAULT 1,
                UNIQUE(id)
            )
        ''')
        
        # Create indexes
        conn.execute("CREATE INDEX IF NOT EXISTS idx_warnings_user_id ON warnings(user_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_warnings_chat_id ON warnings(chat_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_warnings_active ON warnings(is_active)")
        
        conn.commit()
        conn.close()
        
        logger.info("✅ Warnings table created successfully!")
        print("✅ Migration complete! Warnings table added.")
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    migrate()

