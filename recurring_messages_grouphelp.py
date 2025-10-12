#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Recurring messages system - GroupHelpBot Interface Clone
Exact replica of GroupHelpBot's recurring messages interface
"""

import logging
import pytz
from datetime import datetime, time
from typing import Optional, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from database import database
from moderation import is_admin

logger = logging.getLogger(__name__)

# Global scheduler
scheduler = None
_scheduler_lock = None

def init_scheduler():
    """Initialize scheduler (thread-safe)"""
    global scheduler, _scheduler_lock
    
    if _scheduler_lock is None:
        import threading
        _scheduler_lock = threading.Lock()
    
    with _scheduler_lock:
        if scheduler is None:
            scheduler = AsyncIOScheduler(timezone=pytz.timezone('Europe/Vilnius'))
            scheduler.start()
            logger.info("Recurring messages scheduler initialized")


# ============================================================================
# MAIN MENU - GroupHelpBot Style
# ============================================================================

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show main recurring messages menu - EXACTLY like GroupHelpBot"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Only administrators can manage recurring messages!")
        return
    
    # Get current time in Lithuanian timezone
    lithuanian_tz = pytz.timezone('Europe/Vilnius')
    current_time = datetime.now(lithuanian_tz).strftime("%d/%m/%y %H:%M")
    
    text = (
        "🔄 **Recurring messages**\n\n"
        "From this menu you can set messages that will be sent "
        "repeatedly to the group every few minutes/hours or every "
        "few messages.\n\n"
        f"**Current time:** {current_time}"
    )
    
    keyboard = [
        [InlineKeyboardButton("➕ Add message", callback_data="recur_add_message")],
        [InlineKeyboardButton("🔙 Back", callback_data="recur_close")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )


# ============================================================================
# MESSAGE CONFIGURATION SCREEN
# ============================================================================

async def show_message_config(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show message configuration screen - EXACTLY like GroupHelpBot"""
    
    # Get or create message config
    msg_config = context.user_data.get('recur_msg_config', {
        'status': 'Off',
        'time': '20:28',
        'repetition': '24 hours',
        'pin_message': False,
        'delete_last': False,
        'has_text': False,
        'has_media': False,
        'has_buttons': False,
        'text': '',
        'days_of_week': [],
        'days_of_month': [],
        'start_date': None,
        'end_date': None,
        'scheduled_deletion': None
    })
    
    # Get group info
    try:
        chat = await context.bot.get_chat(query.message.chat_id)
        group_name = chat.title or "Group"
    except:
        group_name = "Group"
    
    # Get current time
    lithuanian_tz = pytz.timezone('Europe/Vilnius')
    current_time = datetime.now(lithuanian_tz).strftime("%d/%m/%y %H:%M")
    
    # Build status text
    status = msg_config['status']
    status_icon = "🟢" if status == "On" else "❌"
    pin_icon = "✅" if msg_config['pin_message'] else "❌"
    delete_icon = "✅" if msg_config['delete_last'] else "❌"
    
    text = (
        "🔄 **Recurring messages**\n\n"
        f"From this menu you can set messages that will be sent repeatedly to the group every few minutes/hours or every few messages.\n\n"
        f"**Current time:** {current_time}\n\n"
        f"💬 **{group_name}** • {status_icon} **{status}**\n"
        f"⏰ Time: {msg_config['time']}\n"
        f"🔄 Every {msg_config['repetition']}\n"
        f"📝 Message is {'not ' if not msg_config['has_text'] else ''}set.\n\n"
        f"📌 Pin message: {pin_icon}\n"
        f"🗑️ Delete last message: {delete_icon}"
    )
    
    keyboard = [
        [InlineKeyboardButton("✏️ Customize message", callback_data="recur_customize")],
        [
            InlineKeyboardButton("⏰ Time", callback_data="recur_time"),
            InlineKeyboardButton("🔄 Repetition", callback_data="recur_repetition")
        ],
        [InlineKeyboardButton("📅 Days of the week", callback_data="recur_days_week")],
        [InlineKeyboardButton("📅 Days of the month", callback_data="recur_days_month")],
        [InlineKeyboardButton("🕐 Set time slot", callback_data="recur_time_slot")],
        [
            InlineKeyboardButton("📅 Start date", callback_data="recur_start_date"),
            InlineKeyboardButton("📅 End date", callback_data="recur_end_date")
        ],
        [InlineKeyboardButton(f"📌 Pin message {pin_icon}", callback_data="recur_toggle_pin")],
        [InlineKeyboardButton(f"🗑️ Delete last message {delete_icon}", callback_data="recur_toggle_delete")],
        [InlineKeyboardButton("⏱️ Scheduled deletion", callback_data="recur_sched_deletion")],
        [InlineKeyboardButton("🔙 Back", callback_data="recur_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


# ============================================================================
# MESSAGE CUSTOMIZATION SCREEN
# ============================================================================

async def show_customize_screen(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show message customization screen - EXACTLY like GroupHelpBot"""
    
    msg_config = context.user_data.get('recur_msg_config', {})
    
    text_icon = "✅" if msg_config.get('has_text') else "❌"
    media_icon = "✅" if msg_config.get('has_media') else "❌"
    buttons_icon = "✅" if msg_config.get('has_buttons') else "❌"
    
    text = (
        "🔄 **Recurring messages**\n\n"
        f"📝 Text: {text_icon}\n"
        f"📷 Media: {media_icon}\n"
        f"🔗 Url Buttons: {buttons_icon}\n\n"
        "Use the buttons below to choose what you want to set"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📝 Text", callback_data="recur_set_text"),
            InlineKeyboardButton("👁️ See", callback_data="recur_see_text")
        ],
        [
            InlineKeyboardButton("📷 Media", callback_data="recur_set_media"),
            InlineKeyboardButton("👁️ See", callback_data="recur_see_media")
        ],
        [
            InlineKeyboardButton("🔗 Url Buttons", callback_data="recur_set_buttons"),
            InlineKeyboardButton("👁️ See", callback_data="recur_see_buttons")
        ],
        [InlineKeyboardButton("👁️ Full preview", callback_data="recur_full_preview")],
        [InlineKeyboardButton("📋 Select a Topic", callback_data="recur_topics")],
        [InlineKeyboardButton("🔙 Back", callback_data="recur_config")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


# ============================================================================
# TIME SLOT SELECTION
# ============================================================================

async def show_time_slot_screen(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show time slot selection - EXACTLY like GroupHelpBot"""
    
    text = (
        "🕐 **Set time slot**\n\n"
        "Choose a pre-set time or set your own custom time:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🌅 Morning (08:00)", callback_data="recur_time_08:00")],
        [InlineKeyboardButton("🌞 Midday (12:00)", callback_data="recur_time_12:00")],
        [InlineKeyboardButton("🌇 Evening (18:00)", callback_data="recur_time_18:00")],
        [InlineKeyboardButton("🌙 Night (22:00)", callback_data="recur_time_22:00")],
        [InlineKeyboardButton("⏰ Custom time", callback_data="recur_time_custom")],
        [InlineKeyboardButton("🔄 Multiple times", callback_data="recur_time_multiple")],
        [InlineKeyboardButton("🔙 Back", callback_data="recur_config")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


# ============================================================================
# REPETITION OPTIONS
# ============================================================================

async def show_repetition_screen(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show repetition options - EXACTLY like GroupHelpBot"""
    
    text = (
        "🔄 **Repetition**\n\n"
        "Choose how often to send the recurring message:"
    )
    
    keyboard = [
        [InlineKeyboardButton("⏰ Every 1 hour", callback_data="recur_rep_1h")],
        [InlineKeyboardButton("⏰ Every 2 hours", callback_data="recur_rep_2h")],
        [InlineKeyboardButton("⏰ Every 3 hours", callback_data="recur_rep_3h")],
        [InlineKeyboardButton("⏰ Every 6 hours", callback_data="recur_rep_6h")],
        [InlineKeyboardButton("⏰ Every 12 hours", callback_data="recur_rep_12h")],
        [InlineKeyboardButton("⏰ Every 24 hours", callback_data="recur_rep_24h")],
        [InlineKeyboardButton("📅 Days of the week", callback_data="recur_days_week")],
        [InlineKeyboardButton("📅 Days of the month", callback_data="recur_days_month")],
        [InlineKeyboardButton("⏱️ Custom interval", callback_data="recur_rep_custom")],
        [InlineKeyboardButton("💬 Every few messages", callback_data="recur_rep_messages")],
        [InlineKeyboardButton("🔙 Back", callback_data="recur_config")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


# ============================================================================
# DAYS OF WEEK SELECTION
# ============================================================================

async def show_days_of_week_screen(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show days of week selection - EXACTLY like GroupHelpBot"""
    
    msg_config = context.user_data.get('recur_msg_config', {})
    selected_days = msg_config.get('days_of_week', [])
    
    days = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    text = (
        "📅 **Days of the week**\n\n"
        "Select which days of the week to send the message:"
    )
    
    keyboard = []
    for day in days:
        icon = "✅" if day in selected_days else "⬜"
        keyboard.append([InlineKeyboardButton(f"{icon} {day}", callback_data=f"recur_day_{day}")])
    
    keyboard.append([InlineKeyboardButton("✅ Confirm Selection", callback_data="recur_days_confirm")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="recur_config")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


# ============================================================================
# DAYS OF MONTH SELECTION
# ============================================================================

async def show_days_of_month_screen(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show days of month selection - EXACTLY like GroupHelpBot"""
    
    msg_config = context.user_data.get('recur_msg_config', {})
    selected_days = msg_config.get('days_of_month', [])
    
    text = (
        "📅 **Days of the month**\n\n"
        "Select which days of the month to send the message:"
    )
    
    keyboard = []
    
    # Create rows of 5 days each
    for row_start in range(1, 32, 5):
        row = []
        for day in range(row_start, min(row_start + 5, 32)):
            icon = "✅" if day in selected_days else "⬜"
            row.append(InlineKeyboardButton(f"{icon}{day}", callback_data=f"recur_date_{day}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("✅ Confirm Selection", callback_data="recur_dates_confirm")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="recur_config")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


# ============================================================================
# CALLBACK HANDLER
# ============================================================================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle all recurring message callbacks - GroupHelpBot style"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    # Initialize config if needed
    if 'recur_msg_config' not in context.user_data:
        context.user_data['recur_msg_config'] = {
            'status': 'Off',
            'time': '20:28',
            'repetition': '24 hours',
            'pin_message': False,
            'delete_last': False,
            'has_text': False,
            'has_media': False,
            'has_buttons': False,
            'text': '',
            'days_of_week': [],
            'days_of_month': []
        }
    
    # Main menu
    if data == "recur_main":
        await show_main_menu(update, context)
    
    # Add message
    elif data == "recur_add_message":
        await show_message_config(query, context)
    
    # Configuration screen
    elif data == "recur_config":
        await show_message_config(query, context)
    
    # Customize message
    elif data == "recur_customize":
        await show_customize_screen(query, context)
    
    # Time slot
    elif data == "recur_time_slot":
        await show_time_slot_screen(query, context)
    
    # Repetition
    elif data == "recur_repetition":
        await show_repetition_screen(query, context)
    
    # Days of week
    elif data == "recur_days_week":
        await show_days_of_week_screen(query, context)
    
    # Days of month
    elif data == "recur_days_month":
        await show_days_of_month_screen(query, context)
    
    # Toggle pin message
    elif data == "recur_toggle_pin":
        msg_config = context.user_data['recur_msg_config']
        msg_config['pin_message'] = not msg_config['pin_message']
        await show_message_config(query, context)
    
    # Toggle delete last
    elif data == "recur_toggle_delete":
        msg_config = context.user_data['recur_msg_config']
        msg_config['delete_last'] = not msg_config['delete_last']
        await show_message_config(query, context)
    
    # Handle time selection
    elif data.startswith("recur_time_"):
        time_str = data.replace("recur_time_", "")
        if time_str in ["08:00", "12:00", "18:00", "22:00"]:
            context.user_data['recur_msg_config']['time'] = time_str
            await query.answer(f"✅ Time set to {time_str}")
            await show_message_config(query, context)
        elif time_str == "custom":
            context.user_data['awaiting_input'] = 'custom_time'
            await query.edit_message_text(
                "⏰ **Custom Time**\n\n"
                "Please send the time in HH:MM format (24-hour)\n"
                "Example: 14:30\n\n"
                "Or /cancel to go back",
                parse_mode='Markdown'
            )
    
    # Handle repetition selection
    elif data.startswith("recur_rep_"):
        rep_type = data.replace("recur_rep_", "")
        if rep_type.endswith("h"):
            hours = rep_type[:-1]
            context.user_data['recur_msg_config']['repetition'] = f"{hours} hours"
            await query.answer(f"✅ Set to every {hours} hours")
            await show_message_config(query, context)
    
    # Handle day selection (toggle)
    elif data.startswith("recur_day_"):
        day = data.replace("recur_day_", "")
        selected_days = context.user_data['recur_msg_config']['days_of_week']
        if day in selected_days:
            selected_days.remove(day)
        else:
            selected_days.append(day)
        await show_days_of_week_screen(query, context)
    
    # Handle date selection (toggle)
    elif data.startswith("recur_date_"):
        date = int(data.replace("recur_date_", ""))
        selected_dates = context.user_data['recur_msg_config']['days_of_month']
        if date in selected_dates:
            selected_dates.remove(date)
        else:
            selected_dates.append(date)
        await show_days_of_month_screen(query, context)
    
    # Set text
    elif data == "recur_set_text":
        context.user_data['awaiting_input'] = 'message_text'
        await query.edit_message_text(
            "📝 **Set Message Text**\n\n"
            "Please send the text for your recurring message.\n"
            "You can use Markdown formatting.\n\n"
            "Or /cancel to go back",
            parse_mode='Markdown'
        )
    
    # Close
    elif data == "recur_close":
        await query.edit_message_text("✅ Recurring messages menu closed.")


# ============================================================================
# TEXT INPUT HANDLER
# ============================================================================

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text input for recurring messages"""
    
    awaiting = context.user_data.get('awaiting_input')
    
    if not awaiting:
        return
    
    text = update.message.text
    
    if text == '/cancel':
        context.user_data.pop('awaiting_input', None)
        await update.message.reply_text("❌ Cancelled")
        return
    
    if awaiting == 'message_text':
        context.user_data['recur_msg_config']['text'] = text
        context.user_data['recur_msg_config']['has_text'] = True
        context.user_data.pop('awaiting_input')
        await update.message.reply_text(
            "✅ Message text saved!\n\n"
            "Use /recurring to continue configuration.",
            parse_mode='Markdown'
        )
    
    elif awaiting == 'custom_time':
        try:
            # Validate time format
            time_parts = text.split(':')
            if len(time_parts) == 2:
                hour, minute = int(time_parts[0]), int(time_parts[1])
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    context.user_data['recur_msg_config']['time'] = text
                    context.user_data.pop('awaiting_input')
                    await update.message.reply_text(
                        f"✅ Time set to {text}!\n\n"
                        "Use /recurring to continue configuration."
                    )
                else:
                    await update.message.reply_text("❌ Invalid time. Please use HH:MM format (00:00 - 23:59)")
            else:
                await update.message.reply_text("❌ Invalid format. Please use HH:MM format")
        except ValueError:
            await update.message.reply_text("❌ Invalid time format. Please use HH:MM (e.g., 14:30)")


# Export functions
__all__ = [
    'init_scheduler',
    'show_main_menu',
    'handle_callback',
    'handle_text_input'
]

