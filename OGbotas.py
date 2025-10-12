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
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        file_handler,
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

# Import modules
from config import BOT_TOKEN, WEBHOOK_URL, PORT
from database import database
from utils import data_manager, message_tracker
import moderation_grouphelp as moderation
import recurring_messages_grouphelp as recurring_messages
import masked_users
import admin_panel
import games
import payments
import points_games

# Telegram imports
import telegram
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
from telegram import Update
from telegram.ext import ContextTypes

# Initialize scheduler
recurring_messages.init_scheduler()

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
    """Start command"""
    await update.message.reply_text(
        "🤖 **OGbotas Active!**\n\n"
        "Available commands:\n"
        "🔨 `/ban @user` - Ban user\n"
        "🔓 `/unban @user` - Unban user\n"
        "🔇 `/mute @user` - Mute user\n"
        "🔊 `/unmute @user` - Unmute user\n"
        "🔄 `/recurring` - Recurring messages\n"
        "🔍 `/lookup @user` - Lookup user info\n"
        "📊 `/patikra @user` - Check if scammer\n\n"
        "Bot is ready to serve! 🚀",
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
        "**Points Games (Saved Points Only):**\n"
        "• `/dice2 <points> <prediction>` - 🎲 Dice betting\n"
        "• `/coinflip <points> heads/tails` - 🪙 Coinflip\n"
        "• `/points` - Check your points balance\n\n"
        "**Balance & Payments:**\n"
        "• `/balance` - Check balance, deposit/withdraw\n\n"
        "**Admin Commands:**\n"
        "• `/addbalance @user amount` - Add funds\n"
        "• `/removebalance @user amount` - Remove funds\n\n"
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
    await recurring_messages.show_main_menu(update, context)

# Callback query handler
async def handle_recurring_callback(query, context):
    """Handle recurring messages callbacks"""
    data = query.data
    
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
        else:
            await query.answer("Unknown callback")
    
    except Exception as e:
        logger.error(f"Error in handle_recurring_callback: {e}")
        await query.answer("❌ Error processing request")


async def handle_admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin panel callback queries"""
    query = update.callback_query
    await query.answer()
    
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
    
    # Handle private chat input
    if update.effective_chat.type == 'private':
        # Check if it's admin panel input
        if context.user_data.get('admin_action'):
            await admin_panel.handle_admin_input(update, context)
            return
        
        # Check if awaiting input for recurring messages (GroupHelpBot style)
        if context.user_data.get('awaiting_input'):
            await recurring_messages.handle_text_input(update, context)
            return
        
        # Check if awaiting input for masked users
        if context.user_data.get('mask_action'):
            await masked_users.handle_text_input(update, context)
            return
        
        # Check if awaiting game challenge
        if context.user_data.get('awaiting_challenge'):
            await games.handle_game_challenge(update, context)
            return
        
        # Check if awaiting withdrawal details
        if await payments.handle_withdrawal_text(update, context):
            return
        
        # Otherwise handle old recurring messages input
        # await recurring_messages.process_private_chat_input(update, context)
        return
    
    # Handle group messages
    # TODO: Future feature - banned words filtering will be implemented here
    # For now, just log group messages for analytics
    logger.debug(f"Group message from user {update.effective_user.id} in chat {update.effective_chat.id}")

def main() -> None:
    """Start the bot."""
    if not BOT_TOKEN:
        logger.error("❌ ERROR: BOT_TOKEN environment variable not set!")
        return
    
    logger.info("🤖 Starting OGbotas...")
    
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("admin", admin_command))
    
    # Moderation commands
    application.add_handler(CommandHandler("ban", moderation.ban_user))
    application.add_handler(CommandHandler("unban", moderation.unban_user))
    application.add_handler(CommandHandler("mute", moderation.mute_user))
    application.add_handler(CommandHandler("unmute", moderation.unmute_user))
    application.add_handler(CommandHandler("lookup", moderation.lookup_user))
    application.add_handler(CommandHandler("patikra", patikra_command))
    
    # Casino games commands (with real crypto)
    application.add_handler(CommandHandler("dice", games.dice_command))
    application.add_handler(CommandHandler("basketball", games.basketball_command))
    application.add_handler(CommandHandler("football", games.football_command))
    application.add_handler(CommandHandler("bowling", games.bowling_command))
    
    # Points games commands (saved points only, NO crypto)
    application.add_handler(CommandHandler("dice2", points_games.dice2_command))
    application.add_handler(CommandHandler("coinflip", points_games.coinflip_command))
    application.add_handler(CommandHandler("points", points_games.points_command))
    
    # Payment commands (balance, deposit, withdraw)
    application.add_handler(CommandHandler("balance", payments.balance_command))
    application.add_handler(CommandHandler("addbalance", payments.add_balance_command))
    application.add_handler(CommandHandler("removebalance", payments.remove_balance_command))
    
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
    
    # Recurring messages callbacks (GroupHelpBot style)
    application.add_handler(CallbackQueryHandler(
        recurring_messages.handle_callback,
        pattern="^recur_"
    ))
    
    # Masked users callbacks
    application.add_handler(CallbackQueryHandler(
        masked_users.handle_callback,
        pattern="^mask_"
    ))
    
    # Games callbacks
    application.add_handler(CallbackQueryHandler(
        games.handle_game_buttons,
        pattern="^(dice_|basketball_|football_|bowling_|game_|challenge_)"
    ))
    
    # Payment callbacks (deposit/withdraw)
    application.add_handler(CallbackQueryHandler(
        payments.handle_payment_callback,
        pattern="^(deposit|withdraw)"
    ))
    
    # Old recurring messages callbacks (fallback)
    application.add_handler(CallbackQueryHandler(handle_recurring_callback))
    
    # Message handler (for private chat input and group messages)
    application.add_handler(MessageHandler(~filters.COMMAND, handle_message))
    
    # Start the bot
    if WEBHOOK_URL:
        # Sanitize URL for logging (hide token)
        safe_webhook = f"{WEBHOOK_URL}/webhook/***TOKEN***"
        logger.info(f"🌐 Starting webhook mode on {safe_webhook}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            webhook_url=f"{WEBHOOK_URL}/webhook/{BOT_TOKEN}",
            url_path=f"/webhook/{BOT_TOKEN}"
        )
    else:
        logger.info("🔄 Starting polling mode...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
