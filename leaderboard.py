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
        
        # Color palette - PREMIUM GTA SA theme with depth
        PANEL_COLOR_RGB = (10, 8, 6)      # Darker panel base for better contrast
        PANEL_ALPHA = 235                 # 92% opacity for premium solid look
        PANEL_BORDER_OUTER = '#000000'    # Pure black outer border
        PANEL_BORDER_INNER = '#555555'    # Lighter gray for subtle frame
        TEXT_COLOR = '#FFFFFF'            # Pure white text
        HEADER_COLOR = '#FFFFFF'          # White header
        HEADER_OUTLINE = '#000000'        # Black outline for header
        BAR_OUTLINE = '#1A1A1A'           # Very dark gray outline (softer than pure black)
        BAR_BG = '#2D2D2D'                # Darker background for more contrast
        BAR_FILL = '#A8A8A8'              # Slightly lighter gray for better visibility
        BAR_HIGHLIGHT = '#D4D4D4'         # Bright highlight for 3D effect
        BAR_SHADOW = '#1F1F1F'            # Dark shadow for inset effect
        BAR_RADIUS = 2                    # Very minimal rounding
        
        # Layout constants
        PANEL_MARGIN = 30
        PANEL_MARGIN_TOP = 120            # Much more margin at top = panel starts lower
        PANEL_MARGIN_BOTTOM = 100         # More margin at bottom = smaller panel
        PANEL_RADIUS = 12
        HEADER_X = 35
        HEADER_Y = 65                     # Much higher - sits above the panel box
        HEADER_FONT_SIZE = 90             # Slightly smaller for better fit
        ROW_START_Y = 140
        ROW_SPACING = 82
        LABEL_X = 35
        LABEL_FONT_SIZE = 42              # Bigger username labels (optimized size)
        BAR_X = 270
        BAR_WIDTH = 295
        BAR_HEIGHT = 20                   # Reduced from 28 to 20 (smaller bars)
        BAR_Y_OFFSET = 8                  # Align bars to center with text vertically
        FOOTER_MARGIN_RIGHT = 35
        FOOTER_MARGIN_BOTTOM = 30
        FOOTER_FONT_SIZE = 36

        # Load background image (same as /points)
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
                # Resize to canvas size with high-quality resampling
                if bg_img.size != (CANVAS_WIDTH, CANVAS_HEIGHT):
                    bg_img = bg_img.resize((CANVAS_WIDTH, CANVAS_HEIGHT), Image.Resampling.LANCZOS)
                img = bg_img.convert('RGB')
            else:
                raise FileNotFoundError("background3.jpg not found in any path")
                
        except Exception as e:
            logger.warning(f"Failed to load background3.jpg: {e}, using fallback color")
            # Fallback to solid color
            img = Image.new('RGB', (CANVAS_WIDTH, CANVAS_HEIGHT), '#3D3530')
        
        # Add subtle vignette for depth (same as /points - lighter touch)
        vignette = Image.new('RGBA', (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
        vignette_draw = ImageDraw.Draw(vignette)
        center_x, center_y = CANVAS_WIDTH // 2, CANVAS_HEIGHT // 2
        max_dist = math.sqrt(center_x**2 + center_y**2)
        for y in range(CANVAS_HEIGHT):
            for x in range(0, CANVAS_WIDTH, 4):  # sample every 4px for performance
                dist = math.sqrt((x - center_x)**2 + (y - center_y)**2)
                alpha = int((dist / max_dist) * 60)  # max 60 alpha at corners (lighter than before)
                if alpha > 0:
                    vignette_draw.point((x, y), fill=(0, 0, 0, alpha))
        
        # Composite vignette
        img = img.convert('RGBA')
        img = Image.alpha_composite(img, vignette)
        img = img.convert('RGB')
        
        # Will draw panel as overlay later
        draw = ImageDraw.Draw(img)

        # Create premium panel with depth and subtle gradient
        panel_overlay = Image.new('RGBA', (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
        panel_draw = ImageDraw.Draw(panel_overlay)
        
        panel_rect = [PANEL_MARGIN, PANEL_MARGIN_TOP, 
                     CANVAS_WIDTH - PANEL_MARGIN, CANVAS_HEIGHT - PANEL_MARGIN_BOTTOM]
        
        # Layer 1: Outer shadow for depth (soft)
        for i in range(8, 0, -1):
            alpha = int(30 * (i / 8.0))
            shadow_rect = [PANEL_MARGIN - i, PANEL_MARGIN_TOP - i,
                          CANVAS_WIDTH - PANEL_MARGIN + i, CANVAS_HEIGHT - PANEL_MARGIN_BOTTOM + i]
            panel_draw.rounded_rectangle(shadow_rect, radius=PANEL_RADIUS + i, 
                                        outline=(0, 0, 0, alpha), width=1)
        
        # Layer 2: Outer black border (solid, 4px)
        for i in range(4):
            border_rect = [PANEL_MARGIN + i, PANEL_MARGIN_TOP + i,
                          CANVAS_WIDTH - PANEL_MARGIN - i, CANVAS_HEIGHT - PANEL_MARGIN_BOTTOM - i]
            panel_draw.rounded_rectangle(border_rect, radius=PANEL_RADIUS - i, 
                                        outline=(0, 0, 0, 255), width=1)
        
        # Layer 3: Main panel (semi-transparent so background shows through)
        inner_panel = [PANEL_MARGIN + 4, PANEL_MARGIN_TOP + 4,
                      CANVAS_WIDTH - PANEL_MARGIN - 4, CANVAS_HEIGHT - PANEL_MARGIN_BOTTOM - 4]
        panel_color_rgba = PANEL_COLOR_RGB + (PANEL_ALPHA,)  # Semi-transparent (92% opacity)
        panel_draw.rounded_rectangle(inner_panel, radius=PANEL_RADIUS - 4, fill=panel_color_rgba)
        
        # Layer 4: Inner frame (subtle)
        frame_rect = [PANEL_MARGIN + 6, PANEL_MARGIN_TOP + 6,
                     CANVAS_WIDTH - PANEL_MARGIN - 6, CANVAS_HEIGHT - PANEL_MARGIN_BOTTOM - 6]
        inner_border_rgb = tuple(int(PANEL_BORDER_INNER[i:i+2], 16) for i in (1, 3, 5))
        panel_draw.rounded_rectangle(frame_rect, radius=PANEL_RADIUS - 6, 
                                     outline=inner_border_rgb + (100,), width=1)
        
        # Composite panel onto background
        img = img.convert('RGBA')
        img = Image.alpha_composite(img, panel_overlay)
        img = img.convert('RGB')
        
        # Redraw for content
        draw = ImageDraw.Draw(img)

        # Load fonts
        # CRITICAL: Use Old English/Gothic blackletter font for "Stats" header (like wireframe)
        font_paths_gothic = [
            "/opt/render/project/src/assets/OldEnglishFive.ttf",  # Custom (FIRST - most reliable)
            os.path.join(os.path.dirname(__file__), "assets", "OldEnglishFive.ttf"),  # Workspace
            "C:\\Windows\\Fonts\\OLDENGL.TTF",  # Old English Text MT (Windows)
            "/usr/share/fonts/truetype/ancient-scripts/OldEnglish.ttf",  # Linux
            "/usr/share/fonts/truetype/fonts-blackletter/UnifrakturMaguntia.ttf",  # Linux alt
            "/System/Library/Fonts/Supplemental/Old English Text MT.ttf",  # macOS
        ]
        
        font_title = None
        for path in font_paths_gothic:
            try:
                font_title = ImageFont.truetype(path, HEADER_FONT_SIZE)
                logger.info(f"Loaded gothic header font from: {path}")
                break
            except:
                continue
        
        # If no gothic font found, use Pricedown but log warning
        if not font_title:
            try:
                font_title = ImageFont.truetype("/opt/render/project/src/assets/Pricedown Bl.otf", HEADER_FONT_SIZE)
                logger.warning("Old English font not found, using Pricedown fallback (NOT authentic)")
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
            """Draw label with strong shadow for chunky wireframe look"""
            x, y = position
            # Strong black shadow (3px offset)
            draw.text((x + 3, y + 3), text, font=font, fill='#000000')
            # Main white text (triple-draw for extra boldness like wireframe)
            draw.text((x, y), text, font=font, fill=fill)
            draw.text((x + 0.5, y), text, font=font, fill=fill)
            draw.text((x, y + 0.5), text, font=font, fill=fill)

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

            # Draw premium bar with inset shadow and beveled edges
            bar_y = y + BAR_Y_OFFSET
            
            # Outer border (3px, dark gray)
            for i in range(3):
                border_rect = [BAR_X - i, bar_y - i, 
                              BAR_X + BAR_WIDTH + i, bar_y + BAR_HEIGHT + i]
                border_rgb = tuple(int(BAR_OUTLINE[j:j+2], 16) for j in (1, 3, 5))
                draw.rectangle(border_rect, outline=border_rgb, width=1)
            
            # Inner background with inset shadow
            inner_rect = [BAR_X + 3, bar_y + 3, BAR_X + BAR_WIDTH - 3, bar_y + BAR_HEIGHT - 3]
            bg_rgb = tuple(int(BAR_BG[i:i+2], 16) for i in (1, 3, 5))
            draw.rectangle(inner_rect, fill=bg_rgb)
            
            # Top and left inset shadows (darker)
            shadow_rgb = tuple(int(BAR_SHADOW[i:i+2], 16) for i in (1, 3, 5))
            draw.line([(BAR_X + 3, bar_y + 3), (BAR_X + BAR_WIDTH - 3, bar_y + 3)], 
                     fill=shadow_rgb, width=2)  # Top
            draw.line([(BAR_X + 3, bar_y + 3), (BAR_X + 3, bar_y + BAR_HEIGHT - 3)], 
                     fill=shadow_rgb, width=2)  # Left

            # Calculate fill
            fill_ratio = 0 if max_messages == 0 else min(max(message_count / max_messages, 0), 1)
            fill_width = int((BAR_WIDTH - 6) * fill_ratio)
            
            if fill_width > 8:
                # Main fill with smooth vertical gradient
                fill_rect = [BAR_X + 3, bar_y + 3, BAR_X + 3 + fill_width, bar_y + BAR_HEIGHT - 3]
                bar_height_inner = BAR_HEIGHT - 6
                
                fill_rgb = tuple(int(BAR_FILL[i:i+2], 16) for i in (1, 3, 5))
                highlight_rgb = tuple(int(BAR_HIGHLIGHT[i:i+2], 16) for i in (1, 3, 5))
                
                # Draw gradient with smooth interpolation
                for py in range(bar_height_inner):
                    if bar_height_inner > 0:
                        # More pronounced gradient (darker bottom, brighter top)
                        ratio = (py / bar_height_inner) ** 1.2  # Power curve for smoother gradient
                        color = tuple(int(highlight_rgb[i] * (1 - ratio) + fill_rgb[i] * ratio) for i in range(3))
                        line_y = bar_y + 3 + py
                        draw.line([(BAR_X + 3, line_y), (BAR_X + 3 + fill_width, line_y)], 
                                 fill=color, width=1)
                
                # Top highlight strip (beveled edge)
                if bar_height_inner > 4:
                    highlight_strip = [BAR_X + 3, bar_y + 3, BAR_X + 3 + fill_width, bar_y + 5]
                    draw.rectangle(highlight_strip, fill=highlight_rgb)

        # Draw footer "Apsisaugok"
        footer_text = "Apsisaugok"
        footer_width, footer_height = measure_text(footer_text, font_footer)
        footer_x = panel_rect[2] - footer_width - FOOTER_MARGIN_RIGHT
        footer_y = panel_rect[3] - footer_height - FOOTER_MARGIN_BOTTOM
        draw_label_with_shadow((footer_x, footer_y), footer_text, font_footer)

        # Add subtle PS2-style scanlines (very gentle)
        scanline_overlay = Image.new('RGBA', (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
        scanline_draw = ImageDraw.Draw(scanline_overlay)
        for y in range(0, CANVAS_HEIGHT, 4):  # Every 4 pixels for subtlety
            scanline_draw.line([(0, y), (CANVAS_WIDTH, y)], fill=(0, 0, 0, 8), width=1)  # Very subtle
        
        # Composite scanlines
        img = img.convert('RGBA')
        img = Image.alpha_composite(img, scanline_overlay)
        img = img.convert('RGB')

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

