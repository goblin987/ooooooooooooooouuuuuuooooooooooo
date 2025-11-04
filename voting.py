#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Voting System - Seller Voting & Leaderboards
PRESERVES ALL VOTING DATA from old bot (votes_weekly.pkl, votes_monthly.pkl, votes_alltime.pkl)
"""

import logging
import os
import math
from datetime import datetime, timedelta
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import telegram
from utils import data_manager
from config import TIMEZONE, ADMIN_CHAT_ID
from database import database
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from io import BytesIO

logger = logging.getLogger(__name__)

# Environment variables for voting group
VOTING_GROUP_CHAT_ID = int(os.getenv('VOTING_GROUP_CHAT_ID', '0'))
VOTING_GROUP_LINK = os.getenv('VOTING_GROUP_LINK', '')

if not VOTING_GROUP_CHAT_ID:
    logger.warning("⚠️ VOTING_GROUP_CHAT_ID not set - voting features will be limited")
if not VOTING_GROUP_LINK:
    logger.warning("⚠️ VOTING_GROUP_LINK not set - /balsuoti will not work")

# Load voting data (PRESERVES OLD DATA!)
votes_weekly = data_manager.load_data('votes_weekly.pkl', defaultdict(int))
votes_monthly = data_manager.load_data('votes_monthly.pkl', defaultdict(list))
votes_alltime = data_manager.load_data('votes_alltime.pkl', defaultdict(int))
vote_history = data_manager.load_data('vote_history.pkl', defaultdict(list))
last_vote_attempt = data_manager.load_data('last_vote_attempt.pkl', {})
voters = data_manager.load_data('voters.pkl', set())

# Media for featured seller
featured_media_id = data_manager.load_data('featured_media_id.pkl', None)
featured_media_type = data_manager.load_data('featured_media_type.pkl', None)
last_addftbaryga_message = ""

# Media for barygos command
barygos_media_id = data_manager.load_data('barygos_media_id.pkl', None)
barygos_media_type = data_manager.load_data('barygos_media_type.pkl', None)
last_addftbaryga2_message = ""

# Voting message ID for pinning
voting_message_id = data_manager.load_data('voting_message_id.pkl', None)

# Trusted sellers list
trusted_sellers = data_manager.load_data('trusted_sellers.pkl', [])

# Helper functions for points (USE DATABASE, not pickle!)
def get_user_points(user_id: int) -> int:
    """Get user points from database"""
    try:
        conn = database.get_sync_connection()
        cursor = conn.execute(
            "SELECT points FROM users WHERE user_id = ?",
            (user_id,)
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0
    except Exception as e:
        logger.error(f"Error getting points: {e}")
        return 0


def update_user_points(user_id: int, points: int) -> bool:
    """Update user points in database"""
    try:
        conn = database.get_sync_connection()
        conn.execute(
            "INSERT OR REPLACE INTO users (user_id, points) VALUES (?, ?)",
            (user_id, points)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error updating points: {e}")
        return False

logger.info(f"📊 Voting data loaded:")
logger.info(f"  - Weekly votes: {sum(votes_weekly.values())} total")
logger.info(f"  - All-time votes: {sum(votes_alltime.values())} total")
logger.info(f"  - Voters: {len(voters)} unique")
logger.info(f"  - Trusted sellers: {len(trusted_sellers)}")


# ============================================================================
# BALSUOTI COMMAND - Link to voting group
# ============================================================================

async def balsuoti_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send link to voting group"""
    chat_id = update.message.chat_id
    
    if not VOTING_GROUP_LINK:
        await update.message.reply_text("⚠️ Balsavimo grupė dar nenustatyta!")
        return
    
    msg = await update.message.reply_text(
        f'<a href="{VOTING_GROUP_LINK}">Spauskite čia</a> norėdami eiti į balsavimo grupę.\n'
        f'Ten rasite balsavimo mygtukus!',
        parse_mode='HTML'
    )
    
    # Auto-delete after 45 seconds
    context.job_queue.run_once(
        lambda c: c.bot.delete_message(chat_id=chat_id, message_id=msg.message_id),
        45
    )


# ============================================================================
# VOTE BUTTON HANDLER
# ============================================================================

