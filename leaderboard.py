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
from PIL import Image, ImageDraw, ImageFont, ImageFilter
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
    """Generate GTA SA Stats-style leaderboard matching the wireframe exactly"""
    try:
        # Canvas dimensions
        CANVAS_WIDTH = 600
        CANVAS_HEIGHT = 600
        
        # Color palette (sampled from GTA SA stats screen)
        BG_COLOR = '#1A1612'          # Very dark brown/black background
        PANEL_COLOR = '#0D0C0B'        # Near black panel
        TEXT_COLOR = '#E8E8E8'         # Off-white text
        HEADER_OUTLINE = '#000000'     # Black outline for header
        BAR_OUTLINE = '#0A0A0A'        # Near black bar outline
        BAR_BG = '#2D2925'             # Dark gray-brown bar background
        BAR_FILL = '#8B8680'           # Light gray bar fill
        BAR_HIGHLIGHT = '#B8B3AD'      # Lighter gray bar highlight
        
        # Layout constants
        PANEL_MARGIN = 25
        PANEL_RADIUS = 15
        HEADER_X = 30
        HEADER_Y = 15
        HEADER_FONT_SIZE = 80
        ROW_START_Y = 110
        ROW_SPACING = 80
        LABEL_X = 30
        LABEL_FONT_SIZE = 32
        BAR_X = 260
        BAR_WIDTH = 310
        BAR_HEIGHT = 25
        BAR_Y_OFFSET = 3
        FOOTER_MARGIN_RIGHT = 35
        FOOTER_MARGIN_BOTTOM = 30
        FOOTER_FONT_SIZE = 32

        # Create base canvas
        img = Image.new('RGB', (CANVAS_WIDTH, CANVAS_HEIGHT), BG_COLOR)
        draw = ImageDraw.Draw(img)

        # Draw panel
        panel_rect = [PANEL_MARGIN, PANEL_MARGIN, 
                     CANVAS_WIDTH - PANEL_MARGIN, CANVAS_HEIGHT - PANEL_MARGIN]
        draw.rounded_rectangle(panel_rect, radius=PANEL_RADIUS, fill=PANEL_COLOR)

        # Load fonts
        font_path_pricedown = "/opt/render/project/src/assets/Pricedown Bl.otf"
        
        # Try multiple font paths for the stat labels
        font_paths_label = [
            "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",  # Linux
            "C:\\Windows\\Fonts\\impact.ttf",  # Windows
            "/System/Library/Fonts/Supplemental/Impact.ttf",  # macOS
            "/opt/render/project/src/assets/impact.ttf",  # Custom
        ]
        
        try:
            font_title = ImageFont.truetype(font_path_pricedown, HEADER_FONT_SIZE)
        except:
            logger.warning("Pricedown font not found, using default")
            font_title = ImageFont.load_default()
        
        font_label = None
        for path in font_paths_label:
            try:
                font_label = ImageFont.truetype(path, LABEL_FONT_SIZE)
                logger.info(f"Loaded label font from: {path}")
                break
            except:
                continue
        
        if not font_label:
            logger.warning("Impact font not found, using default")
            font_label = ImageFont.load_default()
        
        try:
            font_footer = ImageFont.truetype(font_paths_label[0] if font_paths_label else None, FOOTER_FONT_SIZE)
        except:
            font_footer = font_label

        def measure_text(text: str, font: ImageFont.FreeTypeFont):
            """Measure text dimensions"""
            try:
                bbox = font.getbbox(text)
                return bbox[2] - bbox[0], bbox[3] - bbox[1]
            except AttributeError:
                return font.getsize(text)

        def draw_outlined_text(position, text, font, fill, outline_fill='#000000', outline_width=5):
            """Draw text with thick outline"""
            x, y = position
            # Draw outline
            for dx in range(-outline_width, outline_width + 1):
                for dy in range(-outline_width, outline_width + 1):
                    if dx == 0 and dy == 0:
                        continue
                    draw.text((x + dx, y + dy), text, font=font, fill=outline_fill)
            # Draw main text
            draw.text((x, y), text, font=font, fill=fill)

        def draw_label_with_shadow(position, text, font, fill=TEXT_COLOR):
            """Draw label with subtle shadow"""
            x, y = position
            # Shadow
            draw.text((x + 2, y + 2), text, font=font, fill='#000000')
            # Main text
            draw.text((x, y), text, font=font, fill=fill)

        # Draw "Stats" header
        draw_outlined_text((HEADER_X, HEADER_Y), "Stats", font_title, TEXT_COLOR, 
                          HEADER_OUTLINE, outline_width=5)

        # Prepare rows (ensure exactly 5)
        rows = top_users[:5]
        while len(rows) < 5:
            rows.append((None, "Unknown", 0))

        max_messages = max([count for _, _, count in rows], default=1)

        # Draw each row
        for index, (_, username, message_count) in enumerate(rows):
            y = ROW_START_Y + index * ROW_SPACING

            # Format username
            display_name = username or "Unknown"
            if display_name.startswith('@'):
                display_name = display_name[1:]
            display_name = display_name[:14]  # Truncate to fit

            # Draw username label
            draw_label_with_shadow((LABEL_X, y), display_name, font_label)

            # Draw bar background with outline
            bar_y = y + BAR_Y_OFFSET
            bar_rect = [BAR_X, bar_y, BAR_X + BAR_WIDTH, bar_y + BAR_HEIGHT]
            
            # Outer black border (thick)
            draw.rectangle(bar_rect, fill=BAR_OUTLINE)
            
            # Inner background
            inner_rect = [BAR_X + 3, bar_y + 3, BAR_X + BAR_WIDTH - 3, bar_y + BAR_HEIGHT - 3]
            draw.rectangle(inner_rect, fill=BAR_BG)

            # Calculate and draw fill
            fill_ratio = 0 if max_messages == 0 else min(max(message_count / max_messages, 0), 1)
            fill_width = int((BAR_WIDTH - 6) * fill_ratio)
            
            if fill_width > 4:
                fill_rect = [BAR_X + 3, bar_y + 3, BAR_X + 3 + fill_width, bar_y + BAR_HEIGHT - 3]
                draw.rectangle(fill_rect, fill=BAR_FILL)
                
                # Top highlight strip
                if BAR_HEIGHT - 6 > 6:
                    highlight_rect = [BAR_X + 3, bar_y + 3, BAR_X + 3 + fill_width, bar_y + 6]
                    draw.rectangle(highlight_rect, fill=BAR_HIGHLIGHT)

        # Draw footer "Apsisaugok"
        footer_text = "Apsisaugok"
        footer_width, footer_height = measure_text(footer_text, font_footer)
        footer_x = panel_rect[2] - footer_width - FOOTER_MARGIN_RIGHT
        footer_y = panel_rect[3] - footer_height - FOOTER_MARGIN_BOTTOM
        draw_label_with_shadow((footer_x, footer_y), footer_text, font_footer)

        # Save to BytesIO
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

