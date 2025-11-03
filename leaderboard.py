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
        from PIL import ImageFilter

        width, height = 600, 600
        base_color = '#000000'
        panel_color = '#1D1A17'
        inner_color = '#221F1B'
        panel_margin = 20
        radius = 12

        # Base canvas
        img = Image.new('RGB', (width, height), base_color)
        draw = ImageDraw.Draw(img)

        # Panel background with subtle depth
        panel_rect = [panel_margin, panel_margin, width - panel_margin, height - panel_margin]
        draw.rounded_rectangle(panel_rect, radius=radius, fill=panel_color)

        inner_rect = [panel_margin + 6, panel_margin + 6, width - panel_margin - 6, height - panel_margin - 6]
        draw.rounded_rectangle(inner_rect, radius=radius - 2, fill=inner_color)

        # Soft shadow around panel edges
        shadow = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        shadow_draw = ImageDraw.Draw(shadow)
        shadow_draw.rounded_rectangle(panel_rect, radius=radius, outline=(0, 0, 0, 90), width=8)
        shadow = shadow.filter(ImageFilter.GaussianBlur(6))
        img = Image.alpha_composite(img.convert('RGBA'), shadow).convert('RGB')
        draw = ImageDraw.Draw(img)

        # Load fonts
        font_path_pricedown = "/opt/render/project/src/assets/Pricedown Bl.otf"
        font_path_arial = "/opt/render/project/src/assets/ariblk.ttf"

        try:
            font_title = ImageFont.truetype(font_path_pricedown, 96)
            font_username = ImageFont.truetype(font_path_arial, 34)
            font_footer = ImageFont.truetype(font_path_arial, 36)
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

        def draw_shadowed_text(xy, text, font, fill, shadow_offset=(2, 2), shadow_fill='#000000', outline=0):
            x, y = xy
            if outline > 0:
                for dx in range(-outline, outline + 1):
                    for dy in range(-outline, outline + 1):
                        if dx == 0 and dy == 0:
                            continue
                        draw.text((x + dx, y + dy), text, font=font, fill=shadow_fill)
            if shadow_offset:
                draw.text((x + shadow_offset[0], y + shadow_offset[1]), text, font=font, fill=shadow_fill)
            draw.text((x, y), text, font=font, fill=fill)

        # Header text
        title_position = (panel_margin + 45, panel_margin + 35)
        draw_shadowed_text(title_position, "Stats", font_title, '#FFFFFF', outline=3)

        # Prepare data (ensure 5 rows)
        displayed_users = top_users[:5]
        while len(displayed_users) < 5:
            displayed_users.append((None, "Unknown", 0))

        max_messages = max([count for _, _, count in displayed_users], default=1)

        # Layout constants
        row_height = 95
        start_y = panel_margin + 130
        username_x = panel_margin + 45
        bar_x = panel_margin + 260
        bar_width = 270
        bar_height = 26

        for index, (_, username, msg_count) in enumerate(displayed_users):
            row_y = start_y + index * row_height

            # Username styling
            username_text = username or "Unknown"
            if username_text.startswith('@'):
                username_text = username_text[1:]
            username_text = username_text[:14]

            draw_shadowed_text((username_x, row_y), username_text, font_username, '#FFFFFF', outline=2)

            # Bar background
            bar_top = row_y + 5
            bar_rect = [bar_x, bar_top, bar_x + bar_width, bar_top + bar_height]
            draw.rounded_rectangle(bar_rect, radius=6, fill='#3C3A36', outline='#0F0F0F', width=3)

            # Filled portion
            fill_ratio = msg_count / max_messages if max_messages else 0
            fill_ratio = max(0.0, min(fill_ratio, 1.0))
            fill_width = int(bar_width * fill_ratio)

            if fill_width > 4:
                fill_rect = [bar_x + 3, bar_top + 3, bar_x + fill_width - 3, bar_top + bar_height - 3]
                draw.rounded_rectangle(fill_rect, radius=4, fill='#38F764')

                # top highlight
                if fill_rect[3] - fill_rect[1] > 4:
                    highlight_rect = [fill_rect[0], fill_rect[1], fill_rect[2], fill_rect[1] + 4]
                    draw.rectangle(highlight_rect, fill='#5BFF8A')

            # optional message count (right aligned if space)
            if msg_count and fill_width > 120:
                count_text = f"{msg_count:,}"
                text_width, _ = measure_text(count_text, font_username)
                text_x = min(bar_x + fill_width - 10 - text_width, bar_x + bar_width - text_width - 10)
                draw_shadowed_text((text_x, row_y + 2), count_text, font_username, '#E0E0E0', shadow_offset=(1, 1))

        # Footer label
        footer_text = "legend"
        footer_width, footer_height = measure_text(footer_text, font_footer)
        footer_position = (panel_rect[2] - footer_width - 40, panel_rect[3] - footer_height - 40)
        draw_shadowed_text(footer_position, footer_text, font_footer, '#FFFFFF', outline=2)

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

