#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Database operations and models for OGbotas
"""

import sqlite3
import logging
import threading
from contextlib import asynccontextmanager
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
from config import DATABASE_PATH

logger = logging.getLogger(__name__)

class Database:
    """Centralized database management with connection pooling"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or str(DATABASE_PATH)
        self._connection_lock = threading.Lock()
        self._init_database()
    
    def _init_database(self):
        """Initialize database with all required tables"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            
            # Create all tables
            self._create_tables(conn)
            self._create_indexes(conn)
            
            conn.commit()
            logger.info("Database initialized successfully")
            
        except Exception as e:
            logger.error(f"Database initialization error: {e}")
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()
    
    def _create_tables(self, conn):
        """Create all database tables"""
        
        # User cache table for username resolution
        conn.execute('''
            CREATE TABLE IF NOT EXISTS user_cache (
                user_id INTEGER PRIMARY KEY,
                username TEXT UNIQUE,
                first_name TEXT,
                last_name TEXT,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, username)
            )
        ''')
        
        # Ban history table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS ban_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                chat_id INTEGER NOT NULL,
                banned_by INTEGER NOT NULL,
                banned_by_username TEXT,
                ban_reason TEXT,
                ban_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                unban_timestamp TIMESTAMP,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Scheduled messages table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS scheduled_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                message_text TEXT NOT NULL,
                message_media TEXT,
                message_buttons TEXT,
                message_type TEXT DEFAULT 'text',
                repetition_type TEXT DEFAULT '24h',
                interval_hours INTEGER DEFAULT 24,
                days_of_week TEXT,
                days_of_month TEXT,
                time_slots TEXT,
                start_date TEXT,
                end_date TEXT,
                pin_message BOOLEAN DEFAULT 0,
                delete_last_message BOOLEAN DEFAULT 0,
                scheduled_deletion_hours INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active',
                created_by INTEGER NOT NULL,
                created_by_username TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_sent TIMESTAMP,
                job_id TEXT,
                is_active BOOLEAN DEFAULT 0,
                last_message_id INTEGER
            )
        ''')
        
        # Banned words table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS banned_words (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                word TEXT NOT NULL,
                action TEXT DEFAULT 'warn',
                added_by INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, word)
            )
        ''')
        
        # Helpers table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS helpers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                added_by INTEGER NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, user_id)
            )
        ''')
        
        # Scammer reports table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS scammer_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reported_username TEXT NOT NULL,
                reported_user_id INTEGER,
                reporter_id INTEGER NOT NULL,
                report_reason TEXT,
                report_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                reviewed_by INTEGER,
                reviewed_at TIMESTAMP,
                review_notes TEXT
            )
        ''')
        
        # Users table - for points and crypto balance
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                points INTEGER DEFAULT 0,
                balance REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Pending bans table - for users to be banned when they join
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pending_bans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                username TEXT,
                chat_id INTEGER NOT NULL,
                banned_by INTEGER NOT NULL,
                banned_by_username TEXT,
                reason TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, chat_id)
            )
        ''')
    
    def _create_indexes(self, conn):
        """Create database indexes for performance"""
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_user_cache_username ON user_cache(username)",
            "CREATE INDEX IF NOT EXISTS idx_user_cache_last_seen ON user_cache(last_seen)",
            "CREATE INDEX IF NOT EXISTS idx_ban_history_user_id ON ban_history(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_ban_history_chat_id ON ban_history(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_ban_history_active ON ban_history(is_active)",
            "CREATE INDEX IF NOT EXISTS idx_scheduled_messages_chat_id ON scheduled_messages(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_scheduled_messages_status ON scheduled_messages(status)",
            "CREATE INDEX IF NOT EXISTS idx_banned_words_chat_id ON banned_words(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_helpers_chat_id ON helpers(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_helpers_user_id ON helpers(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_scammer_reports_status ON scammer_reports(status)",
            "CREATE INDEX IF NOT EXISTS idx_users_points ON users(points)",
            "CREATE INDEX IF NOT EXISTS idx_users_balance ON users(balance)",
            "CREATE INDEX IF NOT EXISTS idx_pending_bans_user_id ON pending_bans(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_pending_bans_chat_id ON pending_bans(chat_id)"
        ]
        
        for index_sql in indexes:
            try:
                conn.execute(index_sql)
            except sqlite3.OperationalError as e:
                if "already exists" not in str(e).lower():
                    logger.warning(f"Error creating index: {e}")
    
    @asynccontextmanager
    async def get_connection(self):
        """Get async database connection with proper cleanup"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database connection error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def get_sync_connection(self):
        """Get synchronous database connection"""
        with self._connection_lock:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA journal_mode = WAL")
            return conn
    
    # User cache methods
    def store_user_info(self, user_id: int, username: str, first_name: str = None, last_name: str = None):
        """Store user information in cache"""
        try:
            conn = self.get_sync_connection()
            try:
                conn.execute('''
                    INSERT OR REPLACE INTO user_cache 
                    (user_id, username, first_name, last_name, last_seen)
                    VALUES (?, ?, ?, ?, datetime('now'))
                ''', (user_id, username, first_name, last_name))
                conn.commit()
                logger.info(f"💾 USER CACHE: Stored @{username} (ID: {user_id}, name: {first_name} {last_name})")
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"❌ USER CACHE ERROR: Failed to store @{username} (ID: {user_id}): {e}", exc_info=True)
    
    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Get user info by username"""
        try:
            conn = self.get_sync_connection()
            try:
                cursor = conn.execute(
                    "SELECT * FROM user_cache WHERE username = ? ORDER BY last_seen DESC LIMIT 1",
                    (username,)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error getting user by username {username}: {e}")
            return None
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Get user info by user ID"""
        try:
            conn = self.get_sync_connection()
            try:
                cursor = conn.execute(
                    "SELECT * FROM user_cache WHERE user_id = ? ORDER BY last_seen DESC LIMIT 1",
                    (user_id,)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error getting user by ID {user_id}: {e}")
            return None
    
    # Pending bans methods
    def add_pending_ban(self, user_id: int, username: str, chat_id: int, banned_by: int, 
                       banned_by_username: str, reason: str = None):
        """Add user to pending ban list"""
        try:
            conn = self.get_sync_connection()
            try:
                conn.execute('''
                    INSERT OR REPLACE INTO pending_bans 
                    (user_id, username, chat_id, banned_by, banned_by_username, reason)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, username, chat_id, banned_by, banned_by_username, reason))
                conn.commit()
                logger.info(f"Added pending ban for {username} (ID: {user_id}) in chat {chat_id}")
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error adding pending ban: {e}")
    
    def is_pending_ban(self, user_id: int, chat_id: int) -> bool:
        """Check if user is in pending ban list"""
        try:
            conn = self.get_sync_connection()
            try:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM pending_bans WHERE user_id = ? AND chat_id = ?",
                    (user_id, chat_id)
                )
                count = cursor.fetchone()[0]
                return count > 0
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error checking pending ban: {e}")
            return False
    
    def get_pending_ban(self, user_id: int, chat_id: int):
        """Get pending ban details"""
        try:
            conn = self.get_sync_connection()
            try:
                cursor = conn.execute(
                    "SELECT * FROM pending_bans WHERE user_id = ? AND chat_id = ?",
                    (user_id, chat_id)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error getting pending ban: {e}")
            return None
    
    def remove_pending_ban(self, user_id: int, chat_id: int):
        """Remove user from pending ban list (after successful ban)"""
        try:
            conn = self.get_sync_connection()
            try:
                conn.execute(
                    "DELETE FROM pending_bans WHERE user_id = ? AND chat_id = ?",
                    (user_id, chat_id)
                )
                conn.commit()
                logger.info(f"Removed pending ban for user {user_id} in chat {chat_id}")
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error removing pending ban: {e}")
    
    # Ban history methods
    def add_ban_record(self, user_id: int, username: str, chat_id: int, banned_by: int, 
                      banned_by_username: str, reason: str = None):
        """Add ban record to history"""
        try:
            conn = self.get_sync_connection()
            try:
                conn.execute('''
                    INSERT INTO ban_history 
                    (user_id, username, chat_id, banned_by, banned_by_username, ban_reason)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, username, chat_id, banned_by, banned_by_username, reason))
                conn.commit()
                logger.info(f"Added ban record for {username} (ID: {user_id})")
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error adding ban record: {e}")
    
    def get_ban_history(self, user_id: int = None, username: str = None) -> List[Dict]:
        """Get ban history for user"""
        try:
            conn = self.get_sync_connection()
            try:
                if user_id:
                    cursor = conn.execute(
                        "SELECT * FROM ban_history WHERE user_id = ? ORDER BY ban_timestamp DESC",
                        (user_id,)
                    )
                elif username:
                    cursor = conn.execute(
                        "SELECT * FROM ban_history WHERE username = ? ORDER BY ban_timestamp DESC",
                        (username,)
                    )
                else:
                    return []
                
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error getting ban history: {e}")
            return []
    
    # Scheduled messages methods
    def add_scheduled_message(self, **kwargs) -> int:
        """Add scheduled message and return ID"""
        try:
            conn = self.get_sync_connection()
            try:
                cursor = conn.execute('''
                    INSERT INTO scheduled_messages 
                    (chat_id, message_text, message_media, message_buttons, message_type,
                     repetition_type, interval_hours, pin_message, delete_last_message,
                     created_by, created_by_username, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    kwargs.get('chat_id'),
                    kwargs.get('message_text', ''),
                    kwargs.get('message_media'),
                    kwargs.get('message_buttons'),
                    kwargs.get('message_type', 'text'),
                    kwargs.get('repetition_type', '24h'),
                    kwargs.get('interval_hours', 24),
                    kwargs.get('pin_message', False),
                    kwargs.get('delete_last_message', False),
                    kwargs.get('created_by'),
                    kwargs.get('created_by_username'),
                    kwargs.get('is_active', False)
                ))
                message_id = cursor.lastrowid
                conn.commit()
                logger.info(f"Added scheduled message ID: {message_id}")
                return message_id
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error adding scheduled message: {e}")
            return 0
    
    def get_scheduled_messages(self, chat_id: int) -> List[Dict]:
        """Get scheduled messages for chat"""
        try:
            conn = self.get_sync_connection()
            try:
                cursor = conn.execute(
                    "SELECT * FROM scheduled_messages WHERE chat_id = ? ORDER BY created_at DESC",
                    (chat_id,)
                )
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error getting scheduled messages: {e}")
            return []
    
    def update_scheduled_message(self, message_id: int, **kwargs):
        """Update scheduled message"""
        try:
            conn = self.get_sync_connection()
            try:
                # Build dynamic update query
                fields = []
                values = []
                for key, value in kwargs.items():
                    fields.append(f"{key} = ?")
                    values.append(value)
                
                if fields:
                    values.append(message_id)
                    query = f"UPDATE scheduled_messages SET {', '.join(fields)} WHERE id = ?"
                    conn.execute(query, values)
                    conn.commit()
                    logger.info(f"Updated scheduled message ID: {message_id}")
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error updating scheduled message: {e}")

# Global database instance
database = Database()
