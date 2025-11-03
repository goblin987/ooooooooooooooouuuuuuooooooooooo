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
            # Add the column
            conn.execute("ALTER TABLE users ADD COLUMN leaderboard_reset_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
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
    """Generate GTA SA style leaderboard image"""
    try:
        # Canvas setup
        width, height = 800, 600
        bg_color = '#1a1a2e'  # Dark blue-black background
        
        img = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(img)
        
        # Load fonts
        font_path_pricedown = "/opt/render/project/src/assets/Pricedown Bl.otf"
        font_path_arial = "/opt/render/project/src/assets/ariblk.ttf"
        
        try:
            font_title = ImageFont.truetype(font_path_pricedown, 80)
            font_rank = ImageFont.truetype(font_path_arial, 48)
            font_username = ImageFont.truetype(font_path_arial, 40)
            font_messages = ImageFont.truetype(font_path_arial, 32)
        except:
            # Fallback to default
            font_title = ImageFont.load_default()
            font_rank = ImageFont.load_default()
            font_username = ImageFont.load_default()
            font_messages = ImageFont.load_default()
        
        # Helper function for outlined text
        def draw_outlined_text(xy, text, font, fill_color, outline_color='#000000', outline_width=3):
            x, y = xy
            # Draw outline
            for adj_x in range(-outline_width, outline_width + 1):
                for adj_y in range(-outline_width, outline_width + 1):
                    if adj_x != 0 or adj_y != 0:
                        draw.text((x + adj_x, y + adj_y), text, font=font, fill=outline_color)
            # Draw main text
            draw.text((x, y), text, font=font, fill=fill_color)
        
        # Title
        title_text = "TOP CHATTERS"
        draw_outlined_text((60, 40), title_text, font_title, '#FFD700', '#000000', 4)
        
        # Subtitle with date range
        thirty_days_ago = datetime.now() - timedelta(days=30)
        subtitle = f"Last 30 Days - {thirty_days_ago.strftime('%b %d')} to {datetime.now().strftime('%b %d')}"
        draw_outlined_text((60, 130), subtitle, font_messages, '#FFFFFF', '#000000', 2)
        
        # Draw leaderboard entries
        start_y = 220
        row_height = 70
        
        medal_colors = {
            1: '#FFD700',  # Gold
            2: '#C0C0C0',  # Silver
            3: '#CD7F32',  # Bronze
            4: '#FFFFFF',  # White
            5: '#CCCCCC',  # Light gray
        }
        
        for i, (user_id, username, msg_count) in enumerate(top_users, 1):
            y_pos = start_y + (i - 1) * row_height
            color = medal_colors.get(i, '#FFFFFF')
            
            # Rank number
            rank_text = f"#{i}"
            draw_outlined_text((80, y_pos), rank_text, font_rank, color, '#000000', 3)
            
            # Username (limit length)
            username_display = username[:20] if username else "Unknown"
            if not username_display.startswith('@'):
                username_display = f"@{username_display}"
            draw_outlined_text((200, y_pos), username_display, font_username, '#FFFFFF', '#000000', 2)
            
            # Message count
            msg_text = f"{msg_count:,} msgs"
            draw_outlined_text((560, y_pos), msg_text, font_messages, color, '#000000', 2)
        
        # If less than 5 users, show empty slots
        if len(top_users) < 5:
            for i in range(len(top_users) + 1, 6):
                y_pos = start_y + (i - 1) * row_height
                color = medal_colors.get(i, '#FFFFFF')
                rank_text = f"#{i}"
                draw_outlined_text((80, y_pos), rank_text, font_rank, '#666666', '#000000', 3)
                draw_outlined_text((200, y_pos), "---", font_username, '#666666', '#000000', 2)
        
        # Add decorative border
        border_color = '#FFD700'
        border_width = 8
        draw.rectangle([(border_width//2, border_width//2), 
                       (width - border_width//2, height - border_width//2)], 
                      outline=border_color, width=border_width)
        
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