async def handle_vote_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle voting button clicks"""
    query = update.callback_query
    if not query:
        return
    
    user_id = query.from_user.id
    if query.message is None:
        await query.answer("Klaida: Balsavimo žinutė nerasta.")
        return
    
    chat_id = query.message.chat_id
    data = query.data
    
    logger.info(f"Vote attempt by user {user_id}, callback_data={data}")
    
    # Check if callback is for voting
    if not data.startswith("vote_"):
        return
    
    seller = data.replace("vote_", "")
    
    # Check if seller is still valid
    if seller not in trusted_sellers:
        await query.answer("Šis pardavėjas nebegalioja!")
        return
    
    # Check weekly cooldown (user can vote once per week)
    now = datetime.now(TIMEZONE)
    last_vote = last_vote_attempt.get(user_id, datetime.min.replace(tzinfo=TIMEZONE))
    cooldown_remaining = timedelta(days=7) - (now - last_vote)
    
    if cooldown_remaining > timedelta(0):
        hours_left = max(1, int(cooldown_remaining.total_seconds() // 3600))
        await query.answer(f"Tu jau balsavai! Liko ~{hours_left} valandų iki kito balsavimo.")
        return
    
    # Process vote
    votes_weekly.setdefault(seller, 0)
    votes_alltime.setdefault(seller, 0)
    votes_monthly.setdefault(seller, [])
    vote_history.setdefault(seller, [])
    
    votes_weekly[seller] += 1
    votes_monthly[seller].append((now, 1))
    votes_alltime[seller] += 1
    voters.add(user_id)
    vote_history[seller].append((user_id, "up", "Button vote", now))
    
    # Add 50 points for voting (no XP, just money points)
    database.add_user_points(user_id, 50)
    
    last_vote_attempt[user_id] = now
    
    # Save voting data (preserve pickle files)
    data_manager.save_data(votes_weekly, 'votes_weekly.pkl')
    data_manager.save_data(votes_monthly, 'votes_monthly.pkl')
    data_manager.save_data(votes_alltime, 'votes_alltime.pkl')
    data_manager.save_data(vote_history, 'vote_history.pkl')
    data_manager.save_data(last_vote_attempt, 'last_vote_attempt.pkl')
    data_manager.save_data(voters, 'voters.pkl')
    
    # Success message
    success_msg = "✅ Ačiū už jūsų balsą!\n💰 +50 points"
    await query.answer(success_msg)
    
    # Get voter info
    if query.from_user.username:
        voter_username = f"@{query.from_user.username}"
    elif query.from_user.first_name:
        voter_username = query.from_user.first_name
    else:
        voter_username = f"Vartotojas {user_id}"
    
    # Calculate next vote time
    next_vote_time = now + timedelta(days=7)
    next_vote_formatted = next_vote_time.strftime("%Y-%m-%d %H:%M")
    
    # Get current counts
    seller_name = seller[1:] if seller.startswith('@') else seller
    weekly_votes = votes_weekly.get(seller, 0)
    alltime_votes = votes_alltime.get(seller, 0)
    
    # Send confirmation
    confirmation_text = f"🗳️ {voter_username} balsavo už {seller_name} (+15 tšk)\n"
    confirmation_text += f"📊 Savaitė: {weekly_votes} | Viso: {alltime_votes}\n"
    confirmation_text += f"⏰ Kitas balsas: {next_vote_formatted}"
    
    try:
        confirmation_msg = await context.bot.send_message(
            chat_id=VOTING_GROUP_CHAT_ID,
            text=confirmation_text
        )
        # Auto-delete after 35 seconds
        context.job_queue.run_once(
            lambda c: c.bot.delete_message(chat_id=VOTING_GROUP_CHAT_ID, message_id=confirmation_msg.message_id),
            35
        )
    except Exception as e:
        logger.error(f"Failed to send vote confirmation: {e}")


# ============================================================================
# BARYGOS COMMAND - Leaderboards
# ============================================================================

def generate_barygos_text() -> str:
    """Generate barygos leaderboard text (reusable for command and auto-post)"""
    now = datetime.now(TIMEZONE)
    
    # Create header
    header = "🏆 PARDAVĖJŲ REITINGAI 🏆\n"
    header += f"📅 {now.strftime('%Y-%m-%d %H:%M')}\n"
    header += "=" * 26 + "\n\n"
    
    # Add custom admin message if exists
    if last_addftbaryga2_message:
        header += f"📢 {last_addftbaryga2_message}\n\n"
    
    # Weekly Leaderboard
    weekly_board = "🔥 SAVAITĖS ČEMPIONAI 🔥\n"
    weekly_board += f"📊 {now.strftime('%V savaitė')}\n\n"
    
    if not votes_weekly:
        weekly_board += "😴 Dar nėra balsų šią savaitę\n\n"
    else:
        sorted_weekly = sorted(votes_weekly.items(), key=lambda x: x[1], reverse=True)
        for i, (vendor, score) in enumerate(sorted_weekly[:10], 1):
            icon = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "🏅" if i <= 5 else "📈"
            vendor_name = vendor[1:] if vendor.startswith('@') else vendor
            weekly_board += f"{icon} {i}. {vendor_name} - {score} balsų\n"
    
    weekly_board += "\n" + "<><><><><><><><><><><><><>\n\n"
    
    # Monthly Leaderboard
    monthly_board = "🗓️ MĖNESIO LYDERIAI 🗓️\n"
    monthly_board += f"📊 {now.strftime('%B %Y')}\n\n"
    
    # Calculate current month totals
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    monthly_totals = defaultdict(int)
    for vendor, votes_list in votes_monthly.items():
        current_month_votes = [(ts, s) for ts, s in votes_list if ts >= month_start]
        monthly_totals[vendor] = sum(s for _, s in current_month_votes)
    
    if not monthly_totals:
        monthly_board += "🌱 Naujas mėnuo - nauji tikslai\n\n"
    else:
        sorted_monthly = sorted(monthly_totals.items(), key=lambda x: x[1], reverse=True)
        for i, (vendor, score) in enumerate(sorted_monthly[:10], 1):
            icon = "👑" if i == 1 else "💎" if i == 2 else "⭐" if i == 3 else "🌟"
            vendor_name = vendor[1:] if vendor.startswith('@') else vendor
            monthly_board += f"{icon} {i}. {vendor_name} - {score} balsų\n"
    
    monthly_board += "\n" + "<><><><><><><><><><><><><>\n\n"
    
    # All-Time Hall of Fame
    alltime_board = "🌟 VISŲ LAIKŲ LEGENDOS 🌟\n"
    alltime_board += "📈 Istoriniai rekordai\n\n"
    
    if not votes_alltime:
        alltime_board += "🎯 Istorija tik prasideda\n\n"
    else:
        sorted_alltime = sorted(votes_alltime.items(), key=lambda x: x[1], reverse=True)
        for i, (vendor, score) in enumerate(sorted_alltime[:10], 1):
            icon = "🏆" if i == 1 else "🎖️" if i == 2 else "🎗️" if i == 3 else "💫" if score >= 100 else "⚡" if score >= 50 else "🔸"
            vendor_name = vendor[1:] if vendor.startswith('@') else vendor
            alltime_board += f"{icon} {i}. {vendor_name} - {score} balsų\n"
    
    alltime_board += "\n" + "<><><><><><><><><><><><><>\n\n"
    
    # Statistics footer
    footer = "📊 STATISTIKOS\n\n"
    
    total_weekly_votes = sum(votes_weekly.values())
    total_monthly_votes = sum(monthly_totals.values())
    total_alltime_votes = sum(votes_alltime.values())
    active_sellers = len([v for v in votes_weekly.values() if v > 0])
    
    footer += f"📈 Savaitės balsų: {total_weekly_votes}\n"
    footer += f"📅 Mėnesio balsų: {total_monthly_votes}\n"
    footer += f"🌟 Visų laikų balsų: {total_alltime_votes}\n"
    footer += f"👥 Aktyvūs pardavėjai: {active_sellers}\n\n"
    
    # Next reset times
    next_sunday = now + timedelta(days=(6 - now.weekday()))
    next_month = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
    
    footer += "⏰ KITAS RESTARTAS\n\n"
    footer += f"• Savaitės: {next_sunday.strftime('%m-%d %H:%M')}\n"
    footer += f"• Mėnesio: {next_month.strftime('%m-%d %H:%M')}\n\n"
    footer += "💡 Balsuok kas savaitę už mėgstamus pardavėjus!"
    
    # Combine all sections
    full_message = header + weekly_board + monthly_board + alltime_board + footer
    return full_message


def generate_barygos_image() -> BytesIO:
    """Generate GTA SA-style barygos leaderboard image (1200x1200px)"""
    try:
        from datetime import datetime
        
        # Canvas dimensions - 2x larger than /stats for more entries
        CANVAS_WIDTH = 800
        CANVAS_HEIGHT = 1600
        
        # Color palette - same as /stats leaderboard
        PANEL_COLOR_RGB = (10, 8, 6)
        PANEL_ALPHA = 235
        PANEL_BORDER_OUTER = '#000000'
        PANEL_BORDER_INNER = '#555555'
        TEXT_COLOR = '#FFFFFF'
        HEADER_COLOR = '#FFFFFF'
        HEADER_OUTLINE = '#000000'
        
        # Layout constants (Vertical scroll-friendly, portrait)
        PANEL_MARGIN = 30
        PANEL_MARGIN_TOP = 140  # Room for header
        PANEL_MARGIN_BOTTOM = 40
        PANEL_RADIUS = 16
        HEADER_X = 40
        HEADER_Y = 40  # "Barygos" at top
        HEADER_FONT_SIZE = 110  # Big header
        
        # Section layout - Single column, vertical
        SECTION_START_Y = 180
        SECTION_SPACING = 480  # Space for each section (header + 7 entries)
        SECTION_HEADER_SIZE = 50  # Big section headers
        ENTRY_FONT_SIZE = 40  # Large for mobile readability
        ENTRY_SPACING = 50  # Spacing between entries
        LABEL_X = 55  # Left padding
        SCORE_X = 700  # Right-aligned scores
        FOOTER_FONT_SIZE = 38
        
        # Load background (same as /stats)
        bg_img = None
        bg_paths = [
            os.path.join(os.path.dirname(__file__), "background4.jpg"),
            "/opt/render/project/src/background4.jpg",
            "background4.jpg",
        ]
        
        for bg_path in bg_paths:
            if os.path.exists(bg_path):
                bg_img = Image.open(bg_path)
                break
        
        if bg_img:
            if bg_img.size != (CANVAS_WIDTH, CANVAS_HEIGHT):
                bg_img = bg_img.resize((CANVAS_WIDTH, CANVAS_HEIGHT), Image.Resampling.LANCZOS)
            img = bg_img.convert('RGB')
        else:
            img = Image.new('RGB', (CANVAS_WIDTH, CANVAS_HEIGHT), '#3D3530')
        
        # Add vignette
        vignette = Image.new('RGBA', (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
        vignette_draw = ImageDraw.Draw(vignette)
        center_x, center_y = CANVAS_WIDTH // 2, CANVAS_HEIGHT // 2
        max_dist = math.sqrt(center_x**2 + center_y**2)
        for y in range(CANVAS_HEIGHT):
            for x in range(0, CANVAS_WIDTH, 4):
                dist = math.sqrt((x - center_x)**2 + (y - center_y)**2)
                alpha = int((dist / max_dist) * 60)
                if alpha > 0:
                    vignette_draw.point((x, y), fill=(0, 0, 0, alpha))
        
        img = img.convert('RGBA')
        img = Image.alpha_composite(img, vignette)
        img = img.convert('RGB')
        
        draw = ImageDraw.Draw(img)
        
        # Create panel overlay
        panel_overlay = Image.new('RGBA', (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
        panel_draw = ImageDraw.Draw(panel_overlay)
        
        panel_rect = [PANEL_MARGIN, PANEL_MARGIN_TOP,
                     CANVAS_WIDTH - PANEL_MARGIN, CANVAS_HEIGHT - PANEL_MARGIN_BOTTOM]
        
        # Outer shadow
        for i in range(10, 0, -1):
            alpha = int(30 * (i / 10.0))
            shadow_rect = [PANEL_MARGIN - i, PANEL_MARGIN_TOP - i,
                          CANVAS_WIDTH - PANEL_MARGIN + i, CANVAS_HEIGHT - PANEL_MARGIN_BOTTOM + i]
            panel_draw.rounded_rectangle(shadow_rect, radius=PANEL_RADIUS + i,
                                        outline=(0, 0, 0, alpha), width=1)
        
        # Border
        for i in range(5):
            border_rect = [PANEL_MARGIN + i, PANEL_MARGIN_TOP + i,
                          CANVAS_WIDTH - PANEL_MARGIN - i, CANVAS_HEIGHT - PANEL_MARGIN_BOTTOM - i]
            panel_draw.rounded_rectangle(border_rect, radius=PANEL_RADIUS - i,
                                        outline=(0, 0, 0, 255), width=1)
        
        # Main panel
        inner_panel = [PANEL_MARGIN + 5, PANEL_MARGIN_TOP + 5,
                      CANVAS_WIDTH - PANEL_MARGIN - 5, CANVAS_HEIGHT - PANEL_MARGIN_BOTTOM - 5]
        panel_color_rgba = PANEL_COLOR_RGB + (PANEL_ALPHA,)
        panel_draw.rounded_rectangle(inner_panel, radius=PANEL_RADIUS - 5, fill=panel_color_rgba)
        
        # Composite panel
        img = img.convert('RGBA')
        img = Image.alpha_composite(img, panel_overlay)
        img = img.convert('RGB')
        draw = ImageDraw.Draw(img)
        
        # Load fonts
        font_paths_gothic = [
            "/opt/render/project/src/assets/OldEnglishFive.ttf",
            os.path.join(os.path.dirname(__file__), "assets", "OldEnglishFive.ttf"),
        ]
        
        font_title = None
        for path in font_paths_gothic:
            try:
                font_title = ImageFont.truetype(path, HEADER_FONT_SIZE)
                break
            except:
                continue
        
        if not font_title:
            font_title = ImageFont.load_default()
        
        # Entry fonts
        font_paths_label = [
            "/opt/render/project/src/assets/impact.ttf",
            os.path.join(os.path.dirname(__file__), "assets", "impact.ttf"),
        ]
        
        try:
            font_section = ImageFont.truetype(font_paths_label[0], SECTION_HEADER_SIZE)
            font_entry = ImageFont.truetype(font_paths_label[0], ENTRY_FONT_SIZE)
            font_footer = ImageFont.truetype(font_paths_label[0], FOOTER_FONT_SIZE)
        except:
            font_section = ImageFont.load_default()
            font_entry = ImageFont.load_default()
            font_footer = ImageFont.load_default()
        
        def draw_outlined_text(position, text, font, fill, outline_fill='#000000', outline_width=5):
            x, y = position
            for dx in range(-outline_width, outline_width + 1):
                for dy in range(-outline_width, outline_width + 1):
                    if dx == 0 and dy == 0:
                        continue
                    draw.text((x + dx, y + dy), text, font=font, fill=outline_fill)
            draw.text((x, y), text, font=font, fill=fill)
        
        def draw_label_with_shadow(position, text, font, fill=TEXT_COLOR):
            x, y = position
            # Triple shadow for maximum visibility
            draw.text((x + 4, y + 4), text, font=font, fill='#000000')
            draw.text((x + 3, y + 3), text, font=font, fill='#000000')
            draw.text((x + 2, y + 2), text, font=font, fill='#000000')
            # Main white text (quadruple-draw for boldness)
            draw.text((x, y), text, font=font, fill=fill)
            draw.text((x + 0.5, y), text, font=font, fill=fill)
            draw.text((x, y + 0.5), text, font=font, fill=fill)
            draw.text((x + 0.5, y + 0.5), text, font=font, fill=fill)
        
        # Draw "Barygos" header
        draw_outlined_text((HEADER_X, HEADER_Y), "Barygos", font_title, HEADER_COLOR,
                          HEADER_OUTLINE, outline_width=6)
        
        # Get leaderboard data
        now = datetime.now(TIMEZONE)
        
        # Weekly (top 7)
        sorted_weekly = sorted(votes_weekly.items(), key=lambda x: x[1], reverse=True)[:7]
        
        # Monthly (top 7)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        monthly_totals = defaultdict(int)
        for vendor, votes_list in votes_monthly.items():
            current_month_votes = [(ts, s) for ts, s in votes_list if ts >= month_start]
            monthly_totals[vendor] = sum(s for _, s in current_month_votes)
        sorted_monthly = sorted(monthly_totals.items(), key=lambda x: x[1], reverse=True)[:7]
        
        # All-time (top 7)
        sorted_alltime = sorted(votes_alltime.items(), key=lambda x: x[1], reverse=True)[:7]
        
        # Vertical Single Column Layout: All sections stacked vertically
        sections = [
            ("🌟 VISŲ LAIKŲ LEGENDOS", sorted_alltime, 0),  # TOP
            ("🔥 SAVAITĖS ČEMPIONAI", sorted_weekly, 1),     # Middle
            ("🗓️ MĖNESIO LYDERIAI", sorted_monthly, 2),     # Bottom
        ]
        
        for section_title, entries, section_idx in sections:
            y_offset = SECTION_START_Y + (section_idx * SECTION_SPACING)
            
            # Section header
            draw_label_with_shadow((LABEL_X, y_offset), section_title, font_section)
            y_offset += SECTION_HEADER_SIZE + 15
            
            # Entries
            if not entries:
                draw_label_with_shadow((LABEL_X + 20, y_offset), "Dar nėra duomenų", font_entry)
            else:
                for i, (vendor, score) in enumerate(entries, 1):
                    vendor_name = vendor[1:] if vendor.startswith('@') else vendor
                    vendor_name = vendor_name[:25]  # Truncate if too long
                    
                    # Draw rank and name
                    entry_text = f"{i}. {vendor_name}"
                    draw_label_with_shadow((LABEL_X + 20, y_offset), entry_text, font_entry)
                    
                    # Draw score (right-aligned)
                    score_text = str(score)
                    bbox = font_entry.getbbox(score_text)
                    score_width = bbox[2] - bbox[0]
                    draw_label_with_shadow((SCORE_X - score_width, y_offset), score_text, font_entry)
                    
                    y_offset += ENTRY_SPACING
        
        # Add scanlines
        scanline_overlay = Image.new('RGBA', (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
        scanline_draw = ImageDraw.Draw(scanline_overlay)
        
        for y in range(0, CANVAS_HEIGHT, 3):
            scanline_draw.line([(0, y), (CANVAS_WIDTH, y)], fill=(0, 0, 0, 15), width=1)
        
        img = img.convert('RGBA')
        img = Image.alpha_composite(img, scanline_overlay)
        img = img.convert('RGB')
        
        # Save to BytesIO
        bio = BytesIO()
        bio.name = 'barygos.png'
        img.save(bio, 'PNG')
        bio.seek(0)
        return bio
        
    except Exception as e:
        logger.error(f"Error generating barygos image: {e}")
        raise


async def barygos_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display seller leaderboards (weekly, monthly, all-time) with GTA SA style image"""
    chat_id = update.message.chat_id
    
    # Register this group in database for barygos auto-post group selection
    if chat_id < 0:  # It's a group
        from database import database
        try:
            chat = await context.bot.get_chat(chat_id)
            database.register_group(chat_id, chat.title)
        except:
            database.register_group(chat_id)
    
    try:
        # Generate GTA SA style image
        image_bio = generate_barygos_image()
        
        # Read bytes to avoid event loop issues
        image_bytes = image_bio.read()
        image_bio.close()
        
        # Send image without caption
        await update.message.reply_photo(
            photo=image_bytes,
            filename='barygos.png'
        )
        
    except Exception as e:
        logger.error(f"Error sending barygos message: {e}")
        # Fallback without media
        try:
            msg = await context.bot.send_message(chat_id=chat_id, text=full_message)
            context.job_queue.run_once(
                lambda c: c.bot.delete_message(chat_id=chat_id, message_id=msg.message_id),
                120
            )
        except Exception as e2:
            logger.error(f"Failed to send barygos fallback: {e2}")


