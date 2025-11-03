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
        
        # Color palette - GTA SA AUTHENTIC orange/amber theme
        PANEL_COLOR_RGB = (15, 13, 11)    # Panel base color (will be made transparent)
        PANEL_ALPHA = 200                 # 78% opacity (200/255) for see-through effect
        PANEL_BORDER_OUTER = '#000000'    # Black outer border
        PANEL_BORDER_INNER = '#3A3631'    # Lighter inner border (frame effect)
        TEXT_COLOR = '#FFB366'            # GTA SA orange/amber text
        HEADER_COLOR = '#FFFFFF'          # White header with orange outline
        HEADER_OUTLINE = '#000000'        # Black outline for header
        BAR_OUTLINE = '#000000'           # Pure black bar outline
        BAR_BG = '#2A2622'                # Dark bar background
        BAR_FILL = '#D4A574'              # Warm tan/gold fill (GTA SA style)
        BAR_HIGHLIGHT = '#F0D9B5'         # Light gold highlight
        BAR_GLOW = '#FFB366'              # Orange glow effect
        
        # Layout constants
        PANEL_MARGIN = 30
        PANEL_RADIUS = 12
        HEADER_X = 35
        HEADER_Y = 20
        HEADER_FONT_SIZE = 96
        ROW_START_Y = 140
        ROW_SPACING = 82
        LABEL_X = 35
        LABEL_FONT_SIZE = 42              # Bigger username labels (optimized size)
        BAR_X = 270
        BAR_WIDTH = 295
        BAR_HEIGHT = 20                   # Reduced from 28 to 20 (smaller bars)
        BAR_Y_OFFSET = 5                  # Offset to align with larger text
        FOOTER_MARGIN_RIGHT = 35
        FOOTER_MARGIN_BOTTOM = 30
        FOOTER_FONT_SIZE = 36

        # Load background image
        try:
            # Try multiple paths for background3.jpg
            bg_paths = [
                os.path.join(os.path.dirname(__file__), "background3.jpg"),  # Workspace root
                "/opt/render/project/src/background3.jpg",  # Render deployment path
                "background3.jpg",  # Current directory
            ]
            
            bg_img = None
            for bg_path in bg_paths:
                if os.path.exists(bg_path):
                    bg_img = Image.open(bg_path)
                    logger.info(f"Loaded background from {bg_path}")
                    break
            
            if bg_img:
                # Resize to canvas size
                bg_img = bg_img.resize((CANVAS_WIDTH, CANVAS_HEIGHT), Image.Resampling.LANCZOS)
                img = bg_img.convert('RGB')
            else:
                raise FileNotFoundError("background3.jpg not found in any path")
                
        except Exception as e:
            logger.warning(f"Failed to load background3.jpg: {e}, using fallback color")
            # Fallback to solid color
            img = Image.new('RGB', (CANVAS_WIDTH, CANVAS_HEIGHT), '#3D3530')
        
        # Apply subtle gaussian blur to background (makes panel pop)
        img = img.filter(ImageFilter.GaussianBlur(2.5))
        
        # Add vignette effect (darken corners for depth)
        vignette = Image.new('RGBA', (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
        vignette_draw = ImageDraw.Draw(vignette)
        # Radial gradient vignette from edges
        for i in range(100):
            alpha = int((i / 100.0) * 120)  # Max 120 alpha at edges
            inset = int(i * 3)
            vignette_draw.rectangle(
                [inset, inset, CANVAS_WIDTH - inset, CANVAS_HEIGHT - inset],
                outline=(0, 0, 0, alpha)
            )
        
        # Composite vignette
        img = img.convert('RGBA')
        img = Image.alpha_composite(img, vignette)
        img = img.convert('RGB')
        
        # Will draw panel as overlay later
        draw = ImageDraw.Draw(img)

        # Create semi-transparent panel overlay (GTA SA style see-through effect)
        panel_overlay = Image.new('RGBA', (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
        panel_draw = ImageDraw.Draw(panel_overlay)
        
        panel_rect = [PANEL_MARGIN, PANEL_MARGIN, 
                     CANVAS_WIDTH - PANEL_MARGIN, CANVAS_HEIGHT - PANEL_MARGIN]
        
        # Layer 1: Outer black border (solid, 6px)
        border_color = PANEL_BORDER_OUTER + 'FF'  # Fully opaque black
        panel_draw.rounded_rectangle(panel_rect, radius=PANEL_RADIUS, fill=border_color)
        
        # Layer 2: Semi-transparent dark panel (inset by 6px)
        inner_panel = [PANEL_MARGIN + 6, PANEL_MARGIN + 6,
                      CANVAS_WIDTH - PANEL_MARGIN - 6, CANVAS_HEIGHT - PANEL_MARGIN - 6]
        panel_color_rgba = PANEL_COLOR_RGB + (PANEL_ALPHA,)  # Add alpha channel
        panel_draw.rounded_rectangle(inner_panel, radius=PANEL_RADIUS - 2, fill=panel_color_rgba)
        
        # Layer 3: Inner frame highlight (subtle, semi-transparent)
        frame_highlight = [PANEL_MARGIN + 8, PANEL_MARGIN + 8,
                          CANVAS_WIDTH - PANEL_MARGIN - 8, CANVAS_HEIGHT - PANEL_MARGIN - 8]
        # Convert hex to RGB + alpha
        inner_border_rgb = tuple(int(PANEL_BORDER_INNER[i:i+2], 16) for i in (1, 3, 5))
        panel_draw.rounded_rectangle(frame_highlight, radius=PANEL_RADIUS - 3, 
                                     outline=inner_border_rgb + (180,), width=2)
        
        # Composite semi-transparent panel onto background
        img = img.convert('RGBA')
        img = Image.alpha_composite(img, panel_overlay)
        img = img.convert('RGB')
        
        # Redraw for content
        draw = ImageDraw.Draw(img)

        # Load fonts
        # Try gothic/blackletter font for "Stats" header (more authentic GTA SA style)
        font_paths_gothic = [
            "/usr/share/fonts/truetype/ancient-scripts/OldEnglish.ttf",
            "C:\\Windows\\Fonts\\OLDENGL.TTF",  # Old English Text MT
            "/usr/share/fonts/truetype/fonts-blackletter/UnifrakturMaguntia.ttf",
            "/opt/render/project/src/assets/Pricedown Bl.otf",  # Fallback to Pricedown
        ]
        
        font_title = None
        for path in font_paths_gothic:
            try:
                font_title = ImageFont.truetype(path, HEADER_FONT_SIZE)
                logger.info(f"Loaded gothic header font from: {path}")
                break
            except:
                continue
        
        if not font_title:
            try:
                font_title = ImageFont.truetype("/opt/render/project/src/assets/Pricedown Bl.otf", HEADER_FONT_SIZE)
            except:
                logger.warning("No header font found, using default")
                font_title = ImageFont.load_default()
        
        # Try multiple font paths for the stat labels (BIGGER SIZE)
        font_paths_label = [
            "/opt/render/project/src/assets/impact.ttf",  # Custom (FIRST - most reliable)
            os.path.join(os.path.dirname(__file__), "assets", "impact.ttf"),  # Workspace assets
            "/usr/share/fonts/truetype/msttcorefonts/Impact.ttf",  # Linux
            "C:\\Windows\\Fonts\\impact.ttf",  # Windows
            "/System/Library/Fonts/Supplemental/Impact.ttf",  # macOS
        ]
        
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
        
        # Footer uses same font as labels
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
            """Draw label with GTA SA style glow and shadow"""
            x, y = position
            # Subtle orange glow (multiple layers)
            glow_color = BAR_GLOW
            for offset in [(2, 2), (1, 1), (-1, 1), (1, -1)]:
                glow_rgb = tuple(int(glow_color[i:i+2], 16) for i in (1, 3, 5, 7)) if len(glow_color) == 9 else tuple(int(glow_color[i:i+2], 16) for i in (1, 3, 5))
                draw.text((x + offset[0], y + offset[1]), text, font=font, fill=glow_rgb)
            # Black shadow for depth
            draw.text((x + 2, y + 2), text, font=font, fill='#000000')
            # Main text (draw twice for extra boldness)
            draw.text((x, y), text, font=font, fill=fill)
            draw.text((x + 0.5, y), text, font=font, fill=fill)

        # Draw "Stats" header with white text and orange outline
        draw_outlined_text((HEADER_X, HEADER_Y), "Stats", font_title, HEADER_COLOR, 
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

            # Draw bar with GTA SA style gradient and glow
            bar_y = y + BAR_Y_OFFSET
            bar_rect = [BAR_X, bar_y, BAR_X + BAR_WIDTH, bar_y + BAR_HEIGHT]
            
            # Outer black border (4px thick for visibility)
            draw.rectangle(bar_rect, fill=BAR_OUTLINE)
            
            # Inner dark background
            inner_rect = [BAR_X + 4, bar_y + 4, BAR_X + BAR_WIDTH - 4, bar_y + BAR_HEIGHT - 4]
            draw.rectangle(inner_rect, fill=BAR_BG)

            # Calculate fill
            fill_ratio = 0 if max_messages == 0 else min(max(message_count / max_messages, 0), 1)
            fill_width = int((BAR_WIDTH - 8) * fill_ratio)
            
            if fill_width > 6:
                # Draw subtle glow behind bar (orange)
                glow_rect = [BAR_X + 2, bar_y + 2, BAR_X + 2 + fill_width + 2, bar_y + BAR_HEIGHT - 2]
                glow_rgb = tuple(int(BAR_GLOW[i:i+2], 16) for i in (1, 3, 5))
                glow_overlay = Image.new('RGBA', (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
                glow_draw = ImageDraw.Draw(glow_overlay)
                glow_draw.rectangle(glow_rect, fill=glow_rgb + (40,))  # Very subtle glow
                img_temp = img.convert('RGBA')
                img = Image.alpha_composite(img_temp, glow_overlay).convert('RGB')
                draw = ImageDraw.Draw(img)
                
                # Main fill with gradient (darker bottom, lighter top)
                fill_rect = [BAR_X + 4, bar_y + 4, BAR_X + 4 + fill_width, bar_y + BAR_HEIGHT - 4]
                bar_height_inner = BAR_HEIGHT - 8
                
                # Draw gradient (pixel by pixel for smooth effect)
                fill_rgb = tuple(int(BAR_FILL[i:i+2], 16) for i in (1, 3, 5))
                highlight_rgb = tuple(int(BAR_HIGHLIGHT[i:i+2], 16) for i in (1, 3, 5))
                
                for py in range(bar_height_inner):
                    ratio = py / bar_height_inner
                    # Interpolate between highlight (top) and fill (bottom)
                    color = tuple(int(highlight_rgb[i] * (1 - ratio) + fill_rgb[i] * ratio) for i in range(3))
                    line_y = bar_y + 4 + py
                    draw.line([(BAR_X + 4, line_y), (BAR_X + 4 + fill_width, line_y)], fill=color, width=1)

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
        # Get top 5 chatters (synchronous is fine, it's fast)
        top_users = get_monthly_leaderboard(limit=5)
        
        if not top_users:
            await update.message.reply_text(
                "📊 Leaderboard is empty! Start chatting to appear here.",
                parse_mode='HTML'
            )
            return
        
        # Generate image (synchronous is fine, PIL is fast)
        image_bio = generate_leaderboard_image(top_users)
        
        # Reset BytesIO position to start
        image_bio.seek(0)
        
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
        logger.error(f"Error in leaderboard command: {e}", exc_info=True)
        try:
            await update.message.reply_text(
                "❌ Error generating leaderboard. Please try again later."
            )
        except:
            pass  # Avoid error on error


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

