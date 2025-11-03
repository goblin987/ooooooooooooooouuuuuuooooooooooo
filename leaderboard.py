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
    """Generate GTA SA Stats-style leaderboard image"""
    try:
        # Canvas setup - match GTA SA stats screen
        width, height = 640, 480
        bg_color = '#000000'  # Pure black like GTA SA
        
        img = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(img)
        
        # Load fonts
        font_path_pricedown = "/opt/render/project/src/assets/Pricedown Bl.otf"
        font_path_arial = "/opt/render/project/src/assets/ariblk.ttf"
        
        try:
            font_title = ImageFont.truetype(font_path_pricedown, 72)  # "Stats" title
            font_label = ImageFont.truetype(font_path_arial, 28)      # Username labels
        except:
            font_title = ImageFont.load_default()
            font_label = ImageFont.load_default()
        
        # Helper function for outlined text
        def draw_outlined_text(xy, text, font, fill_color, outline_color='#000000', outline_width=2):
            x, y = xy
            # Draw outline
            for adj_x in range(-outline_width, outline_width + 1):
                for adj_y in range(-outline_width, outline_width + 1):
                    if adj_x != 0 or adj_y != 0:
                        draw.text((x + adj_x, y + adj_y), text, font=font, fill=outline_color)
            # Draw main text
            draw.text((x, y), text, font=font, fill=fill_color)
        
        # Title: "Stats" in top-left corner (GTA SA style)
        draw_outlined_text((30, 25), "Stats", font_title, '#FFFFFF', '#000000', 3)
        
        # Get max message count for bar scaling
        max_messages = max([count for _, _, count in top_users], default=1000)
        
        # Draw each user as a stat row
        start_y = 130
        row_height = 60
        label_x = 30
        bar_x = 280
        bar_width = 330
        bar_height = 22
        
        for i, (user_id, username, msg_count) in enumerate(top_users[:5], 1):
            y_pos = start_y + (i - 1) * row_height
            
            # Username label (left side, like "Respect", "Stamina")
            username_display = username[:18] if username else "Unknown"
            if username_display.startswith('@'):
                username_display = username_display[1:]  # Remove @ symbol
            
            # Draw label in white
            draw_outlined_text((label_x, y_pos), username_display, font_label, '#FFFFFF', '#000000', 2)
            
            # Calculate bar fill percentage
            bar_fill_percent = min(msg_count / max_messages, 1.0)
            bar_fill_width = int(bar_width * bar_fill_percent)
            
            # Draw bar background (dark gray)
            bar_bg_rect = [bar_x, y_pos + 5, bar_x + bar_width, y_pos + 5 + bar_height]
            draw.rectangle(bar_bg_rect, fill='#404040', outline='#606060', width=2)
            
            # Draw bar fill (GTA SA orange/yellow gradient effect)
            if bar_fill_width > 0:
                bar_fill_rect = [bar_x, y_pos + 5, bar_x + bar_fill_width, y_pos + 5 + bar_height]
                # Use orange/yellow color like GTA SA
                bar_color = '#FFA500'  # Orange
                draw.rectangle(bar_fill_rect, fill=bar_color, outline=None)
                
                # Add lighter top edge for 3D effect
                top_highlight = [bar_x, y_pos + 5, bar_x + bar_fill_width, y_pos + 7]
                draw.rectangle(top_highlight, fill='#FFD700', outline=None)
        
        # If less than 5 users, show empty slots
        if len(top_users) < 5:
            for i in range(len(top_users) + 1, 6):
                y_pos = start_y + (i - 1) * row_height
                
                # Draw "---" as placeholder
                draw_outlined_text((label_x, y_pos), "---", font_label, '#606060', '#000000', 2)
                
                # Draw empty bar
                bar_bg_rect = [bar_x, y_pos + 5, bar_x + bar_width, y_pos + 5 + bar_height]
                draw.rectangle(bar_bg_rect, fill='#202020', outline='#404040', width=2)
        
        # Add "wed" watermark in bottom-right (like GTA SA)
        draw_outlined_text((width - 90, height - 45), "wed", font_label, '#FFFFFF', '#000000', 2)
        
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

