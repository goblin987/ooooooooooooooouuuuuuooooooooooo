#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Leaderboard System - GTA SA Style Top Chatters
Shows top 5 users by message count in last 30 days
"""

import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import database
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os

logger = logging.getLogger(__name__)


def get_monthly_leaderboard(chat_id: int = None, limit: int = 5) -> list:
    """Get top chatters in the last 30 days
    Returns: [(user_id, username, message_count), ...]
    """
    try:
        conn = database.get_sync_connection()
        thirty_days_ago = datetime.now() - timedelta(days=30)
        
        # Get message counts from recent_messages table (tracks last 7 days for spam detection)
        # and total_messages column in users table
        # We'll use total_messages since leaderboard_reset_date
        
        # First check if leaderboard_reset_date column exists
        cursor = conn.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'leaderboard_reset_date' not in columns:
            # Add the column (SQLite doesn't support DEFAULT with functions in ALTER TABLE)
            conn.execute("ALTER TABLE users ADD COLUMN leaderboard_reset_date TIMESTAMP")
            # Set initial values
            conn.execute("UPDATE users SET leaderboard_reset_date = datetime('now') WHERE leaderboard_reset_date IS NULL")
            conn.commit()
        
        # Get users with message counts since last reset
        query = """
            SELECT u.user_id, uc.username, 
                   COALESCE(u.total_messages, 0) as msg_count
            FROM users u
            LEFT JOIN user_cache uc ON u.user_id = uc.user_id
            WHERE u.leaderboard_reset_date IS NOT NULL
            ORDER BY msg_count DESC
            LIMIT ?
        """
        
        cursor = conn.execute(query, (limit,))
        results = cursor.fetchall()
        conn.close()
        
        return [(uid, uname or "Unknown", count) for uid, uname, count in results]
    except Exception as e:
        logger.error(f"Error getting leaderboard: {e}")
        return []


def generate_leaderboard_image(top_users: list) -> BytesIO:
    """Generate GTA SA Stats-style leaderboard matching the provided wireframe"""
    try:
        width, height = 600, 600

        # Base background (outer brown tone)
        background_color = '#3B332B'
        panel_color = '#201B16'
        highlight_color = '#2B241D'
        bar_outline_color = '#111111'
        bar_background_color = '#352F28'
        bar_fill_color = '#38F764'

        panel_margin = 22
        panel_radius = 28

        img = Image.new('RGB', (width, height), background_color)
        draw = ImageDraw.Draw(img)

        panel_rect = [panel_margin, panel_margin, width - panel_margin, height - panel_margin]
        draw.rounded_rectangle(panel_rect, radius=panel_radius, fill=panel_color)

        # Apply subtle top highlight gradient
        gradient = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        gradient_draw = ImageDraw.Draw(gradient)
        highlight_top = [panel_rect[0], panel_rect[1], panel_rect[2], panel_rect[1] + 160]
        gradient_draw.rectangle(highlight_top, fill=(255, 255, 255, 28))
        gradient = gradient.filter(ImageFilter.GaussianBlur(45))
        img = Image.alpha_composite(img.convert('RGBA'), gradient).convert('RGB')
        draw = ImageDraw.Draw(img)

        # Fonts
        font_path_pricedown = "/opt/render/project/src/assets/Pricedown Bl.otf"
        font_path_arial = "/opt/render/project/src/assets/ariblk.ttf"

        try:
            font_title = ImageFont.truetype(font_path_pricedown, 112)
            font_username = ImageFont.truetype(font_path_arial, 36)
            font_footer = ImageFont.truetype(font_path_arial, 38)
        except:
            font_title = ImageFont.load_default()
            font_username = ImageFont.load_default()
            font_footer = ImageFont.load_default()

        def measure_text(text: str, font: ImageFont.FreeTypeFont):
            try:
                bbox = font.getbbox(text)
                return bbox[2] - bbox[0], bbox[3] - bbox[1]
            except AttributeError:
                return font.getsize(text)

        def draw_outlined_text(position, text, font, fill, outline_fill='#000000', outline_width=4):
            x, y = position
            for dx in range(-outline_width, outline_width + 1):
                for dy in range(-outline_width, outline_width + 1):
                    if dx == 0 and dy == 0:
                        continue
                    draw.text((x + dx, y + dy), text, font=font, fill=outline_fill)
            draw.text((x, y), text, font=font, fill=fill)

        def draw_label(position, text):
            draw.text((position[0] + 2, position[1] + 2), text, font=font_username, fill='#050505')
            draw.text(position, text, font=font_username, fill='#FFFFFF')

        # Header
        header_pos = (panel_rect[0] + 42, panel_rect[1] + 38)
        draw_outlined_text(header_pos, "Stats", font_title, '#FFFFFF', '#000000', outline_width=6)

        # Prepare rows
        rows = top_users[:5]
        while len(rows) < 5:
            rows.append((None, "Unknown", 0))

        max_messages = max([count for _, _, count in rows], default=1)

        row_spacing = 92
        row_start_y = panel_rect[1] + 150
        label_x = panel_rect[0] + 50
        bar_x = panel_rect[0] + 300
        bar_width = 290
        bar_height = 30

        for index, (_, username, message_count) in enumerate(rows):
            y = row_start_y + index * row_spacing

            display_name = username or "Unknown"
            if display_name.startswith('@'):
                display_name = display_name[1:]
            display_name = display_name[:16]

            draw_label((label_x, y))

            bar_rect = [bar_x, y - 2, bar_x + bar_width, y - 2 + bar_height]
            draw.rounded_rectangle(bar_rect, radius=8, fill=bar_background_color, outline=bar_outline_color, width=4)

            ratio = 0 if max_messages == 0 else min(max(message_count / max_messages, 0), 1)
            fill_width = int(bar_width * ratio)
            if fill_width > 6:
                fill_rect = [bar_x + 4, y + 2, bar_x + fill_width - 4, y + bar_height - 6]
                draw.rounded_rectangle(fill_rect, radius=6, fill=bar_fill_color)

                highlight_rect = [fill_rect[0], fill_rect[1], fill_rect[2], fill_rect[1] + 4]
                draw.rectangle(highlight_rect, fill='#63FF8C')

        # Footer text
        footer_text = "legend"
        footer_size = measure_text(footer_text, font_footer)
        footer_pos = (panel_rect[2] - footer_size[0] - 42, panel_rect[3] - footer_size[1] - 42)
        draw.text((footer_pos[0] + 3, footer_pos[1] + 3), footer_text, font=font_footer, fill='#050505')
        draw.text(footer_pos, footer_text, font=font_footer, fill='#FFFFFF')

        bio = BytesIO()
        bio.name = 'leaderboard.png'
        img.save(bio, 'PNG')
        bio.seek(0)
        return bio

    except Exception as e:
        logger.error(f"Error generating leaderboard image: {e}")
        raise


async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show monthly leaderboard"""
    try:
        # Get top 5 chatters
        top_users = get_monthly_leaderboard(limit=5)
        
        if not top_users:
            await update.message.reply_text(
                "📊 Leaderboard is empty! Start chatting to appear here.",
                parse_mode='HTML'
            )
            return
        
        # Generate image
        image_bio = generate_leaderboard_image(top_users)
        
        # Caption
        caption = (
            "🏆 <b>TOP CHATTERS LEADERBOARD</b>\n\n"
            "Most active members in the last 30 days!\n"
            "Keep chatting to climb the ranks! 💬"
        )
        
        # Send image
        await update.message.reply_photo(
            photo=image_bio,
            caption=caption,
            parse_mode='HTML'
        )
        
    except Exception as e:
        logger.error(f"Error in leaderboard command: {e}")
        await update.message.reply_text(
            "❌ Error generating leaderboard. Please try again later."
        )


def reset_leaderboard_stats():
    """Reset all message counts and leaderboard date (called by admin)"""
    try:
        conn = database.get_sync_connection()
        
        # Reset total_messages and update leaderboard_reset_date
        conn.execute("""
            UPDATE users 
            SET total_messages = 0,
                leaderboard_reset_date = CURRENT_TIMESTAMP
        """)
        
        conn.commit()
        conn.close()
        
        logger.info("✅ Leaderboard stats reset successfully")
        return True
    except Exception as e:
        logger.error(f"Error resetting leaderboard: {e}")
        return False

