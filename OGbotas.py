#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🤖 OGbotas - Modular Telegram Bot
Main bot file with clean imports and handlers
"""

import logging
import sys
from pathlib import Path

# Setup logging
from logging.handlers import RotatingFileHandler
from config import DATA_DIR

log_dir = Path(DATA_DIR) / 'logs'
log_dir.mkdir(parents=True, exist_ok=True)

# Setup rotating file handler
file_handler = RotatingFileHandler(
    log_dir / 'bot.log', 
    maxBytes=10*1024*1024,  # 10MB per file
    backupCount=5
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))

# Configure root logger
logging.basicConfig(
    level=logging.DEBUG,  # Changed to DEBUG for detailed logging
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        file_handler,
        logging.StreamHandler(sys.stdout)
    ]
)

# Reduce noise from external libraries (keep these at WARNING)
logging.getLogger('httpx').setLevel(logging.WARNING)
logging.getLogger('httpcore').setLevel(logging.WARNING)
logging.getLogger('apscheduler').setLevel(logging.INFO)  # Enable scheduler logging for debugging
logging.getLogger('telegram').setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

# Import modules
from config import BOT_TOKEN, WEBHOOK_URL, PORT, OWNER_ID, ADMIN_CHAT_ID
from database import database
from utils import data_manager, message_tracker
import moderation_grouphelp as moderation
import recurring_messages_grouphelp as recurring_messages
import masked_users
import admin_panel
import games
import payments
import warn_system
import points_games
import voting
import stats
import bajorai
import levels

# Telegram imports
import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from aiohttp import web
from datetime import datetime

# Initialize scheduler
recurring_messages.init_scheduler()

# Helper function to safely answer callback queries
async def safe_answer_callback(query, text: str = None, show_alert: bool = False):
    """
    Safely answer a callback query, handling expired/invalid queries gracefully.
    This prevents crashes when queries are too old (>5 minutes).
    """
    try:
        await query.answer(text=text, show_alert=show_alert)
    except telegram.error.BadRequest as e:
        if "Query is too old" in str(e) or "query id is invalid" in str(e):
            logger.warning(f"Callback query too old or invalid, continuing anyway")
            # Don't raise - the user clicked something, we should still process it
        else:
            # Other BadRequest errors should be raised
            raise
    except Exception as e:
        # Log unexpected errors but don't crash
        logger.error(f"Unexpected error answering callback query: {e}")

# Load persistent data
logger.info("Loading persistent data...")
user_points = data_manager.load_data('user_points.pkl', {})
trusted_sellers = data_manager.load_data('trusted_sellers.pkl', {})
confirmed_scammers = data_manager.load_data('confirmed_scammers.pkl', {})
username_to_id = data_manager.load_data('username_to_id.pkl', {})
coinflip_challenges = data_manager.load_data('coinflip_challenges.pkl', {})
allowed_groups = data_manager.load_data('allowed_groups.pkl', set())

logger.info(f"Loaded {len(user_points)} user points, {len(trusted_sellers)} sellers, {len(confirmed_scammers)} scammers")

# Basic bot commands
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command - handles deep links for wallet/pinigine"""
    user_id = update.effective_user.id
    
    # Check if there's a deep link parameter
    if context.args and context.args[0] == 'pinigine':
        # Redirect to balance command
        await payments.balance_command(update, context)
        return
    
    # Check if user is admin/owner
    is_admin = user_id == OWNER_ID or (update.effective_chat and update.effective_chat.id == ADMIN_CHAT_ID)
    
    if is_admin:
        # Admin message (English with all commands)
        await update.message.reply_text(
            "🤖 **OGbotas Aktyvuotas!**\n\n"
            "**Administratoriaus komandos:**\n"
            "🔨 `/ban @user [priežastis]` - Užblokuoti vartotoją\n"
            "🔓 `/unban @user` - Atblokuoti vartotoją\n"
            "🔇 `/mute @user [minutes]` - Nutildyti vartotoją\n"
            "🔊 `/unmute @user` - Atšaukti nutildymą\n"
            "⚠️ `/warn @user [priežastis]` - Įspėti vartotoją\n"
            "ℹ️ `/info @user` - Vartotojo informacija\n"
            "🔍 `/lookup @user` - Ieškoti vartotojo\n"
            "🔄 `/recurring` - Pasikartojantys pranešimai\n"
            "👤 `/masked` - Maskuoti vartotojai\n\n"
            "**Viešos komandos:**\n"
            "📊 `/patikra @username` - Patikrinti ar sukčius\n"
            "💰 `/pinigine` - Jūsų piniginė\n"
            "🎲 `/dice2 @username` - Žaisti kauliukus taškams\n"
            "🏆 `/points` - Jūsų taškai\n\n"
            "Botas paruoštas! 🚀",
            parse_mode='Markdown'
        )
    else:
        # Regular user message (Lithuanian, simple commands only)
        await update.message.reply_text(
            "🤖 **Sveiki!**\n\n"
            "**Prieinamos komandos:**\n\n"
            "📊 `/patikra @username` - Patikrinti ar vartotojas sukčius\n"
            "💰 `/pinigine` - Jūsų piniginė (balansas, įnešimai, išėmimai)\n"
            "🎲 `/dice2 @username` - Žaisti kauliukus taškams\n"
            "🏆 `/points` - Peržiūrėti savo taškus\n\n"
            "Sėkmės! 🍀",
            parse_mode='Markdown'
        )
    

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Help command - Member commands only, in Lithuanian"""
    await update.message.reply_text(
        "🤖 **Pagalba**\n\n"
        "**Apsauga nuo vagių:**\n"
        "• `/patikra @vartotojas` - Patikrinti ar vagis\n"
        "• `/vagis @vartotojas priežastis` - Pranešti apie vagį\n\n"
        "**Pinigai ir balansas:**\n"
        "• `/pinigine` - Peržiūrėti balansą, įnešti/išimti lėšas\n"
        "• `/tip @vartotojas suma` - Pervesti pinigus kitam nariui\n\n"
        "**Žaidimai (kripto):**\n"
        "• `/dice <suma>` - 🎲 Kauliukai (1.90x)\n"
        "• `/basketball <suma>` - 🏀 Krepšinis (1.90x)\n"
        "• `/football <suma>` - ⚽ Futbolas (1.90x)\n"
        "• `/bowling <suma>` - 🎳 Boulingas (1.90x)\n\n"
        "**Žaidimai (taškai):**\n"
        "• `/dice2 <taškai>` - 🎲 Kauliukai be kripto\n"
        "• `/points` - Peržiūrėti savo taškus\n\n"
        "**Balsavimas:**\n"
        "• `/balsuoti` - Nuoroda į balsavimų grupę\n"
        "• `/barygos` - Patikimiausių pardavėjų reitingai",
        parse_mode='Markdown'
    )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show admin panel"""
    await admin_panel.show_admin_panel(update, context)