# ============================================================================
# UPDATE VOTING MESSAGE (Admin only)
# ============================================================================

async def update_voting_message(context: ContextTypes.DEFAULT_TYPE):
    """Update the pinned voting message in voting group"""
    if not VOTING_GROUP_CHAT_ID:
        logger.warning("VOTING_GROUP_CHAT_ID not set, skipping vote message update")
        return
    
    global voting_message_id
    
    # Create voting buttons for all trusted sellers
    keyboard = []
    for seller in trusted_sellers:
        seller_name = seller[1:] if seller.startswith('@') else seller
        keyboard.append([InlineKeyboardButton(f"🗳️ Balsuoti už {seller_name}", callback_data=f"vote_{seller}")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    message_text = "🗳️ **BALSAVIMAS UŽ PARDAVĖJUS** 🗳️\n\n"
    message_text += "Spauskite mygtuką žemiau norėdami balsuoti už savo mėgstamą pardavėją!\n\n"
    message_text += "✅ Galite balsuoti kas 7 dienas\n"
    message_text += "💰 Už balsą gausite 15 taškų\n\n"
    message_text += "📊 Rezultatus matykite su /barygos"
    
    try:
        # Delete old voting message if exists
        if voting_message_id:
            try:
                await context.bot.delete_message(chat_id=VOTING_GROUP_CHAT_ID, message_id=voting_message_id)
            except:
                pass
        
        # Send new voting message
        if featured_media_id and featured_media_type:
            if featured_media_type == 'photo':
                msg = await context.bot.send_photo(
                    chat_id=VOTING_GROUP_CHAT_ID,
                    photo=featured_media_id,
                    caption=message_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            elif featured_media_type == 'animation':
                msg = await context.bot.send_animation(
                    chat_id=VOTING_GROUP_CHAT_ID,
                    animation=featured_media_id,
                    caption=message_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            elif featured_media_type == 'video':
                msg = await context.bot.send_video(
                    chat_id=VOTING_GROUP_CHAT_ID,
                    video=featured_media_id,
                    caption=message_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                msg = await context.bot.send_message(
                    chat_id=VOTING_GROUP_CHAT_ID,
                    text=message_text,
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
        else:
            msg = await context.bot.send_message(
                chat_id=VOTING_GROUP_CHAT_ID,
                text=message_text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        
        voting_message_id = msg.message_id
        data_manager.save_data(voting_message_id, 'voting_message_id.pkl')
        
        # Pin the message
        await context.bot.pin_chat_message(chat_id=VOTING_GROUP_CHAT_ID, message_id=voting_message_id)
        
        logger.info(f"✅ Voting message updated: message_id={voting_message_id}")
        
    except Exception as e:
        logger.error(f"Failed to update voting message: {e}")


async def updatevoting_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Manually update voting message (admin only)"""
    user_id = update.message.from_user.id
    chat_id = update.message.chat_id
    
    if user_id != ADMIN_CHAT_ID:
        await update.message.reply_text("Tik adminas gali atnaujinti balsavimo mygtukus!")
        return
    
    await update_voting_message(context)
    await update.message.reply_text("✅ Balsavimo mygtukai atnaujinti!")


async def reset_voting_cooldowns_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reset ALL voting cooldowns for testing (admin only)"""
    user_id = update.message.from_user.id
    
    if user_id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Tik adminas gali atstatyti balsavimo laikmatį!")
        return
    
    global last_vote_attempt
    
    # Clear all cooldowns
    old_count = len(last_vote_attempt)
    last_vote_attempt.clear()
    data_manager.save_data(last_vote_attempt, 'last_vote_attempt.pkl')
    
    await update.message.reply_text(
        f"✅ **Voting cooldowns reset!**\n\n"
        f"Cleared {old_count} user cooldowns.\n"
        f"All users can now vote immediately for testing.",
        parse_mode='Markdown'
    )
    
    logger.info(f"Admin {user_id} reset {old_count} voting cooldowns for testing")


# Export functions
__all__ = [
    'balsuoti_command',
    'barygos_command',
    'handle_vote_button',
    'update_voting_message',
    'updatevoting_command',
    'reset_voting_cooldowns_command',
    'votes_weekly',
    'votes_monthly',
    'votes_alltime',
    'vote_history',
]

