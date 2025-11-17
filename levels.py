#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Leveling System - Points and Level Progression
Users earn points through activities, not gambling
"""

import logging
import math
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import database
from datetime import datetime, timedelta
import json

logger = logging.getLogger(__name__)

# Points Rewards Configuration
XP_REWARDS = {
    'message': 5,           # Per message (with cooldown)
    'vote': 50,            # Voting for seller
}

# Cooldown for message points (seconds)
MESSAGE_XP_COOLDOWN = 30  # 30 seconds between message points gains (2 messages/minute max)

# Level calculation formula - EXPONENTIAL SYSTEM (1-600 levels)
def get_xp_for_level(level: int) -> int:
    """Calculate XP needed to advance FROM this level to next level"""
    if level >= 600:
        return 999999999  # Max level cap
    # Exponential curve: progressively harder
    return int(100 * (1 + level * 0.05))


def calculate_level_from_xp(total_xp: int) -> tuple:
    """
    Calculate level from total XP accumulated
    Returns: (level, xp_in_current_level, xp_needed_for_next)
    """
    if total_xp < 0:
        return 1, 0, get_xp_for_level(1)
    
    level = 1
    xp_accumulated = 0
    
    while level < 600:
        xp_needed = get_xp_for_level(level)
        if xp_accumulated + xp_needed > total_xp:
            # Still in this level
            xp_in_level = total_xp - xp_accumulated
            return level, xp_in_level, xp_needed
        xp_accumulated += xp_needed
        level += 1
    
    # Max level reached
    return 600, 0, 0


def get_xp_to_next_level(current_xp: int) -> tuple:
    """
    Get current level, XP in current level, XP needed for next, and progress percentage
    Returns: (current_level, xp_in_level, xp_needed, progress_percentage)
    """
    level, xp_in_level, xp_needed = calculate_level_from_xp(current_xp)
    progress = (xp_in_level / xp_needed * 100) if xp_needed > 0 else 100
    return level, xp_in_level, xp_needed, progress


# Backwards compatibility wrappers
def calculate_level(xp: int) -> int:
    """Get level from XP (wrapper for new system)"""
    return calculate_level_from_xp(xp)[0]


def calculate_xp_for_level(level: int) -> int:
    """Get total XP needed to reach a level (cumulative)"""
    total = 0
    for lvl in range(1, level):
        total += get_xp_for_level(lvl)
    return total


def add_xp(user_id: int, amount: int, reason: str = None) -> dict:
    """
    Add XP to user and return level info (with level-up rewards)
    Returns: dict with old_level, new_level, leveled_up, current_xp, points_earned
    """
    try:
        # Get current XP and level from database
        current_xp = get_user_xp(user_id)
        old_level, _, _ = calculate_level_from_xp(current_xp)
        
        # Add XP
        new_xp = current_xp + amount
        new_level, xp_in_level, xp_needed = calculate_level_from_xp(new_xp)
        
        # FIXED: Update XP and level without destroying other columns
        conn = database.get_sync_connection()
        # First ensure user exists
        conn.execute("""
            INSERT OR IGNORE INTO users (user_id, xp, level, points, balance) 
            VALUES (?, 0, 1, 0, 0.0)
        """, (user_id,))
        # Then update only XP and level
        conn.execute("""
            UPDATE users SET xp = ?, level = ? WHERE user_id = ?
        """, (new_xp, new_level, user_id))
        conn.commit()
        
        # Check for level up and award money points
        points_earned = 0
        if new_level > old_level:
            # Award 100 points (money) per level gained
            levels_gained = new_level - old_level
            points_earned = levels_gained * 100
            
            # Get current money points
            cursor = conn.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            current_money = result[0] if result and result[0] else 0
            
            # Add money reward
            conn.execute("""
                UPDATE users SET points = ? WHERE user_id = ?
            """, (current_money + points_earned, user_id))
        conn.commit()
        
        logger.info(f"🎉 User {user_id} leveled up: {old_level} → {new_level} (+{points_earned} points reward)")
        
        conn.close()
        
        if reason:
            logger.info(f"User {user_id} gained {amount} XP from {reason}. Level: {old_level} → {new_level}")
        
        return {
            'old_level': old_level,
            'new_level': new_level,
            'leveled_up': new_level > old_level,
            'current_xp': new_xp,
            'xp_gained': amount,
            'xp_in_level': xp_in_level,
            'xp_needed': xp_needed,
            'points_earned': points_earned
        }
    except Exception as e:
        logger.error(f"Error adding XP to user {user_id}: {e}")
        return None


def get_user_xp(user_id: int) -> int:
    """Get user's current XP (not points/money)"""
    try:
        conn = database.get_sync_connection()
        cursor = conn.execute("SELECT xp FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result and result[0] else 0
    except Exception as e:
        # Handle missing column during migration
        if "no such column: xp" in str(e):
            logger.warning(f"XP column not yet migrated for user {user_id}, returning 0")
            return 0
        logger.error(f"Error getting XP for user {user_id}: {e}")
        return 0


def get_user_money(user_id: int) -> int:
    """Get user's current money (points balance)"""
    try:
        conn = database.get_sync_connection()
        cursor = conn.execute("SELECT points FROM users WHERE user_id = ?", (user_id,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0
    except Exception as e:
        logger.error(f"Error getting money for user {user_id}: {e}")
        return 0


# Message points tracking (in-memory cache for cooldowns)
last_message_xp = {}

def can_gain_message_xp(user_id: int) -> bool:
    """Check if user can gain points from messaging (cooldown check)"""
    if user_id not in last_message_xp:
        return True
    
    last_time = last_message_xp[user_id]
    return (datetime.now() - last_time).total_seconds() >= MESSAGE_XP_COOLDOWN


def grant_message_xp(user_id: int, message_text: str = '', message_id: int = 0, chat_id: int = 0):
    """Grant XP for sending a message (with comprehensive anti-spam checks)"""
    
    # 1. Message length check (minimum 3 characters)
    if len(message_text.strip()) < 3:
        return None
    
    # 2. Account age check removed (no restriction)
    
    # 3. Daily message cap (400 messages per day)
    today = datetime.now().date().isoformat()
    daily_count = database.get_daily_message_count(user_id, today)
    if daily_count >= 400:
        return None
    
    # 4. Cooldown check (60 seconds between earning)
    if not can_gain_message_xp(user_id):
        return None
    
    # 5. Duplicate detection (no repeats within 5 minutes)
    if database.is_duplicate_message(user_id, message_text):
        return None
    
    # Award POINTS (money) directly - 5 points per message
    points_to_add = 5
    database.add_user_points(user_id, points_to_add)
    
    # Increment total message count for leveling (1000 messages = 1 level)
    database.increment_total_messages(user_id)
    total_messages = database.get_total_messages(user_id)
    
    # Calculate new level (1000 messages per level, linear)
    new_level = (total_messages // 1000) + 1
    old_level = database.get_user_level(user_id)
    
    # Check for level up
    leveled_up = False
    points_earned = 0
    if new_level > old_level:
        database.update_user_level(user_id, new_level)
        # Award 150 points bonus per level
        levels_gained = new_level - old_level
        points_earned = levels_gained * 150
        database.add_user_points(user_id, points_earned)
        leveled_up = True
        logger.info(f"🎉 User {user_id} leveled up: {old_level} → {new_level} (+{points_earned} points bonus)")
    
    # Track message for potential deletion penalty
    database.track_message(user_id, message_id, chat_id, message_text, points_to_add)
    # Increment daily count
    database.increment_daily_count(user_id, today)
    # Update cooldown timestamp
    last_message_xp[user_id] = datetime.now()
    
    # Cleanup old messages periodically
    import random
    if random.randint(1, 100) == 1:
        database.cleanup_old_messages()
    
    # Return result
    messages_in_level = total_messages % 1000
    messages_needed = 1000
    
    return {
        'old_level': old_level,
        'new_level': new_level,
        'leveled_up': leveled_up,
        'points_gained': points_to_add,
        'points_earned': points_earned,
        'total_messages': total_messages,
        'messages_in_level': messages_in_level,
        'messages_needed': messages_needed
    }


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
        
        # Get user stats (message count for leveling, points for money display)
        total_messages = database.get_total_messages(user_id)
        current_money = get_user_money(user_id)
        level = database.get_user_level(user_id)
        messages_in_level = total_messages % 1000
        messages_needed = 1000
        progress = (messages_in_level / messages_needed * 100) if messages_needed > 0 else 100
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
        time_underline_width, time_underline_height, time_underline_gap = 100, 12, 10
        # Health bar slightly lower for better separation
        health_rect = (40, 230, 560, 250)
        money_font_size_px = 100
        star_first_center = (main_margin, 430)
        star_gap = 70
        star_radius = 38  # bigger stars
        total_stars = 6
        # Outline thickness used by draw_outlined_text (keep in sync)
        outline_w = 5
        
        # Load GTA SA background image (green cityscape)
        background_path = os.path.join(os.path.dirname(__file__), 'background.jpg')
        
        try:
            img = Image.open(background_path)
            if img.size != (width, height):
                img = img.resize((width, height), Image.Resampling.LANCZOS)
            logger.info(f"Loaded GTA background from {background_path}")
        except Exception as e:
            # Fallback: create green gradient if image not found
            logger.warning(f"Could not load background image: {e}, using fallback")
            img = Image.new('RGB', (width, height), color='#87A96B')
            draw_temp = ImageDraw.Draw(img)
            for y in range(height):
                green_value = int(169 - (y / height * 40))
                color = (135, green_value, 107)
                draw_temp.line([(0, y), (width, y)], fill=color)
        
        # Add subtle vignette for depth (darker edges)
        vignette = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        vignette_draw = ImageDraw.Draw(vignette)
        center_x, center_y = width // 2, height // 2
        max_dist = math.sqrt(center_x**2 + center_y**2)
        for y in range(height):
            for x in range(0, width, 4):  # sample every 4px for performance
                dist = math.sqrt((x - center_x)**2 + (y - center_y)**2)
                alpha = int((dist / max_dist) * 60)  # max 60 alpha at corners
                if alpha > 0:
                    vignette_draw.point((x, y), fill=(0, 0, 0, alpha))
        try:
            img = Image.alpha_composite(img.convert('RGBA'), vignette).convert('RGB')
        except:
            pass  # skip vignette if alpha composite fails
        
        draw = ImageDraw.Draw(img)
        
        # Add subtle scanlines for retro PS2/CRT feel
        for y in range(0, height, 4):
            draw.line([(0, y), (width, y)], fill=(0, 0, 0, 10), width=1)
        
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

        def draw_outlined_text(text, position, font, fill_color='#FFFFFF', outline_color='#000000', outline_width=4, anchor=None, shadow=True):
            x, y = position
            kwargs = {'font': font}
            if anchor:
                kwargs['anchor'] = anchor
            
            # Drop shadow for depth (GTA SA style) - soft blur effect
            if shadow:
                shadow_offset = 4
                shadow_color = (0, 0, 0, 100)  # semi-transparent black
                # Create soft shadow by drawing multiple offset layers
                for s_offset in range(1, shadow_offset + 1):
                    alpha = int(100 / s_offset)  # fade as we go further
                    for s_adj in range(-1, 2):
                        for s_adj2 in range(-1, 2):
                            try:
                                draw.text((x + s_offset + s_adj, y + s_offset + s_adj2), text, fill=(0, 0, 0, alpha), **kwargs)
                            except:
                                draw.text((x + s_offset + s_adj, y + s_offset + s_adj2), text, fill='#000000', **kwargs)

            # Black outline (thick for visibility on any background)
            for adj in range(-outline_width, outline_width + 1):
                for adj2 in range(-outline_width, outline_width + 1):
                    if adj == 0 and adj2 == 0:
                        continue
                        draw.text((x + adj, y + adj2), text, fill=outline_color, **kwargs)
            # Bright fill on top
            draw.text(position, text, fill=fill_color, **kwargs)
        
        def draw_star(center_x, center_y, radius, filled=False, outline_width=5):
            points = []
            for i in range(10):
                angle_deg = -90 + i * 36
                angle_rad = math.radians(angle_deg)
                r = radius if i % 2 == 0 else radius * 0.45
                points.append((center_x + r * math.cos(angle_rad), center_y + r * math.sin(angle_rad)))
            
            if filled:
                # Gold stars with glow effect
                glow_color = '#FFD70080'  # semi-transparent gold
                for glow_offset in range(1, 4):
                    glow_points = []
                    for i in range(10):
                        angle_deg = -90 + i * 36
                        angle_rad = math.radians(angle_deg)
                        r = (radius + glow_offset) if i % 2 == 0 else (radius + glow_offset) * 0.45
                        glow_points.append((center_x + r * math.cos(angle_rad), center_y + r * math.sin(angle_rad)))
                    try:
                        draw.polygon(glow_points, fill=glow_color, outline=None)
                    except:
                        pass
                # Bright gold fill
                draw.polygon(points, outline='#000000', fill='#FFD700', width=outline_width)
            else:
                # Gray unfilled stars with darker outline
                draw.polygon(points, outline='#000000', fill='#6A6A6A', width=outline_width + 1)
        
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

        # Profile picture box with enhanced borders and subtle glow
        outer_border = icon_outer_border
        inner_border = icon_inner_border
        
        # Subtle outer glow (white)
        for glow_dist in range(1, 3):
            glow_alpha = int(50 / glow_dist)
            try:
                draw.rectangle(
                    [icon_x - outer_border - glow_dist, icon_y - outer_border - glow_dist, 
                     icon_x + icon_size + outer_border + glow_dist, icon_y + icon_size + outer_border + glow_dist],
                    outline=(255, 255, 255, glow_alpha), width=2
                )
            except:
                pass
        
        # Outer white border (bright)
        draw.rectangle(
            [icon_x - outer_border, icon_y - outer_border, icon_x + icon_size + outer_border, icon_y + icon_size + outer_border],
            fill='#FFFFFF', outline='#000000', width=4
        )
        # Inner black frame
        draw.rectangle(
            [icon_x - inner_border, icon_y - inner_border, icon_x + icon_size + inner_border, icon_y + icon_size + inner_border],
            fill='#000000', outline='#000000', width=2
        )
        # Photo background
        draw.rectangle(
            [icon_x, icon_y, icon_x + icon_size, icon_y + icon_size],
            fill='#1A1A1A', outline=None
        )
        
        # Insert profile picture
        if profile_pic:
            # Resize to large size like patch
            profile_pic_resized = profile_pic.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
            img.paste(profile_pic_resized, (icon_x, icon_y))
        else:
            # Keep empty white box (matches mock)
            pass
        
        # Location text removed for cleaner look
        
        
        # Time display (top-right) with dynamic right alignment and underline
        time_text = "04:20"
        time_font = get_font(100)
        tb = draw.textbbox((0, 0), time_text, font=time_font)
        tw, th = tb[2] - tb[0], tb[3] - tb[1]
        time_x = width - time_right_margin - tw
        time_y = time_top
        draw_outlined_text(time_text, (time_x, time_y), time_font)
        # Username and level display below time (stacked vertically, aligned to time's left edge)
        # Balanced gap for visual separation
        info_start_y = time_y + th + (outline_w * 2) + 55  # 55px gap from clock
        
        # Username text (ALL CAPS, clean sans-serif font for readability)
        username_display = username.upper() if username else first_name.upper()
        # Try multiple fonts for best appearance (Impact/Franklin Gothic for GTA look)
        try:
            if os.path.exists("C:/Windows/Fonts/impact.ttf"):
                username_font = ImageFont.truetype("C:/Windows/Fonts/impact.ttf", 32)
            elif os.path.exists("C:/Windows/Fonts/framd.ttf"):  # Franklin Gothic Medium
                username_font = ImageFont.truetype("C:/Windows/Fonts/framd.ttf", 32)
            elif os.path.exists("C:/Windows/Fonts/arialbd.ttf"):
                username_font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 32)
            elif os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
                username_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
            else:
                username_font = get_font(32)
        except:
            username_font = get_font(32)
        
        ub = draw.textbbox((0, 0), username_display, font=username_font)
        uw, uh = ub[2] - ub[0], ub[3] - ub[1]
        # Left-align to match time's left edge
        username_x = time_x
        username_y = info_start_y
        draw_outlined_text(username_display, (username_x, username_y), username_font, fill_color='#FFFFFF', outline_width=3, shadow=True)
        
        # Level text below username (ALL CAPS, clean sans-serif font)
        level_display = f"LEVEL {level}"
        try:
            if os.path.exists("C:/Windows/Fonts/impact.ttf"):
                level_font = ImageFont.truetype("C:/Windows/Fonts/impact.ttf", 28)
            elif os.path.exists("C:/Windows/Fonts/framd.ttf"):
                level_font = ImageFont.truetype("C:/Windows/Fonts/framd.ttf", 28)
            elif os.path.exists("C:/Windows/Fonts/arialbd.ttf"):
                level_font = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 28)
            elif os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
                level_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
            else:
                level_font = get_font(28)
        except:
            level_font = get_font(28)
        
        lb = draw.textbbox((0, 0), level_display, font=level_font)
        lw, lh = lb[2] - lb[0], lb[3] - lb[1]
        # Left-align to match username
        level_x = time_x
        level_y = username_y + uh + 20
        draw_outlined_text(level_display, (level_x, level_y), level_font, fill_color='#FFFFFF', outline_width=3, shadow=True)
        
        # Money text: display money balance (not XP)
        points_text = f"${current_money:09d}"
        money_font = get_font(95)  # slightly smaller to avoid edge-to-edge
        mb = draw.textbbox((0, 0), points_text, font=money_font)
        mw, mh = mb[2] - mb[0], mb[3] - mb[1]
        money_x = (width - mw) // 2
        
        # Stars geometry: align star row to match money width
        stars_y = height - 80  # move to bottom with small margin
        star_diameter = 68  # larger for wireframe prominence
        star_radius = star_diameter // 2
        star_row_width = mw
        # Distribute 6 stars evenly across money width
        star_gap_calculated = (star_row_width - star_diameter) / 5 if total_stars > 1 else 0
        star_first_x = money_x + star_radius
        
        # Position money with larger gap from stars (doubled)
        vertical_gap = 72  # doubled from 36 for more breathing room
        star_top = stars_y - star_radius
        money_y = star_top - vertical_gap - mh - outline_w
        
        # Health bar: smaller and closer to money
        health_bar_height = 22  # reduce from 28
        health_gap_to_money = 24  # smaller gap than vertical_gap
        health_bottom = money_y - outline_w
        health_top = health_bottom - health_gap_to_money - health_bar_height
        health_rect_adjusted = (health_rect[0], int(health_top), health_rect[2], int(health_top + health_bar_height))
        
        # Draw health bar showing message progress to next level
        from PIL import ImageDraw
        x1, y1, x2, y2 = health_rect_adjusted
        health_width_total = x2 - x1
        
        # Calculate fill width based on message progress (X/1000 messages)
        progress_ratio = messages_in_level / messages_needed if messages_needed > 0 else 1.0
        fill_width = int((health_width_total - 4) * progress_ratio)
        
        # Draw background (dark red for unfilled portion to add depth)
        draw.rounded_rectangle(health_rect_adjusted, radius=4, fill='#4A1616', outline=None)
        
        # Draw filled portion with brighter red gradient (only up to progress)
        for y_offset in range(int(y2 - y1)):
            ratio = y_offset / (y2 - y1)
            red_val = int(220 + (245 - 220) * (1 - ratio))  # brighter red range
            green_val = int(40 + (75 - 40) * (1 - ratio))
            color = (red_val, green_val, 45)
            # Only draw up to fill_width
            if fill_width > 0:
                draw.line([(x1 + 2, y1 + y_offset), (min(x1 + 2 + fill_width, x2 - 2), y1 + y_offset)], fill=color, width=1)
        
        # Black border
        draw.rounded_rectangle(health_rect_adjusted, radius=4, outline='#000000', width=3, fill=None)
        
        # Inner bevel on filled portion
        if fill_width > 10:
            draw.line([(x1 + 4, y1 + 3), (min(x1 + fill_width, x2 - 4), y1 + 3)], fill='#FF6B6B', width=2)
            draw.line([(x1 + 4, y2 - 3), (min(x1 + fill_width, x2 - 4), y2 - 3)], fill='#8B0000', width=2)
        
        # XP text removed for cleaner health bar
        
        # Draw money (clean GTA style with thicker outline)
        # Thicker outline for more authentic GTA look
        for adj in range(-6, 7):
            for adj2 in range(-6, 7):
                if adj == 0 and adj2 == 0:
                    continue
                draw.text((money_x + adj, money_y + adj2), points_text, fill='#000000', font=money_font)
        # Bright green fill
        draw.text((money_x, money_y), points_text, fill='#0FFF50', font=money_font)
        
        # Draw stars with gradual filling based on level (1 star per 100 levels)
        # Level based on messages: 1000 messages = 1 level
        stars_earned = min(6, level // 100)  # 0-6 full stars
        partial_progress = (level % 100) / 100.0  # 0.0-1.0 progress to next star
        
        # Override: new users start with first star at 33% filled (1/3)
        if stars_earned == 0 and partial_progress < 0.33:
            partial_progress = 0.33
        
        def blend_colors(color1_hex, color2_hex, ratio):
            """Blend two hex colors by ratio (0=color1, 1=color2)"""
            c1 = tuple(int(color1_hex[i:i+2], 16) for i in (1, 3, 5))
            c2 = tuple(int(color2_hex[i:i+2], 16) for i in (1, 3, 5))
            blended = tuple(int(c1[i] + (c2[i] - c1[i]) * ratio) for i in range(3))
            return '#{:02x}{:02x}{:02x}'.format(*blended)
        
        # Extremely bright GTA SA yellow for stars (like real GTA SA)
        gta_yellow = '#FFFF00'  # pure bright yellow for maximum visibility
        
        star_positions = []
        for index in range(total_stars):
            cx = int(star_first_x + index * star_gap_calculated)
            
            if index < stars_earned:
                # Fully earned star (bright GTA yellow)
                filled = True
            elif index == stars_earned:
                # Partially earned star - draw with vertical split fill
                filled = 'partial'
            else:
                # Not earned yet (gray)
                filled = False
            
            # Draw star polygon
            points_list = []
            for i in range(10):
                angle_deg = -90 + i * 36
                angle_rad = math.radians(angle_deg)
                r = star_radius if i % 2 == 0 else star_radius * 0.45
                points_list.append((cx + r * math.cos(angle_rad), stars_y + r * math.sin(angle_rad)))
            
            if filled == 'partial':
                # Draw with blended color instead of hard cutoff (smoother visual)
                blended_color = blend_colors('#6A6A6A', gta_yellow, partial_progress)
                draw.polygon(points_list, outline='#000000', fill=blended_color, width=5)
            elif filled:
                # Fully yellow
                draw.polygon(points_list, outline='#000000', fill=gta_yellow, width=5)
            else:
                # Gray
                draw.polygon(points_list, outline='#000000', fill='#6A6A6A', width=5)
            
            # Add shimmer to fully gold stars only
            if index < stars_earned:
                shimmer_y = stars_y - star_radius + 2
                shimmer_size = 4
                draw.ellipse([cx - shimmer_size//2, shimmer_y - shimmer_size//2, 
                             cx + shimmer_size//2, shimmer_y + shimmer_size//2], 
                             fill='#FFFFCC')
        
            # Determine star color for debugging
            if filled == True:
                star_color = gta_yellow
            elif filled == 'partial':
                star_color = 'partial_fill'
            else:
                star_color = '#6A6A6A'
            
            star_positions.append({'index': index, 'x': cx, 'y': stars_y, 'radius': star_radius, 'color': star_color, 'progress': partial_progress if index == stars_earned else (1.0 if index < stars_earned else 0.0)})
        try:
            layout_debug = {
                'canvas': {'width': width, 'height': height},
                'icon': {'top_left': [icon_x, icon_y], 'size': icon_size},
                'time': {'text': time_text, 'position': [time_x, time_y], 'text_size': [tw, th]},
                'username': {'text': username_display, 'position': [username_x, username_y]},
                'level_display': {'text': level_display, 'position': [level_x, level_y]},
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
        
        # Send image with caption and exchange button
        caption = (
            f"Uždirbkite Taškus:\n\n"
            f"Žinutės +5\n"
            f"Balsavimas +50\n"
            f"Pakėlimas lygio +150\n\n"
            f"Keitimas: 2,000 taškų = $1"
        )
        
        # Add exchange button (with url to start private chat for exchange)
        keyboard = [
            [InlineKeyboardButton("💱 Iškeisti Taškus į Pinigus", url=f"https://t.me/{context.bot.username}?start=exchange")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_photo(photo=bio, caption=caption, reply_markup=reply_markup, parse_mode='HTML')
        
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
        message += "<i>Uždirbkite taškus:</i>\n"
        message += f"💬 Žinutės: +{XP_REWARDS['message']}\n"
        message += f"🗳️ Balsavimas: +{XP_REWARDS['vote']}\n"
        message += f"🎉 Pakėlimas lygio: +150"
        
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

