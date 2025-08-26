#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utility functions and shared components for OGbotas
"""

import re
import html
import logging
import pickle
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional, List
from collections import defaultdict
from datetime import datetime
import telegram
from config import DATA_DIR, PICKLE_FILES, DELETE_TIMEOUTS

logger = logging.getLogger(__name__)

class SecurityValidator:
    """Input validation and sanitization"""
    
    @staticmethod
    def sanitize_text(text: str) -> str:
        """Sanitize text input"""
        if not text:
            return ""
        
        # Remove null bytes and control characters
        text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)
        
        # HTML escape
        text = html.escape(text)
        
        # Limit length
        return text[:4000]  # Telegram message limit
    
    @staticmethod
    def validate_username(username: str) -> bool:
        """Validate username format"""
        if not username:
            return False
        
        # Remove @ if present
        username = username.lstrip('@')
        
        # Check format: 5-32 characters, alphanumeric + underscores
        return bool(re.match(r'^[a-zA-Z0-9_]{5,32}$', username))
    
    @staticmethod
    def validate_user_id(user_id: str) -> Optional[int]:
        """Validate and convert user ID"""
        try:
            uid = int(user_id)
            return uid if uid > 0 else None
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def sanitize_username(username: str) -> str:
        """Sanitize username input"""
        if not username:
            return ""
        
        # Remove @ and clean
        username = username.lstrip('@').strip()
        
        # Only allow valid characters
        username = re.sub(r'[^a-zA-Z0-9_]', '', username)
        
        return username[:32]  # Telegram username limit

class MessageTracker:
    """Track messages with automatic cleanup"""
    
    def __init__(self, max_age_minutes: int = 60):
        self.messages = defaultdict(list)
        self.max_age_minutes = max_age_minutes
    
    def add_message(self, chat_id: int, message_id: int):
        """Add message to tracking"""
        now = datetime.now()
        self.messages[chat_id].append((message_id, now))
        self._cleanup_old_messages(chat_id)
    
    def get_messages(self, chat_id: int) -> List[int]:
        """Get tracked messages for chat"""
        self._cleanup_old_messages(chat_id)
        return [msg_id for msg_id, _ in self.messages[chat_id]]
    
    def _cleanup_old_messages(self, chat_id: int):
        """Remove old messages from tracking"""
        now = datetime.now()
        cutoff = now.timestamp() - (self.max_age_minutes * 60)
        
        self.messages[chat_id] = [
            (msg_id, timestamp) for msg_id, timestamp in self.messages[chat_id]
            if timestamp.timestamp() > cutoff
        ]

class DataManager:
    """Manage pickle data files"""
    
    def __init__(self, data_dir: str = None):
        self.data_dir = Path(data_dir or DATA_DIR)
        self.data_dir.mkdir(parents=True, exist_ok=True)
    
    def load_data(self, filename: str, default_value=None):
        """Load data from pickle file"""
        try:
            file_path = self.data_dir / filename
            if file_path.exists():
                with open(file_path, 'rb') as f:
                    data = pickle.load(f)
                logger.debug(f"Loaded {len(data) if hasattr(data, '__len__') else 'data'} items from {filename}")
                return data
        except Exception as e:
            logger.warning(f"Error loading {filename}: {e}")
        
        return default_value if default_value is not None else {}
    
    def save_data(self, data: Any, filename: str):
        """Save data to pickle file"""
        try:
            file_path = self.data_dir / filename
            with open(file_path, 'wb') as f:
                pickle.dump(data, f)
            logger.debug(f"Saved data to {filename}")
        except Exception as e:
            logger.error(f"Error saving {filename}: {e}")
    
    async def atomic_operation(self, operation_key: str):
        """Provide atomic operation context"""
        # Simple implementation - could be enhanced with proper locking
        class AtomicContext:
            def __init__(self, key):
                self.key = key
            
            async def __aenter__(self):
                return self
            
            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass
        
        return AtomicContext(operation_key)

def sanitize_username(username: str) -> str:
    """Legacy function wrapper"""
    return SecurityValidator.sanitize_username(username)

def validate_amount(amount_str: str) -> tuple[bool, int]:
    """Validate amount for games"""
    try:
        amount = int(amount_str)
        return True, amount
    except (ValueError, TypeError):
        return False, 0

def parse_interval(interval_str: str) -> float:
    """Parse interval string to hours (converts minutes to fractional hours)"""
    try:
        if not interval_str:
            return 24
            
        # Handle new minute formats
        if 'minutes' in interval_str:
            if '1 minutes' in interval_str:
                return 1/60  # 1 minute = 1/60 hour
            elif '2 minutes' in interval_str:
                return 2/60
            elif '3 minutes' in interval_str:
                return 3/60
            elif '5 minutes' in interval_str:
                return 5/60
            elif '10 minutes' in interval_str:
                return 10/60
            elif '15 minutes' in interval_str:
                return 15/60
            elif '20 minutes' in interval_str:
                return 20/60
            elif '30 minutes' in interval_str:
                return 30/60
                
        # Handle hour formats
        if 'hours' in interval_str:
            if '1 hours' in interval_str:
                return 1
            elif '2 hours' in interval_str:
                return 2
            elif '3 hours' in interval_str:
                return 3
            elif '4 hours' in interval_str:
                return 4
            elif '6 hours' in interval_str:
                return 6
            elif '8 hours' in interval_str:
                return 8
            elif '12 hours' in interval_str:
                return 12
            elif '24 hours' in interval_str:
                return 24
                
        # Handle "Every X hours" format (legacy)
        if 'Every' in interval_str:
            if '12 hours' in interval_str:
                return 12
            elif '6 hours' in interval_str:
                return 6
            elif '3 hours' in interval_str:
                return 3
            elif '1 hour' in interval_str:
                return 1
            elif '24 hours' in interval_str:
                return 24
            elif 'hour' in interval_str and '24' not in interval_str:
                return 1
                
        # Handle simple formats
        if 'h' in interval_str:
            return int(interval_str.replace('h', ''))
        elif 'd' in interval_str:
            return int(interval_str.replace('d', '')) * 24
        else:
            return int(interval_str)
    except:
        return 24

async def safe_bot_operation(operation, *args, **kwargs):
    """Safely execute bot operation with error handling"""
    try:
        return await operation(*args, **kwargs)
    except telegram.error.RetryAfter as e:
        logger.warning(f"Rate limited, waiting {e.retry_after} seconds")
        await asyncio.sleep(e.retry_after)
        return await operation(*args, **kwargs)
    except telegram.error.TelegramError as e:
        logger.error(f"Telegram error in {operation.__name__}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error in {operation.__name__}: {e}")
        return None

async def delete_message_job(context):
    """Job to delete a message after delay"""
    chat_id, message_id = context.job.data
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.debug(f"Deleted message {message_id} in chat {chat_id}")
    except telegram.error.TelegramError as e:
        logger.debug(f"Could not delete message {message_id}: {e}")

def format_interval(hours: float, minutes: int = 0) -> str:
    """Format hours and minutes to readable string"""
    if hours == 0 and minutes == 0:
        return "Not set"
    
    if hours < 1:
        # Convert fractional hours to minutes
        total_minutes = int(hours * 60) + minutes
        return f"{total_minutes} minutes"
    elif hours == int(hours):
        # Whole hours
        h = int(hours)
        if minutes > 0:
            return f"{h} hours {minutes} minutes"
        else:
            return f"{h} hour{'s' if h != 1 else ''}"
    else:
        # Fractional hours
        return f"{hours:.1f} hours"

# Global instances
data_manager = DataManager()
message_tracker = MessageTracker()
security_validator = SecurityValidator()
