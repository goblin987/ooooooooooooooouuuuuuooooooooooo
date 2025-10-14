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
logging.getLogger('apscheduler').setLevel(logging.WARNING)
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

# Telegram imports
import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram import Update
from telegram.ext import ContextTypes
from aiohttp import web

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
    """Help command"""
    await update.message.reply_text(
        "🤖 **OGbotas Help**\n\n"
        "**Moderation:**\n"
        "• `/ban @user [reason]` - Ban user\n"
        "• `/unban @user` - Unban user\n"
        "• `/mute @user [minutes]` - Mute user\n"
        "• `/unmute @user` - Unmute user\n\n"
        "**Recurring Messages:**\n"
        "• `/recurring` - Manage recurring messages\n\n"
        "**Utilities:**\n"
        "• `/lookup @user` - Lookup user info\n"
        "• `/patikra @user` - Check if user is scammer\n\n"
        "**Admin Panel:**\n"
        "• `/admin` - Interactive admin panel\n"
        "  - 💰 Points, ⭐ Sellers, 🚨 Scammers\n"
        "  - 📋 Claims, 🔍 Lookup, 📊 Stats\n"
        "  - 🔄 Recurring Messages\n"
        "  - 👤 Masked Users\n\n"
        "**Group Management:**\n"
        "• `/recurring` - Recurring messages (GroupHelpBot style)\n"
        "• `/masked` - Manage masked/anonymous users\n\n"
        "**Casino Games (Player vs Player with Crypto):**\n"
        "• `/dice <points>` - 🎲 Dice game\n"
        "• `/basketball <points>` - 🏀 Basketball\n"
        "• `/football <points>` - ⚽ Football\n"
        "• `/bowling <points>` - 🎳 Bowling\n\n"
        "**Points Games (Saved Points, PvP):**\n"
        "• `/dice2 <points>` - 🎲 Dice PvP (no crypto)\n"
        "• `/points` - Check your points balance\n\n"
        "**Balance & Payments:**\n"
        "• `/balance` - Check balance, deposit/withdraw\n\n"
        "**Voting System:**\n"
        "• `/balsuoti` - Link to voting group\n"
        "• `/barygos` - View seller leaderboards\n\n"
        "**Admin Commands:**\n"
        "• `/addbalance @user amount` - Add funds\n"
        "• `/removebalance @user amount` - Remove funds\n"
        "• `/updatevoting` - Update voting buttons\n\n"
        "**Note:** Admin permissions required for most commands.",
        parse_mode='Markdown'
    )

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show admin panel"""
    await admin_panel.show_admin_panel(update, context)


async def patikra_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Check if user is scammer command.
    Currently a placeholder until full scammer database integration.
    """
    if not context.args:
        await update.message.reply_text(
            "❌ **Usage:** `/patikra @username`\n\n"
            "Check if a user is in the scammer database.",
            parse_mode='Markdown'
        )
        return
    
    username = context.args[0].lstrip('@')
    
    # Placeholder response until full integration with readonly_scammer_bot
    await update.message.reply_text(
        f"🔍 **Scammer Check: @{username}**\n\n"
        "⚙️ Scammer database integration is in progress.\n\n"
        "**Current Status:**\n"
        "• Database: Ready\n"
        "• API Sync: In Development\n"
        "• Full Integration: Coming Soon\n\n"
        "💡 This feature will be fully functional after integration with the scammer database API.",
        parse_mode='Markdown'
    )

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
    elif data == "seller_add":
        await admin_panel.seller_add_start(query, context)
    elif data == "seller_remove":
        await admin_panel.seller_remove_start(query, context)
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
        await admin_panel.show_claim_detail(query, context, report_id)
    elif data.startswith("claim_confirm_"):
        report_id = data.replace("claim_confirm_", "")
        await admin_panel.confirm_claim(query, context, report_id)
    elif data.startswith("claim_dismiss_"):
        report_id = data.replace("claim_dismiss_", "")
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
    
    # Masked Users (from admin panel)
    elif data == "admin_masked":
        await masked_users.show_main_menu(update, context)
    
    # Close panel
    elif data == "admin_close":
        await query.edit_message_text("✅ Admin panel closed.")
    
    else:
        await query.answer("Feature coming soon!")


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
    application.add_handler(CommandHandler("ban", moderation.ban_user))
    application.add_handler(CommandHandler("unban", moderation.unban_user))
    application.add_handler(CommandHandler("mute", moderation.mute_user))
    application.add_handler(CommandHandler("unmute", moderation.unmute_user))
    application.add_handler(CommandHandler("lookup", moderation.lookup_user))
    application.add_handler(CommandHandler("info", moderation.info_user))
    application.add_handler(CommandHandler("patikra", patikra_command))
    
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
    application.add_handler(CommandHandler("points", points_games.points_command))
    
    # Payment commands (balance, deposit, withdraw)
    application.add_handler(CommandHandler("balance", payments.balance_command))
    application.add_handler(CommandHandler("pinigine", payments.balance_command))  # Lithuanian alias
    application.add_handler(CommandHandler("setbalance", payments.setbalance_command))
    application.add_handler(CommandHandler("addbalance", payments.add_balance_command))
    application.add_handler(CommandHandler("removebalance", payments.remove_balance_command))

    # Barygos banners command
    from barygos_banners import generate_all as _gen_banners
    async def barygos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
        import os, random
        paths = [f"barygos_{i}.png" for i in range(1,6)]
        existing = [p for p in paths if os.path.exists(p)]
        if not existing:
            try:
                _gen_banners()
                existing = [p for p in paths if os.path.exists(p)]
            except Exception:
                existing = []
        if not existing:
            await update.message.reply_text("❌ Nerasta banerių ir nepavyko sugeneruoti.")
            return
        path = random.choice(existing)
        with open(path, "rb") as img:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=img, caption="🔒 Apsisaugok • CRYPTO")

    application.add_handler(CommandHandler("barygos", barygos_command))
    
    # Voting commands (PRESERVED from old bot - keeps 3 months of data!)
    application.add_handler(CommandHandler("balsuoti", voting.balsuoti_command))
    application.add_handler(CommandHandler("barygos", voting.barygos_command))
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
        pattern="^(admin_|points_|seller_|scammer_|claim_)"
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
        
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        
        logger.info("✅ Bot is fully operational!")
        logger.info("   - Polling: Receiving Telegram updates")
        logger.info("   - HTTP Server: Ready for payment webhooks")
        logger.info("   - Scheduled messages: Loaded from database")
        
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
