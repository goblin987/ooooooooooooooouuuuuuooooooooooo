#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Leveling System - XP and Level Progression
"""

import logging
import math
from telegram import Update
from telegram.ext import ContextTypes
from database import database
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# XP Rewards Configuration
XP_REWARDS = {
    'message': 5,           # Per message (with cooldown)
    'vote': 50,            # Voting for seller
    'scammer_report': 100, # Reporting scammer
    'dice2_win': 30,       # Winning dice2
    'dice2_play': 10,      # Playing dice2 (participation)
}

# Cooldown for message XP (seconds)
MESSAGE_XP_COOLDOWN = 60  # 1 minute between message XP gains

# Level calculation formula
def calculate_level(xp: int) -> int:
    """Calculate level from XP using exponential formula"""
    # Level = floor(0.1 * sqrt(XP))
    # This creates a nice curve: 
    # Level 1 = 100 XP, Level 2 = 400 XP, Level 3 = 900 XP, Level 10 = 10,000 XP
    if xp <= 0:
        return 1
    level = int(0.1 * math.sqrt(xp)) + 1
    return max(1, level)


def calculate_xp_for_level(level: int) -> int:
    """Calculate XP needed for a specific level"""
    # Inverse of level formula: XP = (level * 10)^2
    if level <= 1:
        return 0
    return ((level - 1) * 10) ** 2


def get_xp_to_next_level(current_xp: int) -> tuple:
    """
    Get current level, XP for current level, and XP needed for next level
    Returns: (current_level, xp_for_current, xp_for_next, progress_percentage)
    """
    current_level = calculate_level(current_xp)
    xp_for_current = calculate_xp_for_level(current_level)
    xp_for_next = calculate_xp_for_level(current_level + 1)
    
    xp_in_level = current_xp - xp_for_current
    xp_needed = xp_for_next - xp_for_current
    
    progress = (xp_in_level / xp_needed * 100) if xp_needed > 0 else 100
    
    return current_level, xp_in_level, xp_needed, progress


def add_xp(user_id: int, amount: int, reason: str = None) -> dict:
    """
    Add XP to user and return level info
    Returns: dict with old_level, new_level, leveled_up, current_xp
    """
    try:
        # Get current XP (stored in points column)
        current_xp = get_user_xp(user_id)
        old_level = calculate_level(current_xp)
        
        # Add XP
        new_xp = current_xp + amount
        
        # Update in database
        conn = database.get_sync_connection()
        conn.execute("""
            INSERT INTO users (user_id, points) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET points = ?
        """, (user_id, new_xp, new_xp))
        conn.commit()
        conn.close()
        
        new_level = calculate_level(new_xp)
        leveled_up = new_level > old_level
        
        if reason:
            logger.info(f"User {user_id} gained {amount} XP from {reason}. Level: {old_level} → {new_level}")
        
        return {
            'old_level': old_level,
            'new_level': new_level,
            'leveled_up': leveled_up,
            'current_xp': new_xp,
            'xp_gained': amount
        }
    except Exception as e:
        logger.error(f"Error adding XP to user {user_id}: {e}")
        return None


def get_user_xp(user_id: int) -> int:
    """Get user's current XP"""
    try:
        conn = database.get_sync_connection()
        cursor = conn.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0
    except Exception as e:
        logger.error(f"Error getting XP for user {user_id}: {e}")
        return 0


# Message XP tracking (in-memory cache for cooldowns)
last_message_xp = {}

def can_gain_message_xp(user_id: int) -> bool:
    """Check if user can gain XP from messaging (cooldown check)"""
    if user_id not in last_message_xp:
        return True
    
    last_time = last_message_xp[user_id]
    return (datetime.now() - last_time).total_seconds() >= MESSAGE_XP_COOLDOWN


def grant_message_xp(user_id: int):
    """Grant XP for sending a message (with cooldown)"""
    if can_gain_message_xp(user_id):
        result = add_xp(user_id, XP_REWARDS['message'], 'message')
        last_message_xp[user_id] = datetime.now()
        return result
    return None


# Level rank titles
LEVEL_RANKS = {
    1: "🥚 Naujokas",
    5: "🐣 Pradedantis",
    10: "🐥 Aktyvus",
    20: "🦅 Veteranas",
    30: "⭐ Ekspertas",
    40: "💎 Legenda",
    50: "👑 Dievas",
}

def get_rank_title(level: int) -> str:
    """Get rank title for level"""
    for req_level in sorted(LEVEL_RANKS.keys(), reverse=True):
        if level >= req_level:
            return LEVEL_RANKS[req_level]
    return LEVEL_RANKS[1]


async def points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's XP, level, and progress"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    try:
        # Get user XP
        current_xp = get_user_xp(user_id)
        level, xp_in_level, xp_needed, progress = get_xp_to_next_level(current_xp)
        rank = get_rank_title(level)
        
        # Create progress bar
        bar_length = 10
        filled = int(progress / 10)
        bar = "▰" * filled + "▱" * (bar_length - filled)
        
        # Build message
        message = f"📊 <b>{username}</b>\n\n"
        message += f"{rank}\n"
        message += f"<b>Level {level}</b>\n\n"
        message += f"{bar} {progress:.1f}%\n"
        message += f"{xp_in_level:,} / {xp_needed:,} XP\n\n"
        message += f"<b>Total XP:</b> {current_xp:,}\n\n"
        message += "<i>Kaip gauti XP:</i>\n"
        message += f"💬 Rašyti žinutes: +{XP_REWARDS['message']} XP\n"
        message += f"🗳️ Balsuoti: +{XP_REWARDS['vote']} XP\n"
        message += f"🚨 Pranešti vagį: +{XP_REWARDS['scammer_report']} XP\n"
        message += f"🎲 Žaisti dice2: +{XP_REWARDS['dice2_play']}-{XP_REWARDS['dice2_win']} XP"
        
        await update.message.reply_text(message, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error in points command: {e}", exc_info=True)
        await update.message.reply_text("❌ Klaida gaunant informaciją")


# Export
__all__ = [
    'add_xp',
    'get_user_xp',
    'grant_message_xp',
    'calculate_level',
    'get_xp_to_next_level',
    'get_rank_title',
    'points_command',
    'XP_REWARDS'
]

