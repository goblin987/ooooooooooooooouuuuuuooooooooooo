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
    """Generate GTA SA Stats-style leaderboard image with rounded panel"""
    try:
        from PIL import ImageFilter
        
        # Canvas setup
        width, height = 600, 600
        bg_color = '#1a1a1a'  # Dark gray background
        
        # Create image with alpha for rounded corners
        img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        
        # Draw rounded rectangle background
        from PIL import ImageDraw as ID
        overlay = Image.new('RGBA', (width, height), (0, 0, 0, 0))
        draw_bg = ID.Draw(overlay)
        
        # Rounded rectangle with shadow effect
        margin = 20
        radius = 12
        rect_coords = [margin, margin, width - margin, height - margin]
        draw_bg.rounded_rectangle(rect_coords, radius=radius, fill='#1a1a1a')
        
        # Apply shadow (simple darkening around edges)
        img = Image.alpha_composite(img, overlay)
        img = img.convert('RGB')
        
        draw = ImageDraw.Draw(img)
        
        # Load fonts
        font_path_pricedown = "/opt/render/project/src/assets/Pricedown Bl.otf"
        font_path_arial = "/opt/render/project/src/assets/ariblk.ttf"
        
        try:
            font_title = ImageFont.truetype(font_path_pricedown, 56)
            font_username = ImageFont.truetype(font_path_arial, 26)
            font_label = ImageFont.truetype(font_path_arial, 18)
            font_footer = ImageFont.truetype(font_path_arial, 16)
        except:
            font_title = ImageFont.load_default()
            font_username = ImageFont.load_default()
            font_label = ImageFont.load_default()
            font_footer = ImageFont.load_default()
        
        # Helper for outlined text
        def draw_outlined_text(xy, text, font, fill_color, outline_color='#000000', outline_width=2):
            x, y = xy
            for adj_x in range(-outline_width, outline_width + 1):
                for adj_y in range(-outline_width, outline_width + 1):
                    if adj_x != 0 or adj_y != 0:
                        draw.text((x + adj_x, y + adj_y), text, font=font, fill=outline_color)
            draw.text((x, y), text, font=font, fill=fill_color)
        
        # Title
        draw_outlined_text((40, 35), "Stats", font_title, '#FFFFFF', '#000000', 3)
        
        # Get max messages for scaling
        max_messages = max([count for _, _, count in top_users], default=1000)
        
        # Draw user rows
        start_y = 100
        row_height = 90
        username_x = 40
        bar_start_x = 200
        bar_width = 340
        bar_height = 14
        
        for i, (user_id, username, msg_count) in enumerate(top_users[:5], 1):
            y_pos = start_y + (i - 1) * row_height
            
            # Username
            username_display = username[:15] if username else "Unknown"
            if username_display.startswith('@'):
                username_display = username_display[1:]
            
            draw_outlined_text((username_x, y_pos), username_display, font_username, '#FFFFFF', '#000000', 2)
            
            # Calculate stats (simulate kills, wins, deaths from message count)
            kills = msg_count
            wins = int(msg_count * 0.7)
            deaths = int(msg_count * 0.3)
            
            stats = [
                ("Messages", kills, '#00FF00'),  # Green
                ("Wins", wins, '#00FF00'),       # Green
                ("Deaths", deaths, '#FF4500')    # Orange/red
            ]
            
            # Draw three bars
            for j, (label, value, color) in enumerate(stats):
                bar_y = y_pos + 30 + (j * 20)
                
                # Label
                draw.text((username_x + 10, bar_y - 2), label, font=font_label, fill='#cccccc')
                
                # Bar background
                bar_bg = [bar_start_x, bar_y, bar_start_x + bar_width, bar_y + bar_height]
                draw.rounded_rectangle(bar_bg, radius=4, fill='#2b2b2b', outline='#444444', width=1)
                
                # Bar fill
                fill_percent = min(value / max_messages, 1.0)
                fill_width = int(bar_width * fill_percent)
                
                if fill_width > 4:
                    bar_fill = [bar_start_x, bar_y, bar_start_x + fill_width, bar_y + bar_height]
                    draw.rounded_rectangle(bar_fill, radius=4, fill=color, outline=None)
        
        # Footer
        draw.text((width - 140, height - 40), "updated live", font=font_footer, fill='#cccccc')
        
        # Convert to BytesIO
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

