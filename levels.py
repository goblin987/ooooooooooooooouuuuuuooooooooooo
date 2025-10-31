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
        
        # Create epic card (1200x1600 for better proportions)
        width, height = 1200, 1600
        
        # Create vibrant gradient background
        img = Image.new('RGB', (width, height), color='#1c1c1e')
        draw = ImageDraw.Draw(img)
        
        # Draw vibrant gradient background (purple to cyan)
        for y in range(height):
            # Epic gradient: dark purple -> bright purple -> cyan
            ratio = y / height
            if ratio < 0.5:
                # Purple section
                r = int(75 + (139 - 75) * (ratio * 2))
                g = int(0 + (92 - 0) * (ratio * 2))
                b = int(130 + (246 - 130) * (ratio * 2))
            else:
                # Cyan section
                r = int(139 + (34 - 139) * ((ratio - 0.5) * 2))
                g = int(92 + (211 - 92) * ((ratio - 0.5) * 2))
                b = int(246 + (238 - 246) * ((ratio - 0.5) * 2))
            draw.line([(0, y), (width, y)], fill=(r, g, b))
        
        # Try to load fonts (BIGGER sizes)
        try:
            name_font = ImageFont.truetype("arial.ttf", 110)  # Bigger!
            rank_font = ImageFont.truetype("arial.ttf", 60)
            level_font = ImageFont.truetype("arial.ttf", 200)  # Massive!
            label_font = ImageFont.truetype("arial.ttf", 50)
            stats_font = ImageFont.truetype("arial.ttf", 65)   # Bigger!
            small_font = ImageFont.truetype("arial.ttf", 45)
        except:
            name_font = ImageFont.load_default()
            rank_font = ImageFont.load_default()
            level_font = ImageFont.load_default()
            label_font = ImageFont.load_default()
            stats_font = ImageFont.load_default()
            small_font = ImageFont.load_default()
        
        # Get user profile photo
        profile_pic = None
        try:
            photos = await context.bot.get_user_profile_photos(user_id, limit=1)
            if photos.total_count > 0:
                file = await context.bot.get_file(photos.photos[0][-1].file_id)
                photo_bytes = await file.download_as_bytearray()
                profile_pic = Image.open(BytesIO(photo_bytes))
        except Exception as e:
            logger.debug(f"Could not get profile photo: {e}")
        
        # Draw profile picture (circular, top center) - BIGGER
        pic_size = 240
        pic_x = (width - pic_size) // 2
        pic_y = 100
        
        if profile_pic:
            # Resize and crop to circle
            profile_pic = profile_pic.resize((pic_size, pic_size), Image.Resampling.LANCZOS)
            
            # Create circular mask
            mask = Image.new('L', (pic_size, pic_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse([0, 0, pic_size, pic_size], fill=255)
            
            # Create white border circle
            border_size = pic_size + 8
            border_x = pic_x - 4
            border_y = pic_y - 4
            draw.ellipse([border_x, border_y, border_x + border_size, border_y + border_size], 
                        fill='#ffffff', outline='#ffffff', width=4)
            
            # Paste circular profile pic
            img.paste(profile_pic, (pic_x, pic_y), mask)
        else:
            # Draw default avatar circle
            draw.ellipse([pic_x, pic_y, pic_x + pic_size, pic_y + pic_size], 
                        fill='#48484a', outline='#ffffff', width=4)
            # Draw user initial
            initial = first_name[0].upper() if first_name else "?"
            draw.text((pic_x + pic_size//2, pic_y + pic_size//2), initial, 
                     fill='#ffffff', anchor='mm', font=level_font)
        
        # Draw name (below profile pic) - MASSIVE
        name_y = pic_y + pic_size + 60
        
        # Add shadow effect to name
        shadow_offset = 4
        draw.text((width//2 + shadow_offset, name_y + shadow_offset), first_name, 
                 fill='#00000060', anchor='mm', font=name_font)
        draw.text((width//2, name_y), first_name, fill='#ffffff', anchor='mm', font=name_font)
        
        # Draw rank badge (pill-shaped) - BIGGER
        rank_y = name_y + 100
        rank_text = rank_title
        
        # Draw glowing badge background
        badge_padding = 40
        bbox = draw.textbbox((0, 0), rank_text, font=rank_font)
        badge_width = bbox[2] - bbox[0] + badge_padding * 2
        badge_height = 80
        badge_x = (width - badge_width) // 2
        badge_y = rank_y - badge_height // 2
        
        # Glow effect
        draw.rounded_rectangle([badge_x - 4, badge_y - 4, badge_x + badge_width + 4, badge_y + badge_height + 4],
                              radius=40, fill='#ffd60a40')
        draw.rounded_rectangle([badge_x, badge_y, badge_x + badge_width, badge_y + badge_height],
                              radius=35, fill='#ffd60a')
        draw.text((width//2, rank_y), rank_text, fill='#1c1c1e', anchor='mm', font=rank_font)
        
        # Draw level (HUGE and bold)
        level_y = rank_y + 150
        draw.text((width//2, level_y - 30), "LEVEL", fill='#ffffff', anchor='mm', font=label_font)
        
        # Shadow for level number
        draw.text((width//2 + 6, level_y + 90 + 6), str(level), fill='#00000060', anchor='mm', font=level_font)
        draw.text((width//2, level_y + 90), str(level), fill='#ffffff', anchor='mm', font=level_font)
        
        # Draw EPIC progress section
        card_y = level_y + 300
        card_padding = 80
        card_width = width - card_padding * 2
        card_height = 400
        card_x = card_padding
        
        # Glowing card background
        draw.rounded_rectangle([card_x - 4, card_y - 4, card_x + card_width + 4, card_y + card_height + 4],
                              radius=40, fill='#ffffff30')
        draw.rounded_rectangle([card_x, card_y, card_x + card_width, card_y + card_height],
                              radius=35, fill='#ffffff25')
        
        # "POINTS" label
        draw.text((width//2, card_y + 60), "POINTS", fill='#ffffff', anchor='mm', font=label_font)
        
        # Points numbers (BIG and BOLD)
        points_y = card_y + 140
        draw.text((width//2, points_y), f"{points_in_level:,}", fill='#06ffa5', anchor='mm', font=stats_font)
        draw.text((width//2, points_y + 70), f"/ {points_needed:,}", fill='#ffffff80', anchor='mm', font=small_font)
        
        # Progress bar (MUCH BIGGER and more visible)
        bar_padding = 50
        bar_x = card_x + bar_padding
        bar_y = card_y + 250
        bar_width = card_width - bar_padding * 2
        bar_height = 40  # Much thicker!
        
        # Background bar with border
        draw.rounded_rectangle([bar_x - 2, bar_y - 2, bar_x + bar_width + 2, bar_y + bar_height + 2],
                              radius=22, fill='#ffffff40')
        draw.rounded_rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height],
                              radius=20, fill='#1c1c1e')
        
        # Filled bar (glowing effect)
        filled_width = int((progress / 100) * bar_width)
        if filled_width > 16:  # Only draw if there's enough space for rounded corners
            # Glow
            draw.rounded_rectangle([bar_x - 2, bar_y - 2, bar_x + filled_width + 2, bar_y + bar_height + 2],
                                  radius=22, fill='#06ffa560')
            # Fill
            draw.rounded_rectangle([bar_x, bar_y, bar_x + filled_width, bar_y + bar_height],
                                  radius=20, fill='#06ffa5')
        
        # Progress percentage
        progress_text = f"{progress:.0f}%"
        draw.text((width//2, bar_y + bar_height + 60), progress_text, 
                 fill='#ffffff', anchor='mm', font=stats_font)
        
        # Next rank with icon
        draw.text((width//2, height - 300), f"Next Rank: {next_rank}", 
                 fill='#ffd60a', anchor='mm', font=small_font)
        
        # Leaderboard position (bottom) - BIGGER
        draw.text((width//2, height - 180), f"#{leaderboard_pos}", fill='#ffd60a', anchor='mm', font=level_font)
        draw.text((width//2, height - 80), "ON LEADERBOARD", fill='#ffffff', anchor='mm', font=label_font)
        
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

