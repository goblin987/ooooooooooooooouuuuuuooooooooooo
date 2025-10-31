#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Leveling System - Points and Level Progression
Users earn points through activities, not gambling
"""

import logging
import math
from telegram import Update
from telegram.ext import ContextTypes
from database import database
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Points Rewards Configuration (displayed as "points" to users)
XP_REWARDS = {
    'message': 5,           # Per message (with cooldown)
    'vote': 50,            # Voting for seller
    'scammer_report': 100, # Reporting scammer
}

# Cooldown for message points (seconds)
MESSAGE_XP_COOLDOWN = 60  # 1 minute between message points gains

# Level calculation formula
def calculate_level(xp: int) -> int:
    """Calculate level from points using exponential formula"""
    # Level = floor(0.1 * sqrt(points))
    # This creates a nice curve: 
    # Level 1 = 100 points, Level 2 = 400 points, Level 3 = 900 points, Level 10 = 10,000 points
    if xp <= 0:
        return 1
    level = int(0.1 * math.sqrt(xp)) + 1
    return max(1, level)


def calculate_xp_for_level(level: int) -> int:
    """Calculate points needed for a specific level"""
    # Inverse of level formula: points = (level * 10)^2
    if level <= 1:
        return 0
    return ((level - 1) * 10) ** 2


def get_xp_to_next_level(current_xp: int) -> tuple:
    """
    Get current level, points for current level, and points needed for next level
    Returns: (current_level, points_for_current, points_for_next, progress_percentage)
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
    Add points to user and return level info
    Returns: dict with old_level, new_level, leveled_up, current_xp
    """
    try:
        # Get current points (stored in points column)
        current_xp = get_user_xp(user_id)
        old_level = calculate_level(current_xp)
        
        # Add points
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
            logger.info(f"User {user_id} gained {amount} points from {reason}. Level: {old_level} → {new_level}")
        
        return {
            'old_level': old_level,
            'new_level': new_level,
            'leveled_up': leveled_up,
            'current_xp': new_xp,
            'xp_gained': amount
        }
    except Exception as e:
        logger.error(f"Error adding points to user {user_id}: {e}")
        return None


def get_user_xp(user_id: int) -> int:
    """Get user's current points"""
    try:
        conn = database.get_sync_connection()
        cursor = conn.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0
    except Exception as e:
        logger.error(f"Error getting points for user {user_id}: {e}")
        return 0


# Message points tracking (in-memory cache for cooldowns)
last_message_xp = {}

def can_gain_message_xp(user_id: int) -> bool:
    """Check if user can gain points from messaging (cooldown check)"""
    if user_id not in last_message_xp:
        return True
    
    last_time = last_message_xp[user_id]
    return (datetime.now() - last_time).total_seconds() >= MESSAGE_XP_COOLDOWN


def grant_message_xp(user_id: int):
    """Grant points for sending a message (with cooldown)"""
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