async def patikra_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Check if user is a scammer - shows confirmed/pending/legit status
    """
    if not context.args:
        await update.message.reply_text(
            "❌ **Usage:** `/patikra @username`\n\n"
            "Check if a user is in the scammer database.",
            parse_mode='Markdown'
        )
        return
    
    username = context.args[0].lstrip('@')
    
    # Load latest data
    confirmed_scammers = data_manager.load_data('confirmed_scammers.pkl', {})
    pending_scammer_reports = data_manager.load_data('pending_scammer_reports.pkl', {})
    
    # Check if user is confirmed scammer
    if username in confirmed_scammers:
        scammer_data = confirmed_scammers[username]
        reports_count = len(scammer_data.get('reports', []))
        confirmed_date = scammer_data.get('confirmed_date', 'Unknown')
        
        # Get first report reason if available
        first_reason = "N/A"
        if scammer_data.get('reports'):
            first_reason = scammer_data['reports'][0].get('reason', 'N/A')
        
        await update.message.reply_text(
            f"🚫 PATVIRTINTAS VAGIS\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Vartotojas: @{username}\n"
            f"Statusas: ⛔️ Patvirtintas vagis\n"
            f"Pranešimų: {reports_count}\n"
            f"Patvirtinta: {confirmed_date}\n\n"
            f"Pirmas pranešimas:\n{first_reason}\n\n"
            f"⚠️ DĖMESIO: Šis vartotojas patvirtintas kaip vagis. "
            f"Būkite ypač atsargūs su juo bendraudami!"
        )
        return
    
    # Check if user has pending reports
    pending_count = 0
    pending_reasons = []
    for report_id, report in pending_scammer_reports.items():
        if report.get('reported_username') == username:
            pending_count += 1
            pending_reasons.append(report.get('reason', 'No reason'))
    
    if pending_count > 0:
        reasons_text = "\n• ".join(pending_reasons[:3])  # Show max 3 reasons
        more_text = f"\n...dar {pending_count - 3}" if pending_count > 3 else ""
        
        await update.message.reply_text(
            f"⚠️ TIKRINAMA\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Vartotojas: @{username}\n"
            f"Statusas: 🔍 Tikrinama\n"
            f"Laukiančių pranešimų: {pending_count}\n\n"
            f"Priežastys:\n• {reasons_text}{more_text}\n\n"
            f"⚠️ Šis vartotojas praneštas, bet dar nepatvirtintas. "
            f"Būkite atsargūs!"
        )
        return
    
    # User is clean - check if trusted seller
    trusted_sellers = data_manager.load_data('trusted_sellers.pkl', {})
    
    # Check if user is trusted seller (handle both list and dict formats)
    is_trusted = False
    if isinstance(trusted_sellers, list):
        is_trusted = username in trusted_sellers or f"@{username}" in trusted_sellers
    elif isinstance(trusted_sellers, dict):
        is_trusted = username in trusted_sellers or f"@{username}" in trusted_sellers
    
    if is_trusted:
        # Load vote data
        votes_weekly = data_manager.load_data('votes_weekly.pkl', {})
        votes_alltime = data_manager.load_data('votes_alltime.pkl', {})
        
        # Get vote counts (check both with and without @)
        weekly_votes = votes_weekly.get(username, 0) or votes_weekly.get(f"@{username}", 0)
        alltime_votes = votes_alltime.get(username, 0) or votes_alltime.get(f"@{username}", 0)
        
        await update.message.reply_text(
            f"⭐ PATIKIMAS PARDAVĖJAS\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Vartotojas: @{username}\n"
            f"Statusas: ⭐ Patikimas pardavėjas\n\n"
            f"📊 Balsai:\n"
            f"• Šią savaitę: {weekly_votes}\n"
            f"• Viso laiko: {alltime_votes}\n\n"
            f"✅ Šis vartotojas yra patvirtintas patikimas pardavėjas.\n"
            f"Pranešimų apie vagystes nėra."
        )
    else:
        await update.message.reply_text(
            f"✅ PATIKIMAS\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Vartotojas: @{username}\n"
            f"Statusas: ✅ Pranešimų nėra\n\n"
            f"Apie šį vartotoją pranešimų nėra.\n\n"
            f"💡 Jei įtariate, kad tai vagis, naudokite: /vagis @{username} priežastis"
        )

async def vagis_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Report a scammer - /vagis @username reason
    Auto-approved if already confirmed scammer, otherwise goes to admin for review
    """
    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "❌ Naudojimas: /vagis @username priežastis\n\n"
            "Pavyzdys: /vagis @vagis Neišsiuntė prekės po apmokėjimo"
        )
        return
    
    # Parse username and reason
    username = context.args[0].lstrip('@')
    reason = ' '.join(context.args[1:])
    
    # Get reporter info
    reporter_id = update.effective_user.id
    reporter_username = update.effective_user.username or f"user_{reporter_id}"
    reporter_name = update.effective_user.first_name or "Unknown"
    
    # Load latest data
    confirmed_scammers = data_manager.load_data('confirmed_scammers.pkl', {})
    pending_scammer_reports = data_manager.load_data('pending_scammer_reports.pkl', {})
    
    # CHECK FOR DUPLICATE REPORT: Has this user already reported this person?
    # Check in confirmed scammers
    if username in confirmed_scammers:
        for existing_report in confirmed_scammers[username].get('reports', []):
            if existing_report.get('reporter_id') == reporter_id:
                await update.message.reply_text(
                    f"⚠️ Jūs jau pranešėte apie @{username}\n\n"
                    f"Kiekvienas vartotojas gali pranešti tik vieną kartą."
                )
                return
    
    # Check in pending reports
    for report in pending_scammer_reports.values():
        if report.get('reported_username') == username and report.get('reporter_id') == reporter_id:
            await update.message.reply_text(
                f"⚠️ Jūs jau pranešėte apie @{username}\n\n"
                f"Jūsų pranešimas dar laukia administratorių peržiūros."
            )
            return
    
    # Check if user is already a confirmed scammer
    if username in confirmed_scammers:
        # AUTO-APPROVE: Add report directly to confirmed scammer's record
        report_data = {
            'reported_username': username,
            'reporter_id': reporter_id,
            'reporter_username': reporter_username,
            'reporter_name': reporter_name,
            'reason': reason,
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'auto_approved': True
        }
        
        confirmed_scammers[username]['reports'].append(report_data)
        data_manager.save_data(confirmed_scammers, 'confirmed_scammers.pkl')
        
        total_reports = len(confirmed_scammers[username]['reports'])
        
        await update.message.reply_text(
            f"✅ Pranešimas pridėtas\n\n"
            f"@{username} jau patvirtintas kaip vagis.\n"
            f"Bendrai pranešimų: {total_reports}"
        )
        
        # Notify admin
        try:
            await context.bot.send_message(
                chat_id=ADMIN_CHAT_ID,
                text=f"📊 AUTO-PATVIRTINTAS PRANEŠIMAS\n\n"
                     f"@{reporter_username} pranešė apie @{username}\n"
                     f"Priežastis: {reason}\n"
                     f"Bendrai pranešimų: {total_reports}",
        parse_mode='Markdown'
    )
        except Exception as e:
            logger.error(f"Failed to notify admin about auto-approved report: {e}")
        
        return
    
    # NEW REPORT: Send to admin for review
    # Generate unique report ID
    report_id = f"scam_{int(datetime.now().timestamp())}_{reporter_id}"
    
    report_data = {
        'reported_username': username,
        'reporter_id': reporter_id,
        'reporter_username': reporter_username,
        'reporter_name': reporter_name,
        'reason': reason,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    
    pending_scammer_reports[report_id] = report_data
    data_manager.save_data(pending_scammer_reports, 'pending_scammer_reports.pkl')
    
    # Add points for reporting scammer
    try:
        levels.add_xp(reporter_id, levels.XP_REWARDS['scammer_report'], 'scammer_report')
    except Exception as e:
        logger.error(f"Error adding points for scammer report: {e}")
    
    await update.message.reply_text(
        f"✅ Pranešimas išsiųstas\n\n"
        f"Vartotojas: @{username}\n"
        f"Priežastis: {reason}\n\n"
        f"Administratoriai peržiūrės ir praneš apie sprendimą."
    )
    
    # Notify admin with review buttons
    try:
        keyboard = [
            [InlineKeyboardButton("✅ Patvirtinti vagį", callback_data=f"claim_confirm_{report_id}")],
            [InlineKeyboardButton("❌ Atmesti pranešimą", callback_data=f"claim_dismiss_{report_id}")],
            [InlineKeyboardButton("🔍 Peržiūrėti", callback_data=f"claim_review_{report_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=ADMIN_CHAT_ID,
            text=f"🚨 NAUJAS PRANEŠIMAS APIE VAGĮ\n"
                 f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                 f"Pranešė: @{reporter_username} ({reporter_name})\n"
                 f"Apie: @{username}\n"
                 f"Priežastis: {reason}\n"
                 f"Laikas: {report_data['timestamp']}\n\n"
                 f"ID: {report_id}",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Failed to notify admin about new scammer report: {e}")

async def recurring_messages_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Main recurring messages menu - GroupHelpBot style"""
    
    # If in group chat, register the group
    if update.effective_chat.type in ['group', 'supergroup']:
        # Check if user is admin
        try:
            member = await context.bot.get_chat_member(update.effective_chat.id, update.effective_user.id)
            if member.status not in ['creator', 'administrator']:
                await update.message.reply_text("❌ Tik administratoriai gali aktyvuoti skelbimus.")
                return
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            return
        
        # Register the group in database
        chat_id = update.effective_chat.id
        chat_title = update.effective_chat.title or "Group"
        user_id = update.effective_user.id
        
        # Store in groups table
        database.add_or_update_group(chat_id, chat_title, user_id)
        
        # Reply with simple Lithuanian confirmation
        await update.message.reply_text("grupės skelbimai aktyvuoti")
        
        logger.info(f"Registered group: {chat_title} (ID: {chat_id})")
    else:
        # In private chat, show group selection
        await recurring_messages.show_main_menu(update, context)

# Callback query handler
async def handle_recurring_callback(query, context):
    """Handle recurring messages callbacks"""
    data = query.data
    
    # Only handle recurring message callbacks (early return for others)
    recurring_prefixes = ("hour_", "minute_", "repeat_", "back_to_hour_selection", 
                          "toggle_message_status", "show_full_customize", "delete_message",
                          "customize_message", "set_time", "set_repetition", "set_text",
                          "set_media", "set_url_buttons", "save_message", "start_recurring_now",
                          "back_to_config")
    
    if not any(data.startswith(prefix) if isinstance(prefix, str) and "_" in prefix else data == prefix for prefix in recurring_prefixes):
        return  # Not a recurring message callback, let other handlers process it
    
    try:
        # Time selection callbacks
        if data.startswith("hour_"):
            hour = int(data.split("_")[1])
            context.user_data['selected_hour'] = hour
            await recurring_messages.show_time_selection(query, context)
        elif data.startswith("minute_"):
            minute = int(data.split("_")[1])
            selected_hour = context.user_data.get('selected_hour', 0)
            # Set the time in Lithuanian timezone format
            time_str = f"{selected_hour:02d}:{minute:02d}"
            config = context.user_data.get('current_message_config', {})
            config['time'] = time_str
            context.user_data['current_message_config'] = config
            # Clear selected hour
            context.user_data.pop('selected_hour', None)
            # Return to main config
            await recurring_messages.show_message_config(query, context)
            await query.answer(f"⏰ Laikas nustatytas: {time_str}")
        elif data == "back_to_hour_selection":
            context.user_data.pop('selected_hour', None)
            await recurring_messages.show_time_selection(query, context)
        elif data == "toggle_message_status":
            await recurring_messages.toggle_message_status_main(query, context)
        elif data == "show_full_customize":
            await recurring_messages.show_full_customize_interface(query, context)
        elif data == "delete_message":
            await recurring_messages.delete_current_message(query, context)
        elif data == "customize_message":
            await recurring_messages.show_message_customization(query, context)
        elif data == "set_time":
            await recurring_messages.show_time_selection(query, context)
        elif data == "set_repetition":
            await recurring_messages.show_repetition_options(query, context)
        elif data == "set_text":
            await recurring_messages.set_message_text(query, context)
        elif data == "set_media":
            await recurring_messages.set_message_media(query, context)
        elif data == "set_url_buttons":
            await recurring_messages.set_url_buttons(query, context)
        elif data == "save_message":
            await recurring_messages.save_recurring_message(query, context)
        elif data == "start_recurring_now":
            await recurring_messages.start_recurring_message_now(query, context)
        elif data == "back_to_config":
            await recurring_messages.show_message_config(query, context)
        elif data.startswith("repeat_"):
            # Handle repetition settings
            repeat_value = data.split("_", 1)[1]
            config = context.user_data.get('current_message_config', {})
            
            # Handle hours
            if repeat_value == "1h":
                config['repetition'] = "1 hour"
            elif repeat_value == "2h":
                config['repetition'] = "2 hours"
            elif repeat_value == "3h":
                config['repetition'] = "3 hours"
            elif repeat_value == "4h":
                config['repetition'] = "4 hours"
            elif repeat_value == "6h":
                config['repetition'] = "6 hours"
            elif repeat_value == "8h":
                config['repetition'] = "8 hours"
            elif repeat_value == "12h":
                config['repetition'] = "12 hours"
            elif repeat_value == "24h":
                config['repetition'] = "24 hours"
            # Handle minutes
            elif repeat_value == "1m":
                config['repetition'] = "1 minute"
            elif repeat_value == "2m":
                config['repetition'] = "2 minutes"
            elif repeat_value == "3m":
                config['repetition'] = "3 minutes"
            elif repeat_value == "5m":
                config['repetition'] = "5 minutes"
            elif repeat_value == "10m":
                config['repetition'] = "10 minutes"
            elif repeat_value == "15m":
                config['repetition'] = "15 minutes"
            elif repeat_value == "20m":
                config['repetition'] = "20 minutes"
            elif repeat_value == "30m":
                config['repetition'] = "30 minutes"
            elif repeat_value == "messages":
                config['repetition'] = "few messages"
            else:
                config['repetition'] = "24 hours"
                
            context.user_data['current_message_config'] = config
            await query.answer(f"🔄 Kartojimas nustatytas: Every {config['repetition']}")
            await recurring_messages.show_message_config(query, context)
    
    except Exception as e:
        logger.error(f"Error in handle_recurring_callback: {e}")
        await safe_answer_callback(query, "❌ Error processing request")


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin panel callback queries"""
    query = update.callback_query
    await safe_answer_callback(query)
    
    data = query.data
    logger.info(f"🔔 Admin callback received: {data}")
    
    try:
        # Main menu
        if data == "admin_main":
            await admin_panel.show_admin_panel(update, context)
        
        # Points management
        elif data == "admin_points":
            await admin_panel.show_points_menu(query, context)
        elif data == "points_add":
            await admin_panel.points_add_start(query, context)
        elif data == "points_remove":
            await admin_panel.points_remove_start(query, context)
        elif data == "points_leaderboard":
            await admin_panel.show_points_leaderboard(query, context)
        
        # Sellers management
        elif data == "admin_sellers":
            await admin_panel.show_sellers_menu(query, context)
        elif data == "seller_manage":
            await admin_panel.show_sellers_menu(query, context)
        elif data == "seller_add":
            await admin_panel.seller_add_start(query, context)
        elif data == "seller_remove":
            await admin_panel.seller_remove_start(query, context)
        elif data.startswith("seller_remove_confirm_"):
            seller_username = data.replace("seller_remove_confirm_", "")
            await admin_panel.seller_remove_confirm(query, context, seller_username)
        elif data == "seller_rename":
            await admin_panel.seller_rename_start(query, context)
        elif data == "seller_list":
            await admin_panel.show_all_sellers(query, context)
        
        # Scammers management
        elif data == "admin_scammers":
            await admin_panel.show_scammers_menu(query, context)
        elif data == "scammer_add":
            await admin_panel.scammer_add_start(query, context)
        elif data == "scammer_remove":
            await admin_panel.scammer_remove_start(query, context)
        elif data == "scammer_list":
            await admin_panel.show_all_scammers(query, context)
        
        # Claims review
        elif data == "admin_claims":
            await admin_panel.show_claims_menu(query, context)
        elif data.startswith("claim_review_"):
            report_id = data.replace("claim_review_", "")
            logger.info(f"📋 Showing claim detail for report: {report_id}")
            await admin_panel.show_claim_detail(query, context, report_id)
        elif data.startswith("claim_confirm_"):
            report_id = data.replace("claim_confirm_", "")
            logger.info(f"✅ Confirming claim for report: {report_id}")
            await admin_panel.confirm_claim(query, context, report_id)
        elif data.startswith("claim_dismiss_"):
            report_id = data.replace("claim_dismiss_", "")
            logger.info(f"❌ Dismissing claim for report: {report_id}")
            await admin_panel.dismiss_claim(query, context, report_id)
        
        # User lookup
        elif data == "admin_lookup":
            await admin_panel.show_lookup_menu(query, context)
        
        # Statistics
        elif data == "admin_stats":
            await admin_panel.show_statistics(query, context)
        
        # Recurring Messages (from admin panel)
        elif data == "admin_recurring":
            await recurring_messages.show_main_menu(update, context)
        
        # Barygos Auto-Post
        elif data == "admin_barygos_auto":
            await admin_panel.show_barygos_auto_settings(update, context)
        elif data == "admin_barygos_auto_toggle":
            await admin_panel.handle_barygos_auto_toggle(update, context)
        elif data == "admin_barygos_auto_interval":
            await admin_panel.show_barygos_auto_interval(update, context)
        elif data.startswith("admin_barygos_auto_interval_"):
            hours = int(data.split("_")[-1])
            await admin_panel.handle_barygos_auto_interval_set(update, context, hours)
        elif data == "admin_barygos_auto_groups":
            await admin_panel.show_barygos_auto_groups(update, context)
        elif data.startswith("admin_barygos_auto_group_toggle_"):
            chat_id = int(data.replace("admin_barygos_auto_group_toggle_", ""))
            await admin_panel.handle_barygos_auto_group_toggle(update, context, chat_id)
        elif data == "admin_barygos_auto_voting_link":
            await admin_panel.show_barygos_auto_voting_link(update, context)
        
        # Helpers Management
        elif data == "admin_helpers":
            await admin_panel.show_helpers_list(update, context)
        elif data.startswith("admin_helpers_group_"):
            chat_id = int(data.replace("admin_helpers_group_", ""))
            await admin_panel.show_helpers_for_group(update, context, chat_id)
        elif data.startswith("admin_helper_perm_"):
            # Format: admin_helper_perm_CHAT_ID_USER_ID_PERMISSION
            parts = data.split("_")
            chat_id = int(parts[3])
            user_id = int(parts[4])
            permission = parts[5]
            await admin_panel.toggle_helper_permission(update, context, chat_id, user_id, permission)
        elif data.startswith("admin_helper_remove_"):
            # Format: admin_helper_remove_CHAT_ID_USER_ID
            parts = data.split("_")
            chat_id = int(parts[3])
            user_id = int(parts[4])
            await admin_panel.remove_helper(update, context, chat_id, user_id)
        elif data.startswith("admin_helper_"):
            # Format: admin_helper_CHAT_ID_USER_ID
            parts = data.split("_")
            chat_id = int(parts[2])
            user_id = int(parts[3])
            await admin_panel.show_helper_detail(update, context, chat_id, user_id)
        
        # Masked Users (from admin panel)
        elif data == "admin_masked":
            await masked_users.show_main_menu(update, context)
        
        # Settings menu
        elif data == "admin_settings":
            await admin_panel.show_settings_menu(query, context)
        elif data == "settings_toggle_withdrawals":
            await admin_panel.toggle_withdrawals_setting(query, context)
        
        # Close panel
        elif data == "admin_close":
            await query.edit_message_text("✅ Admin panel closed.")
        
        else:
            await query.answer("Feature coming soon!")
    
    except Exception as e:
        logger.error(f"❌ Error in admin callback handler: {e}")
        logger.exception(e)
        await query.answer("❌ Klaida apdorojant užklausą")


# Message handler for private chat input
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all messages"""
    
    # Store user info if available
    if update.effective_user and update.effective_user.username:
        database.store_user_info(
            update.effective_user.id,
            update.effective_user.username,
            update.effective_user.first_name,
            update.effective_user.last_name
        )
    
    # Grant points for messages (with cooldown)
    if update.effective_chat.type in ['group', 'supergroup'] and update.message and update.message.text:
        points_result = levels.grant_message_xp(update.effective_user.id)
        if points_result and points_result.get('leveled_up'):
            # Notify user of level up
            try:
                username = update.effective_user.first_name
                new_level = points_result['new_level']
                rank = levels.get_rank_title(new_level)
                await update.message.reply_text(
                    f"🎉 <b>{username}</b> pasiekė <b>Level {new_level}</b>!\n{rank}",
                    parse_mode='HTML'
                )
            except:
                pass
    
    # Check game challenge handlers FIRST (work in both private and group chats)
    logger.debug(f"🔍 MESSAGE HANDLER: Checking game challenges for user {update.effective_user.id}")
    
    if await games.handle_game_challenge(update, context):
        logger.debug(f"✅ MESSAGE HANDLER: Crypto game challenge handled")
        return
    
    logger.debug(f"🔍 MESSAGE HANDLER: Checking dice2 challenge (expecting={context.user_data.get('expecting_username')})")
    dice2_result = await points_games.handle_dice2_challenge(update, context)
    logger.debug(f"🔍 MESSAGE HANDLER: dice2 challenge returned {dice2_result}")
    if dice2_result:
        logger.debug(f"✅ MESSAGE HANDLER: Dice2 challenge handled")
        return
    
    # Check for awaiting input (WORKS IN BOTH PRIVATE AND GROUP CHATS)
    # This handles recurring messages, masked users, etc.
    if context.user_data.get('awaiting_input'):
        logger.debug(f"🔍 MESSAGE HANDLER: Awaiting input detected: {context.user_data.get('awaiting_input')}")
        await recurring_messages.handle_text_input(update, context)
        return
    
    # Handle private chat input
    if update.effective_chat.type == 'private':
        # Check if it's admin panel input
        if context.user_data.get('admin_action'):
            await admin_panel.handle_admin_input(update, context)
            return
        
        # Check if awaiting input for masked users
        if context.user_data.get('mask_action'):
            await masked_users.handle_text_input(update, context)
            return
        
        # Check if awaiting withdrawal details
        if await payments.handle_withdrawal_text(update, context):
            return
        
        # Otherwise handle old recurring messages input
        # await recurring_messages.process_private_chat_input(update, context)
        return
    
    # Handle group messages
    # CRITICAL: Auto-cache users when they send ANY message (for challenge lookup!)
    user = update.effective_user
    if user and user.id:
        try:
            database.store_user_info(
                user.id,
                user.username or f"user_{user.id}",
                user.first_name,
                user.last_name
            )
            logger.debug(f"✅ Cached user @{user.username or user.id} (ID: {user.id}) from group message")
        except Exception as e:
            logger.error(f"❌ Failed to cache user {user.id}: {e}")

def create_application():
    """Create and configure the Telegram bot application."""
    if not BOT_TOKEN:
        logger.error("❌ ERROR: BOT_TOKEN environment variable not set!")
        return None
    
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_command))
    
    # Moderation commands (GroupHelpBot style with pending bans)
    application.add_handler(CommandHandler("cache", moderation.cache_user))  # Manual user caching
    application.add_handler(CommandHandler("ban", moderation.ban_user))
    application.add_handler(CommandHandler("unban", moderation.unban_user))
    application.add_handler(CommandHandler("mute", moderation.mute_user))
    application.add_handler(CommandHandler("unmute", moderation.unmute_user))
    application.add_handler(CommandHandler("lookup", moderation.lookup_user))
    application.add_handler(CommandHandler("info", moderation.info_user))
    application.add_handler(CommandHandler("patikra", patikra_command))
    application.add_handler(CommandHandler("vagis", vagis_command))
    
    # Helper management commands
    application.add_handler(CommandHandler("addhelper", moderation.add_helper))
    application.add_handler(CommandHandler("removehelper", moderation.remove_helper))
    application.add_handler(CommandHandler("delete", moderation.delete_message_command))
    
    # Warn system commands (GroupHelpBot style)
    application.add_handler(CommandHandler("warn", warn_system.warn_user))
    application.add_handler(CommandHandler("unwarn", warn_system.unwarn_user))
    application.add_handler(CommandHandler("warnings", warn_system.warnings_command))
    application.add_handler(CommandHandler("resetwarns", warn_system.resetwarns_command))
    
    # Chat member handler for auto-ban on join (pending bans)
    from telegram.ext import ChatMemberHandler
    application.add_handler(ChatMemberHandler(moderation.handle_new_chat_member, ChatMemberHandler.CHAT_MEMBER))
    
    # Casino games commands (with real crypto)
    application.add_handler(CommandHandler("cleargames", games.cleargames_command))
    application.add_handler(CommandHandler("dice", games.dice_command))
    application.add_handler(CommandHandler("basketball", games.basketball_command))
    application.add_handler(CommandHandler("football", games.football_command))
    application.add_handler(CommandHandler("bowling", games.bowling_command))
    
    # Points games commands (saved points only, NO crypto)
    application.add_handler(CommandHandler("dice2", points_games.dice2_command))
    # Note: /points command now handled by levels.py (level system), not points_games.py
    
    # Stats command
    application.add_handler(CommandHandler("stats", stats.stats_command))
    
    # Payment commands (balance, deposit, withdraw, tip)
    application.add_handler(CommandHandler("pinigine", payments.balance_command))  # Wallet command
    application.add_handler(CommandHandler("tip", payments.tip_command))  # Send crypto to others
    application.add_handler(CommandHandler("setbalance", payments.setbalance_command))
    application.add_handler(CommandHandler("addbalance", payments.add_balance_command))
    application.add_handler(CommandHandler("removebalance", payments.remove_balance_command))
    application.add_handler(CommandHandler("togglewithdrawals", payments.toggle_withdrawals_command))
    
    # Debug command for scheduler status (owner only)
    async def check_scheduler(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check scheduler status and list all jobs (with database comparison)"""
        if update.effective_user.id != OWNER_ID:
            return
        
        from recurring_messages_grouphelp import scheduler
        import database as db
        
        text = "📋 **Scheduler Debug Info**\n\n"
        
        # Check scheduler state
        if scheduler is None:
            text += "❌ Scheduler: None (not initialized!)\n"
        else:
            text += f"✅ Scheduler: Initialized\n"
            text += f"  - Running: {scheduler.running}\n"
            text += f"  - State: {scheduler.state}\n"
        
        # Check database
        try:
            conn = db.database.get_sync_connection()
            cursor = conn.execute('''
                SELECT COUNT(*) FROM scheduled_messages 
                WHERE status = 'active' AND is_active = 1
            ''')
            db_count = cursor.fetchone()[0]
            conn.close()
            text += f"\n📊 Database: {db_count} active recurring messages\n"
        except Exception as e:
            text += f"\n❌ Database error: {e}\n"
        
        # Check scheduler jobs
        if scheduler:
            jobs = scheduler.get_jobs()
            text += f"\n🔧 Scheduler Jobs: {len(jobs)}\n\n"
            
            if not jobs:
                text += "⚠️ No jobs in scheduler!\n"
                text += "\nThis means jobs aren't being loaded or are being lost.\n"
                text += "Check logs for errors during job loading.\n"
            else:
                for job in jobs:
                    text += f"**{job.id}**\n"
                    text += f"  Next: {job.next_run_time}\n"
                    text += f"  Trigger: {job.trigger}\n\n"
        
        await update.message.reply_text(text, parse_mode='Markdown')
    
    application.add_handler(CommandHandler("checkscheduler", check_scheduler))
    
    # Reload scheduler jobs command (owner only)
    async def reload_scheduler_jobs(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Manually reload all scheduled jobs from database"""
        if update.effective_user.id != OWNER_ID:
            return
        
        await update.message.reply_text("🔄 Reloading all scheduled jobs from database...")
        
        try:
            from recurring_messages_grouphelp import load_scheduled_jobs_from_db
            load_scheduled_jobs_from_db(context.bot)
            
            from recurring_messages_grouphelp import scheduler
            if scheduler:
                jobs = scheduler.get_jobs()
                text = f"✅ Reload complete!\n\n"
                text += f"📊 Scheduler now has {len(jobs)} jobs\n\n"
                
                if jobs:
                    for job in jobs:
                        text += f"• {job.id}\n  Next: {job.next_run_time}\n\n"
                
                await update.message.reply_text(text)
            else:
                await update.message.reply_text("❌ Scheduler is None after reload!")
        except Exception as e:
            await update.message.reply_text(f"❌ Error reloading jobs: {e}")
    
    application.add_handler(CommandHandler("reloadjobs", reload_scheduler_jobs))
    
    # Fix broken recurring messages in database (owner only)
    async def fix_recurring_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Fix recurring messages that have is_active = 0 or NULL"""
        if update.effective_user.id != OWNER_ID:
            return
        
        await update.message.reply_text("🔧 Fixing recurring messages in database...")
        
        try:
            import database as db
            conn = db.database.get_sync_connection()
            
            # Find messages with status='active' but is_active != 1
            cursor = conn.execute('''
                SELECT id, chat_id, message_text FROM scheduled_messages 
                WHERE status = 'active' AND (is_active IS NULL OR is_active != 1)
            ''')
            broken_messages = cursor.fetchall()
            
            if not broken_messages:
                await update.message.reply_text("✅ No broken messages found! All messages are properly configured.")
                conn.close()
                return
            
            # Fix them
            fixed_count = 0
            for msg_id, chat_id, text in broken_messages:
                conn.execute('UPDATE scheduled_messages SET is_active = 1 WHERE id = ?', (msg_id,))
                fixed_count += 1
            
            conn.commit()
            conn.close()
            
            text = f"✅ Fixed {fixed_count} recurring messages!\n\n"
            text += "Now run /reloadjobs to reload them into the scheduler."
            
            await update.message.reply_text(text)
            
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {e}")
    
    application.add_handler(CommandHandler("fixrecurring", fix_recurring_messages))
    
    # Voting commands (PRESERVED from old bot - keeps 3 months of data!)
    application.add_handler(CommandHandler("balsuoti", voting.balsuoti_command))
    application.add_handler(CommandHandler("barygos", voting.barygos_command))  # Scoreboard leaderboard
    application.add_handler(CommandHandler("bajorai", bajorai.bajorai_command))  # Top balances & game stats
    application.add_handler(CommandHandler("points", levels.points_command))  # XP & Level system
    application.add_handler(CommandHandler("updatevoting", voting.updatevoting_command))
    application.add_handler(CommandHandler("resetvotes", voting.reset_voting_cooldowns_command))
    
    # Recurring messages
    application.add_handler(CommandHandler("recurring", recurring_messages_menu))
    
    # Masked users command
    async def masked_users_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show masked users menu"""
        await masked_users.show_main_menu(update, context)
    
    application.add_handler(CommandHandler("masked", masked_users_menu))
    
    # Callback query handlers
    # Admin panel callbacks (check admin_ prefix first)
    application.add_handler(CallbackQueryHandler(
        handle_admin_callback,
        pattern="^(admin_|points_|seller_|scammer_|claim_|settings_)"
    ))
    
    # Recurring messages callbacks (GroupHelpBot style + old style)
    application.add_handler(CallbackQueryHandler(
        recurring_messages.handle_callback,
        pattern="^recur_"
    ))
    
    # Old-style recurring message callbacks (hour_, minute_, repeat_, etc.)
    application.add_handler(CallbackQueryHandler(
        handle_recurring_callback,
        pattern="^(hour_|minute_|repeat_|back_to_hour_selection|toggle_message_status|show_full_customize|delete_message|customize_message|set_time|set_repetition|set_text|set_media|set_url_buttons|save_message|start_recurring_now|back_to_config)"
    ))
    
    # Masked users callbacks
    application.add_handler(CallbackQueryHandler(
        masked_users.handle_callback,
        pattern="^mask_"
    ))
    
    # Games callbacks (crypto games)
    application.add_handler(CallbackQueryHandler(
        games.handle_game_buttons,
        pattern="^(dice_|basketball_|football_|bowling_|game_|challenge_)"
    ))
    
    # Points games callbacks (dice2)
    application.add_handler(CallbackQueryHandler(
        points_games.handle_dice2_buttons,
        pattern="^dice2_"
    ))
    
    # Voting callbacks (PRESERVED from old bot)
    application.add_handler(CallbackQueryHandler(
        voting.handle_vote_button,
        pattern="^vote_"
    ))
    
    # Payment callbacks (deposit/withdraw)
    application.add_handler(CallbackQueryHandler(
        payments.handle_payment_callback,
        pattern="^(deposit|withdraw|cancel_deposit_)"
    ))
    
    # Message handler (for private chat input and group messages)
    application.add_handler(MessageHandler(~filters.COMMAND, handle_message))
    
    # Return configured application
    return application


# ============================================================================
# HTTP SERVER FOR WEBHOOKS (NOWPayments)
# ============================================================================

# Global bot instance for webhooks
BOT_INSTANCE = None

async def webhook_handler(request):
    """Handle NOWPayments webhook callbacks"""
    try:
        data = await request.json()
        payment_status = data.get('payment_status', 'unknown')
        logger.info(f"📥 NOWPayments webhook: status={payment_status}")
        
        # Process payment webhook
        import payments_webhook
        result = await payments_webhook.handle_nowpayments_webhook(data, bot=BOT_INSTANCE)
        
        if result:
            return web.Response(text="OK", status=200)
        else:
            return web.Response(text="Invalid webhook", status=400)
            
    except Exception as e:
        logger.error(f"❌ Webhook error: {e}")
        return web.Response(text="Error", status=500)


async def health_check(request):
    """Health check endpoint for Render"""
    return web.Response(text="✅ Bot is running!", status=200)


async def start_http_server():
    """Start HTTP server for webhooks and health checks"""
    app = web.Application()
    
    # Health check endpoints
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    # NOWPayments webhook endpoint
    app.router.add_post('/webhook/nowpayments', webhook_handler)
    
    # Start server
    runner = web.AppRunner(app)
    await runner.setup()
    
    port = PORT or 8080
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logger.info(f"🌐 HTTP Server started on port {port}")
    logger.info(f"   Health: https://your-app.onrender.com/health")
    logger.info(f"   NOWPayments Webhook: https://your-app.onrender.com/webhook/nowpayments")
    
    return runner


async def main():
    """Run the bot with polling + HTTP server for webhooks"""
    global BOT_INSTANCE
    logger.info("🚀 Starting OGbotas...")
    
    # Create and configure application
    application = create_application()
    
    # Set global bot instance for webhooks
    BOT_INSTANCE = application.bot
    
    # Start HTTP server for NOWPayments webhooks
    logger.info("🌐 Starting HTTP server for webhooks...")
    web_runner = await start_http_server()
    
    try:
        # Start bot in polling mode
        logger.info("🤖 Starting bot in POLLING mode...")
        await application.initialize()
        await application.start()
        
        # Load recurring message jobs from database
        logger.info("📅 Loading scheduled recurring messages...")
        recurring_messages.load_scheduled_jobs_from_db(application.bot)
        
        # Initialize barygos auto-post if enabled
        logger.info("📈 Checking barygos auto-post settings...")
        try:
            from database import database
            settings = database.get_barygos_auto_settings()
            if settings and settings.get('enabled'):
                recurring_messages.schedule_barygos_auto_job()
                interval_hours = settings.get('interval_hours', 2)
                interval_text = f"{int(interval_hours * 60)}min" if interval_hours < 1 else f"{int(interval_hours)}h"
                logger.info(f"   ✅ Barygos auto-post enabled (every {interval_text})")
            else:
                logger.info("   ℹ️ Barygos auto-post disabled")
        except Exception as e:
            logger.warning(f"   Could not initialize barygos auto-post: {e}")
        
        # Cache administrators from all registered groups
        # This helps with user resolution for existing members
        logger.info("👥 Caching group administrators...")
        try:
            groups = database.get_all_groups()
            for group in groups:
                try:
                    admins = await application.bot.get_chat_administrators(group['chat_id'])
                    for admin in admins:
                        database.store_user_info(
                            admin.user.id,
                            admin.user.username or f"user_{admin.user.id}",
                            admin.user.first_name,
                            admin.user.last_name
                        )
                    logger.info(f"   Cached {len(admins)} admins from {group['title']}")
                except Exception as e:
                    logger.warning(f"   Could not cache admins from {group.get('title', 'Unknown')}: {e}")
        except Exception as e:
            logger.warning(f"   Administrator caching failed: {e}")
        
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        
        logger.info("✅ Bot is fully operational!")
        logger.info("   - Polling: Receiving Telegram updates")
        logger.info("   - HTTP Server: Ready for payment webhooks")
        logger.info("   - Scheduled messages: Loaded from database")
        logger.info("   - User cache: Administrators cached")
        
        # Keep running forever
        import asyncio
        await asyncio.Event().wait()
        
    except KeyboardInterrupt:
        logger.info("🛑 Stopping bot...")
    finally:
        # Cleanup
        if application.updater.running:
            await application.updater.stop()
        await application.stop()
        await application.shutdown()
        await web_runner.cleanup()
        logger.info("👋 Bot stopped.")

if __name__ == '__main__':
    import asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
