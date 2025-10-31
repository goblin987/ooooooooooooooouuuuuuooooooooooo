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
        
        # GTA SAN ANDREAS HUD STYLE
        width, height = 1080, 1920
        
        # GTA SA background with sky, desert, and palm trees
        img = Image.new('RGB', (width, height), color='#87CEEB')
        draw = ImageDraw.Draw(img)
        
        # Sky blue gradient at top (0-40%)
        sky_start = (135, 206, 235)
        sky_end = (176, 196, 222)
        for y in range(int(height * 0.4)):
            ratio = y / (height * 0.4)
            r = int(sky_start[0] + (sky_end[0] - sky_start[0]) * ratio)
            g = int(sky_start[1] + (sky_end[1] - sky_start[1]) * ratio)
            b = int(sky_start[2] + (sky_end[2] - sky_start[2]) * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b))
        
        # Desert/sand gradient in middle (40-85%)
        desert_start = (210, 180, 140)
        desert_end = (194, 178, 128)
        for y in range(int(height * 0.4), int(height * 0.85)):
            ratio = (y - height * 0.4) / (height * 0.45)
            r = int(desert_start[0] + (desert_end[0] - desert_start[0]) * ratio)
            g = int(desert_start[1] + (desert_end[1] - desert_start[1]) * ratio)
            b = int(desert_start[2] + (desert_end[2] - desert_start[2]) * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b))
        
        # Ground/darker sand at bottom (85-100%)
        ground_color = (184, 134, 88)
        for y in range(int(height * 0.85), height):
            draw.line([(0, y), (width, y)], fill=ground_color)
        
        # Draw horizon line
        horizon_y = int(height * 0.4)
        draw.line([(0, horizon_y), (width, horizon_y)], fill='#4682B4', width=2)
        
        # Draw palm trees at bottom-right (simple pixelated style)
        tree_x = width - 200
        tree_y = height - 300
        
        # Palm tree trunk (dark brown vertical rectangle)
        draw.rectangle([tree_x + 20, tree_y + 100, tree_x + 35, tree_y + 200], fill='#8B4513', outline='#000000', width=2)
        
        # Palm tree leaves (dark green triangles/rectangles)
        # Left leaf
        draw.polygon([(tree_x + 10, tree_y + 50), (tree_x + 20, tree_y + 100), (tree_x + 5, tree_y + 100)], fill='#228B22', outline='#000000', width=2)
        # Right leaf
        draw.polygon([(tree_x + 50, tree_y + 50), (tree_x + 35, tree_y + 100), (tree_x + 55, tree_y + 100)], fill='#228B22', outline='#000000', width=2)
        # Top leaf
        draw.polygon([(tree_x + 27, tree_y + 30), (tree_x + 20, tree_y + 100), (tree_x + 35, tree_y + 100)], fill='#228B22', outline='#000000', width=2)
        
        # Additional smaller palm tree further left
        tree2_x = width - 450
        tree2_y = height - 280
        draw.rectangle([tree2_x + 15, tree2_y + 90, tree2_x + 28, tree2_y + 180], fill='#8B4513', outline='#000000', width=2)
        draw.polygon([(tree2_x + 5, tree2_y + 40), (tree2_x + 15, tree2_y + 90), (tree2_x + 2, tree2_y + 90)], fill='#228B22', outline='#000000', width=2)
        draw.polygon([(tree2_x + 40, tree2_y + 40), (tree2_x + 28, tree2_y + 90), (tree2_x + 48, tree2_y + 90)], fill='#228B22', outline='#000000', width=2)
        draw.polygon([(tree2_x + 21, tree2_y + 25), (tree2_x + 15, tree2_y + 90), (tree2_x + 28, tree2_y + 90)], fill='#228B22', outline='#000000', width=2)
        
        # Load pixelated fonts - try multiple paths, fallback to bold with pixelation
        time_font = None
        level_font = None
        points_font = None
        
        # Try pixelated fonts in order
        pixel_font_paths = [
            ("C:/Windows/Fonts/pressstart2p.ttf", "Press Start 2P"),
            ("/usr/share/fonts/truetype/pressstart2p/PressStart2P-Regular.ttf", "Press Start 2P"),
            ("C:/Windows/Fonts/Minecraftia-Regular.ttf", "Minecraftia"),
            ("/usr/share/fonts/truetype/minecraftia/Minecraftia-Regular.ttf", "Minecraftia"),
        ]
        
        for font_path, font_name in pixel_font_paths:
            try:
                import os
                if os.path.exists(font_path):
                    time_font = ImageFont.truetype(font_path, 130)
                    level_font = ImageFont.truetype(font_path, 55)
                    points_font = ImageFont.truetype(font_path, 115)
                    logger.info(f"Loaded pixelated font: {font_name}")
                    break
            except:
                continue
        
        # Fallback to bold Arial if pixel fonts not found
        if not time_font:
            try:
                time_font = ImageFont.truetype("arialbd.ttf", 130)
                level_font = ImageFont.truetype("arialbd.ttf", 55)
                points_font = ImageFont.truetype("arialbd.ttf", 115)
            except:
                try:
                    time_font = ImageFont.truetype("arial.ttf", 130)
                    level_font = ImageFont.truetype("arial.ttf", 55)
                    points_font = ImageFont.truetype("arial.ttf", 115)
                except:
                    time_font = ImageFont.load_default()
                    level_font = ImageFont.load_default()
                    points_font = ImageFont.load_default()
        
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
        
        # GTA SAN ANDREAS HUD LAYOUT
        
        # 1. TOP-LEFT: Profile Picture in Light Green Square
        pic_size = 200
        pic_x = 40
        pic_y = 60
        square_size = pic_size + 40  # Extra space for border
        
        # Draw light green square with thick black border (5px)
        border_thickness = 5
        draw.rectangle([pic_x - border_thickness, pic_y - border_thickness, 
                       pic_x + square_size + border_thickness, pic_y + square_size + border_thickness], 
                      fill='#000000')  # Black border
        draw.rectangle([pic_x, pic_y, pic_x + square_size, pic_y + square_size], 
                      fill='#90EE90')  # Light green
        
        # Place profile picture inside square (square, not circular)
        pic_inner_x = pic_x + 20
        pic_inner_y = pic_y + 20
        if profile_pic:
            # Apply subtle pixelation to profile pic for retro look
            profile_pic = profile_pic.resize((pic_size, pic_size), Image.Resampling.LANCZOS)
            # Small pixelation effect
            profile_pic_small = profile_pic.resize((pic_size // 2, pic_size // 2), Image.Resampling.NEAREST)
            profile_pic = profile_pic_small.resize((pic_size, pic_size), Image.Resampling.NEAREST)
            img.paste(profile_pic, (pic_inner_x, pic_inner_y))
        else:
            # Default avatar
            draw.rectangle([pic_inner_x, pic_inner_y, pic_inner_x + pic_size, pic_inner_y + pic_size], 
                          fill='#555555', outline='#000000', width=2)
            initial = first_name[0].upper() if first_name else "?"
            draw_outlined_text(initial, (pic_inner_x + pic_size//2, pic_inner_y + pic_size//2), 
                             level_font, '#FFFFFF', outline_width=4, anchor='mm')
        
        # Level text INSIDE green square (below profile pic, like ammo count in reference)
        level_text_y = pic_y + square_size - 25  # Position inside square at bottom
        level_text = f"Level: {level}"
        draw_outlined_text(level_text, (pic_x + square_size//2, level_text_y), 
                         level_font, '#87CEEB', outline_width=4, anchor='mm')
        
        # 2. TOP-RIGHT: Time Display "04:20"
        time_text = "04:20"
        time_x = width - 250
        time_y = 50
        draw_outlined_text(time_text, (time_x, time_y), 
                         time_font, '#D3D3D3', outline_width=4)
        
        # 3. MIDDLE-RIGHT: Status Bars (thicker with better visibility)
        bar_x = width - 450
        bar_y = 350
        bar_width = 380
        bar_height = 65  # Thicker bars
        bar_spacing = 75
        
        # TOP BAR: Progress Bar (White fill) - thicker outline
        outline_thickness = 5
        draw.rectangle([bar_x - outline_thickness, bar_y - outline_thickness, 
                       bar_x + bar_width + outline_thickness, bar_y + bar_height + outline_thickness], 
                     fill='#000000')  # Black outline
        draw.rectangle([bar_x, bar_y, bar_x + bar_width, bar_y + bar_height], 
                     fill='#333333')  # Dark gray background
        
        # Progress fill (bright white)
        filled_width = int((progress / 100) * bar_width)
        if filled_width > 5:
            draw.rectangle([bar_x, bar_y, bar_x + filled_width, bar_y + bar_height], 
                          fill='#FFFFFF')
            # Add subtle inner highlight
            draw.rectangle([bar_x, bar_y, bar_x + filled_width, bar_y + 3], fill='#CCCCCC')
        
        # BOTTOM BAR: Secondary Bar (Red fill - represents level completion)
        bar2_y = bar_y + bar_height + bar_spacing
        draw.rectangle([bar_x - outline_thickness, bar2_y - outline_thickness, 
                       bar_x + bar_width + outline_thickness, bar2_y + bar_height + outline_thickness], 
                     fill='#000000')  # Black outline
        draw.rectangle([bar_x, bar2_y, bar_x + bar_width, bar2_y + bar_height], 
                     fill='#333333')  # Dark gray background
        
        # Level completion fill (bright red) - shows how far through current level
        level_completion = (points_in_level / points_needed * 100) if points_needed > 0 else 0
        filled_width2 = int((level_completion / 100) * bar_width)
        if filled_width2 > 5:
            draw.rectangle([bar_x, bar2_y, bar_x + filled_width2, bar2_y + bar_height], 
                          fill='#FF0000')
            # Add subtle inner highlight
            draw.rectangle([bar_x, bar2_y, bar_x + filled_width2, bar2_y + 3], fill='#CC0000')
        
        # 4. BOTTOM-CENTER/RIGHT: Points Display (Money style)
        points_text = f"${current_points:08d}"  # Format like "$00251742"
        points_x = width - 400
        points_y = height - 120
        draw_outlined_text(points_text, (points_x, points_y), 
                         points_font, '#006400', outline_width=4)  # Dark green
        
        # Apply retro pixelation effect to entire image
        img = pixelate_image(img, scale_factor=0.6)
        
        # Recreate draw object after pixelation
        draw = ImageDraw.Draw(img)
        
        # Redraw UI elements after pixelation to keep them sharp (optional enhancement)
        # The pixelation will give the retro look while keeping elements readable
        
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

