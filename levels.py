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
        
        # GTA SAN ANDREAS HUD STYLE - DARK BACKGROUND LIKE PATCH
        width, height = 1080, 1920
        
        # Very dark background like the patch (almost black)
        img = Image.new('RGB', (width, height), color='#0A0A0A')
        draw = ImageDraw.Draw(img)
        
        # Load GTA SA style fonts - try Pricedown first, fallback to bold
        import os
        money_font = None
        label_font = None
        
        # Try Pricedown font (iconic GTA font) for money display
        pricedown_paths = [
            ("C:/Windows/Fonts/pricedown bl.ttf", "Pricedown"),
            ("C:/Windows/Fonts/PRICEDOW.TTF", "Pricedown"),
            ("/usr/share/fonts/truetype/pricedown/pricedown.ttf", "Pricedown"),
        ]
        
        for font_path, font_name in pricedown_paths:
            try:
                if os.path.exists(font_path):
                    money_font = ImageFont.truetype(font_path, 140)  # Large for money
                    label_font = ImageFont.truetype(font_path, 45)   # Small for labels
                    logger.info(f"Loaded GTA font: {font_name}")
                    break
            except:
                continue
        
        # Fallback to bold Arial if Pricedown not found
        if not money_font:
            try:
                money_font = ImageFont.truetype("arialbd.ttf", 140)
                label_font = ImageFont.truetype("arialbd.ttf", 45)
            except:
                try:
                    money_font = ImageFont.truetype("arial.ttf", 140)
                    label_font = ImageFont.truetype("arial.ttf", 45)
                except:
                    money_font = ImageFont.load_default()
                    label_font = ImageFont.load_default()
        
        # Helper function to apply pixelation effect to image
        def pixelate_image(image, scale_factor=0.5):
            """Apply pixelation effect by scaling down and back up"""
            w, h = image.size
            small = image.resize((int(w * scale_factor), int(h * scale_factor)), Image.Resampling.NEAREST)
            pixelated = small.resize((w, h), Image.Resampling.NEAREST)
            return pixelated
        
        # Helper function to draw text with thick black outline (GTA SA style)
        def draw_outlined_text(text, position, font, fill_color, outline_color='#000000', outline_width=4, anchor=None):
            x, y = position
            kwargs = {'font': font}
            if anchor:
                kwargs['anchor'] = anchor
            
            # Draw outline by drawing text multiple times at offsets
            for adj in range(-outline_width, outline_width + 1):
                for adj2 in range(-outline_width, outline_width + 1):
                    if adj != 0 or adj2 != 0:
                        draw.text((x + adj, y + adj2), text, fill=outline_color, **kwargs)
            # Draw main text on top
            draw.text(position, text, fill=fill_color, **kwargs)
        
        # GTA SAN ANDREAS HUD - CLEAN MINIMAL VERSION (MONEY + STARS ONLY)
        # ❌ No profile icon, no progress bars, no time display
        # ✅ Only money counter and star row
        
        # Calculate how many stars to fill based on level
        total_stars = 5
        filled_stars = min((level - 1) // 2 + 1, 5)  # Fill more stars as level increases
        
        # Right-aligned positioning (anchor from right edge)
        money_x = width - 100  # 100px from right edge
        money_y = 150  # 150px from top
        
        # 1. MONEY/POINTS DISPLAY - Dark GTA Green with thick black outline
        points_text = f"${current_points:08d}"
        
        # Use dark GTA green color from reference
        gta_green = '#36682C'  # Authentic GTA SA money color
        
        # Draw money text with thick black outline (right-aligned)
        draw_outlined_text(points_text, (money_x, money_y), 
                         money_font, gta_green, outline_width=7, anchor='rm')
        
        # 2. STARS - Row of 5 stars below money (right-aligned)
        stars_y = money_y + 110
        star_size = 85
        star_spacing = 95
        
        # Calculate starting position for right-alignment
        total_star_width = (total_stars - 1) * star_spacing
        first_star_x = money_x - total_star_width
        
        # Draw 5 stars
        for i in range(total_stars):
            star_x_pos = first_star_x + (i * star_spacing)
            
            # Determine star color based on progress
            if i < filled_stars:
                star_color = '#FFD700'  # Gold/Yellow for filled
            else:
                star_color = '#3E3E3E'  # Dark grey for empty
            
            # Draw blocky star with thick outline
            draw_outlined_text("★", (star_x_pos, stars_y), 
                             money_font, star_color, outline_width=5, anchor='mm')
        
        # Apply retro pixelation effect to entire image (lighter effect to preserve details)
        img = pixelate_image(img, scale_factor=0.75)  # Less aggressive pixelation
        
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

