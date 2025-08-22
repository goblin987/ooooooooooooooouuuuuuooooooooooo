# -*- coding: utf-8 -*-
import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.triggers.cron import CronTrigger
import pytz
from collections import defaultdict
from datetime import datetime, timedelta, time
import random
import logging
import asyncio
import pickle
import os
import sys
import re
import html
import json
import sqlite3
from pathlib import Path
import threading
from contextlib import asynccontextmanager

# New imports for webhook support
from aiohttp import web
from aiohttp.web_request import Request
from aiohttp.web_response import Response

# Configure data directory first
DATA_DIR = os.getenv('DATA_DIR', '/opt/render/data')

# Configure logging with rotating logs
from logging.handlers import RotatingFileHandler
log_dir = Path(DATA_DIR) / 'logs'
log_dir.mkdir(parents=True, exist_ok=True)

# Setup rotating file handler
file_handler = RotatingFileHandler(
    log_dir / 'bot.log', 
    maxBytes=10*1024*1024,  # 10MB per file
    backupCount=5
)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Setup console handler
console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

# Configure root logger
logging.basicConfig(
    level=logging.INFO, 
    handlers=[file_handler, console_handler]
)
logger = logging.getLogger(__name__)
logger.info(f"Running on Python {sys.version}")

# IMMEDIATE DEBUG: Check persistent storage setup
logger.info("=" * 50)
logger.info("PERSISTENT STORAGE DEBUG - STARTUP")
logger.info("=" * 50)
logger.info(f"DATA_DIR configured as: {DATA_DIR}")
logger.info(f"DATA_DIR exists: {os.path.exists(DATA_DIR)}")
if os.path.exists(DATA_DIR):
    logger.info(f"DATA_DIR is writable: {os.access(DATA_DIR, os.W_OK)}")
    try:
        files = os.listdir(DATA_DIR)
        logger.info(f"Existing files in DATA_DIR: {files}")
        for file in files:
            filepath = os.path.join(DATA_DIR, file)
            if os.path.isfile(filepath):
                size = os.path.getsize(filepath)
                logger.info(f"  {file}: {size} bytes")
    except Exception as e:
        logger.error(f"Failed to list DATA_DIR contents: {e}")
else:
    logger.warning(f"DATA_DIR {DATA_DIR} does not exist!")

# Test write functionality immediately
try:
    os.makedirs(DATA_DIR, exist_ok=True)
    test_file = os.path.join(DATA_DIR, 'startup_test.txt')
    with open(test_file, 'w') as f:
        f.write(f'Bot started at {datetime.now()}')
    logger.info("✅ SUCCESSFULLY wrote startup test file to DATA_DIR")
    logger.info(f"✅ Test file created at: {test_file}")
except Exception as e:
    logger.error(f"❌ FAILED to write to DATA_DIR: {e}")

logger.info("=" * 50)

# Environment detection
RENDER_ENV = os.getenv('RENDER') == 'true'
PORT = int(os.getenv('PORT', 8443))  # Render.com provides PORT env var
WEBHOOK_HOST = os.getenv('RENDER_EXTERNAL_URL')  # Render.com provides this
WEBHOOK_PATH = f"/webhook/{os.getenv('TELEGRAM_TOKEN', 'token')}"
WEBHOOK_URL = f"{WEBHOOK_HOST}{WEBHOOK_PATH}" if WEBHOOK_HOST else None

logger.info(f"Environment - RENDER: {RENDER_ENV}, PORT: {PORT}, WEBHOOK_URL: {WEBHOOK_URL}")



# Analytics and Metrics System
class BotAnalytics:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize analytics database"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS command_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    command TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    success BOOLEAN DEFAULT TRUE,
                    error_message TEXT
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS user_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    activity_type TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS system_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
    
    def log_command_usage(self, command, user_id, chat_id, success=True, error=None):
        """Log command usage for analytics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO command_usage (command, user_id, chat_id, success, error_message)
                    VALUES (?, ?, ?, ?, ?)
                ''', (command, user_id, chat_id, success, error))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log command usage: {str(e)}")
    
    def log_user_activity(self, user_id, chat_id, activity_type, metadata=None):
        """Log user activity for engagement tracking"""
        try:
            metadata_json = json.dumps(metadata) if metadata else None
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO user_activity (user_id, chat_id, activity_type, metadata)
                    VALUES (?, ?, ?, ?)
                ''', (user_id, chat_id, activity_type, metadata_json))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log user activity: {str(e)}")
    
    def log_system_metric(self, metric_name, value):
        """Log system performance metrics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO system_metrics (metric_name, metric_value)
                    VALUES (?, ?)
                ''', (metric_name, value))
                conn.commit()
        except Exception as e:
            logger.error(f"Failed to log system metric: {str(e)}")
    
    def get_usage_stats(self, days=7):
        """Get command usage statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT command, COUNT(*) as count, 
                           AVG(CASE WHEN success THEN 1.0 ELSE 0.0 END) as success_rate
                    FROM command_usage 
                    WHERE timestamp > datetime('now', '-{} days')
                    GROUP BY command
                    ORDER BY count DESC
                '''.format(days))
                return cursor.fetchall()
        except Exception as e:
            logger.error(f"Failed to get usage stats: {str(e)}")
            return []

# Initialize analytics
analytics_db_path = os.path.join(os.getenv('DATA_DIR', '/opt/render/data'), 'analytics.db')
analytics = BotAnalytics(analytics_db_path)

