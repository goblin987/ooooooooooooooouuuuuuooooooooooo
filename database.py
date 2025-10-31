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
            
            # Run migrations for existing databases
            self._run_migrations(conn)
            
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
        
        # Groups table - for recurring messages group registration
        conn.execute('''
            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER UNIQUE NOT NULL,
                title TEXT,
                registered_by INTEGER,
                registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Warnings table - for warn system
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
                reset_at TIMESTAMP,
                is_active INTEGER DEFAULT 1
            )
        ''')
        
        # Game statistics table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS game_stats (
                user_id INTEGER PRIMARY KEY,
                games_played INTEGER DEFAULT 0,
                games_won INTEGER DEFAULT 0,
                total_wagered REAL DEFAULT 0.0,
                biggest_win REAL DEFAULT 0.0,
                biggest_loss REAL DEFAULT 0.0,
                current_streak INTEGER DEFAULT 0,
                dice_played INTEGER DEFAULT 0,
                dice_won INTEGER DEFAULT 0,
                basketball_played INTEGER DEFAULT 0,
                basketball_won INTEGER DEFAULT 0,
                football_played INTEGER DEFAULT 0,
                football_won INTEGER DEFAULT 0,
                bowling_played INTEGER DEFAULT 0,
                bowling_won INTEGER DEFAULT 0,
                last_game_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Barygos auto-post settings table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS barygos_auto_settings (
                id INTEGER PRIMARY KEY,
                enabled INTEGER DEFAULT 0,
                interval_hours INTEGER DEFAULT 2,
                target_groups TEXT,
                voting_group_link TEXT,
                last_sent TIMESTAMP
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
            "CREATE INDEX IF NOT EXISTS idx_pending_bans_chat_id ON pending_bans(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_groups_chat_id ON groups(chat_id)",
            "CREATE INDEX IF NOT EXISTS idx_warnings_user_id ON warnings(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_warnings_chat_id ON warnings(chat_id)"
        ]
        
        for index_sql in indexes:
            try:
                conn.execute(index_sql)
            except sqlite3.OperationalError as e:
                if "already exists" not in str(e).lower():
                    logger.warning(f"Error creating index: {e}")
    
    def _run_migrations(self, conn):
        """Run database migrations for existing databases"""
        try:
            # Migration 1: Add is_active column to warnings table if it doesn't exist
            cursor = conn.execute("PRAGMA table_info(warnings)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'is_active' not in columns:
                logger.info("Running migration: Adding is_active column to warnings table")
                conn.execute("ALTER TABLE warnings ADD COLUMN is_active INTEGER DEFAULT 1")
                logger.info("✅ Migration completed: is_active column added")
            
            # Migration 2: Add permissions column to helpers table
            cursor = conn.execute("PRAGMA table_info(helpers)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'permissions' not in columns:
                logger.info("Running migration: Adding permissions column to helpers table")
                # Default permissions: can_ban, can_mute, can_warn, can_delete
                # Stored as comma-separated string: "ban,mute,warn,delete"
                conn.execute("ALTER TABLE helpers ADD COLUMN permissions TEXT DEFAULT 'ban,mute,warn,delete'")
                logger.info("✅ Migration completed: permissions column added to helpers")
        except Exception as e:
            logger.error(f"Migration error: {e}")
            # Don't raise - let app continue if migration fails
    
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
        """Get user info by username (case-insensitive)"""
        try:
            conn = self.get_sync_connection()
            try:
                cursor = conn.execute(
                    "SELECT * FROM user_cache WHERE LOWER(username) = LOWER(?) ORDER BY last_seen DESC LIMIT 1",
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
    
    # Groups methods (for recurring messages)
    def add_or_update_group(self, chat_id: int, title: str, registered_by: int):
        """Add or update group registration"""
        try:
            conn = self.get_sync_connection()
            try:
                conn.execute('''
                    INSERT OR REPLACE INTO groups 
                    (chat_id, title, registered_by, registered_at)
                    VALUES (?, ?, ?, datetime('now'))
                ''', (chat_id, title, registered_by))
                conn.commit()
                logger.info(f"Registered group: {title} (ID: {chat_id})")
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error adding/updating group: {e}")
    
    def get_all_groups(self) -> List[Dict]:
        """Get all registered groups"""
        try:
            conn = self.get_sync_connection()
            try:
                cursor = conn.execute(
                    "SELECT * FROM groups ORDER BY registered_at DESC"
                )
                return [dict(row) for row in cursor.fetchall()]
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error getting groups: {e}")
            return []
    
    def list_groups_for_user(self, user_id: int) -> List[Dict]:
        """Get groups registered by a specific user (optional filtering)"""
        # For now, return all groups - admin check will be done at runtime
        return self.get_all_groups()
    
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
    
    # Game Statistics Methods
    def record_game_result(self, user_id: int, game_type: str, won: bool, bet_amount: float, prize: float = 0):
        """Record game result and update statistics"""
        try:
            conn = self.get_sync_connection()
            try:
                # Get current stats
                cursor = conn.execute(
                    "SELECT * FROM game_stats WHERE user_id = ?",
                    (user_id,)
                )
                stats = cursor.fetchone()
                
                if stats:
                    stats = dict(stats)
                    games_played = stats['games_played'] + 1
                    games_won = stats['games_won'] + (1 if won else 0)
                    total_wagered = stats['total_wagered'] + bet_amount
                    
                    # Update streak
                    if won:
                        current_streak = stats['current_streak'] + 1 if stats['current_streak'] >= 0 else 1
                    else:
                        current_streak = stats['current_streak'] - 1 if stats['current_streak'] <= 0 else -1
                    
                    # Update biggest win/loss
                    profit = prize - bet_amount
                    biggest_win = max(stats['biggest_win'], profit) if won else stats['biggest_win']
                    biggest_loss = min(stats['biggest_loss'], profit) if not won else stats['biggest_loss']
                    
                    # Update game-specific stats
                    game_field = f"{game_type}_played"
                    won_field = f"{game_type}_won"
                    game_played = stats[game_field] + 1
                    game_won = stats[won_field] + (1 if won else 0)
                    
                    conn.execute(f'''
                        UPDATE game_stats SET 
                            games_played = ?,
                            games_won = ?,
                            total_wagered = ?,
                            biggest_win = ?,
                            biggest_loss = ?,
                            current_streak = ?,
                            {game_field} = ?,
                            {won_field} = ?,
                            last_game_timestamp = CURRENT_TIMESTAMP
                        WHERE user_id = ?
                    ''', (games_played, games_won, total_wagered, biggest_win, biggest_loss, 
                          current_streak, game_played, game_won, user_id))
                else:
                    # Create new stats
                    profit = prize - bet_amount
                    conn.execute(f'''
                        INSERT INTO game_stats (
                            user_id, games_played, games_won, total_wagered,
                            biggest_win, biggest_loss, current_streak,
                            {game_type}_played, {game_type}_won
                        ) VALUES (?, 1, ?, ?, ?, ?, ?, 1, ?)
                    ''', (user_id, 1 if won else 0, bet_amount, 
                          profit if won else 0, profit if not won else 0,
                          1 if won else -1, 1 if won else 0))
                
                conn.commit()
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error recording game result: {e}")
    
    def get_user_stats(self, user_id: int) -> Optional[Dict]:
        """Get user game statistics"""
        try:
            conn = self.get_sync_connection()
            try:
                cursor = conn.execute(
                    "SELECT * FROM game_stats WHERE user_id = ?",
                    (user_id,)
                )
                row = cursor.fetchone()
                return dict(row) if row else None
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error getting user stats: {e}")
            return None
    
    def get_user_rank(self, user_id: int) -> int:
        """Get user's rank based on balance"""
        try:
            conn = self.get_sync_connection()
            try:
                cursor = conn.execute('''
                    SELECT COUNT(*) + 1 as rank
                    FROM users
                    WHERE balance > (SELECT balance FROM users WHERE user_id = ?)
                ''', (user_id,))
                result = cursor.fetchone()
                return result[0] if result else 0
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error getting user rank: {e}")
            return 0
    
    def get_barygos_auto_settings(self) -> Optional[Dict]:
        """Get barygos auto-post settings"""
        try:
            conn = self.get_sync_connection()
            try:
                cursor = conn.execute(
                    "SELECT * FROM barygos_auto_settings WHERE id = 1"
                )
                row = cursor.fetchone()
                if row:
                    return dict(row)
                else:
                    # Return default settings if none exist
                    return {
                        'id': 1,
                        'enabled': 0,
                        'interval_hours': 2,
                        'target_groups': '[]',
                        'last_sent': None
                    }
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error getting barygos auto settings: {e}")
            return None
    
    def update_barygos_auto_settings(self, enabled: int, interval_hours: int, target_groups: str, voting_group_link: str = ''):
        """Update barygos auto-post settings"""
        try:
            conn = self.get_sync_connection()
            try:
                conn.execute('''
                    INSERT OR REPLACE INTO barygos_auto_settings (id, enabled, interval_hours, target_groups, voting_group_link, last_sent)
                    VALUES (1, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ''', (enabled, interval_hours, target_groups, voting_group_link))
                conn.commit()
                logger.info(f"Updated barygos auto settings: enabled={enabled}, interval={interval_hours}h, groups={target_groups}, link={voting_group_link}")
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error updating barygos auto settings: {e}")
    
    def register_group(self, chat_id: int, title: str = None):
        """Register or update a group in the database"""
        try:
            conn = self.get_sync_connection()
            try:
                conn.execute('''
                    INSERT OR REPLACE INTO groups (chat_id, title, registered_at)
                    VALUES (?, ?, CURRENT_TIMESTAMP)
                ''', (chat_id, title or f'Group {chat_id}'))
                conn.commit()
                logger.debug(f"Registered group {chat_id}")
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error registering group: {e}")
    
    def get_all_groups(self):
        """Get all groups where bot is active (from multiple sources)"""
        groups_dict = {}
        
        try:
            conn = self.get_sync_connection()
            try:
                # Primary source: groups table
                try:
                    cursor = conn.execute('''
                        SELECT DISTINCT chat_id, title
                        FROM groups
                        WHERE chat_id < 0
                        ORDER BY registered_at DESC
                    ''')
                    rows = cursor.fetchall()
                    for row in rows:
                        groups_dict[row[0]] = row[1] or f'Group {row[0]}'
                except Exception as e:
                    logger.debug(f"Could not get groups from groups table: {e}")
                
                # Fallback: recurring_messages
                try:
                    cursor = conn.execute('''
                        SELECT DISTINCT chat_id
                        FROM recurring_messages
                        WHERE chat_id < 0 AND status = 'active'
                    ''')
                    rows = cursor.fetchall()
                    for row in rows:
                        if row[0] not in groups_dict:
                            groups_dict[row[0]] = f'Group {row[0]}'
                except:
                    pass  # Table might not exist yet
                
                # Fallback: game_stats (groups where games were played)
                try:
                    cursor = conn.execute('''
                        SELECT DISTINCT group_chat_id
                        FROM game_stats
                        WHERE group_chat_id < 0
                    ''')
                    rows = cursor.fetchall()
                    for row in rows:
                        if row[0] not in groups_dict:
                            groups_dict[row[0]] = f'Group {row[0]}'
                except:
                    pass  # Table might not exist yet
                
                # If we still have no groups, return empty list
                result = [{'chat_id': chat_id, 'title': title} for chat_id, title in groups_dict.items()]
                return sorted(result, key=lambda x: x['chat_id'])
                
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error getting all groups: {e}")
            return []
    
    def has_helper_permission(self, chat_id: int, user_id: int, permission: str) -> bool:
        """
        Check if a helper has a specific permission in a chat
        
        Args:
            chat_id: The chat ID
            user_id: The user ID to check
            permission: One of: 'ban', 'mute', 'warn', 'delete'
        
        Returns:
            True if user has the permission, False otherwise
        """
        try:
            conn = self.get_sync_connection()
            try:
                cursor = conn.execute(
                    "SELECT permissions FROM helpers WHERE chat_id = ? AND user_id = ?",
                    (chat_id, user_id)
                )
                row = cursor.fetchone()
                
                if not row:
                    return False  # Not a helper
                
                permissions = row[0] if row[0] else ""
                # Check if the permission is in the comma-separated list
                return permission in permissions.split(',')
                
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error checking helper permission: {e}")
            return False

# Global database instance
database = Database()
