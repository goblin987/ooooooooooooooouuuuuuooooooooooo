#!/usr/bin/env python3
"""
Read-Only Scammer Check Bot for Render Hosting
A standalone bot that provides read-only access to scammer and buyer reports.
"""

import logging
import os
import sqlite3
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
import asyncio
import aiohttp
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import re

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration from environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
MAIN_BOT_API_URL = os.getenv('MAIN_BOT_API_URL', '')  # URL to sync data from main bot
DATABASE_PATH = os.getenv('DATABASE_PATH', 'scammer_reports.db')

class Database:
    """Database handler for scammer and buyer reports"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Scammers table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scammers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    user_id INTEGER,
                    reports TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Bad buyers table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bad_buyers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    user_id INTEGER,
                    reports TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Username to ID mappings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS username_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Scheduled messages table (enhanced for GroupHelpBot features)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scheduled_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    message_text TEXT,
                    message_media TEXT,
                    message_buttons TEXT,
                    message_type TEXT DEFAULT 'text',
                    repetition_type TEXT DEFAULT 'interval',
                    interval_hours INTEGER DEFAULT 0,
                    interval_minutes INTEGER DEFAULT 30,
                    days_of_week TEXT,
                    days_of_month TEXT,
                    time_slots TEXT,
                    start_date TEXT,
                    end_date TEXT,
                    pin_message BOOLEAN DEFAULT 0,
                    delete_last_message BOOLEAN DEFAULT 0,
                    scheduled_deletion_hours INTEGER DEFAULT 0,
                    created_by INTEGER NOT NULL,
                    created_by_username TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT 1,
                    job_id TEXT UNIQUE,
                    last_sent TIMESTAMP,
                    status TEXT DEFAULT 'Off'
                )
            ''')
            
            # Banned words table
            cursor.execute('''
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
            
            # Helpers table for moderation permissions
            cursor.execute('''
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
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_scammers_username ON scammers(username)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_scammers_user_id ON scammers(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_buyers_username ON bad_buyers(username)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_buyers_user_id ON bad_buyers(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mappings_username ON username_mappings(username)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mappings_user_id ON username_mappings(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_scheduled_chat_id ON scheduled_messages(chat_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_scheduled_active ON scheduled_messages(is_active)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_banned_words_chat_id ON banned_words(chat_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_banned_words_word ON banned_words(word)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_helpers_chat_id ON helpers(chat_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_helpers_user_id ON helpers(user_id)')
            
            conn.commit()
    
    def get_scammer(self, username: str) -> Optional[Dict[str, Any]]:
        """Get scammer data by username"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT username, user_id, reports FROM scammers WHERE username = ?', (username.lower(),))
            row = cursor.fetchone()
            if row:
                return {
                    'username': row[0],
                    'user_id': row[1],
                    'reports': json.loads(row[2])
                }
        return None
    
    def get_bad_buyer(self, username: str) -> Optional[Dict[str, Any]]:
        """Get bad buyer data by username"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT username, user_id, reports FROM bad_buyers WHERE username = ?', (username.lower(),))
            row = cursor.fetchone()
            if row:
                return {
                    'username': row[0],
                    'user_id': row[1],
                    'reports': json.loads(row[2])
                }
        return None
    
    def get_user_id(self, username: str) -> Optional[int]:
        """Get user ID by username"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM username_mappings WHERE username = ?', (username.lower(),))
            row = cursor.fetchone()
            return row[0] if row else None
    
    def find_scammer_by_user_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Find scammer by user ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT username, user_id, reports FROM scammers WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'username': row[0],
                    'user_id': row[1],
                    'reports': json.loads(row[2])
                }
        return None
    
    def find_bad_buyer_by_user_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Find bad buyer by user ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT username, user_id, reports FROM bad_buyers WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'username': row[0],
                    'user_id': row[1],
                    'reports': json.loads(row[2])
                }
        return None
    
    def get_statistics(self) -> Dict[str, int]:
        """Get overall statistics"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Count scammers
            cursor.execute('SELECT COUNT(*) FROM scammers')
            total_scammers = cursor.fetchone()[0]
            
            # Count bad buyers
            cursor.execute('SELECT COUNT(*) FROM bad_buyers')
            total_bad_buyers = cursor.fetchone()[0]
            
            # Count total scammer reports
            cursor.execute('SELECT reports FROM scammers')
            scammer_reports = cursor.fetchall()
            total_scammer_reports = sum(len(json.loads(row[0])) for row in scammer_reports)
            
            # Count total buyer reports
            cursor.execute('SELECT reports FROM bad_buyers')
            buyer_reports = cursor.fetchall()
            total_buyer_reports = sum(len(json.loads(row[0])) for row in buyer_reports)
            
            return {
                'total_scammers': total_scammers,
                'total_bad_buyers': total_bad_buyers,
                'total_scammer_reports': total_scammer_reports,
                'total_buyer_reports': total_buyer_reports
            }
    
    def update_scammer(self, username: str, user_id: Optional[int], reports: List[Dict]):
        """Update or insert scammer data"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO scammers (username, user_id, reports, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (username.lower(), user_id, json.dumps(reports)))
            conn.commit()
    
    def update_bad_buyer(self, username: str, user_id: Optional[int], reports: List[Dict]):
        """Update or insert bad buyer data"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO bad_buyers (username, user_id, reports, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (username.lower(), user_id, json.dumps(reports)))
            conn.commit()
    
    def update_username_mapping(self, username: str, user_id: int):
        """Update username to ID mapping"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO username_mappings (username, user_id)
                VALUES (?, ?)
            ''', (username.lower(), user_id))
            conn.commit()
    
    def add_scheduled_message(self, chat_id: int, message_text: str, interval_hours: int, interval_minutes: int, 
                            created_by: int, created_by_username: str, job_id: str) -> int:
        """Add a new scheduled message"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO scheduled_messages (chat_id, message_text, interval_hours, interval_minutes, 
                                              created_by, created_by_username, job_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (chat_id, message_text, interval_hours, interval_minutes, created_by, created_by_username, job_id))
            conn.commit()
            return cursor.lastrowid
    
    def get_scheduled_messages(self, chat_id: int, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get scheduled messages for a chat"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            query = '''
                SELECT id, message_text, interval_hours, interval_minutes, created_by_username, 
                       created_at, is_active, job_id, last_sent
                FROM scheduled_messages 
                WHERE chat_id = ?
            '''
            params = [chat_id]
            
            if active_only:
                query += ' AND is_active = 1'
            
            query += ' ORDER BY created_at DESC'
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            return [{
                'id': row[0],
                'message_text': row[1],
                'interval_hours': row[2],
                'interval_minutes': row[3],
                'created_by_username': row[4],
                'created_at': row[5],
                'is_active': bool(row[6]),
                'job_id': row[7],
                'last_sent': row[8]
            } for row in rows]
    
    def delete_scheduled_message(self, message_id: int, chat_id: int) -> bool:
        """Delete a scheduled message"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM scheduled_messages 
                WHERE id = ? AND chat_id = ?
            ''', (message_id, chat_id))
            conn.commit()
            return cursor.rowcount > 0
    
    def update_scheduled_message_status(self, job_id: str, is_active: bool):
        """Update scheduled message status"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE scheduled_messages 
                SET is_active = ? 
                WHERE job_id = ?
            ''', (is_active, job_id))
            conn.commit()
    
    def update_last_sent(self, job_id: str):
        """Update last sent timestamp"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE scheduled_messages 
                SET last_sent = CURRENT_TIMESTAMP 
                WHERE job_id = ?
            ''', (job_id,))
            conn.commit()
    
     def get_all_active_scheduled_messages(self) -> List[Dict[str, Any]]:
         """Get all active scheduled messages"""
         with sqlite3.connect(self.db_path) as conn:
             cursor = conn.cursor()
             cursor.execute('''
                 SELECT id, chat_id, message_text, interval_hours, interval_minutes, job_id
                 FROM scheduled_messages 
                 WHERE is_active = 1
             ''')
             rows = cursor.fetchall()
             
             return [{
                 'id': row[0],
                 'chat_id': row[1],
                 'message_text': row[2],
                 'interval_hours': row[3],
                 'interval_minutes': row[4],
                 'job_id': row[5]
             } for row in rows]
     
     def add_banned_word(self, chat_id: int, word: str, action: str, created_by: int, created_by_username: str) -> int:
         """Add a new banned word"""
         with sqlite3.connect(self.db_path) as conn:
             cursor = conn.cursor()
             cursor.execute('''
                 INSERT INTO banned_words (chat_id, word, action, created_by, created_by_username)
                 VALUES (?, ?, ?, ?, ?)
             ''', (chat_id, word.lower(), action, created_by, created_by_username))
             conn.commit()
             return cursor.lastrowid
     
     def get_banned_words(self, chat_id: int, active_only: bool = True) -> List[Dict[str, Any]]:
         """Get banned words for a chat"""
         with sqlite3.connect(self.db_path) as conn:
             cursor = conn.cursor()
             query = '''
                 SELECT id, word, action, created_by_username, created_at, is_active
                 FROM banned_words 
                 WHERE chat_id = ?
             '''
             params = [chat_id]
             
             if active_only:
                 query += ' AND is_active = 1'
             
             query += ' ORDER BY created_at DESC'
             
             cursor.execute(query, params)
             rows = cursor.fetchall()
             
             return [{
                 'id': row[0],
                 'word': row[1],
                 'action': row[2],
                 'created_by_username': row[3],
                 'created_at': row[4],
                 'is_active': bool(row[5])
             } for row in rows]
     
     def delete_banned_word(self, word_id: int, chat_id: int) -> bool:
         """Delete a banned word"""
         with sqlite3.connect(self.db_path) as conn:
             cursor = conn.cursor()
             cursor.execute('''
                 DELETE FROM banned_words 
                 WHERE id = ? AND chat_id = ?
             ''', (word_id, chat_id))
             conn.commit()
             return cursor.rowcount > 0
     
     def update_banned_word_status(self, word_id: int, is_active: bool):
         """Update banned word status"""
         with sqlite3.connect(self.db_path) as conn:
             cursor = conn.cursor()
             cursor.execute('''
                 UPDATE banned_words 
                 SET is_active = ? 
                 WHERE id = ?
             ''', (is_active, word_id))
             conn.commit()
     
     def check_banned_words(self, chat_id: int, message_text: str) -> List[Dict[str, Any]]:
         """Check if message contains banned words"""
         banned_words = self.get_banned_words(chat_id, active_only=True)
         found_words = []
         
         message_lower = message_text.lower()
         for word_data in banned_words:
             if word_data['word'] in message_lower:
                 found_words.append(word_data)
         
         return found_words
     
     def add_helper(self, chat_id: int, user_id: int, username: str, added_by: int, added_by_username: str) -> int:
         """Add a new helper"""
         with sqlite3.connect(self.db_path) as conn:
             cursor = conn.cursor()
             cursor.execute('''
                 INSERT INTO helpers (chat_id, user_id, username, added_by, added_by_username)
                 VALUES (?, ?, ?, ?, ?)
             ''', (chat_id, user_id, username, added_by, added_by_username))
             conn.commit()
             return cursor.lastrowid
     
     def get_helpers(self, chat_id: int, active_only: bool = True) -> List[Dict[str, Any]]:
         """Get helpers for a chat"""
         with sqlite3.connect(self.db_path) as conn:
             cursor = conn.cursor()
             query = '''
                 SELECT id, user_id, username, added_by_username, added_at, is_active
                 FROM helpers 
                 WHERE chat_id = ?
             '''
             params = [chat_id]
             
             if active_only:
                 query += ' AND is_active = 1'
             
             query += ' ORDER BY added_at DESC'
             
             cursor.execute(query, params)
             rows = cursor.fetchall()
             
             return [{
                 'id': row[0],
                 'user_id': row[1],
                 'username': row[2],
                 'added_by_username': row[3],
                 'added_at': row[4],
                 'is_active': bool(row[5])
             } for row in rows]
     
     def remove_helper(self, helper_id: int, chat_id: int) -> bool:
         """Remove a helper"""
         with sqlite3.connect(self.db_path) as conn:
             cursor = conn.cursor()
             cursor.execute('''
                 DELETE FROM helpers 
                 WHERE id = ? AND chat_id = ?
             ''', (helper_id, chat_id))
             conn.commit()
             return cursor.rowcount > 0
     
     def is_helper(self, chat_id: int, user_id: int) -> bool:
         """Check if user is a helper in the chat"""
         with sqlite3.connect(self.db_path) as conn:
             cursor = conn.cursor()
             cursor.execute('''
                 SELECT COUNT(*) FROM helpers 
                 WHERE chat_id = ? AND user_id = ? AND is_active = 1
             ''', (chat_id, user_id))
             return cursor.fetchone()[0] > 0

# Global database instance
db = Database(DATABASE_PATH)

# Global scheduler instance
scheduler = AsyncIOScheduler()
application_instance = None  # Will be set in main()

def sanitize_username(username: str) -> str:
    """Sanitize username input"""
    if not username:
        return ""
    # Remove @ symbol if present
    username = username.lstrip('@')
    # Remove any whitespace and convert to lowercase
    username = username.strip().lower()
    return username

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is admin in the group"""
    if update.effective_chat.type == 'private':
        return True  # In private chats, user is always "admin"
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        is_admin_member = member.status in ['creator', 'administrator']
        
        # Check if user is a helper (even if not admin)
        is_helper = db.is_helper(chat_id, user_id)
        
        return is_admin_member or is_helper
    except Exception:
        return False

async def can_ban_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user can ban users in the group"""
    if update.effective_chat.type == 'private':
        return False  # Can't ban in private chats
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        is_admin_with_permissions = member.status in ['creator', 'administrator'] and member.can_restrict_members
        
        # Check if user is a helper (helpers can ban even if not admin)
        is_helper = db.is_helper(chat_id, user_id)
        
        return is_admin_with_permissions or is_helper
    except Exception:
        return False

async def can_mute_users(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user can mute users in the group"""
    if update.effective_chat.type == 'private':
        return False  # Can't mute in private chats
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        is_admin_with_permissions = member.status in ['creator', 'administrator'] and member.can_restrict_members
        
        # Check if user is a helper (helpers can mute even if not admin)
        is_helper = db.is_helper(chat_id, user_id)
        
        return is_admin_with_permissions or is_helper
    except Exception:
        return False

async def send_scheduled_message(chat_id: int, message_text: str, job_id: str):
    """Send a scheduled message"""
    try:
        if application_instance and application_instance.bot:
            await application_instance.bot.send_message(
                chat_id=chat_id,
                text=message_text,
                parse_mode='Markdown'
            )
            # Update last sent timestamp
            db.update_last_sent(job_id)
            logger.info(f"Sent scheduled message to chat {chat_id}")
    except Exception as e:
        logger.error(f"Error sending scheduled message to chat {chat_id}: {e}")
        # If message fails, we could optionally disable the schedule
        # db.update_scheduled_message_status(job_id, False)

def parse_interval(interval_text: str) -> tuple[int, int]:
    """Parse interval text like '3h', '30m', '2h30m' into hours and minutes"""
    hours = 0
    minutes = 0
    
    # Match patterns like 3h, 30m, 2h30m
    hour_match = re.search(r'(\d+)h', interval_text.lower())
    minute_match = re.search(r'(\d+)m', interval_text.lower())
    
    if hour_match:
        hours = int(hour_match.group(1))
    if minute_match:
        minutes = int(minute_match.group(1))
    
    # If no pattern matched, try to parse as pure number (assume minutes)
    if hours == 0 and minutes == 0:
        try:
            minutes = int(interval_text)
        except ValueError:
            pass
    
    return hours, minutes

def format_interval(hours: int, minutes: int) -> str:
    """Format interval as human readable string"""
    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    return " ".join(parts) if parts else "0m"

async def sync_data_from_main_bot():
    """Sync data from main bot API (if available)"""
    if not MAIN_BOT_API_URL:
        logger.info("No main bot API URL configured, skipping sync")
        return
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{MAIN_BOT_API_URL}/api/scammers") as response:
                if response.status == 200:
                    scammers = await response.json()
                    for username, data in scammers.items():
                        db.update_scammer(username, data.get('user_id'), data.get('reports', []))
            
            async with session.get(f"{MAIN_BOT_API_URL}/api/bad_buyers") as response:
                if response.status == 200:
                    buyers = await response.json()
                    for username, data in buyers.items():
                        db.update_bad_buyer(username, data.get('user_id'), data.get('reports', []))
            
            async with session.get(f"{MAIN_BOT_API_URL}/api/username_mappings") as response:
                if response.status == 200:
                    mappings = await response.json()
                    for username, user_id in mappings.items():
                        db.update_username_mapping(username, user_id)
                        
        logger.info("Data sync completed successfully")
    except Exception as e:
        logger.error(f"Error syncing data from main bot: {e}")

async def recurring_messages_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the main recurring messages menu"""
    if not await is_admin(update, context):
        await update.message.reply_text(
            "❌ **KLAIDA**\n\n"
            "Tik grupės administratoriai gali naudoti šią komandą!",
            parse_mode='Markdown'
        )
        return
    
    chat_id = update.effective_chat.id
    current_time = datetime.now().strftime("%d/%m/%y %H:%M")
    
    # Check if there are any active scheduled messages
    scheduled_messages = db.get_scheduled_messages(chat_id, active_only=True)
    has_active = len(scheduled_messages) > 0
    
    text = (
        "🔄 **Recurring messages**\n\n"
        f"From this menu you can set messages that will be sent "
        f"repeatedly to the group every few minutes/hours or every "
        f"few messages.\n\n"
        f"Current time: {current_time}"
    )
    
    keyboard = [
        [InlineKeyboardButton("➕ Add message", callback_data="add_recurring_message")]
    ]
    
    if has_active:
        keyboard.append([InlineKeyboardButton("📋 Manage messages", callback_data="manage_recurring_messages")])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def show_message_config(update: Update, context: ContextTypes.DEFAULT_TYPE, message_id: int = None) -> None:
    """Show message configuration screen"""
    query = update.callback_query
    if query:
        await query.answer()
    
    chat_id = update.effective_chat.id if update.effective_chat else query.message.chat.id
    current_time = datetime.now().strftime("%H:%M")
    
    # Get existing message data if editing
    if message_id:
        # TODO: Get existing message data from database
        pass
    
    text = (
        "🔄 **Recurring messages**\n\n"
        f"📊 Status: ❌ Off\n"
        f"⏰ Time: {current_time}\n"
        f"🔄 Repetition: Every 24 hours\n"
        f"📌 Pin message: ❌\n"
        f"🗑️ Delete last message: ❌"
    )
    
    keyboard = [
        [InlineKeyboardButton("✏️ Customize message", callback_data="customize_message")],
        [
            InlineKeyboardButton("⏰ Time", callback_data="set_time"),
            InlineKeyboardButton("🔄 Repetition", callback_data="set_repetition")
        ],
        [InlineKeyboardButton("📅 Days of the week", callback_data="set_days_week")],
        [InlineKeyboardButton("📅 Days of the month", callback_data="set_days_month")],
        [InlineKeyboardButton("🕐 Set time slot", callback_data="set_time_slot")],
        [
            InlineKeyboardButton("📅 Start date", callback_data="set_start_date"),
            InlineKeyboardButton("📅 End date", callback_data="set_end_date")
        ],
        [InlineKeyboardButton("📌 Pin message ❌", callback_data="toggle_pin_message")],
        [InlineKeyboardButton("🗑️ Delete last message ❌", callback_data="toggle_delete_last")],
        [InlineKeyboardButton("⏱️ Scheduled deletion", callback_data="set_scheduled_deletion")],
        [InlineKeyboardButton("🔙 Back", callback_data="recurring_messages_menu")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if query:
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode='Markdown',
            reply_markup=reply_markup
        )

async def show_message_customization(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show message customization options"""
    query = update.callback_query
    await query.answer()
    
    text = (
        "🔄 **Recurring messages**\n\n"
        "📝 Text: ❌\n"
        "📷 Media: ❌\n"
        "🔗 Url Buttons: ❌\n\n"
        "Use the buttons below to choose what you want to set"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📝 Text", callback_data="set_text"),
            InlineKeyboardButton("👁️ See", callback_data="preview_text")
        ],
        [
            InlineKeyboardButton("📷 Media", callback_data="set_media"),
            InlineKeyboardButton("👁️ See", callback_data="preview_media")
        ],
        [
            InlineKeyboardButton("🔗 Url Buttons", callback_data="set_url_buttons"),
            InlineKeyboardButton("👁️ See", callback_data="preview_buttons")
        ],
        [InlineKeyboardButton("👁️ Full preview", callback_data="full_preview")],
        [InlineKeyboardButton("📋 Select a Topic", callback_data="select_topic")],
        [InlineKeyboardButton("🔙 Back", callback_data="message_config")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all callback queries from inline keyboards"""
    query = update.callback_query
    await query.answer()
    
    if not await is_admin_callback(query, context):
        await query.edit_message_text(
            "❌ **KLAIDA**\n\n"
            "Tik grupės administratoriai gali naudoti šią funkciją!",
            parse_mode='Markdown'
        )
        return
    
    data = query.data
    
    # Main menu callbacks
    if data == "recurring_messages_menu":
        await show_recurring_messages_menu_callback(query, context)
    elif data == "add_recurring_message":
        await show_message_config(update, context)
    elif data == "manage_recurring_messages":
        await show_manage_messages(query, context)
    
    # Message configuration callbacks
    elif data == "message_config":
        await show_message_config(update, context)
    elif data == "customize_message":
        await show_message_customization(update, context)
    
    # Message customization callbacks
    elif data == "set_text":
        await prompt_text_input(query, context)
    elif data == "set_media":
        await prompt_media_input(query, context)
    elif data == "set_url_buttons":
        await prompt_url_buttons_input(query, context)
    elif data.startswith("preview_"):
        await show_preview(query, context, data.split("_")[1])
    elif data == "full_preview":
        await show_full_preview(query, context)
    elif data == "select_topic":
        await show_topic_selection(query, context)
    
    # Time and repetition callbacks
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
    elif data == "set_start_date":
        await prompt_start_date(query, context)
    elif data == "set_end_date":
        await prompt_end_date(query, context)
    
    # Toggle callbacks
    elif data == "toggle_pin_message":
        await toggle_pin_message(query, context)
    elif data == "toggle_delete_last":
        await toggle_delete_last(query, context)
    elif data == "set_scheduled_deletion":
        await show_scheduled_deletion_options(query, context)
    
         # Message management callbacks
     elif data.startswith("msg_info_"):
         await show_message_info(query, context, data)
     elif data.startswith("toggle_msg_"):
         await toggle_message_status(query, context, data)
     elif data.startswith("delete_msg_"):
         await delete_message(query, context, data)
     
     # Banned words callbacks
     elif data == "banned_words_menu":
         await show_banned_words_menu_callback(query, context)
     elif data == "add_banned_word":
         await show_add_banned_word(query, context)
     elif data.startswith("word_info_"):
         await show_word_info(query, context, data)
     elif data.startswith("toggle_word_"):
         await toggle_word_status(query, context, data)
     elif data.startswith("delete_word_"):
         await delete_word(query, context, data)
     elif data.startswith("action_"):
         await handle_action_selection(query, context, data)
     
     # Helpers callbacks
     elif data == "helpers_menu":
         await show_helpers_menu_callback(query, context)
     elif data == "add_helper":
         await show_add_helper(query, context)
     elif data.startswith("helper_info_"):
         await show_helper_info(query, context, data)
     elif data.startswith("remove_helper_"):
         await remove_helper(query, context, data)
    
    # Repetition type callbacks
    elif data.startswith("rep_"):
        await handle_repetition_selection(query, context, data)
    elif data.startswith("toggle_day_"):
        await handle_day_toggle(query, context, data)
    elif data == "confirm_days_week":
        await confirm_days_selection(query, context)
    elif data.startswith("timeslot_"):
        await handle_timeslot_selection(query, context, data)
    
    # Navigation callbacks
    elif data == "main_menu":
        await show_main_menu(query, context)

# Additional handler functions for new callbacks
async def handle_repetition_selection(query, context, data):
    """Handle repetition type selection"""
    rep_type = data.replace("rep_", "")
    context.user_data['repetition_type'] = rep_type
    
    if rep_type == "24hours":
        await query.edit_message_text("✅ Set to repeat every 24 hours!", parse_mode='Markdown')
    elif rep_type == "days_week":
        await show_days_of_week(query, context)
    elif rep_type == "days_month":
        await show_days_of_month(query, context)
    elif rep_type == "custom_interval":
        await query.edit_message_text("⏰ Please enter custom interval (e.g., 3h, 30m, 2h30m):", parse_mode='Markdown')

async def handle_day_toggle(query, context, data):
    """Handle day of week toggle"""
    day_code = data.replace("toggle_day_", "")
    selected_days = context.user_data.get('selected_days_week', set())
    
    if day_code in selected_days:
        selected_days.remove(day_code)
    else:
        selected_days.add(day_code)
    
    context.user_data['selected_days_week'] = selected_days
    await show_days_of_week(query, context)

async def confirm_days_selection(query, context):
    """Confirm days of week selection"""
    selected_days = context.user_data.get('selected_days_week', set())
    if selected_days:
        days_text = ", ".join(selected_days)
        await query.edit_message_text(f"✅ Days selected: {days_text}", parse_mode='Markdown')
    else:
        await query.edit_message_text("❌ No days selected!", parse_mode='Markdown')

async def handle_timeslot_selection(query, context, data):
    """Handle time slot selection"""
    timeslot = data.replace("timeslot_", "")
    context.user_data['selected_timeslot'] = timeslot
    
    if timeslot == "custom":
        await query.edit_message_text("⏰ Please enter custom time (HH:MM format):", parse_mode='Markdown')
    elif timeslot == "multiple":
        await query.edit_message_text("🔄 Please enter multiple times separated by commas (e.g., 08:00, 14:00, 20:00):", parse_mode='Markdown')
    else:
        await query.edit_message_text(f"✅ Time slot set to: {timeslot}", parse_mode='Markdown')

# Message management functions
async def show_message_info(query, context, data):
    """Show detailed information about a specific message"""
    message_id = int(data.replace("msg_info_", ""))
    chat_id = query.message.chat.id
    
    # Get message details from database
    scheduled_messages = db.get_scheduled_messages(chat_id, active_only=False)
    target_message = None
    
    for msg in scheduled_messages:
        if msg['id'] == message_id:
            target_message = msg
            break
    
    if not target_message:
        await query.edit_message_text("❌ Message not found!", parse_mode='Markdown')
        return
    
    # Format the message info
    status = "✅ Active" if target_message['is_active'] else "❌ Inactive"
    time_str = f"{target_message['interval_hours']}h{target_message['interval_minutes']}m" if target_message['interval_hours'] > 0 else f"{target_message['interval_minutes']}m"
    if target_message['interval_hours'] == 24 and target_message['interval_minutes'] == 0:
        time_str = "Every 24 hours"
    
    text = (
        f"📋 **Message #{message_id} Details**\n\n"
        f"📊 Status: {status}\n"
        f"⏰ Interval: {time_str}\n"
        f"👤 Created by: @{target_message['created_by_username']}\n"
        f"📅 Created: {target_message['created_at'][:19]}\n"
    )
    
    if target_message['last_sent']:
        text += f"📤 Last sent: {target_message['last_sent'][:19]}\n"
    
    text += f"\n📝 **Message:**\n{target_message['message_text'] or 'Message is not set.'}"
    
    keyboard = [
        [InlineKeyboardButton("🔙 Back to Manage", callback_data="manage_recurring_messages")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def toggle_message_status(query, context, data):
    """Toggle message active/inactive status"""
    message_id = int(data.replace("toggle_msg_", ""))
    chat_id = query.message.chat.id
    
    # Get current message status
    scheduled_messages = db.get_scheduled_messages(chat_id, active_only=False)
    target_message = None
    
    for msg in scheduled_messages:
        if msg['id'] == message_id:
            target_message = msg
            break
    
    if not target_message:
        await query.edit_message_text("❌ Message not found!", parse_mode='Markdown')
        return
    
    # Toggle status
    new_status = not target_message['is_active']
    
    # Update database
    db.update_scheduled_message_status(target_message['job_id'], new_status)
    
    # Update scheduler
    if new_status:
        # Re-add job to scheduler
        scheduler.add_job(
            send_scheduled_message,
            IntervalTrigger(hours=target_message['interval_hours'], minutes=target_message['interval_minutes']),
            args=[chat_id, target_message['message_text'], target_message['job_id']],
            id=target_message['job_id'],
            replace_existing=True
        )
    else:
        # Remove job from scheduler
        try:
            scheduler.remove_job(target_message['job_id'])
        except Exception:
            pass
    
    # Show updated manage messages screen
    await show_manage_messages(query, context)

async def delete_message(query, context, data):
    """Delete a scheduled message"""
    message_id = int(data.replace("delete_msg_", ""))
    chat_id = query.message.chat.id
    
    # Get message details before deletion
    scheduled_messages = db.get_scheduled_messages(chat_id, active_only=False)
    target_message = None
    
    for msg in scheduled_messages:
        if msg['id'] == message_id:
            target_message = msg
            break
    
    if not target_message:
        await query.edit_message_text("❌ Message not found!", parse_mode='Markdown')
        return
    
    # Remove from scheduler
    try:
        scheduler.remove_job(target_message['job_id'])
    except Exception:
        pass
    
    # Delete from database
    if db.delete_scheduled_message(message_id, chat_id):
        await query.edit_message_text(
            f"✅ **Message #{message_id} deleted successfully!**\n\n"
            f"📝 Message: {target_message['message_text'][:100]}{'...' if len(target_message['message_text'] or '') > 100 else ''}",
            parse_mode='Markdown'
        )
        
        # Return to manage messages after 2 seconds
        await asyncio.sleep(2)
        await show_manage_messages(query, context)
    else:
        await query.edit_message_text("❌ Failed to delete message!", parse_mode='Markdown')

async def is_admin_callback(query, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is admin for callback queries"""
    if query.message.chat.type == 'private':
        return True
    
    user_id = query.from_user.id
    chat_id = query.message.chat.id
    
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except Exception:
        return False

async def show_recurring_messages_menu_callback(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recurring messages menu via callback"""
    chat_id = query.message.chat.id
    current_time = datetime.now().strftime("%d/%m/%y %H:%M")
    
    scheduled_messages = db.get_scheduled_messages(chat_id, active_only=True)
    has_active = len(scheduled_messages) > 0
    
    text = (
        "🔄 **Recurring messages**\n\n"
        f"From this menu you can set messages that will be sent "
        f"repeatedly to the group every few minutes/hours or every "
        f"few messages.\n\n"
        f"Current time: {current_time}"
    )
    
    keyboard = [
        [InlineKeyboardButton("➕ Add message", callback_data="add_recurring_message")],
        [InlineKeyboardButton("🔙 Back", callback_data="main_menu")]
    ]
    
    if has_active:
        keyboard.insert(-1, [InlineKeyboardButton("📋 Manage messages", callback_data="manage_recurring_messages")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

# Placeholder functions for callback handlers (to be implemented)
async def show_manage_messages(query, context):
    """Show manage messages screen with existing scheduled messages"""
    chat_id = query.message.chat.id
    current_time = datetime.now().strftime("%d/%m/%y %H:%M")
    
    # Get all scheduled messages for this chat
    scheduled_messages = db.get_scheduled_messages(chat_id, active_only=False)
    
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
            time_str = f"{msg['interval_hours']}h{msg['interval_minutes']}m" if msg['interval_hours'] > 0 else f"{msg['interval_minutes']}m"
            if msg['interval_hours'] == 24 and msg['interval_minutes'] == 0:
                time_str = "Every 24 hours"
            elif msg['interval_hours'] == 0 and msg['interval_minutes'] == 0:
                time_str = "Custom"
            
            # Get message preview
            message_preview = msg['message_text'][:50] if msg['message_text'] else "Message is not set."
            if len(msg['message_text'] or "") > 50:
                message_preview += "..."
            
            text += f"\n\n**{i} • {status}** {status_icon}\n"
            text += f"   Time: {time_str}\n"
            text += f"   {message_preview}"
    
    keyboard = [
        [InlineKeyboardButton("➕ Add message", callback_data="add_recurring_message")]
    ]
    
    # Add message management buttons for each existing message
    if scheduled_messages:
        for i, msg in enumerate(scheduled_messages, 1):
            status_text = "❌ Inactive" if msg['is_active'] else "✅ Active"
            keyboard.append([
                InlineKeyboardButton(f"{i}", callback_data=f"msg_info_{msg['id']}"),
                InlineKeyboardButton(status_text, callback_data=f"toggle_msg_{msg['id']}"),
                InlineKeyboardButton("🗑️", callback_data=f"delete_msg_{msg['id']}")
            ])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="recurring_messages_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def prompt_text_input(query, context):
    await query.edit_message_text("📝 Please send your message text:", parse_mode='Markdown')

async def prompt_media_input(query, context):
    await query.edit_message_text("📷 Please send your media (photo/video/document):", parse_mode='Markdown')

async def prompt_url_buttons_input(query, context):
    await query.edit_message_text("🔗 Please send URL buttons in format: Text|URL", parse_mode='Markdown')

async def show_preview(query, context, preview_type):
    await query.edit_message_text(f"👁️ Preview {preview_type} - Coming soon!", parse_mode='Markdown')

async def show_full_preview(query, context):
    await query.edit_message_text("👁️ Full preview - Coming soon!", parse_mode='Markdown')

async def show_topic_selection(query, context):
    await query.edit_message_text("📋 Topic selection - Coming soon!", parse_mode='Markdown')

async def show_time_selection(query, context):
    await query.edit_message_text("⏰ Time selection - Coming soon!", parse_mode='Markdown')

async def show_repetition_options(query, context):
    """Show repetition options matching GroupHelpBot"""
    text = (
        "🔄 **Recurring messages**\n\n"
        "**Choose repetition type:**"
    )
    
    keyboard = [
        [InlineKeyboardButton("⏰ Every 24 hours", callback_data="rep_24hours")],
        [InlineKeyboardButton("📅 Days of the week", callback_data="rep_days_week")],
        [InlineKeyboardButton("📅 Days of the month", callback_data="rep_days_month")],
        [InlineKeyboardButton("🔄 Custom interval", callback_data="rep_custom_interval")],
        [InlineKeyboardButton("🔙 Back", callback_data="message_config")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def show_days_of_week(query, context):
    """Show days of the week selection"""
    text = (
        "📅 **Days of the week**\n\n"
        "Select which days of the week to send the message:"
    )
    
    # Get current selection (would be stored in context.user_data)
    selected_days = context.user_data.get('selected_days_week', set())
    
    days = [
        ("Monday", "mon"), ("Tuesday", "tue"), ("Wednesday", "wed"),
        ("Thursday", "thu"), ("Friday", "fri"), ("Saturday", "sat"), ("Sunday", "sun")
    ]
    
    keyboard = []
    for day_name, day_code in days:
        if day_code in selected_days:
            keyboard.append([InlineKeyboardButton(f"✅ {day_name}", callback_data=f"toggle_day_{day_code}")])
        else:
            keyboard.append([InlineKeyboardButton(f"⬜ {day_name}", callback_data=f"toggle_day_{day_code}")])
    
    keyboard.append([InlineKeyboardButton("✅ Confirm Selection", callback_data="confirm_days_week")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="set_repetition")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def show_days_of_month(query, context):
    await query.edit_message_text("📅 Days of month - Coming soon!", parse_mode='Markdown')

async def show_time_slot_options(query, context):
    """Show time slot selection options"""
    text = (
        "🕐 **Set time slot**\n\n"
        "Choose when to send the recurring message:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🌅 Morning (08:00)", callback_data="timeslot_08:00")],
        [InlineKeyboardButton("🌞 Midday (12:00)", callback_data="timeslot_12:00")],
        [InlineKeyboardButton("🌇 Evening (18:00)", callback_data="timeslot_18:00")],
        [InlineKeyboardButton("🌙 Night (22:00)", callback_data="timeslot_22:00")],
        [InlineKeyboardButton("⏰ Custom time", callback_data="timeslot_custom")],
        [InlineKeyboardButton("🔄 Multiple times", callback_data="timeslot_multiple")],
        [InlineKeyboardButton("🔙 Back", callback_data="message_config")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def prompt_start_date(query, context):
    await query.edit_message_text("📅 Please enter start date (DD/MM/YYYY):", parse_mode='Markdown')

async def prompt_end_date(query, context):
    await query.edit_message_text("📅 Please enter end date (DD/MM/YYYY):", parse_mode='Markdown')

async def toggle_pin_message(query, context):
    await query.edit_message_text("📌 Pin message toggled!", parse_mode='Markdown')

async def toggle_delete_last(query, context):
    await query.edit_message_text("🗑️ Delete last message toggled!", parse_mode='Markdown')

async def show_scheduled_deletion_options(query, context):
    await query.edit_message_text("⏱️ Scheduled deletion options - Coming soon!", parse_mode='Markdown')

async def show_main_menu(query, context):
     await query.edit_message_text("🏠 Main menu - Coming soon!", parse_mode='Markdown')

# Banned words callback functions
async def show_banned_words_menu_callback(query, context):
     """Show banned words menu via callback"""
     chat_id = query.message.chat.id
     current_time = datetime.now().strftime("%d/%m/%y %H:%M")
     
     banned_words = db.get_banned_words(chat_id, active_only=False)
     
     text = (
         "🚫 **Banned words**\n\n"
         f"From this menu you can manage words that are banned "
         f"in this group. Users who use these words will be "
         f"automatically punished.\n\n"
         f"Current time: {current_time}"
     )
     
     if banned_words:
         text += f"\n\n📋 **Banned words ({len(banned_words)}):**"
         for i, word_data in enumerate(banned_words, 1):
             status = "✅ Active" if word_data['is_active'] else "❌ Inactive"
             status_icon = "✅" if word_data['is_active'] else "❌"
             action_emoji = "⚠️" if word_data['action'] == 'warn' else "🚫" if word_data['action'] == 'ban' else "🔇"
             
             text += f"\n\n**{i} • {status}** {status_icon}\n"
             text += f"   Word: `{word_data['word']}`\n"
             text += f"   Action: {action_emoji} {word_data['action'].title()}\n"
             text += f"   Added by: @{word_data['created_by_username']}"
     
     keyboard = [
         [InlineKeyboardButton("➕ Add word", callback_data="add_banned_word")]
     ]
     
     if banned_words:
         for i, word_data in enumerate(banned_words, 1):
             status_text = "❌ Inactive" if word_data['is_active'] else "✅ Active"
             keyboard.append([
                 InlineKeyboardButton(f"{i}", callback_data=f"word_info_{word_data['id']}"),
                 InlineKeyboardButton(status_text, callback_data=f"toggle_word_{word_data['id']}"),
                 InlineKeyboardButton("🗑️", callback_data=f"delete_word_{word_data['id']}")
             ])
     
     keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
     
     reply_markup = InlineKeyboardMarkup(keyboard)
     await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def show_add_banned_word(query, context):
     """Show add banned word interface"""
     text = (
         "🚫 **Add banned word**\n\n"
         "Please send the word you want to ban.\n\n"
         "**Examples:**\n"
         "• `spam`\n"
         "• `badword`\n"
         "• `inappropriate`"
     )
     
     keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="banned_words_menu")]]
     reply_markup = InlineKeyboardMarkup(keyboard)
     
     await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
     # Set state to wait for word input
     context.user_data['waiting_for_word'] = True

async def show_word_info(query, context, data):
     """Show detailed information about a banned word"""
     word_id = int(data.replace("word_info_", ""))
     chat_id = query.message.chat.id
     
     banned_words = db.get_banned_words(chat_id, active_only=False)
     target_word = None
     
     for word_data in banned_words:
         if word_data['id'] == word_id:
             target_word = word_data
             break
     
     if not target_word:
         await query.edit_message_text("❌ Word not found!", parse_mode='Markdown')
         return
     
     status = "✅ Active" if target_word['is_active'] else "❌ Inactive"
     action_emoji = "⚠️" if target_word['action'] == 'warn' else "🚫" if target_word['action'] == 'ban' else "🔇"
     
     text = (
         f"📋 **Banned Word #{word_id} Details**\n\n"
         f"📝 Word: `{target_word['word']}`\n"
         f"📊 Status: {status}\n"
         f"⚡ Action: {action_emoji} {target_word['action'].title()}\n"
         f"👤 Added by: @{target_word['created_by_username']}\n"
         f"📅 Added: {target_word['created_at'][:19]}"
     )
     
     keyboard = [[InlineKeyboardButton("🔙 Back to Manage", callback_data="banned_words_menu")]]
     reply_markup = InlineKeyboardMarkup(keyboard)
     await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def toggle_word_status(query, context, data):
     """Toggle banned word active/inactive status"""
     word_id = int(data.replace("toggle_word_", ""))
     chat_id = query.message.chat.id
     
     banned_words = db.get_banned_words(chat_id, active_only=False)
     target_word = None
     
     for word_data in banned_words:
         if word_data['id'] == word_id:
             target_word = word_data
             break
     
     if not target_word:
         await query.edit_message_text("❌ Word not found!", parse_mode='Markdown')
         return
     
     new_status = not target_word['is_active']
     db.update_banned_word_status(word_id, new_status)
     
     await show_banned_words_menu_callback(query, context)

async def delete_word(query, context, data):
     """Delete a banned word"""
     word_id = int(data.replace("delete_word_", ""))
     chat_id = query.message.chat.id
     
     banned_words = db.get_banned_words(chat_id, active_only=False)
     target_word = None
     
     for word_data in banned_words:
         if word_data['id'] == word_id:
             target_word = word_data
             break
     
     if not target_word:
         await query.edit_message_text("❌ Word not found!", parse_mode='Markdown')
         return
     
     if db.delete_banned_word(word_id, chat_id):
         await query.edit_message_text(
             f"✅ **Word deleted successfully!**\n\n"
             f"📝 Word: `{target_word['word']}`\n"
             f"⚡ Action: {target_word['action'].title()}",
             parse_mode='Markdown'
         )
         await asyncio.sleep(2)
         await show_banned_words_menu_callback(query, context)
     else:
         await query.edit_message_text("❌ Failed to delete word!", parse_mode='Markdown')

async def handle_action_selection(query, context, data):
     """Handle action selection for new banned word"""
     action = data.replace("action_", "")
     word = context.user_data.get('pending_word', '')
     
     if not word:
         await query.edit_message_text("❌ No word pending!", parse_mode='Markdown')
         return
     
     chat_id = query.message.chat.id
     user_id = query.from_user.id
     username = query.from_user.username or query.from_user.first_name
     
     # Add the banned word
     word_id = db.add_banned_word(chat_id, word, action, user_id, username)
     
     action_emoji = "⚠️" if action == 'warn' else "🚫" if action == 'ban' else "🔇"
     
     await query.edit_message_text(
         f"✅ **Word banned successfully!**\n\n"
         f"📝 Word: `{word}`\n"
         f"⚡ Action: {action_emoji} {action.title()}\n"
         f"👤 Added by: @{username}",
         parse_mode='Markdown'
     )
     
     # Clear pending word
     context.user_data.pop('pending_word', None)
     
     await asyncio.sleep(2)
     await show_banned_words_menu_callback(query, context)

async def show_action_selection(query, context, word):
     """Show action selection for new banned word"""
     text = (
         f"🚫 **Add banned word: `{word}`**\n\n"
         "Choose what action to take when this word is used:"
     )
     
     keyboard = [
         [InlineKeyboardButton("⚠️ Warn", callback_data=f"action_warn")],
         [InlineKeyboardButton("🔇 Mute", callback_data=f"action_mute")],
         [InlineKeyboardButton("🚫 Ban", callback_data=f"action_ban")],
         [InlineKeyboardButton("🔙 Back", callback_data="add_banned_word")]
     ]
     
     reply_markup = InlineKeyboardMarkup(keyboard)
     await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
     """Handle incoming messages to check for banned words"""
     if not update.message or not update.message.text:
         return
     
     # Check if user is waiting for word input
     if context.user_data.get('waiting_for_word'):
         word = update.message.text.strip().lower()
         if len(word) > 50:
             await update.message.reply_text("❌ Word too long! Maximum 50 characters.", parse_mode='Markdown')
             return
         
         # Store the word and show action selection
         context.user_data['pending_word'] = word
         context.user_data.pop('waiting_for_word', None)
         
         # Create a mock query for the callback
         from telegram import CallbackQuery
         mock_query = type('MockQuery', (), {
             'edit_message_text': lambda text, **kwargs: update.message.reply_text(text, **kwargs),
             'from_user': update.effective_user,
             'message': update.message
         })()
         
         await show_action_selection(mock_query, context, word)
         return
     
     # Check if user is waiting for helper ID input
     if context.user_data.get('waiting_for_helper_id'):
         try:
             user_id = int(update.message.text.strip())
             
             # Try to get user info
             try:
                 chat_member = await context.bot.get_chat_member(update.effective_chat.id, user_id)
                 target_user = chat_member.user
                 username = target_user.username or target_user.first_name
                 
                 # Add the helper
                 admin_user = update.effective_user
                 admin_username = admin_user.username or admin_user.first_name
                 
                 helper_id = db.add_helper(update.effective_chat.id, user_id, username, admin_user.id, admin_username)
                 
                 await update.message.reply_text(
                     f"✅ **Helper added successfully!**\n\n"
                     f"👤 User: {target_user.first_name}"
                     f"{f' (@{target_user.username})' if target_user.username else ''}\n"
                     f"🆔 ID: `{user_id}`\n"
                     f"👮 Added by: @{admin_username}",
                     parse_mode='Markdown'
                 )
                 
             except Exception as e:
                 await update.message.reply_text(
                     f"❌ **Failed to add helper!**\n\n"
                     f"User with ID `{user_id}` not found in this group.\n"
                     f"Error: {str(e)}",
                     parse_mode='Markdown'
                 )
             
         except ValueError:
             await update.message.reply_text(
                 "❌ **Invalid user ID!**\n\n"
                 "Please send a valid numeric user ID.\n"
                 "**Example:** `123456789`",
                 parse_mode='Markdown'
             )
         
         # Clear the waiting state
         context.user_data.pop('waiting_for_helper_id', None)
         return
     
     # Check for banned words in the message
     chat_id = update.effective_chat.id
     user = update.effective_user
     message_text = update.message.text
     
     # Skip if user is admin
     if await is_admin(update, context):
         return
     
     # Check for banned words
     found_words = db.check_banned_words(chat_id, message_text)
     
     if found_words:
         # Take action based on the first found word's action
         action = found_words[0]['action']
         word = found_words[0]['word']
         
         # Delete the message
         try:
             await update.message.delete()
         except Exception:
             pass  # Message might already be deleted
         
         # Take action based on the word's action
         if action == 'warn':
             await context.bot.send_message(
                 chat_id=chat_id,
                 text=f"⚠️ **WARNING** ⚠️\n\n"
                      f"👤 User: {user.first_name}"
                      f"{f' (@{user.username})' if user.username else ''}\n"
                      f"🚫 Used banned word: `{word}`\n"
                      f"📝 Message: `{message_text[:100]}{'...' if len(message_text) > 100 else ''}`\n\n"
                      f"⚠️ Please avoid using banned words!",
                 parse_mode='Markdown'
             )
         elif action == 'mute':
             # Mute the user
             permissions = telegram.ChatPermissions(
                 can_send_messages=False,
                 can_send_media_messages=False,
                 can_send_other_messages=False,
                 can_add_web_page_previews=False
             )
             
             try:
                 await context.bot.restrict_chat_member(chat_id, user.id, permissions)
                 await context.bot.send_message(
                     chat_id=chat_id,
                     text=f"🔇 **USER MUTED** 🔇\n\n"
                          f"👤 User: {user.first_name}"
                          f"{f' (@{user.username})' if user.username else ''}\n"
                          f"🚫 Used banned word: `{word}`\n"
                          f"📝 Message: `{message_text[:100]}{'...' if len(message_text) > 100 else ''}`\n\n"
                          f"🔇 User has been muted for using banned word.",
                     parse_mode='Markdown'
                 )
             except Exception as e:
                 await context.bot.send_message(
                     chat_id=chat_id,
                     text=f"❌ Failed to mute user: {str(e)}",
                     parse_mode='Markdown'
                 )
         elif action == 'ban':
             # Ban the user
             try:
                 await context.bot.ban_chat_member(chat_id, user.id)
                 await context.bot.send_message(
                     chat_id=chat_id,
                     text=f"🚫 **USER BANNED** 🚫\n\n"
                          f"👤 User: {user.first_name}"
                          f"{f' (@{user.username})' if user.username else ''}\n"
                          f"🚫 Used banned word: `{word}`\n"
                          f"📝 Message: `{message_text[:100]}{'...' if len(message_text) > 100 else ''}`\n\n"
                          f"🚫 User has been banned for using banned word.",
                     parse_mode='Markdown'
                 )
             except Exception as e:
                 await context.bot.send_message(
                     chat_id=chat_id,
                     text=f"❌ Failed to ban user: {str(e)}",
                     parse_mode='Markdown'
                 )

# Helper management functions
async def helpers_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show the helpers management menu"""
    if not await is_admin(update, context):
        await update.message.reply_text(
            "❌ **KLAIDA**\n\n"
            "Tik grupės administratoriai gali naudoti šią komandą!",
            parse_mode='Markdown'
        )
        return
    
    chat_id = update.effective_chat.id
    current_time = datetime.now().strftime("%d/%m/%y %H:%M")
    
    # Get helpers for this chat
    helpers = db.get_helpers(chat_id, active_only=False)
    
    text = (
        "👥 **Helpers**\n\n"
        f"From this menu you can manage helpers who can use "
        f"ban and mute commands even if they are not group administrators.\n\n"
        f"Current time: {current_time}"
    )
    
    # Add helpers list if they exist
    if helpers:
        text += f"\n\n📋 **Helpers ({len(helpers)}):**"
        for i, helper_data in enumerate(helpers, 1):
            status = "✅ Active" if helper_data['is_active'] else "❌ Inactive"
            status_icon = "✅" if helper_data['is_active'] else "❌"
            
            text += f"\n\n**{i} • {status}** {status_icon}\n"
            text += f"   User: @{helper_data['username']}\n"
            text += f"   ID: `{helper_data['user_id']}`\n"
            text += f"   Added by: @{helper_data['added_by_username']}"
    
    keyboard = [
        [InlineKeyboardButton("➕ Add helper", callback_data="add_helper")]
    ]
    
    # Add helper management buttons for each existing helper
    if helpers:
        for i, helper_data in enumerate(helpers, 1):
            status_text = "❌ Inactive" if helper_data['is_active'] else "✅ Active"
            keyboard.append([
                InlineKeyboardButton(f"{i}", callback_data=f"helper_info_{helper_data['id']}"),
                InlineKeyboardButton(status_text, callback_data=f"toggle_helper_{helper_data['id']}"),
                InlineKeyboardButton("🗑️", callback_data=f"remove_helper_{helper_data['id']}")
            ])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def show_helpers_menu_callback(query, context):
    """Show helpers menu via callback"""
    chat_id = query.message.chat.id
    current_time = datetime.now().strftime("%d/%m/%y %H:%M")
    
    helpers = db.get_helpers(chat_id, active_only=False)
    
    text = (
        "👥 **Helpers**\n\n"
        f"From this menu you can manage helpers who can use "
        f"ban and mute commands even if they are not group administrators.\n\n"
        f"Current time: {current_time}"
    )
    
    if helpers:
        text += f"\n\n📋 **Helpers ({len(helpers)}):**"
        for i, helper_data in enumerate(helpers, 1):
            status = "✅ Active" if helper_data['is_active'] else "❌ Inactive"
            status_icon = "✅" if helper_data['is_active'] else "❌"
            
            text += f"\n\n**{i} • {status}** {status_icon}\n"
            text += f"   User: @{helper_data['username']}\n"
            text += f"   ID: `{helper_data['user_id']}`\n"
            text += f"   Added by: @{helper_data['added_by_username']}"
    
    keyboard = [
        [InlineKeyboardButton("➕ Add helper", callback_data="add_helper")]
    ]
    
    if helpers:
        for i, helper_data in enumerate(helpers, 1):
            status_text = "❌ Inactive" if helper_data['is_active'] else "✅ Active"
            keyboard.append([
                InlineKeyboardButton(f"{i}", callback_data=f"helper_info_{helper_data['id']}"),
                InlineKeyboardButton(status_text, callback_data=f"toggle_helper_{helper_data['id']}"),
                InlineKeyboardButton("🗑️", callback_data=f"remove_helper_{helper_data['id']}")
            ])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def show_add_helper(query, context):
    """Show add helper interface"""
    text = (
        "👥 **Add helper**\n\n"
        "Please send the user ID of the person you want to add as a helper.\n\n"
        "**How to get user ID:**\n"
        "• Ask the user to send /id command\n"
        "• Or use @userinfobot\n\n"
        "**Example:** `123456789`"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="helpers_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)
    # Set state to wait for user ID input
    context.user_data['waiting_for_helper_id'] = True

async def show_helper_info(query, context, data):
    """Show detailed information about a helper"""
    helper_id = int(data.replace("helper_info_", ""))
    chat_id = query.message.chat.id
    
    helpers = db.get_helpers(chat_id, active_only=False)
    target_helper = None
    
    for helper_data in helpers:
        if helper_data['id'] == helper_id:
            target_helper = helper_data
            break
    
    if not target_helper:
        await query.edit_message_text("❌ Helper not found!", parse_mode='Markdown')
        return
    
    status = "✅ Active" if target_helper['is_active'] else "❌ Inactive"
    
    text = (
        f"👥 **Helper #{helper_id} Details**\n\n"
        f"👤 User: @{target_helper['username']}\n"
        f"🆔 ID: `{target_helper['user_id']}`\n"
        f"📊 Status: {status}\n"
        f"👮 Added by: @{target_helper['added_by_username']}\n"
        f"📅 Added: {target_helper['added_at'][:19]}"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Manage", callback_data="helpers_menu")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, parse_mode='Markdown', reply_markup=reply_markup)

async def remove_helper(query, context, data):
    """Remove a helper"""
    helper_id = int(data.replace("remove_helper_", ""))
    chat_id = query.message.chat.id
    
    success = db.remove_helper(helper_id, chat_id)
    
    if success:
        await query.edit_message_text(
            "✅ **Helper removed successfully!**",
            parse_mode='Markdown'
        )
    else:
        await query.edit_message_text(
            "❌ **Failed to remove helper!**",
            parse_mode='Markdown'
        )
    
    await asyncio.sleep(2)
    await show_helpers_menu_callback(query, context)

async def banned_words_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
     """Show the banned words management menu"""
     if not await is_admin(update, context):
         await update.message.reply_text(
             "❌ **KLAIDA**\n\n"
             "Tik grupės administratoriai gali naudoti šią komandą!",
             parse_mode='Markdown'
         )
         return
     
     chat_id = update.effective_chat.id
     current_time = datetime.now().strftime("%d/%m/%y %H:%M")
     
     # Get banned words for this chat
     banned_words = db.get_banned_words(chat_id, active_only=False)
     
     text = (
         "🚫 **Banned words**\n\n"
         f"From this menu you can manage words that are banned "
         f"in this group. Users who use these words will be "
         f"automatically punished.\n\n"
         f"Current time: {current_time}"
     )
     
     # Add banned words list if they exist
     if banned_words:
         text += f"\n\n📋 **Banned words ({len(banned_words)}):**"
         for i, word_data in enumerate(banned_words, 1):
             status = "✅ Active" if word_data['is_active'] else "❌ Inactive"
             status_icon = "✅" if word_data['is_active'] else "❌"
             action_emoji = "⚠️" if word_data['action'] == 'warn' else "🚫" if word_data['action'] == 'ban' else "🔇"
             
             text += f"\n\n**{i} • {status}** {status_icon}\n"
             text += f"   Word: `{word_data['word']}`\n"
             text += f"   Action: {action_emoji} {word_data['action'].title()}\n"
             text += f"   Added by: @{word_data['created_by_username']}"
     
     keyboard = [
         [InlineKeyboardButton("➕ Add word", callback_data="add_banned_word")]
     ]
     
     # Add word management buttons for each existing word
     if banned_words:
         for i, word_data in enumerate(banned_words, 1):
             status_text = "❌ Inactive" if word_data['is_active'] else "✅ Active"
             keyboard.append([
                 InlineKeyboardButton(f"{i}", callback_data=f"word_info_{word_data['id']}"),
                 InlineKeyboardButton(status_text, callback_data=f"toggle_word_{word_data['id']}"),
                 InlineKeyboardButton("🗑️", callback_data=f"delete_word_{word_data['id']}")
             ])
     
     keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="main_menu")])
     
     reply_markup = InlineKeyboardMarkup(keyboard)
     
     await update.message.reply_text(
         text,
         parse_mode='Markdown',
         reply_markup=reply_markup
     )

async def list_schedules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List all scheduled messages for this chat"""
    if not await is_admin(update, context):
        await update.message.reply_text(
            "❌ **KLAIDA**\n\n"
            "Tik grupės administratoriai gali naudoti šią komandą!",
            parse_mode='Markdown'
        )
        return
    
    chat_id = update.effective_chat.id
    scheduled_messages = db.get_scheduled_messages(chat_id)
    
    if not scheduled_messages:
        await update.message.reply_text(
            "📋 **SUPLANUOTOS ŽINUTĖS** 📋\n\n"
            "Šioje grupėje nėra suplanuotų žinučių.\n\n"
            "Naudokite `/schedule` komandą žinutei suplanuoti.",
            parse_mode='Markdown'
        )
        return
    
    msg_text = "📋 **SUPLANUOTOS ŽINUTĖS** 📋\n\n"
    
    for i, msg in enumerate(scheduled_messages, 1):
        interval_str = format_interval(msg['interval_hours'], msg['interval_minutes'])
        status = "🟢 Aktyvus" if msg['is_active'] else "🔴 Neaktyvus"
        
        # Truncate message text for display
        display_text = msg['message_text'][:50]
        if len(msg['message_text']) > 50:
            display_text += "..."
        
        msg_text += f"**{i}. ID #{msg['id']}**\n"
        msg_text += f"📝 `{display_text}`\n"
        msg_text += f"⏰ Kas {interval_str}\n"
        msg_text += f"👤 @{msg['created_by_username']}\n"
        msg_text += f"📊 {status}\n"
        
        if msg['last_sent']:
            msg_text += f"📤 Paskutinį kartą: {msg['last_sent'][:19]}\n"
        
        msg_text += "\n"
    
    msg_text += "🗑️ Naudokite `/delete_schedule <ID>` žinutei ištrinti"
    
    await send_long_message(update, msg_text)

async def delete_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a scheduled message"""
    if not await is_admin(update, context):
        await update.message.reply_text(
            "❌ **KLAIDA**\n\n"
            "Tik grupės administratoriai gali naudoti šią komandą!",
            parse_mode='Markdown'
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ **KLAIDA**\n\n"
            "Nenurodėte žinutės ID!\n\n"
            "**Naudojimas:** `/delete_schedule <ID>`\n"
            "**Pavyzdys:** `/delete_schedule 1`\n\n"
            "Naudokite `/list_schedules` ID sąrašui peržiūrėti.",
            parse_mode='Markdown'
        )
        return
    
    try:
        message_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text(
            "❌ **KLAIDA**\n\n"
            "Neteisingas ID formatas! Turi būti skaičius.",
            parse_mode='Markdown'
        )
        return
    
    chat_id = update.effective_chat.id
    
    # Get message info before deletion to remove from scheduler
    scheduled_messages = db.get_scheduled_messages(chat_id, active_only=False)
    target_message = None
    
    for msg in scheduled_messages:
        if msg['id'] == message_id:
            target_message = msg
            break
    
    if not target_message:
        await update.message.reply_text(
            f"❌ **KLAIDA**\n\n"
            f"Žinutė su ID #{message_id} nerasta šioje grupėje.",
            parse_mode='Markdown'
        )
        return
    
    # Remove from scheduler
    try:
        scheduler.remove_job(target_message['job_id'])
    except Exception:
        pass  # Job might not exist in scheduler
    
    # Delete from database
    if db.delete_scheduled_message(message_id, chat_id):
        await update.message.reply_text(
            f"✅ **ŽINUTĖ IŠTRINTA** ✅\n\n"
            f"🆔 **ID:** #{message_id}\n"
            f"📝 **Žinutė:** `{target_message['message_text'][:100]}{'...' if len(target_message['message_text']) > 100 else ''}`\n\n"
            f"🗑️ Suplanuota žinutė sėkmingai ištrinta.",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "❌ **KLAIDA**\n\n"
            "Nepavyko ištrinti žinutės. Bandykite dar kartą.",
            parse_mode='Markdown'
        )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    welcome_text = """
🔍 **SCAMMER & BUYER CHECK BOT** 🔍

Šis botas leidžia patikrinti scamerius ir blogus pirkėjus:

📋 **KOMANDOS:**
• `/patikra username` - Patikrinti vartotoją
• `/scameris username` - Peržiūrėti scamer pranešimus  
• `/vagis username` - Peržiūrėti pirkėjų pranešimus
• `/stats` - Statistikos
• `/help` - Pagalba

🔄 **PAKARTOJAMOS ŽINUTĖS:**
• `/recurring` - Atidarti pakartojamų žinučių meniu (GroupHelpBot stilius)

🛡️ **MODERACIJA** (tik administratoriams):
• `/ban username/id [priežastis]` - Uždrausti vartotoją
• `/unban username/id` - Atkurti vartotoją
• `/mute username/id [priežastis]` - Nutildyti vartotoją
• `/unmute username/id` - Atkurti vartotojo teises
• `/bannedwords` - Uždraustų žodžių valdymas
• `/helpers` - Pagalbininkų valdymas

⚠️ **SVARBU:**
• Šis botas yra tik skaitymo režimu
• Duomenys sinchronizuojami su pagrindiniu botu
• Negalite pridėti naujų pranešimų per šį botą
• Pakartojamos žinutės ir moderacija - tik administratoriams

🛡️ Apsaugokite save nuo sukčių!
    """
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send help message"""
    help_text = """
🔍 **SCAMMER & BUYER CHECK BOT - PAGALBA** 

📋 **GALIMOS KOMANDOS:**

🔍 `/patikra username` 
   • Patikrinti ar vartotojas yra scamer arba blogas pirkėjas
   • Pavyzdys: `/patikra @username`

📊 `/scameris username`
   • Peržiūrėti visus scamer pranešimus apie vartotoją
   • Rodo kas pranešė ir kodėl

📊 `/vagis username` 
   • Peržiūrėti visus pirkėjų pranešimus apie vartotoją
   • Rodo pardavėjų skundus

📈 `/stats`
   • Peržiūrėti bendrą statistiką

🔄 **PAKARTOJAMOS ŽINUTĖS** (tik administratoriams):

📱 `/recurring`
   • Atidarti interaktyvų pakartojamų žinučių meniu
   • Pilnas GroupHelpBot funkcionalumas su inline klaviatūra
   • Konfigūruoti žinutes, laikus, pakartojimus ir daugiau

🛡️ **MODERACIJA** (tik administratoriams):

🚫 `/ban username/id [priežastis]`
   • Uždrausti vartotoją iš grupės
   • Pavyzdžiai: `/ban @username`, `/ban 123456789 Spam`

✅ `/unban username/id`
   • Atkurti uždraustą vartotoją
   • Pavyzdžiai: `/unban @username`, `/unban 123456789`

🔇 `/mute username/id [priežastis]`
   • Nutildyti vartotoją (negalės rašyti žinučių)
   • Pavyzdžiai: `/mute @username`, `/mute 123456789 Spam`

🔊 `/unmute username/id`
   • Atkurti vartotojo teises rašyti žinutes
   • Pavyzdžiai: `/unmute @username`, `/unmute 123456789`

🚫 `/bannedwords`
   • Uždraustų žodžių valdymas su inline meniu
   • Pridėti, pašalinti ir valdyti uždraustus žodžius
   • Automatinis žinučių tikrinimas ir baudimas

👥 `/helpers`
   • Pagalbininkų valdymas su inline meniu
   • Pridėti vartotojus, kurie gali naudoti ban/mute komandas
   • Pagalbininkai gali moderuoti net jei nėra administratoriai

⚠️ **PASTABOS:**
• Galite naudoti username su @ arba be @
• Botas ieško tiek pagal username, tiek pagal ID
• Duomenys atnaujinami realiu laiku
• Pakartojamos žinutės ir moderacija veiks tik administratoriams
• Priežastis yra neprivaloma - galite uždrausti/nutildyti be priežasties

🛡️ **SAUGUMAS:**
• Visada patikrinkite vartotojus prieš sandorius
• Nepasitikėkite nepažįstamais pardavėjais
• Naudokite saugius mokėjimo būdus
    """
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def patikra(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check if user is a scammer or bad buyer"""
    if not context.args:
        await update.message.reply_text(
            "❌ Nenurodėte vartotojo vardo!\n"
            "Naudojimas: `/patikra username`\n"
            "Pavyzdys: `/patikra @username`",
            parse_mode='Markdown'
        )
        return
    
    check_username = sanitize_username(context.args[0])
    
    if not check_username:
        await update.message.reply_text("❌ Neteisingas vartotojo vardas!")
        return
    
    # Check if user is a confirmed scammer
    scammer_info = db.get_scammer(check_username)
    if scammer_info:
        reports = scammer_info.get('reports', [])
        msg_text = f"🚨 **PATVIRTINTAS SCAMER** 🚨\n\n"
        msg_text += f"👤 Vartotojas: `{check_username}`\n"
        msg_text += f"📊 Pranešimų kiekis: **{len(reports)}**\n"
        msg_text += f"⚠️ **ATSARGIAI! Šis vartotojas yra patvirtintas scamer!**\n\n"
        msg_text += f"🛡️ Rekomenduojame vengti sandorių su šiuo vartotoju."
        
        await update.message.reply_text(msg_text, parse_mode='Markdown')
        return
    
    # Check if user is a confirmed bad buyer
    buyer_info = db.get_bad_buyer(check_username)
    if buyer_info:
        reports = buyer_info.get('reports', [])
        msg_text = f"⚠️ **BLOGAS PIRKĖJAS** ⚠️\n\n"
        msg_text += f"👤 Vartotojas: `{check_username}`\n"
        msg_text += f"📊 Pranešimų kiekis: **{len(reports)}**\n"
        msg_text += f"🛒 **Šis pirkėjas turi neigiamų atsiliepimų!**\n\n"
        msg_text += f"💡 Patartina būti atsargiems su šiuo pirkėju."
        
        await update.message.reply_text(msg_text, parse_mode='Markdown')
        return
    
    # Check by user ID if available
    user_id = db.get_user_id(check_username)
    if user_id:
        # Check scammers by ID
        scammer_by_id = db.find_scammer_by_user_id(user_id)
        if scammer_by_id:
            reports = scammer_by_id.get('reports', [])
            original_username = scammer_by_id.get('username', check_username)
            msg_text = f"🚨 **PATVIRTINTAS SCAMER** 🚨\n\n"
            msg_text += f"👤 Vartotojas: `{check_username}` (aka `{original_username}`)\n"
            msg_text += f"📊 Pranešimų kiekis: **{len(reports)}**\n"
            msg_text += f"⚠️ **ATSARGIAI! Šis vartotojas yra patvirtintas scamer!**\n\n"
            msg_text += f"🛡️ Rekomenduojame vengti sandorių su šiuo vartotoju."
            await update.message.reply_text(msg_text, parse_mode='Markdown')
            return
        
        # Check bad buyers by ID
        buyer_by_id = db.find_bad_buyer_by_user_id(user_id)
        if buyer_by_id:
            reports = buyer_by_id.get('reports', [])
            original_username = buyer_by_id.get('username', check_username)
            msg_text = f"⚠️ **BLOGAS PIRKĖJAS** ⚠️\n\n"
            msg_text += f"👤 Vartotojas: `{check_username}` (aka `{original_username}`)\n"
            msg_text += f"📊 Pranešimų kiekis: **{len(reports)}**\n"
            msg_text += f"🛒 **Šis pirkėjas turi neigiamų atsiliepimų!**\n\n"
            msg_text += f"💡 Patartina būti atsargiems su šiuo pirkėju."
            await update.message.reply_text(msg_text, parse_mode='Markdown')
            return
    
    # User is clean
    await update.message.reply_text(
        f"✅ **VARTOTOJAS ŠVARUS** ✅\n\n"
        f"👤 Vartotojas: `{check_username}`\n"
        f"🛡️ Nerasta jokių pranešimų apie šį vartotoją\n"
        f"💚 Galite saugiai bendrauti su šiuo vartotoju",
        parse_mode='Markdown'
    )

async def scameris_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View scammer reports for a user"""
    if not context.args:
        await update.message.reply_text(
            "❌ Nenurodėte vartotojo vardo!\n"
            "Naudojimas: `/scameris username`\n"
            "Pavyzdys: `/scameris @username`",
            parse_mode='Markdown'
        )
        return
    
    check_username = sanitize_username(context.args[0])
    
    if not check_username:
        await update.message.reply_text("❌ Neteisingas vartotojo vardas!")
        return
    
    scammer_info = None
    found_username = check_username
    
    # Direct username check
    scammer_info = db.get_scammer(check_username)
    if not scammer_info:
        # Check by user ID
        user_id = db.get_user_id(check_username)
        if user_id:
            scammer_info = db.find_scammer_by_user_id(user_id)
            if scammer_info:
                found_username = scammer_info.get('username', check_username)
    
    if not scammer_info:
        await update.message.reply_text(
            f"ℹ️ **PRANEŠIMŲ NERASTA**\n\n"
            f"👤 Vartotojas: `{check_username}`\n"
            f"📊 Nerasta jokių scamer pranešimų apie šį vartotoją",
            parse_mode='Markdown'
        )
        return
    
    reports = scammer_info.get('reports', [])
    msg_text = f"🚨 **SCAMER PRANEŠIMAI** 🚨\n\n"
    msg_text += f"👤 Vartotojas: `{found_username}`\n"
    msg_text += f"📊 Pranešimų kiekis: **{len(reports)}**\n\n"
    
    if scammer_info.get('user_id'):
        msg_text += f"🆔 User ID: `{scammer_info['user_id']}`\n\n"
    
    msg_text += "📋 **PRANEŠIMŲ SĄRAŠAS:**\n"
    
    for i, report in enumerate(reports, 1):
        reporter = report.get('reporter', 'Nežinomas')
        reason = report.get('reason', 'Nenurodyta')
        timestamp = report.get('timestamp', 'Nežinoma data')
        
        msg_text += f"\n**{i}.** 👤 `{reporter}`\n"
        msg_text += f"   📅 {timestamp}\n"
        msg_text += f"   📝 {reason}\n"
    
    # Split message if too long
    await send_long_message(update, msg_text)

async def vagis_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View buyer reports for a user"""
    if not context.args:
        await update.message.reply_text(
            "❌ Nenurodėte vartotojo vardo!\n"
            "Naudojimas: `/vagis username`\n"
            "Pavyzdys: `/vagis @username`",
            parse_mode='Markdown'
        )
        return
    
    check_username = sanitize_username(context.args[0])
    
    if not check_username:
        await update.message.reply_text("❌ Neteisingas vartotojo vardas!")
        return
    
    buyer_info = None
    found_username = check_username
    
    # Direct username check
    buyer_info = db.get_bad_buyer(check_username)
    if not buyer_info:
        # Check by user ID
        user_id = db.get_user_id(check_username)
        if user_id:
            buyer_info = db.find_bad_buyer_by_user_id(user_id)
            if buyer_info:
                found_username = buyer_info.get('username', check_username)
    
    if not buyer_info:
        await update.message.reply_text(
            f"ℹ️ **PRANEŠIMŲ NERASTA**\n\n"
            f"👤 Vartotojas: `{check_username}`\n"
            f"📊 Nerasta jokių pirkėjų pranešimų apie šį vartotoją",
            parse_mode='Markdown'
        )
        return
    
    reports = buyer_info.get('reports', [])
    msg_text = f"🛒 **PIRKĖJŲ PRANEŠIMAI** 🛒\n\n"
    msg_text += f"👤 Vartotojas: `{found_username}`\n"
    msg_text += f"📊 Pranešimų kiekis: **{len(reports)}**\n\n"
    
    if buyer_info.get('user_id'):
        msg_text += f"🆔 User ID: `{buyer_info['user_id']}`\n\n"
    
    msg_text += "📋 **PRANEŠIMŲ SĄRAŠAS:**\n"
    
    for i, report in enumerate(reports, 1):
        reporter = report.get('reporter', 'Nežinomas')
        reason = report.get('reason', 'Nenurodyta')
        timestamp = report.get('timestamp', 'Nežinoma data')
        
        msg_text += f"\n**{i}.** 👤 `{reporter}`\n"
        msg_text += f"   📅 {timestamp}\n"
        msg_text += f"   📝 {reason}\n"
    
    # Split message if too long
    await send_long_message(update, msg_text)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show statistics about scammers and bad buyers"""
    stats_data = db.get_statistics()
    
    msg_text = f"📊 **STATISTIKOS** 📊\n\n"
    msg_text += f"🚨 **SCAMERIAI:**\n"
    msg_text += f"   • Patvirtinti scameriai: **{stats_data['total_scammers']}**\n"
    msg_text += f"   • Viso pranešimų: **{stats_data['total_scammer_reports']}**\n\n"
    msg_text += f"🛒 **BLOGI PIRKĖJAI:**\n"
    msg_text += f"   • Patvirtinti blogi pirkėjai: **{stats_data['total_bad_buyers']}**\n"
    msg_text += f"   • Viso pranešimų: **{stats_data['total_buyer_reports']}**\n\n"
    msg_text += f"🛡️ **BENDRA INFORMACIJA:**\n"
    msg_text += f"   • Viso problematiškų vartotojų: **{stats_data['total_scammers'] + stats_data['total_bad_buyers']}**\n"
    msg_text += f"   • Viso pranešimų: **{stats_data['total_scammer_reports'] + stats_data['total_buyer_reports']}**\n\n"
    msg_text += f"⚠️ Visada patikrinkite vartotojus prieš sandorius!"
    
    await update.message.reply_text(msg_text, parse_mode='Markdown')

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ban a user from the group"""
    if not await can_ban_users(update, context):
        await update.message.reply_text(
            "❌ **KLAIDA**\n\n"
            "Jūs neturite teisių uždrausti vartotojų šioje grupėje!",
            parse_mode='Markdown'
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ **KLAIDA**\n\n"
            "Nenurodėte vartotojo!\n\n"
            "**Naudojimas:** `/ban username/id [priežastis]`\n"
            "**Pavyzdžiai:**\n"
            "• `/ban @username`\n"
            "• `/ban 123456789`\n"
            "• `/ban @username Spam`\n"
            "• `/ban 123456789 Įžeidžiantis elgesys`",
            parse_mode='Markdown'
        )
        return
    
    # Get target user
    target = context.args[0]
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Nenurodyta priežastis"
    
    chat_id = update.effective_chat.id
    admin_user = update.effective_user
    
    try:
        # Try to get user by username or ID
        if target.startswith('@'):
            username = target[1:]  # Remove @
            # Try to get user by username
            try:
                chat_member = await context.bot.get_chat_member(chat_id, username)
                target_user = chat_member.user
            except:
                await update.message.reply_text(
                    f"❌ **KLAIDA**\n\n"
                    f"Vartotojas `{target}` nerastas grupėje!",
                    parse_mode='Markdown'
                )
                return
        else:
            # Try to get user by ID
            try:
                user_id = int(target)
                chat_member = await context.bot.get_chat_member(chat_id, user_id)
                target_user = chat_member.user
            except ValueError:
                await update.message.reply_text(
                    f"❌ **KLAIDA**\n\n"
                    f"Neteisingas vartotojo ID formatas: `{target}`",
                    parse_mode='Markdown'
                )
                return
            except:
                await update.message.reply_text(
                    f"❌ **KLAIDA**\n\n"
                    f"Vartotojas su ID `{target}` nerastas grupėje!",
                    parse_mode='Markdown'
                )
                return
        
        # Check if target is admin/creator
        if chat_member.status in ['creator', 'administrator']:
            await update.message.reply_text(
                f"❌ **KLAIDA**\n\n"
                f"Negalite uždrausti administratoriaus ar grupės savininko!",
                parse_mode='Markdown'
            )
            return
        
        # Ban the user
        await context.bot.ban_chat_member(chat_id, target_user.id)
        
        # Delete all messages from the banned user
        try:
            # Get recent messages from the user (Telegram API limitation: can only delete recent messages)
            # We'll try to delete messages from the last 1000 messages in the chat
            messages_deleted = 0
            async for message in context.bot.get_chat_history(chat_id, limit=1000):
                if message.from_user and message.from_user.id == target_user.id:
                    try:
                        await context.bot.delete_message(chat_id, message.message_id)
                        messages_deleted += 1
                    except Exception:
                        # Skip messages that can't be deleted (too old, etc.)
                        continue
        except Exception as e:
            logger.warning(f"Could not delete all messages from banned user {target_user.id}: {e}")
        
        # Success message
        ban_text = f"🚫 **VARTOTOJA UŽBANINTAS** 🚫\n\n"
        ban_text += f"👤 **Vartotojas:** {target_user.first_name}"
        if target_user.username:
            ban_text += f" (@{target_user.username})"
        ban_text += f"\n🆔 **ID:** `{target_user.id}`\n"
        ban_text += f"👮 **Uždraudė:** {admin_user.first_name}"
        if admin_user.username:
            ban_text += f" (@{admin_user.username})"
        ban_text += f"\n📝 **Priežastis:** {reason}\n"
        ban_text += f"🗑️ **Ištrinti pranešimai:** {messages_deleted}\n"
        ban_text += f"⏰ **Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        await update.message.reply_text(ban_text, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ **KLAIDA**\n\n"
            f"Nepavyko uždrausti vartotojo: {str(e)}",
            parse_mode='Markdown'
        )

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mute a user in the group"""
    if not await can_mute_users(update, context):
        await update.message.reply_text(
            "❌ **KLAIDA**\n\n"
            "Jūs neturite teisių nutildyti vartotojų šioje grupėje!",
            parse_mode='Markdown'
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ **KLAIDA**\n\n"
            "Nenurodėte vartotojo!\n\n"
            "**Naudojimas:** `/mute username/id [priežastis]`\n"
            "**Pavyzdžiai:**\n"
            "• `/mute @username`\n"
            "• `/mute 123456789`\n"
            "• `/mute @username Spam`\n"
            "• `/mute 123456789 Įžeidžiantis elgesys`",
            parse_mode='Markdown'
        )
        return
    
    # Get target user
    target = context.args[0]
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "Nenurodyta priežastis"
    
    chat_id = update.effective_chat.id
    admin_user = update.effective_user
    
    try:
        # Try to get user by username or ID
        if target.startswith('@'):
            username = target[1:]  # Remove @
            # Try to get user by username
            try:
                chat_member = await context.bot.get_chat_member(chat_id, username)
                target_user = chat_member.user
            except:
                await update.message.reply_text(
                    f"❌ **KLAIDA**\n\n"
                    f"Vartotojas `{target}` nerastas grupėje!",
                    parse_mode='Markdown'
                )
                return
        else:
            # Try to get user by ID
            try:
                user_id = int(target)
                chat_member = await context.bot.get_chat_member(chat_id, user_id)
                target_user = chat_member.user
            except ValueError:
                await update.message.reply_text(
                    f"❌ **KLAIDA**\n\n"
                    f"Neteisingas vartotojo ID formatas: `{target}`",
                    parse_mode='Markdown'
                )
                return
            except:
                await update.message.reply_text(
                    f"❌ **KLAIDA**\n\n"
                    f"Vartotojas su ID `{target}` nerastas grupėje!",
                    parse_mode='Markdown'
                )
                return
        
        # Check if target is admin/creator
        if chat_member.status in ['creator', 'administrator']:
            await update.message.reply_text(
                f"❌ **KLAIDA**\n\n"
                f"Negalite nutildyti administratoriaus ar grupės savininko!",
                parse_mode='Markdown'
            )
            return
        
        # Mute the user (restrict permissions)
        permissions = telegram.ChatPermissions(
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False
        )
        
        await context.bot.restrict_chat_member(chat_id, target_user.id, permissions)
        
        # Success message
        mute_text = f"🔇 **VARTOTOJAS NUTILDYTAS** 🔇\n\n"
        mute_text += f"👤 **Vartotojas:** {target_user.first_name}"
        if target_user.username:
            mute_text += f" (@{target_user.username})"
        mute_text += f"\n🆔 **ID:** `{target_user.id}`\n"
        mute_text += f"👮 **Nutildė:** {admin_user.first_name}"
        if admin_user.username:
            mute_text += f" (@{admin_user.username})"
        mute_text += f"\n📝 **Priežastis:** {reason}\n"
        mute_text += f"⏰ **Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        await update.message.reply_text(mute_text, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ **KLAIDA**\n\n"
            f"Nepavyko nutildyti vartotojo: {str(e)}",
            parse_mode='Markdown'
        )

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unmute a user in the group"""
    if not await can_mute_users(update, context):
        await update.message.reply_text(
            "❌ **KLAIDA**\n\n"
            "Jūs neturite teisių atkurti vartotojų teises šioje grupėje!",
            parse_mode='Markdown'
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ **KLAIDA**\n\n"
            "Nenurodėte vartotojo!\n\n"
            "**Naudojimas:** `/unmute username/id`\n"
            "**Pavyzdžiai:**\n"
            "• `/unmute @username`\n"
            "• `/unmute 123456789`",
            parse_mode='Markdown'
        )
        return
    
    # Get target user
    target = context.args[0]
    
    chat_id = update.effective_chat.id
    admin_user = update.effective_user
    
    try:
        # Try to get user by username or ID
        if target.startswith('@'):
            username = target[1:]  # Remove @
            # Try to get user by username
            try:
                chat_member = await context.bot.get_chat_member(chat_id, username)
                target_user = chat_member.user
            except:
                await update.message.reply_text(
                    f"❌ **KLAIDA**\n\n"
                    f"Vartotojas `{target}` nerastas grupėje!",
                    parse_mode='Markdown'
                )
                return
        else:
            # Try to get user by ID
            try:
                user_id = int(target)
                chat_member = await context.bot.get_chat_member(chat_id, user_id)
                target_user = chat_member.user
            except ValueError:
                await update.message.reply_text(
                    f"❌ **KLAIDA**\n\n"
                    f"Neteisingas vartotojo ID formatas: `{target}`",
                    parse_mode='Markdown'
                )
                return
            except:
                await update.message.reply_text(
                    f"❌ **KLAIDA**\n\n"
                    f"Vartotojas su ID `{target}` nerastas grupėje!",
                    parse_mode='Markdown'
                )
                return
        
        # Unmute the user (restore permissions)
        permissions = telegram.ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True
        )
        
        await context.bot.restrict_chat_member(chat_id, target_user.id, permissions)
        
        # Success message
        unmute_text = f"🔊 **VARTOTOJO TEISĖS ATKURTOS** 🔊\n\n"
        unmute_text += f"👤 **Vartotojas:** {target_user.first_name}"
        if target_user.username:
            unmute_text += f" (@{target_user.username})"
        unmute_text += f"\n🆔 **ID:** `{target_user.id}`\n"
        unmute_text += f"👮 **Atkūrė:** {admin_user.first_name}"
        if admin_user.username:
            unmute_text += f" (@{admin_user.username})"
        unmute_text += f"\n⏰ **Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        await update.message.reply_text(unmute_text, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ **KLAIDA**\n\n"
            f"Nepavyko atkurti vartotojo teisių: {str(e)}",
            parse_mode='Markdown'
        )

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unban a user from the group"""
    if not await can_ban_users(update, context):
        await update.message.reply_text(
            "❌ **KLAIDA**\n\n"
            "Jūs neturite teisių atkurti vartotojų šioje grupėje!",
            parse_mode='Markdown'
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ **KLAIDA**\n\n"
            "Nenurodėte vartotojo!\n\n"
            "**Naudojimas:** `/unban username/id`\n"
            "**Pavyzdžiai:**\n"
            "• `/unban @username`\n"
            "• `/unban 123456789`",
            parse_mode='Markdown'
        )
        return
    
    # Get target user
    target = context.args[0]
    
    chat_id = update.effective_chat.id
    admin_user = update.effective_user
    
    try:
        # Try to get user by username or ID
        if target.startswith('@'):
            username = target[1:]  # Remove @
            # Try to get user by username
            try:
                chat_member = await context.bot.get_chat_member(chat_id, username)
                target_user = chat_member.user
            except:
                await update.message.reply_text(
                    f"❌ **KLAIDA**\n\n"
                    f"Vartotojas `{target}` nerastas grupėje!",
                    parse_mode='Markdown'
                )
                return
        else:
            # Try to get user by ID
            try:
                user_id = int(target)
                chat_member = await context.bot.get_chat_member(chat_id, user_id)
                target_user = chat_member.user
            except ValueError:
                await update.message.reply_text(
                    f"❌ **KLAIDA**\n\n"
                    f"Neteisingas vartotojo ID formatas: `{target}`",
                    parse_mode='Markdown'
                )
                return
            except:
                await update.message.reply_text(
                    f"❌ **KLAIDA**\n\n"
                    f"Vartotojas su ID `{target}` nerastas grupėje!",
                    parse_mode='Markdown'
                )
                return
        
        # Unban the user
        await context.bot.unban_chat_member(chat_id, target_user.id)
        
        # Success message
        unban_text = f"✅ **VARTOTOJAS ATKURTAS** ✅\n\n"
        unban_text += f"👤 **Vartotojas:** {target_user.first_name}"
        if target_user.username:
            unban_text += f" (@{target_user.username})"
        unban_text += f"\n🆔 **ID:** `{target_user.id}`\n"
        unban_text += f"👮 **Atkūrė:** {admin_user.first_name}"
        if admin_user.username:
            unban_text += f" (@{admin_user.username})"
        unban_text += f"\n⏰ **Data:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        await update.message.reply_text(unban_text, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ **KLAIDA**\n\n"
            f"Nepavyko atkurti vartotojo: {str(e)}",
            parse_mode='Markdown'
        )

async def send_long_message(update: Update, text: str):
    """Send long message by splitting it into chunks"""
    if len(text) <= 4000:
        await update.message.reply_text(text, parse_mode='Markdown')
        return
    
    # Split message if too long
    lines = text.split('\n')
    current_chunk = ""
    
    for line in lines:
        if len(current_chunk + line + '\n') > 4000:
            await update.message.reply_text(current_chunk, parse_mode='Markdown')
            current_chunk = line + '\n'
        else:
            current_chunk += line + '\n'
    
    if current_chunk:
        await update.message.reply_text(current_chunk, parse_mode='Markdown')

async def restore_scheduled_jobs():
    """Restore scheduled jobs from database on startup"""
    try:
        scheduled_messages = db.get_all_active_scheduled_messages()
        
        for msg in scheduled_messages:
            try:
                scheduler.add_job(
                    send_scheduled_message,
                    IntervalTrigger(hours=msg['interval_hours'], minutes=msg['interval_minutes']),
                    args=[msg['chat_id'], msg['message_text'], msg['job_id']],
                    id=msg['job_id'],
                    replace_existing=True
                )
                logger.info(f"Restored scheduled job: {msg['job_id']}")
            except Exception as e:
                logger.error(f"Failed to restore job {msg['job_id']}: {e}")
                
        logger.info(f"Restored {len(scheduled_messages)} scheduled jobs")
    except Exception as e:
        logger.error(f"Error restoring scheduled jobs: {e}")

async def periodic_sync():
    """Periodically sync data from main bot"""
    while True:
        try:
            await sync_data_from_main_bot()
            await asyncio.sleep(300)  # Sync every 5 minutes
        except Exception as e:
            logger.error(f"Error in periodic sync: {e}")
            await asyncio.sleep(60)  # Wait 1 minute on error

def main() -> None:
    """Start the bot."""
    global application_instance
    
    if not BOT_TOKEN:
        logger.error("❌ ERROR: BOT_TOKEN environment variable not set!")
        logger.error("Please set BOT_TOKEN in your environment variables")
        return
    
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()
    application_instance = application  # Set global reference for scheduler

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("patikra", patikra))
    application.add_handler(CommandHandler("scameris", scameris_check))
    application.add_handler(CommandHandler("vagis", vagis_check))
    application.add_handler(CommandHandler("stats", stats))
    
    # Add moderation command handlers
    application.add_handler(CommandHandler("ban", ban_user))
    application.add_handler(CommandHandler("unban", unban_user))
    application.add_handler(CommandHandler("mute", mute_user))
    application.add_handler(CommandHandler("unmute", unmute_user))
    
         # Add recurring messages command handler
     application.add_handler(CommandHandler("recurring", recurring_messages_menu))
     application.add_handler(CallbackQueryHandler(handle_callback_query))
     
     # Add banned words command handler
     application.add_handler(CommandHandler("bannedwords", banned_words_menu))
     
     # Add helpers command handler
     application.add_handler(CommandHandler("helpers", helpers_menu))
     
     # Add message handler for banned words checking
     from telegram.ext import MessageHandler, filters
     application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Keep old commands for backward compatibility
    application.add_handler(CommandHandler("schedule", list_schedules))  # Redirect to list
    application.add_handler(CommandHandler("list_schedules", list_schedules))
    application.add_handler(CommandHandler("delete_schedule", delete_schedule))

    # Log that the bot is starting
    logger.info("Read-Only Scammer Check Bot with Scheduling is starting...")
    
    # Start the scheduler
    scheduler.start()
    logger.info("Scheduler started")
    
    # Restore scheduled jobs from database
    asyncio.create_task(restore_scheduled_jobs())
    
    # Start periodic sync task
    if MAIN_BOT_API_URL:
        asyncio.create_task(periodic_sync())
        logger.info("Periodic data sync enabled")

    # Run the bot until the user presses Ctrl-C
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    finally:
        # Shutdown scheduler gracefully
        scheduler.shutdown()
        logger.info("Scheduler stopped")

if __name__ == '__main__':
    main()
