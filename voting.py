#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Voting System - Seller Voting & Leaderboards
PRESERVES ALL VOTING DATA from old bot (votes_weekly.pkl, votes_monthly.pkl, votes_alltime.pkl)
"""

import logging
import os
from datetime import datetime, timedelta
from collections import defaultdict
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import telegram
from utils import data_manager
from config import TIMEZONE, ADMIN_CHAT_ID
from database import database

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
    
    # Check 7-day cooldown
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
    
    # Add points to DATABASE (not pickle!)
    current_points = get_user_points(user_id)
    update_user_points(user_id, current_points + 15)
    
    last_vote_attempt[user_id] = now
    
    # Save voting data
    data_manager.save_data(votes_weekly, 'votes_weekly.pkl')
    data_manager.save_data(votes_monthly, 'votes_monthly.pkl')
    data_manager.save_data(votes_alltime, 'votes_alltime.pkl')
    data_manager.save_data(vote_history, 'vote_history.pkl')
    data_manager.save_data(last_vote_attempt, 'last_vote_attempt.pkl')
    data_manager.save_data(voters, 'voters.pkl')
    
    await query.answer("Ačiū už jūsų balsą, 15 taškų buvo pridėti prie jūsų sąskaitos.")
    
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

async def barygos_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display seller leaderboards (weekly, monthly, all-time)"""
    chat_id = update.message.chat_id
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
    
    try:
        # Send with media if available
        if barygos_media_id and barygos_media_type:
            if len(full_message) > 1000:
                # Send media and text separately if too long
                if barygos_media_type == 'photo':
                    await context.bot.send_photo(chat_id=chat_id, photo=barygos_media_id)
                elif barygos_media_type == 'animation':
                    await context.bot.send_animation(chat_id=chat_id, animation=barygos_media_id)
                elif barygos_media_type == 'video':
                    await context.bot.send_video(chat_id=chat_id, video=barygos_media_id)
                
                msg = await context.bot.send_message(chat_id=chat_id, text=full_message)
            else:
                # Send with caption
                if barygos_media_type == 'photo':
                    msg = await context.bot.send_photo(chat_id=chat_id, photo=barygos_media_id, caption=full_message)
                elif barygos_media_type == 'animation':
                    msg = await context.bot.send_animation(chat_id=chat_id, animation=barygos_media_id, caption=full_message)
                elif barygos_media_type == 'video':
                    msg = await context.bot.send_video(chat_id=chat_id, video=barygos_media_id, caption=full_message)
                else:
                    msg = await context.bot.send_message(chat_id=chat_id, text=full_message)
        else:
            msg = await context.bot.send_message(chat_id=chat_id, text=full_message)
        
        # Auto-delete after 120 seconds
        context.job_queue.run_once(
            lambda c: c.bot.delete_message(chat_id=chat_id, message_id=msg.message_id),
            120
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


# Export functions
__all__ = [
    'balsuoti_command',
    'barygos_command',
    'handle_vote_button',
    'update_voting_message',
    'updatevoting_command',
    'votes_weekly',
    'votes_monthly',
    'votes_alltime',
    'vote_history',
]