async def get_leaderboard_position(user_id: int) -> int:
    """Get user's position on the leaderboard"""
    try:
        conn = database.get_sync_connection()
        cursor = conn.execute("""
            SELECT COUNT(*) + 1 as position
            FROM users
            WHERE points > (SELECT points FROM users WHERE user_id = ?)
        """, (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 1
    except:
        return 1


async def points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's level and progress with modern image card"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    first_name = update.effective_user.first_name
    
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageFilter
        from io import BytesIO
        import requests
        import os
        
        # Get user stats
        current_points = get_user_xp(user_id)
        level, points_in_level, points_needed, progress = get_xp_to_next_level(current_points)
        rank_title = get_rank_title(level)
        leaderboard_pos = await get_leaderboard_position(user_id)
        
        # Get next rank
        next_rank_level = None
        for req_level in sorted(LEVEL_RANKS.keys()):
            if req_level > level:
                next_rank_level = req_level
                break
        next_rank = LEVEL_RANKS.get(next_rank_level, "👑 Max Rank") if next_rank_level else "👑 Max Rank"
        
        # Create FULL SCREEN modern Apple-like card (1080x1920 - full phone)
        width, height = 1080, 1920
        
        # Apple-like blurred background (dark)
        img = Image.new('RGB', (width, height), color='#0f172a')
        draw = ImageDraw.Draw(img)
        
        # Subtle gradient
        for y in range(height):
            ratio = y / height
            r = int(15 + (25 - 15) * ratio)
            g = int(23 + (35 - 23) * ratio)
            b = int(42 + (52 - 42) * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b))
        
        # Load fonts - MUCH BIGGER to fill screen
        try:
            title_font = ImageFont.truetype("arial.ttf", 75)          # "Your Stats" title - BIGGER
            name_font = ImageFont.truetype("arialbd.ttf", 95)          # Username (bold) - MUCH BIGGER
            info_font = ImageFont.truetype("arial.ttf", 62)            # Info labels - BIGGER
            level_font = ImageFont.truetype("arialbd.ttf", 85)        # Level number - ALMOST SAME AS USERNAME
            points_font = ImageFont.truetype("arialbd.ttf", 80)       # Points text - ALMOST SAME AS USERNAME
        except:
            try:
                title_font = ImageFont.truetype("arial.ttf", 75)
                name_font = ImageFont.truetype("arial.ttf", 95)
                info_font = ImageFont.truetype("arial.ttf", 62)
                level_font = ImageFont.truetype("arial.ttf", 85)
                points_font = ImageFont.truetype("arial.ttf", 80)
            except:
                title_font = ImageFont.load_default()
                name_font = ImageFont.load_default()
                info_font = ImageFont.load_default()
                level_font = ImageFont.load_default()
                points_font = ImageFont.load_default()
        
        # Get user profile photo
        profile_pic = None
        try:
            photos = await context.bot.get_user_profile_photos(user_id, limit=1)
            if photos.total_count > 0:
                file = await context.bot.get_file(photos.photos[0][-1].file_id)
                photo_bytes = await file.download_as_bytearray()
                profile_pic = Image.open(BytesIO(photo_bytes))
                logger.info(f"Successfully loaded profile photo for user {user_id}")
        except Exception as e:
            logger.warning(f"Could not get profile photo: {e}")
        
        # APPLE-LIKE MODERN LAYOUT - FILL SCREEN
        
        # Title at top - "Your Stats" - BIGGER
        title_y = 80
        draw.text((width//2, title_y), "Your Stats", fill='#60a5fa', anchor='mm', font=title_font)
        
        # Main card - dark grey-blue, Apple-like - USE MORE SPACE
        card_margin = 40
        card_x = card_margin
        card_y = 180
        card_width = width - card_margin * 2
        card_height = height - card_y - 80
        
        # Draw main card with subtle shadow effect
        draw.rounded_rectangle([card_x, card_y, card_x + card_width, card_y + card_height],
                              radius=28, fill='#1e293b')
        
        # LEFT SIDE - Profile Picture - MUCH BIGGER
        pic_size = 320
        pic_x = card_x + 60
        pic_y = card_y + 80
        
        if profile_pic:
            # Resize and make circular
            profile_pic = profile_pic.resize((pic_size, pic_size), Image.Resampling.LANCZOS)
            
            # Create circular mask
            mask = Image.new('L', (pic_size, pic_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse([0, 0, pic_size, pic_size], fill=255)
            
            # Paste circular profile pic (no border for cleaner look)
            output = Image.new('RGBA', (pic_size, pic_size), (0, 0, 0, 0))
            output.paste(profile_pic, (0, 0))
            img.paste(output, (pic_x, pic_y), mask)
        else:
            # Draw default avatar circle
            draw.ellipse([pic_x, pic_y, pic_x + pic_size, pic_y + pic_size], 
                        fill='#334155')
            
            # Draw user initial
            initial = first_name[0].upper() if first_name else "?"
            draw.text((pic_x + pic_size//2, pic_y + pic_size//2), initial, 
                     fill='#ffffff', anchor='mm', font=level_font)
        
        # RIGHT SIDE - All info LEFT-ALIGNED (not centered) - BIGGER SPACING
        info_x = pic_x + pic_size + 60
        info_start_y = card_y + 80
        
        current_y = info_start_y
        
        # Username - HUGE bold white (left-aligned)
        draw.text((info_x, current_y), first_name, fill='#ffffff', anchor='lt', font=name_font)
        current_y += 110
        
        # Leaderboard - Green - BIGGER
        draw.text((info_x, current_y), f"Leaderboard: #{leaderboard_pos}", 
                 fill='#34d399', anchor='lt', font=info_font)
        current_y += 80
        
        # Rank - Yellow (no badge, just text) - BIGGER
        draw.text((info_x, current_y), f"Rank: {rank_title}", 
                 fill='#fbbf24', anchor='lt', font=info_font)
        current_y += 90
        
        # Level - White - ALMOST SAME SIZE AS USERNAME
        draw.text((info_x, current_y), f"Level: {level}", 
                 fill='#ffffff', anchor='lt', font=level_font)
        current_y += 100
        
        # Points Progress - White - ALMOST SAME SIZE AS USERNAME
        draw.text((info_x, current_y), f"{points_in_level:,} / {points_needed:,} Points", 
                 fill='#ffffff', anchor='lt', font=points_font)
        current_y += 100
        
        # Progress bar - MUCH THICKER - Light blue (Apple-like)
        bar_width = card_x + card_width - info_x - 60
        bar_height = 60  # MUCH THICKER!
        bar_x = info_x
        bar_y = current_y
        
        # Background bar - dark grey
        draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height],
                              radius=30, fill='#334155')
        
        # Filled bar - light blue (Apple accent color)
        filled_width = int((progress / 100) * bar_width)
        if filled_width > 12:
            draw.rounded_rectangle([bar_x, bar_y, bar_x + filled_width, bar_y + bar_height],
                                  radius=30, fill='#60a5fa')
        
        current_y = bar_y + bar_height + 80
        
        # Next rank - Light blue - BIGGER
        draw.text((info_x, current_y), f"Next: {next_rank}", 
                 fill='#60a5fa', anchor='lt', font=info_font)
        
        # Save to bytes
        bio = BytesIO()
        bio.name = 'stats.png'
        img.save(bio, 'PNG', quality=95)
        bio.seek(0)
        
        # Send image with minimal caption
        caption = (
            f"<b>Earn Points:</b>\n"
            f"💬 Chat +{XP_REWARDS['message']} • 🗳️ Vote +{XP_REWARDS['vote']} • 🚨 Report +{XP_REWARDS['scammer_report']}"
        )
        
        await update.message.reply_photo(photo=bio, caption=caption, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error in points command: {e}", exc_info=True)
        # Fallback to text
        current_points = get_user_xp(user_id)
        level, points_in_level, points_needed, progress = get_xp_to_next_level(current_points)
        rank_title = get_rank_title(level)
        
        bar_length = 10
        filled = int(progress / 10)
        bar = "▰" * filled + "▱" * (bar_length - filled)
        
        message = f"📊 <b>{username}</b>\n\n"
        message += f"{rank_title}\n"
        message += f"<b>Level {level}</b>\n\n"
        message += f"{bar} {progress:.1f}%\n"
        message += f"{points_in_level:,} / {points_needed:,} points\n\n"
        message += "<i>Kaip gauti points:</i>\n"
        message += f"💬 Rašyti: +{XP_REWARDS['message']}\n"
        message += f"🗳️ Balsuoti: +{XP_REWARDS['vote']}\n"
        message += f"🚨 Pranešti: +{XP_REWARDS['scammer_report']}"
        
        await update.message.reply_text(message, parse_mode='HTML')


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

