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
import json

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
        
        # Layout constants taken from the mock layout
        width, height = 600, 600
        icon_size = 140
        icon_outer_border = 6
        icon_inner_border = 3
        icon_origin = (40, 40)
        main_margin = 60  # matches wireframe baseline text "60 px"
        # Time block will be measured and right-aligned to 60px margin
        time_top = 40
        time_right_margin = 60
        time_underline_width, time_underline_height, time_underline_gap = 100, 8, 10
        # Health bar slightly lower for better separation
        health_rect = (40, 230, 560, 250)
        money_font_size_px = 100
        star_first_center = (main_margin, 430)
        star_gap = 70
        star_radius = 35
        total_stars = 6
        # Outline thickness used by draw_outlined_text (keep in sync)
        outline_w = 5

        # Create clean white canvas
        img = Image.new('RGB', (width, height), color='#FFFFFF')
        
        draw = ImageDraw.Draw(img)
        
        # Load Pricedown font (or fallback) for outline text
        assets_dir = os.path.join(os.path.dirname(__file__), 'assets')
        font_candidates = [
            os.path.join(assets_dir, "Pricedown Bl.otf"),
            os.path.join(assets_dir, "pricedown.ttf"),
            os.path.join(assets_dir, "Pricedown bl.ttf"),
            "C:/Windows/Fonts/pricedown bl.ttf",
            "C:/Windows/Fonts/PRICEDOW.TTF",
            "/usr/share/fonts/truetype/pricedown/pricedown.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]

        font_path_used = None
        pricedown_font = None
        for candidate in font_candidates:
            if os.path.exists(candidate):
                try:
                    pricedown_font = ImageFont.truetype(candidate, money_font_size_px)
                    font_path_used = candidate
                    logger.info(f"Loaded HUD font: {candidate}")
                    break
                except Exception as font_error:
                    logger.debug(f"Failed to load font {candidate}: {font_error}")

        if not pricedown_font:
            pricedown_font = ImageFont.load_default()
            logger.warning("Falling back to default font for HUD")

        def get_font(size):
            if font_path_used:
                try:
                    return ImageFont.truetype(font_path_used, size)
                except Exception as font_error:
                    logger.warning(f"Failed resizing font {font_path_used} to {size}px: {font_error}")
            if pricedown_font and hasattr(pricedown_font, "path"):
                try:
                    return ImageFont.truetype(pricedown_font.path, size)
                except Exception:
                    pass
            if pricedown_font and hasattr(pricedown_font, "font_variant"):
                try:
                    return pricedown_font.font_variant(size=size)
                except Exception:
                    pass
            return ImageFont.load_default()

        def fit_font_size(text: str, target_width: int, start_size: int, max_size: int = 140) -> int:
            """Increase font size until text width approaches target_width (<= target),
            then return the size. Keeps a little side padding (98% of target).
            """
            size = max(8, start_size)
            while size < max_size:
                f = get_font(size)
                bbox = draw.textbbox((0, 0), text, font=f)
                w = bbox[2] - bbox[0]
                if w >= int(target_width * 0.98):
                    break
                size += 2
            return size

        def draw_outlined_text(text, position, font, fill_color='#FFFFFF', outline_color='#000000', outline_width=4, anchor=None):
            x, y = position
            kwargs = {'font': font}
            if anchor:
                kwargs['anchor'] = anchor

            for adj in range(-outline_width, outline_width + 1):
                for adj2 in range(-outline_width, outline_width + 1):
                    if adj == 0 and adj2 == 0:
                        continue
                    draw.text((x + adj, y + adj2), text, fill=outline_color, **kwargs)
            draw.text(position, text, fill=fill_color, **kwargs)

        def draw_star(center_x, center_y, radius, outline_width=5):
            points = []
            for i in range(10):
                angle_deg = -90 + i * 36
                angle_rad = math.radians(angle_deg)
                r = radius if i % 2 == 0 else radius * 0.45
                points.append((center_x + r * math.cos(angle_rad), center_y + r * math.sin(angle_rad)))
            draw.polygon(points, outline='#000000', fill='#FFFFFF', width=outline_width)
        
        # Get user profile photo (optional)
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
        
        icon_x, icon_y = icon_origin

        # Profile picture box (outer + inner outline only)
        outer_border = icon_outer_border
        inner_border = icon_inner_border
        draw.rectangle(
            [icon_x - outer_border, icon_y - outer_border, icon_x + icon_size + outer_border, icon_y + icon_size + outer_border],
            fill='#FFFFFF', outline='#000000', width=4
        )
        draw.rectangle(
            [icon_x - inner_border, icon_y - inner_border, icon_x + icon_size + inner_border, icon_y + icon_size + inner_border],
            fill='#FFFFFF', outline='#000000', width=3
        )
        draw.rectangle(
            [icon_x, icon_y, icon_x + icon_size, icon_y + icon_size],
            fill='#FFFFFF', outline='#000000', width=3
        )
        
        # Insert profile picture
        if profile_pic:
            # Resize to large size like patch
            profile_pic_resized = profile_pic.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
            img.paste(profile_pic_resized, (icon_x, icon_y))
        else:
            # Keep empty white box (matches mock)
            pass
        
        
        # Time display (top-right) with dynamic right alignment and underline
        time_text = "04:20"
        time_font = get_font(100)
        tb = draw.textbbox((0, 0), time_text, font=time_font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        time_x = width - time_right_margin - tw
        time_y = time_top
        draw_outlined_text(time_text, (time_x, time_y), time_font)
        # underline centered under the time text
        ul_x1 = time_x + (tw - time_underline_width) // 2
        ul_y1 = time_y + th + outline_w + time_underline_gap
        time_underline_rect = (ul_x1, ul_y1, ul_x1 + time_underline_width, ul_y1 + time_underline_height)
        draw.rectangle(time_underline_rect, outline='#000000', width=4, fill='#FFFFFF')
        
        # Money text: size to fill most of row width
        points_text = f"${current_points:09d}"
        money_font = get_font(95)  # slightly smaller to avoid edge-to-edge
        mb = draw.textbbox((0, 0), points_text, font=money_font)
        mw, mh = mb[2] - mb[0], mb[3] - mb[1]
        money_x = (width - mw) // 2
        
        # Stars geometry: align star row to match money width
        stars_y = 430
        star_diameter = 56
        star_radius = star_diameter // 2
        star_row_width = mw
        # Distribute 6 stars evenly across money width
        star_gap_calculated = (star_row_width - star_diameter) / 5 if total_stars > 1 else 0
        star_first_x = money_x + star_radius
        
        # Position money with equal gap above and below
        vertical_gap = 32  # consistent spacing
        star_top = stars_y - star_radius
        money_y = star_top - vertical_gap - mh - outline_w
        
        # Health bar: same gap above money as money has above stars
        health_bottom = money_y - outline_w
        health_top = health_bottom - vertical_gap - (health_rect[3] - health_rect[1])
        health_rect_adjusted = (health_rect[0], int(health_top), health_rect[2], int(health_bottom - vertical_gap))
        
        # Draw health bar
        draw.rectangle(health_rect_adjusted, outline='#000000', width=5, fill='#FFFFFF')
        
        # Draw money
        draw_outlined_text(points_text, (money_x, money_y), money_font)
        
        # Draw stars aligned to money width
        star_positions = []
        for index in range(total_stars):
            cx = int(star_first_x + index * star_gap_calculated)
            draw_star(cx, stars_y, star_radius)
            star_positions.append({'index': index, 'x': cx, 'y': stars_y, 'radius': star_radius})
        try:
            layout_debug = {
                'canvas': {'width': width, 'height': height},
                'icon': {'top_left': [icon_x, icon_y], 'size': icon_size},
                'time': {'text': time_text, 'position': [time_x, time_y], 'underline': list(time_underline_rect), 'text_size': [tw, th]},
                'health_bar': {'rect': health_rect_adjusted},
                'money': {
                    'text': points_text,
                    'position': [money_x, money_y],
                    'font_path': font_path_used,
                    'bbox': {'width': mw, 'height': mh}
                },
                'stars': {'gap': star_gap_calculated, 'radius': star_radius, 'positions': star_positions}
            }
            logger.info("HUD layout debug: %s", json.dumps(layout_debug))
        except Exception as debug_error:
            logger.warning(f"Failed to serialize HUD layout debug data: {debug_error}")
        
        # No pixelation needed for green cityscape background
        
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

