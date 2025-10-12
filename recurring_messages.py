#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recurring messages system for OGbotas - GroupHelpBot style
"""

import logging
import pytz
from datetime import datetime
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from database import database
from utils import parse_interval, SecurityValidator, safe_bot_operation
from config import TIMEZONE
from moderation import is_admin

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None
_scheduler_lock = None

def init_scheduler():
    """Initialize the global scheduler (thread-safe)"""
    global scheduler, _scheduler_lock
    
    # Create lock on first call
    if _scheduler_lock is None:
        import threading
        _scheduler_lock = threading.Lock()
    
    # Thread-safe initialization
    with _scheduler_lock:
        if scheduler is None:
            scheduler = AsyncIOScheduler(timezone=TIMEZONE)
            scheduler.start()
            logger.info("Recurring messages scheduler initialized")

async def show_message_config(query, context, private_mode=False, edit_mode=False):
    """Show message configuration screen - GroupHelpBot style"""
    chat_id = query.message.chat.id if not private_mode else context.user_data.get('target_group_id', query.message.chat.id)
    
    # Lithuanian timezone
    lithuanian_tz = pytz.timezone('Europe/Vilnius')
    current_time = datetime.now(lithuanian_tz).strftime("%d/%m/%y %H:%M")
    
    # Get group name
    group_name = "Unknown Group"
    try:
        if private_mode:
            # In private mode, try to get group name from stored info
            stored_group_name = context.user_data.get('target_group_name')
            if stored_group_name:
                group_name = stored_group_name
            else:
                # Try to get group info
                target_chat = await context.bot.get_chat(chat_id)
                group_name = target_chat.title or f"Group {chat_id}"
                context.user_data['target_group_name'] = group_name
        else:
            # Get current chat info
            chat = await context.bot.get_chat(chat_id)
            group_name = chat.title or f"Group {chat_id}"
    except Exception as e:
        logger.warning(f"Could not get group name for {chat_id}: {e}")
        group_name = f"Group {chat_id}"
    
    # Get current message config from user data or defaults
    message_config = context.user_data.get('current_message_config', {
        'status': 'Off',
        'time': '20:28',
        'repetition': 'Every 24 hours',
        'pin_message': False,
        'delete_last': False,
        'has_text': False,
        'has_media': False,
        'has_buttons': False
    })
    
    # Build the configuration screen exactly like GroupHelpBot
    text = "🔄 **Recurring messages**\n"
    text += f"From this menu you can set messages that will be sent repeatedly to the group every few minutes/hours or every few messages.\n\n"
    text += f"**Current time:** {current_time}\n\n"
    
    # Show group name and message status
    status = message_config.get('status', 'Off')
    if status == 'On':
        status_icon = "🟢"  # Green circle for On
        text += f"💬 **{group_name}** • {status_icon} **{status}**\n"
    else:
        status_icon = "❌"  # Red X for Off
        text += f"💬 **{group_name}** • {status_icon} **{status}**\n"
    text += f"⏰ Time: {message_config.get('time', '20:28')}\n"
    text += f"🔄 Every {message_config.get('repetition', '24 hours')}\n"
    text += f"📝 Message is {'not ' if not message_config.get('has_text') else ''}set."
    
    # Create keyboard exactly like GroupHelpBot - clean and simple
    # Dynamic button text based on status
    status_button_text = "❌ Off" if status == 'Off' else "🟢 On"
    
    keyboard = [
        [InlineKeyboardButton("➕ Add message", callback_data="customize_message")],
        [InlineKeyboardButton("📝 T", callback_data="show_full_customize"), 
         InlineKeyboardButton(status_button_text, callback_data="toggle_message_status"), 
         InlineKeyboardButton("🗑️", callback_data="delete_message")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except telegram.error.BadRequest as e:
        if "Message is not modified" in str(e):
            # Message content is the same, just acknowledge the callback
            logger.info("Message content unchanged in show_message_config, skipping edit")
            return
        else:
            logger.error(f"BadRequest error in show_message_config: {e}")
            await query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error in show_message_config: {e}")
        await query.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_time_selection(query, context):
    """Show time selection options - GroupHelpBot style"""
    current_config = context.user_data.get('current_message_config', {})
    selected_hour = context.user_data.get('selected_hour', None)
    
    if selected_hour is None:
        # Show hour selection first
        text = "🔄 **Recurring messages**\n\n"
        text += "👆 Select the start time."
        
        keyboard = []
        # Create hour grid (0-23)
        for row in range(6):  # 6 rows
            buttons = []
            for col in range(4):  # 4 columns
                hour = row * 4 + col
                if hour <= 23:
                    buttons.append(InlineKeyboardButton(str(hour), callback_data=f"hour_{hour}"))
            if buttons:
                keyboard.append(buttons)
        
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_config")])
    else:
        # Show minute selection after hour is selected
        text = "🔄 **Recurring messages**\n\n"
        text += f"Selected hour: **{selected_hour}**\n"
        text += "👆 Now select minutes."
        
        keyboard = []
        # Create minute grid (0, 5, 10, 15, etc.)
        minutes = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]
        for row in range(3):  # 3 rows
            buttons = []
            for col in range(4):  # 4 columns
                idx = row * 4 + col
                if idx < len(minutes):
                    minute = minutes[idx]
                    buttons.append(InlineKeyboardButton(f"{minute:02d}", callback_data=f"minute_{minute}"))
            keyboard.append(buttons)
        
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="back_to_hour_selection")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_repetition_options(query, context):
    """Show repetition options for recurring messages - GroupHelpBot style"""
    text = "🔄 **Recurring messages**\n\n"
    text += "🔄 **Repetition: Every 24 hours**\n\n"
    text += "👆 Select how often the message should be repeated."
    
    keyboard = [
        # Hours section
        [InlineKeyboardButton("• Hours •", callback_data="ignore")],
        [InlineKeyboardButton("1", callback_data="repeat_1h"), 
         InlineKeyboardButton("2", callback_data="repeat_2h"), 
         InlineKeyboardButton("3", callback_data="repeat_3h"), 
         InlineKeyboardButton("4", callback_data="repeat_4h")],
        [InlineKeyboardButton("6", callback_data="repeat_6h"), 
         InlineKeyboardButton("8", callback_data="repeat_8h"), 
         InlineKeyboardButton("12", callback_data="repeat_12h"), 
         InlineKeyboardButton("24 ✅", callback_data="repeat_24h")],
        
        # Minutes section  
        [InlineKeyboardButton("• Minutes •", callback_data="ignore")],
        [InlineKeyboardButton("⏰ 1", callback_data="repeat_1m"), 
         InlineKeyboardButton("⏰ 2", callback_data="repeat_2m"), 
         InlineKeyboardButton("⏰ 3", callback_data="repeat_3m"), 
         InlineKeyboardButton("⏰ 5", callback_data="repeat_5m")],
        [InlineKeyboardButton("10", callback_data="repeat_10m"), 
         InlineKeyboardButton("15", callback_data="repeat_15m"), 
         InlineKeyboardButton("20", callback_data="repeat_20m"), 
         InlineKeyboardButton("30", callback_data="repeat_30m")],
        
        # Special options
        [InlineKeyboardButton("🔄 Repeat every few messages", callback_data="repeat_messages")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_config")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_full_customize_interface(query, context):
    """Show full customize message interface - like second screenshot"""
    config = context.user_data.get('current_message_config', {})
    
    text = "🔄 **Recurring messages**\n\n"
    text += f"**Status:** {config.get('status', 'Off')}\n"
    text += f"⏰ **Time:** {config.get('time', '20:28')}\n"
    text += f"🔄 **Repetition:** Every {config.get('repetition', '24 hours')}\n"
    text += f"📌 **Pin message:** {'✅' if config.get('pin_message', False) else '❌'}\n"
    text += f"🗑️ **Delete last message:** {'✅' if config.get('delete_last', False) else '❌'}"
    
    keyboard = [
        [InlineKeyboardButton("✏️ Customize message", callback_data="customize_message")],
        [InlineKeyboardButton("⏰ Time", callback_data="set_time"), 
         InlineKeyboardButton("🔄 Repetition", callback_data="set_repetition")],
        [InlineKeyboardButton("📅 Days of the week", callback_data="set_days_week")],
        [InlineKeyboardButton("📅 Days of the month", callback_data="set_days_month")],
        [InlineKeyboardButton("🕐 Set time slot", callback_data="set_time_slot")],
        [InlineKeyboardButton("📅 Start date", callback_data="set_start_date"), 
         InlineKeyboardButton("📅 End date", callback_data="set_end_date")],
        [InlineKeyboardButton(f"📌 Pin message {'✅' if config.get('pin_message', False) else '❌'}", 
                            callback_data="toggle_pin_message")],
        [InlineKeyboardButton(f"🗑️ Delete last message {'✅' if config.get('delete_last', False) else '❌'}", 
                            callback_data="toggle_delete_last")],
        [InlineKeyboardButton("⏱️ Scheduled deletion", callback_data="scheduled_deletion")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_config")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def show_message_customization(query, context):
    """Show message customization screen - GroupHelpBot style"""
    message_config = context.user_data.get('current_message_config', {})
    
    text = "🔄 **Recurring messages**\n\n"
    text += f"📝 **Text:** {'✅' if message_config.get('has_text', False) else '❌'}\n"
    text += f"📷 **Media:** {'✅' if message_config.get('has_media', False) else '❌'}\n"
    text += f"🔗 **Url Buttons:** {'✅' if message_config.get('has_buttons', False) else '❌'}\n\n"
    text += "Choose what to customize:"
    
    keyboard = [
        [InlineKeyboardButton("📝 Set Text", callback_data="set_text")],
        [InlineKeyboardButton("📷 Set Media", callback_data="set_media")],
        [InlineKeyboardButton("🔗 Set URL Buttons", callback_data="set_url_buttons")],
        [InlineKeyboardButton("👀 Preview Message", callback_data="preview_message")],
        [InlineKeyboardButton("✅ Save Message", callback_data="save_message")],
        [InlineKeyboardButton("🔙 Back", callback_data="back_to_config")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')

async def delete_current_message(query, context):
    """Delete/reset current message configuration"""
    # Reset the message config to defaults
    context.user_data['current_message_config'] = {
        'status': 'Off',
        'time': '20:28',
        'repetition': 'Every 24 hours',
        'pin_message': False,
        'delete_last': False,
        'has_text': False,
        'has_media': False,
        'has_buttons': False
    }
    
    await query.answer("🗑️ Pranešimo konfigūracija ištrinta")
    await show_message_config(query, context)

async def toggle_message_status_main(query, context):
    """Toggle message on/off status"""
    config = context.user_data.get('current_message_config', {})
    current_status = config.get('status', 'Off')
    new_status = 'On' if current_status == 'Off' else 'Off'
    config['status'] = new_status
    context.user_data['current_message_config'] = config
    
    await query.answer(f"📊 Statusas pakeistas į: {new_status}")
    await show_message_config(query, context)

async def save_recurring_message(query, context):
    """Save recurring message to database"""
    config = context.user_data.get('current_message_config', {})
    chat_id = context.user_data.get('target_group_id', query.message.chat.id)
    user_id = query.from_user.id
    username = query.from_user.username or f"User{user_id}"
    
    try:
        # Parse interval
        repetition = config.get('repetition', '24 hours')
        interval_hours = parse_interval(repetition)
        
        # Save to database
        message_id = database.add_scheduled_message(
            chat_id=chat_id,
            message_text=config.get('message_text', ''),
            message_media=config.get('message_media'),
            message_buttons=config.get('message_buttons'),
            message_type=config.get('message_type', 'text'),
            repetition_type=repetition,
            interval_hours=interval_hours,
            pin_message=config.get('pin_message', False),
            delete_last_message=config.get('delete_last', False),
            created_by=user_id,
            created_by_username=username,
            is_active=config.get('status', 'Off') == 'On'
        )
        
        if message_id:
            # Show confirmation
            text = "✅ **Message Saved Successfully!**\n\n"
            text += f"📊 Status: {config.get('status', 'Off')}\n"
            text += f"⏰ Time: {config.get('time', '20:28')}\n"
            text += f"🔄 Repetition: Every {repetition}\n\n"
            text += "Would you like to start sending this message now?"
            
            keyboard = [
                [InlineKeyboardButton("🚀 Start Now", callback_data="start_recurring_now")],
                [InlineKeyboardButton("⏰ Start Later", callback_data="start_recurring_later")],
                [InlineKeyboardButton("🔙 Back", callback_data="back_to_config")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
            
            logger.info(f"Saved recurring message ID {message_id} for chat {chat_id}")
        else:
            await query.answer("❌ Error saving message")
            
    except Exception as e:
        logger.error(f"Error saving recurring message: {e}")
        await query.answer("❌ Error saving message")

async def start_recurring_message_now(query, context):
    """Start recurring message immediately"""
    config = context.user_data.get('current_message_config', {})
    chat_id = context.user_data.get('target_group_id', query.message.chat.id)
    
    try:
        # Update config to active
        config['status'] = 'On'
        context.user_data['current_message_config'] = config
        
        # Schedule the job
        await schedule_recurring_message(chat_id, config, context)
        
        # Send first message immediately
        await send_recurring_message_now(chat_id, config, context)
        
        await query.answer("🚀 Recurring message started!")
        await show_message_config(query, context)
        
    except Exception as e:
        logger.error(f"Error starting recurring message: {e}")
        await query.answer("❌ Error starting message")

async def schedule_recurring_message(chat_id: int, config: dict, context):
    """Schedule recurring message job"""
    global scheduler
    if not scheduler:
        init_scheduler()
    
    try:
        repetition = config.get('repetition', '24 hours')
        interval_hours = parse_interval(repetition)
        
        # Create job ID
        job_id = f"recurring_{chat_id}_{datetime.now().timestamp()}"
        
        # Schedule job
        scheduler.add_job(
            send_recurring_message_job,
            'interval',
            hours=interval_hours,
            id=job_id,
            args=[chat_id, config, context.bot]
        )
        
        logger.info(f"Scheduled recurring message job {job_id} for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error scheduling recurring message: {e}")

async def send_recurring_message_job(chat_id: int, config: dict, bot):
    """Job function to send recurring message"""
    try:
        message_text = config.get('message_text', 'Recurring message')
        
        # Send message
        await bot.send_message(chat_id=chat_id, text=message_text)
        
        logger.info(f"Sent recurring message to chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error sending recurring message to {chat_id}: {e}")

async def send_recurring_message_now(chat_id: int, config: dict, context):
    """Send recurring message immediately"""
    try:
        message_text = config.get('message_text', 'Recurring message')
        
        # Send message
        await context.bot.send_message(chat_id=chat_id, text=message_text)
        
        logger.info(f"Sent immediate recurring message to chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error sending immediate recurring message to {chat_id}: {e}")

# Message input handlers
async def set_message_text(query, context):
    """Set message text"""
    context.user_data['waiting_for_text'] = True
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="customize_message")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📝 **Set Message Text**\n\n"
        "Send me the text you want to use for the recurring message:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def set_message_media(query, context):
    """Set message media"""
    logger.info("set_message_media function called - setting waiting_for_media = True")
    context.user_data['waiting_for_media'] = True
    logger.info(f"waiting_for_media state set. Current user_data keys: {list(context.user_data.keys())}")
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="customize_message")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "📷 **Set Message Media**\n\n"
        "Send me a photo, video, or GIF to include with the message:",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def set_url_buttons(query, context):
    """Set URL buttons"""
    context.user_data['waiting_for_buttons'] = True
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="customize_message")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(
        "🔗 **Set URL Buttons**\n\n"
        "Send me the button configuration in format:\n"
        "`Button Text | URL`\n\n"
        "For multiple buttons, send each on a new line.",
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )

async def process_private_chat_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Process input in private chat for message configuration"""
    
    # Store user info
    if update.effective_user and update.effective_user.username:
        database.store_user_info(
            update.effective_user.id,
            update.effective_user.username,
            update.effective_user.first_name,
            update.effective_user.last_name
        )
    
    # Handle text input
    if context.user_data.get('waiting_for_text') and update.message.text:
        context.user_data['waiting_for_text'] = False
        
        # Store text
        config = context.user_data.get('current_message_config', {})
        config['message_text'] = SecurityValidator.sanitize_text(update.message.text)
        config['has_text'] = True
        context.user_data['current_message_config'] = config
        
        # Create mock query to return to customization
        class MockQuery:
            def __init__(self, message):
                self.message = message
                self.from_user = message.from_user
            
            async def edit_message_text(self, text, reply_markup=None, parse_mode=None):
                await self.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            
            async def answer(self, text):
                pass
        
        mock_query = MockQuery(update.message)
        await show_message_customization(mock_query, context)
        return
    
    # Handle media input
    if context.user_data.get('waiting_for_media'):
        context.user_data['waiting_for_media'] = False
        
        config = context.user_data.get('current_message_config', {})
        
        # Handle different media types
        if update.message.photo:
            file_id = update.message.photo[-1].file_id
            config['message_media'] = file_id
            config['message_type'] = 'photo'
            config['has_media'] = True
        elif update.message.video:
            file_id = update.message.video.file_id
            config['message_media'] = file_id
            config['message_type'] = 'video'
            config['has_media'] = True
        elif update.message.animation:
            file_id = update.message.animation.file_id
            config['message_media'] = file_id
            config['message_type'] = 'animation'
            config['has_media'] = True
        elif update.message.document:
            file_id = update.message.document.file_id
            config['message_media'] = file_id
            config['message_type'] = 'document'
            config['has_media'] = True
        
        context.user_data['current_message_config'] = config
        
        # Create mock query to return to customization
        class MockQuery:
            def __init__(self, message):
                self.message = message
                self.from_user = message.from_user
            
            async def edit_message_text(self, text, reply_markup=None, parse_mode=None):
                await self.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
            
            async def answer(self, text):
                pass
        
        mock_query = MockQuery(update.message)
        await show_message_customization(mock_query, context)
        return
