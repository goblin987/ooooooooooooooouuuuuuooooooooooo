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
        
        # GTA SAN ANDREAS HUD STYLE - SQUARE EMBROIDERED PATCH
        width, height = 800, 800  # Square like the patch
        
        # Dark black background like patch fabric
        img = Image.new('RGB', (width, height), color='#1A1A1A')
        draw = ImageDraw.Draw(img)
        
        # Very subtle texture variation for fabric look
        for y in range(height):
            darkness = int(y / height * 8)  # Much more subtle
            color = (26 - darkness, 26 - darkness, 26 - darkness)
            draw.line([(0, y), (width, y)], fill=color)
        
        # Add stitched border like an embroidered patch
        border_width = 8
        border_color = '#333333'
        draw.rectangle([0, 0, width, height], outline=border_color, width=border_width)
        
        # Load GTA SA style fonts - try Pricedown first, fallback to bold
        import os
        money_font = None
        label_font = None
        font_path_used = None
        
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
                    label_font = ImageFont.truetype(font_path, 90)   # Large for stars (1:1 with patch)
                    font_path_used = font_path
                    logger.info(f"Loaded GTA font: {font_name}")
                    break
            except:
                continue
        
        # Fallback to system fonts if Pricedown not found
        if not money_font:
            fallback_fonts = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",  # Linux
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",  # Linux
                "C:/Windows/Fonts/arialbd.ttf",  # Windows
                "C:/Windows/Fonts/arial.ttf",  # Windows
                "/System/Library/Fonts/Helvetica.ttc",  # macOS
            ]
            
            for font_path in fallback_fonts:
                try:
                    if os.path.exists(font_path):
                        money_font = ImageFont.truetype(font_path, 140)
                        label_font = ImageFont.truetype(font_path, 90)
                        font_path_used = font_path
                        logger.info(f"Loaded fallback font: {font_path}")
                        break
                except:
                    continue
            
            # Ultimate fallback
            if not money_font:
                money_font = ImageFont.load_default()
                label_font = ImageFont.load_default()
                font_path_used = None
                logger.warning("Using default font")
        
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
        
        # GTA SAN ANDREAS HUD - COMPLETE 1:1 REPLICA
        # All 6 elements from patch: weapon box, time, 2 bars, money, stars
        
        # Get user profile photo for weapon icon
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
        
        # Layout positioning - compact square patch layout
        hud_x = 40
        hud_y = 40
        icon_size = 160  # Slightly smaller for square format
        
        # 1. WEAPON ICON BOX (Top-Left)
        icon_x = hud_x
        icon_y = hud_y
        
        # White border, black fill
        border_width = 5
        draw.rectangle([icon_x - border_width, icon_y - border_width, 
                       icon_x + icon_size + border_width, icon_y + icon_size + border_width], 
                      fill='#FFFFFF')
        draw.rectangle([icon_x, icon_y, icon_x + icon_size, icon_y + icon_size], 
                      fill='#000000')
        
        # Insert profile picture or weapon graphic
        if profile_pic:
            # Heavy pixelation for retro look
            profile_pic_small = profile_pic.resize((45, 45), Image.Resampling.NEAREST)
            profile_pic_pixelated = profile_pic_small.resize((icon_size - 15, icon_size - 15), Image.Resampling.NEAREST)
            img.paste(profile_pic_pixelated, (icon_x + 8, icon_y + 8))
        else:
            # Simple weapon shape in light grey
            gun_y = icon_y + 50
            draw.rectangle([icon_x + 75, gun_y, icon_x + 165, gun_y + 18], fill='#DDDDDD', outline='#000000', width=2)
            draw.rectangle([icon_x + 35, gun_y + 12, icon_x + 80, gun_y + 55], fill='#DDDDDD', outline='#000000', width=2)
            draw.polygon([(icon_x + 55, gun_y + 55), (icon_x + 65, gun_y + 55), 
                         (icon_x + 70, gun_y + 95), (icon_x + 50, gun_y + 95)], 
                         fill='#DDDDDD', outline='#000000')
        
        # Ammo count below weapon (level-points_in_level)
        ammo_text = f"{level}-{points_in_level}"
        if font_path_used:
            try:
                ammo_font = ImageFont.truetype(font_path_used, 35)
            except:
                ammo_font = label_font
        else:
            ammo_font = label_font
        draw_outlined_text(ammo_text, (icon_x + icon_size//2, icon_y + icon_size + 12), 
                         ammo_font, '#FFFFFF', outline_width=2, anchor='mm')
        
        # 2. TIME DISPLAY (Top-Right)
        time_text = "04:20"
        time_x = icon_x + icon_size + 80
        time_y = icon_y
        # Draw time with smaller font
        if font_path_used:
            try:
                time_font = ImageFont.truetype(font_path_used, 85)
            except:
                time_font = label_font
        else:
            time_font = label_font
        draw_outlined_text(time_text, (time_x, time_y), 
                         time_font, '#FFFFFF', outline_width=4)
        
        # 3. WHITE/GREY BAR (Middle-Right, below time)
        bar_x = icon_x + icon_size + 30
        bar_y = icon_y + 65
        bar_width = 380  # Shorter for square format
        bar_height = 32
        
        # Black outline
        draw.rectangle([bar_x - 4, bar_y - 4, bar_x + bar_width + 4, bar_y + bar_height + 4], 
                     fill='#000000')
        # Very dark background
        draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], 
                     fill='#0A0A0A')
        # Light grey fill (75% full, static)
        white_fill = int(bar_width * 0.75)
        draw.rectangle([bar_x, bar_y, bar_x + white_fill, bar_y + bar_height], 
                      fill='#D0D0D0')
        
        # 4. RED BAR (Below white bar)
        bar2_y = bar_y + bar_height + 8
        
        # Black outline
        draw.rectangle([bar_x - 4, bar2_y - 4, bar_x + bar_width + 4, bar2_y + bar_height + 4], 
                     fill='#000000')
        # Very dark background
        draw.rectangle([bar_x, bar2_y, bar_x + bar_width, bar2_y + bar_height], 
                     fill='#0A0A0A')
        # Bright red fill (dynamic based on level progress)
        filled_width = int((progress / 100) * bar_width)
        if filled_width < 12:
            filled_width = max(12, int(bar_width * 0.05))
        draw.rectangle([bar_x, bar2_y, bar_x + filled_width, bar2_y + bar_height], 
                      fill='#DD0000')
        
        # PROMINENT RED SEPARATOR BAR (Full width like the patch)
        separator_y = bar2_y + bar_height + 25
        separator_height = 18
        separator_margin = 60
        draw.rectangle([separator_margin, separator_y, width - separator_margin, separator_y + separator_height], 
                      fill='#DD0000', outline='#000000', width=2)
        
        # 5. MONEY TEXT (Below red separator) - FULL WIDTH CENTERED
        money_y = bar2_y + bar_height + 50
        points_text = f"${current_points:08d}"
        
        # Bright lime green (GTA SA money color) - centered on patch
        if font_path_used:
            try:
                money_font_size = ImageFont.truetype(font_path_used, 100)
            except:
                money_font_size = money_font
        else:
            money_font_size = money_font
        draw_outlined_text(points_text, (width//2 - 190, money_y), 
                         money_font_size, '#00FF00', outline_width=4)
        
        # 6. STARS (Below money - 6 total: 3 grey + 3 gold) - CENTERED
        stars_y = money_y + 120
        star_spacing = 70
        total_stars = 6
        
        # Center the stars on the patch
        total_star_width = (total_stars - 1) * star_spacing
        stars_start_x = (width - total_star_width) // 2 - 20
        
        # Always show 3 grey + 3 gold (like patch)
        for i in range(total_stars):
            star_x_pos = stars_start_x + (i * star_spacing)
            if i >= 3:  # Last 3 are gold
                star_color = '#FFD700'
            else:  # First 3 are grey
                star_color = '#999999'  # Lighter grey - clearly visible like patch
            
            # Draw star
            draw_outlined_text("★", (star_x_pos, stars_y), 
                             label_font, star_color, outline_width=3)
        
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

