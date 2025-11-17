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
        
        # Users table - for points (money), XP, level, and crypto balance
        conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                points INTEGER DEFAULT 0,
                xp INTEGER DEFAULT 0,
                level INTEGER DEFAULT 1,
                balance REAL DEFAULT 0.0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Migration: Add xp and level columns if they don't exist
        try:
            conn.execute('ALTER TABLE users ADD COLUMN xp INTEGER DEFAULT 0')
            logger.info("Added xp column to users table")
        except:
            pass  # Column already exists
        
        try:
            conn.execute('ALTER TABLE users ADD COLUMN level INTEGER DEFAULT 1')
            logger.info("Added level column to users table")
        except:
            pass  # Column already exists
        
        try:
            conn.execute('ALTER TABLE users ADD COLUMN total_messages INTEGER DEFAULT 0')
            logger.info("Added total_messages column to users table")
        except:
            pass  # Column already exists
        
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
        
        # Exchange system settings table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS exchange_settings (
                id INTEGER PRIMARY KEY DEFAULT 1,
                points_per_dollar INTEGER DEFAULT 2000,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_by INTEGER
            )
        ''')
        
        # Initialize default exchange rate if not exists
        conn.execute('''
            INSERT OR IGNORE INTO exchange_settings (id, points_per_dollar)
            VALUES (1, 2000)
        ''')
        
        # Daily message tracking for anti-spam
        conn.execute('''
            CREATE TABLE IF NOT EXISTS daily_message_stats (
                user_id INTEGER,
                date TEXT,
                messages_counted INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, date)
            )
        ''')
        
        # Recent messages for duplicate detection
        conn.execute('''
            CREATE TABLE IF NOT EXISTS recent_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                message_text TEXT,
                message_id INTEGER,
                chat_id INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                xp_awarded INTEGER DEFAULT 0
            )
        ''')
        
        # Point exchange history
        conn.execute('''
            CREATE TABLE IF NOT EXISTS point_exchanges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                points_spent INTEGER,
                usd_amount REAL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                week_number INTEGER
            )
        ''')
        
        # Solana payment tables
        conn.execute('''
            CREATE TABLE IF NOT EXISTS pending_sol_deposits (
                deposit_id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expected_sol_amount REAL NOT NULL,
                expected_usd_amount REAL NOT NULL,
                created_at TIMESTAMP NOT NULL,
                expires_at TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'pending',
                transaction_signature TEXT,
                confirmed_at TIMESTAMP,
                chat_id INTEGER,
                message_id INTEGER
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS withdrawal_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount_sol REAL NOT NULL,
                amount_usd REAL NOT NULL,
                destination_address TEXT NOT NULL,
                transaction_signature TEXT,
                status TEXT NOT NULL,
                created_at TIMESTAMP NOT NULL,
                completed_at TIMESTAMP,
                error_message TEXT
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS withdrawal_rate_limits (
                user_id INTEGER PRIMARY KEY,
                withdrawal_count INTEGER DEFAULT 0,
                last_reset TIMESTAMP NOT NULL
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
            "CREATE INDEX IF NOT EXISTS idx_warnings_chat_id ON warnings(chat_id)",
            # Solana payment indexes
            "CREATE INDEX IF NOT EXISTS idx_pending_sol_deposits_user_id ON pending_sol_deposits(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_pending_sol_deposits_status ON pending_sol_deposits(status)",
            "CREATE INDEX IF NOT EXISTS idx_withdrawal_history_user_id ON withdrawal_history(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_withdrawal_history_status ON withdrawal_history(status)"
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
            
            # Migration 3: Add chat_id and message_id to pending_sol_deposits
            cursor = conn.execute("PRAGMA table_info(pending_sol_deposits)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'chat_id' not in columns:
                logger.info("Running migration: Adding chat_id and message_id to pending_sol_deposits")
                conn.execute("ALTER TABLE pending_sol_deposits ADD COLUMN chat_id INTEGER")
                conn.execute("ALTER TABLE pending_sol_deposits ADD COLUMN message_id INTEGER")
                logger.info("✅ Migration completed: message tracking added to deposits")
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
                logger.debug(f"💾 USER CACHE: Stored @{username} (ID: {user_id}, name: {first_name} {last_name})")
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
    
    def get_exchange_rate(self) -> int:
        """Get current points per dollar exchange rate"""
        try:
            conn = self.get_sync_connection()
            try:
                cursor = conn.execute(
                    "SELECT points_per_dollar FROM exchange_settings WHERE id = 1"
                )
                row = cursor.fetchone()
                if row:
                    return row[0]
                else:
                    return 2000  # Default fallback
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error getting exchange rate: {e}")
            return 2000  # Default fallback
    
    def set_exchange_rate(self, points_per_dollar: int, admin_id: int):
        """Set exchange rate (points per dollar)"""
        try:
            conn = self.get_sync_connection()
            try:
                conn.execute('''
                    UPDATE exchange_settings 
                    SET points_per_dollar = ?, updated_at = CURRENT_TIMESTAMP, updated_by = ?
                    WHERE id = 1
                ''', (points_per_dollar, admin_id))
                conn.commit()
                logger.info(f"Exchange rate updated to {points_per_dollar} points/$1 by admin {admin_id}")
                return True
            finally:
                conn.close()
        except Exception as e:
            logger.error(f"Error setting exchange rate: {e}")
            return False
    
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
    # ============================================================================
    # ANTI-SPAM & EXCHANGE HELPER METHODS
    # ============================================================================
    
    def get_account_age_days(self, user_id: int) -> int:
        """Get user account age in days"""
        try:
            conn = self.get_sync_connection()
            cursor = conn.execute("SELECT created_at FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            conn.close()
            
            if result and result[0]:
                from datetime import datetime
                created = datetime.fromisoformat(result[0]) if isinstance(result[0], str) else result[0]
                return (datetime.now() - created).days
            return 0
        except Exception as e:
            logger.error(f"Error getting account age: {e}")
            return 0
    
    def get_daily_message_count(self, user_id: int, date_str: str) -> int:
        """Get message count for a specific day"""
        try:
            conn = self.get_sync_connection()
            cursor = conn.execute(
                "SELECT messages_counted FROM daily_message_stats WHERE user_id = ? AND date = ?",
                (user_id, date_str)
            )
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else 0
        except Exception as e:
            logger.error(f"Error getting daily count: {e}")
            return 0
    
    def increment_daily_count(self, user_id: int, date_str: str):
        """Increment daily message count"""
        try:
            conn = self.get_sync_connection()
            conn.execute("""
                INSERT INTO daily_message_stats (user_id, date, messages_counted)
                VALUES (?, ?, 1)
                ON CONFLICT(user_id, date) DO UPDATE SET messages_counted = messages_counted + 1
            """, (user_id, date_str))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error incrementing daily count: {e}")
    
    def is_duplicate_message(self, user_id: int, message_text: str) -> bool:
        """Check if message is duplicate within last 5 minutes"""
        try:
            from datetime import datetime, timedelta
            conn = self.get_sync_connection()
            five_min_ago = (datetime.now() - timedelta(minutes=5)).isoformat()
            
            cursor = conn.execute("""
                SELECT COUNT(*) FROM recent_messages 
                WHERE user_id = ? AND message_text = ? AND timestamp > ?
            """, (user_id, message_text, five_min_ago))
            result = cursor.fetchone()
            conn.close()
            
            return result[0] > 0 if result else False
        except Exception as e:
            logger.error(f"Error checking duplicate: {e}")
            return False
    
    def track_message(self, user_id: int, message_id: int, chat_id: int, message_text: str, xp_awarded: int):
        """Track message for deletion penalty"""
        try:
            conn = self.get_sync_connection()
            conn.execute("""
                INSERT INTO recent_messages (user_id, message_text, message_id, chat_id, xp_awarded)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, message_text, message_id, chat_id, xp_awarded))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error tracking message: {e}")
    
    def cleanup_old_messages(self):
        """Delete messages older than 10 minutes"""
        try:
            from datetime import datetime, timedelta
            conn = self.get_sync_connection()
            ten_min_ago = (datetime.now() - timedelta(minutes=10)).isoformat()
            conn.execute("DELETE FROM recent_messages WHERE timestamp < ?", (ten_min_ago,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error cleanup old messages: {e}")
    
    def get_weekly_exchange_total(self, user_id: int, week_number: int) -> float:
        """Get total USD exchanged this week"""
        try:
            conn = self.get_sync_connection()
            cursor = conn.execute("""
                SELECT SUM(usd_amount) FROM point_exchanges 
                WHERE user_id = ? AND week_number = ?
            """, (user_id, week_number))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result and result[0] else 0.0
        except Exception as e:
            logger.error(f"Error getting weekly exchange: {e}")
            return 0.0
    
    def process_point_exchange(self, user_id: int, points_spent: int, usd_amount: float, week_number: int) -> bool:
        """Process points→crypto exchange transaction with atomic safety"""
        conn = None
        try:
            conn = self.get_sync_connection()
            
            # Begin atomic transaction
            conn.execute("BEGIN IMMEDIATE TRANSACTION")
            
            # Lock row and read current balances
            cursor = conn.execute("""
                SELECT points, balance FROM users WHERE user_id = ?
            """, (user_id,))
            result = cursor.fetchone()
            
            if not result:
                logger.warning(f"User {user_id} not found in database")
                conn.execute("ROLLBACK")
                conn.close()
                return False
            
            current_points = result[0] if result[0] else 0
            current_balance = result[1] if result[1] else 0.0
            
            # Final validation inside transaction
            if current_points < points_spent:
                logger.warning(f"User {user_id} insufficient points: has {current_points}, needs {points_spent}")
                conn.execute("ROLLBACK")
                conn.close()
                return False
            
            # Calculate new balances
            new_points = current_points - points_spent
            new_balance = current_balance + usd_amount
            
            # Update balances atomically
            conn.execute("""
                UPDATE users SET points = ?, balance = ? WHERE user_id = ?
            """, (new_points, new_balance, user_id))
            
            # Record transaction
            conn.execute("""
                INSERT INTO point_exchanges (user_id, points_spent, usd_amount, week_number)
                VALUES (?, ?, ?, ?)
            """, (user_id, points_spent, usd_amount, week_number))
            
            # Commit transaction
            conn.execute("COMMIT")
            conn.close()
            
            logger.info(f"✅ Exchange SUCCESS: User {user_id} exchanged {points_spent} points for ${usd_amount:.2f} (new balances: {new_points} pts, ${new_balance:.2f})")
            return True
            
        except Exception as e:
            logger.error(f"❌ Exchange FAILED for user {user_id}: {e}")
            if conn:
                try:
                    conn.execute("ROLLBACK")
                    conn.close()
                except:
                    pass
            return False
    
    def get_user_balance(self, user_id: int) -> float:
        """Get user's crypto balance"""
        try:
            conn = self.get_sync_connection()
            cursor = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result and result[0] else 0.0
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return 0.0
    
    def get_total_messages(self, user_id: int) -> int:
        """Get user's total message count"""
        try:
            conn = self.get_sync_connection()
            cursor = conn.execute("SELECT total_messages FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result and result[0] else 0
        except Exception as e:
            logger.error(f"Error getting total messages: {e}")
            return 0
    
    def increment_total_messages(self, user_id: int):
        """Increment user's total message count"""
        try:
            conn = self.get_sync_connection()
            conn.execute("""
                INSERT INTO users (user_id, total_messages) VALUES (?, 1)
                ON CONFLICT(user_id) DO UPDATE SET total_messages = total_messages + 1
            """, (user_id,))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error incrementing messages: {e}")
    
    def update_user_level(self, user_id: int, new_level: int):
        """Update user's level"""
        try:
            conn = self.get_sync_connection()
            conn.execute("UPDATE users SET level = ? WHERE user_id = ?", (new_level, user_id))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error updating level: {e}")
    
    def get_user_level(self, user_id: int) -> int:
        """Get user's current level"""
        try:
            conn = self.get_sync_connection()
            cursor = conn.execute("SELECT level FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            conn.close()
            return result[0] if result and result[0] else 1
        except Exception as e:
            logger.error(f"Error getting level: {e}")
            return 1
    
    def add_user_points(self, user_id: int, points_to_add: int):
        """Add points (money) to user balance"""
        try:
            conn = self.get_sync_connection()
            conn.execute("""
                INSERT INTO users (user_id, points) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET points = points + ?
            """, (user_id, points_to_add, points_to_add))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error adding points: {e}")
    
    def get_user_id_by_username(self, username: str) -> Optional[int]:
        """Get user ID from username using user_cache"""
        try:
            conn = self.get_sync_connection()
            cursor = conn.execute(
                "SELECT user_id FROM user_cache WHERE username = ? COLLATE NOCASE",
                (username.lstrip('@'),)
            )
            result = cursor.fetchone()
            conn.close()
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Error getting user ID for username {username}: {e}")
            return None


database = Database()