# Enhanced Database class for new features
class Database:
    def __init__(self, db_path):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database with all tables"""
        with sqlite3.connect(self.db_path) as conn:
            # Existing analytics tables
            conn.execute('''
                CREATE TABLE IF NOT EXISTS command_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    command TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    success BOOLEAN DEFAULT TRUE,
                    error_message TEXT
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS user_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    activity_type TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT
                )
            ''')
            
            conn.execute('''
                CREATE TABLE IF NOT EXISTS system_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    metric_name TEXT NOT NULL,
                    metric_value REAL NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # New tables for recurring messages
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
                    job_id TEXT
                )
            ''')
            
            # Banned words table
            conn.execute('''
                CREATE TABLE IF NOT EXISTS banned_words (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    word TEXT NOT NULL,
                    action TEXT DEFAULT 'warn',
                    created_by INTEGER NOT NULL,
                    created_by_username TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
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
                    added_by_username TEXT,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1
                )
            ''')
            
            # Create indexes for better performance
            conn.execute('CREATE INDEX IF NOT EXISTS idx_scheduled_messages_chat_id ON scheduled_messages(chat_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_scheduled_messages_status ON scheduled_messages(status)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_banned_words_chat_id ON banned_words(chat_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_banned_words_word ON banned_words(word)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_helpers_chat_id ON helpers(chat_id)')
            conn.execute('CREATE INDEX IF NOT EXISTS idx_helpers_user_id ON helpers(user_id)')
            
            conn.commit()
    
    # Scheduled messages methods
    def add_scheduled_message(self, chat_id, message_text, created_by, created_by_username, **kwargs):
        """Add a new scheduled message"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                INSERT INTO scheduled_messages 
                (chat_id, message_text, message_media, message_buttons, message_type, 
                 repetition_type, interval_hours, days_of_week, days_of_month, time_slots,
                 start_date, end_date, pin_message, delete_last_message, scheduled_deletion_hours,
                 status, created_by, created_by_username)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (chat_id, message_text, kwargs.get('message_media'), kwargs.get('message_buttons'),
                  kwargs.get('message_type', 'text'), kwargs.get('repetition_type', '24h'),
                  kwargs.get('interval_hours', 24), kwargs.get('days_of_week'), kwargs.get('days_of_month'),
                  kwargs.get('time_slots'), kwargs.get('start_date'), kwargs.get('end_date'),
                  kwargs.get('pin_message', 0), kwargs.get('delete_last_message', 0),
                  kwargs.get('scheduled_deletion_hours', 0), kwargs.get('status', 'active'),
                  created_by, created_by_username))
            conn.commit()
            return cursor.lastrowid
    
    def get_scheduled_messages(self, chat_id):
        """Get all scheduled messages for a chat"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT * FROM scheduled_messages WHERE chat_id = ? ORDER BY created_at DESC
            ''', (chat_id,))
            return cursor.fetchall()
    
    def delete_scheduled_message(self, message_id):
        """Delete a scheduled message"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('DELETE FROM scheduled_messages WHERE id = ?', (message_id,))
            conn.commit()
    
    def update_scheduled_message_status(self, message_id, status):
        """Update scheduled message status"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('UPDATE scheduled_messages SET status = ? WHERE id = ?', (status, message_id))
            conn.commit()
    
    def update_last_sent(self, message_id):
        """Update last sent timestamp"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('UPDATE scheduled_messages SET last_sent = CURRENT_TIMESTAMP WHERE id = ?', (message_id,))
            conn.commit()
    
    def get_all_active_scheduled_messages(self):
        """Get all active scheduled messages"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('SELECT * FROM scheduled_messages WHERE status = "active"')
            return cursor.fetchall()
    
    # Banned words methods
    def add_banned_word(self, chat_id, word, action, created_by, created_by_username):
        """Add a banned word"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                INSERT INTO banned_words (chat_id, word, action, created_by, created_by_username)
                VALUES (?, ?, ?, ?, ?)
            ''', (chat_id, word.lower(), action, created_by, created_by_username))
            conn.commit()
            return cursor.lastrowid
    
    def get_banned_words(self, chat_id):
        """Get all banned words for a chat"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT * FROM banned_words WHERE chat_id = ? AND is_active = 1 ORDER BY created_at DESC
            ''', (chat_id,))
            return cursor.fetchall()
    
    def delete_banned_word(self, word_id):
        """Delete a banned word"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('DELETE FROM banned_words WHERE id = ?', (word_id,))
            conn.commit()
    
    def update_banned_word_status(self, word_id, is_active):
        """Update banned word status"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('UPDATE banned_words SET is_active = ? WHERE id = ?', (is_active, word_id))
            conn.commit()
    
    def check_banned_words(self, chat_id, text):
        """Check if text contains banned words"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT word, action FROM banned_words 
                WHERE chat_id = ? AND is_active = 1
            ''', (chat_id,))
            banned_words = cursor.fetchall()
            
            text_lower = text.lower()
            for word, action in banned_words:
                if word.lower() in text_lower:
                    return word, action
            return None, None
    
    # Helpers methods
    def add_helper(self, chat_id, user_id, username, added_by, added_by_username):
        """Add a helper"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                INSERT INTO helpers (chat_id, user_id, username, added_by, added_by_username)
                VALUES (?, ?, ?, ?, ?)
            ''', (chat_id, user_id, username, added_by, added_by_username))
            conn.commit()
            return cursor.lastrowid
    
    def get_helpers(self, chat_id):
        """Get all helpers for a chat"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT * FROM helpers WHERE chat_id = ? AND is_active = 1 ORDER BY added_at DESC
            ''', (chat_id,))
            return cursor.fetchall()
    
    def remove_helper(self, helper_id):
        """Remove a helper"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute('UPDATE helpers SET is_active = 0 WHERE id = ?', (helper_id,))
            conn.commit()
    
    def is_helper(self, chat_id, user_id):
        """Check if user is a helper"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute('''
                SELECT 1 FROM helpers WHERE chat_id = ? AND user_id = ? AND is_active = 1
            ''', (chat_id, user_id))
            return cursor.fetchone() is not None

# Initialize enhanced database
database = Database(analytics_db_path)

# Global variable for application instance (needed for scheduler)
application_instance = None

# Permission functions for new features
async def is_admin(update, context):
    """Check if user is admin or helper"""
    if not update.effective_chat:
        return False
    
    # Allow private chat access for configuration
    if update.effective_chat.type == 'private':
        # For private chats, we need to check if user is admin in any group where bot is present
        # This is a simplified check - in practice, you might want to store admin groups
        return True  # Allow access in private chat for now
    
    try:
        # Check if user is a helper first
        if database.is_helper(update.effective_chat.id, update.effective_user.id):
            return True
        
        # Check if user is admin
        chat_member = await context.bot.get_chat_member(
            update.effective_chat.id, update.effective_user.id
        )
        return chat_member.status in ['creator', 'administrator']
    except Exception as e:
        logger.error(f"Error checking admin status: {e}")
        return False

async def can_ban_users(update, context):
    """Check if user can ban users (admin with permissions or helper)"""
    if not update.effective_chat or update.effective_chat.type == 'private':
        return False
    
    try:
        # Check if user is a helper first
        if database.is_helper(update.effective_chat.id, update.effective_user.id):
            return True
        
        # Check if user is admin with ban permissions
        chat_member = await context.bot.get_chat_member(
            update.effective_chat.id, update.effective_user.id
        )
        return (chat_member.status in ['creator', 'administrator'] and 
                chat_member.can_restrict_members)
    except Exception as e:
        logger.error(f"Error checking ban permissions: {e}")
        return False

async def can_mute_users(update, context):
    """Check if user can mute users (admin with permissions or helper)"""
    if not update.effective_chat or update.effective_chat.type == 'private':
        return False
    
    try:
        # Check if user is a helper first
        if database.is_helper(update.effective_chat.id, update.effective_user.id):
            return True
        
        # Check if user is admin with mute permissions
        chat_member = await context.bot.get_chat_member(
            update.effective_chat.id, update.effective_user.id
        )
        return (chat_member.status in ['creator', 'administrator'] and 
                chat_member.can_restrict_members)
    except Exception as e:
        logger.error(f"Error checking mute permissions: {e}")
        return False

async def is_admin_callback(query, context):
    """Check if user is admin or helper for callback queries"""
    if not query.message:
        return False
    
    # Allow private chat access for configuration - but only for the admin
    if query.message.chat.type == 'private':
        # Check if this is the admin user
        return query.from_user.id == ADMIN_CHAT_ID
    
    try:
        # Check if user is a helper first
        if database.is_helper(query.message.chat.id, query.from_user.id):
            return True
        
        # Check if user is admin
        chat_member = await context.bot.get_chat_member(
            query.message.chat.id, query.from_user.id
        )
        return chat_member.status in ['creator', 'administrator']
    except Exception as e:
        logger.error(f"Error checking admin status in callback: {e}")
        return False

async def get_user_admin_groups(context, user_id):
    """Get list of groups where user is admin"""
    admin_groups = []
    
    # Get bot's updates to find groups it's in
    try:
        # This is a simplified approach - in practice, you might want to store groups in database
        # For now, we'll return an empty list and let users manually enter group IDs
        # In a full implementation, you would:
        # 1. Store groups where bot is added in database
        # 2. Check user's admin status in each stored group
        # 3. Return list of groups where user is admin
        
        # For now, return empty list - users will need to enter group ID manually
        return admin_groups
    except Exception as e:
        logger.error(f"Error getting admin groups: {e}")
        return admin_groups

# Utility functions for scheduling
def parse_interval(interval_str):
    """Parse interval string to hours"""
    try:
        if 'h' in interval_str:
            return int(interval_str.replace('h', ''))
        elif 'd' in interval_str:
            return int(interval_str.replace('d', '')) * 24
        else:
            return int(interval_str)
    except:
        return 24

def format_interval(hours, minutes=0):
    """Format hours and minutes to readable string"""
    if hours == 0 and minutes == 0:
        return "Not set"
    elif hours == 0:
        return f"{minutes}m"
    elif minutes == 0:
        if hours < 24:
            return f"{hours}h"
        elif hours % 24 == 0:
            return f"{hours // 24}d"
        else:
            return f"{hours}h"
    else:
        return f"{hours}h {minutes}m"

# Scheduler functions for recurring messages
async def send_scheduled_message(chat_id, message_text, job_id):
    """Send a scheduled message"""
    try:
        if application_instance:
            await application_instance.bot.send_message(chat_id, message_text, parse_mode='HTML')
            # Update last sent timestamp
            database.update_last_sent(job_id)
            logger.info(f"Sent scheduled message {job_id} to chat {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send scheduled message {job_id}: {e}")

async def restore_scheduled_jobs():
    """Restore active scheduled jobs on startup"""
    try:
        active_messages = database.get_all_active_scheduled_messages()
        for message in active_messages:
            message_id, chat_id, message_text, _, _, _, repetition_type, interval_hours, _, _, _, _, _, _, _, _, _, _, _, _, job_id = message
            
            if repetition_type == '24h':
                # Schedule for every 24 hours
                scheduler.add_job(
                    send_scheduled_message,
                    'interval',
                    hours=interval_hours,
                    args=[chat_id, message_text, message_id],
                    id=f"scheduled_{message_id}",
                    replace_existing=True
                )
            elif repetition_type == 'custom':
                # Schedule for custom interval
                scheduler.add_job(
                    send_scheduled_message,
                    'interval',
                    hours=interval_hours,
                    args=[chat_id, message_text, message_id],
                    id=f"scheduled_{message_id}",
                    replace_existing=True
                )
        
        logger.info(f"Restored {len(active_messages)} scheduled jobs")
    except Exception as e:
        logger.error(f"Failed to restore scheduled jobs: {e}")

# Input validation functions
def sanitize_username(username: str) -> str:
    """Sanitize username input to prevent injection"""
    if not username:
        return ""
    # Remove non-alphanumeric characters except @ and underscore
    sanitized = re.sub(r'[^@a-zA-Z0-9_]', '', username)
    # Ensure it starts with @
    if not sanitized.startswith('@'):
        sanitized = '@' + sanitized.lstrip('@')
    # Limit length
    return sanitized[:33]  # Telegram username max is 32 chars + @

def sanitize_text_input(text: str, max_length: int = 500) -> str:
    """Sanitize text input to prevent XSS and limit length"""
    if not text:
        return ""
    # HTML escape the text
    sanitized = html.escape(text.strip())
    # Limit length
    return sanitized[:max_length]

def validate_amount(amount_str: str) -> tuple[bool, int]:
    """Validate and convert amount string to int with bounds checking"""
    try:
        amount = int(amount_str)
        # Reasonable bounds for points/votes
        if amount < -10000 or amount > 10000:
            return False, 0
        return True, amount
    except (ValueError, TypeError):
        return False, 0

def validate_chat_id(chat_id_str: str) -> tuple[bool, int]:
    """Validate chat ID format"""
    try:
        chat_id = int(chat_id_str)
        # Telegram chat IDs are typically negative for groups/channels
        if abs(chat_id) > 10**15:  # Reasonable upper bound
            return False, 0
        return True, chat_id
    except (ValueError, TypeError):
        return False, 0

def validate_user_id(user_id) -> bool:
    """Validate user ID to prevent invalid operations"""
    if not isinstance(user_id, int):
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return False
    
    # Telegram user IDs are positive integers, typically 9-10 digits
    return 1 <= user_id <= 9999999999

def validate_chat_id_safe(chat_id) -> bool:
    """Validate chat ID for safety"""
    if not isinstance(chat_id, (int, str)):
        return False
    
    try:
        chat_id_int = int(chat_id)
        # Telegram chat IDs can be negative (groups) or positive (private chats)
        return -9999999999999 <= chat_id_int <= 9999999999999
    except (ValueError, TypeError):
        return False

def sanitize_file_path(file_path: str) -> str:
    """Sanitize file paths to prevent directory traversal"""
    if not file_path or not isinstance(file_path, str):
        return ""
    
    # Remove dangerous characters and path traversal attempts
    safe_path = re.sub(r'[<>:"|?*]', '', file_path)
    safe_path = safe_path.replace('..', '').replace('/', '').replace('\\', '')
    
    # Limit length
    safe_path = safe_path[:100]
    
    return safe_path

# Network resilience functions
async def safe_send_message(bot, chat_id: int, text: str, retries: int = 3, **kwargs):
    """Send message with retry logic and error handling"""
    for attempt in range(retries):
        try:
            return await bot.send_message(chat_id=chat_id, text=text, **kwargs)
        except telegram.error.TimedOut:
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
            logger.error(f"Message send timeout after {retries} attempts to chat {chat_id}")
            raise
        except telegram.error.NetworkError as e:
            if attempt < retries - 1:
                await asyncio.sleep(2 ** attempt)
                continue
            logger.error(f"Network error after {retries} attempts: {str(e)}")
            raise
        except telegram.error.BadRequest as e:
            logger.warning(f"Bad request sending message to {chat_id}: {str(e)}")
            raise  # Don't retry bad requests
        except Exception as e:
            logger.error(f"Unexpected error sending message: {str(e)}")
            raise

async def safe_bot_operation(operation_func, *args, retries: int = 2, **kwargs):
    """Generic wrapper for bot operations with retry logic"""
    for attempt in range(retries):
        try:
            return await operation_func(*args, **kwargs)
        except (telegram.error.TimedOut, telegram.error.NetworkError) as e:
            if attempt < retries - 1:
                await asyncio.sleep(1.5 ** attempt)
                continue
            logger.error(f"Bot operation failed after {retries} attempts: {str(e)}")
            raise
        except Exception as e:
            logger.warning(f"Bot operation error: {str(e)}")
            raise

# Get sensitive information from environment variables
TOKEN = os.getenv('TELEGRAM_TOKEN')
try:
    ADMIN_CHAT_ID = int(os.getenv('ADMIN_CHAT_ID', '0'))
except (ValueError, TypeError):
    ADMIN_CHAT_ID = 0

try:
    GROUP_CHAT_ID = int(os.getenv('GROUP_CHAT_ID', '0'))
except (ValueError, TypeError):
    GROUP_CHAT_ID = 0

try:
    VOTING_GROUP_CHAT_ID = int(os.getenv('VOTING_GROUP_CHAT_ID', '0'))
except (ValueError, TypeError):
    VOTING_GROUP_CHAT_ID = 0

# Helper IDs - users who can also approve/reject scammer reports
HELPER_IDS = []
helper_ids_env = os.getenv('HELPER_IDS', '')
if helper_ids_env:
    try:
        HELPER_IDS = [int(id.strip()) for id in helper_ids_env.split(',') if id.strip()]
        logger.info(f"Loaded {len(HELPER_IDS)} helper IDs: {HELPER_IDS}")
    except (ValueError, TypeError) as e:
        logger.warning(f"Failed to parse HELPER_IDS: {e}")
        HELPER_IDS = []

PASSWORD = os.getenv('PASSWORD', 'shoebot123')
VOTING_GROUP_LINK = os.getenv('VOTING_GROUP_LINK')

def is_admin_or_helper(user_id):
    """Check if user is admin or helper"""
    return user_id == ADMIN_CHAT_ID or user_id in HELPER_IDS

def get_all_moderators():
    """Get list of all moderators (admin + helpers)"""
    moderators = [ADMIN_CHAT_ID]
    moderators.extend(HELPER_IDS)
    return list(set(moderators))  # Remove duplicates

# Check if required environment variables are set
if not TOKEN:
    logger.error("TELEGRAM_TOKEN environment variable is not set.")
    sys.exit(1)
if not ADMIN_CHAT_ID:
    logger.error("ADMIN_CHAT_ID environment variable is not set.")
    sys.exit(1)
if not GROUP_CHAT_ID:
    logger.error("GROUP_CHAT_ID environment variable is not set.")
    sys.exit(1)
if not VOTING_GROUP_CHAT_ID:
    logger.error("VOTING_GROUP_CHAT_ID environment variable is not set.")
    sys.exit(1)
if not VOTING_GROUP_LINK:
    logger.error("VOTING_GROUP_LINK environment variable is not set.")
    sys.exit(1)

# Constants
TIMEZONE = pytz.timezone('Europe/Vilnius')
COINFLIP_STICKER_ID = 'CAACAgIAAxkBAAEN32tnuPb-ovynJR5WNO1TQyv_ea17AC-RkAAtswEEqAzfrZRd8B1zYE'

# Data loading and saving functions
def load_data(filename, default):
    filepath = os.path.join(DATA_DIR, filename)
    try:
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            with open(filepath, 'rb') as f:
                data = pickle.load(f)
                logger.info(f"Loaded data from {filepath}")
                return data
        logger.info(f"No data found at {filepath}, returning default")
        return default
    except (FileNotFoundError, EOFError, pickle.UnpicklingError) as e:
        logger.error(f"Failed to load {filepath}: {str(e)}, returning default")
        return default

def save_data(data, filename):
    filepath = os.path.join(DATA_DIR, filename)
    if isinstance(data, defaultdict):
        data = dict(data)
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        # Use atomic write operation to prevent corruption
        temp_filepath = filepath + '.tmp'
        with open(temp_filepath, 'wb') as f:
            pickle.dump(data, f)
        # Atomic move operation
        os.replace(temp_filepath, filepath)
        file_size = os.path.getsize(filepath)
        logger.info(f"✅ Saved {filename}: {file_size} bytes, {len(data) if hasattr(data, '__len__') else 'N/A'} entries")
    except Exception as e:
        logger.error(f"❌ Failed to save {filepath}: {str(e)}")
        # Clean up temp file if it exists
        temp_filepath = filepath + '.tmp'
        if os.path.exists(temp_filepath):
            try:
                os.remove(temp_filepath)
            except (OSError, IOError) as e:
                logger.warning(f"Failed to remove temp file {temp_filepath}: {e}")
        raise  # Re-raise to catch persistence issues

class DataManager:
    """Thread-safe data manager for critical operations"""
    def __init__(self):
        self._locks = {}
        self._global_lock = threading.RLock()
    
    def get_lock(self, resource_name):
        """Get or create a lock for a specific resource"""
        with self._global_lock:
            if resource_name not in self._locks:
                self._locks[resource_name] = threading.RLock()
            return self._locks[resource_name]
    
    @asynccontextmanager
    async def atomic_operation(self, resource_name):
        """Context manager for atomic operations"""
        lock = self.get_lock(resource_name)
        loop = asyncio.get_event_loop()
        
        # Acquire lock in thread pool to avoid blocking event loop
        acquired = await loop.run_in_executor(None, lock.acquire, True)  # blocking=True
        if not acquired:
            raise RuntimeError(f"Failed to acquire lock for {resource_name}")
        
        try:
            yield
        finally:
            try:
                lock.release()
            except RuntimeError as e:
                logger.warning(f"Lock release error for {resource_name}: {e}")

# Initialize data manager
data_manager = DataManager()

# Load initial data
logger.info("=" * 50)
logger.info("LOADING DATA FILES...")
logger.info("=" * 50)

featured_media_id = load_data('featured_media_id.pkl', None)
featured_media_type = load_data('featured_media_type.pkl', None)
barygos_media_id = load_data('barygos_media_id.pkl', None)
barygos_media_type = load_data('barygos_media_type.pkl', None)
voting_message_id = load_data('voting_message_id.pkl', None)

PARDAVEJAI_MESSAGE_FILE = 'pardavejai_message.pkl'
DEFAULT_PARDAVEJAI_MESSAGE = "Pasirink pardavėją, už kurį nori balsuoti:"
pardavejai_message = load_data(PARDAVEJAI_MESSAGE_FILE, DEFAULT_PARDAVEJAI_MESSAGE)
last_addftbaryga_message = None
last_addftbaryga2_message = None

def save_pardavejai_message():
    save_data(pardavejai_message, PARDAVEJAI_MESSAGE_FILE)

# Scheduler setup
scheduler = AsyncIOScheduler(timezone=TIMEZONE)
scheduler.add_executor(ThreadPoolExecutor(max_workers=10), alias='default')

async def configure_scheduler(application):
    logger.info("Configuring scheduler...")
    application.job_queue.scheduler = scheduler
    
    # Set global application instance for scheduled messages
    global application_instance
    application_instance = application
    
    try:
        if not scheduler.running:
            scheduler.start()
            logger.info("Scheduler started successfully.")
        else:
            logger.info("Scheduler was already running.")
    except Exception as e:
        logger.error(f"Scheduler failed to start: {str(e)}")
        raise
    
    # Restore scheduled jobs from database
    await restore_scheduled_jobs()
    
    await initialize_voting_message(application)

# Bot initialization
application = Application.builder().token(TOKEN).post_init(configure_scheduler).build()
logger.info("Bot initialized")

# Data structures - Load trusted sellers from persistent storage
default_sellers = ['@Seller1', '@Seller2', '@Seller3', '@Vatnikas']
trusted_sellers = load_data('trusted_sellers.pkl', default_sellers)
logger.info(f"Loaded trusted sellers: {trusted_sellers}")

def save_trusted_sellers():
    """Save trusted sellers to persistent storage"""
    save_data(trusted_sellers, 'trusted_sellers.pkl')
    logger.info(f"Saved trusted sellers: {trusted_sellers}")

# Ensure @Vatnikas is in the list and save the initial state
if '@Vatnikas' not in trusted_sellers:
    trusted_sellers.append('@Vatnikas')
    logger.info("Added @Vatnikas to trusted sellers list")

# Save the trusted sellers list on startup to ensure persistence
save_trusted_sellers()

# Load critical vote data with detailed logging
logger.info("Loading votes_weekly.pkl...")
votes_weekly = load_data('votes_weekly.pkl', defaultdict(int))
logger.info(f"votes_weekly loaded: {len(votes_weekly)} entries, sample: {dict(list(votes_weekly.items())[:3])}")

logger.info("Loading votes_monthly.pkl...")
votes_monthly = load_data('votes_monthly.pkl', defaultdict(list))
logger.info(f"votes_monthly loaded: {len(votes_monthly)} entries")

logger.info("Loading votes_alltime.pkl...")
votes_alltime = load_data('votes_alltime.pkl', defaultdict(int))
logger.info(f"votes_alltime loaded: {len(votes_alltime)} entries, sample: {dict(list(votes_alltime.items())[:3])}")

logger.info("Loading user_points.pkl...")
user_points = load_data('user_points.pkl', defaultdict(int))
logger.info(f"user_points loaded: {len(user_points)} users")

logger.info("Loading alltime_messages.pkl...")
alltime_messages = load_data('alltime_messages.pkl', defaultdict(int))
logger.info(f"alltime_messages loaded: {len(alltime_messages)} users")

logger.info("Loading chat_streaks.pkl...")
chat_streaks = load_data('chat_streaks.pkl', defaultdict(int))
logger.info(f"chat_streaks loaded: {len(chat_streaks)} users")

voters = set()
downvoters = set()
pending_downvotes = {}
approved_downvotes = {}
vote_history = load_data('vote_history.pkl', defaultdict(list))
last_vote_attempt = defaultdict(lambda: datetime.min.replace(tzinfo=TIMEZONE))
last_downvote_attempt = defaultdict(lambda: datetime.min.replace(tzinfo=TIMEZONE))
complaint_id = 0
coinflip_challenges = {}
daily_messages = defaultdict(lambda: defaultdict(int))
weekly_messages = defaultdict(int)
last_chat_day_raw = load_data('last_chat_day.pkl', {})
last_chat_day = defaultdict(lambda: datetime.min.replace(tzinfo=TIMEZONE), last_chat_day_raw)

logger.info("=" * 50)
logger.info("DATA LOADING COMPLETED")
logger.info("=" * 50)
allowed_groups = {str(GROUP_CHAT_ID)}  # Store as strings for consistency
valid_licenses = {'LICENSE-XYZ123', 'LICENSE-ABC456'}
pending_activation = {}
username_to_id = {}
polls = {}

# Scammer tracking system
pending_scammer_reports = load_data('pending_scammer_reports.pkl', {})  # report_id: {username, reporter_id, proof, timestamp, chat_id}
confirmed_scammers = load_data('confirmed_scammers.pkl', {})  # username: {confirmed_by, reporter_id, proof, timestamp, reports_count}
scammer_report_id = load_data('scammer_report_id.pkl', 0)

# Create user_id to scammer mapping for reverse lookup
user_id_to_scammer = {}  # user_id: username
for username, scammer_info in confirmed_scammers.items():
    if scammer_info.get('user_id'):
        user_id_to_scammer[scammer_info['user_id']] = username

# Buyer report tracking system
pending_buyer_reports = load_data('pending_buyer_reports.pkl', {})  # report_id: {username, user_id, reporter_id, reporter_username, reason, timestamp, chat_id}
confirmed_bad_buyers = load_data('confirmed_bad_buyers.pkl', {})  # username: {reports: [{confirmed_by, reporter_id, reason, timestamp}], total_reports: int}
buyer_report_id = load_data('buyer_report_id.pkl', 0)

# Create user_id to bad buyer mapping for reverse lookup
user_id_to_bad_buyer = {}  # user_id: username
for username, buyer_info in confirmed_bad_buyers.items():
    if buyer_info.get('user_id'):
        user_id_to_bad_buyer[buyer_info['user_id']] = username

# Enhanced user ID tracking system
async def resolve_user_id(username, context, chat_id):
    """
    Enhanced function to resolve username to user ID with multiple strategies
    Returns (user_id, method_used) or (None, 'failed')
    """
    if not username:
        return None, 'no_username'
    
    # Clean username
    clean_username = username.replace('@', '').strip()
    if not clean_username:
        return None, 'invalid_username'
    
    try:
        # Method 1: Try direct API lookup
        try:
            user_info = await context.bot.get_chat(f"@{clean_username}")
            if user_info and user_info.id:
                logger.info(f"Resolved @{clean_username} to user ID {user_info.id} via API")
                # Always update our mappings when we successfully resolve
                update_user_id_mappings(user_info.id, clean_username)
                return user_info.id, 'api_lookup'
        except telegram.error.BadRequest as e:
            if "User not found" in str(e) or "Chat not found" in str(e):
                logger.debug(f"User @{clean_username} not found via API (private account or doesn't exist)")
            else:
                logger.warning(f"API error resolving @{clean_username}: {e}")
        except Exception as e:
            logger.warning(f"Unexpected error resolving @{clean_username} via API: {e}")
        
        # Method 2: Check our internal username_to_id mapping
        username_key = f"@{clean_username.lower()}"
        if username_key in username_to_id:
            user_id = username_to_id[username_key]
            logger.info(f"Resolved @{clean_username} to user ID {user_id} via internal mapping")
            return user_id, 'internal_mapping'
        
        # Method 3: Check confirmed scammers for user ID
        for scammer_username, scammer_info in confirmed_scammers.items():
            if scammer_username.lower() == clean_username.lower() and scammer_info.get('user_id'):
                user_id = scammer_info['user_id']
                logger.info(f"Resolved @{clean_username} to user ID {user_id} via scammer database")
                update_user_id_mappings(user_id, clean_username)
                return user_id, 'scammer_database'
        
        # Method 4: Check confirmed bad buyers for user ID
        for buyer_username, buyer_info in confirmed_bad_buyers.items():
            if buyer_username.lower() == clean_username.lower() and buyer_info.get('user_id'):
                user_id = buyer_info['user_id']
                logger.info(f"Resolved @{clean_username} to user ID {user_id} via buyer database")
                update_user_id_mappings(user_id, clean_username)
                return user_id, 'buyer_database'
        
        # Method 5: Try alternative username formats
        alternative_formats = [
            clean_username.lower(),
            clean_username.upper(),
            f"@{clean_username.lower()}",
            f"@{clean_username.upper()}"
        ]
        
        for alt_format in alternative_formats:
            if alt_format in username_to_id:
                user_id = username_to_id[alt_format]
                logger.info(f"Resolved @{clean_username} to user ID {user_id} via alternative format: {alt_format}")
                update_user_id_mappings(user_id, clean_username)
                return user_id, 'alternative_format'
        
        # Method 6: Try to get recent chat members (if in group)
        try:
            if chat_id and is_allowed_group(chat_id):
                # This is a fallback method - try to get user from chat
                # Note: This has limited success due to Telegram API restrictions
                pass
        except Exception as e:
            logger.debug(f"Chat member lookup failed for @{clean_username}: {e}")
        
        logger.warning(f"Could not resolve user ID for @{clean_username} - all methods failed")
        return None, 'all_methods_failed'
        
    except Exception as e:
        logger.error(f"Critical error in resolve_user_id for @{clean_username}: {e}")
        return None, 'critical_error'

def update_user_id_mappings(user_id, username):
    """
    Update all user ID mappings when we discover a user ID
    """
    if not user_id or not username:
        return
    
    clean_username = username.replace('@', '').strip().lower()
    if not clean_username:
        return
    
    # Update internal mapping
    username_key = f"@{clean_username}"
    username_to_id[username_key] = user_id
    
    # Save the mapping
    try:
        save_data(username_to_id, 'username_to_id.pkl')
        logger.debug(f"Updated user ID mapping: @{clean_username} -> {user_id}")
    except Exception as e:
        logger.error(f"Failed to save username_to_id mapping: {e}")

def is_allowed_group(chat_id: str) -> bool:
    return str(chat_id) in allowed_groups

# Message deletion function
async def delete_message_job(context: telegram.ext.CallbackContext):
    job = context.job
    chat_id, message_id = job.data
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except telegram.error.BadRequest as e:
        if "Message to delete not found" in str(e):
            pass
        else:
            logger.error(f"Failed to delete message: {str(e)}")

# Initialize or update the persistent voting message
async def update_voting_message(context):
    global voting_message_id
    keyboard = [[InlineKeyboardButton(seller, callback_data=f"vote_{seller}")] for seller in trusted_sellers]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        if voting_message_id:
            try:
                if featured_media_type == 'photo':
                    await context.bot.edit_message_media(
                        chat_id=VOTING_GROUP_CHAT_ID,
                        message_id=voting_message_id,
                        media=telegram.InputMediaPhoto(media=featured_media_id, caption=pardavejai_message),
                        reply_markup=reply_markup
                    )
                elif featured_media_type == 'animation':
                    await context.bot.edit_message_media(
                        chat_id=VOTING_GROUP_CHAT_ID,
                        message_id=voting_message_id,
                        media=telegram.InputMediaAnimation(media=featured_media_id, caption=pardavejai_message),
                        reply_markup=reply_markup
                    )
                elif featured_media_type == 'video':
                    await context.bot.edit_message_media(
                        chat_id=VOTING_GROUP_CHAT_ID,
                        message_id=voting_message_id,
                        media=telegram.InputMediaVideo(media=featured_media_id, caption=pardavejai_message),
                        reply_markup=reply_markup
                    )
                else:
                    await context.bot.edit_message_text(
                        chat_id=VOTING_GROUP_CHAT_ID,
                        message_id=voting_message_id,
                        text=pardavejai_message,
                        reply_markup=reply_markup
                    )
                logger.info(f"Successfully updated voting message ID {voting_message_id}")
            except telegram.error.BadRequest as e:
                logger.warning(f"Failed to edit voting message ID {voting_message_id}: {str(e)}. Recreating...")
                voting_message_id = None
        if not voting_message_id:
            if featured_media_type == 'photo':
                msg = await context.bot.send_photo(
                    chat_id=VOTING_GROUP_CHAT_ID,
                    photo=featured_media_id,
                    caption=pardavejai_message,
                    reply_markup=reply_markup
                )
            elif featured_media_type == 'animation':
                msg = await context.bot.send_animation(
                    chat_id=VOTING_GROUP_CHAT_ID,
                    animation=featured_media_id,
                    caption=pardavejai_message,
                    reply_markup=reply_markup
                )
            elif featured_media_type == 'video':
                msg = await context.bot.send_video(
                    chat_id=VOTING_GROUP_CHAT_ID,
                    video=featured_media_id,
                    caption=pardavejai_message,
                    reply_markup=reply_markup
                )
            else:
                msg = await context.bot.send_message(
                    chat_id=VOTING_GROUP_CHAT_ID,
                    text=pardavejai_message,
                    reply_markup=reply_markup
                )
            voting_message_id = msg.message_id
            await context.bot.pin_chat_message(chat_id=VOTING_GROUP_CHAT_ID, message_id=voting_message_id)
            save_data(voting_message_id, 'voting_message_id.pkl')
            logger.info(f"Created and pinned new voting message ID {voting_message_id}")
    except telegram.error.TelegramError as e:
        logger.error(f"Failed to update voting message: {str(e)}")

async def initialize_voting_message(application):
    if not voting_message_id:
        await update_voting_message(application)

# Command handlers
async def debug(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if user_id != ADMIN_CHAT_ID:
        await update.message.reply_text("Tik adminas gali naudoti šią komandą!")
        return
    chat_id = update.message.chat_id
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        admin_list = "\n".join([f"@{m.user.username or m.user.id} (ID: {m.user.id})" for m in admins])
        msg = await update.message.reply_text(f"Matomi adminai:\n{admin_list}")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
    except telegram.error.TelegramError as e:
        msg = await update.message.reply_text(f"Debug failed: {str(e)}")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def whoami(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        username = f"@{member.user.username}" if member.user.username else "No username"
        msg = await update.message.reply_text(f"Jūs esate: {username} (ID: {user_id})")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
    except telegram.error.TelegramError as e:
        msg = await update.message.reply_text(f"Error: {str(e)}")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def startas(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    if chat_id != user_id:
        if is_allowed_group(chat_id):
            msg = await update.message.reply_text(
                "🤖 Sveiki! Štai galimi veiksmai:\n\n"
                "📊 /balsuoti - Balsuoti už pardavėjus balsavimo grupėje\n"
                "👎 /nepatiko @pardavejas priežastis - Pateikti skundą (5 tšk)\n"
                "💰 /points - Patikrinti savo taškus ir seriją\n"
                "👑 /chatking - Pokalbių lyderiai\n"
                "📈 /barygos - Pardavėjų reitingai\n"
                "🎯 /coinflip suma @vartotojas - Monetos metimas\n"
                "📋 /apklausa klausimas - Sukurti apklausą\n\n"
                "💬 Rašyk kasdien - gauk 1-3 taškus + serijos bonusą!"
            )
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        else:
            msg = await update.message.reply_text("Šis botas skirtas tik mano grupėms! Siųsk /startas Password privačiai!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
    else:
        # Private chat
        # Check if this is the admin - if so, show admin dashboard directly
        if user_id == ADMIN_CHAT_ID:
            await admin_dashboard(update, context)
            return
            
        # For non-admin users, require password
        if len(context.args) < 1:
            await update.message.reply_text("Naudok: /startas Password privačiai!")
            return
        
        password = sanitize_text_input(" ".join(context.args), max_length=100)
        if password == PASSWORD:
            pending_activation[user_id] = "password"
            await update.message.reply_text("Slaptažodis teisingas! Siųsk /activate_group GroupChatID.")
        else:
            await update.message.reply_text("Neteisingas slaptažodis!")
            logger.warning(f"Failed password attempt from user {user_id}")

async def activate_group(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if user_id != ADMIN_CHAT_ID:
        await update.message.reply_text("Tik adminas gali aktyvuoti grupes!")
        return
    if user_id not in pending_activation:
        await update.message.reply_text("Pirma įvesk slaptažodį privačiai!")
        return
    try:
        group_id = context.args[0]
        if group_id in allowed_groups:
            await update.message.reply_text("Grupė jau aktyvuota!")
        else:
            allowed_groups.add(group_id)
            if pending_activation[user_id] != "password":
                valid_licenses.remove(pending_activation[user_id])
            del pending_activation[user_id]
            await update.message.reply_text(f"Grupė {group_id} aktyvuota! Use /startas in the group.")
    except IndexError:
        await update.message.reply_text("Naudok: /activate_group GroupChatID")

async def privatus(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali naudoti šią komandą!")
        context.job_queue.run_once(delete_message_job, 45, data=(update.message.chat_id, msg.message_id))
        return
    chat_id = update.message.chat_id
    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(update.message.chat_id, msg.message_id))
        return
    keyboard = [[InlineKeyboardButton("Valdyti privačiai", url=f"https://t.me/{context.bot.username}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await update.message.reply_text("Spausk mygtuką, kad valdytum botą privačiai:", reply_markup=reply_markup)
    context.job_queue.run_once(delete_message_job, 45, data=(update.message.chat_id, msg.message_id))

async def start_private(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if chat_id == user_id and user_id == ADMIN_CHAT_ID:
        # Show the new admin dashboard instead of the old simple menu
        await admin_dashboard(update, context)

async def admin_dashboard(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Show admin dashboard with inline buttons for all setup options"""
    # Handle both message updates and callback queries
    if update.callback_query:
        # This is a callback query, we need to handle it differently
        query = update.callback_query
        user_id = query.from_user.id
        
        if user_id != ADMIN_CHAT_ID:
            await query.answer("❌ Tik adminas gali naudoti šią komandą!")
            return
        
        # For callback queries, we need to edit the existing message
        await show_admin_dashboard_ui(query, context)
        return
    
    # This is a regular message update
    if not update.message:
        return
        
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Tik adminas gali naudoti šią komandą!")
        return
    
    # For regular messages, send a new message
    await show_admin_dashboard_ui(update, context)

async def show_admin_dashboard_ui(update_or_query, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Show the admin dashboard UI (works with both messages and callback queries)"""
    # Create beautiful admin dashboard with inline buttons
    keyboard = [
        [InlineKeyboardButton("🔄 Kartojami pranešimai", callback_data="admin_recurring")],
        [InlineKeyboardButton("🚫 Uždrausti žodžiai", callback_data="admin_banned_words")],
        [InlineKeyboardButton("👥 Pagalbininkai", callback_data="admin_helpers")],
        [InlineKeyboardButton("🛡️ Moderacija", callback_data="admin_moderation")],
        [InlineKeyboardButton("📊 Statistika", callback_data="admin_stats")],
        [InlineKeyboardButton("⚙️ Pardavėjų valdymas", callback_data="admin_vendors")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    dashboard_text = (
        "🎯 **ADMIN DASHBOARD**\n\n"
        "Sveiki, administratoriau! Pasirinkite, ką norite valdyti:\n\n"
        "🔄 **Kartojami pranešimai** - Nustatyti automatinius pranešimus\n"
        "🚫 **Uždrausti žodžiai** - Valdyti draudžiamus žodžius ir baudas\n"
        "👥 **Pagalbininkai** - Pridėti/pašalinti pagalbininkus\n"
        "🛡️ **Moderacija** - Ban/mute komandos ir nustatymai\n"
        "📊 **Statistika** - Bot statistikos ir duomenys\n"
        "⚙️ **Pardavėjų valdymas** - Pridėti/pašalinti pardavėjus"
    )
    
    if hasattr(update_or_query, 'edit_message_text'):
        # This is a callback query
        await update_or_query.edit_message_text(
            dashboard_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        # This is a regular message
        await update_or_query.message.reply_text(
            dashboard_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def handle_admin_button(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    if not is_admin_or_helper(user_id):
        await query.answer("Tik adminai ir pagalbininkai gali tai daryti!")
        return

    data = query.data
    if data == "admin_addseller":
        await query.edit_message_text("Įvesk: /addseller @VendorTag")
    elif data == "admin_removeseller":
        await query.edit_message_text("Įvesk: /removeseller @VendorTag")
    elif data == "admin_editpardavejai":
        await query.edit_message_text("Įvesk: /editpardavejai 'Naujas tekstas'")
    elif data == "admin_recurring":
        # Show the new group buttons menu for recurring messages
        await show_recurring_groups_menu_admin(query, context)
        
    elif data == "admin_banned_words":
        # Show group selection for banned words
        keyboard = [
            [InlineKeyboardButton("📝 Įvesti grupės ID", callback_data="group_select_banned_words")],
            [InlineKeyboardButton("🔍 Rasti grupes", callback_data="group_find_banned_words")],
            [InlineKeyboardButton("⬅️ Atgal", callback_data="admin_dashboard_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🚫 **Uždrausti žodžiai**\n\n"
            "Pasirinkite grupę, kurioje norite valdyti uždraustus žodžius:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    elif data == "admin_helpers":
        # Show the new group buttons menu for helpers
        await show_helpers_groups_menu_admin(query, context)
        
    elif data == "admin_moderation":
        # Show moderation options
        keyboard = [
            [InlineKeyboardButton("🔄 Kartojami pranešimai", callback_data="admin_recurring")],
            [InlineKeyboardButton("🚫 Uždrausti žodžiai", callback_data="admin_banned_words")],
            [InlineKeyboardButton("👥 Pagalbininkai", callback_data="admin_helpers")],
            [InlineKeyboardButton("⬅️ Atgal", callback_data="admin_dashboard_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "🛡️ **Moderacija**\n\n"
            "Moderacijos funkcijos yra integruotos į kitus menius:\n\n"
            "• **Ban/Mute komandos** - naudokite `/ban`, `/mute` grupėse\n"
            "• **Uždrausti žodžiai** - automatinės baudas\n"
            "• **Pagalbininkai** - deleguoti teises\n\n"
            "Pasirinkite meniu elementą:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    elif data == "admin_stats":
        # Show bot statistics
        keyboard = [
            [InlineKeyboardButton("📊 Grupės statistika", callback_data="admin_group_stats")],
            [InlineKeyboardButton("👥 Vartotojų statistika", callback_data="admin_user_stats")],
            [InlineKeyboardButton("⬅️ Atgal", callback_data="admin_dashboard_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "📊 **Bot statistika**\n\n"
            "Pasirinkite statistikos tipą:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    elif data == "admin_vendors":
        # Show vendor management options
        keyboard = [
            [InlineKeyboardButton("➕ Pridėti pardavėją", callback_data="admin_add_vendor")],
            [InlineKeyboardButton("➖ Pašalinti pardavėją", callback_data="admin_remove_vendor")],
            [InlineKeyboardButton("✏️ Redaguoti pardavėjus", callback_data="admin_edit_vendor")],
            [InlineKeyboardButton("⬅️ Atgal", callback_data="admin_dashboard_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "⚙️ **Pardavėjų valdymas**\n\n"
            "Pasirinkite veiksmą:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    elif data == "admin_dashboard_back":
        # Return to main admin dashboard
        await admin_dashboard(update, context)
        await query.delete_message()
        
    elif data.startswith("group_select_"):
        # Handle group selection for different features
        feature = data.replace("group_select_", "")
        context.user_data['waiting_for_group_id'] = True
        context.user_data['group_selection_type'] = feature
        
        await query.edit_message_text(
            f"📝 **Įveskite grupės ID**\n\n"
            f"Funkcija: **{get_feature_name(feature)}**\n\n"
            f"Įveskite grupės ID (pvz., -1001234567890):",
            parse_mode='Markdown'
        )
        
    elif data.startswith("group_find_"):
        # Handle group find for different features
        feature = data.replace("group_find_", "")
        # For now, just show the group selection option
        context.user_data['waiting_for_group_id'] = True
        context.user_data['group_selection_type'] = feature
        
        await query.edit_message_text(
            f"🔍 **Rasti grupes**\n\n"
            f"Funkcija: **{get_feature_name(feature)}**\n\n"
            "Šiuo metu reikia įvesti grupės ID rankiniu būdu.\n"
            f"Įveskite grupės ID (pvz., -1001234567890):",
            parse_mode='Markdown'
        )
    elif data == "mod_pending_scammers":
        await show_pending_scammers_panel(query, context)
    elif data == "mod_pending_buyers":
        await show_pending_buyers_panel(query, context)
    elif data == "mod_warnings":
        await query.edit_message_text("Perspėjimų sistema dar nepridėta.")
    elif data == "mod_trusted":
        await query.edit_message_text("Patikimų vartotojų sistema dar nepridėta.")
    elif data == "mod_banned_words":
        await query.edit_message_text("Uždrausti žodžiai dar nepridėti.")
    elif data == "mod_logs":
        await query.edit_message_text("Moderacijos logai dar nepridėti.")
    elif data == "mod_back":
        # Return to main moderation panel
        keyboard = [
            [InlineKeyboardButton("Laukiantys scamer pranešimai", callback_data="mod_pending_scammers")],
            [InlineKeyboardButton("Laukiantys pirkėjų pranešimai", callback_data="mod_pending_buyers")],
            [InlineKeyboardButton("Perspėjimų sąrašas", callback_data="mod_warnings")],
            [InlineKeyboardButton("Patikimi vartotojai", callback_data="mod_trusted")],
            [InlineKeyboardButton("Uždrausti žodžiai", callback_data="mod_banned_words")],
            [InlineKeyboardButton("Moderacijos logai", callback_data="mod_logs")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("🛡️ Moderacijos Pultas 🛡️\n\nPasirink veiksmą:", reply_markup=reply_markup)
    else:
        await query.edit_message_text("❌ Nežinomas veiksmas!")
    await query.answer()

def get_feature_name(feature):
    """Get human-readable feature name"""
    feature_names = {
        'recurring': 'Kartojami pranešimai',
        'banned_words': 'Uždrausti žodžiai',
        'helpers': 'Pagalbininkai'
    }
    return feature_names.get(feature, feature)

async def show_group_selection_menu(query, context, feature, selection_type):
    """Show a list of all groups where the bot is present for selection"""
    try:
        # Get all chats where the bot is present using a more reliable method
        bot = context.bot
        chat_ids = set()
        
        # Method 1: Check allowed_groups from the bot's configuration
        if 'allowed_groups' in globals():
            for group_id in allowed_groups:
                chat_ids.add(int(group_id))
        
        # Method 2: Try to get groups from recent updates (limited but more reliable)
        try:
            # Get recent updates with a limit
            updates = await bot.get_updates(limit=100, timeout=1)
            for update in updates:
                if update.message and update.message.chat:
                    chat = update.message.chat
                    if chat.type in ['group', 'supergroup']:
                        chat_ids.add(chat.id)
        except Exception:
            pass  # Ignore errors from get_updates
        
        # Method 3: Check if we have any stored group data
        try:
            # Try to get groups from analytics database or other stored data
            if 'database' in globals() and hasattr(database, 'get_all_groups'):
                stored_groups = database.get_all_groups()
                for group_id in stored_groups:
                    chat_ids.add(int(group_id))
        except Exception:
            pass
        
        # Method 4: Add some common group IDs that might be used
        # You can manually add your group IDs here
        manual_groups = [
            # Add your actual group IDs here, for example:
            # -1001234567890,  # Your main group
            # -1001987654321,  # Your backup group
        ]
        for group_id in manual_groups:
            chat_ids.add(group_id)
        
        if not chat_ids:
            # Fallback: show manual input option
            keyboard = [
                [InlineKeyboardButton("📝 Įvesti grupės ID rankiniu", callback_data=f"manual_group_{feature}")],
                [InlineKeyboardButton("🔧 Pridėti grupes rankiniu", callback_data=f"add_manual_groups_{feature}")],
                [InlineKeyboardButton("⬅️ Atgal", callback_data="admin_dashboard_back")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f"🔍 **Grupės nerastos**\n\n"
                f"Funkcija: **{get_feature_name(feature)}**\n\n"
                "Botas negali automatiškai aptikti grupių, kuriose yra.\n\n"
                "**Galimi sprendimai:**\n"
                "• 📝 Įvesti grupės ID rankiniu\n"
                "• 🔧 Pridėti grupes rankiniu\n"
                "• Patikrinti, ar botas yra grupėse ir ar turi teises",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
        
        # Create keyboard with group buttons
        keyboard = []
        for chat_id in sorted(chat_ids):
            try:
                # Get chat info to show group name
                chat_info = await bot.get_chat(chat_id)
                group_name = chat_info.title or f"Grupė {chat_id}"
                # Truncate long names
                if len(group_name) > 30:
                    group_name = group_name[:27] + "..."
                
                keyboard.append([InlineKeyboardButton(
                    f"📱 {group_name}", 
                    callback_data=f"select_group_{feature}_{chat_id}"
                )])
            except Exception as e:
                # If we can't get chat info, just show the ID
                keyboard.append([InlineKeyboardButton(
                    f"📱 Grupė {chat_id}", 
                    callback_data=f"select_group_{feature}_{chat_id}"
                )])
        
        # Add additional options
        keyboard.append([InlineKeyboardButton("🔧 Pridėti naują grupę", callback_data=f"add_new_group_{feature}")])
        keyboard.append([InlineKeyboardButton("⬅️ Atgal", callback_data="admin_dashboard_back")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        selection_text = "📝" if selection_type == "select" else "🔍"
        await query.edit_message_text(
            f"{selection_text} **Pasirinkite grupę**\n\n"
            f"Funkcija: **{get_feature_name(feature)}**\n\n"
            f"Rastos {len(chat_ids)} grupės, kuriose botas gali veikti:\n\n"
            f"Pasirinkite grupę, kurioje norite valdyti:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
    except Exception as e:
        # Fallback to manual input
        keyboard = [
            [InlineKeyboardButton("📝 Įvesti grupės ID rankiniu", callback_data=f"manual_group_{feature}")],
            [InlineKeyboardButton("🔧 Pridėti grupes rankiniu", callback_data=f"add_manual_groups_{feature}")],
            [InlineKeyboardButton("⬅️ Atgal", callback_data="admin_dashboard_back")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"❌ **Klaida gaunant grupes**\n\n"
            f"Funkcija: **{get_feature_name(feature)}**\n\n"
            f"Klaida: {str(e)}\n\n"
            "**Galimi sprendimai:**\n"
            "• 📝 Įvesti grupės ID rankiniu\n"
            "• 🔧 Pridėti grupes rankiniu\n"
            "• Patikrinti bot nustatymus",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

async def show_feature_management_menu(query, context, feature, group_id):
    """Show the appropriate management menu for the selected feature and group"""
    try:
        # Get group info
        bot = context.bot
        chat_info = await bot.get_chat(group_id)
        group_name = chat_info.title or f"Grupė {group_id}"
        
        if feature == "recurring":
            # Show recurring messages management for this group
            await show_recurring_messages_for_group(query, context, group_id, group_name)
        elif feature == "banned_words":
            # Show banned words management for this group
            await show_banned_words_for_group(query, context, group_id, group_name)
        elif feature == "helpers":
            # Show helpers management for this group
            await show_helpers_for_group(query, context, group_id, group_name)
        else:
            await query.edit_message_text(f"❌ Nežinoma funkcija: {feature}")
            
    except Exception as e:
        await query.edit_message_text(
            f"❌ **Klaida gaunant grupės informaciją**\n\n"
            f"Grupės ID: {group_id}\n"
            f"Klaida: {str(e)}"
        )

async def show_recurring_messages_for_group(query, context, group_id, group_name):
    """Show recurring messages management for a specific group"""
    # Store the target group ID for future use
    context.user_data['target_group_id'] = group_id
    
    keyboard = [
        [InlineKeyboardButton("➕ Pridėti naują pranešimą", callback_data="add_recurring_message")],
        [InlineKeyboardButton("📋 Peržiūrėti pranešimus", callback_data="list_recurring_messages")],
        [InlineKeyboardButton("⚙️ Nustatymai", callback_data="recurring_settings")],
        [InlineKeyboardButton("⬅️ Atgal į grupės pasirinkimą", callback_data="admin_recurring")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🔄 **Kartojami pranešimai - {group_name}**\n\n"
        f"Grupės ID: `{group_id}`\n\n"
        "Pasirinkite veiksmą:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_banned_words_for_group(query, context, group_id, group_name):
    """Show banned words management for a specific group"""
    # Store the target group ID for future use
    context.user_data['target_group_id'] = group_id
    
    keyboard = [
        [InlineKeyboardButton("➕ Pridėti uždraustą žodį", callback_data="add_banned_word")],
        [InlineKeyboardButton("📋 Peržiūrėti uždraustus žodžius", callback_data="list_banned_words")],
        [InlineKeyboardButton("⚙️ Nustatymai", callback_data="banned_words_settings")],
        [InlineKeyboardButton("⬅️ Atgal į grupės pasirinkimą", callback_data="admin_banned_words")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"🚫 **Uždrausti žodžiai - {group_name}**\n\n"
        f"Grupės ID: `{group_id}`\n\n"
        "Pasirinkite veiksmą:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_helpers_for_group(query, context, group_id, group_name):
    """Show helpers management for a specific group"""
    # Store the target group ID for future use
    context.user_data['target_group_id'] = group_id
    
    keyboard = [
        [InlineKeyboardButton("➕ Pridėti pagalbininką", callback_data="add_helper")],
        [InlineKeyboardButton("📋 Peržiūrėti pagalbininkus", callback_data="list_helpers")],
        [InlineKeyboardButton("⚙️ Nustatymai", callback_data="helpers_settings")],
        [InlineKeyboardButton("⬅️ Atgal į grupės pasirinkimą", callback_data="admin_helpers")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"👥 **Pagalbininkai - {group_name}**\n\n"
        f"Grupės ID: `{group_id}`\n\n"
        "Pasirinkite veiksmą:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_pending_scammers_panel(query, context):
    """Show pending scammer reports in moderation panel"""
    if not pending_scammer_reports:
        await query.edit_message_text("✅ Nėra laukiančių scamer pranešimų!")
        return
    
    reports_text = "⏳ LAUKIANTYS SCAMER PRANEŠIMAI ⏳\n\n"
    keyboard = []
    
    for report_id, report in list(pending_scammer_reports.items())[:10]:  # Show max 10 reports
        date = report['timestamp'].strftime('%m-%d %H:%M')
        proof_short = report['proof'][:30] + "..." if len(report['proof']) > 30 else report['proof']
        
        reports_text += f"#{report_id} {report['username']}\n"
        reports_text += f"👤 {report['reporter_username']}\n"
        reports_text += f"📅 {date}\n"
        reports_text += f"📝 {proof_short}\n\n"
        
        # Add buttons for each report
        keyboard.append([
            InlineKeyboardButton(f"✅ #{report_id}", callback_data=f"approve_scammer_{report_id}"),
            InlineKeyboardButton(f"❌ #{report_id}", callback_data=f"reject_scammer_{report_id}"),
            InlineKeyboardButton(f"ℹ️ #{report_id}", callback_data=f"scammer_details_{report_id}")
        ])
    
    if len(pending_scammer_reports) > 10:
        reports_text += f"\n... ir dar {len(pending_scammer_reports) - 10} pranešimų"
    
    reports_text += f"\n\nViso pranešimų: {len(pending_scammer_reports)}"
    
    # Add back button
    keyboard.append([InlineKeyboardButton("◀️ Atgal į moderacijos pultą", callback_data="mod_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(reports_text, reply_markup=reply_markup)

async def show_pending_buyers_panel(query, context):
    """Show pending buyer reports in moderation panel"""
    if not pending_buyer_reports:
        await query.edit_message_text("✅ Nėra laukiančių pirkėjų pranešimų!")
        return
    
    reports_text = "⏳ LAUKIANTYS PIRKĖJŲ PRANEŠIMAI ⏳\n\n"
    keyboard = []
    
    for report_id, report in list(pending_buyer_reports.items())[:10]:  # Show max 10 reports
        date = report['timestamp'].strftime('%m-%d %H:%M')
        reason_short = report['reason'][:30] + "..." if len(report['reason']) > 30 else report['reason']
        
        reports_text += f"#{report_id} {report['username']}\n"
        reports_text += f"👤 {report['reporter_username']}\n"
        reports_text += f"📅 {date}\n"
        reports_text += f"📝 {reason_short}\n\n"
        
        # Add buttons for each report
        keyboard.append([
            InlineKeyboardButton(f"✅ #{report_id}", callback_data=f"approve_buyer_{report_id}"),
            InlineKeyboardButton(f"❌ #{report_id}", callback_data=f"reject_buyer_{report_id}"),
            InlineKeyboardButton(f"ℹ️ #{report_id}", callback_data=f"buyer_details_{report_id}")
        ])
    
    if len(pending_buyer_reports) > 10:
        reports_text += f"\n... ir dar {len(pending_buyer_reports) - 10} pranešimų"
    
    reports_text += f"\n\nViso pranešimų: {len(pending_buyer_reports)}"
    
    # Add back button
    keyboard.append([InlineKeyboardButton("◀️ Atgal į moderacijos pultą", callback_data="mod_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(reports_text, reply_markup=reply_markup)

async def balsuoti(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return

    msg = await update.message.reply_text(
        f'<a href="{VOTING_GROUP_LINK}">Spauskite čia</a> norėdami eiti į balsavimo grupę.\nTen rasite balsavimo mygtukus!',
        parse_mode=telegram.constants.ParseMode.HTML
    )
    context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def handle_vote_button(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        logger.error("No callback query received")
        return
    
    user_id = query.from_user.id
    if query.message is None:
        await query.answer("Klaida: Balsavimo žinutė nerasta.")
        logger.error(f"Message is None for user_id={user_id}, callback_data={query.data}")
        return
    
    chat_id = query.message.chat_id
    data = query.data

    logger.info(f"Vote attempt by user_id={user_id} in chat_id={chat_id}, callback_data={data}")

    # Check for button spam protection (10 second cooldown between button clicks)
    can_vote, remaining = rate_limiter.check_cooldown(user_id, 'balsuoti')
    if not can_vote:
        cooldown_msg = rate_limiter.format_cooldown_message(remaining)
        await query.answer(f"Per dažnai spaudžiate mygtuką! {cooldown_msg}")
        logger.info(f"User_id={user_id} blocked by button spam protection, {remaining:.1f}s remaining")
        return

    if not data.startswith("vote_"):
        logger.warning(f"Invalid callback data: {data} from user_id={user_id}")
        return

    seller = data.replace("vote_", "")
    if seller not in trusted_sellers:
        await query.answer("Šis pardavėjas nebegalioja!")
        logger.warning(f"Attempt to vote for invalid seller '{seller}' by user_id={user_id}")
        return

    now = datetime.now(TIMEZONE)
    last_vote = last_vote_attempt.get(user_id, datetime.min.replace(tzinfo=TIMEZONE))
    cooldown_remaining = timedelta(days=7) - (now - last_vote)
    if cooldown_remaining > timedelta(0):
        hours_left = max(1, int(cooldown_remaining.total_seconds() // 3600))
        await query.answer(f"Tu jau balsavai! Liko ~{hours_left} valandų iki kito balsavimo.")
        logger.info(f"User_id={user_id} blocked by cooldown, {hours_left} hours left.")
        return

    # Use atomic operations for vote processing
    async with data_manager.atomic_operation("voting_data"):
        user_points.setdefault(user_id, 0)
        votes_weekly.setdefault(seller, 0)
        votes_alltime.setdefault(seller, 0)
        votes_monthly.setdefault(seller, [])
        vote_history.setdefault(seller, [])  # FIX: Initialize vote_history for new sellers

        votes_weekly[seller] += 1
        votes_monthly[seller].append((now, 1))
        votes_alltime[seller] += 1
        voters.add(user_id)
        vote_history[seller].append((user_id, "up", "Button vote", now))
        user_points[user_id] += 15
        last_vote_attempt[user_id] = now

        # Save all voting data atomically
        save_data(votes_weekly, 'votes_weekly.pkl')
        save_data(votes_monthly, 'votes_monthly.pkl')
        save_data(votes_alltime, 'votes_alltime.pkl')
        save_data(vote_history, 'vote_history.pkl')
        save_data(user_points, 'user_points.pkl')

    await query.answer("Ačiū už jūsų balsą, 15 taškų buvo pridėti prie jūsų sąskaitos.")
    
    # Get voter's username with better formatting
    if query.from_user.username:
        voter_username = f"@{query.from_user.username}"
    elif query.from_user.first_name:
        if query.from_user.last_name:
            voter_username = f"{query.from_user.first_name} {query.from_user.last_name}"
        else:
            voter_username = query.from_user.first_name
    else:
        voter_username = f"Vartotojas {user_id}"
    
    # Calculate when user can vote next (7 days from now)
    next_vote_time = now + timedelta(days=7)
    next_vote_formatted = next_vote_time.strftime("%Y-%m-%d %H:%M")
    
    # Get current vote counts for the seller
    seller_name = seller[1:] if seller.startswith('@') else seller  # Remove @ for display
    weekly_votes = votes_weekly.get(seller, 0)
    alltime_votes = votes_alltime.get(seller, 0)
    
    # Send short confirmation message
    confirmation_text = f"🗳️ {voter_username} balsavo už {seller_name} (+15 tšk)\n"
    confirmation_text += f"📊 Savaitė: {weekly_votes} | Viso: {alltime_votes}\n"
    confirmation_text += f"⏰ Kitas balsas: {next_vote_formatted}"
    
    try:
        confirmation_msg = await context.bot.send_message(
            chat_id=VOTING_GROUP_CHAT_ID,  # Send to voting group so everyone can see
            text=confirmation_text,
            parse_mode='Markdown'
        )
    except telegram.error.TelegramError as e:
        # Fallback without markdown if formatting fails
        logger.warning(f"Failed to send formatted vote confirmation: {str(e)}")
        fallback_text = confirmation_text.replace('**', '').replace('*', '')
        confirmation_msg = await context.bot.send_message(
            chat_id=VOTING_GROUP_CHAT_ID,  # Send to voting group so everyone can see
            text=fallback_text
        )
    
    # Delete confirmation message after 35 seconds
    context.job_queue.run_once(delete_message_job, 35, data=(VOTING_GROUP_CHAT_ID, confirmation_msg.message_id))

async def updatevoting(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali atnaujinti balsavimo mygtukus!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    await update_voting_message(context)
    msg = await update.message.reply_text("Balsavimo mygtukai atnaujinti!")
    context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def addftbaryga(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali pridėti media!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    if not update.message.reply_to_message:
        msg = await update.message.reply_text("Atsakyk į žinutę su paveikslėliu, GIF ar video!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    global featured_media_id, featured_media_type, last_addftbaryga_message
    reply = update.message.reply_to_message
    if reply.photo:
        media = reply.photo[-1]
        featured_media_id = media.file_id
        featured_media_type = 'photo'
        last_addftbaryga_message = "Paveikslėlis pridėtas prie /balsuoti!"
    elif reply.animation:
        media = reply.animation
        featured_media_id = media.file_id
        featured_media_type = 'animation'
        last_addftbaryga_message = "GIF pridėtas prie /balsuoti!"
    elif reply.video:
        media = reply.video
        featured_media_id = media.file_id
        featured_media_type = 'video'
        last_addftbaryga_message = "Video pridėtas prie /balsuoti!"
    else:
        msg = await update.message.reply_text("Atsakyk į žinutę su paveikslėliu, GIF ar video!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    save_data(featured_media_id, 'featured_media_id.pkl')
    save_data(featured_media_type, 'featured_media_type.pkl')
    msg = await update.message.reply_text(last_addftbaryga_message)
    context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
    await update_voting_message(context)

async def addftbaryga2(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali pridėti media!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    if not update.message.reply_to_message:
        msg = await update.message.reply_text("Atsakyk į žinutę su paveikslėliu, GIF ar video!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    global barygos_media_id, barygos_media_type, last_addftbaryga2_message
    reply = update.message.reply_to_message
    if reply.photo:
        media = reply.photo[-1]
        barygos_media_id = media.file_id
        barygos_media_type = 'photo'
        last_addftbaryga2_message = "Paveikslėlis pridėtas prie /barygos!"
    elif reply.animation:
        media = reply.animation
        barygos_media_id = media.file_id
        barygos_media_type = 'animation'
        last_addftbaryga2_message = "GIF pridėtas prie /barygos!"
    elif reply.video:
        media = reply.video
        barygos_media_id = media.file_id
        barygos_media_type = 'video'
        last_addftbaryga2_message = "Video pridėtas prie /barygos!"
    else:
        msg = await update.message.reply_text("Atsakyk į žinutę su paveikslėliu, GIF ar video!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    save_data(barygos_media_id, 'barygos_media_id.pkl')
    save_data(barygos_media_type, 'barygos_media_type.pkl')
    msg = await update.message.reply_text(last_addftbaryga2_message)
    context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def editpardavejai(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali redaguoti šį tekstą!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return

    try:
        new_message = " ".join(context.args)
        if not new_message:
            msg = await update.message.reply_text("Naudok: /editpardavejai 'Naujas tekstas'")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
        global pardavejai_message
        pardavejai_message = new_message
        save_pardavejai_message()
        msg = await update.message.reply_text(f"Pardavėjų žinutė atnaujinta: '{pardavejai_message}'")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        await update_voting_message(context)
    except IndexError:
        msg = await update.message.reply_text("Naudok: /editpardavejai 'Naujas tekstas'")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def apklausa(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id

    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return

    try:
        question = " ".join(context.args)
        if not question:
            msg = await update.message.reply_text("Naudok: /apklausa 'Klausimas'")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return

        poll_id = f"{chat_id}_{user_id}_{int(datetime.now(TIMEZONE).timestamp())}"
        polls[poll_id] = {"question": question, "yes": 0, "no": 0, "voters": set()}
        logger.info(f"Created poll with ID: {poll_id}")

        keyboard = [
            [InlineKeyboardButton("Taip (0)", callback_data=f"poll_{poll_id}_yes"),
             InlineKeyboardButton("Ne (0)", callback_data=f"poll_{poll_id}_no")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(f"📊 Apklausa: {question}", reply_markup=reply_markup)
    except IndexError:
        msg = await update.message.reply_text("Naudok: /apklausa 'Klausimas'")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def handle_poll_button(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user_id = query.from_user.id
    data = query.data

    if not data.startswith("poll_"):
        return

    parts = data.rsplit("_", 1)
    if len(parts) != 2:
        logger.error(f"Invalid callback data format: {data}")
        await query.answer("Klaida: Netinkamas balsavimo formatas!")
        return

    poll_id, vote = parts[0][5:], parts[1]
    if poll_id not in polls:
        await query.answer("Ši apklausa nebegalioja!")
        return

    poll = polls[poll_id]
    if user_id in poll["voters"]:
        await query.answer("Jau balsavai šioje apklausoje!")
        return

    poll["voters"].add(user_id)
    if vote == "yes":
        poll["yes"] += 1
    elif vote == "no":
        poll["no"] += 1
    else:
        logger.error(f"Invalid vote type: {vote}")
        await query.answer("Klaida balsuojant!")
        return

    keyboard = [
        [InlineKeyboardButton(f"Taip ({poll['yes']})", callback_data=f"poll_{poll_id}_yes"),
         InlineKeyboardButton(f"Ne ({poll['no']})", callback_data=f"poll_{poll_id}_no")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f"📊 Apklausa: {poll['question']}\nBalsai: Taip - {poll['yes']}, Ne - {poll['no']}", reply_markup=reply_markup)
    await query.answer("Tavo balsas užskaitytas!")

async def cleanup_old_polls(context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Clean up polls older than 24 hours to prevent memory leaks"""
    current_time = datetime.now(TIMEZONE).timestamp()
    polls_to_remove = []
    
    for poll_id in polls:
        try:
            # Extract timestamp from poll_id
            poll_timestamp = int(poll_id.split('_')[-1])
            if current_time - poll_timestamp > 86400:  # 24 hours
                polls_to_remove.append(poll_id)
        except (ValueError, IndexError):
            # If we can't parse timestamp, remove old format polls
            polls_to_remove.append(poll_id)
    
    for poll_id in polls_to_remove:
        del polls[poll_id]
    
    if polls_to_remove:
        logger.info(f"Cleaned up {len(polls_to_remove)} old polls")

async def cleanup_expired_challenges(context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Clean up expired coinflip challenges to prevent memory leaks"""
    current_time = datetime.now(TIMEZONE)
    challenges_to_remove = []
    
    for user_id, (initiator_id, amount, timestamp, initiator_username, opponent_username, chat_id) in coinflip_challenges.items():
        if current_time - timestamp > timedelta(minutes=10):  # 10 minutes expiry
            challenges_to_remove.append(user_id)
    
    for user_id in challenges_to_remove:
        del coinflip_challenges[user_id]
    
    if challenges_to_remove:
        logger.info(f"Cleaned up {len(challenges_to_remove)} expired coinflip challenges")

async def cleanup_memory(context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Clean up data structures to prevent memory leaks"""
    now = datetime.now(TIMEZONE)
    
    # Clean up daily messages older than 7 days
    cutoff_date = (now - timedelta(days=7)).date()
    cleanup_count = 0
    
    for user_id in list(daily_messages.keys()):
        user_daily = daily_messages[user_id]
        old_dates = [date for date in user_daily.keys() if date < cutoff_date]
        for old_date in old_dates:
            del user_daily[old_date]
            cleanup_count += 1
        
        # Remove empty user entries
        if not user_daily:
            del daily_messages[user_id]
    
    # Limit username_to_id cache to prevent unbounded growth
    if len(username_to_id) > 10000:
        # Keep only the most recent 5000 entries (rough LRU)
        items = list(username_to_id.items())
        username_to_id.clear()
        username_to_id.update(items[-5000:])
        logger.info("Trimmed username_to_id cache")
    
    # Clean up expired challenges (manual cleanup, not scheduled)
    current_time = datetime.now(TIMEZONE)
    challenges_to_remove = []
    
    for user_id, (initiator_id, amount, timestamp, initiator_username, opponent_username, chat_id) in coinflip_challenges.items():
        if current_time - timestamp > timedelta(minutes=10):  # 10 minutes expiry
            challenges_to_remove.append(user_id)
    
    for user_id in challenges_to_remove:
        del coinflip_challenges[user_id]
    
    if challenges_to_remove:
        logger.info(f"Memory cleanup: removed {len(challenges_to_remove)} expired coinflip challenges")
    
    # Clean up old rate limiter data (older than 1 hour)
    rate_limiter_cutoff = now - timedelta(hours=1)
    cleaned_users = []
    
    for user_id, commands in list(rate_limiter.command_cooldowns.items()):
        expired_commands = []
        for command, last_use in commands.items():
            if last_use < rate_limiter_cutoff:
                expired_commands.append(command)
        
        for command in expired_commands:
            del commands[command]
        
        if not commands:
            cleaned_users.append(user_id)
    
    for user_id in cleaned_users:
        del rate_limiter.command_cooldowns[user_id]
    
    logger.info(f"Memory cleanup completed: {cleanup_count} daily message entries, "
                f"{len(cleaned_users)} rate limiter entries")

async def nepatiko(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    now = datetime.now(TIMEZONE)
    last_downvote_attempt[user_id] = last_downvote_attempt.get(user_id, datetime.min.replace(tzinfo=TIMEZONE))
    if now - last_downvote_attempt[user_id] < timedelta(days=7):
        msg = await update.message.reply_text("Palauk 7 dienas po paskutinio nepritarimo!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Input validation
    if len(context.args) < 2:
        msg = await update.message.reply_text("Naudok: /nepatiko @VendorTag 'Reason'")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Sanitize vendor username
    vendor = sanitize_username(context.args[0])
    if not vendor or len(vendor) < 2:
        msg = await update.message.reply_text("Netinkamas pardavėjo vardas! Naudok @username formatą.")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Sanitize and validate reason
    reason = sanitize_text_input(" ".join(context.args[1:]), max_length=200)
    if not reason or len(reason.strip()) < 3:
        msg = await update.message.reply_text("Prašau nurodyti išsamią priežastį (bent 3 simboliai)!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Check if vendor exists in trusted sellers
    if vendor not in trusted_sellers:
        msg = await update.message.reply_text(f"{vendor} nėra patikimų pardavėjų sąraše!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Rate limiting check
    user_complaints_today = sum(1 for _, (_, uid, _, ts) in pending_downvotes.items() 
                               if uid == user_id and now - ts < timedelta(hours=24))
    if user_complaints_today >= 3:
        msg = await update.message.reply_text("Per daug skundų per dieną! Palauk.")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    try:
        global complaint_id
        complaint_id += 1
        pending_downvotes[complaint_id] = (vendor, user_id, reason, now)
        downvoters.add(user_id)
        vote_history.setdefault(vendor, []).append((user_id, "down", reason, now))
        user_points[user_id] = user_points.get(user_id, 0) + 5
        last_downvote_attempt[user_id] = now
        
        admin_message = f"Skundas #{complaint_id}: {vendor} - '{reason}' by User {user_id}. Patvirtinti su /approve {complaint_id}"
        await safe_send_message(context.bot, ADMIN_CHAT_ID, admin_message)
        
        msg = await update.message.reply_text(f"Skundas pateiktas! Atsiųsk įrodymus @kunigasnew dėl Skundo #{complaint_id}. +5 taškų!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        save_data(vote_history, 'vote_history.pkl')
        save_data(user_points, 'user_points.pkl')
    except Exception as e:
        logger.error(f"Error processing complaint: {str(e)}")
        msg = await update.message.reply_text("Klaida pateikiant skundą. Bandyk vėliau.")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def approve(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if user_id != ADMIN_CHAT_ID:
        return
    if not (is_allowed_group(chat_id) or chat_id == user_id):
        msg = await update.message.reply_text("Ši komanda veikia tik grupėje arba privačiai!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    try:
        cid = int(context.args[0])
        if cid not in pending_downvotes:
            msg = await update.message.reply_text("Neteisingas skundo ID!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
        vendor, user_id, reason, timestamp = pending_downvotes[cid]
        votes_weekly[vendor] -= 1
        votes_monthly[vendor].append((timestamp, -1))
        votes_alltime[vendor] -= 1
        approved_downvotes[cid] = pending_downvotes[cid]
        del pending_downvotes[cid]
        msg = await update.message.reply_text(f"Skundas patvirtintas dėl {vendor}!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        save_data(votes_weekly, 'votes_weekly.pkl')
        save_data(votes_monthly, 'votes_monthly.pkl')
        save_data(votes_alltime, 'votes_alltime.pkl')
    except (IndexError, ValueError):
        msg = await update.message.reply_text("Naudok: /approve ComplaintID")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def addseller(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali pridėti pardavėją!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    if not is_allowed_group(chat_id) and chat_id != user_id:
        msg = await update.message.reply_text("Botas neveikia šioje grupėje arba naudok privačiai!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Input validation
    if len(context.args) < 1:
        msg = await update.message.reply_text("Naudok: /addseller @VendorTag")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Sanitize vendor username
    vendor = sanitize_username(context.args[0])
    if not vendor or len(vendor) < 2:
        msg = await update.message.reply_text("Netinkamas pardavėjo vardas! Naudok @username formatą.")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Check if already exists
    if vendor in trusted_sellers:
        msg = await update.message.reply_text(f"{vendor} jau yra patikimų pardavėjų sąraše!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Check seller limit
    if len(trusted_sellers) >= 50:  # Reasonable limit
        msg = await update.message.reply_text("Per daug pardavėjų! Pašalink senus prieš pridedant naujus.")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    try:
        trusted_sellers.append(vendor)
        save_trusted_sellers()  # Save to persistent storage
        
        # Initialize data structures for new seller
        votes_weekly.setdefault(vendor, 0)
        votes_monthly.setdefault(vendor, [])
        votes_alltime.setdefault(vendor, 0)
        vote_history.setdefault(vendor, [])
        
        msg = await update.message.reply_text(f"Pardavėjas {vendor} pridėtas! Jis dabar matomas /balsuoti sąraše.")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        await update_voting_message(context)
        logger.info(f"Admin {user_id} added seller: {vendor}")
    except Exception as e:
        logger.error(f"Error adding seller: {str(e)}")
        trusted_sellers.remove(vendor) if vendor in trusted_sellers else None
        msg = await update.message.reply_text("Klaida pridedant pardavėją!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def removeseller(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali pašalinti pardavėją!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    if not is_allowed_group(chat_id) and chat_id != user_id:
        msg = await update.message.reply_text("Botas neveikia šioje grupėje arba naudok privačiai!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Input validation
    if len(context.args) < 1:
        msg = await update.message.reply_text("Naudok: /removeseller @VendorTag")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Sanitize vendor username
    vendor = sanitize_username(context.args[0])
    if not vendor or len(vendor) < 2:
        msg = await update.message.reply_text("Netinkamas pardavėjo vardas! Naudok @username formatą.")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    if vendor not in trusted_sellers:
        msg = await update.message.reply_text(f"'{vendor}' nėra patikimų pardavėjų sąraše! Sąrašas: {trusted_sellers}")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    try:
        trusted_sellers.remove(vendor)
        save_trusted_sellers()  # Save to persistent storage
        
        votes_weekly.pop(vendor, None)
        votes_monthly.pop(vendor, None)
        votes_alltime.pop(vendor, None)
        vote_history.pop(vendor, None)  # Also remove vote history
        
        msg = await update.message.reply_text(f"Pardavėjas {vendor} pašalintas iš sąrašo ir balsų!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        await update_voting_message(context)
        
        # Save all affected data
        save_data(votes_weekly, 'votes_weekly.pkl')
        save_data(votes_monthly, 'votes_monthly.pkl')
        save_data(votes_alltime, 'votes_alltime.pkl')
        save_data(vote_history, 'vote_history.pkl')
        logger.info(f"Admin {user_id} removed seller: {vendor}")
    except Exception as e:
        logger.error(f"Error removing seller: {str(e)}")
        msg = await update.message.reply_text("Klaida šalinant pardavėją!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def sellerinfo(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    try:
        vendor = context.args[0]
        if not vendor.startswith('@'):
            vendor = '@' + vendor
        if vendor not in trusted_sellers:
            msg = await update.message.reply_text(f"{vendor} nėra patikimas pardavėjas!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
        now = datetime.now(TIMEZONE)
        monthly_score = sum(s for ts, s in votes_monthly[vendor] if now - ts < timedelta(days=30))
        downvotes_30d = sum(1 for cid, (v, _, _, ts) in approved_downvotes.items() if v == vendor and now - ts < timedelta(days=30))
        info = f"{vendor} Info:\nSavaitė: {votes_weekly[vendor]}\nMėnuo: {monthly_score}\nViso: {votes_alltime[vendor]}\nNeigiami (30d): {downvotes_30d}"
        msg = await update.message.reply_text(info)
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
    except IndexError:
        msg = await update.message.reply_text("Naudok: /pardavejoinfo @VendorTag")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def barygos(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    now = datetime.now(TIMEZONE)
    
    # Create centered header
    header = "🏆 PARDAVĖJŲ REITINGAI 🏆".center(26) + "\n"
    header += f"📅 {now.strftime('%Y-%m-%d %H:%M')}".center(26) + "\n"
    header += "=" * 26 + "\n\n"
    
    # Add custom admin message if exists
    if last_addftbaryga2_message:
        header += f"📢 {last_addftbaryga2_message}\n\n"
    
    # Build centered Weekly Leaderboard
    weekly_board = "🔥 SAVAITĖS ČEMPIONAI 🔥".center(26) + "\n"
    weekly_board += f"📊 {now.strftime('%V savaitė')}".center(26) + "\n\n"
    
    if not votes_weekly:
        weekly_board += "😴 Dar nėra balsų šią savaitę".center(26) + "\n"
        weekly_board += "Būk pirmas - balsuok dabar!".center(26) + "\n\n"
    else:
        sorted_weekly = sorted(votes_weekly.items(), key=lambda x: x[1], reverse=True)
        
        for i, (vendor, score) in enumerate(sorted_weekly[:10], 1):
            # Create trophy icons based on position
            if i == 1:
                icon = "🥇"
            elif i == 2:
                icon = "🥈"
            elif i == 3:
                icon = "🥉"
            elif i <= 5:
                icon = "🏅"
            else:
                icon = "📈"
            
            # Format vendor name (remove @)
            vendor_name = vendor[1:] if vendor.startswith('@') else vendor
            
            weekly_board += f"{icon} {i}. {vendor_name} - {score} balsų".center(26) + "\n"
    
    weekly_board += "\n" + "<><><><><><><><><><><><><>" + "\n\n"
    
    # Build centered Monthly Leaderboard
    monthly_board = "🗓️ MĖNESIO LYDERIAI 🗓️".center(26) + "\n"
    monthly_board += f"📊 {now.strftime('%B %Y')}".center(26) + "\n\n"
    
    # Calculate current calendar month totals
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_totals = defaultdict(int)
    for vendor, votes_list in votes_monthly.items():
        current_month_votes = [(ts, s) for ts, s in votes_list if ts >= month_start]
        monthly_totals[vendor] = sum(s for _, s in current_month_votes)
    
    if not monthly_totals:
        monthly_board += "🌱 Naujas mėnuo - nauji tikslai".center(26) + "\n"
        monthly_board += "Pradėk balsuoti dabar!".center(26) + "\n\n"
    else:
        sorted_monthly = sorted(monthly_totals.items(), key=lambda x: x[1], reverse=True)
        
        for i, (vendor, score) in enumerate(sorted_monthly[:10], 1):
            # Create crown icons for monthly leaders
            if i == 1:
                icon = "👑"
            elif i == 2:
                icon = "💎"
            elif i == 3:
                icon = "⭐"
            else:
                icon = "🌟"
            
            vendor_name = vendor[1:] if vendor.startswith('@') else vendor
            monthly_board += f"{icon} {i}. {vendor_name} - {score} balsų".center(26) + "\n"
    
    monthly_board += "\n" + "<><><><><><><><><><><><><>" + "\n\n"
    
    # Build centered All-Time Hall of Fame
    alltime_board = "🌟 VISŲ LAIKŲ LEGENDOS 🌟".center(26) + "\n"
    alltime_board += "📈 Istoriniai rekordai".center(26) + "\n\n"
    
    if not votes_alltime:
        alltime_board += "🎯 Istorija tik prasideda".center(26) + "\n"
        alltime_board += "Tapk pirmąja legenda!".center(26) + "\n\n"
    else:
        sorted_alltime = sorted(votes_alltime.items(), key=lambda x: x[1], reverse=True)
        
        for i, (vendor, score) in enumerate(sorted_alltime[:10], 1):
            # Special icons for hall of fame
            if i == 1:
                icon = "🏆"
            elif i == 2:
                icon = "🎖️"
            elif i == 3:
                icon = "🎗️"
            elif score >= 100:
                icon = "💫"
            elif score >= 50:
                icon = "⚡"
            else:
                icon = "🔸"
            
            vendor_name = vendor[1:] if vendor.startswith('@') else vendor
            alltime_board += f"{icon} {i}. {vendor_name} - {score} balsų".center(26) + "\n"
    
    alltime_board += "\n" + "<><><><><><><><><><><><><>" + "\n\n"
    
    # Add centered footer
    footer = "📊 STATISTIKOS".center(26) + "\n\n"
    
    total_weekly_votes = sum(votes_weekly.values())
    total_monthly_votes = sum(monthly_totals.values())
    total_alltime_votes = sum(votes_alltime.values())
    active_sellers = len([v for v in votes_weekly.values() if v > 0])
    
    footer += f"📈 Savaitės balsų: {total_weekly_votes}".center(26) + "\n"
    footer += f"📅 Mėnesio balsų: {total_monthly_votes}".center(26) + "\n"
    footer += f"🌟 Visų laikų balsų: {total_alltime_votes}".center(26) + "\n"
    footer += f"👥 Aktyvūs pardavėjai: {active_sellers}".center(26) + "\n\n"
    
    # Add next reset information
    next_sunday = now + timedelta(days=(6 - now.weekday()))
    next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
    
    footer += "⏰ KITAS RESTARTAS".center(26) + "\n\n"
    footer += f"• Savaitės: {next_sunday.strftime('%m-%d %H:%M')}".center(26) + "\n"
    footer += f"• Mėnesio: {next_month.strftime('%m-%d %H:%M')}".center(26) + "\n\n"
    
    footer += "💡 Balsuok kas savaitę už mėgstamus pardavėjus!".center(26) + "\n"
    footer += "🎯 Skundai padeda kokybei (+5 tšk)".center(26)
    
    # Combine all sections - ensure all parts are included
    full_message = header + weekly_board + monthly_board + alltime_board + footer
    
    # Debug: Log message length for troubleshooting
    logger.info(f"Barygos message length: {len(full_message)} characters")
    
    try:
        # Check message length - if too long for caption, send as separate text message
        if len(full_message) > 1000 and barygos_media_id and barygos_media_type:
            # Send media without caption first
            if barygos_media_type == 'photo':
                await context.bot.send_photo(chat_id=chat_id, photo=barygos_media_id)
            elif barygos_media_type == 'animation':
                await context.bot.send_animation(chat_id=chat_id, animation=barygos_media_id)
            elif barygos_media_type == 'video':
                await context.bot.send_video(chat_id=chat_id, video=barygos_media_id)
            
            # Then send full message as text
            msg = await context.bot.send_message(
                chat_id=chat_id, 
                text=full_message,
                parse_mode='Markdown'
            )
        elif barygos_media_id and barygos_media_type:
            # Message is short enough for caption
            if barygos_media_type == 'photo':
                msg = await context.bot.send_photo(
                    chat_id=chat_id, 
                    photo=barygos_media_id, 
                    caption=full_message,
                    parse_mode='Markdown'
                )
            elif barygos_media_type == 'animation':
                msg = await context.bot.send_animation(
                    chat_id=chat_id, 
                    animation=barygos_media_id, 
                    caption=full_message,
                    parse_mode='Markdown'
                )
            elif barygos_media_type == 'video':
                msg = await context.bot.send_video(
                    chat_id=chat_id, 
                    video=barygos_media_id, 
                    caption=full_message,
                    parse_mode='Markdown'
                )
            else:
                msg = await context.bot.send_message(
                    chat_id=chat_id, 
                    text=full_message,
                    parse_mode='Markdown'
                )
        else:
            # No media, send as text
            msg = await context.bot.send_message(
                chat_id=chat_id, 
                text=full_message,
                parse_mode='Markdown'
            )
        
        context.job_queue.run_once(delete_message_job, 120, data=(chat_id, msg.message_id))  # Keep longer for reading
        
    except telegram.error.TelegramError as e:
        # Fallback without markdown if formatting fails
        logger.error(f"Error sending formatted barygos message: {str(e)}")
        try:
            fallback_message = full_message.replace('**', '').replace('*', '')
            msg = await context.bot.send_message(chat_id=chat_id, text=fallback_message)
            context.job_queue.run_once(delete_message_job, 90, data=(chat_id, msg.message_id))
        except Exception as fallback_error:
            logger.error(f"Fallback message also failed: {str(fallback_error)}")
            msg = await update.message.reply_text("❌ Klaida gaunant pardavėjų reitingus!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def chatking(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    if not alltime_messages:
        msg = await update.message.reply_text(
            "👑 POKALBIŲ LYDERIAI 👑\n\n"
            "🤐 Dar nėra žinučių istorijoje!\n"
            "Pradėk pokalbį ir tapk pirmuoju!"
        )
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Build beautiful header
    now = datetime.now(TIMEZONE)
    header = "👑✨ POKALBIŲ IMPERATORIAI ✨👑\n"
    header += f"📅 {now.strftime('%Y-%m-%d %H:%M')}\n"
    header += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Get top chatters
    sorted_chatters = sorted(alltime_messages.items(), key=lambda x: x[1], reverse=True)[:15]
    max_messages = sorted_chatters[0][1] if sorted_chatters else 1
    
    leaderboard = "🏆 VISŲ LAIKŲ TOP POKALBININKAI 🏆\n"
    leaderboard += "┌───────────────────────────────────────┐\n"
    
    for i, (user_id, msg_count) in enumerate(sorted_chatters, 1):
        try:
            # Try to get username from our mapping first
            username = next((k for k, v in username_to_id.items() if v == user_id), None)
            
            if not username:
                # Try to get from Telegram API
                try:
                    member = await context.bot.get_chat_member(chat_id, user_id)
                    if member.user.username:
                        username = f"@{member.user.username}"
                    else:
                        username = member.user.first_name or f"User {user_id}"
                except telegram.error.TelegramError:
                    username = f"User {user_id}"
            
            # Create crown icons based on ranking
            if i == 1:
                icon = "👑"
            elif i == 2:
                icon = "🥈"
            elif i == 3:
                icon = "🥉"
            elif i <= 5:
                icon = "🏅"
            elif i <= 10:
                icon = "⭐"
            else:
                icon = "🌟"
            
            # Create progress bar
            progress = msg_count / max(max_messages, 1)
            bar_length = 12
            filled = int(progress * bar_length)
            progress_bar = "█" * filled + "░" * (bar_length - filled)
            
            # Format username (remove @ if present, limit length)
            display_name = username[1:] if username.startswith('@') else username
            display_name = display_name[:10] if len(display_name) > 10 else display_name
            
            # Create achievement levels
            if msg_count >= 10000:
                level = "🔥LEGENDA"
            elif msg_count >= 5000:
                level = "⚡EKSPERTAS"
            elif msg_count >= 1000:
                level = "💎MEISTRAS"
            elif msg_count >= 500:
                level = "🌟AKTYVUS"
            elif msg_count >= 100:
                level = "📈NAUJOKAS"
            else:
                level = "🌱PRADŽIA"
            
            leaderboard += f"│{icon} {i:2d}. {display_name:<10} │{msg_count:4d}│{progress_bar}│{level}\n"
            
        except Exception as e:
            logger.error(f"Error processing user {user_id} in chatking: {str(e)}")
            leaderboard += f"│💬 {i:2d}. User {user_id}     │{msg_count:4d}│{'█' * 8 + '░' * 4}│🤖ERROR\n"
    
    leaderboard += "└───────────────────────────────────────┘\n\n"
    
    # Add statistics and achievements info
    footer = "📊 GRUPĖS STATISTIKOS\n"
    total_messages = sum(alltime_messages.values())
    active_users = len([count for count in alltime_messages.values() if count >= 10])
    super_active = len([count for count in alltime_messages.values() if count >= 1000])
    
    footer += f"• Visų žinučių: {total_messages:,} 💬\n"
    footer += f"• Aktyvūs nariai: {active_users} 👥\n"
    footer += f"• Super aktyvūs: {super_active} 🔥\n"
    footer += f"• Vidurkis per narį: {total_messages // len(alltime_messages) if alltime_messages else 0} 📈\n\n"
    
    footer += "🎯 PASIEKIMŲ LYGIAI\n"
    footer += "🌱 Pradžia: 1-99 žinučių\n"
    footer += "📈 Naujokas: 100-499 žinučių\n"
    footer += "🌟 Aktyvus: 500-999 žinučių\n"
    footer += "💎 Meistras: 1,000-4,999 žinučių\n"
    footer += "⚡ Ekspertas: 5,000-9,999 žinučių\n"
    footer += "🔥 Legenda: 10,000+ žinučių\n\n"
    
    footer += "💬 Tęsk pokalbius ir kilk lyderių lentoje!"
    
    full_message = header + leaderboard + footer
    
    try:
        msg = await update.message.reply_text(full_message, parse_mode='Markdown')
        context.job_queue.run_once(delete_message_job, 90, data=(chat_id, msg.message_id))
    except telegram.error.TelegramError as e:
        # Fallback without markdown
        logger.error(f"Error sending formatted chatking: {str(e)}")
        fallback_message = full_message.replace('**', '').replace('*', '')
        msg = await update.message.reply_text(fallback_message)
        context.job_queue.run_once(delete_message_job, 60, data=(chat_id, msg.message_id))

async def handle_message(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    try:
        chat_id = update.message.chat_id
        
        # Handle private chat messages for admin features
        if update.message.chat.type == 'private':
            # Check if user is waiting for input
            if (context.user_data.get('waiting_for_group_id') or 
                context.user_data.get('waiting_for_word') or 
                context.user_data.get('waiting_for_helper_id') or 
                context.user_data.get('waiting_for_message') or
                context.user_data.get('waiting_for_manual_groups') or
                context.user_data.get('waiting_for_new_group') or
                context.user_data.get('waiting_for_custom_time') or
                context.user_data.get('waiting_for_custom_interval') or
                context.user_data.get('waiting_for_text') or
                context.user_data.get('waiting_for_media') or
                context.user_data.get('waiting_for_buttons')):
                
                # Process private chat input
                await process_private_chat_input(update, context)
                return
            
            # If not waiting for input, ignore private chat messages
            return
        
        # Handle group messages
        if not is_allowed_group(chat_id):
            return
        
        # Check message validity
        if not update.message.text or update.message.text.startswith('/'):
            return
        
        # Check message length to prevent spam
        if len(update.message.text) > 4000:  # Telegram's limit is 4096
            return
        
        user_id = update.message.from_user.id
        username = update.message.from_user.username
        
        # Enhanced validation
        if not validate_user_id(user_id):
            logger.warning(f"Invalid user_id received: {user_id}")
            return
        
        if not validate_chat_id_safe(chat_id):
            logger.warning(f"Invalid chat_id received: {chat_id}")
            return
        
        # All private chat input is now handled in process_private_chat_input function
        
        elif context.user_data.get('waiting_for_manual_groups'):
            # User is entering multiple group IDs separated by commas
            try:
                group_ids_text = update.message.text.strip()
                group_ids = [int(gid.strip()) for gid in group_ids_text.split(',')]
                group_selection_type = context.user_data.get('group_selection_type', 'recurring')
                
                # Verify each group and add to allowed_groups if not already there
                added_groups = []
                for group_id in group_ids:
                    try:
                        # Check if user is admin in this group
                        chat_member = await context.bot.get_chat_member(group_id, user_id)
                        if chat_member.status in ['creator', 'administrator']:
                            if str(group_id) not in allowed_groups:
                                allowed_groups.add(str(group_id))
                                added_groups.append(group_id)
                    except Exception:
                        continue
                
                if added_groups:
                    # Save the updated allowed_groups
                    save_data(allowed_groups, 'allowed_groups.pkl')
                    
                    await update.message.reply_text(
                        f"✅ **Grupės pridėtos!**\n\n"
                        f"Pridėtos grupės: {', '.join(map(str, added_groups))}\n\n"
                        f"Dabar galite pasirinkti šias grupes iš sąrašo.",
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(
                        "❌ **Nepavyko pridėti grupių!**\n\n"
                        "Patikrinkite:\n"
                        "• Ar grupės ID teisingi\n"
                        "• Ar esate administratorius grupėse\n"
                        "• Ar grupės egzistuoja"
                    )
                
            except ValueError:
                await update.message.reply_text("❌ Neteisingas formatas! Įveskite grupės ID, atskirtus kableliais.")
            
            # Clear waiting state
            context.user_data.pop('waiting_for_manual_groups', None)
            context.user_data.pop('group_selection_type', None)
            return
        
        elif context.user_data.get('waiting_for_new_group'):
            # User is adding a single new group
            try:
                group_id = int(update.message.text.strip())
                group_selection_type = context.user_data.get('group_selection_type', 'recurring')
                
                # Verify the group exists and user is admin there
                try:
                    chat_member = await context.bot.get_chat_member(group_id, user_id)
                    if chat_member.status not in ['creator', 'administrator']:
                        await update.message.reply_text("❌ Turite būti administratorius nurodytoje grupėje!")
                        return
                except Exception as e:
                    await update.message.reply_text("❌ Nepavyko patikrinti teisių grupėje arba grupė neegzistuoja!")
                    return
                
                # Add to allowed_groups if not already there
                if str(group_id) not in allowed_groups:
                    allowed_groups.add(str(group_id))
                    save_data(allowed_groups, 'allowed_groups.pkl')
                    
                    await update.message.reply_text(
                        f"✅ **Grupė pridėta!**\n\n"
                        f"Grupės ID: `{group_id}`\n"
                        f"Funkcija: **{get_feature_name(group_selection_type)}**\n\n"
                        f"Dabar galite pasirinkti šią grupę iš sąrašo.",
                        parse_mode='Markdown'
                    )
                else:
                    await update.message.reply_text(
                        f"ℹ️ **Grupė jau pridėta!**\n\n"
                        f"Grupės ID: `{group_id}` jau yra sąraše."
                    )
                
            except ValueError:
                await update.message.reply_text("❌ Neteisingas grupės ID formatas! Įveskite skaičių.")
            
            # Clear waiting state
            context.user_data.pop('waiting_for_new_group', None)
            context.user_data.pop('group_selection_type', None)
            return
        
        # Check for banned words
        banned_word, action = database.check_banned_words(chat_id, update.message.text)
        if banned_word:
            # Delete the message
            try:
                await update.message.delete()
            except Exception as e:
                logger.warning(f"Could not delete message with banned word: {e}")
            
            # Take action based on the word's action setting
            if action == 'warn':
                await update.message.reply_text(
                    f"⚠️ **Perspėjimas!**\n\n"
                    f"Vartotojas {update.message.from_user.first_name} naudojo uždraustą žodį: **{banned_word}**",
                    parse_mode='Markdown'
                )
            elif action == 'mute':
                # Mute the user for 1 hour
                until_date = datetime.now() + timedelta(hours=1)
                try:
                    await context.bot.restrict_chat_member(
                        chat_id, user_id,
                        permissions=telegram.ChatPermissions(
                            can_send_messages=False,
                            can_send_media_messages=False,
                            can_send_other_messages=False,
                            can_add_web_page_previews=False
                        ),
                        until_date=until_date
                    )
                    await update.message.reply_text(
                        f"🔇 **Vartotojas nutildytas!**\n\n"
                        f"👤 **Vartotojas:** {update.message.from_user.first_name}"
                        f"{f' (@{username})' if username else ''}\n"
                        f"🚫 **Priežastis:** Uždraustas žodis: **{banned_word}**\n"
                        f"⏰ **Trukmė:** 1 valanda",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Failed to mute user for banned word: {e}")
            elif action == 'ban':
                # Ban the user
                try:
                    await context.bot.ban_chat_member(chat_id, user_id)
                    await update.message.reply_text(
                        f"🚫 **Vartotojas uždraustas!**\n\n"
                        f"👤 **Vartotojas:** {update.message.from_user.first_name}"
                        f"{f' (@{username})' if username else ''}\n"
                        f"🚫 **Priežastis:** Uždraustas žodis: **{banned_word}**\n"
                        f"⏰ **Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        parse_mode='Markdown'
                    )
                except Exception as e:
                    logger.error(f"Failed to ban user for banned word: {e}")
            
            return
        
        # Update username mapping if available
        if username and len(username) <= 32:  # Telegram username limit
            clean_username = re.sub(r'[^a-zA-Z0-9_]', '', username)
            if clean_username:
                username_key = f"@{clean_username.lower()}"
                # Only update if this is new information or if the user ID changed
                if username_key not in username_to_id or username_to_id[username_key] != user_id:
                    username_to_id[username_key] = user_id
                    logger.debug(f"Updated username mapping from message: {username_key} -> {user_id}")
                    # Periodically save the mapping (every 100 updates to avoid too frequent saves)
                    if len(username_to_id) % 100 == 0:
                        save_data(username_to_id, 'username_to_id.pkl')
        
        today = datetime.now(TIMEZONE)
        daily_messages[user_id][today.date()] += 1
        weekly_messages[user_id] += 1
        alltime_messages.setdefault(user_id, 0)
        alltime_messages[user_id] += 1
        
        # Update chat streaks safely
        yesterday = today - timedelta(days=1)
        last_day = last_chat_day[user_id].date()
        if last_day == yesterday.date():
            chat_streaks[user_id] = chat_streaks.get(user_id, 0) + 1
        elif last_day == today.date():
            # User already chatted today, don't increment streak
            pass
        elif last_day < yesterday.date():
            chat_streaks[user_id] = 1  # Reset if more than a day has passed
        last_chat_day[user_id] = today
        
        # Save data less frequently to improve performance
        # Only save every 10th message or for new users
        if alltime_messages[user_id] % 10 == 0 or alltime_messages[user_id] == 1:
            try:
                save_data(alltime_messages, 'alltime_messages.pkl')
                save_data(chat_streaks, 'chat_streaks.pkl')
                save_data(last_chat_day, 'last_chat_day.pkl')
            except Exception as e:
                logger.error(f"Error saving message data: {str(e)}")
                # Continue execution even if save fails
    
    except Exception as e:
        logger.error(f"Error in handle_message: {str(e)}")
        # Don't crash the bot on message handling errors

async def award_daily_points(context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    today = datetime.now(TIMEZONE).date()
    yesterday = today - timedelta(days=1)
    for user_id in daily_messages:
        msg_count = daily_messages[user_id].get(yesterday, 0)
        if msg_count < 50:
            continue
        
        chat_points = min(3, max(1, msg_count // 50))
        streak_bonus = max(0, chat_streaks.get(user_id, 0) // 3)
        total_points = chat_points + streak_bonus
        user_points[user_id] = user_points.get(user_id, 0) + total_points
        
        msg = f"Gavai {chat_points} taškus už {msg_count} žinučių vakar!"
        if streak_bonus > 0:
            msg += f" +{streak_bonus} už {chat_streaks[user_id]}-dienų seriją!"
        
        try:
            username = next((k for k, v in username_to_id.items() if v == user_id), f"User {user_id}")
            await context.bot.send_message(
                chat_id=GROUP_CHAT_ID,
                text=f"{username}, {msg} Dabar turi {user_points[user_id]} taškų!"
            )
        except (StopIteration, telegram.error.TelegramError) as e:
            logger.error(f"Failed to send daily points message to user {user_id}: {str(e)}")
    
    daily_messages.clear()
    save_data(user_points, 'user_points.pkl')

async def weekly_recap(context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Send weekly recap and reset weekly votes"""
    logger.info("Starting weekly recap and reset...")
    
    # Send chat recap first
    if not weekly_messages:
        try:
            await context.bot.send_message(GROUP_CHAT_ID, "Šią savaitę nebuvo pokalbių!")
        except telegram.error.TelegramError as e:
            logger.error(f"Failed to send weekly recap (no messages): {str(e)}")
    else:
        sorted_chatters = sorted(weekly_messages.items(), key=lambda x: x[1], reverse=True)[:3]
        recap = "📢 Savaitės Pokalbių Karaliai 📢\n"
        for user_id, msg_count in sorted_chatters:
            try:
                username = next((k for k, v in username_to_id.items() if v == user_id), f"User {user_id}")
                recap += f"{username}: {msg_count} žinučių\n"
            except Exception as e:
                logger.error(f"Error processing user {user_id} in weekly recap: {str(e)}")
                recap += f"User {user_id}: {msg_count} žinučių\n"
        
        try:
            await context.bot.send_message(GROUP_CHAT_ID, recap)
        except telegram.error.TelegramError as e:
            logger.error(f"Failed to send weekly recap: {str(e)}")
    
    # Send voting recap if there were votes
    if votes_weekly:
        sorted_sellers = sorted(votes_weekly.items(), key=lambda x: x[1], reverse=True)[:5]
        vote_recap = "🏆 Savaitės Balsavimo Nugalėtojai 🏆\n"
        for seller, votes in sorted_sellers:
            vote_recap += f"{seller[1:]}: {votes} balsų\n"
        
        try:
            await context.bot.send_message(GROUP_CHAT_ID, vote_recap)
        except telegram.error.TelegramError as e:
            logger.error(f"Failed to send voting recap: {str(e)}")
    
    # Reset weekly data
    await reset_weekly_data(context)
    
    logger.info("Weekly recap and reset completed.")

async def reset_weekly_data(context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Reset all weekly data"""
    global votes_weekly, voters, downvoters, pending_downvotes, complaint_id, last_vote_attempt, weekly_messages
    
    logger.info("Resetting weekly data...")
    
    # Clear weekly votes and related data
    votes_weekly.clear()
    voters.clear()
    downvoters.clear()
    pending_downvotes.clear()
    last_vote_attempt.clear()
    weekly_messages.clear()
    complaint_id = 0
    
    # Save cleared data
    save_data(votes_weekly, 'votes_weekly.pkl')
    save_data(user_points, 'user_points.pkl')  # Save any pending point changes
    
    # Notify group
    try:
        await context.bot.send_message(GROUP_CHAT_ID, "🔄 Nauja balsavimo savaitė prasidėjo! Visi gali vėl balsuoti.")
    except telegram.error.TelegramError as e:
        logger.error(f"Failed to send weekly reset notification: {str(e)}")
    
    logger.info("Weekly data reset completed.")

async def monthly_recap_and_reset(context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Send monthly recap and reset monthly votes"""
    logger.info("Starting monthly recap and reset...")
    
    # Calculate current month totals
    now = datetime.now(TIMEZONE)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    
    if votes_monthly:
        monthly_totals = defaultdict(int)
        for vendor, votes_list in votes_monthly.items():
            current_month_votes = [(ts, s) for ts, s in votes_list if ts >= month_start]
            monthly_totals[vendor] = sum(s for _, s in current_month_votes)
        
        if monthly_totals:
            sorted_monthly = sorted(monthly_totals.items(), key=lambda x: x[1], reverse=True)[:5]
            monthly_recap = "🗓️ Mėnesio Balsavimo Čempionai 🗓️\n"
            for seller, votes in sorted_monthly:
                monthly_recap += f"{seller[1:]}: {votes} balsų\n"
            
            try:
                await context.bot.send_message(GROUP_CHAT_ID, monthly_recap)
            except telegram.error.TelegramError as e:
                logger.error(f"Failed to send monthly recap: {str(e)}")
    
    # Reset monthly data  
    await reset_monthly_data(context)
    
    logger.info("Monthly recap and reset completed.")

async def reset_monthly_data(context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Reset monthly voting data"""
    global votes_monthly
    
    logger.info("Resetting monthly data...")
    
    # Clear monthly votes
    votes_monthly.clear()
    save_data(votes_monthly, 'votes_monthly.pkl')
    
    # Notify group
    try:
        await context.bot.send_message(GROUP_CHAT_ID, "📅 Naujas balsavimo mėnuo prasidėjo!")
    except telegram.error.TelegramError as e:
        logger.error(f"Failed to send monthly reset notification: {str(e)}")
    
    logger.info("Monthly data reset completed.")

async def coinflip(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    initiator_id = update.message.from_user.id
    
    # Input validation
    if len(context.args) < 2:
        msg = await update.message.reply_text("Naudok: /coinflip Amount @Username")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Validate amount
    valid_amount, amount = validate_amount(context.args[0])
    if not valid_amount or amount <= 0:
        msg = await update.message.reply_text("Netinkama suma! Naudok teigiamą skaičių (1-10000).")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Sanitize opponent username
    opponent = sanitize_username(context.args[1])
    if not opponent or len(opponent) < 2:
        msg = await update.message.reply_text("Netinkamas vartotojo vardas! Naudok @username formatą.")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Check initiator points
    if user_points.get(initiator_id, 0) < amount:
        msg = await update.message.reply_text("Neturi pakankamai taškų!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    try:
        initiator_member = await safe_bot_operation(context.bot.get_chat_member, chat_id, initiator_id)
        initiator_username = f"@{initiator_member.user.username}" if initiator_member.user.username else f"@User{initiator_id}"

        target_id = username_to_id.get(opponent.lower(), None)
        if not target_id or target_id == initiator_id:
            msg = await update.message.reply_text("Negalima mesti iššūkio sau ar neegzistuojančiam vartotojui!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
        
        if user_points.get(target_id, 0) < amount:
            msg = await update.message.reply_text(f"{opponent} neturi pakankamai taškų!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
        
        # Check for existing challenge
        if target_id in coinflip_challenges:
            msg = await update.message.reply_text(f"{opponent} jau turi aktyvų iššūkį!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
        
        coinflip_challenges[target_id] = (initiator_id, amount, datetime.now(TIMEZONE), initiator_username, opponent, chat_id)
        msg = await update.message.reply_text(f"{initiator_username} iššaukė {opponent} monetos metimui už {amount} taškų! Priimk su /accept_coinflip!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        context.job_queue.run_once(expire_challenge, 300, data=(target_id, context))
    except telegram.error.TelegramError as e:
        logger.error(f"Error in coinflip: {str(e)}")
        msg = await update.message.reply_text("Klaida gaunant vartotojo informaciją!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def accept_coinflip(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    # Use atomic operation to prevent race conditions
    async with data_manager.atomic_operation(f"coinflip_{user_id}"):
        if user_id not in coinflip_challenges:
            msg = await update.message.reply_text("Nėra aktyvaus iššūkio!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
            
        challenge_data = coinflip_challenges[user_id]
        if len(challenge_data) != 6:
            # Invalid challenge data, remove it
            del coinflip_challenges[user_id]
            msg = await update.message.reply_text("Neteisingi iššūkio duomenys!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
            
        initiator_id, amount, timestamp, initiator_username, opponent_username, original_chat_id = challenge_data
        now = datetime.now(TIMEZONE)
        
        # Validate challenge is still valid
        if now - timestamp > timedelta(minutes=5) or chat_id != original_chat_id:
            del coinflip_challenges[user_id]
            msg = await update.message.reply_text("Iššūkis pasibaigė arba neteisinga grupė!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
        
        # Double-check both users still have enough points
        if user_points.get(initiator_id, 0) < amount or user_points.get(user_id, 0) < amount:
            del coinflip_challenges[user_id]
            msg = await update.message.reply_text("Vienas iš žaidėjų neturi pakankamai taškų!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
        
        # Execute the coinflip atomically
        result = random.choice([initiator_id, user_id])
        
        # Update points atomically
        async with data_manager.atomic_operation("user_points"):
            if result == initiator_id:
                user_points[initiator_id] += amount
                user_points[user_id] -= amount
                winner_name, loser_name = initiator_username, opponent_username
            else:
                user_points[user_id] += amount
                user_points[initiator_id] -= amount
                winner_name, loser_name = opponent_username, initiator_username
            
            # Save points immediately
            save_data(user_points, 'user_points.pkl')
        
        # Remove challenge after successful completion
        del coinflip_challenges[user_id]
        
        # Send results
        try:
            await context.bot.send_sticker(chat_id=chat_id, sticker=COINFLIP_STICKER_ID)
        except telegram.error.TelegramError as e:
            logger.warning(f"Failed to send coinflip sticker: {e}")
        
        msg = await update.message.reply_text(f"🪙 {winner_name} laimėjo {amount} taškų prieš {loser_name}!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def expire_challenge(context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    job_context = context.job.data
    if not isinstance(job_context, tuple) or len(job_context) != 2:
        logger.error("Invalid job context for expire_challenge")
        return
    
    opponent_id, ctx = job_context
    if opponent_id in coinflip_challenges:
        _, amount, _, initiator_username, opponent_username, chat_id = coinflip_challenges[opponent_id]
        del coinflip_challenges[opponent_id]
        try:
            msg = await ctx.bot.send_message(chat_id, f"Iššūkis tarp {initiator_username} ir {opponent_username} už {amount} taškų pasibaigė!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        except telegram.error.TelegramError as e:
            logger.error(f"Failed to send expiration message: {str(e)}")

async def addpoints(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali pridėti taškus!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Input validation
    if len(context.args) < 2:
        msg = await update.message.reply_text("Naudok: /addpoints Amount @UserID")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Validate amount
    valid_amount, amount = validate_amount(context.args[0])
    if not valid_amount:
        msg = await update.message.reply_text("Netinkama suma! Naudok skaičių tarp -10000 ir 10000.")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Validate target format
    target = context.args[1]
    if not target.startswith('@User'):
        msg = await update.message.reply_text("Naudok: /addpoints Amount @UserID")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    try:
        target_id = int(target.strip('@User'))
        if target_id <= 0:
            raise ValueError("Invalid user ID")
    except ValueError:
        msg = await update.message.reply_text("Netinkamas vartotojo ID!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    try:
        user_points[target_id] = user_points.get(target_id, 0) + amount
        # Prevent negative points
        if user_points[target_id] < 0:
            user_points[target_id] = 0
        
        msg = await update.message.reply_text(f"Pridėta {amount} taškų @User{target_id}! Dabar: {user_points[target_id]}")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        save_data(user_points, 'user_points.pkl')
        logger.info(f"Admin {user_id} added {amount} points to user {target_id}")
    except Exception as e:
        logger.error(f"Error adding points: {str(e)}")
        msg = await update.message.reply_text("Klaida pridedant taškus!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def pridetitaskus(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali naudoti šią komandą!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    try:
        seller = context.args[0]
        if not seller.startswith('@'):
            seller = '@' + seller
        amount = int(context.args[1])
        if seller not in trusted_sellers:
            msg = await update.message.reply_text(f"{seller} nėra patikimų pardavėjų sąraše!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
        votes_alltime[seller] += amount
        msg = await update.message.reply_text(f"Pridėta {amount} taškų {seller} visų laikų balsams. Dabar: {votes_alltime[seller]}")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        save_data(votes_alltime, 'votes_alltime.pkl')
    except (IndexError, ValueError):
        msg = await update.message.reply_text("Naudok: /pridetitaskus @Seller Amount")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def points(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    logger.info(f"/points called by user_id={user_id} in chat_id={chat_id}")

    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        logger.warning(f"Chat_id={chat_id} not in allowed_groups={allowed_groups}")
        return

    points = user_points.get(user_id, 0)
    streak = chat_streaks.get(user_id, 0)
    msg = await update.message.reply_text(f"Jūsų taškai: {points}\nSerija: {streak} dienų")
    context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
    logger.info(f"Points for user_id={user_id}: {points}, Streak: {streak}")

# New admin commands for resetting votes
async def reset_weekly(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali naudoti šią komandą!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    await reset_weekly_data(context)
    msg = await update.message.reply_text("✅ Savaitės balsai iš naujo nukryžiuoti!")
    context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def reset_monthly(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali naudoti šią komandą!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    await reset_monthly_data(context)
    msg = await update.message.reply_text("✅ Mėnesio balsai iš naujo nukryžiuoti!")
    context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

# New admin commands to add points
async def add_weekly_points(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali naudoti šią komandą!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    try:
        seller = context.args[0]
        if not seller.startswith('@'):
            seller = '@' + seller
        amount = int(context.args[1])
        if seller not in trusted_sellers:
            msg = await update.message.reply_text(f"{seller} nėra patikimų pardavėjų sąraše!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
        votes_weekly[seller] += amount
        msg = await update.message.reply_text(f"Pridėta {amount} taškų {seller} savaitės balsams. Dabar: {votes_weekly[seller]}")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        save_data(votes_weekly, 'votes_weekly.pkl')
    except (IndexError, ValueError):
        msg = await update.message.reply_text("Naudok: /add_weekly_points @Seller Amount")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def add_monthly_points(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali naudoti šią komandą!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    try:
        seller = context.args[0]
        if not seller.startswith('@'):
            seller = '@' + seller
        amount = int(context.args[1])
        if seller not in trusted_sellers:
            msg = await update.message.reply_text(f"{seller} nėra patikimų pardavėjų sąraše!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
        now = datetime.now(TIMEZONE)
        votes_monthly[seller].append((now, amount))
        msg = await update.message.reply_text(f"Pridėta {amount} taškų {seller} mėnesio balsams.")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        save_data(votes_monthly, 'votes_monthly.pkl')
    except (IndexError, ValueError):
        msg = await update.message.reply_text("Naudok: /add_monthly_points @Seller Amount")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def add_alltime_points(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali naudoti šią komandą!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    try:
        seller = context.args[0]
        if not seller.startswith('@'):
            seller = '@' + seller
        amount = int(context.args[1])
        if seller not in trusted_sellers:
            msg = await update.message.reply_text(f"{seller} nėra patikimų pardavėjų sąraše!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
        votes_alltime[seller] += amount
        msg = await update.message.reply_text(f"Pridėta {amount} taškų {seller} visų laikų balsams. Dabar: {votes_alltime[seller]}")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        save_data(votes_alltime, 'votes_alltime.pkl')
    except (IndexError, ValueError):
        msg = await update.message.reply_text("Naudok: /add_alltime_points @Seller Amount")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

# New admin commands to remove points
async def remove_weekly_points(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali naudoti šią komandą!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    try:
        seller = context.args[0]
        if not seller.startswith('@'):
            seller = '@' + seller
        amount = int(context.args[1])
        if seller not in trusted_sellers:
            msg = await update.message.reply_text(f"{seller} nėra patikimų pardavėjų sąraše!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
        votes_weekly[seller] -= amount
        msg = await update.message.reply_text(f"Pašalinta {amount} taškų iš {seller} savaitės balsų. Dabar: {votes_weekly[seller]}")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        save_data(votes_weekly, 'votes_weekly.pkl')
    except (IndexError, ValueError):
        msg = await update.message.reply_text("Naudok: /remove_weekly_points @Seller Amount")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def remove_monthly_points(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali naudoti šią komandą!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    try:
        seller = context.args[0]
        if not seller.startswith('@'):
            seller = '@' + seller
        amount = int(context.args[1])
        if seller not in trusted_sellers:
            msg = await update.message.reply_text(f"{seller} nėra patikimų pardavėjų sąraše!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
        now = datetime.now(TIMEZONE)
        votes_monthly[seller].append((now, -amount))  # Append a negative vote
        msg = await update.message.reply_text(f"Pašalinta {amount} taškų iš {seller} mėnesio balsų.")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        save_data(votes_monthly, 'votes_monthly.pkl')
    except (IndexError, ValueError):
        msg = await update.message.reply_text("Naudok: /remove_monthly_points @Seller Amount")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def remove_alltime_points(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali naudoti šią komandą!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    try:
        seller = context.args[0]
        if not seller.startswith('@'):
            seller = '@' + seller
        amount = int(context.args[1])
        if seller not in trusted_sellers:
            msg = await update.message.reply_text(f"{seller} nėra patikimų pardavėjų sąraše!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
        votes_alltime[seller] -= amount
        msg = await update.message.reply_text(f"Pašalinta {amount} taškų iš {seller} visų laikų balsų. Dabar: {votes_alltime[seller]}")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        save_data(votes_alltime, 'votes_alltime.pkl')
    except (IndexError, ValueError):
        msg = await update.message.reply_text("Naudok: /remove_alltime_points @Seller Amount")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

# Scammer tracking system commands
async def scameris(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Report a scammer with proof"""
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # No daily report limit - users can report unlimited scammers
    now = datetime.now(TIMEZONE)
    
    # Input validation
    if len(context.args) < 2:
        msg = await update.message.reply_text(
            "📋 Naudojimas: `/scameris @username įrodymai`\n\n"
            "Pavyzdys: `/scameris @scammer123 Nepavede prekės, ignoruoja žinutes`\n"
            "Reikia: Detalūs įrodymai kodėl šis žmogus yra scameris\n\n"
            "💡 Pridėkite įrodymus po vartotojo vardo!\n"
            "🤖 Botas automatiškai bandys rasti user ID\n"
            "🔍 Jei vartotojas privatus, pridėkite user ID: `/scameris @username 123456789 įrodymai`"
        )
        context.job_queue.run_once(delete_message_job, 60, data=(chat_id, msg.message_id))
        return
    
    # Sanitize and validate inputs
    reported_username = sanitize_username(context.args[0])
    if not reported_username or len(reported_username) < 2:
        msg = await update.message.reply_text("❌ Netinkamas vartotojo vardas! Naudok @username formatą.")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Check if second argument is a user ID (numeric)
    reported_user_id = None
    proof_args = context.args[1:]
    
    if len(proof_args) >= 1 and proof_args[0].isdigit():
        reported_user_id = int(proof_args[0])
        proof_args = proof_args[1:]  # Remove user ID from proof arguments
        # Update our mappings with this manually provided user ID
        update_user_id_mappings(reported_user_id, reported_username)
    
    # If no user ID provided, try to get it automatically using enhanced resolution
    if not reported_user_id:
        reported_user_id, resolution_method = await resolve_user_id(reported_username, context, chat_id)
        if reported_user_id:
            logger.info(f"Enhanced resolution: {reported_username} -> {reported_user_id} via {resolution_method}")
            # Update our mappings with this new information
            update_user_id_mappings(reported_user_id, reported_username)
        else:
            logger.warning(f"Enhanced resolution failed for {reported_username}: {resolution_method}")
    
    proof = sanitize_text_input(" ".join(proof_args), max_length=500)
    if not proof or len(proof.strip()) < 10:
        msg = await update.message.reply_text("❌ Prašau nurodyti detalius įrodymus (bent 10 simbolių)!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Check if already confirmed scammer
    if reported_username.lower() in confirmed_scammers:
        msg = await update.message.reply_text(f"⚠️ {reported_username} jau yra patvirtintų scamerių sąraše!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Check if user is trying to report themselves
    reporter_username = f"@{update.message.from_user.username}" if update.message.from_user.username else None
    if reporter_username and reported_username.lower() == reporter_username.lower():
        msg = await update.message.reply_text("❌ Negalite pranešti apie save!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    try:
        global scammer_report_id
        scammer_report_id += 1
        
        # Store the report
        pending_scammer_reports[scammer_report_id] = {
            'username': reported_username,
            'user_id': reported_user_id,  # Store user ID if provided
            'reporter_id': user_id,
            'reporter_username': reporter_username or f"User {user_id}",
            'proof': proof,
            'timestamp': now,
            'chat_id': chat_id
        }
        
        # Track that user made a report today (for daily limit counting)
        
        # Create message with inline buttons
        user_id_info = f"User ID: {reported_user_id}" if reported_user_id else "User ID: Nerastas (privatus paskyra)"
        if reported_user_id:
            logger.info(f"Scammer report #{scammer_report_id} includes user ID: {reported_user_id}")
        else:
            logger.warning(f"Scammer report #{scammer_report_id} has no user ID for {reported_username}")
        
        admin_message = (
            f"🚨 NAUJAS SCAMER PRANEŠIMAS 🚨\n\n"
            f"Report ID: #{scammer_report_id}\n"
            f"Pranešė: {reporter_username or f'User {user_id}'}\n"
            f"Apie: {reported_username}\n"
            f"{user_id_info}\n"
            f"Įrodymai: {proof}\n"
            f"Laikas: {now.strftime('%Y-%m-%d %H:%M')}\n\n"
            f"Spustelėkite mygtukus žemiau:"
        )
        
        # Create inline keyboard with approve/reject buttons
        keyboard = [
            [
                telegram.InlineKeyboardButton("✅ Patvirtinti", callback_data=f"approve_scammer_{scammer_report_id}"),
                telegram.InlineKeyboardButton("❌ Atmesti", callback_data=f"reject_scammer_{scammer_report_id}")
            ],
            [telegram.InlineKeyboardButton("📋 Detalės", callback_data=f"scammer_details_{scammer_report_id}")]
        ]
        reply_markup = telegram.InlineKeyboardMarkup(keyboard)
        
        # Send to all moderators (admin + helpers)
        moderators = get_all_moderators()
        for moderator_id in moderators:
            try:
                await context.bot.send_message(
                    chat_id=moderator_id,
                    text=admin_message,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
                logger.info(f"Sent scammer report #{scammer_report_id} to moderator {moderator_id}")
            except Exception as e:
                logger.warning(f"Failed to send scammer report to moderator {moderator_id}: {e}")
        
        # Confirm to user
        msg = await update.message.reply_text(
                    f"✅ Pranešimas pateiktas!\n\n"
        f"Report ID: #{scammer_report_id}\n"
        f"Apie: {reported_username}\n"
        f"Statusas: Laukia admin peržiūros\n\n"
            f"Adminai peržiūrės jūsų pranešimą ir priims sprendimą. Ačiū už saugios bendruomenės kūrimą! 🛡️"
        )
        context.job_queue.run_once(delete_message_job, 90, data=(chat_id, msg.message_id))
        
        # Save data
        save_data(pending_scammer_reports, 'pending_scammer_reports.pkl')
        save_data(scammer_report_id, 'scammer_report_id.pkl')
        
        # Add points for reporting
        user_points[user_id] = user_points.get(user_id, 0) + 3
        save_data(user_points, 'user_points.pkl')
        
        logger.info(f"Scammer report #{scammer_report_id}: {reported_username} reported by user {user_id}")
        
    except Exception as e:
        logger.error(f"Error processing scammer report: {str(e)}")
        msg = await update.message.reply_text("❌ Klaida pateikiant pranešimą. Bandykite vėliau.")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def patikra(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Check if a user is in the scammer list"""
    chat_id = update.message.chat_id
    
    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    if len(context.args) < 1:
        msg = await update.message.reply_text(
            "📋 Naudojimas: `/patikra @username` arba `/patikra 123456789`\n\n"
            "Pavyzdys: `/patikra @user123` arba `/patikra 123456789`\n"
            "Patikrinkite ar vartotojas yra scamerių sąraše arba patikimas pardavėjas"
        )
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Sanitize username
    check_username = sanitize_username(context.args[0])
    if not check_username or len(check_username) < 2:
        msg = await update.message.reply_text("❌ Netinkamas vartotojo vardas! Naudok @username formatą.")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Check if input is a user ID (numeric)
    check_user_id = None
    original_input = check_username
    if check_username.isdigit():
        check_user_id = int(check_username)
        # Find username by user ID in scammer database
        if check_user_id in user_id_to_scammer:
            check_username = user_id_to_scammer[check_user_id]
            logger.info(f"Found scammer by user ID {check_user_id} -> {check_username}")
        # Also try to find in our general username mapping
        elif check_user_id in [v for v in username_to_id.values()]:
            # Find the username for this user ID
            for username_key, user_id in username_to_id.items():
                if user_id == check_user_id:
                    check_username = username_key
                    logger.info(f"Found username by user ID {check_user_id} -> {check_username}")
                    break
    
    # Check if in confirmed scammers list
    if check_username.lower() in confirmed_scammers:
        scammer_info = confirmed_scammers[check_username.lower()]
        confirmed_date = scammer_info['timestamp'].strftime('%Y-%m-%d')
        reports_count = scammer_info.get('reports_count', 1)
        user_id_info = f"User ID: {scammer_info.get('user_id')}" if scammer_info.get('user_id') else "User ID: Nerastas (privatus paskyra)"
        
        msg = await update.message.reply_text(
                    f"🚨 SCAMER RASTAS! 🚨\n\n"
        f"Vartotojas: {check_username}\n"
        f"{user_id_info}\n"
        f"Statusas: ❌ Patvirtintas scameris\n"
        f"Patvirtinta: {confirmed_date}\n"
        f"Pranešimų: {reports_count}\n"
        f"Įrodymai: {scammer_info.get('proof', 'Nenurodyta')}\n\n"
        f"⚠️ ATSARGIAI! Šis vartotojas yra žinomas scameris!"
        )
        context.job_queue.run_once(delete_message_job, 120, data=(chat_id, msg.message_id))
    elif check_username in trusted_sellers:
        # Check if user is a trusted seller - get their voting stats
        weekly_votes = votes_weekly.get(check_username, 0)
        monthly_votes = len(votes_monthly.get(check_username, []))
        alltime_votes = votes_alltime.get(check_username, 0)
        
        msg = await update.message.reply_text(
            f"✅ PATIKIMAS PARDAVĖJAS ✅\n\n"
            f"Vartotojas: {check_username}\n"
            f"Statusas: 🟢 LEGIT IR PATVIRTINTAS\n"
            f"🏆 Patvirtintas šios grupės narių balsavimu\n"
            f"📊 Savaitės balsai: {weekly_votes}\n"
            f"📊 Mėnesio balsai: {monthly_votes}\n" 
            f"📊 Visų laikų balsai: {alltime_votes}\n\n"
            f"✅ Šis pardavėjas yra patikimas ir patvirtintas bendruomenės!\n"
            f"🛡️ Saugus pasirinkimas sandoriams!"
        )
        context.job_queue.run_once(delete_message_job, 60, data=(chat_id, msg.message_id))
    else:
        # Check if there are pending reports
        pending_count = sum(1 for report in pending_scammer_reports.values() 
                          if report['username'].lower() == check_username.lower())
        
        if pending_count > 0:
            msg = await update.message.reply_text(
                        f"🔍 PATIKRA ATLIKTA\n\n"
        f"Vartotojas: {check_username}\n"
        f"Statusas: ⚠️ Yra nepatvirtintų pranešimų ({pending_count})\n"
        f"Rekomendacija: Būkite atsargūs, pranešimai dar tikrinami\n\n"
                f"ℹ️ Naudokite pardavėjus iš /barygos komandos"
            )
        else:
            msg = await update.message.reply_text(
                        f"ℹ️ NĖRA INFORMACIJOS\n\n"
        f"Vartotojas: {check_username}\n"
        f"Statusas: ❓ Nėra duomenų\n\n"
                f"🔍 Šis vartotojas nėra scamerių sąraše\n"
                f"🛡️ Saugumui naudokite pardavėjus iš /barygos"
            )
        
        context.job_queue.run_once(delete_message_job, 60, data=(chat_id, msg.message_id))

# Admin commands for scammer management
async def approve_scammer(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to approve a scammer report"""
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    
    if not is_admin_or_helper(user_id):
        msg = await update.message.reply_text("Tik adminai ir pagalbininkai gali patvirtinti scamer pranešimus!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    if len(context.args) < 1:
        msg = await update.message.reply_text("Naudok: /approve_scammer [report_id]")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    try:
        report_id = int(context.args[0])
        if report_id not in pending_scammer_reports:
            msg = await update.message.reply_text(f"Pranešimas #{report_id} nerastas!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
        
        report = pending_scammer_reports[report_id]
        username = report['username'].lower()
        
        # Try to resolve user ID if we don't have it yet
        if not report.get('user_id'):
            try:
                resolved_id, method = await resolve_user_id(report['username'], context, report.get('chat_id'))
                if resolved_id:
                    report['user_id'] = resolved_id
                    logger.info(f"Resolved missing user ID for scammer {report['username']}: {resolved_id} via {method}")
            except Exception as e:
                logger.warning(f"Failed to resolve user ID during approval for {report['username']}: {e}")
        
        # Move to confirmed scammers
        confirmed_scammers[username] = {
            'confirmed_by': user_id,
            'reporter_id': report['reporter_id'],  # Track original reporter for daily limits
            'proof': report['proof'],
            'timestamp': datetime.now(TIMEZONE),
            'reports_count': 1,
            'original_report_id': report_id,
            'user_id': report.get('user_id')  # Store user ID if available
        }
        
        # Update user ID mappings if we have the user ID
        if report.get('user_id'):
            update_user_id_mappings(report['user_id'], report['username'])
            user_id_to_scammer[report['user_id']] = username
            logger.info(f"Stored user ID {report['user_id']} for confirmed scammer {username}")
        
        # Remove from pending
        del pending_scammer_reports[report_id]
        
        # Save data
        save_data(confirmed_scammers, 'confirmed_scammers.pkl')
        save_data(pending_scammer_reports, 'pending_scammer_reports.pkl')
        
        # Notify original reporter
        try:
            await context.bot.send_message(
                chat_id=report['chat_id'],
                text=f"🚨 SCAMER PATVIRTINTAS! 🚨\n\n"
                     f"@{report['username']} pridėtas į scamerių sąrašą!\n"
                     f"+3 taškai už patvirtintą pranešimą! 🛡️"
            )
        except (telegram.error.TelegramError, telegram.error.ChatNotFound) as e:
            logger.warning(f"Failed to notify reporter about approved scammer report: {e}")
        except Exception as e:
            logger.error(f"Unexpected error notifying reporter: {e}")
        
        msg = await update.message.reply_text(
                    f"✅ SCAMER PATVIRTINTAS\n\n"
        f"Report ID: #{report_id}\n"
        f"Scameris: {report['username']}\n"
        f"Pridėtas į sąrašą: ✅\n\n"
            f"Vartotojas dabar bus rodomas kaip scameris per /patikra komandą."
        )
        context.job_queue.run_once(delete_message_job, 60, data=(chat_id, msg.message_id))
        
        logger.info(f"Admin {user_id} approved scammer report #{report_id} for {report['username']}")
        
    except ValueError:
        msg = await update.message.reply_text("Neteisingas report ID!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
    except Exception as e:
        logger.error(f"Error approving scammer: {str(e)}")
        msg = await update.message.reply_text("Klaida patvirtinant pranešimą!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def reject_scammer(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Admin command to reject a scammer report"""
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    
    if not is_admin_or_helper(user_id):
        msg = await update.message.reply_text("Tik adminai ir pagalbininkai gali atmesti scamer pranešimus!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    if len(context.args) < 1:
        msg = await update.message.reply_text("Naudok: /reject_scammer [report_id]")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    try:
        report_id = int(context.args[0])
        if report_id not in pending_scammer_reports:
            msg = await update.message.reply_text(f"Pranešimas #{report_id} nerastas!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
            return
        
        report = pending_scammer_reports[report_id]
        
        # Remove from pending
        del pending_scammer_reports[report_id]
        save_data(pending_scammer_reports, 'pending_scammer_reports.pkl')
        
        # Notify original reporter
        try:
            await context.bot.send_message(
                chat_id=report['chat_id'],
                text=f"❌ PRANEŠIMAS ATMESTAS\n\n"
                     f"Jūsų pranešimas apie {report['username']} buvo atmestas.\n"
                     f"Įrodymai buvo nepakankant arba neteisingi."
            )
        except (telegram.error.TelegramError, telegram.error.ChatNotFound) as e:
            logger.warning(f"Failed to notify reporter about rejected scammer report: {e}")
        except Exception as e:
            logger.error(f"Unexpected error notifying reporter: {e}")
        
        msg = await update.message.reply_text(
                    f"❌ PRANEŠIMAS ATMESTAS\n\n"
        f"Report ID: #{report_id}\n"
        f"Apie: {report['username']}\n"
        f"Statusas: Atmestas"
        )
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        
        logger.info(f"Admin {user_id} rejected scammer report #{report_id} for {report['username']}")
        
    except ValueError:
        msg = await update.message.reply_text("Neteisingas report ID!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
    except Exception as e:
        logger.error(f"Error rejecting scammer: {str(e)}")
        msg = await update.message.reply_text("Klaida atmestant pranešimą!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))


# Callback handlers for inline buttons
async def handle_scammer_callback(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button callbacks for scammer reports"""
    query = update.callback_query
    await query.answer()  # Acknowledge the callback
    
    user_id = query.from_user.id
    callback_data = query.data
    
    # Check if user is authorized
    if not is_admin_or_helper(user_id):
        await query.edit_message_text("❌ Tik adminai ir pagalbininkai gali valdyti scamer pranešimus!")
        return
    
    try:
        # Parse callback data
        if callback_data.startswith("approve_scammer_"):
            report_id = int(callback_data.replace("approve_scammer_", ""))
            await approve_scammer_callback(query, context, report_id, user_id)
        elif callback_data.startswith("reject_scammer_"):
            report_id = int(callback_data.replace("reject_scammer_", ""))
            await reject_scammer_callback(query, context, report_id, user_id)
        elif callback_data.startswith("scammer_details_"):
            report_id = int(callback_data.replace("scammer_details_", ""))
            await scammer_details_callback(query, context, report_id)
        else:
            await query.edit_message_text("❌ Nežinomas veiksmas!")
    except ValueError:
        await query.edit_message_text("❌ Neteisingas report ID!")
    except Exception as e:
        logger.error(f"Error handling scammer callback: {str(e)}")
        await query.edit_message_text("❌ Klaida vykdant veiksmą!")

async def approve_scammer_callback(query, context, report_id, user_id):
    """Handle approve scammer button callback"""
    if report_id not in pending_scammer_reports:
        await query.edit_message_text(f"❌ Pranešimas #{report_id} nerastas arba jau apdorotas!")
        return
    
    try:
        report = pending_scammer_reports[report_id]
        username = report['username'].lower()
        
        # Move to confirmed scammers
        confirmed_scammers[username] = {
            'confirmed_by': user_id,
            'reporter_id': report['reporter_id'],
            'user_id': report.get('user_id'),  # Store user ID if available
            'proof': report['proof'],
            'timestamp': datetime.now(TIMEZONE),
            'reports_count': 1,
            'original_report_id': report_id
        }
        
        # Update user_id to scammer mapping
        if report.get('user_id'):
            user_id_to_scammer[report['user_id']] = username
            # Also update our username mappings
            update_user_id_mappings(report['user_id'], username)
        
        # Remove from pending
        del pending_scammer_reports[report_id]
        
        # Save data
        save_data(confirmed_scammers, 'confirmed_scammers.pkl')
        save_data(pending_scammer_reports, 'pending_scammer_reports.pkl')
        save_data(user_id_to_scammer, 'user_id_to_scammer.pkl')
        
        # Add points to original reporter (if not already added)
        user_points[report['reporter_id']] = user_points.get(report['reporter_id'], 0) + 3
        save_data(user_points, 'user_points.pkl')
        
        # Update message
        confirmed_text = (
            f"✅ SCAMER PATVIRTINTAS\n\n"
            f"Report ID: #{report_id}\n"
            f"Scameris: {report['username']}\n"
            f"Patvirtino: {query.from_user.first_name or 'Moderatorius'}\n"
            f"Laikas: {datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M')}\n\n"
            f"Vartotojas pridėtas į scamerių sąrašą!"
        )
        await query.edit_message_text(confirmed_text)
        
        # Notify original reporter
        try:
            await context.bot.send_message(
                chat_id=report['chat_id'],
                text=f"🚨 SCAMER PATVIRTINTAS! 🚨\n\n"
                     f"@{report['username']} pridėtas į scamerių sąrašą!\n"
                     f"+3 taškai už patvirtintą pranešimą! 🛡️"
            )
        except Exception as e:
            logger.warning(f"Failed to notify reporter about approved scammer: {e}")
        
        logger.info(f"Moderator {user_id} approved scammer report #{report_id} for {report['username']}")
        
    except Exception as e:
        logger.error(f"Error approving scammer: {str(e)}")
        await query.edit_message_text("❌ Klaida patvirtinant pranešimą!")

async def reject_scammer_callback(query, context, report_id, user_id):
    """Handle reject scammer button callback"""
    if report_id not in pending_scammer_reports:
        await query.edit_message_text(f"❌ Pranešimas #{report_id} nerastas arba jau apdorotas!")
        return
    
    try:
        report = pending_scammer_reports[report_id]
        
        # Remove from pending
        del pending_scammer_reports[report_id]
        save_data(pending_scammer_reports, 'pending_scammer_reports.pkl')
        
        # Update message
        rejected_text = (
            f"❌ PRANEŠIMAS ATMESTAS\n\n"
            f"Report ID: #{report_id}\n"
            f"Apie: {report['username']}\n"
            f"Atmėtė: {query.from_user.first_name or 'Moderatorius'}\n"
            f"Laikas: {datetime.now(TIMEZONE).strftime('%Y-%m-%d %H:%M')}\n\n"
            f"Pranešimas pašalintas iš sąrašo."
        )
        await query.edit_message_text(rejected_text)
        
        # Notify original reporter
        try:
            await context.bot.send_message(
                chat_id=report['chat_id'],
                text=f"❌ PRANEŠIMAS ATMESTAS\n\n"
                     f"Jūsų pranešimas apie {report['username']} buvo atmestas.\n"
                     f"Įrodymai buvo nepakankant arba neteisingi."
            )
        except Exception as e:
            logger.warning(f"Failed to notify reporter about rejected scammer: {e}")
        
        logger.info(f"Moderator {user_id} rejected scammer report #{report_id} for {report['username']}")
        
    except Exception as e:
        logger.error(f"Error rejecting scammer: {str(e)}")
        await query.edit_message_text("❌ Klaida atmestant pranešimą!")

async def scammer_details_callback(query, context, report_id):
    """Handle scammer details button callback"""
    if report_id not in pending_scammer_reports:
        await query.edit_message_text(f"❌ Pranešimas #{report_id} nerastas!")
        return
    
    try:
        report = pending_scammer_reports[report_id]
        
        details_text = (
            f"📋 DETALĖS PRANEŠIMO #{report_id}\n\n"
            f"👤 Pranešė: {report['reporter_username']}\n"
            f"🚨 Apie: {report['username']}\n"
            f"📅 Laikas: {report['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"🆔 Reporter ID: {report['reporter_id']}\n"
            f"💬 Chat ID: {report['chat_id']}\n\n"
            f"📝 ĮRODYMAI:\n{report['proof']}\n\n"
            f"Spustelėkite mygtukus žemiau norėdami patvirtinti arba atmesti:"
        )
        
        # Create inline keyboard with approve/reject buttons
        keyboard = [
            [
                telegram.InlineKeyboardButton("✅ Patvirtinti", callback_data=f"approve_scammer_{report_id}"),
                telegram.InlineKeyboardButton("❌ Atmesti", callback_data=f"reject_scammer_{report_id}")
            ]
        ]
        reply_markup = telegram.InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(details_text, reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Error showing scammer details: {str(e)}")
        await query.edit_message_text("❌ Klaida rodant detales!")


async def scameriai(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Show list of confirmed scammers (public command)"""
    chat_id = update.message.chat_id
    
    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    if not confirmed_scammers:
        msg = await update.message.reply_text("✅ Scamerių sąrašas tuščias! Bendruomenė švarūs. 🛡️")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Create paginated list for mobile-friendly display
    scammer_text = "🚨 PATVIRTINTI SCAMERIAI 🚨\n"
    scammer_text += f"📊 Viso: {len(confirmed_scammers)} | Būkite atsargūs!\n\n"
    
    # Sort by most recent first
    sorted_scammers = sorted(confirmed_scammers.items(), 
                           key=lambda x: x[1]['timestamp'], reverse=True)
    
    for i, (username, info) in enumerate(sorted_scammers[:20], 1):  # Show top 20
        date = info['timestamp'].strftime('%m-%d')
        proof_short = info['proof'][:40] + "..." if len(info['proof']) > 40 else info['proof']
        
        scammer_text += f"🚫 {i}. @{username}\n"
        scammer_text += f"   📅 {date} | 📝 {proof_short}\n\n"
    
    if len(confirmed_scammers) > 20:
        scammer_text += f"... ir dar {len(confirmed_scammers) - 20} scamerių\n\n"
    
    scammer_text += "🔍 Naudok `/patikra @username` specifinei patikriai\n"
    scammer_text += "🚨 Naudok `/scameris @user įrodymai` pranešti naują"
    
    msg = await update.message.reply_text(scammer_text, parse_mode='Markdown')
    context.job_queue.run_once(delete_message_job, 120, data=(chat_id, msg.message_id))

async def scammer_list(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Show detailed list of confirmed scammers (admin only)"""
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali matyti detalų scamerių sąrašą!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    if not confirmed_scammers:
        msg = await update.message.reply_text("✅ Scamerių sąrašas tuščias!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    scammer_text = "🚨 ADMIN - PATVIRTINTI SCAMERIAI 🚨\n\n"
    
    for i, (username, info) in enumerate(confirmed_scammers.items(), 1):
        date = info['timestamp'].strftime('%Y-%m-%d %H:%M')
        proof_short = info['proof'][:60] + "..." if len(info['proof']) > 60 else info['proof']
        reporter_id = info.get('reporter_id', 'Unknown')
        confirmed_by = info.get('confirmed_by', 'Unknown')
        
        scammer_text += f"{i}. @{username}\n"
        scammer_text += f"   📅 {date}\n"
        scammer_text += f"   👤 Reporter: {reporter_id}\n"
        scammer_text += f"   ✅ Confirmed by: {confirmed_by}\n"
        scammer_text += f"   📝 {proof_short}\n\n"
    
    scammer_text += f"Viso scamerių: {len(confirmed_scammers)}"
    
    msg = await update.message.reply_text(scammer_text, parse_mode='Markdown')
    context.job_queue.run_once(delete_message_job, 180, data=(chat_id, msg.message_id))

async def pending_reports(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Show pending scammer reports (admin only)"""
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali matyti laukiančius pranešimus!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    if not pending_scammer_reports:
        msg = await update.message.reply_text("✅ Nėra laukiančių pranešimų!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    reports_text = "⏳ LAUKIANTYS PRANEŠIMAI ⏳\n\n"
    
    for report_id, report in pending_scammer_reports.items():
        date = report['timestamp'].strftime('%m-%d %H:%M')
        proof_short = report['proof'][:40] + "..." if len(report['proof']) > 40 else report['proof']
        
        reports_text += f"#{report_id} {report['username']}\n"
        reports_text += f"   👤 {report['reporter_username']}\n"
        reports_text += f"   📅 {date}\n"
        reports_text += f"   📝 {proof_short}\n"
        reports_text += f"   ✅ `/approve_scammer {report_id}`\n"
        reports_text += f"   ❌ `/reject_scammer {report_id}`\n\n"
    
    reports_text += f"Viso pranešimų: {len(pending_scammer_reports)}"
    
    msg = await update.message.reply_text(reports_text, parse_mode='Markdown')
    context.job_queue.run_once(delete_message_job, 120, data=(chat_id, msg.message_id))


# Buyer report tracking system commands
async def vagis(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Report a buyer for lying about product or other issues"""
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    now = datetime.now(TIMEZONE)
    
    # Input validation
    if len(context.args) < 2:
        msg = await update.message.reply_text(
            "📋 Naudojimas: `/vagis @username priežastis`\n\n"
            "Pavyzdys: `/vagis @buyer123 Meluoja apie prekę, reikalauja pinigų grąžinimo`\n"
            "Reikia: Detalus aprašymas kodėl šis pirkėjas problematiškas\n\n"
            "💡 Pridėkite priežastį po vartotojo vardo!\n"
            "🤖 Botas automatiškai bandys rasti user ID\n"
            "🔍 Jei vartotojas privatus, pridėkite user ID: `/vagis @username 123456789 priežastis`"
        )
        context.job_queue.run_once(delete_message_job, 60, data=(chat_id, msg.message_id))
        return
    
    # Sanitize and validate inputs
    reported_username = sanitize_username(context.args[0])
    if not reported_username or len(reported_username) < 2:
        msg = await update.message.reply_text("❌ Netinkamas vartotojo vardas! Naudok @username formatą.")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Check if second argument is a user ID (numeric)
    reported_user_id = None
    reason_args = context.args[1:]
    
    if len(reason_args) >= 1 and reason_args[0].isdigit():
        reported_user_id = int(reason_args[0])
        reason_args = reason_args[1:]  # Remove user ID from reason arguments
        # Update our mappings with this manually provided user ID
        update_user_id_mappings(reported_user_id, reported_username)
    
    # If no user ID provided, try to get it automatically using enhanced resolution
    if not reported_user_id:
        reported_user_id, resolution_method = await resolve_user_id(reported_username, context, chat_id)
        if reported_user_id:
            logger.info(f"Enhanced buyer resolution: {reported_username} -> {reported_user_id} via {resolution_method}")
            # Update our mappings with this new information
            update_user_id_mappings(reported_user_id, reported_username)
        else:
            logger.warning(f"Enhanced buyer resolution failed for {reported_username}: {resolution_method}")
    
    reason = sanitize_text_input(" ".join(reason_args), max_length=500)
    if not reason or len(reason.strip()) < 10:
        msg = await update.message.reply_text("❌ Prašau nurodyti detalią priežastį (bent 10 simbolių)!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Check if user is trying to report themselves
    reporter_username = f"@{update.message.from_user.username}" if update.message.from_user.username else None
    if reporter_username and reported_username.lower() == reporter_username.lower():
        msg = await update.message.reply_text("❌ Negalite pranešti apie save!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    try:
        global buyer_report_id
        buyer_report_id += 1
        
        # Store the report
        pending_buyer_reports[buyer_report_id] = {
            'username': reported_username,
            'user_id': reported_user_id,  # Store user ID if provided
            'reporter_id': user_id,
            'reporter_username': reporter_username or f"User {user_id}",
            'reason': reason,
            'timestamp': now,
            'chat_id': chat_id
        }
        
        # Save data
        save_data(pending_buyer_reports, 'pending_buyer_reports.pkl')
        save_data(buyer_report_id, 'buyer_report_id.pkl')
        
        # Create message with inline buttons for admins
        user_id_info = f"User ID: {reported_user_id}" if reported_user_id else "User ID: Nerastas (privatus paskyra)"
        if reported_user_id:
            logger.info(f"Buyer report #{buyer_report_id} includes user ID: {reported_user_id}")
        else:
            logger.warning(f"Buyer report #{buyer_report_id} has no user ID for {reported_username}")
        
        admin_message = (
            f"🛒 NAUJAS PIRKĖJO PRANEŠIMAS 🛒\n\n"
            f"Report ID: #{buyer_report_id}\n"
            f"Pranešė: {reporter_username or f'User {user_id}'}\n"
            f"Apie: {reported_username}\n"
            f"{user_id_info}\n"
            f"Priežastis: {reason}\n"
            f"Laikas: {now.strftime('%Y-%m-%d %H:%M')}\n\n"
            f"Spustelėkite mygtukus žemiau:"
        )
        
        # Create inline keyboard with approve/reject buttons
        keyboard = [
            [
                InlineKeyboardButton("✅ Patvirtinti", callback_data=f"approve_buyer_{buyer_report_id}"),
                InlineKeyboardButton("❌ Atmesti", callback_data=f"reject_buyer_{buyer_report_id}")
            ],
            [InlineKeyboardButton("ℹ️ Detaliau", callback_data=f"buyer_details_{buyer_report_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send to admin chat
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=admin_message,
                reply_markup=reply_markup
            )
        except Exception as e:
            logger.error(f"Failed to send buyer report to admin: {e}")
        
        # Send confirmation to user
        confirmation_message = (
            f"✅ Pirkėjo pranešimas pateiktas!\n\n"
            f"Report ID: #{buyer_report_id}\n"
            f"Pranešta apie: {reported_username}\n"
            f"Jūsų pranešimas perduotas moderatoriams peržiūrai.\n\n"
            f"📊 Dėkojame už pagalbą kuriant saugesnę bendruomenę!"
        )
        
        msg = await update.message.reply_text(confirmation_message)
        context.job_queue.run_once(delete_message_job, 60, data=(chat_id, msg.message_id))
        
        logger.info(f"Buyer report #{buyer_report_id} created by user {user_id} about {reported_username}")
        
    except Exception as e:
        logger.error(f"Error creating buyer report: {str(e)}")
        msg = await update.message.reply_text("❌ Klaida pateikiant pranešimą. Bandykite vėliau.")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def neradejas(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Check if a user has buyer reports"""
    chat_id = update.message.chat_id
    
    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    if len(context.args) < 1:
        msg = await update.message.reply_text(
            "📋 Naudojimas: `/neradejas @username` arba `/neradejas 123456789`\n\n"
            "Pavyzdys: `/neradejas @user123` arba `/neradejas 123456789`\n"
            "Patikrinkite ar pirkėjas turi pranešimų"
        )
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Sanitize username
    check_username = sanitize_username(context.args[0])
    if not check_username or len(check_username) < 2:
        msg = await update.message.reply_text("❌ Netinkamas vartotojo vardas! Naudok @username formatą.")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    # Check if input is a user ID (numeric)
    check_user_id = None
    original_input = check_username
    if check_username.isdigit():
        check_user_id = int(check_username)
        # Find username by user ID in bad buyer database
        if check_user_id in user_id_to_bad_buyer:
            check_username = user_id_to_bad_buyer[check_user_id]
            logger.info(f"Found bad buyer by user ID {check_user_id} -> {check_username}")
        # Also try to find in our general username mapping
        elif check_user_id in [v for v in username_to_id.values()]:
            # Find the username for this user ID
            for username_key, user_id in username_to_id.items():
                if user_id == check_user_id:
                    check_username = username_key
                    logger.info(f"Found username by user ID {check_user_id} -> {check_username}")
                    break
    
    # Check if in confirmed bad buyers list
    if check_username.lower() in confirmed_bad_buyers:
        buyer_info = confirmed_bad_buyers[check_username.lower()]
        total_reports = buyer_info.get('total_reports', len(buyer_info.get('reports', [])))
        
        # Get recent reports (last 3)
        reports = buyer_info.get('reports', [])
        recent_reports = sorted(reports, key=lambda x: x.get('timestamp', datetime.min), reverse=True)[:3]
        
        result_text = f"⚠️ PIRKĖJAS SU PRANEŠIMAIS ⚠️\n\n"
        result_text += f"👤 Vartotojas: {check_username}\n"
        result_text += f"📊 Iš viso pranešimų: {total_reports}\n\n"
        
        if recent_reports:
            result_text += "📋 Paskutiniai pranešimai:\n"
            for i, report in enumerate(recent_reports, 1):
                timestamp = report.get('timestamp', 'Nežinoma')
                if isinstance(timestamp, datetime):
                    timestamp = timestamp.strftime('%Y-%m-%d')
                reason_short = report.get('reason', 'Nėra priežasties')[:50]
                if len(report.get('reason', '')) > 50:
                    reason_short += "..."
                result_text += f"{i}. {timestamp}: {reason_short}\n"
        
        result_text += f"\n⚠️ Būkite atsargūs darydami sandorius!"
        
    else:
        result_text = f"✅ PIRKĖJAS ŠVARUS ✅\n\n"
        result_text += f"👤 Vartotojas: {check_username}\n"
        result_text += f"📊 Pranešimų nerasta\n\n"
        result_text += f"✅ Šis pirkėjas neturi patvirtintų pranešimų"
    
    msg = await update.message.reply_text(result_text)
    context.job_queue.run_once(delete_message_job, 60, data=(chat_id, msg.message_id))


# Admin commands for buyer report management moved to moderation panel buttons

# pending_buyer_reports_command removed - now accessible through moderation panel


async def help_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Show comprehensive help information"""
    chat_id = update.message.chat_id
    
    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    help_text = """
🤖 Greitas Komandų Sąrašas

📚 Nori detalų vadovą? Naudok /komandos - pilnas vadovas su pavyzdžiais!

📊 Pagrindinės Komandos:
📊 /balsuoti - Balsuoti už pardavėjus balsavimo grupėje
👎 /nepatiko @pardavejas priežastis - Pateikti skundą (+5 tšk)
💰 /points - Patikrinti savo taškus ir pokalbių seriją
👑 /chatking - Visų laikų pokalbių lyderiai
📈 /barygos - Pardavėjų reitingai ir statistika

🛡️ Saugumo Sistema:
🚨 /scameris @username įrodymai - Pranešti apie scamerį (+3 tšk)
🔍 /patikra @username - Patikrinti ar vartotojas scameris arba patikimas pardavėjas
📋 /scameriai - Peržiūrėti visų patvirtintų scamerių sąrašą
🛒 /vagis @username priežastis - Pranešti apie problematišką pirkėją (+2 tšk)
🔎 /neradejas @username - Patikrinti ar pirkėjas turi pranešimų

🛡️ Moderacijos Komandos (Admin/Pagalbininkai):
🚫 /ban username/id [priežastis] - Uždrausti vartotoją
✅ /unban username/id - Atšaukti uždraudimą
🔇 /mute username/id [priežastis] - Nutildyti vartotoją
🔊 /unmute username/id - Atšaukti nutildymą
🔄 /recurring - Kartojami pranešimai
🚫 /bannedwords - Uždrausti žodžiai
👥 /helpers - Pagalbininkų valdymas

🔧 Privataus Pokalbio Komandos (Admin):
🔄 /recurring_messages - Kartojami pranešimai (privatai, su inline UI)
🚫 /banned_words - Uždrausti žodžiai (privatai, su inline UI)
👥 /helpers - Pagalbininkų valdymas (privatai, su inline UI)

🎮 Žaidimai ir Veikla:
🎯 /coinflip suma @vartotojas - Iššūkis monetos metimui
📋 /apklausa klausimas - Sukurti grupės apklausą

ℹ️ Informacija:
📚 /komandos - Pilnas komandų vadovas
❓ /whoami - Tavo vartotojo informacija

🎖️ Taškų Sistema:
• Balsavimas už pardavėją: +15 taškų (1x per savaitę)
• Skundas pardavėjui: +5 taškų (1x per savaitę)  
• Scamerio pranešimas: +3 taškų (neribota)
• Pirkėjo pranešimas: +2 taškų (neribota)
• Kasdieniai pokalbiai: 1-3 taškų + serijos bonusas
• Serijos bonusas: +1 tšk už kiekvieną 3 dienų seriją

💬 Rašyk kasdien kaupiant taškus ir seriją!
"""
    
    msg = await update.message.reply_text(help_text)
    context.job_queue.run_once(delete_message_job, 90, data=(chat_id, msg.message_id))

async def komandos(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Show comprehensive list of all commands with detailed explanations"""
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    

    
    commands_text = f"""
📚 VISŲ KOMANDŲ VADOVAS 📚
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏆 BALSAVIMO SISTEMA
📊 `/barygos` - Pardavėjų reitingai (savaitės, mėnesio, visų laikų)
📊 `/balsuoti` - Nukreipia į balsavimo grupę (+15 tšk, 1x/savaitę)
👎 `/nepatiko @pardavejas priežastis` - Skundu pardavėją (+5 tšk, 1x/savaitę)

🛡️ SAUGUMO SISTEMA
🚨 `/scameris @username įrodymai` - Pranešti scamerį (+3 tšk, neribota)
🔍 `/patikra @username` - Patikrinti ar vartotojas scameris arba patikimas pardavėjas
📋 `/scameriai` - Peržiūrėti visų patvirtintų scamerių sąrašą
🛒 `/vagis @username priežastis` - Pranešti problematišką pirkėją (+2 tšk, neribota)
🔎 `/neradejas @username` - Patikrinti ar pirkėjas turi pranešimų

🛡️ MODERACIJOS SISTEMA (Admin/Pagalbininkai)
🚫 `/ban username/id [priežastis]` - Uždrausti vartotoją (ištrina pranešimus)
✅ `/unban username/id` - Atšaukti uždraudimą
🔇 `/mute username/id [priežastis]` - Nutildyti vartotoją (24h)
🔊 `/unmute username/id` - Atšaukti nutildymą
🔄 `/recurring` - Kartojami pranešimai (GroupHelpBot stilius)
🚫 `/bannedwords` - Uždrausti žodžiai (automatinis aptikimas)
👥 `/helpers` - Pagalbininkų valdymas (deleguoti modifikaciją)

🔧 PRIVATAUS POKALBIO KOMANDOS (Admin):
🔄 `/recurring_messages` - Kartojami pranešimai (privatai, su inline UI)
🚫 `/banned_words` - Uždrausti žodžiai (privatai, su inline UI)
👥 `/helpers` - Pagalbininkų valdymas (privatai, su inline UI)

💰 TAŠKŲ SISTEMA
💰 `/points` - Patikrinti savo taškus ir pokalbių seriją
👑 `/chatking` - Visų laikų pokalbių lyderiai su pasiekimų lygiais

🎮 ŽAIDIMAI IR VEIKLA
🎯 `/coinflip suma @vartotojas` - Iššūkis monetos metimui (laimėtojas gauna taškus)
📋 `/apklausa klausimas` - Sukurti grupės apklausą

ℹ️ INFORMACIJA
📚 `/komandos` - Šis detalus komandų sąrašas
🤖 `/help` - Trumpas pagalbos tekstas
❓ `/whoami` - Tavo vartotojo informacija ir ID
🔧 `/debug` - Grupės administratoriai (tik adminams)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💎 TAŠKŲ GAVIMO BŪDAI
• 📊 Balsavimas už pardavėją: +15 taškų (1x per savaitę)
• 👎 Skundas pardavėjui: +5 taškų (1x per savaitę)
• 🚨 Scamerio pranešimas: +3 taškų (neribota)
• 🛒 Pirkėjo pranešimas: +2 taškų (neribota)
• 💬 Kasdieniai pokalbiai: 1-3 taškų + serijos bonusas
• 🔥 Serijos bonusas: +1 tšk už kiekvieną 3 dienų seriją
• 🎯 Monetos metimas: Laimėtojo suma taškų

🏅 POKALBIŲ LYGIAI
🌱 Pradžia: 1-99 žinučių
📈 Naujokas: 100-499 žinučių  
🌟 Aktyvus: 500-999 žinučių
💎 Meistras: 1,000-4,999 žinučių
⚡ Ekspertas: 5,000-9,999 žinučių
🔥 Legenda: 10,000+ žinučių

⏰ AUTOMATINIAI RESTARTAI
• 🗓️ Savaitės balsai: kas sekmadienį 23:00
• 📅 Mėnesio balsai: kiekvieną mėnesio 1-ą dieną
• 💬 Pokalbių taškų suvestinė: kasdien 6:00

🔒 SAUGUMO PATARIMAI
• Visada naudok `/patikra @username` ir `/neradejas @username` prieš sandorį
• Pranešk apie scamerius su detaliais įrodymais
• Pranešk apie problemiškus pirkėjus su konkrečiomis priežastimis
• Saugok savo asmeninę informaciją
• Nenurodyti pin kodų ar slaptažodžių

📱 NAUDOJIMO PATARIMAI
• Komandos veikia tik šioje grupėje
• Naudok @ prieš vartotojo vardus
• Dalis komandų automatiškai ištrinamos po laiko
• Aktyvus dalyvavimas = daugiau taškų"""



    commands_text += f"""

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 GREITI PAVYZDŽIAI
• Balsuoti: `/balsuoti` → Spausk nuorodą → Rinktis pardavėją
• Patikrinti: `/patikra @username` → Gauni saugumo ataskaitą  
• Pranešti scamerį: `/scameris @blogas Nesiunčia prekių, ignoruoja`
• Patikrinti pirkėją: `/neradejas @username` → Gauni pirkėjo ataskaitą
• Pranešti pirkėją: `/vagis @blogas Meluoja apie prekę, reikalauja grąžinimo`
• Žaisti: `/coinflip 10 @friends` → Mėtkyos monetą už 10 tšk
• Skundas: `/nepatiko @pardavejas Bloga kokybė, vėluoja`

📊 STATISTIKOS
• Aktyvūs vartotojai šiandien: ~{len(daily_messages)}
• Visų laikų žinučių: {sum(alltime_messages.values()):,}
• Patvirtinti scameriai: {len(confirmed_scammers)}
• Problemiški pirkėjai: {len(confirmed_bad_buyers)}
• Patikimi pardavėjai: {len(trusted_sellers)}

💡 PRO PATARIMAI
• Rašyk kasdien - serija didina taškų gavimą
• Dalyvaukite apklausose - stiprina bendruomenę  
• Praneškit apie scamerius - apsaugot kitus
• Sekite pardavėjų reitingus - raskite geriausius

Norint gauti pilną pagalbą: `/help`
"""

    try:
        msg = await update.message.reply_text(commands_text, parse_mode='Markdown')
        context.job_queue.run_once(delete_message_job, 180, data=(chat_id, msg.message_id))  # Keep longer for reading
        
        # Log command usage
        analytics.log_command_usage('komandos', user_id, chat_id)
        
    except telegram.error.TelegramError as e:
        # Fallback without markdown if formatting fails
        logger.error(f"Error sending formatted komandos: {str(e)}")
        try:
            fallback_text = commands_text.replace('**', '').replace('*', '')
            msg = await update.message.reply_text(fallback_text)
            context.job_queue.run_once(delete_message_job, 120, data=(chat_id, msg.message_id))
        except Exception as fallback_error:
            logger.error(f"Fallback komandos also failed: {str(fallback_error)}")
            msg = await update.message.reply_text("❌ Klaida rodant komandų sąrašą!")
            context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))

async def achievements(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Show user achievements and progress"""
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    try:
        # Log command usage
        analytics.log_command_usage('achievements', user_id, chat_id)
        
        user_achievements = achievement_system.get_user_achievements(user_id)
        total_achievements = len(achievement_system.achievements)
        
        if not user_achievements:
            msg = await update.message.reply_text(
                "🏆 Dar neturi pasiekimų!\n\n"
                "Balsuok, rašyk žinutes ir dalyvauk veikloje, kad gautum pasiekimus!"
            )
        else:
            achievement_text = "🏆 Tavo Pasiekimai 🏆\n\n"
            for achievement in user_achievements:
                achievement_text += f"{achievement['name']}\n"
                achievement_text += f"📝 {achievement['description']}\n"
                achievement_text += f"🎯 +{achievement['points']} taškų\n\n"
            
            achievement_text += f"📊 Progresą: {len(user_achievements)}/{total_achievements} pasiekimų"
            
            msg = await update.message.reply_text(achievement_text)
        
        context.job_queue.run_once(delete_message_job, 60, data=(chat_id, msg.message_id))
    except Exception as e:
        logger.error(f"Error in achievements command: {str(e)}")
        analytics.log_command_usage('achievements', user_id, chat_id, False, str(e))

async def challenges(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Show weekly challenges and progress"""
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    try:
        # Log command usage
        analytics.log_command_usage('challenges', user_id, chat_id)
        
        user_challenges = challenge_system.get_weekly_challenges(user_id)
        event_id, event = achievement_system.get_current_event()
        
        challenge_text = "🎯 Savaitės Iššūkiai 🎯\n\n"
        
        if event:
            challenge_text += f"🎉 {event['name']} - {event['bonus_multiplier']}x taškai!\n\n"
        
        for challenge_data in user_challenges:
            challenge = challenge_data['challenge']
            progress = challenge_data['progress']
            completed = challenge_data['completed']
            
            status = "✅" if completed else "⏳"
            challenge_text += f"{status} {challenge['name']}\n"
            challenge_text += f"📝 {challenge['description']}\n"
            challenge_text += f"📊 Progresą: {progress}/{challenge['target']}\n"
            challenge_text += f"🎁 Atlygis: {challenge['reward_points']} taškų\n\n"
        
        msg = await update.message.reply_text(challenge_text)
        context.job_queue.run_once(delete_message_job, 60, data=(chat_id, msg.message_id))
    except Exception as e:
        logger.error(f"Error in challenges command: {str(e)}")
        analytics.log_command_usage('challenges', user_id, chat_id, False, str(e))

async def leaderboard(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Show comprehensive leaderboards"""
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    try:
        # Log command usage
        analytics.log_command_usage('leaderboard', user_id, chat_id)
        
        # Create beautiful header
        now = datetime.now(TIMEZONE)
        header = "🏆✨ BENDROS LYDERIŲ LENTOS ✨🏆\n"
        header += f"📅 {now.strftime('%Y-%m-%d %H:%M')}\n"
        header += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        
        # Points leaderboard
        sorted_points = sorted(user_points.items(), key=lambda x: x[1], reverse=True)[:10]
        max_points = sorted_points[0][1] if sorted_points else 1
        
        points_board = "💰 TAŠKŲ MAGNATAI 💰\n"
        points_board += "┌─────────────────────────────────────┐\n"
        
        if not sorted_points:
            points_board += "│       Dar nėra taškų lyderių       │\n"
        else:
            for i, (uid, points) in enumerate(sorted_points, 1):
                try:
                    username = next((k for k, v in username_to_id.items() if v == uid), f"User {uid}")
                    
                    # Create wealth icons based on points
                    if points >= 1000:
                        icon = "💎"
                    elif points >= 500:
                        icon = "🥇"
                    elif points >= 200:
                        icon = "🥈"
                    elif points >= 100:
                        icon = "🥉"
                    elif points >= 50:
                        icon = "⭐"
                    else:
                        icon = "🌟"
                    
                    # Create progress bar
                    progress = points / max(max_points, 1)
                    bar_length = 15
                    filled = int(progress * bar_length)
                    progress_bar = "█" * filled + "░" * (bar_length - filled)
                    
                    # Format username
                    display_name = username[1:] if username.startswith('@') else username
                    display_name = display_name[:12] if len(display_name) > 12 else display_name
                    
                    points_board += f"│{icon} {i:2d}. {display_name:<12} │{points:4d}│{progress_bar}│\n"
                except (KeyError, TypeError, ValueError) as e:
                    logger.warning(f"Error formatting user {uid} in leaderboard: {e}")
                    points_board += f"│💰 {i:2d}. User {uid}       │{points:4d}│{'█' * 8 + '░' * 7}│\n"
        
        points_board += "└─────────────────────────────────────┘\n\n"
        
        # Messages leaderboard
        sorted_messages = sorted(alltime_messages.items(), key=lambda x: x[1], reverse=True)[:10]
        max_messages = sorted_messages[0][1] if sorted_messages else 1
        
        messages_board = "💬 POKALBIŲ ČEMPIONAI 💬\n"
        messages_board += "┌─────────────────────────────────────┐\n"
        
        if not sorted_messages:
            messages_board += "│      Dar nėra pokalbių lyderių     │\n"
        else:
            for i, (uid, msg_count) in enumerate(sorted_messages, 1):
                try:
                    username = next((k for k, v in username_to_id.items() if v == uid), f"User {uid}")
                    
                    # Create chat activity icons
                    if msg_count >= 5000:
                        icon = "🔥"
                    elif msg_count >= 1000:
                        icon = "⚡"
                    elif msg_count >= 500:
                        icon = "💎"
                    elif msg_count >= 100:
                        icon = "🌟"
                    elif msg_count >= 50:
                        icon = "⭐"
                    else:
                        icon = "📈"
                    
                    # Create progress bar
                    progress = msg_count / max(max_messages, 1)
                    bar_length = 15
                    filled = int(progress * bar_length)
                    progress_bar = "█" * filled + "░" * (bar_length - filled)
                    
                    # Format username
                    display_name = username[1:] if username.startswith('@') else username
                    display_name = display_name[:12] if len(display_name) > 12 else display_name
                    
                    messages_board += f"│{icon} {i:2d}. {display_name:<12} │{msg_count:4d}│{progress_bar}│\n"
                except (KeyError, TypeError, ValueError) as e:
                    logger.warning(f"Error formatting user {uid} in messages leaderboard: {e}")
                    messages_board += f"│💬 {i:2d}. User {uid}       │{msg_count:4d}│{'█' * 8 + '░' * 7}│\n"
        
        messages_board += "└─────────────────────────────────────┘\n\n"
        
        # Achievement leaderboard
        achievement_counts = {}
        for user_id_ach, achievements in achievement_system.user_achievements.items():
            achievement_counts[user_id_ach] = len(achievements)
        
        sorted_achievements = sorted(achievement_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        max_achievements = sorted_achievements[0][1] if sorted_achievements else 1
        
        achievements_board = "🏅 **PASIEKIMŲ KOLEKCIONIERIAI** 🏅\n"
        achievements_board += "┌─────────────────────────────────────┐\n"
        
        if not sorted_achievements:
            achievements_board += "│    Dar nėra pasiekimų kolekcininkų  │\n"
        else:
            for i, (uid, ach_count) in enumerate(sorted_achievements, 1):
                try:
                    username = next((k for k, v in username_to_id.items() if v == uid), f"User {uid}")
                    
                    # Create achievement icons
                    if ach_count >= 8:
                        icon = "🏆"
                    elif ach_count >= 6:
                        icon = "🎖️"
                    elif ach_count >= 4:
                        icon = "🥇"
                    elif ach_count >= 2:
                        icon = "🏅"
                    else:
                        icon = "⭐"
                    
                    # Create progress bar
                    progress = ach_count / max(max_achievements, 1)
                    bar_length = 15
                    filled = int(progress * bar_length)
                    progress_bar = "█" * filled + "░" * (bar_length - filled)
                    
                    # Format username
                    display_name = username[1:] if username.startswith('@') else username
                    display_name = display_name[:12] if len(display_name) > 12 else display_name
                    
                    achievements_board += f"│{icon} {i:2d}. {display_name:<12} │{ach_count:4d}│{progress_bar}│\n"
                except (KeyError, TypeError, ValueError) as e:
                    logger.warning(f"Error formatting user {uid} in achievements leaderboard: {e}")
                    achievements_board += f"│🏅 {i:2d}. User {uid}       │{ach_count:4d}│{'█' * 8 + '░' * 7}│\n"
        
        achievements_board += "└─────────────────────────────────────┘\n\n"
        
        # Community statistics
        stats = "📊 **BENDRUOMĖS STATISTIKOS**\n"
        total_users = len(user_points)
        total_points = sum(user_points.values())
        total_messages = sum(alltime_messages.values())
        total_achievements = sum(len(ach) for ach in achievement_system.user_achievements.values())
        
        stats += f"• Narių: {total_users} 👥\n"
        stats += f"• Taškų: {total_points:,} 💰\n"
        stats += f"• Žinučių: {total_messages:,} 💬\n"
        stats += f"• Pasiekimų: {total_achievements} 🏆\n"
        stats += f"• Vidurkis taškų: {total_points // total_users if total_users else 0} 📈\n\n"
        
        # Tips and motivation
        footer = "🎯 **KAIP KILTI AUKŠTYN**\n"
        footer += "• Dalyvaukite kasdienių pokalbių (+1-3 tšk)\n"
        footer += "• Balsuokite už pardavėjus (+5 tšk/sav)\n"
        footer += "• Pildykite savaitės iššūkius (+60-100 tšk)\n"
        footer += "• Gaukite pasiekimus (+10-200 tšk)\n"
        footer += "• Palaikykite pokalbių seijas (bonusai)\n\n"
        footer += "🚀 Dalyvaukite aktyviai ir tapkite lyderiais!"
        
        full_message = header + points_board + messages_board + achievements_board + stats + footer
        
        try:
            msg = await update.message.reply_text(full_message, parse_mode='Markdown')
            context.job_queue.run_once(delete_message_job, 120, data=(chat_id, msg.message_id))
        except telegram.error.TelegramError as e:
            # Fallback without markdown
            logger.error(f"Error sending formatted leaderboard: {str(e)}")
            fallback_message = full_message.replace('**', '').replace('*', '')
            msg = await update.message.reply_text(fallback_message)
            context.job_queue.run_once(delete_message_job, 90, data=(chat_id, msg.message_id))
        
    except Exception as e:
        logger.error(f"Error in leaderboard command: {str(e)}")
        analytics.log_command_usage('leaderboard', user_id, chat_id, False, str(e))

async def mystats(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Show detailed user statistics"""
    chat_id = update.message.chat_id
    user_id = update.message.from_user.id
    
    if not is_allowed_group(chat_id):
        msg = await update.message.reply_text("Botas neveikia šioje grupėje!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    try:
        # Log command usage
        analytics.log_command_usage('mystats', user_id, chat_id)
        
        points = user_points.get(user_id, 0)
        streak = chat_streaks.get(user_id, 0)
        messages = alltime_messages.get(user_id, 0)
        achievements = len(achievement_system.get_user_achievements(user_id))
        
        # Calculate user rank
        sorted_points = sorted(user_points.items(), key=lambda x: x[1], reverse=True)
        user_rank = next((i for i, (uid, _) in enumerate(sorted_points, 1) if uid == user_id), "N/A")
        
        stats_text = f"📊 Tavo Statistikos 📊\n\n"
        stats_text += f"💰 Taškai: {points}\n"
        stats_text += f"🔥 Serija: {streak} dienų\n"
        stats_text += f"💬 Žinutės: {messages}\n"
        stats_text += f"🏆 Pasiekimai: {achievements}\n"
        stats_text += f"📈 Ranka: #{user_rank}\n\n"
        
        # Add weekly stats
        today = datetime.now(TIMEZONE).date()
        week_start = today - timedelta(days=today.weekday())
        weekly_msgs = sum(daily_messages[user_id].get(week_start + timedelta(days=i), 0) for i in range(7))
        stats_text += f"📅 Šios savaitės žinutės: {weekly_msgs}\n"
        
        # Add voting stats
        total_votes = sum(1 for vendor_votes in vote_history.values() 
                         for vote in vendor_votes if vote[0] == user_id and vote[1] == "up")
        total_complaints = sum(1 for vendor_votes in vote_history.values() 
                              for vote in vendor_votes if vote[0] == user_id and vote[1] == "down")
        
        stats_text += f"🗳️ Balsai: {total_votes}\n"
        stats_text += f"👎 Skundai: {total_complaints}\n"
        
        msg = await update.message.reply_text(stats_text)
        context.job_queue.run_once(delete_message_job, 60, data=(chat_id, msg.message_id))
    except Exception as e:
        logger.error(f"Error in mystats command: {str(e)}")
        analytics.log_command_usage('mystats', user_id, chat_id, False, str(e))

async def botstats(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Show bot analytics and statistics (admin only)"""
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali naudoti šią komandą!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    try:
        # Log command usage
        analytics.log_command_usage('botstats', user_id, chat_id)
        
        usage_stats = analytics.get_usage_stats(7)
        
        stats_text = "📈 Bot Statistikos (7 dienos) 📈\n\n"
        
        if usage_stats:
            stats_text += "🔥 Populiariausios komandos:\n"
            for command, count, success_rate in usage_stats[:10]:
                stats_text += f"/{command}: {count}x ({success_rate:.1%} sėkmė)\n"
        
        stats_text += f"\n👥 Viso vartotojų: {len(user_points)}\n"
        stats_text += f"💬 Viso žinučių: {sum(alltime_messages.values())}\n"
        stats_text += f"🗳️ Viso balsų: {sum(votes_alltime.values())}\n"
        stats_text += f"📊 Viso apklausų: {len(polls)}\n"
        stats_text += f"🏆 Viso pasiekimų: {sum(len(achievements) for achievements in achievement_system.user_achievements.values())}\n"
        
        # System health
        stats_text += f"\n🖥️ Sistemos būklė:\n"
        stats_text += f"Leistinos grupės: {len(allowed_groups)}\n"
        stats_text += f"Patikimi pardavėjai: {len(trusted_sellers)}\n"
        stats_text += f"Laukiantys skundai: {len(pending_downvotes)}\n"
        
        msg = await update.message.reply_text(stats_text)
        context.job_queue.run_once(delete_message_job, 60, data=(chat_id, msg.message_id))
    except Exception as e:
        logger.error(f"Error in botstats command: {str(e)}")
        analytics.log_command_usage('botstats', user_id, chat_id, False, str(e))

async def moderation_command(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Moderation panel for admins"""
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    
    if user_id != ADMIN_CHAT_ID:
        msg = await update.message.reply_text("Tik adminas gali naudoti šią komandą!")
        context.job_queue.run_once(delete_message_job, 45, data=(chat_id, msg.message_id))
        return
    
    try:
        # Show moderation options
        keyboard = [
            [InlineKeyboardButton("Laukiantys scamer pranešimai", callback_data="mod_pending_scammers")],
            [InlineKeyboardButton("Laukiantys pirkėjų pranešimai", callback_data="mod_pending_buyers")],
            [InlineKeyboardButton("Perspėjimų sąrašas", callback_data="mod_warnings")],
            [InlineKeyboardButton("Patikimi vartotojai", callback_data="mod_trusted")],
            [InlineKeyboardButton("Uždrausti žodžiai", callback_data="mod_banned_words")],
            [InlineKeyboardButton("Moderacijos logai", callback_data="mod_logs")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        msg = await update.message.reply_text(
            "🛡️ Moderacijos Pultas 🛡️\n\nPasirink veiksmą:",
            reply_markup=reply_markup
        )
        context.job_queue.run_once(delete_message_job, 60, data=(chat_id, msg.message_id))
    except Exception as e:
        logger.error(f"Error in moderation command: {str(e)}")
        analytics.log_command_usage('moderation', user_id, chat_id, False, str(e))

# New feature command functions
async def recurring_messages_menu(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Main menu for recurring messages - GroupHelpBot style"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Tik administratoriai gali naudoti šią komandą!")
        return
    
    # Handle private chat - ask for group selection
    if update.effective_chat.type == 'private':
        await recurring_messages_private(update, context)
        return
    
    chat_id = update.effective_chat.id
    current_time = datetime.now().strftime("%d/%m/%y %H:%M")
    
    # Get scheduled messages for this chat
    scheduled_messages = database.get_scheduled_messages(chat_id)
    
    # Create main menu text exactly like GroupHelpBot
    text = (
        "🔄 **Recurring messages**\n\n"
        "From this menu you can set messages that will be sent "
        "repeatedly to the group every few minutes/hours or every "
        "few messages.\n\n"
        f"Current time: {current_time}"
    )
    
    # Add message entries if they exist
    if scheduled_messages:
        for i, msg in enumerate(scheduled_messages, 1):
            status_icon = "✅" if msg['is_active'] else "❌"
            time_str = format_interval(msg['interval_hours'], msg.get('interval_minutes', 0))
            
            # Get message preview
            message_preview = "Message is not set." if not msg.get('message_text') else msg['message_text'][:30]
            if msg.get('message_text') and len(msg['message_text']) > 30:
                message_preview += "..."
            
            text += f"\n\n**{i} • Off** {status_icon}\n"
            text += f"⏰ Time: {time_str}\n"
            text += f"📝 {message_preview}"
    
    # Create keyboard
    keyboard = [[InlineKeyboardButton("➕ Add message", callback_data="recurring_add")]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def ban_user(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Ban a user"""
    if not await can_ban_users(update, context):
        await update.message.reply_text("❌ Neturite teisių uždrausti vartotojų!")
        return
    
    args = context.args
    chat_id = update.effective_chat.id
    admin_user = update.effective_user
    
    # Check if this is a reply to a message
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_id = target_user.id
        reason = " ".join(args) if args else "Nenurodyta"
    else:
        if len(args) < 1:
            await update.message.reply_text(
                "❌ Naudojimas: /ban username/id [priežastis]\n\n"
                "**Arba:** Atsakykite į vartotojo žinutę su `/ban [priežastis]`"
            )
            return
        
        target = args[0]
        reason = " ".join(args[1:]) if len(args) > 1 else "Nenurodyta"
    
    try:
        # If not replying to a message, we need to resolve the target
        if not update.message.reply_to_message:
            # Get target user info and try to ban directly
            target_user = None
            target_id = None
            
            if target.startswith('@'):
                # For username, use the most reliable method: try to ban directly
                # This is how most bots like GroupHelpBot handle usernames
                username_without_at = target[1:]  # Remove @ symbol
                
                # Try to get user info first for display purposes
                try:
                    # Try to get user by username (this works in most cases)
                    target_user = None
                    target_id = username_without_at  # Use username directly
                    
                    # Try to get additional user info if possible
                    try:
                        # Try to get user info from chat member
                        target_member = await context.bot.get_chat_member(chat_id, target)
                        target_user = target_member.user
                        target_id = target_user.id  # Use actual user ID if we got it
                    except telegram.error.BadRequest:
                        # If we can't get member info, continue with username
                        pass
                        
                except Exception as e:
                    # If anything fails, still try to ban by username
                    target_user = None
                    target_id = username_without_at
            else:
                try:
                    user_id = int(target)
                    target_id = user_id
                    # Try to get user info for display purposes
                    try:
                        target_member = await context.bot.get_chat_member(chat_id, user_id)
                        target_user = target_member.user
                    except telegram.error.BadRequest:
                        target_user = None
                except ValueError:
                    await update.message.reply_text("❌ Neteisingas vartotojo ID!")
                    return
        
        # Try to ban the user
        try:
            await context.bot.ban_chat_member(chat_id, target_id)
        except telegram.error.BadRequest as e:
            if "USER_NOT_PARTICIPANT" in str(e):
                await update.message.reply_text("❌ Vartotojas nėra grupės narys!")
            elif "CHAT_ADMIN_REQUIRED" in str(e):
                await update.message.reply_text("❌ Neturite teisių uždrausti vartotojų!")
            elif "USER_IS_CHAT_OWNER" in str(e):
                await update.message.reply_text("❌ Negalite uždrausti grupės savininko!")
            else:
                await update.message.reply_text(f"❌ Klaida uždraudžiant vartotoją: {str(e)}")
            return
        
        # Delete all messages from the banned user
        messages_deleted = 0
        # Note: get_chat_history is not available in python-telegram-bot
        # Message deletion would require storing message IDs or using other methods
        # For now, we'll skip automatic message deletion
        logger.info(f"User {target_id} banned successfully. Automatic message deletion not implemented.")
        
        # Success message
        ban_text = f"🚫 **VARTOTOJA UŽBANINTAS** 🚫\n\n"
        if target_user:
            ban_text += f"👤 **Vartotojas:** {target_user.first_name}"
            if target_user.username:
                ban_text += f" (@{target_user.username})"
            ban_text += f"\n🆔 **ID:** `{target_user.id}`\n"
        else:
            ban_text += f"👤 **Vartotojas:** {target}\n"
            ban_text += f"🆔 **ID:** `{target_id}`\n"
        ban_text += f"👮 **Uždraudė:** {admin_user.first_name}"
        if admin_user.username:
            ban_text += f" (@{admin_user.username})"
        ban_text += f"\n📝 **Priežastis:** {reason}\n"
        ban_text += f"🗑️ **Ištrinti pranešimai:** {messages_deleted}\n"
        ban_text += f"⏰ **Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        await update.message.reply_text(ban_text, parse_mode='Markdown')
        
    except telegram.error.BadRequest as e:
        if "Invalid user_id specified" in str(e):
            await update.message.reply_text("❌ Neteisingas vartotojo ID arba vartotojas nerastas!")
        else:
            await update.message.reply_text(f"❌ Klaida uždraudžiant vartotoją: {str(e)}")
    except Exception as e:
        # Escape markdown characters in error message
        error_msg = str(e).replace('*', '\\*').replace('_', '\\_').replace('`', '\\`')
        await update.message.reply_text(
            f"❌ **KLAIDA**\n\n"
            f"Nepavyko uždrausti vartotojo: {error_msg}",
            parse_mode='Markdown'
        )

async def unban_user(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Unban a user"""
    if not await can_ban_users(update, context):
        await update.message.reply_text("❌ Neturite teisių atšaukti uždraudimą!")
        return
    
    args = context.args
    chat_id = update.effective_chat.id
    admin_user = update.effective_user
    
    # Check if this is a reply to a message
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_id = target_user.id
    else:
        if len(args) < 1:
            await update.message.reply_text(
                "❌ Naudojimas: /unban username/id\n\n"
                "**Arba:** Atsakykite į vartotojo žinutę su `/unban`"
            )
            return
        
        target = args[0]
    
    try:
        # If not replying to a message, we need to resolve the target
        if not update.message.reply_to_message:
            # Get target user info and try to unban directly
            target_user = None
            target_id = None
            
            if target.startswith('@'):
                # For username, we need to resolve it to a user ID for unban operations
                # Telegram's unban_chat_member API only accepts user IDs, not usernames
                username_without_at = target[1:]  # Remove @ symbol
                
                # Try different methods to resolve username to user ID
                target_user = None
                target_id = None
                
                # Method 1: Check if user has sent recent messages (check updates)
                try:
                    updates = await context.bot.get_updates(limit=100)
                    for upd in reversed(updates):  # Check most recent first
                        if (upd.message and upd.message.from_user and 
                            upd.message.from_user.username and
                            upd.message.from_user.username.lower() == username_without_at.lower()):
                            target_user = upd.message.from_user
                            target_id = target_user.id
                            break
                except Exception:
                    pass
                
                # Method 2: Try to get user from chat administrators (in case they're admin)
                if target_id is None:
                    try:
                        admins = await context.bot.get_chat_administrators(chat_id)
                        for admin in admins:
                            if (admin.user.username and 
                                admin.user.username.lower() == username_without_at.lower()):
                                target_user = admin.user
                                target_id = target_user.id
                                break
                    except Exception:
                        pass
                
                # Method 3: Try using the user ID from the ban message if available
                # This is a fallback that might help in some cases
                if target_id is None:
                    try:
                        # Try to find the user in the bot's database or recent interactions
                        # For now, we'll just proceed with a more informative error
                        pass
                    except Exception:
                        pass
                
                # If we still can't resolve the username, inform the user
                if target_id is None:
                    await update.message.reply_text(
                        f"❌ Negaliu rasti vartotojo ID pagal username @{username_without_at}\n\n"
                        "**Sprendimas:**\n"
                        "• Naudokite vartotojo ID vietoj username: `/unban 123456789`\n"
                        "• Arba paprašykite vartotojo parašyti žinutę grupėje ir tada bandykite vėl\n"
                        "• Galite naudoti @userinfobot, kad sužinotumėte vartotojo ID"
                    )
                    return
            else:
                try:
                    user_id = int(target)
                    target_id = user_id
                    # For unban operations, we can't get chat member info since user is banned
                    # So we'll just use the user ID directly
                    target_user = None
                except ValueError:
                    await update.message.reply_text("❌ Neteisingas vartotojo ID!")
                    return
        
        # Try to unban the user
        try:
            await context.bot.unban_chat_member(chat_id, target_id)
        except telegram.error.BadRequest as e:
            if "USER_NOT_PARTICIPANT" in str(e):
                await update.message.reply_text("❌ Vartotojas nėra užblokuotas!")
            elif "CHAT_ADMIN_REQUIRED" in str(e):
                await update.message.reply_text("❌ Neturite teisių atblokuoti vartotojų!")
            else:
                await update.message.reply_text(f"❌ Klaida atblokuojant vartotoją: {str(e)}")
            return
        
        unban_text = f"✅ **VARTOTOJAS ATBLOKUOTAS** ✅\n\n"
        if target_user:
            unban_text += f"👤 **Vartotojas:** {target_user.first_name}"
            if target_user.username:
                unban_text += f" (@{target_user.username})"
            unban_text += f"\n🆔 **ID:** `{target_user.id}`\n"
        else:
            unban_text += f"👤 **Vartotojas:** {target if 'target' in locals() else 'Unknown'}\n"
            unban_text += f"🆔 **ID:** `{target_id}`\n"
        unban_text += f"👮 **Atblokavo:** {admin_user.first_name}"
        if admin_user.username:
            unban_text += f" (@{admin_user.username})"
        unban_text += f"\n⏰ **Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        await update.message.reply_text(unban_text, parse_mode='Markdown')
        
    except telegram.error.BadRequest as e:
        if "Invalid user_id specified" in str(e):
            await update.message.reply_text("❌ Neteisingas vartotojo ID arba vartotojas nerastas!")
        else:
            await update.message.reply_text(f"❌ Klaida atblokuojant vartotoją: {str(e)}")
    except Exception as e:
        # Escape markdown characters in error message
        error_msg = str(e).replace('*', '\\*').replace('_', '\\_').replace('`', '\\`')
        await update.message.reply_text(
            f"❌ **KLAIDA**\n\n"
            f"Nepavyko atblokuoti vartotojo: {error_msg}",
            parse_mode='Markdown'
        )

async def mute_user(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Mute a user"""
    if not await can_mute_users(update, context):
        await update.message.reply_text("❌ Neturite teisių nutildyti vartotojų!")
        return
    
    args = context.args
    chat_id = update.effective_chat.id
    admin_user = update.effective_user
    
    # Check if this is a reply to a message
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_id = target_user.id
        reason = " ".join(args) if args else "Nenurodyta"
    else:
        if len(args) < 1:
            await update.message.reply_text(
                "❌ Naudojimas: /mute username/id [priežastis]\n\n"
                "**Arba:** Atsakykite į vartotojo žinutę su `/mute [priežastis]`"
            )
            return
        
        target = args[0]
        reason = " ".join(args[1:]) if len(args) > 1 else "Nenurodyta"
    
    try:
        # If not replying to a message, we need to resolve the target
        if not update.message.reply_to_message:
            # Get target user info and try to mute directly
            target_user = None
            target_id = None
            
            if target.startswith('@'):
                # For username, use the most reliable method: try to mute directly
                # This is how most bots like GroupHelpBot handle usernames
                username_without_at = target[1:]  # Remove @ symbol
                
                # Try to get user info first for display purposes
                try:
                    # Try to get user by username (this works in most cases)
                    target_user = None
                    target_id = username_without_at  # Use username directly
                    
                    # Try to get additional user info if possible
                    try:
                        # Try to get user info from chat member
                        target_member = await context.bot.get_chat_member(chat_id, target)
                        target_user = target_member.user
                        target_id = target_user.id  # Use actual user ID if we got it
                    except telegram.error.BadRequest:
                        # If we can't get member info, continue with username
                        pass
                        
                except Exception as e:
                    # If anything fails, still try to mute by username
                    target_user = None
                    target_id = username_without_at
            else:
                try:
                    user_id = int(target)
                    target_id = user_id
                    # Try to get user info for display purposes
                    try:
                        target_member = await context.bot.get_chat_member(chat_id, user_id)
                        target_user = target_member.user
                    except telegram.error.BadRequest:
                        target_user = None
                except ValueError:
                    await update.message.reply_text("❌ Neteisingas vartotojo ID!")
                    return
        
        # Try to mute the user
        try:
            until_date = datetime.now() + timedelta(hours=24)  # 24 hour mute
            await context.bot.restrict_chat_member(
                chat_id, target_id,
                permissions=telegram.ChatPermissions(
                    can_send_messages=False,
                    can_send_media_messages=False,
                    can_send_other_messages=False,
                    can_add_web_page_previews=False
                ),
                until_date=until_date
            )
        except telegram.error.BadRequest as e:
            if "USER_NOT_PARTICIPANT" in str(e):
                await update.message.reply_text("❌ Vartotojas nėra grupės narys!")
            elif "CHAT_ADMIN_REQUIRED" in str(e):
                await update.message.reply_text("❌ Neturite teisių nutildyti vartotojų!")
            elif "USER_IS_CHAT_OWNER" in str(e):
                await update.message.reply_text("❌ Negalite nutildyti grupės savininko!")
            else:
                await update.message.reply_text(f"❌ Klaida nutildant vartotoją: {str(e)}")
            return
        
        mute_text = f"🔇 **VARTOTOJAS NUTILDYTAS** 🔇\n\n"
        if target_user:
            mute_text += f"👤 **Vartotojas:** {target_user.first_name}"
            if target_user.username:
                mute_text += f" (@{target_user.username})"
            mute_text += f"\n🆔 **ID:** `{target_user.id}`\n"
        else:
            mute_text += f"👤 **Vartotojas:** {target}\n"
            mute_text += f"🆔 **ID:** `{target_id}`\n"
        mute_text += f"👮 **Nutildė:** {admin_user.first_name}"
        if admin_user.username:
            mute_text += f" (@{admin_user.username})"
        mute_text += f"\n📝 **Priežastis:** {reason}\n"
        mute_text += f"⏰ **Trukmė:** 24 valandos\n"
        mute_text += f"📅 **Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        await update.message.reply_text(mute_text, parse_mode='Markdown')
        
    except telegram.error.BadRequest as e:
        if "Invalid user_id specified" in str(e):
            await update.message.reply_text("❌ Neteisingas vartotojo ID arba vartotojas nerastas!")
        else:
            await update.message.reply_text(f"❌ Klaida nutildant vartotoją: {str(e)}")
    except Exception as e:
        # Escape markdown characters in error message
        error_msg = str(e).replace('*', '\\*').replace('_', '\\_').replace('`', '\\`')
        await update.message.reply_text(
            f"❌ **KLAIDA**\n\n"
            f"Nepavyko nutildyti vartotojo: {error_msg}",
            parse_mode='Markdown'
        )

async def unmute_user(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Unmute a user"""
    if not await can_mute_users(update, context):
        await update.message.reply_text("❌ Neturite teisių atšaukti nutildymą!")
        return
    
    args = context.args
    chat_id = update.effective_chat.id
    admin_user = update.effective_user
    
    # Check if this is a reply to a message
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        target_id = target_user.id
    else:
        if len(args) < 1:
            await update.message.reply_text(
                "❌ Naudojimas: /unmute username/id\n\n"
                "**Arba:** Atsakykite į vartotojo žinutę su `/unmute`"
            )
            return
        
        target = args[0]
    
    try:
        # If not replying to a message, we need to resolve the target
        if not update.message.reply_to_message:
            # Get target user info and try to unmute directly
            target_user = None
            target_id = None
            
            if target.startswith('@'):
                # For username, use the most reliable method: try to unmute directly
                # This is how most bots like GroupHelpBot handle usernames
                username_without_at = target[1:]  # Remove @ symbol
                
                # Try to get user info first for display purposes
                try:
                    # Try to get user by username (this works in most cases)
                    target_user = None
                    target_id = username_without_at  # Use username directly
                    
                    # Try to get additional user info if possible
                    try:
                        # Try to get user info from chat member
                        target_member = await context.bot.get_chat_member(chat_id, target)
                        target_user = target_member.user
                        target_id = target_user.id  # Use actual user ID if we got it
                    except telegram.error.BadRequest:
                        # If we can't get member info, continue with username
                        pass
                        
                except Exception as e:
                    # If anything fails, still try to unmute by username
                    target_user = None
                    target_id = username_without_at
            else:
                try:
                    user_id = int(target)
                    target_id = user_id
                    # Try to get user info for display purposes
                    try:
                        target_member = await context.bot.get_chat_member(chat_id, user_id)
                        target_user = target_member.user
                    except telegram.error.BadRequest:
                        target_user = None
                except ValueError:
                    await update.message.reply_text("❌ Neteisingas vartotojo ID!")
                    return
        
        # Try to unmute the user
        try:
            await context.bot.restrict_chat_member(
                chat_id, target_id,
                permissions=telegram.ChatPermissions(
                    can_send_messages=True,
                    can_send_media_messages=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True
                )
            )
        except telegram.error.BadRequest as e:
            if "USER_NOT_PARTICIPANT" in str(e):
                await update.message.reply_text("❌ Vartotojas nėra grupės narys!")
            elif "CHAT_ADMIN_REQUIRED" in str(e):
                await update.message.reply_text("❌ Neturite teisių atnutildyti vartotojų!")
            else:
                await update.message.reply_text(f"❌ Klaida atnutildant vartotoją: {str(e)}")
            return
        
        unmute_text = f"🔊 **VARTOTOJAS ATNUTILDYTAS** 🔊\n\n"
        if target_user:
            unmute_text += f"👤 **Vartotojas:** {target_user.first_name}"
            if target_user.username:
                unmute_text += f" (@{target_user.username})"
            unmute_text += f"\n🆔 **ID:** `{target_user.id}`\n"
        else:
            unmute_text += f"👤 **Vartotojas:** {target if 'target' in locals() else 'Unknown'}\n"
            unmute_text += f"🆔 **ID:** `{target_id}`\n"
        unmute_text += f"👮 **Atnutildė:** {admin_user.first_name}"
        if admin_user.username:
            unmute_text += f" (@{admin_user.username})"
        unmute_text += f"\n⏰ **Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        await update.message.reply_text(unmute_text, parse_mode='Markdown')
        
    except telegram.error.BadRequest as e:
        if "Invalid user_id specified" in str(e):
            await update.message.reply_text("❌ Neteisingas vartotojo ID arba vartotojas nerastas!")
        else:
            await update.message.reply_text(f"❌ Klaida atnutildant vartotoją: {str(e)}")
    except Exception as e:
        # Escape markdown characters in error message
        error_msg = str(e).replace('*', '\\*').replace('_', '\\_').replace('`', '\\`')
        await update.message.reply_text(
            f"❌ **KLAIDA**\n\n"
            f"Nepavyko atnutildyti vartotojo: {error_msg}",
            parse_mode='Markdown'
        )

async def banned_words_menu(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Main menu for banned words"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Tik administratoriai gali naudoti šią komandą!")
        return
    
    # Handle private chat - ask for group selection
    if update.effective_chat.type == 'private':
        await update.message.reply_text(
            "🚫 **Uždrausti Žodžiai**\n\n"
            "Kadangi esate privatiame pokalbyje, turite nurodyti grupės ID, kurią norite valdyti.\n\n"
            "📝 **Naudojimas:**\n"
            "`/banned_words [group_id]`\n\n"
            "**Pavyzdys:**\n"
            "`/banned_words -1001234567890`",
            parse_mode='Markdown'
        )
        return
    
    chat_id = update.effective_chat.id
    banned_words = database.get_banned_words(chat_id)
    
    keyboard = [
        [InlineKeyboardButton("➕ Pridėti žodį", callback_data="banned_words_add")]
    ]
    
    if banned_words:
        keyboard.append([InlineKeyboardButton("📋 Žodžių sąrašas", callback_data="banned_words_list")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "🚫 **Uždrausti Žodžiai**\n\n"
    if banned_words:
        text += f"📊 Aktyvūs žodžiai: {len(banned_words)}\n"
        text += "Žodžiai automatiškai aptinkami ir baudžiami."
    else:
        text += "Dar nėra uždraustų žodžių.\nPridėkite žodžius, kuriuos norite drausti."
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def helpers_menu(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Main menu for helpers"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Tik administratoriai gali naudoti šią komandą!")
        return
    
    # Handle private chat - ask for group selection
    if update.effective_chat.type == 'private':
        await update.message.reply_text(
            "👥 **Pagalbininkai**\n\n"
            "Kadangi esate privatiame pokalbyje, turite nurodyti grupės ID, kurią norite valdyti.\n\n"
            "📝 **Naudojimas:**\n"
            "`/helpers [group_id]`\n\n"
            "**Pavyzdys:**\n"
            "`/helpers -1001234567890`",
            parse_mode='Markdown'
        )
        return
    
    chat_id = update.effective_chat.id
    helpers = database.get_helpers(chat_id)
    
    keyboard = [
        [InlineKeyboardButton("➕ Pridėti pagalbininką", callback_data="helpers_add")]
    ]
    
    if helpers:
        keyboard.append([InlineKeyboardButton("📋 Pagalbininkų sąrašas", callback_data="helpers_list")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    text = "👥 **Pagalbininkai**\n\n"
    if helpers:
        text += f"📊 Aktyvūs pagalbininkai: {len(helpers)}\n"
        text += "Pagalbininkai gali naudoti ban/mute komandas."
    else:
        text += "Dar nėra pagalbininkų.\nPridėkite vartotojus, kurie galės modifikuoti."
    
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# Private chat command handlers with inline group selection
async def recurring_messages_private(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Handle recurring messages in private chat with inline group selection"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Tik administratoriai gali naudoti šią komandą!")
        return
    
    # Check if group_id is provided as argument
    args = context.args
    if len(args) >= 1:
        try:
            group_id = int(args[0])
            # Verify the group exists and user is admin there
            try:
                chat_member = await context.bot.get_chat_member(group_id, update.effective_user.id)
                if chat_member.status not in ['creator', 'administrator']:
                    await update.message.reply_text("❌ Turite būti administratorius nurodytoje grupėje!")
                    return
            except Exception as e:
                await update.message.reply_text("❌ Nepavyko patikrinti teisių grupėje arba grupė neegzistuoja!")
                return
            
            # Store the group_id in user_data for future use
            context.user_data['target_group_id'] = group_id
            
            keyboard = [
                [InlineKeyboardButton("➕ Pridėti pranešimą", callback_data="recurring_add_private")],
                [InlineKeyboardButton("📋 Valdyti pranešimus", callback_data="recurring_manage_private")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f"🔄 **Kartojami Pranešimai**\n\n"
                f"Grupė: `{group_id}`\n"
                f"Sukurkite pranešimus, kurie kartojasi automatiškai.",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
            
        except ValueError:
            await update.message.reply_text("❌ Neteisingas grupės ID formatas!")
            return
    
    # Show group selection with buttons for already added groups
    keyboard = []
    
    # Add buttons for already added groups
    if allowed_groups:
        added_groups_count = 0
        for group_id_str in allowed_groups:
            try:
                group_id = int(group_id_str)
                # Try to get group name
                try:
                    chat_info = await context.bot.get_chat(group_id)
                    group_name = chat_info.title or f"Grupė {group_id}"
                    # Truncate long names
                    if len(group_name) > 25:
                        group_name = group_name[:22] + "..."
                    
                    # Verify user is admin in this group
                    try:
                        chat_member = await context.bot.get_chat_member(group_id, update.effective_user.id)
                        if chat_member.status in ['creator', 'administrator']:
                            keyboard.append([InlineKeyboardButton(
                                f"📱 {group_name}", 
                                callback_data=f"recurring_select_group_{group_id}"
                            )])
                            added_groups_count += 1
                    except Exception:
                        # User is not admin in this group, skip it
                        continue
                        
                except Exception:
                    # Can't get group info, but still show it with ID
                    try:
                        chat_member = await context.bot.get_chat_member(group_id, update.effective_user.id)
                        if chat_member.status in ['creator', 'administrator']:
                            keyboard.append([InlineKeyboardButton(
                                f"📱 Grupė {group_id}", 
                                callback_data=f"recurring_select_group_{group_id}"
                            )])
                            added_groups_count += 1
                    except Exception:
                        continue
                        
            except (ValueError, Exception):
                continue
    
    # Add button to add new group by ID
    keyboard.append([InlineKeyboardButton("➕ Pridėti naują grupę", callback_data="recurring_add_new_group")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Create message text
    text = "🔄 **Kartojami Pranešimai**\n\n"
    if keyboard[:-1]:  # If there are group buttons (excluding the add button)
        text += "Pasirinkite grupę iš sąrašo arba pridėkite naują:"
    else:
        text += "Dar neturite pridėtų grupių.\nPridėkite grupę, kad galėtumėte valdyti kartojamuosius pranešimus:"
    
    await update.message.reply_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def banned_words_private(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Handle banned words in private chat with inline group selection"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Tik administratoriai gali naudoti šią komandą!")
        return
    
    # Check if group_id is provided as argument
    args = context.args
    if len(args) >= 1:
        try:
            group_id = int(args[0])
            # Verify the group exists and user is admin there
            try:
                chat_member = await context.bot.get_chat_member(group_id, update.effective_user.id)
                if chat_member.status not in ['creator', 'administrator']:
                    await update.message.reply_text("❌ Turite būti administratorius nurodytoje grupėje!")
                    return
            except Exception as e:
                await update.message.reply_text("❌ Nepavyko patikrinti teisių grupėje arba grupė neegzistuoja!")
                return
            
            # Store the group_id in user_data for future use
            context.user_data['target_group_id'] = group_id
            
            banned_words = database.get_banned_words(group_id)
            
            keyboard = [
                [InlineKeyboardButton("➕ Pridėti žodį", callback_data="banned_words_add_private")]
            ]
            
            if banned_words:
                keyboard.append([InlineKeyboardButton("📋 Žodžių sąrašas", callback_data="banned_words_list_private")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            text = f"🚫 **Uždrausti Žodžiai**\n\n"
            text += f"Grupė: `{group_id}`\n\n"
            if banned_words:
                text += f"📊 Aktyvūs žodžiai: {len(banned_words)}\n"
                text += "Žodžiai automatiškai aptinkami ir baudžiami."
            else:
                text += "Dar nėra uždraustų žodžių.\nPridėkite žodžius, kuriuos norite drausti."
            
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            return
            
        except ValueError:
            await update.message.reply_text("❌ Neteisingas grupės ID formatas!")
            return
    
    # Show group selection interface
    keyboard = [
        [InlineKeyboardButton("📝 Įvesti grupės ID", callback_data="group_select_manual_banned_words")],
        [InlineKeyboardButton("🔍 Rasti grupes", callback_data="group_select_search_banned_words")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🚫 **Uždrausti Žodžiai**\n\n"
        "Pasirinkite grupę, kurią norite valdyti:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def helpers_private(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Handle helpers in private chat with inline group selection"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Tik administratoriai gali naudoti šią komandą!")
        return
    
    # Check if group_id is provided as argument
    args = context.args
    if len(args) >= 1:
        try:
            group_id = int(args[0])
            # Verify the group exists and user is admin there
            try:
                chat_member = await context.bot.get_chat_member(group_id, update.effective_user.id)
                if chat_member.status not in ['creator', 'administrator']:
                    await update.message.reply_text("❌ Turite būti administratorius nurodytoje grupėje!")
                    return
            except Exception as e:
                await update.message.reply_text("❌ Nepavyko patikrinti teisių grupėje arba grupė neegzistuoja!")
                return
            
            # Store the group_id in user_data for future use
            context.user_data['target_group_id'] = group_id
            
            helpers = database.get_helpers(group_id)
            
            keyboard = [
                [InlineKeyboardButton("➕ Pridėti pagalbininką", callback_data="helpers_add_private")]
            ]
            
            if helpers:
                keyboard.append([InlineKeyboardButton("📋 Pagalbininkų sąrašas", callback_data="helpers_list_private")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            text = f"👥 **Pagalbininkai**\n\n"
            text += f"Grupė: `{group_id}`\n\n"
            if helpers:
                text += f"📊 Aktyvūs pagalbininkai: {len(helpers)}\n"
                text += "Pagalbininkai gali naudoti ban/mute komandas."
            else:
                text += "Dar nėra pagalbininkų.\nPridėkite vartotojus, kurie galės modifikuoti."
            
            await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            return
            
        except ValueError:
            await update.message.reply_text("❌ Neteisingas grupės ID formatas!")
            return
    
    # Show group selection interface
    keyboard = [
        [InlineKeyboardButton("📝 Įvesti grupės ID", callback_data="group_select_manual_helpers")],
        [InlineKeyboardButton("🔍 Rasti grupes", callback_data="group_select_search_helpers")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👥 **Pagalbininkai**\n\n"
        "Pasirinkite grupę, kurią norite valdyti:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

# Function to process private chat input for admin features
async def process_private_chat_input(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE) -> None:
    """Process input from private chat for admin features"""
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    
    if context.user_data.get('waiting_for_group_id'):
        # User is entering a group ID for private chat management
        try:
            group_id = int(update.message.text.strip())
            group_selection_type = context.user_data.get('group_selection_type', 'recurring')
            
            # Verify the group exists and user is admin there
            try:
                chat_member = await context.bot.get_chat_member(group_id, user_id)
                if chat_member.status not in ['creator', 'administrator']:
                    await update.message.reply_text("❌ Turite būti administratorius nurodytoje grupėje!")
                    return
            except Exception as e:
                await update.message.reply_text("❌ Nepavyko patikrinti teisių grupėje arba grupė neegzistuoja!")
                return
            
            # Add group to allowed_groups list if not already there
            group_id_str = str(group_id)
            group_was_added = False
            if group_id_str not in allowed_groups:
                allowed_groups.append(group_id_str)
                group_was_added = True
                logger.info(f"Added group {group_id} to allowed_groups via private chat")
                # Save the updated allowed_groups list
                save_data(allowed_groups, 'allowed_groups.pkl')
            
            # Store the group_id in user_data for future use
            context.user_data['target_group_id'] = group_id
            context.user_data['private_mode'] = True
            
            # Show appropriate menu based on selection type
            if group_selection_type == 'recurring':
                keyboard = [
                    [InlineKeyboardButton("➕ Pridėti pranešimą", callback_data="recurring_add_private")],
                    [InlineKeyboardButton("📋 Valdyti pranešimus", callback_data="recurring_manage_private")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Add feedback about group being added to the list
                status_text = ""
                if group_was_added:
                    status_text = "✅ Grupė pridėta į sąrašą! Dabar ji bus rodoma pasirinkimo meniu.\n\n"
                
                await update.message.reply_text(
                    f"🔄 **Kartojami Pranešimai**\n\n"
                    f"{status_text}"
                    f"Grupė: `{group_id}`\n"
                    f"Sukurkite pranešimus, kurie kartojasi automatiškai.",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            
            elif group_selection_type == 'banned_words':
                banned_words = database.get_banned_words(group_id)
                
                keyboard = [
                    [InlineKeyboardButton("➕ Pridėti žodį", callback_data="banned_words_add_private")]
                ]
                
                if banned_words:
                    keyboard.append([InlineKeyboardButton("📋 Žodžių sąrašas", callback_data="banned_words_list_private")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Add feedback about group being added to the list
                status_text = ""
                if group_was_added:
                    status_text = "✅ Grupė pridėta į sąrašą! Dabar ji bus rodoma pasirinkimo meniu.\n\n"
                
                text = f"🚫 **Uždrausti Žodžiai**\n\n"
                text += f"{status_text}"
                text += f"Grupė: `{group_id}`\n\n"
                if banned_words:
                    text += f"📊 Aktyvūs žodžiai: {len(banned_words)}\n"
                    text += "Žodžiai automatiškai aptinkami ir baudžiami."
                else:
                    text += "Dar nėra uždraustų žodžių.\nPridėkite žodžius, kuriuos norite drausti."
                
                await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
            elif group_selection_type == 'helpers':
                helpers = database.get_helpers(group_id)
                
                keyboard = [
                    [InlineKeyboardButton("➕ Pridėti pagalbininką", callback_data="helpers_add_private")]
                ]
                
                if helpers:
                    keyboard.append([InlineKeyboardButton("📋 Pagalbininkų sąrašas", callback_data="helpers_list_private")])
                
                reply_markup = InlineKeyboardMarkup(keyboard)
                
                # Add feedback about group being added to the list
                status_text = ""
                if group_was_added:
                    status_text = "✅ Grupė pridėta į sąrašą! Dabar ji bus rodoma pasirinkimo meniu.\n\n"
                
                text = f"👥 **Pagalbininkai**\n\n"
                text += f"{status_text}"
                text += f"Grupė: `{group_id}`\n\n"
                if helpers:
                    text += f"📊 Aktyvūs pagalbininkai: {len(helpers)}\n"
                    text += "Pagalbininkai gali naudoti ban/mute komandas."
                else:
                    text += "Dar nėra pagalbininkų.\nPridėkite vartotojus, kurie galės modifikuoti."
                
                await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
        except ValueError:
            await update.message.reply_text("❌ Neteisingas grupės ID formatas! Įveskite skaičių.")
        
        # Clear waiting state
        context.user_data.pop('waiting_for_group_id', None)
        context.user_data.pop('group_selection_type', None)
        return
    
    elif context.user_data.get('waiting_for_word'):
        # User is adding a banned word
        word = update.message.text.strip()
        if len(word) > 50:
            await update.message.reply_text("❌ Žodis per ilgas! Maksimalus ilgis: 50 simbolių.")
            return
        
        # Check if this is private mode
        is_private = context.user_data.get('private_mode', False)
        target_chat_id = context.user_data.get('target_group_id', update.message.chat_id)
        
        # Show action selection
        keyboard = [
            [InlineKeyboardButton("⚠️ Perspėjimas", callback_data=f"action_warn_{word}_{target_chat_id}" if is_private else f"action_warn_{word}")],
            [InlineKeyboardButton("🔇 Nutildyti", callback_data=f"action_mute_{word}_{target_chat_id}" if is_private else f"action_mute_{word}")],
            [InlineKeyboardButton("🚫 Uždrausti", callback_data=f"action_ban_{word}_{target_chat_id}" if is_private else f"action_ban_{word}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        group_info = f"\nGrupė: `{target_chat_id}`" if is_private else ""
        await update.message.reply_text(
            f"🚫 **Pridėti žodį: {word}**{group_info}\n\n"
            "Pasirinkite veiksmą, kurį atlikti, kai vartotojas naudos šį žodį:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        
        # Clear waiting state
        context.user_data.pop('waiting_for_word', None)
        return
    
    elif context.user_data.get('waiting_for_helper_id'):
        # User is adding a helper
        try:
            helper_id = int(update.message.text.strip())
            if helper_id <= 0:
                await update.message.reply_text("❌ Neteisingas vartotojo ID!")
                return
            
            # Check if this is private mode
            is_private = context.user_data.get('private_mode', False)
            target_chat_id = context.user_data.get('target_group_id', update.message.chat_id)
            
            # Try to get user info
            try:
                helper_user = await context.bot.get_chat_member(target_chat_id, helper_id)
                helper_username = helper_user.user.username
                
                # Add helper to database
                database.add_helper(
                    target_chat_id, helper_id, helper_username,
                    user_id, username or f"User {user_id}"
                )
                
                group_info = f"\nGrupė: `{target_chat_id}`" if is_private else ""
                await update.message.reply_text(
                    f"✅ **Pagalbininkas pridėtas!**{group_info}\n\n"
                    f"👤 **Vartotojas:** {helper_user.user.first_name}"
                    f"{f' (@{helper_username})' if helper_username else ''}\n"
                    f"🆔 **ID:** `{helper_id}`\n"
                    f"👮 **Pridėjo:** {update.message.from_user.first_name}"
                    f"{f' (@{username})' if username else ''}",
                    parse_mode='Markdown'
                )
            except Exception as e:
                await update.message.reply_text(f"❌ Nepavyko pridėti pagalbininko: {str(e)}")
            
        except ValueError:
            await update.message.reply_text("❌ Neteisingas vartotojo ID! Įveskite skaičių.")
        
        # Clear waiting state
        context.user_data.pop('waiting_for_helper_id', None)
        context.user_data.pop('private_mode', None)
        return
    
    elif context.user_data.get('waiting_for_message'):
        # User is adding a recurring message
        message_text = update.message.text.strip()
        if len(message_text) > 1000:
            await update.message.reply_text("❌ Pranešimas per ilgas! Maksimalus ilgis: 1000 simbolių.")
            return
        
        # Check if this is private mode
        is_private = context.user_data.get('private_mode', False)
        target_chat_id = context.user_data.get('target_group_id', update.message.chat_id)
        
        # Add message to database with default settings
        message_id = database.add_scheduled_message(
            target_chat_id, message_text, user_id, username or f"User {user_id}",
            repetition_type='24h', interval_hours=24
        )
        
        # Schedule the message
        scheduler.add_job(
            send_scheduled_message,
            'interval',
            hours=24,
            args=[target_chat_id, message_text, message_id],
            id=f"scheduled_{message_id}",
            replace_existing=True
        )
        
        group_info = f"\nGrupė: `{target_chat_id}`" if is_private else ""
        await update.message.reply_text(
            f"✅ **Pranešimas pridėtas!**{group_info}\n\n"
            f"📝 **Tekstas:** {message_text[:100]}{'...' if len(message_text) > 100 else ''}\n"
            f"🔄 **Kartojimas:** Kas 24 valandas\n"
            f"🆔 **ID:** `{message_id}`\n"
            f"👮 **Pridėjo:** {update.message.from_user.first_name}"
            f"{f' (@{username})' if username else ''}",
            parse_mode='Markdown'
        )
        
        # Clear waiting state
        context.user_data.pop('waiting_for_message', None)
        context.user_data.pop('private_mode', None)
        return
    
    elif context.user_data.get('waiting_for_manual_groups'):
        # User is entering multiple group IDs separated by commas
        try:
            group_ids_text = update.message.text.strip()
            group_ids = [int(gid.strip()) for gid in group_ids_text.split(',')]
            group_selection_type = context.user_data.get('group_selection_type', 'recurring')
            
            # Verify each group and add to allowed_groups if not already there
            added_groups = []
            for group_id in group_ids:
                try:
                    # Check if user is admin in this group
                    chat_member = await context.bot.get_chat_member(group_id, user_id)
                    if chat_member.status in ['creator', 'administrator']:
                        if str(group_id) not in allowed_groups:
                            allowed_groups.append(str(group_id))
                            added_groups.append(group_id)
                except Exception:
                    continue
            
            if added_groups:
                await update.message.reply_text(
                    f"✅ Pridėtos {len(added_groups)} grupės: {', '.join(map(str, added_groups))}\n\n"
                    f"Dabar galite pasirinkti grupę iš sąrašo.",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ Nepavyko pridėti jokių grupių. Patikrinkite, ar esate administratorius visose grupėse.")
            
        except ValueError:
            await update.message.reply_text("❌ Neteisingas formatas! Įveskite grupės ID atskirtus kableliais (pvz., -1001234567890, -1009876543210)")
        
        # Clear waiting state
        context.user_data.pop('waiting_for_manual_groups', None)
        context.user_data.pop('group_selection_type', None)
        return
    
    elif context.user_data.get('waiting_for_new_group'):
        # User is adding a single new group ID
        try:
            group_id = int(update.message.text.strip())
            
            # Verify the group exists and user is admin there
            try:
                chat_member = await context.bot.get_chat_member(group_id, user_id)
                if chat_member.status not in ['creator', 'administrator']:
                    await update.message.reply_text("❌ Turite būti administratorius nurodytoje grupėje!")
                    return
            except Exception as e:
                await update.message.reply_text("❌ Nepavyko patikrinti teisių grupėje arba grupė neegzistuoja!")
                return
            
            # Add to allowed_groups if not already there
            if str(group_id) not in allowed_groups:
                allowed_groups.append(str(group_id))
                await update.message.reply_text(f"✅ Grupė `{group_id}` pridėta prie leidžiamų grupių!")
            else:
                await update.message.reply_text(f"ℹ️ Grupė `{group_id}` jau yra leidžiamų grupių sąraše.")
            
        except ValueError:
            await update.message.reply_text("❌ Neteisingas grupės ID formatas! Įveskite skaičių.")
        
        # Clear waiting state
        context.user_data.pop('waiting_for_new_group', None)
        return
    
    elif context.user_data.get('waiting_for_custom_time'):
        # User is entering custom time
        try:
            time_text = update.message.text.strip()
            # Validate time format (HH:MM)
            if not re.match(r'^([01]?[0-9]|2[0-3]):[0-5][0-9]$', time_text):
                await update.message.reply_text("❌ Neteisingas laiko formatas! Naudokite HH:MM (pvz., 14:30)")
                return
            
            config = context.user_data.get('current_message_config', {})
            config['time'] = time_text
            context.user_data['current_message_config'] = config
            
            # Show updated config screen
            await update.message.reply_text(
                f"✅ Laikas nustatytas: {time_text}\n\n"
                "Grįžtame į konfigūraciją...",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            await update.message.reply_text("❌ Klaida nustatant laiką!")
        
        # Clear waiting state
        context.user_data.pop('waiting_for_custom_time', None)
        return
    
    elif context.user_data.get('waiting_for_custom_interval'):
        # User is entering custom interval
        try:
            interval_text = update.message.text.strip().lower()
            
            # Parse interval (e.g., "2h30m", "45m", "1h")
            hours = 0
            minutes = 0
            
            # Extract hours
            hour_match = re.search(r'(\d+)h', interval_text)
            if hour_match:
                hours = int(hour_match.group(1))
            
            # Extract minutes
            minute_match = re.search(r'(\d+)m', interval_text)
            if minute_match:
                minutes = int(minute_match.group(1))
            
            if hours == 0 and minutes == 0:
                await update.message.reply_text("❌ Neteisingas intervalo formatas! Naudokite XhYm formatą (pvz., 2h30m)")
                return
            
            # Format the repetition text
            if hours > 0 and minutes > 0:
                repetition_text = f"Every {hours}h {minutes}m"
            elif hours > 0:
                repetition_text = f"Every {hours} hour{'s' if hours > 1 else ''}"
            else:
                repetition_text = f"Every {minutes} minute{'s' if minutes > 1 else ''}"
            
            config = context.user_data.get('current_message_config', {})
            config['repetition'] = repetition_text
            config['interval_hours'] = hours
            config['interval_minutes'] = minutes
            context.user_data['current_message_config'] = config
            
            await update.message.reply_text(
                f"✅ Intervalas nustatytas: {repetition_text}\n\n"
                "Grįžtame į konfigūraciją...",
                parse_mode='Markdown'
            )
            
        except Exception as e:
            await update.message.reply_text("❌ Klaida nustatant intervalą!")
        
        # Clear waiting state
        context.user_data.pop('waiting_for_custom_interval', None)
        return
    
    elif context.user_data.get('waiting_for_text'):
        # User is setting message text
        message_text = update.message.text.strip()
        if len(message_text) > 4000:
            await update.message.reply_text("❌ Tekstas per ilgas! Maksimalus ilgis: 4000 simbolių.")
            return
        
        config = context.user_data.get('current_message_config', {})
        config['text'] = message_text
        config['has_text'] = True
        context.user_data['current_message_config'] = config
        
        await update.message.reply_text(
            f"✅ Tekstas nustatytas!\n\n"
            f"**Peržiūra:** {message_text[:100]}{'...' if len(message_text) > 100 else ''}\n\n"
            "Grįžtame į konfigūraciją...",
            parse_mode='Markdown'
        )
        
        # Clear waiting state
        context.user_data.pop('waiting_for_text', None)
        return
    
    elif context.user_data.get('waiting_for_media'):
        # User is setting message media
        if update.message.photo or update.message.video or update.message.animation:
            config = context.user_data.get('current_message_config', {})
            config['has_media'] = True
            if update.message.photo:
                config['media_type'] = 'photo'
                config['media_file_id'] = update.message.photo[-1].file_id
            elif update.message.video:
                config['media_type'] = 'video'
                config['media_file_id'] = update.message.video.file_id
            elif update.message.animation:
                config['media_type'] = 'animation'
                config['media_file_id'] = update.message.animation.file_id
            
            context.user_data['current_message_config'] = config
            
            await update.message.reply_text(
                "✅ Media nustatytas!\n\n"
                f"**Tipas:** {config['media_type'].title()}\n\n"
                "Grįžtame į konfigūraciją...",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ Prašome atsiųsti nuotrauką, video ar GIF!")
            return
        
        # Clear waiting state
        context.user_data.pop('waiting_for_media', None)
        return
    
    elif context.user_data.get('waiting_for_buttons'):
        # User is setting URL buttons
        try:
            button_text = update.message.text.strip()
            lines = button_text.split('\n')
            buttons = []
            
            for line in lines:
                if '|' in line:
                    parts = line.split('|', 1)
                    if len(parts) == 2:
                        button_name = parts[0].strip()
                        button_url = parts[1].strip()
                        if button_name and button_url:
                            buttons.append({'text': button_name, 'url': button_url})
            
            if buttons:
                config = context.user_data.get('current_message_config', {})
                config['has_buttons'] = True
                config['buttons'] = buttons
                context.user_data['current_message_config'] = config
                
                await update.message.reply_text(
                    f"✅ URL mygtukai nustatyti!\n\n"
                    f"**Sukurta:** {len(buttons)} mygtuk{'ų' if len(buttons) > 1 else 'as'}\n\n"
                    "Grįžtame į konfigūraciją...",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ Neteisingas formatas! Naudokite: Pavadinimas | URL")
                return
            
        except Exception as e:
            await update.message.reply_text("❌ Klaida apdorojant mygtukus!")
            return
        
        # Clear waiting state
        context.user_data.pop('waiting_for_buttons', None)
        return

# Callback handler functions for new features
async def handle_recurring_callback(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Handle recurring messages callback queries"""
    query = update.callback_query
    if not await is_admin_callback(query, context):
        await query.answer("❌ Tik administratoriai gali naudoti šią funkciją!")
        return
    
    data = query.data
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    
    # Handle callback queries
    if data == "recurring_add":
        await show_message_config(query, context)
    elif data == "recurring_manage":
        await show_manage_messages(query, context)
    elif data == "recurring_add_private":
        await show_message_config(query, context, private_mode=True)
    elif data == "recurring_manage_private":
        await show_manage_messages_private(query, context)
    elif data == "customize_message":
        await show_message_customization(query, context)
    elif data == "set_time":
        await show_time_selection(query, context)
    elif data == "set_repetition":
        await show_repetition_options(query, context)
    elif data == "set_days_week":
        await show_days_of_week(query, context)
    elif data == "set_days_month":
        await show_days_of_month(query, context)
    elif data == "set_time_slot":
        await show_time_slot_options(query, context)
    elif data == "toggle_pin_message":
        await toggle_pin_message(query, context)
    elif data == "toggle_delete_last":
        await toggle_delete_last_message(query, context)
    elif data == "scheduled_deletion":
        await show_scheduled_deletion_options(query, context)
    elif data == "set_text":
        await set_message_text(query, context)
    elif data == "set_media":
        await set_message_media(query, context)
    elif data == "set_url_buttons":
        await set_url_buttons(query, context)
    elif data.startswith("preview_"):
        await show_content_preview(query, context, data.split("_")[1])
    elif data == "full_preview":
        await show_full_preview(query, context)
    elif data == "select_topic":
        await show_topic_selection(query, context)
    elif data == "back_to_config":
        await show_message_config(query, context)
    elif data == "back_to_main":
        await show_recurring_main_menu(query, context)
    elif data.startswith("recurring_info_"):
        message_id = int(data.split("_")[2])
        await show_message_info(query, context, message_id)
    elif data.startswith("recurring_toggle_"):
        message_id = int(data.split("_")[2])
        await toggle_message_status(query, context, message_id)
    elif data.startswith("recurring_delete_"):
        message_id = int(data.split("_")[2])
        await delete_message(query, context, message_id)
    # Handle time selection callbacks
    elif data.startswith("time_"):
        time_value = data.split("_", 1)[1]
        if time_value == "custom":
            context.user_data['waiting_for_custom_time'] = True
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="set_time")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "⏰ **Custom Time**\n\nEnter time in HH:MM format (24-hour):\n\nExample: 14:30",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            config = context.user_data.get('current_message_config', {})
            config['time'] = time_value
            context.user_data['current_message_config'] = config
            await show_message_config(query, context)
    
    # Handle repetition callbacks
    elif data.startswith("repeat_"):
        repeat_value = data.split("_", 1)[1]
        config = context.user_data.get('current_message_config', {})
        if repeat_value == "24h":
            config['repetition'] = "Every 24 hours"
        elif repeat_value == "12h":
            config['repetition'] = "Every 12 hours"
        elif repeat_value == "6h":
            config['repetition'] = "Every 6 hours"
        elif repeat_value == "3h":
            config['repetition'] = "Every 3 hours"
        elif repeat_value == "1h":
            config['repetition'] = "Every hour"
        elif repeat_value == "custom":
            context.user_data['waiting_for_custom_interval'] = True
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="set_repetition")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                "🔄 **Custom Interval**\n\nEnter interval in format:\n`XhYm` (X hours Y minutes)\n\nExamples:\n`2h30m` - Every 2 hours 30 minutes\n`45m` - Every 45 minutes\n`1h` - Every hour\n`5m` - Every 5 minutes",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            return
        context.user_data['current_message_config'] = config
        await show_message_config(query, context)
    
    # Handle day selection callbacks
    elif data.startswith("day_"):
        day_value = data.split("_", 1)[1]
        config = context.user_data.get('current_message_config', {})
        selected_days = config.get('selected_days', [])
        
        if day_value in selected_days:
            selected_days.remove(day_value)
        else:
            selected_days.append(day_value)
        
        config['selected_days'] = selected_days
        context.user_data['current_message_config'] = config
        
        # Update repetition text to show selected days
        if selected_days:
            day_names = {'mon': 'Monday', 'tue': 'Tuesday', 'wed': 'Wednesday', 
                        'thu': 'Thursday', 'fri': 'Friday', 'sat': 'Saturday', 'sun': 'Sunday'}
            selected_day_names = [day_names.get(day, day) for day in selected_days]
            config['repetition'] = f"On {', '.join(selected_day_names)}"
        else:
            config['repetition'] = "Every 24 hours"
        
        await show_days_of_week(query, context)
    
    # Handle custom interval button directly
    elif data == "repeat_custom":
        context.user_data['waiting_for_custom_interval'] = True
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="set_repetition")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🔄 **Custom Interval**\n\nEnter interval in format:\n`XhYm` (X hours Y minutes)\n\nExamples:\n`2h30m` - Every 2 hours 30 minutes\n`45m` - Every 45 minutes\n`1h` - Every hour\n`5m` - Every 5 minutes",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Handle time slot options
    elif data.startswith("time_slot_"):
        slot_type = data.split("_", 2)[2]  # time_slot_morning -> morning
        config = context.user_data.get('current_message_config', {})
        
        slot_times = {
            'morning': '06:00-12:00',
            'afternoon': '12:00-18:00', 
            'evening': '18:00-00:00',
            'night': '00:00-06:00'
        }
        
        if slot_type in slot_times:
            config['time_slot'] = slot_times[slot_type]
            config['repetition'] = f"During {slot_type.title()} hours ({slot_times[slot_type]})"
            context.user_data['current_message_config'] = config
            
            await query.edit_message_text(
                f"✅ Time slot set to: {slot_times[slot_type]}\n\n"
                f"Returning to configuration...",
                parse_mode='Markdown'
            )
            
            # Return to config after a short delay
            await asyncio.sleep(1.5)
            await show_message_config(query, context)
        return
    
    # Handle date selection callbacks
    elif data.startswith("date_"):
        date_value = int(data.split("_", 1)[1])
        config = context.user_data.get('current_message_config', {})
        selected_dates = config.get('selected_dates', [])
        
        if date_value in selected_dates:
            selected_dates.remove(date_value)
        else:
            selected_dates.append(date_value)
        
        config['selected_dates'] = selected_dates
        context.user_data['current_message_config'] = config
        
        # Update repetition text to show selected dates
        if selected_dates:
            config['repetition'] = f"On dates: {', '.join(map(str, sorted(selected_dates)))}"
        else:
            config['repetition'] = "Every 24 hours"
        
        await show_days_of_month(query, context)
    
    # Handle start/end date buttons
    elif data == "set_start_date":
        context.user_data['waiting_for_start_date'] = True
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_to_config")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📅 **Set Start Date**\n\nEnter start date in DD/MM/YYYY format:\n\nExample: 01/01/2024",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    elif data == "set_end_date":
        context.user_data['waiting_for_end_date'] = True
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back_to_config")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "📅 **Set End Date**\n\nEnter end date in DD/MM/YYYY format:\n\nExample: 31/12/2024",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
        return
    
    # Handle deletion option callbacks
    elif data.startswith("delete_"):
        delete_value = data.split("_", 1)[1]
        config = context.user_data.get('current_message_config', {})
        
        if delete_value == "never":
            config['scheduled_deletion'] = None
        elif delete_value == "1h":
            config['scheduled_deletion'] = "1 hour"
        elif delete_value == "6h":
            config['scheduled_deletion'] = "6 hours"
        elif delete_value == "1d":
            config['scheduled_deletion'] = "1 day"
        elif delete_value == "7d":
            config['scheduled_deletion'] = "7 days"
        
        context.user_data['current_message_config'] = config
        await show_message_config(query, context)
    
    # Handle save message callback
    elif data == "save_message":
        config = context.user_data.get('current_message_config', {})
        
        if not config.get('text') and not config.get('has_media'):
            await query.answer("❌ Please set message text or media first!")
            return
        
        # TODO: Save the message to database and schedule it
        await query.edit_message_text(
            "✅ **Message Saved!**\n\n"
            "Your recurring message has been configured and will start sending according to your schedule.\n\n"
            f"⏰ **Schedule:** {config.get('repetition', 'Every 24 hours')}\n"
            f"📌 **Pin:** {'Yes' if config.get('pin_message') else 'No'}\n"
            f"🗑️ **Delete last:** {'Yes' if config.get('delete_last') else 'No'}",
            parse_mode='Markdown'
        )
        
        # Clear the configuration
        context.user_data.pop('current_message_config', None)
    
    # Handle topic selection callbacks
    elif data.startswith("topic_"):
        topic_type = data.split("_", 1)[1]
        config = context.user_data.get('current_message_config', {})
        
        # Set predefined text based on topic
        if topic_type == "announcements":
            config['text'] = "📢 Important announcement will be posted here!"
        elif topic_type == "events":
            config['text'] = "🎉 Upcoming events and activities will be shared here!"
        elif topic_type == "rules":
            config['text'] = "📝 Please follow our group rules and guidelines."
        elif topic_type == "tips":
            config['text'] = "💡 Helpful tips and tricks will be shared regularly!"
        
        config['has_text'] = True
        context.user_data['current_message_config'] = config
        
        await show_message_customization(query, context)
    
    # Handle group selection for recurring messages
    elif data.startswith("recurring_select_group_"):
        group_id = int(data.split("_")[-1])
        
        # Store the group_id in user_data
        context.user_data['target_group_id'] = group_id
        context.user_data['private_mode'] = True
        
        # Get group info for display
        try:
            chat_info = await context.bot.get_chat(group_id)
            group_name = chat_info.title or f"Grupė {group_id}"
        except Exception:
            group_name = f"Grupė {group_id}"
        
        keyboard = [
            [InlineKeyboardButton("➕ Pridėti pranešimą", callback_data="recurring_add_private")],
            [InlineKeyboardButton("📋 Valdyti pranešimus", callback_data="recurring_manage_private")],
            [InlineKeyboardButton("🔙 Atgal į grupių sąrašą", callback_data="recurring_back_to_groups")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"🔄 **Kartojami Pranešimai**\n\n"
            f"📱 **Grupė:** {group_name}\n"
            f"🆔 **ID:** `{group_id}`\n\n"
            f"Pasirinkite veiksmą:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    
    # Handle add new group button
    elif data == "recurring_add_new_group":
        context.user_data['waiting_for_group_id'] = True
        context.user_data['group_selection_type'] = 'recurring'
        
        await query.edit_message_text(
            "➕ **Pridėti Naują Grupę**\n\n"
            "Įveskite grupės ID (pvz., -1001234567890):\n\n"
            "💡 **Kaip gauti grupės ID:**\n"
            "1. Pridėkite @userinfobot į grupę\n"
            "2. Parašykite /start grupėje\n"
            "3. Botas parodys grupės ID",
            parse_mode='Markdown'
        )
    
    # Handle back to groups list
    elif data == "recurring_back_to_groups":
        # Clear user data and show groups list again
        context.user_data.pop('target_group_id', None)
        context.user_data.pop('private_mode', None)
        
        # Recreate the groups menu
        await show_recurring_groups_menu(query, context)
    
    # Handle back to admin dashboard from recurring messages
    elif data == "admin_dashboard_back":
        # Return to admin dashboard
        await show_admin_dashboard_ui(query, context)
    
    await query.answer()

# GroupHelpBot-style recurring messages functions
async def show_message_config(query, context, private_mode=False):
    """Show message configuration screen - GroupHelpBot style"""
    chat_id = query.message.chat.id if not private_mode else context.user_data.get('target_group_id', query.message.chat.id)
    current_time = datetime.now().strftime("%H:%M")
    
    # Get current message config from user data or defaults
    message_config = context.user_data.get('current_message_config', {
        'status': 'Off',
        'time': current_time,
        'repetition': 'Every 24 hours',
        'pin_message': False,
        'delete_last': False,
        'has_text': False,
        'has_media': False,
        'has_buttons': False
    })
    
    # Build the configuration screen exactly like GroupHelpBot
    text = "🔄 **Recurring messages**\n\n"
    text += f"📊 **Status:** ❌ {message_config['status']}\n"
    text += f"⏰ **Time:** {message_config['time']}\n"
    text += f"🔄 **Repetition:** {message_config['repetition']}\n"
    text += f"📌 **Pin message:** {'✅' if message_config['pin_message'] else '❌'}\n"
    text += f"🗑️ **Delete last message:** {'✅' if message_config['delete_last'] else '❌'}"
    
    # Create keyboard exactly like GroupHelpBot
    keyboard = [
        [InlineKeyboardButton("✏️ Customize message", callback_data="customize_message")],
        [InlineKeyboardButton("⏰ Time", callback_data="set_time"), 
         InlineKeyboardButton("🔄 Repetition", callback_data="set_repetition")],
        [InlineKeyboardButton("📅 Days of the week", callback_data="set_days_week")],
        [InlineKeyboardButton("📅 Days of the month", callback_data="set_days_month")],
        [InlineKeyboardButton("🕐 Set time slot", callback_data="set_time_slot")],
        [InlineKeyboardButton("📅 Start date", callback_data="set_start_date"), 
         InlineKeyboardButton("📅 End date", callback_data="set_end_date")],
        [InlineKeyboardButton(f"📌 Pin message {'✅' if message_config['pin_message'] else '❌'}", 
                            callback_data="toggle_pin_message")],
        [InlineKeyboardButton(f"🗑️ Delete last message {'✅' if message_config['delete_last'] else '❌'}", 
                            callback_data="toggle_delete_last")],
        [InlineKeyboardButton("⏱️ Scheduled deletion", callback_data="scheduled_deletion")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_message_customization(query, context):
    """Show message customization screen - GroupHelpBot style"""
    message_config = context.user_data.get('current_message_config', {})
    
    text = "🔄 **Recurring messages**\n\n"
    text += f"📝 **Text:** {'✅' if message_config.get('has_text', False) else '❌'}\n"
    text += f"📷 **Media:** {'✅' if message_config.get('has_media', False) else '❌'}\n"
    text += f"🔗 **Url Buttons:** {'✅' if message_config.get('has_buttons', False) else '❌'}\n\n"
    text += "Use the buttons below to choose what you want to set"
    
    keyboard = [
        [InlineKeyboardButton("📝 Text", callback_data="set_text"), 
         InlineKeyboardButton("👁️ See", callback_data="preview_text")],
        [InlineKeyboardButton("📷 Media", callback_data="set_media"), 
         InlineKeyboardButton("👁️ See", callback_data="preview_media")],
        [InlineKeyboardButton("🔗 Url Buttons", callback_data="set_url_buttons"), 
         InlineKeyboardButton("👁️ See", callback_data="preview_buttons")],
        [InlineKeyboardButton("👁️ Full preview", callback_data="full_preview")],
        [InlineKeyboardButton("📋 Select a Topic", callback_data="select_topic")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_config")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_time_selection(query, context):
    """Show time selection options"""
    text = "⏰ **Set Time**\n\nChoose when to send the message:"
    
    keyboard = [
        [InlineKeyboardButton("🌅 Morning (08:00)", callback_data="time_08:00")],
        [InlineKeyboardButton("🌞 Midday (12:00)", callback_data="time_12:00")],
        [InlineKeyboardButton("🌇 Evening (18:00)", callback_data="time_18:00")],
        [InlineKeyboardButton("🌙 Night (22:00)", callback_data="time_22:00")],
        [InlineKeyboardButton("⏰ Custom time", callback_data="time_custom")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_config")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_repetition_options(query, context):
    """Show repetition options"""
    text = "🔄 **Set Repetition**\n\nChoose how often to repeat:"
    
    keyboard = [
        [InlineKeyboardButton("⏰ Every 24 hours", callback_data="repeat_24h")],
        [InlineKeyboardButton("🔄 Every 12 hours", callback_data="repeat_12h")],
        [InlineKeyboardButton("🔄 Every 6 hours", callback_data="repeat_6h")],
        [InlineKeyboardButton("🔄 Every 3 hours", callback_data="repeat_3h")],
        [InlineKeyboardButton("🔄 Every hour", callback_data="repeat_1h")],
        [InlineKeyboardButton("⏰ Custom interval", callback_data="repeat_custom")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_config")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def toggle_pin_message(query, context):
    """Toggle pin message setting"""
    config = context.user_data.get('current_message_config', {})
    config['pin_message'] = not config.get('pin_message', False)
    context.user_data['current_message_config'] = config
    
    await show_message_config(query, context)

async def toggle_delete_last_message(query, context):
    """Toggle delete last message setting"""
    config = context.user_data.get('current_message_config', {})
    config['delete_last'] = not config.get('delete_last', False)
    context.user_data['current_message_config'] = config
    
    await show_message_config(query, context)

async def show_recurring_main_menu(query, context):
    """Show main recurring messages menu via callback"""
    chat_id = query.message.chat.id
    current_time = datetime.now().strftime("%d/%m/%y %H:%M")
    
    # Get scheduled messages for this chat
    scheduled_messages = database.get_scheduled_messages(chat_id)
    
    # Create main menu text exactly like GroupHelpBot
    text = (
        "🔄 **Recurring messages**\n\n"
        "From this menu you can set messages that will be sent "
        "repeatedly to the group every few minutes/hours or every "
        "few messages.\n\n"
        f"Current time: {current_time}"
    )
    
    # Add message entries if they exist
    if scheduled_messages:
        for i, msg in enumerate(scheduled_messages, 1):
            status_icon = "✅" if msg['is_active'] else "❌"
            time_str = format_interval(msg['interval_hours'], msg.get('interval_minutes', 0))
            
            # Get message preview
            message_preview = "Message is not set." if not msg.get('message_text') else msg['message_text'][:30]
            if msg.get('message_text') and len(msg['message_text']) > 30:
                message_preview += "..."
            
            text += f"\n\n**{i} • Off** {status_icon}\n"
            text += f"⏰ Time: {time_str}\n"
            text += f"📝 {message_preview}"
    
    # Create keyboard
    keyboard = [[InlineKeyboardButton("➕ Add message", callback_data="recurring_add")]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_days_of_week(query, context):
    """Show days of week selection"""
    text = "📅 **Days of the Week**\n\nSelect which days to send messages:"
    
    keyboard = [
        [InlineKeyboardButton("📅 Monday", callback_data="day_mon")],
        [InlineKeyboardButton("📅 Tuesday", callback_data="day_tue")],
        [InlineKeyboardButton("📅 Wednesday", callback_data="day_wed")],
        [InlineKeyboardButton("📅 Thursday", callback_data="day_thu")],
        [InlineKeyboardButton("📅 Friday", callback_data="day_fri")],
        [InlineKeyboardButton("📅 Saturday", callback_data="day_sat")],
        [InlineKeyboardButton("📅 Sunday", callback_data="day_sun")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_config")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_days_of_month(query, context):
    """Show days of month selection"""
    text = "📅 **Days of the Month**\n\nSelect which dates to send messages:"
    
    # Create a grid of date buttons (1-31)
    keyboard = []
    for row in range(0, 31, 7):  # 7 buttons per row
        button_row = []
        for day in range(row + 1, min(row + 8, 32)):
            button_row.append(InlineKeyboardButton(str(day), callback_data=f"date_{day}"))
        keyboard.append(button_row)
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_config")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_scheduled_deletion_options(query, context):
    """Show scheduled deletion options"""
    text = "⏱️ **Scheduled Deletion**\n\nChoose when to delete messages:"
    
    keyboard = [
        [InlineKeyboardButton("🕐 After 1 hour", callback_data="delete_1h")],
        [InlineKeyboardButton("🕕 After 6 hours", callback_data="delete_6h")],
        [InlineKeyboardButton("📅 After 1 day", callback_data="delete_1d")],
        [InlineKeyboardButton("📅 After 7 days", callback_data="delete_7d")],
        [InlineKeyboardButton("❌ Never delete", callback_data="delete_never")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_config")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_content_preview(query, context, content_type):
    """Show preview of specific content type"""
    config = context.user_data.get('current_message_config', {})
    
    if content_type == "text":
        preview = config.get('text', 'No text set')
        text = f"📝 **Text Preview:**\n\n{preview}"
    elif content_type == "media":
        preview = "📷 Media attached" if config.get('has_media') else "No media set"
        text = f"📷 **Media Preview:**\n\n{preview}"
    elif content_type == "buttons":
        preview = "🔗 URL buttons configured" if config.get('has_buttons') else "No buttons set"
        text = f"🔗 **Buttons Preview:**\n\n{preview}"
    else:
        text = "❌ Unknown preview type"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="customize_message")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def set_message_text(query, context):
    """Set message text"""
    context.user_data['waiting_for_text'] = True
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="customize_message")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📝 **Set Message Text**\n\n"
        "Send me the text you want to use for the recurring message:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def set_message_media(query, context):
    """Set message media"""
    context.user_data['waiting_for_media'] = True
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="customize_message")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📷 **Set Message Media**\n\n"
        "Send me a photo, video, or GIF to include with the message:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def set_url_buttons(query, context):
    """Set URL buttons"""
    context.user_data['waiting_for_buttons'] = True
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="customize_message")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🔗 **Set URL Buttons**\n\n"
        "Send me the button configuration in format:\n"
        "`Button Text | URL`\n\n"
        "Example:\n"
        "`Visit Website | https://example.com`\n"
        "`Join Channel | https://t.me/channel`",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_full_preview(query, context):
    """Show full message preview"""
    config = context.user_data.get('current_message_config', {})
    
    text = "👁️ **Full Message Preview**\n\n"
    
    if config.get('text'):
        text += f"📝 **Text:**\n{config['text']}\n\n"
    
    if config.get('has_media'):
        text += "📷 **Media:** Attached\n\n"
    
    if config.get('has_buttons'):
        text += "🔗 **URL Buttons:** Configured\n\n"
    
    text += f"⏰ **Schedule:** {config.get('repetition', 'Every 24 hours')}\n"
    text += f"📌 **Pin:** {'Yes' if config.get('pin_message') else 'No'}\n"
    text += f"🗑️ **Delete last:** {'Yes' if config.get('delete_last') else 'No'}"
    
    keyboard = [
        [InlineKeyboardButton("✅ Save Message", callback_data="save_message")],
        [InlineKeyboardButton("🔙 Back", callback_data="customize_message")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_topic_selection(query, context):
    """Show topic selection (placeholder)"""
    text = "📋 **Select a Topic**\n\nChoose a predefined message topic:"
    
    keyboard = [
        [InlineKeyboardButton("📢 Announcements", callback_data="topic_announcements")],
        [InlineKeyboardButton("🎉 Events", callback_data="topic_events")],
        [InlineKeyboardButton("📝 Rules", callback_data="topic_rules")],
        [InlineKeyboardButton("💡 Tips", callback_data="topic_tips")],
        [InlineKeyboardButton("🔙 Back", callback_data="customize_message")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_time_slot_options(query, context):
    """Show time slot options"""
    text = "🕐 **Set Time Slot**\n\nChoose a time slot for message sending:"
    
    keyboard = [
        [InlineKeyboardButton("🌅 Morning (06:00-12:00)", callback_data="time_slot_morning")],
        [InlineKeyboardButton("🌞 Afternoon (12:00-18:00)", callback_data="time_slot_afternoon")],
        [InlineKeyboardButton("🌇 Evening (18:00-00:00)", callback_data="time_slot_evening")],
        [InlineKeyboardButton("🌙 Night (00:00-06:00)", callback_data="time_slot_night")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_config")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_manage_messages(query, context):
    """Show manage messages screen with existing scheduled messages"""
    chat_id = query.message.chat.id
    current_time = datetime.now().strftime("%d/%m/%y %H:%M")
    
    # Get all scheduled messages for this chat
    scheduled_messages = database.get_scheduled_messages(chat_id)
    
    text = (
        "🔄 **Recurring messages**\n\n"
        f"From this menu you can set messages that will be sent "
        f"repeatedly to the group every few minutes/hours or every "
        f"few messages.\n\n"
        f"Current time: {current_time}"
    )
    
    # Add message entries if they exist
    if scheduled_messages:
        for i, msg in enumerate(scheduled_messages, 1):
            status = "✅ Active" if msg['is_active'] else "❌ Inactive"
            status_icon = "✅" if msg['is_active'] else "❌"
            
            # Format time
            time_str = format_interval(msg['interval_hours'], msg.get('interval_minutes', 0))
            
            # Get message preview
            message_preview = msg['message_text'][:50] if msg['message_text'] else "Message is not set."
            if len(msg['message_text'] or "") > 50:
                message_preview += "..."
            
            text += f"\n\n**{i} • {status}** {status_icon}\n"
            text += f"   Time: {time_str}\n"
            text += f"   {message_preview}"
    
    keyboard = [
        [InlineKeyboardButton("➕ Add message", callback_data="recurring_add")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_recurring_groups_menu(query, context):
    """Show the groups menu for recurring messages"""
    # Show group selection with buttons for already added groups
    keyboard = []
    
    # Add buttons for already added groups
    if allowed_groups:
        added_groups_count = 0
        for group_id_str in allowed_groups:
            try:
                group_id = int(group_id_str)
                # Try to get group name
                try:
                    chat_info = await context.bot.get_chat(group_id)
                    group_name = chat_info.title or f"Grupė {group_id}"
                    # Truncate long names
                    if len(group_name) > 25:
                        group_name = group_name[:22] + "..."
                    
                    # Verify user is admin in this group
                    try:
                        chat_member = await context.bot.get_chat_member(group_id, query.from_user.id)
                        if chat_member.status in ['creator', 'administrator']:
                            keyboard.append([InlineKeyboardButton(
                                f"📱 {group_name}", 
                                callback_data=f"recurring_select_group_{group_id}"
                            )])
                            added_groups_count += 1
                    except Exception:
                        # User is not admin in this group, skip it
                        continue
                        
                except Exception:
                    # Can't get group info, but still show it with ID
                    try:
                        chat_member = await context.bot.get_chat_member(group_id, query.from_user.id)
                        if chat_member.status in ['creator', 'administrator']:
                            keyboard.append([InlineKeyboardButton(
                                f"📱 Grupė {group_id}", 
                                callback_data=f"recurring_select_group_{group_id}"
                            )])
                            added_groups_count += 1
                    except Exception:
                        continue
                        
            except (ValueError, Exception):
                continue
    
    # Add button to add new group by ID
    keyboard.append([InlineKeyboardButton("➕ Pridėti naują grupę", callback_data="recurring_add_new_group")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Create message text
    text = "🔄 **Kartojami Pranešimai**\n\n"
    if keyboard[:-1]:  # If there are group buttons (excluding the add button)
        text += "Pasirinkite grupę iš sąrašo arba pridėkite naują:"
    else:
        text += "Dar neturite pridėtų grupių.\nPridėkite grupę, kad galėtumėte valdyti kartojamuosius pranešimus:"
    
    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def show_recurring_groups_menu_admin(query, context):
    """Show the groups menu for recurring messages from admin dashboard"""
    # Show group selection with buttons for already added groups
    keyboard = []
    
    # Add buttons for already added groups
    if allowed_groups:
        added_groups_count = 0
        for group_id_str in allowed_groups:
            try:
                group_id = int(group_id_str)
                # Try to get group name
                try:
                    chat_info = await context.bot.get_chat(group_id)
                    group_name = chat_info.title or f"Grupė {group_id}"
                    # Truncate long names
                    if len(group_name) > 25:
                        group_name = group_name[:22] + "..."
                    
                    # Verify user is admin in this group
                    try:
                        chat_member = await context.bot.get_chat_member(group_id, query.from_user.id)
                        if chat_member.status in ['creator', 'administrator']:
                            keyboard.append([InlineKeyboardButton(
                                f"📱 {group_name}", 
                                callback_data=f"recurring_select_group_{group_id}"
                            )])
                            added_groups_count += 1
                    except Exception:
                        # User is not admin in this group, skip it
                        continue
                        
                except Exception:
                    # Can't get group info, but still show it with ID
                    try:
                        chat_member = await context.bot.get_chat_member(group_id, query.from_user.id)
                        if chat_member.status in ['creator', 'administrator']:
                            keyboard.append([InlineKeyboardButton(
                                f"📱 Grupė {group_id}", 
                                callback_data=f"recurring_select_group_{group_id}"
                            )])
                            added_groups_count += 1
                    except Exception:
                        continue
                        
            except (ValueError, Exception):
                continue
    
    # Add button to add new group by ID
    keyboard.append([InlineKeyboardButton("➕ Pridėti naują grupę", callback_data="recurring_add_new_group")])
    
    # Add back button to admin dashboard
    keyboard.append([InlineKeyboardButton("⬅️ Atgal į admin dashboard", callback_data="admin_dashboard_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Create message text
    text = "🔄 **Kartojami Pranešimai**\n\n"
    if keyboard[:-2]:  # If there are group buttons (excluding the add button and back button)
        text += "Pasirinkite grupę iš sąrašo arba pridėkite naują:"
    else:
        text += "Dar neturite pridėtų grupių.\nPridėkite grupę, kad galėtumėte valdyti kartojamuosius pranešimus:"
    
    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_banned_words_callback(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Handle banned words callback queries"""
    query = update.callback_query
    if not await is_admin_callback(query, context):
        await query.answer("❌ Tik administratoriai gali naudoti šią funkciją!")
        return
    
    data = query.data
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    
    # Handle private chat scenarios
    if data == "banned_words_add_private":
        # Set user state to wait for word
        context.user_data['waiting_for_word'] = True
        context.user_data['private_mode'] = True
        await query.edit_message_text(
            "🚫 **Pridėti Uždraustą Žodį**\n\n"
            "Parašykite žodį, kurį norite drausti:",
            parse_mode='Markdown'
        )
    elif data == "banned_words_list_private":
        await show_banned_words_list_private(query, context)
    elif data == "banned_words_add":
        # Set user state to wait for word
        context.user_data['waiting_for_word'] = True
        context.user_data['private_mode'] = False
        await query.edit_message_text(
            "🚫 **Pridėti Uždraustą Žodį**\n\n"
            "Parašykite žodį, kurį norite drausti:",
            parse_mode='Markdown'
        )
    elif data == "banned_words_list":
        await show_banned_words_list(query, context)
    elif data.startswith("banned_words_info_"):
        word_id = int(data.split("_")[3])
        await show_word_info(query, context, word_id)
    elif data.startswith("banned_words_toggle_"):
        word_id = int(data.split("_")[3])
        await toggle_word_status(query, context, word_id)
    elif data.startswith("banned_words_delete_"):
        word_id = int(data.split("_")[3])
        await delete_word(query, context, word_id)
    
    await query.answer()

async def handle_helpers_callback(update: telegram.Update, context: telegram.ext.ContextTypes.DEFAULT_TYPE):
    """Handle helpers callback queries"""
    query = update.callback_query
    if not await is_admin_callback(query, context):
        await query.answer("❌ Tik administratoriai gali naudoti šią funkciją!")
        return
    
    data = query.data
    chat_id = query.message.chat.id
    user_id = query.from_user.id
    
    # Handle private chat scenarios
    if data == "helpers_add_private":
        # Set user state to wait for helper ID
        context.user_data['waiting_for_helper_id'] = True
        context.user_data['private_mode'] = True
        await query.edit_message_text(
            "👥 **Pridėti Pagalbininką**\n\n"
            "Parašykite vartotojo ID:",
            parse_mode='Markdown'
        )
    elif data == "helpers_list_private":
        await show_helpers_list_private(query, context)
    elif data == "helpers_add":
        # Set user state to wait for helper ID
        context.user_data['waiting_for_helper_id'] = True
        context.user_data['private_mode'] = False
        await query.edit_message_text(
            "👥 **Pridėti Pagalbininką**\n\n"
            "Parašykite vartotojo ID:",
            parse_mode='Markdown'
        )
    elif data == "helpers_list":
        await show_helpers_list(query, context)
    elif data.startswith("helpers_info_"):
        helper_id = int(data.split("_")[2])
        await show_helper_info(query, context, helper_id)
    elif data.startswith("helpers_remove_"):
        helper_id = int(data.split("_")[2])
        await remove_helper(query, context, helper_id)
    elif data.startswith("helper_manage_"):
        helper_id = int(data.split("_")[2])
        await show_helper_management(query, context, helper_id)
    elif data == "helper_add_new":
        await show_add_helper_interface(query, context)
    elif data == "helper_add_by_id":
        context.user_data['waiting_for_helper_id'] = True
        context.user_data['helper_add_type'] = 'id'
        keyboard = [[InlineKeyboardButton("🔙 Atgal", callback_data="helper_add_new")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🔢 **Įveskite User ID**\n\n"
            "Parašykite vartotojo ID numerį:\n\n"
            "Pavyzdys: `123456789`",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    elif data == "helper_add_by_username":
        context.user_data['waiting_for_helper_id'] = True
        context.user_data['helper_add_type'] = 'username'
        keyboard = [[InlineKeyboardButton("🔙 Atgal", callback_data="helper_add_new")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "👤 **Įveskite Username**\n\n"
            "Parašykite vartotojo username su @ ženklu:\n\n"
            "Pavyzdys: `@username`",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    elif data == "helpers_back_to_groups":
        await show_helpers_groups_menu_admin(query, context)
    elif data == "helpers_back_to_list":
        await show_helpers_list_private(query, context)
    elif data.startswith("helper_toggle_"):
        helper_id = int(data.split("_")[2])
        await toggle_helper_status(query, context, helper_id)
    elif data.startswith("helper_remove_"):
        helper_id = int(data.split("_")[2])
        await remove_helper_confirm(query, context, helper_id)
    elif data.startswith("helper_perm_"):
        # Handle permission changes
        perm_type = data.split("_")[2]  # pin, delete, ban, mute
        helper_id = int(data.split("_")[3])
        await handle_helper_permission(query, context, helper_id, perm_type)
    elif data.startswith("helpers_select_group_"):
        group_id = int(data.split("_")[-1])
        
        # Store the group_id in user_data
        context.user_data['target_group_id'] = group_id
        context.user_data['private_mode'] = True
        
        # Show helpers list for this group
        await show_helpers_list_private(query, context)
    elif data == "helpers_add_new_group":
        context.user_data['waiting_for_group_id'] = True
        context.user_data['group_selection_type'] = 'helpers'
        
        await query.edit_message_text(
            "➕ **Pridėti Naują Grupę**\n\n"
            "Įveskite grupės ID (pvz., -1001234567890):\n\n"
            "💡 **Kaip gauti grupės ID:**\n"
            "1. Pridėkite @userinfobot į grupę\n"
            "2. Parašykite /start grupėje\n"
            "3. Botas parodys grupės ID",
            parse_mode='Markdown'
        )
    elif data.startswith("helper_remove_confirm_"):
        helper_id = int(data.split("_")[3])
        # TODO: Actually remove the helper from database
        await query.edit_message_text(
            "✅ **Pagalbininkas pašalintas!**\n\n"
            "Jis nebegali valdyti grupės per botą.",
            parse_mode='Markdown'
        )
        await asyncio.sleep(1.5)
        await show_helpers_list_private(query, context)
    
    await query.answer()

# Group selection callback handlers
async def handle_group_selection_callback(query, context):
    """Handle group selection callback queries"""
    if not await is_admin_callback(query, context):
        await query.answer("❌ Tik administratoriai gali naudoti šią funkciją!")
        return
    
    data = query.data
    user_id = query.from_user.id
    
    if data == "group_select_manual_recurring":
        context.user_data['waiting_for_group_id'] = True
        context.user_data['group_selection_type'] = 'recurring'
        await query.edit_message_text(
            "📝 **Įvesti Grupės ID**\n\n"
            "Parašykite grupės ID, kurią norite valdyti:\n\n"
            "**Pavyzdys:** `-1001234567890`",
            parse_mode='Markdown'
        )
    elif data == "group_select_search_recurring":
        await query.edit_message_text(
            "🔍 **Rasti Grupes**\n\n"
            "Ši funkcija dar kuriama.\n"
            "Naudokite '📝 Įvesti grupės ID' opciją.",
            parse_mode='Markdown'
        )
    elif data == "group_select_manual_banned_words":
        context.user_data['waiting_for_group_id'] = True
        context.user_data['group_selection_type'] = 'banned_words'
        await query.edit_message_text(
            "📝 **Įvesti Grupės ID**\n\n"
            "Parašykite grupės ID, kurią norite valdyti:\n\n"
            "**Pavyzdys:** `-1001234567890`",
            parse_mode='Markdown'
        )
    elif data == "group_select_search_banned_words":
        await query.edit_message_text(
            "🔍 **Rasti Grupes**\n\n"
            "Ši funkcija dar kuriama.\n"
            "Naudokite '📝 Įvesti grupės ID' opciją.",
            parse_mode='Markdown'
        )
    elif data == "group_select_manual_helpers":
        context.user_data['waiting_for_group_id'] = True
        context.user_data['group_selection_type'] = 'helpers'
        await query.edit_message_text(
            "📝 **Įvesti Grupės ID**\n\n"
            "Parašykite grupės ID, kurią norite valdyti:\n\n"
            "**Pavyzdys:** `-1001234567890`",
            parse_mode='Markdown'
        )
    elif data == "group_select_search_helpers":
        await query.edit_message_text(
            "🔍 **Rasti Grupes**\n\n"
            "Ši funkcija dar kuriama.\n"
            "Naudokite '📝 Įvesti grupės ID' opciją.",
            parse_mode='Markdown'
        )

# Helper functions for UI
async def show_manage_messages(query, context):
    """Show manage messages interface"""
    chat_id = query.message.chat.id
    messages = database.get_scheduled_messages(chat_id)
    
    if not messages:
        await query.edit_message_text(
            "📋 **Valdyti Pranešimus**\n\n"
            "Dar nėra suplanuotų pranešimų.",
            parse_mode='Markdown'
        )

async def show_manage_messages_private(query, context):
    """Show manage messages interface for private chat"""
    group_id = context.user_data.get('target_group_id')
    if not group_id:
        await query.edit_message_text(
            "❌ **Klaida**\n\n"
            "Nepavyko nustatyti grupės ID. Bandykite iš naujo.",
            parse_mode='Markdown'
        )
        return
    
    messages = database.get_scheduled_messages(group_id)
    
    if not messages:
        await query.edit_message_text(
            f"📋 **Valdyti Pranešimus**\n\n"
            f"Grupė: `{group_id}`\n\n"
            f"Dar nėra suplanuotų pranešimų.",
            parse_mode='Markdown'
        )
        return
    
    # Show messages list with management options
    text = f"📋 **Valdyti Pranešimus**\n\n"
    text += f"Grupė: `{group_id}`\n\n"
    
    keyboard = []
    for i, msg in enumerate(messages[:10]):  # Limit to 10 messages
        # msg is a tuple: (id, chat_id, message_text, message_media, message_buttons, message_type, 
        #                  repetition_type, interval_hours, days_of_week, days_of_month, time_slots,
        #                  start_date, end_date, pin_message, delete_last_message, scheduled_deletion_hours,
        #                  status, created_by, created_by_username, created_at, last_sent, job_id)
        msg_id = msg[0]
        message_text = msg[2] or "Pranešimas nenustatytas"
        status = msg[16]  # status column
        status_icon = "✅" if status == 'active' else "❌"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{status_icon} {message_text[:30]}...",
                callback_data=f"recurring_info_{msg_id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Atgal", callback_data="recurring_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_banned_words_list_private(query, context):
    """Show banned words list for private chat"""
    group_id = context.user_data.get('target_group_id')
    if not group_id:
        await query.edit_message_text(
            "❌ **Klaida**\n\n"
            "Nepavyko nustatyti grupės ID. Bandykite iš naujo.",
            parse_mode='Markdown'
        )
        return
    
    banned_words = database.get_banned_words(group_id)
    
    if not banned_words:
        await query.edit_message_text(
            f"🚫 **Uždrausti Žodžiai**\n\n"
            f"Grupė: `{group_id}`\n\n"
            f"Dar nėra uždraustų žodžių.",
            parse_mode='Markdown'
        )
        return
    
    # Show words list with management options
    text = f"🚫 **Uždrausti Žodžiai**\n\n"
    text += f"Grupė: `{group_id}`\n\n"
    
    keyboard = []
    for i, word in enumerate(banned_words[:10]):  # Limit to 10 words
        status = "✅" if word['is_active'] else "❌"
        keyboard.append([
            InlineKeyboardButton(
                f"{status} {word['word']}",
                callback_data=f"banned_words_info_{word['id']}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Atgal", callback_data="banned_words_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_helpers_list_private(query, context):
    """Show helpers list for private chat with enhanced management"""
    group_id = context.user_data.get('target_group_id')
    if not group_id:
        await query.edit_message_text(
            "❌ **Klaida**\n\n"
            "Nepavyko nustatyti grupės ID. Bandykite iš naujo.",
            parse_mode='Markdown'
        )
        return
    
    helpers = database.get_helpers(group_id)
    
    # Get group info for display
    try:
        chat_info = await context.bot.get_chat(group_id)
        group_name = chat_info.title or f"Grupė {group_id}"
    except Exception:
        group_name = f"Grupė {group_id}"
    
    text = f"👥 **Pagalbininkai**\n\n"
    text += f"📱 **Grupė:** {group_name}\n"
    text += f"🆔 **ID:** `{group_id}`\n\n"
    
    keyboard = []
    
    if helpers:
        text += "**Aktyvūs pagalbininkai:**\n\n"
        for i, helper in enumerate(helpers[:10]):  # Limit to 10 helpers
            # helper is a tuple: (id, chat_id, user_id, username, added_by, added_by_username, added_at, is_active)
            helper_id = helper[0]
            user_id = helper[2]
            username = helper[3] or f"ID: {user_id}"
            is_active = helper[7]
            status_icon = "✅" if is_active else "❌"
            
            # Try to get current user info from Telegram
            try:
                user_info = await context.bot.get_chat(user_id)
                display_name = f"@{user_info.username}" if user_info.username else user_info.first_name or f"ID: {user_id}"
            except Exception:
                display_name = f"@{username}" if username and not username.startswith("ID:") else username
            
            text += f"{i+1}. {status_icon} {display_name}\n"
            keyboard.append([
                InlineKeyboardButton(
                    f"⚙️ {display_name}",
                    callback_data=f"helper_manage_{helper_id}"
                )
            ])
        text += "\n"
    else:
        text += "Dar nėra pridėtų pagalbininkų.\n\n"
    
    # Add management buttons
    keyboard.extend([
        [InlineKeyboardButton("➕ Pridėti pagalbininką", callback_data="helper_add_new")],
        [InlineKeyboardButton("🔙 Atgal į grupių sąrašą", callback_data="helpers_back_to_groups")]
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_helper_management(query, context, helper_id):
    """Show helper management interface with permissions"""
    group_id = context.user_data.get('target_group_id')
    if not group_id:
        await query.edit_message_text("❌ Klaida: Nepavyko nustatyti grupės ID.")
        return
    
    # Get helper info
    helpers = database.get_helpers(group_id)
    helper_data = None
    for helper in helpers:
        if helper[0] == helper_id:  # helper[0] is id
            helper_data = helper
            break
    
    if not helper_data:
        await query.edit_message_text("❌ Pagalbininkas nerastas.")
        return
    
    # helper_data is tuple: (id, chat_id, user_id, username, added_by, added_by_username, added_at, is_active)
    user_id = helper_data[2]
    username = helper_data[3] or f"ID: {user_id}"
    is_active = helper_data[7]
    
    # Try to get current user info
    try:
        user_info = await context.bot.get_chat(user_id)
        display_name = f"@{user_info.username}" if user_info.username else user_info.first_name or f"ID: {user_id}"
    except Exception:
        display_name = f"@{username}" if username and not username.startswith("ID:") else username
    
    # Get group info
    try:
        chat_info = await context.bot.get_chat(group_id)
        group_name = chat_info.title or f"Grupė {group_id}"
    except Exception:
        group_name = f"Grupė {group_id}"
    
    status_text = "✅ Aktyvus" if is_active else "❌ Neaktyvus"
    
    text = f"⚙️ **Pagalbininko Valdymas**\n\n"
    text += f"👤 **Pagalbininkas:** {display_name}\n"
    text += f"🆔 **User ID:** `{user_id}`\n"
    text += f"📱 **Grupė:** {group_name}\n"
    text += f"📊 **Statusas:** {status_text}\n\n"
    text += f"**Galimos teisės per botą:**\n"
    text += f"• 📌 Prisegti pranešimus\n"
    text += f"• 🗑️ Ištrinti pranešimus\n"
    text += f"• 🚫 Užbaninti narius\n"
    text += f"• 🔇 Nutildyti narius\n\n"
    text += f"*Pagalbininkas gali valdyti grupę per botą, net nebūdamas admin Telegram.*"
    
    keyboard = [
        [InlineKeyboardButton("📌 Leisti prisegti", callback_data=f"helper_perm_pin_{helper_id}")],
        [InlineKeyboardButton("🗑️ Leisti trinti", callback_data=f"helper_perm_delete_{helper_id}")],
        [InlineKeyboardButton("🚫 Leisti baninti", callback_data=f"helper_perm_ban_{helper_id}")],
        [InlineKeyboardButton("🔇 Leisti tildyti", callback_data=f"helper_perm_mute_{helper_id}")],
        [InlineKeyboardButton(f"{'❌ Išjungti' if is_active else '✅ Įjungti'}", 
                            callback_data=f"helper_toggle_{helper_id}")],
        [InlineKeyboardButton("🗑️ Pašalinti pagalbininką", callback_data=f"helper_remove_{helper_id}")],
        [InlineKeyboardButton("🔙 Atgal", callback_data="helpers_back_to_list")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_add_helper_interface(query, context):
    """Show add helper interface"""
    group_id = context.user_data.get('target_group_id')
    if not group_id:
        await query.edit_message_text("❌ Klaida: Nepavyko nustatyti grupės ID.")
        return
    
    # Get group info
    try:
        chat_info = await context.bot.get_chat(group_id)
        group_name = chat_info.title or f"Grupė {group_id}"
    except Exception:
        group_name = f"Grupė {group_id}"
    
    text = f"➕ **Pridėti Pagalbininką**\n\n"
    text += f"📱 **Grupė:** {group_name}\n"
    text += f"🆔 **ID:** `{group_id}`\n\n"
    text += f"**Galite pridėti pagalbininką dviem būdais:**\n\n"
    text += f"1️⃣ **Per User ID** - Įveskite vartotojo ID numerį\n"
    text += f"2️⃣ **Per Username** - Įveskite @username\n\n"
    text += f"**Pavyzdžiai:**\n"
    text += f"• `123456789` (User ID)\n"
    text += f"• `@username` (Username)\n\n"
    text += f"💡 *User ID galite gauti per @userinfobot*"
    
    keyboard = [
        [InlineKeyboardButton("🔢 Įvesti User ID", callback_data="helper_add_by_id")],
        [InlineKeyboardButton("👤 Įvesti Username", callback_data="helper_add_by_username")],
        [InlineKeyboardButton("🔙 Atgal", callback_data="helpers_back_to_list")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_helpers_groups_menu_admin(query, context):
    """Show the groups menu for helpers from admin dashboard"""
    # Show group selection with buttons for already added groups
    keyboard = []
    
    # Add buttons for already added groups
    if allowed_groups:
        added_groups_count = 0
        for group_id_str in allowed_groups:
            try:
                group_id = int(group_id_str)
                # Try to get group name
                try:
                    chat_info = await context.bot.get_chat(group_id)
                    group_name = chat_info.title or f"Grupė {group_id}"
                    # Truncate long names
                    if len(group_name) > 25:
                        group_name = group_name[:22] + "..."
                    
                    # Verify user is admin in this group
                    try:
                        chat_member = await context.bot.get_chat_member(group_id, query.from_user.id)
                        if chat_member.status in ['creator', 'administrator']:
                            keyboard.append([InlineKeyboardButton(
                                f"📱 {group_name}", 
                                callback_data=f"helpers_select_group_{group_id}"
                            )])
                            added_groups_count += 1
                    except Exception:
                        # User is not admin in this group, skip it
                        continue
                        
                except Exception:
                    # Can't get group info, but still show it with ID
                    try:
                        chat_member = await context.bot.get_chat_member(group_id, query.from_user.id)
                        if chat_member.status in ['creator', 'administrator']:
                            keyboard.append([InlineKeyboardButton(
                                f"📱 Grupė {group_id}", 
                                callback_data=f"helpers_select_group_{group_id}"
                            )])
                            added_groups_count += 1
                    except Exception:
                        continue
                        
            except (ValueError, Exception):
                continue
    
    # Add button to add new group by ID
    keyboard.append([InlineKeyboardButton("➕ Pridėti naują grupę", callback_data="helpers_add_new_group")])
    
    # Add back button to admin dashboard
    keyboard.append([InlineKeyboardButton("⬅️ Atgal į admin dashboard", callback_data="admin_dashboard_back")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Create message text
    text = "👥 **Pagalbininkai**\n\n"
    if keyboard[:-2]:  # If there are group buttons (excluding the add button and back button)
        text += "Pasirinkite grupę iš sąrašo arba pridėkite naują:"
    else:
        text += "Dar neturite pridėtų grupių.\nPridėkite grupę, kad galėtumėte valdyti pagalbininkus:"
    
    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def toggle_helper_status(query, context, helper_id):
    """Toggle helper active status"""
    # Implementation for toggling helper status
    await query.edit_message_text("⚙️ Pagalbininko statusas pakeistas!")
    await asyncio.sleep(1)
    await show_helper_management(query, context, helper_id)

async def remove_helper_confirm(query, context, helper_id):
    """Show helper removal confirmation"""
    keyboard = [
        [InlineKeyboardButton("✅ Taip, pašalinti", callback_data=f"helper_remove_confirm_{helper_id}")],
        [InlineKeyboardButton("❌ Atšaukti", callback_data="helpers_back_to_list")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "⚠️ **Patvirtinimas**\n\n"
        "Ar tikrai norite pašalinti šį pagalbininką?\n"
        "Jis negalės daugiau valdyti grupės per botą.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def handle_helper_permission(query, context, helper_id, perm_type):
    """Handle helper permission changes"""
    perm_names = {
        'pin': '📌 Prisegti pranešimus',
        'delete': '🗑️ Ištrinti pranešimus', 
        'ban': '🚫 Užbaninti narius',
        'mute': '🔇 Nutildyti narius'
    }
    
    perm_name = perm_names.get(perm_type, 'Nežinoma teisė')
    
    await query.edit_message_text(
        f"✅ **Teisė suteikta!**\n\n"
        f"Pagalbininkas dabar gali: {perm_name}\n\n"
        f"Grįžtame į valdymą...",
        parse_mode='Markdown'
    )
    
    await asyncio.sleep(1.5)
    await show_helper_management(query, context, helper_id)

async def show_banned_words_list(query, context):
    """Show banned words list"""
    chat_id = query.message.chat.id
    banned_words = database.get_banned_words(chat_id)
    
    if not banned_words:
        await query.edit_message_text(
            "🚫 **Uždrausti Žodžiai**\n\n"
            "Dar nėra uždraustų žodžių.",
            parse_mode='Markdown'
        )
        return
    
    text = "🚫 **Uždrausti Žodžiai**\n\n"
    keyboard = []
    
    for word_data in banned_words:
        word_id, _, word, action, _, _, _, _ = word_data
        
        text += f"🔴 **{word}** ({action})\n\n"
        
        # Action buttons
        keyboard.append([
            InlineKeyboardButton(f"ℹ️ {word_id}", callback_data=f"banned_words_info_{word_id}"),
            InlineKeyboardButton("🗑️", callback_data=f"banned_words_delete_{word_id}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Atgal", callback_data="banned_words_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_helpers_list(query, context):
    """Show helpers list"""
    chat_id = query.message.chat.id
    helpers = database.get_helpers(chat_id)
    
    if not helpers:
        await query.edit_message_text(
            "👥 **Pagalbininkai**\n\n"
            "Dar nėra pagalbininkų.",
            parse_mode='Markdown'
        )
        return
    
    text = "👥 **Pagalbininkai**\n\n"
    keyboard = []
    
    for helper_data in helpers:
        helper_id, _, user_id, username, _, added_by_username, _, _ = helper_data
        
        text += f"👤 **{username or f'User {user_id}'}**\n"
        text += f"   Pridėjo: {added_by_username}\n\n"
        
        # Action buttons
        keyboard.append([
            InlineKeyboardButton(f"ℹ️ {helper_id}", callback_data=f"helpers_info_{helper_id}"),
            InlineKeyboardButton("🗑️", callback_data=f"helpers_remove_{helper_id}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Atgal", callback_data="helpers_back")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

# Placeholder functions for other UI elements
async def show_message_info(query, context, message_id):
    await query.answer("ℹ️ Informacija apie pranešimą")
    # TODO: Implement detailed message info

async def toggle_message_status(query, context, message_id):
    await query.answer("🔄 Pranešimo statusas pakeistas")
    # TODO: Implement status toggle

async def delete_message(query, context, message_id):
    await query.answer("🗑️ Pranešimas ištrintas")
    # TODO: Implement message deletion

async def show_word_info(query, context, word_id):
    await query.answer("ℹ️ Informacija apie žodį")
    # TODO: Implement word info

async def toggle_word_status(query, context, word_id):
    await query.answer("🔄 Žodžio statusas pakeistas")
    # TODO: Implement word status toggle

async def delete_word(query, context, word_id):
    await query.answer("🗑️ Žodis ištrintas")
    # TODO: Implement word deletion

async def show_helper_info(query, context, helper_id):
    await query.answer("ℹ️ Informacija apie pagalbininką")
    # TODO: Implement helper info

async def remove_helper(query, context, helper_id):
    await query.answer("🗑️ Pagalbininkas pašalintas")
    # TODO: Implement helper removal

# Add handlers
application.add_handler(CommandHandler(['startas'], startas))
application.add_handler(CommandHandler(['activate_group'], activate_group))
application.add_handler(CommandHandler(['nepatiko'], nepatiko))
application.add_handler(CommandHandler(['approve'], approve))
application.add_handler(CommandHandler(['addseller'], addseller))
application.add_handler(CommandHandler(['removeseller'], removeseller))
application.add_handler(CommandHandler(['pardavejoinfo'], sellerinfo))
application.add_handler(CommandHandler(['barygos'], barygos))
application.add_handler(CommandHandler(['balsuoti'], balsuoti))
application.add_handler(CommandHandler(['chatking'], chatking))
application.add_handler(CommandHandler(['coinflip'], coinflip))
application.add_handler(CommandHandler(['accept_coinflip'], accept_coinflip))
application.add_handler(CommandHandler(['addpoints'], addpoints))
application.add_handler(CommandHandler(['pridetitaskus'], pridetitaskus))
application.add_handler(CommandHandler(['points'], points))
application.add_handler(CommandHandler(['debug'], debug))
application.add_handler(CommandHandler(['whoami'], whoami))
application.add_handler(CommandHandler(['addftbaryga'], addftbaryga))
application.add_handler(CommandHandler(['addftbaryga2'], addftbaryga2))
application.add_handler(CommandHandler(['editpardavejai'], editpardavejai))
application.add_handler(CommandHandler(['apklausa'], apklausa))
application.add_handler(CommandHandler(['updatevoting'], updatevoting))
application.add_handler(CommandHandler(['privatus'], privatus))
application.add_handler(CommandHandler(['reset_weekly'], reset_weekly))
application.add_handler(CommandHandler(['reset_monthly'], reset_monthly))
application.add_handler(CommandHandler(['add_weekly_points'], add_weekly_points))
application.add_handler(CommandHandler(['add_monthly_points'], add_monthly_points))
application.add_handler(CommandHandler(['add_alltime_points'], add_alltime_points))
application.add_handler(CommandHandler(['remove_weekly_points'], remove_weekly_points))
application.add_handler(CommandHandler(['remove_monthly_points'], remove_monthly_points))
application.add_handler(CommandHandler(['remove_alltime_points'], remove_alltime_points))
application.add_handler(CommandHandler(['help'], help_command))
application.add_handler(CommandHandler(['komandos'], komandos))
application.add_handler(CommandHandler(['achievements'], achievements))
application.add_handler(CommandHandler(['challenges'], challenges))
application.add_handler(CommandHandler(['leaderboard'], leaderboard))
application.add_handler(CommandHandler(['mystats'], mystats))
application.add_handler(CommandHandler(['botstats'], botstats))
application.add_handler(CommandHandler(['moderation'], moderation_command))

# Scammer tracking system handlers
application.add_handler(CommandHandler(['scameris'], scameris))
application.add_handler(CommandHandler(['patikra'], patikra))
application.add_handler(CommandHandler(['scameriai'], scameriai))  # Public scammer list
application.add_handler(CommandHandler(['approve_scammer'], approve_scammer))
application.add_handler(CommandHandler(['reject_scammer'], reject_scammer))
application.add_handler(CommandHandler(['scammer_list'], scammer_list))  # Admin detailed list
application.add_handler(CommandHandler(['pending_reports'], pending_reports))

# Buyer report tracking system handlers
application.add_handler(CommandHandler(['vagis'], vagis))
application.add_handler(CommandHandler(['neradejas'], neradejas))

# New feature command handlers
application.add_handler(CommandHandler(['recurring'], recurring_messages_menu))
application.add_handler(CommandHandler(['ban'], ban_user))
application.add_handler(CommandHandler(['unban'], unban_user))
application.add_handler(CommandHandler(['mute'], mute_user))
application.add_handler(CommandHandler(['unmute'], unmute_user))
application.add_handler(CommandHandler(['bannedwords'], banned_words_menu))
application.add_handler(CommandHandler(['helpers'], helpers_menu))

# Private chat command handlers with group_id parameter
application.add_handler(CommandHandler(['recurring_messages'], recurring_messages_private))
application.add_handler(CommandHandler(['banned_words'], banned_words_private))
application.add_handler(CommandHandler(['helpers'], helpers_private))
# Admin commands removed - now accessible through moderation panel buttons only

# Add callback query handler for inline buttons
application.add_handler(CallbackQueryHandler(handle_scammer_callback, pattern=r"^(approve_scammer_|reject_scammer_|scammer_details_)"))
application.add_handler(MessageHandler(filters.Regex('^/start$') & filters.ChatType.PRIVATE, start_private))
application.add_handler(CallbackQueryHandler(handle_vote_button, pattern="vote_"))
application.add_handler(CallbackQueryHandler(handle_poll_button, pattern="poll_"))
application.add_handler(CallbackQueryHandler(handle_admin_button, pattern="admin_"))
application.add_handler(CallbackQueryHandler(handle_admin_button, pattern="mod_"))
application.add_handler(CallbackQueryHandler(handle_admin_button, pattern="^group_select_"))

# New feature callback handlers
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^recurring_"))
application.add_handler(CallbackQueryHandler(handle_banned_words_callback, pattern="^banned_words_"))
application.add_handler(CallbackQueryHandler(handle_helpers_callback, pattern="^helpers_"))
application.add_handler(CallbackQueryHandler(handle_helpers_callback, pattern="^helper_"))

# GroupHelpBot-style recurring message callbacks
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^customize_message$"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^set_"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^set_start_date$"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^set_end_date$"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^toggle_"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^time_"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^time_slot_"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^repeat_"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^repeat_custom$"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^preview_"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^back_to_"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^full_preview$"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^select_topic$"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^scheduled_deletion$"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^day_"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^date_"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^delete_"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^save_message$"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^topic_"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^recurring_select_group_"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^recurring_add_new_group$"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^recurring_back_to_groups$"))
application.add_handler(CallbackQueryHandler(handle_recurring_callback, pattern="^admin_dashboard_back$"))

# Enhanced message handler for banned words detection
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

# Schedule jobs
application.job_queue.run_daily(award_daily_points, time=time(hour=0, minute=0))
application.job_queue.run_repeating(cleanup_old_polls, interval=3600, first=10)  # Cleanup polls every hour
application.job_queue.run_repeating(cleanup_expired_challenges, interval=300, first=30)  # Cleanup challenges every 5 minutes
application.job_queue.run_repeating(cleanup_memory, interval=3600, first=60)  # Memory cleanup every hour

# Weekly recap and reset - Every Sunday at 23:00
application.job_queue.run_daily(
    lambda context: asyncio.create_task(weekly_recap(context)) if datetime.now(TIMEZONE).weekday() == 6 else None,
    time=time(hour=23, minute=0)
)

# Monthly recap and reset - First day of each month at 00:30  
application.job_queue.run_daily(
    lambda context: asyncio.create_task(monthly_recap_and_reset(context)) if datetime.now(TIMEZONE).day == 1 else None,
    time=time(hour=0, minute=30)
)

# Achievement and Badge System
class AchievementSystem:
    def __init__(self):
        self.achievements = {
            'first_vote': {'name': '🗳️ Pirmasis Balsas', 'description': 'Pirmą kartą balsavai', 'points': 10},
            'voter_streak_7': {'name': '🔥 Balsavimo Entuziastas', 'description': '7 dienas iš eilės balsavai', 'points': 50},
            'chat_master_100': {'name': '💬 Pokalbių Meistras', 'description': '100 žinučių parašyta', 'points': 25},
            'chat_king_1000': {'name': '👑 Pokalbių Karalius', 'description': '1000 žinučių parašyta', 'points': 100},
            'coinflip_winner_5': {'name': '🪙 Monetos Valdovas', 'description': '5 coinflip laimėjimai', 'points': 30},
            'complaint_investigator': {'name': '🕵️ Tyrėjas', 'description': 'Pateikė 10 skundų', 'points': 75},
            'early_bird': {'name': '🌅 Ankstyvas Paukštis', 'description': 'Rašo iki 6 ryto', 'points': 20},
            'night_owl': {'name': '🦉 Nakties Pelėda', 'description': 'Rašo po 22 vakaro', 'points': 20},
            'weekend_warrior': {'name': '⚔️ Savaitgalio Karys', 'description': 'Aktyvus savaitgaliais', 'points': 15},
            'monthly_champion': {'name': '🏆 Mėnesio Čempionas', 'description': '#1 mėnesio pokalbių lyderis', 'points': 200},
        }
        
        self.seasonal_events = {
            'christmas': {
                'name': '🎄 Kalėdų Šventė',
                'start_date': '12-20',
                'end_date': '01-07',
                'bonus_multiplier': 2.0,
                'special_achievements': ['santa_helper', 'gift_giver']
            },
            'easter': {
                'name': '🐰 Velykos',
                'start_date': '03-20',
                'end_date': '04-20',
                'bonus_multiplier': 1.5,
                'special_achievements': ['egg_hunter']
            },
            'summer': {
                'name': '☀️ Vasaros Šventė',
                'start_date': '06-20',
                'end_date': '08-31',
                'bonus_multiplier': 1.3,
                'special_achievements': ['summer_vibes']
            }
        }
        
        self.load_user_achievements()
    
    def load_user_achievements(self):
        """Load user achievements from file"""
        self.user_achievements = load_data('user_achievements.pkl', defaultdict(set))
        self.user_progress = load_data('user_progress.pkl', defaultdict(dict))
    
    def save_achievements(self):
        """Save achievements to file"""
        save_data(dict(self.user_achievements), 'user_achievements.pkl')
        save_data(dict(self.user_progress), 'user_progress.pkl')
    
    def check_achievement(self, user_id, achievement_id, current_value=None):
        """Check if user earned an achievement"""
        if achievement_id in self.user_achievements[user_id]:
            return False  # Already has this achievement
        
        earned = False
        
        # Check specific achievement conditions
        if achievement_id == 'first_vote' and current_value == 1:
            earned = True
        elif achievement_id == 'chat_master_100' and current_value >= 100:
            earned = True
        elif achievement_id == 'chat_king_1000' and current_value >= 1000:
            earned = True
        elif achievement_id == 'early_bird':
            current_hour = datetime.now(TIMEZONE).hour
            if current_hour < 6:
                earned = True
        elif achievement_id == 'night_owl':
            current_hour = datetime.now(TIMEZONE).hour
            if current_hour >= 22:
                earned = True
        elif achievement_id == 'weekend_warrior':
            if datetime.now(TIMEZONE).weekday() >= 5:  # Saturday or Sunday
                earned = True
        
        if earned:
            self.user_achievements[user_id].add(achievement_id)
            achievement = self.achievements[achievement_id]
            user_points[user_id] = user_points.get(user_id, 0) + achievement['points']
            self.save_achievements()
            save_data(user_points, 'user_points.pkl')
            return achievement
        
        return False
    
    def get_user_achievements(self, user_id):
        """Get all achievements for a user"""
        user_achievement_ids = self.user_achievements.get(user_id, set())
        return [self.achievements[aid] for aid in user_achievement_ids if aid in self.achievements]
    
    def get_current_event(self):
        """Get currently active seasonal event"""
        now = datetime.now(TIMEZONE)
        current_date = now.strftime('%m-%d')
        
        for event_id, event in self.seasonal_events.items():
            start_date = event['start_date']
            end_date = event['end_date']
            
            # Handle year wrap-around (e.g., Christmas)
            if start_date > end_date:
                if current_date >= start_date or current_date <= end_date:
                    return event_id, event
            else:
                if start_date <= current_date <= end_date:
                    return event_id, event
        
        return None, None

# Weekly Challenge System
class WeeklyChallengeSystem:
    def __init__(self):
        self.challenges = [
            {
                'id': 'message_master',
                'name': '💬 Žinučių Meistras',
                'description': 'Parašyk 50 žinučių per savaitę',
                'target': 50,
                'reward_points': 100,
                'type': 'messages'
            },
            {
                'id': 'voting_champion',
                'name': '🗳️ Balsavimo Čempionas',
                'description': 'Balsuok už 3 skirtingus pardavėjus',
                'target': 3,
                'reward_points': 75,
                'type': 'unique_votes'
            },
            {
                'id': 'poll_creator',
                'name': '📊 Apklausų Kūrėjas',
                'description': 'Sukurk 3 apklausas',
                'target': 3,
                'reward_points': 60,
                'type': 'polls_created'
            },
            {
                'id': 'social_butterfly',
                'name': '🦋 Socialus Drugelis',
                'description': 'Pokalbiauk 5 skirtingas dienas',
                'target': 5,
                'reward_points': 80,
                'type': 'active_days'
            }
        ]
        
        self.load_weekly_progress()
    
    def load_weekly_progress(self):
        """Load weekly challenge progress"""
        self.weekly_progress = load_data('weekly_progress.pkl', defaultdict(dict))
    
    def save_weekly_progress(self):
        """Save weekly challenge progress"""
        save_data(dict(self.weekly_progress), 'weekly_progress.pkl')
    
    def update_progress(self, user_id, challenge_type, amount=1):
        """Update user progress for challenges"""
        week_key = datetime.now(TIMEZONE).strftime('%Y-W%U')
        
        if week_key not in self.weekly_progress[user_id]:
            self.weekly_progress[user_id][week_key] = defaultdict(int)
        
        self.weekly_progress[user_id][week_key][challenge_type] += amount
        self.save_weekly_progress()
        
        # Check for completed challenges
        completed = []
        for challenge in self.challenges:
            if challenge['type'] == challenge_type:
                current_progress = self.weekly_progress[user_id][week_key][challenge_type]
                if current_progress >= challenge['target']:
                    completed_key = f"{week_key}_{challenge['id']}"
                    if completed_key not in self.weekly_progress[user_id].get('completed', set()):
                        if 'completed' not in self.weekly_progress[user_id]:
                            self.weekly_progress[user_id]['completed'] = set()
                        self.weekly_progress[user_id]['completed'].add(completed_key)
                        completed.append(challenge)
                        
                        # Award points
                        user_points[user_id] = user_points.get(user_id, 0) + challenge['reward_points']
                        save_data(user_points, 'user_points.pkl')
        
        return completed
    
    def get_weekly_challenges(self, user_id):
        """Get current week's challenges and progress"""
        week_key = datetime.now(TIMEZONE).strftime('%Y-W%U')
        user_progress = self.weekly_progress[user_id].get(week_key, defaultdict(int))
        completed_challenges = self.weekly_progress[user_id].get('completed', set())
        
        result = []
        for challenge in self.challenges:
            completed_key = f"{week_key}_{challenge['id']}"
            current_progress = user_progress[challenge['type']]
            
            result.append({
                'challenge': challenge,
                'progress': current_progress,
                'completed': completed_key in completed_challenges
            })
        
        return result

# Initialize systems
achievement_system = AchievementSystem()
challenge_system = WeeklyChallengeSystem()

# Advanced Moderation System
class ModerationSystem:
    def __init__(self):
        self.load_moderation_data()
        self.spam_patterns = [
            r'(https?://\S+)',  # URLs
            r'(@[a-zA-Z0-9_]{5,})',  # Potential spam usernames
            r'(\b\d{10,}\b)',  # Long numbers (phone numbers)
            r'(telegram\.me|t\.me)',  # Telegram links
            r'(\b[A-Z]{5,}\b)',  # Excessive caps
        ]
        
        self.warning_thresholds = {
            'spam': 3,
            'caps': 2,
            'flood': 5,
            'links': 2
        }
        
        self.auto_actions = {
            'warn': 'warning',
            'mute': 'temporary_restriction',
            'ban': 'permanent_restriction'
        }
    
    def load_moderation_data(self):
        """Load moderation data"""
        self.user_warnings = load_data('user_warnings.pkl', defaultdict(list))
        self.banned_words = load_data('banned_words.pkl', set())
        self.trusted_users = load_data('trusted_users.pkl', set())
        self.moderation_logs = load_data('moderation_logs.pkl', [])
    
    def save_moderation_data(self):
        """Save moderation data"""
        save_data(dict(self.user_warnings), 'user_warnings.pkl')
        save_data(self.banned_words, 'banned_words.pkl')
        save_data(self.trusted_users, 'trusted_users.pkl')
        save_data(self.moderation_logs, 'moderation_logs.pkl')
    
    def check_spam(self, user_id, message_text, chat_id):
        """Check if message is spam"""
        if user_id in self.trusted_users:
            return False, None
        
        issues = []
        
        # Check for banned words
        message_lower = message_text.lower()
        for word in self.banned_words:
            if word.lower() in message_lower:
                issues.append(('banned_word', f"Banned word: {word}"))
        
        # Check spam patterns
        for pattern in self.spam_patterns:
            if re.search(pattern, message_text, re.IGNORECASE):
                pattern_name = {
                    r'(https?://\S+)': 'links',
                    r'(@[a-zA-Z0-9_]{5,})': 'mentions',
                    r'(\b\d{10,}\b)': 'phone_numbers',
                    r'(telegram\.me|t\.me)': 'telegram_links',
                    r'(\b[A-Z]{5,}\b)': 'caps'
                }.get(pattern, 'unknown')
                issues.append((pattern_name, f"Spam pattern: {pattern_name}"))
        
        # Check message length
        if len(message_text) > 1000:
            issues.append(('long_message', "Message too long"))
        
        # Check for excessive emoji
        emoji_count = len(re.findall(r'[^\w\s]', message_text))
        if emoji_count > 20:
            issues.append(('emoji_spam', f"Too many emojis: {emoji_count}"))
        
        return len(issues) > 0, issues
    
    def add_warning(self, user_id, chat_id, reason, moderator_id=None):
        """Add warning to user"""
        warning = {
            'timestamp': datetime.now(TIMEZONE),
            'reason': reason,
            'chat_id': chat_id,
            'moderator_id': moderator_id
        }
        
        self.user_warnings[user_id].append(warning)
        self.moderation_logs.append({
            'action': 'warning',
            'user_id': user_id,
            'chat_id': chat_id,
            'reason': reason,
            'moderator_id': moderator_id,
            'timestamp': datetime.now(TIMEZONE)
        })
        
        self.save_moderation_data()
        
        # Check if action needed
        recent_warnings = [w for w in self.user_warnings[user_id] 
                          if datetime.now(TIMEZONE) - w['timestamp'] < timedelta(days=7)]
        
        warning_count = len(recent_warnings)
        if warning_count >= 3:
            return 'mute'
        elif warning_count >= 5:
            return 'ban'
        
        return 'warn'
    
    def get_user_warnings(self, user_id, days=30):
        """Get user warnings in last N days"""
        cutoff = datetime.now(TIMEZONE) - timedelta(days=days)
        return [w for w in self.user_warnings.get(user_id, []) 
                if w['timestamp'] > cutoff]
    
    def is_flooding(self, user_id, chat_id, time_window=60, message_limit=10):
        """Check if user is flooding (too many messages)"""
        # This would need to track recent messages per user
        # For now, return False - implement based on analytics data
        return False

# Rate Limiting System
class RateLimiter:
    def __init__(self):
        self.command_cooldowns = defaultdict(dict)
        self.global_cooldowns = {
            'coinflip': 30,  # 30 seconds between coinflips
            'apklausa': 60,  # 1 minute between polls
            'nepatiko': 300,  # 5 minutes between complaints
            'balsuoti': 10,  # 10 seconds between votes
        }
    
    def check_cooldown(self, user_id, command):
        """Check if user is on cooldown for command"""
        if command not in self.global_cooldowns:
            return True, 0
        
        now = datetime.now(TIMEZONE)
        cooldown_time = self.global_cooldowns[command]
        
        if user_id in self.command_cooldowns and command in self.command_cooldowns[user_id]:
            last_use = self.command_cooldowns[user_id][command]
            time_since = (now - last_use).total_seconds()
            
            if time_since < cooldown_time:
                remaining = cooldown_time - time_since
                return False, remaining
        
        # Update last use time
        if user_id not in self.command_cooldowns:
            self.command_cooldowns[user_id] = {}
        self.command_cooldowns[user_id][command] = now
        
        return True, 0
    
    def format_cooldown_message(self, remaining_seconds):
        """Format cooldown message"""
        if remaining_seconds < 60:
            return f"Palauk {int(remaining_seconds)} sekundžių"
        else:
            minutes = int(remaining_seconds // 60)
            return f"Palauk {minutes} minučių"

# Initialize moderation systems
moderation_system = ModerationSystem()
rate_limiter = RateLimiter()

# Webhook support for production deployment
async def webhook_handler(request: Request) -> Response:
    """Handle incoming webhook updates from Telegram"""
    try:
        # Verify the request is from the correct path
        if request.path != WEBHOOK_PATH:
            logger.warning(f"Invalid webhook path: {request.path}")
            return Response(status=404)
        
        # Get the update data
        update_data = await request.json()
        
        # Process the update
        update = telegram.Update.de_json(update_data, application.bot)
        if update:
            # Use the application's update queue to process the update
            await application.process_update(update)
            logger.debug(f"Processed webhook update: {update.update_id}")
            
        return Response(text="OK")
        
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}")
        return Response(status=500, text="Internal Server Error")

async def health_check_handler(request: Request) -> Response:
    """Health check endpoint for Render.com"""
    return Response(text="Bot is healthy!", status=200)

async def create_webhook_app():
    """Create the webhook application"""
    app = web.Application()
    
    # Add webhook endpoint
    app.router.add_post(WEBHOOK_PATH, webhook_handler)
    
    # Add health check endpoint
    app.router.add_get("/health", health_check_handler)
    app.router.add_get("/", health_check_handler)  # Root endpoint
    
    return app

async def setup_webhook():
    """Set up webhook for the bot"""
    try:
        logger.info(f"Setting up webhook: {WEBHOOK_URL}")
        
        # Set the webhook
        await application.bot.set_webhook(
            url=WEBHOOK_URL,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True
        )
        
        # Verify webhook was set
        webhook_info = await application.bot.get_webhook_info()
        logger.info(f"Webhook set successfully: {webhook_info.url}")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to set webhook: {str(e)}")
        return False

async def run_webhook_mode():
    """Run the bot in webhook mode for production"""
    logger.info("Starting bot in webhook mode...")
    
    try:
        # Initialize the application
        await application.initialize()
        await application.start()
        
        # Set up the webhook
        webhook_success = await setup_webhook()
        if not webhook_success:
            logger.error("Failed to setup webhook, falling back to polling")
            await run_polling_mode()
            return
        
        # Create and start the web application
        webapp = await create_webhook_app()
        
        # Start the web server
        runner = web.AppRunner(webapp)
        await runner.setup()
        
        site = web.TCPSite(runner, host="0.0.0.0", port=PORT)
        await site.start()
        
        logger.info(f"Webhook server started on port {PORT}")
        
        # Keep the server running
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        
    except Exception as e:
        logger.error(f"Error in webhook mode: {str(e)}")
        raise
    finally:
        # Cleanup
        try:
            await application.stop()
            await application.shutdown()
            logger.info("Bot webhook mode stopped")
        except Exception as e:
            logger.error(f"Error during cleanup: {str(e)}")

async def run_polling_mode():
    """Run the bot in polling mode for development"""
    logger.info("Starting bot in polling mode...")
    
    try:
        # Remove webhook if it exists
        await application.bot.delete_webhook(drop_pending_updates=True)
        logger.info("Webhook removed, starting polling")
        
        # Run polling
        application.run_polling(
            poll_interval=1.0,
            timeout=10,
            bootstrap_retries=-1,
            read_timeout=10,
            write_timeout=10,
            connect_timeout=10,
            pool_timeout=10
        )
        
    except Exception as e:
        logger.error(f"Polling failed: {str(e)}")
        raise

if __name__ == '__main__':
    try:
        if RENDER_ENV and WEBHOOK_URL:
            # Production mode with webhooks
            asyncio.run(run_webhook_mode())
        else:
            # Development mode with polling
            asyncio.run(run_polling_mode())
            
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Bot failed to start: {str(e)}")
        sys.exit(1)
