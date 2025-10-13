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
from moderation_grouphelp import is_admin

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

async def show_group_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show group selection menu - GroupHelpBot style"""
    user_id = update.effective_user.id
    
    # Get all groups where the bot is present and user is admin
    # We'll get this from the database (groups where messages exist) or bot's memory
    try:
        # Get unique chat_ids from scheduled_messages and user_cache
        conn = database.get_sync_connection()
        
        # Get chats from scheduled_messages
        cursor = conn.execute('''
            SELECT DISTINCT chat_id FROM scheduled_messages 
            WHERE chat_id < 0
            ORDER BY chat_id DESC
        ''')
        chat_ids = [row[0] for row in cursor.fetchall()]
        
        # Also get from user_cache (groups where bot has been active)
        cursor = conn.execute('''
            SELECT DISTINCT user_id FROM user_cache 
            WHERE user_id < 0
            LIMIT 20
        ''')
        cache_ids = [row[0] for row in cursor.fetchall()]
        
        # Combine and deduplicate
        all_chat_ids = list(set(chat_ids + cache_ids))
        conn.close()
        
        # Get chat info for each group
        groups = []
        for chat_id in all_chat_ids[:10]:  # Limit to 10 groups
            try:
                chat = await context.bot.get_chat(chat_id)
                # Check if user is admin
                member = await context.bot.get_chat_member(chat_id, user_id)
                if member.status in ['creator', 'administrator']:
                    groups.append({
                        'id': chat_id,
                        'title': chat.title or f"Group {chat_id}"
                    })
            except Exception as e:
                logger.debug(f"Could not get chat info for {chat_id}: {e}")
                continue
        
        if not groups:
            await update.message.reply_text(
                "❌ **No groups found!**\n\n"
                "To use recurring messages:\n"
                "1. Add me to a group\n"
                "2. Make me an admin\n"
                "3. Use /recurring in the group\n\n"
                "Or use /recurring directly in the group chat.",
                parse_mode='Markdown'
            )
            return
        
        # Build selection menu
        text = (
            "🔄 **Recurring messages**\n\n"
            "Select a group to manage recurring messages:\n\n"
        )
        
        keyboard = []
        for group in groups:
            keyboard.append([
                InlineKeyboardButton(
                    f"💬 {group['title']}", 
                    callback_data=f"recur_select_group_{group['id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Cancel", callback_data="recur_close")])
        
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
            
    except Exception as e:
        logger.error(f"Error showing group selection: {e}")
        await update.message.reply_text(
            "❌ Error loading groups. Please use /recurring directly in the group chat.",
            parse_mode='Markdown'
        )


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show main recurring messages menu - EXACTLY like GroupHelpBot"""
    
    # If in private chat, show group selection first
    if update.effective_chat.type == 'private':
        # Check if a group was already selected
        if not context.user_data.get('selected_group_id'):
            await show_group_selection(update, context)
            return
        else:
            # Use the selected group
            chat_id = context.user_data['selected_group_id']
            # Verify user is still admin
            try:
                member = await context.bot.get_chat_member(chat_id, update.effective_user.id)
                if member.status not in ['creator', 'administrator']:
                    await update.message.reply_text("❌ You are no longer an admin in that group!")
                    context.user_data.pop('selected_group_id', None)
                    return
            except Exception as e:
                await update.message.reply_text("❌ Could not access that group!")
                context.user_data.pop('selected_group_id', None)
                return
    else:
        # In group chat, use current chat
        chat_id = update.effective_chat.id
        
        # Check if user is admin
        if not await is_admin(update, context):
            await update.message.reply_text("❌ Only administrators can manage recurring messages!")
            return
    
    # Get current time in Lithuanian timezone
    lithuanian_tz = pytz.timezone('Europe/Vilnius')
    current_time = datetime.now(lithuanian_tz).strftime("%d/%m/%y %H:%M")
    
    # Get existing messages
    conn = database.get_sync_connection()
    cursor = conn.execute(
        '''SELECT id, message_text, repetition_type, status, is_active 
           FROM scheduled_messages WHERE chat_id = ? ORDER BY created_at DESC''',
        (chat_id,)
    )
    messages = cursor.fetchall()
    conn.close()
    
    # Get group name
    try:
        chat = await context.bot.get_chat(chat_id)
        group_name = chat.title or "Group"
    except:
        group_name = "Group"
    
    text = (
        "🔄 **Recurring messages**\n\n"
        "From this menu you can set messages that will be sent "
        "repeatedly to the group every few minutes/hours or every "
        "few messages.\n\n"
        f"**Group:** {group_name}\n"
        f"**Current time:** {current_time}\n\n"
    )
    
    if messages:
        text += f"**Active messages:** {len(messages)}\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ Add message", callback_data="recur_add_message")]
    ]
    
    # Add buttons for existing messages
    if messages:
        keyboard.append([InlineKeyboardButton("📋 Manage messages", callback_data="recur_manage_list")])
    
    # If in private chat, add "Change group" button
    if update.effective_chat.type == 'private':
        keyboard.append([InlineKeyboardButton("🔄 Change group", callback_data="recur_change_group")])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="recur_close")])
    
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
    
    # Get group info - use selected_group_id if in private chat
    if query.message.chat.type == 'private' and context.user_data.get('selected_group_id'):
        chat_id = context.user_data['selected_group_id']
    else:
        chat_id = query.message.chat_id
    
    try:
        chat = await context.bot.get_chat(chat_id)
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
        [InlineKeyboardButton("👁️ Full preview", callback_data="recur_preview")],
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
# MULTIPLE TIMES SELECTION
# ============================================================================

async def show_multiple_times_screen(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show multiple times selection - GroupHelpBot style"""
    
    msg_config = context.user_data.get('recur_msg_config', {})
    selected_times = msg_config.get('multiple_times', [])
    
    text = (
        "⏰ **Multiple Times**\n\n"
        "Set multiple times to send the message each day.\n\n"
    )
    
    if selected_times:
        text += "**Current times:**\n"
        for i, time in enumerate(selected_times, 1):
            text += f"{i}. {time}\n"
        text += "\n"
    else:
        text += "_(No times set yet)_\n\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Time", callback_data="recur_add_time")],
    ]
    
    # Add remove buttons for existing times
    if selected_times:
        for i, time in enumerate(selected_times):
            keyboard.append([
                InlineKeyboardButton(f"🗑️ Remove {time}", callback_data=f"recur_remove_time_{i}")
            ])
    
    keyboard.append([InlineKeyboardButton("✅ Confirm", callback_data="recur_times_confirm")])
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
    
    # Change group (from private chat)
    elif data == "recur_change_group":
        context.user_data.pop('selected_group_id', None)
        await show_group_selection(update, context)
    
    # Select group
    elif data.startswith("recur_select_group_"):
        group_id = int(data.replace("recur_select_group_", ""))
        context.user_data['selected_group_id'] = group_id
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
    
    # Time (same as time slot)
    elif data == "recur_time":
        await show_time_slot_screen(query, context)
    
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
    
    # Multiple times screen
    elif data == "recur_time_multiple":
        if 'multiple_times' not in context.user_data['recur_msg_config']:
            context.user_data['recur_msg_config']['multiple_times'] = []
        await show_multiple_times_screen(query, context)
    
    # Add time to multiple times
    elif data == "recur_add_time":
        context.user_data['awaiting_input'] = 'add_time'
        await query.edit_message_text(
            "⏰ **Add Time**\n\n"
            "Please send the time in HH:MM format (24-hour)\n"
            "Example: 14:30\n\n"
            "Or /cancel to go back",
            parse_mode='Markdown'
        )
    
    # Remove time from multiple times
    elif data.startswith("recur_remove_time_"):
        index = int(data.replace("recur_remove_time_", ""))
        times = context.user_data['recur_msg_config'].get('multiple_times', [])
        if 0 <= index < len(times):
            removed = times.pop(index)
            await query.answer(f"🗑️ Removed {removed}")
        await show_multiple_times_screen(query, context)
    
    # Confirm multiple times
    elif data == "recur_times_confirm":
        times = context.user_data['recur_msg_config'].get('multiple_times', [])
        if times:
            context.user_data['recur_msg_config']['repetition_type'] = 'multiple_times'
            context.user_data['recur_msg_config']['repetition'] = f"{len(times)} times per day"
            await query.answer(f"✅ Set {len(times)} times")
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
    
    # Set media
    elif data == "recur_set_media":
        context.user_data['awaiting_input'] = 'message_media'
        await query.edit_message_text(
            "📷 **Set Media**\n\n"
            "Please send a photo, video, or document for your recurring message.\n"
            "You can also send a media URL.\n\n"
            "Or /cancel to go back",
            parse_mode='Markdown'
        )
    
    # Set URL buttons
    elif data == "recur_set_buttons":
        context.user_data['awaiting_input'] = 'message_buttons'
        await query.edit_message_text(
            "🔗 **Set URL Buttons**\n\n"
            "Send button(s) in this format:\n"
            "`Button Text - https://example.com`\n\n"
            "For multiple buttons (one per line):\n"
            "`Button 1 - https://example1.com`\n"
            "`Button 2 - https://example2.com`\n\n"
            "Or /cancel to go back",
            parse_mode='Markdown'
        )
    
    # See text
    elif data == "recur_see_text":
        msg_config = context.user_data.get('recur_msg_config', {})
        text = msg_config.get('text', '_(No text set)_')
        await query.edit_message_text(
            f"📝 **Current Text:**\n\n{text}\n\n"
            "Use /recurring to go back",
            parse_mode='Markdown'
        )
    
    # See media
    elif data == "recur_see_media":
        msg_config = context.user_data.get('recur_msg_config', {})
        media = msg_config.get('media', None)
        if media:
            await query.edit_message_text(
                f"📷 **Current Media:**\n\n{media}\n\n"
                "Use /recurring to go back",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                "📷 **Current Media:**\n\n_(No media set)_\n\n"
                "Use /recurring to go back",
                parse_mode='Markdown'
            )
    
    # See buttons
    elif data == "recur_see_buttons":
        msg_config = context.user_data.get('recur_msg_config', {})
        buttons = msg_config.get('buttons', [])
        if buttons:
            btn_text = "\n".join([f"• {btn['text']} → {btn['url']}" for btn in buttons])
            await query.edit_message_text(
                f"🔗 **Current Buttons:**\n\n{btn_text}\n\n"
                "Use /recurring to go back",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                "🔗 **Current Buttons:**\n\n_(No buttons set)_\n\n"
                "Use /recurring to go back",
                parse_mode='Markdown'
            )
    
    # Topics (not implemented yet)
    elif data == "recur_topics":
        await query.edit_message_text(
            "📋 **Select a Topic**\n\n"
            "This feature allows you to select pre-made message templates.\n\n"
            "_(Not implemented yet)_\n\n"
            "Use /recurring to go back",
            parse_mode='Markdown'
        )
    
    # Confirm days of week selection
    elif data == "recur_days_confirm":
        selected = context.user_data['recur_msg_config']['days_of_week']
        if selected:
            context.user_data['recur_msg_config']['repetition_type'] = 'days_of_week'
            context.user_data['recur_msg_config']['repetition'] = ', '.join(selected)
            await query.answer(f"✅ Selected {len(selected)} days")
        await show_message_config(query, context)
    
    # Confirm days of month selection
    elif data == "recur_dates_confirm":
        selected = context.user_data['recur_msg_config']['days_of_month']
        if selected:
            context.user_data['recur_msg_config']['repetition_type'] = 'days_of_month'
            days_str = ', '.join([str(d) for d in sorted(selected)])
            context.user_data['recur_msg_config']['repetition'] = f"Days: {days_str}"
            await query.answer(f"✅ Selected {len(selected)} dates")
        await show_message_config(query, context)
    
    # Preview message
    elif data == "recur_preview":
        await show_message_preview(query, context)
    
    # Save message (THIS IS THE CRITICAL FIX!)
    elif data == "recur_save":
        await save_and_schedule_message(query, context)
    
    # Manage messages list
    elif data == "recur_manage_list":
        await show_manage_list(query, context)
    
    # Manage single message
    elif data.startswith("recur_manage_") and not data.startswith("recur_manage_list"):
        msg_id = int(data.replace("recur_manage_", ""))
        await show_manage_single(query, context, msg_id)
    
    # Pause message
    elif data.startswith("recur_pause_"):
        msg_id = int(data.replace("recur_pause_", ""))
        await pause_message(query, context, msg_id)
    
    # Resume message
    elif data.startswith("recur_resume_"):
        msg_id = int(data.replace("recur_resume_", ""))
        await resume_message(query, context, msg_id)
    
    # Delete message
    elif data.startswith("recur_delete_"):
        msg_id = int(data.replace("recur_delete_", ""))
        await delete_message(query, context, msg_id)
    
    # Close
    elif data == "recur_close":
        await query.edit_message_text("✅ Recurring messages menu closed.")


# ============================================================================
# HELPER FUNCTION - Show Customize Screen After Input
# ============================================================================

async def show_customize_screen_after_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show customize screen with checkmarks after saving input"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
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
        [InlineKeyboardButton("👁️ Full preview", callback_data="recur_preview")],
        [InlineKeyboardButton("📋 Select a Topic", callback_data="recur_topics")],
        [InlineKeyboardButton("🔙 Back", callback_data="recur_config")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='Markdown')


# ============================================================================
# TEXT INPUT HANDLER
# ============================================================================

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text input for recurring messages"""
    
    awaiting = context.user_data.get('awaiting_input')
    
    if not awaiting:
        return
    
    # Check for media files (photo, video, document)
    if awaiting == 'message_media':
        if update.message.photo:
            # Get the largest photo
            photo = update.message.photo[-1]
            file = await context.bot.get_file(photo.file_id)
            context.user_data['recur_msg_config']['media'] = file.file_path
            context.user_data['recur_msg_config']['media_type'] = 'photo'
            context.user_data['recur_msg_config']['has_media'] = True
            context.user_data.pop('awaiting_input')
            
            await update.message.reply_text("✅ Photo saved!")
            await show_customize_screen_after_input(update, context)
            return
            
        elif update.message.video:
            video = update.message.video
            file = await context.bot.get_file(video.file_id)
            context.user_data['recur_msg_config']['media'] = file.file_path
            context.user_data['recur_msg_config']['media_type'] = 'video'
            context.user_data['recur_msg_config']['has_media'] = True
            context.user_data.pop('awaiting_input')
            
            await update.message.reply_text("✅ Video saved!")
            await show_customize_screen_after_input(update, context)
            return
            
        elif update.message.document:
            document = update.message.document
            file = await context.bot.get_file(document.file_id)
            context.user_data['recur_msg_config']['media'] = file.file_path
            context.user_data['recur_msg_config']['media_type'] = 'document'
            context.user_data['recur_msg_config']['has_media'] = True
            context.user_data.pop('awaiting_input')
            
            await update.message.reply_text("✅ Document saved!")
            await show_customize_screen_after_input(update, context)
            return
    
    text = update.message.text
    
    if not text:
        return
    
    if text == '/cancel':
        context.user_data.pop('awaiting_input', None)
        await update.message.reply_text("❌ Cancelled")
        return
    
    if awaiting == 'message_text':
        context.user_data['recur_msg_config']['text'] = text
        context.user_data['recur_msg_config']['has_text'] = True
        context.user_data.pop('awaiting_input')
        
        await update.message.reply_text("✅ Message text saved!")
        await show_customize_screen_after_input(update, context)
    
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
    
    elif awaiting == 'add_time':
        try:
            # Validate time format
            time_parts = text.split(':')
            if len(time_parts) == 2:
                hour, minute = int(time_parts[0]), int(time_parts[1])
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    # Add to multiple times list
                    if 'multiple_times' not in context.user_data['recur_msg_config']:
                        context.user_data['recur_msg_config']['multiple_times'] = []
                    
                    times = context.user_data['recur_msg_config']['multiple_times']
                    if text not in times:
                        times.append(text)
                        times.sort()  # Keep sorted
                        context.user_data.pop('awaiting_input')
                        await update.message.reply_text(
                            f"✅ Added {text}!\n\n"
                            "Use /recurring to continue configuration."
                        )
                    else:
                        await update.message.reply_text("❌ This time is already added!")
                else:
                    await update.message.reply_text("❌ Invalid time. Please use HH:MM format (00:00 - 23:59)")
            else:
                await update.message.reply_text("❌ Invalid format. Please use HH:MM format")
        except ValueError:
            await update.message.reply_text("❌ Invalid time format. Please use HH:MM (e.g., 14:30)")
    
    elif awaiting == 'message_media':
        # Handle media URL input
        if text.startswith('http://') or text.startswith('https://'):
            context.user_data['recur_msg_config']['media'] = text
            context.user_data['recur_msg_config']['media_type'] = 'url'
            context.user_data['recur_msg_config']['has_media'] = True
            context.user_data.pop('awaiting_input')
            
            await update.message.reply_text("✅ Media URL saved!")
            await show_customize_screen_after_input(update, context)
        else:
            await update.message.reply_text(
                "❌ Invalid URL. Please send a valid HTTP/HTTPS URL.\n"
                "Example: https://example.com/image.jpg"
            )
    
    elif awaiting == 'message_buttons':
        # Parse button format: "Button Text - https://example.com"
        from urllib.parse import urlparse
        
        try:
            buttons = []
            lines = text.strip().split('\n')
            
            for line in lines:
                if ' - ' not in line:
                    await update.message.reply_text(
                        "❌ Invalid format! Use:\n"
                        "`Button Text - https://example.com`"
                    )
                    return
                
                parts = line.split(' - ', 1)
                if len(parts) != 2:
                    await update.message.reply_text(
                        "❌ Invalid format! Use:\n"
                        "`Button Text - https://example.com`"
                    )
                    return
                
                btn_text = parts[0].strip()
                btn_url = parts[1].strip()
                
                # Validate URL
                parsed = urlparse(btn_url)
                if not parsed.scheme or not parsed.netloc:
                    await update.message.reply_text(
                        f"❌ Invalid URL: {btn_url}\n"
                        "Please provide a valid HTTP/HTTPS URL."
                    )
                    return
                
                # URL encoding for special characters
                from urllib.parse import quote
                # Only encode path and query, not the scheme and domain
                encoded_url = f"{parsed.scheme}://{parsed.netloc}"
                if parsed.path:
                    encoded_url += quote(parsed.path, safe='/')
                if parsed.query:
                    encoded_url += '?' + quote(parsed.query, safe='=&')
                
                buttons.append({
                    'text': btn_text,
                    'url': encoded_url
                })
            
            # Save buttons
            context.user_data['recur_msg_config']['buttons'] = buttons
            context.user_data['recur_msg_config']['has_buttons'] = True
            context.user_data.pop('awaiting_input')
            
            btn_count = len(buttons)
            await update.message.reply_text(
                f"✅ {btn_count} button{'s' if btn_count > 1 else ''} saved!"
            )
            await show_customize_screen_after_input(update, context)
            
        except Exception as e:
            logger.error(f"Error parsing buttons: {e}")
            await update.message.reply_text(
                "❌ Error parsing buttons. Please check the format:\n"
                "`Button Text - https://example.com`"
            )


# ============================================================================
# MESSAGE MANAGEMENT - List, Pause, Resume, Delete
# ============================================================================

async def show_manage_list(query, context: ContextTypes.DEFAULT_TYPE):
    """Show list of recurring messages with management options"""
    chat_id = query.message.chat_id
    
    conn = database.get_sync_connection()
    cursor = conn.execute(
        '''SELECT id, message_text, repetition_type, status, is_active, last_sent 
           FROM scheduled_messages WHERE chat_id = ? ORDER BY created_at DESC LIMIT 10''',
        (chat_id,)
    )
    messages = cursor.fetchall()
    conn.close()
    
    if not messages:
        await query.edit_message_text(
            "📋 **No recurring messages**\n\nYou haven't created any recurring messages yet.",
            parse_mode='Markdown'
        )
        return
    
    text = "📋 **Manage Recurring Messages**\n\n"
    text += "Click on a message to manage it:\n\n"
    
    keyboard = []
    for msg in messages:
        msg_id, msg_text, rep_type, status, is_active, last_sent = msg
        
        # Truncate text
        preview = msg_text[:30] + "..." if len(msg_text) > 30 else msg_text
        
        # Status icon
        icon = "✅" if is_active else "⏸️"
        
        keyboard.append([
            InlineKeyboardButton(
                f"{icon} {preview}",
                callback_data=f"recur_manage_{msg_id}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="recur_main")])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def show_manage_single(query, context: ContextTypes.DEFAULT_TYPE, message_id: int):
    """Show management options for a single message"""
    conn = database.get_sync_connection()
    cursor = conn.execute(
        '''SELECT message_text, repetition_type, status, is_active, last_sent, 
           pin_message, delete_last_message FROM scheduled_messages WHERE id = ?''',
        (message_id,)
    )
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        await query.answer("❌ Message not found")
        return
    
    msg_text, rep_type, status, is_active, last_sent, pin, delete_last = result
    
    text = "⚙️ **Manage Message**\n\n"
    text += f"**Text:** {msg_text[:100]}...\n" if len(msg_text) > 100 else f"**Text:** {msg_text}\n"
    text += f"**Type:** {rep_type}\n"
    text += f"**Status:** {'Active' if is_active else 'Paused'}\n"
    text += f"**Pin:** {'Yes' if pin else 'No'}\n"
    text += f"**Delete last:** {'Yes' if delete_last else 'No'}\n"
    
    if last_sent:
        text += f"**Last sent:** {last_sent}\n"
    
    keyboard = []
    
    # Pause/Resume button
    if is_active:
        keyboard.append([InlineKeyboardButton("⏸️ Pause", callback_data=f"recur_pause_{message_id}")])
    else:
        keyboard.append([InlineKeyboardButton("▶️ Resume", callback_data=f"recur_resume_{message_id}")])
    
    # Delete button
    keyboard.append([InlineKeyboardButton("🗑️ Delete", callback_data=f"recur_delete_{message_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="recur_manage_list")])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


async def pause_message(query, context: ContextTypes.DEFAULT_TYPE, message_id: int):
    """Pause a recurring message"""
    try:
        # Update database
        conn = database.get_sync_connection()
        cursor = conn.execute('SELECT job_id FROM scheduled_messages WHERE id = ?', (message_id,))
        result = cursor.fetchone()
        
        if result:
            job_id_str = result[0]
            
            # Remove from scheduler (handle multiple job IDs)
            if scheduler and job_id_str:
                job_ids = job_id_str.split(',')
                for job_id in job_ids:
                    try:
                        scheduler.remove_job(job_id.strip())
                        logger.info(f"Paused job {job_id}")
                    except Exception as e:
                        logger.warning(f"Could not remove job {job_id}: {e}")
            
            # Update status
            conn.execute('UPDATE scheduled_messages SET is_active = 0 WHERE id = ?', (message_id,))
            conn.commit()
        
        conn.close()
        
        await query.answer("⏸️ Message paused")
        await show_manage_single(query, context, message_id)
        
    except Exception as e:
        logger.error(f"Error pausing message: {e}")
        await query.answer(f"❌ Error: {str(e)}")


async def resume_message(query, context: ContextTypes.DEFAULT_TYPE, message_id: int):
    """Resume a paused recurring message"""
    try:
        # Get message details
        conn = database.get_sync_connection()
        cursor = conn.execute(
            '''SELECT repetition_type, interval_hours FROM scheduled_messages WHERE id = ?''',
            (message_id,)
        )
        result = cursor.fetchone()
        
        if result:
            rep_type, interval = result
            
            # Recreate job
            if rep_type == 'interval':
                trigger = IntervalTrigger(
                    hours=interval,
                    timezone=pytz.timezone('Europe/Vilnius')
                )
                
                job_id = f"recur_{query.message.chat_id}_{message_id}"
                
                init_scheduler()
                scheduler.add_job(
                    send_recurring_message,
                    trigger=trigger,
                    args=[context.bot, query.message.chat_id, message_id],
                    id=job_id,
                    replace_existing=True
                )
                
                # Update status
                conn.execute('UPDATE scheduled_messages SET is_active = 1 WHERE id = ?', (message_id,))
                conn.commit()
                
                logger.info(f"Resumed job {job_id}")
        
        conn.close()
        
        await query.answer("▶️ Message resumed")
        await show_manage_single(query, context, message_id)
        
    except Exception as e:
        logger.error(f"Error resuming message: {e}")
        await query.answer(f"❌ Error: {str(e)}")


async def delete_message(query, context: ContextTypes.DEFAULT_TYPE, message_id: int):
    """Delete a recurring message"""
    try:
        # Get job_id
        conn = database.get_sync_connection()
        cursor = conn.execute('SELECT job_id FROM scheduled_messages WHERE id = ?', (message_id,))
        result = cursor.fetchone()
        
        if result:
            job_id_str = result[0]
            
            # Remove from scheduler (handle multiple job IDs)
            if scheduler and job_id_str:
                job_ids = job_id_str.split(',')
                for job_id in job_ids:
                    try:
                        scheduler.remove_job(job_id.strip())
                        logger.info(f"Deleted job {job_id}")
                    except Exception as e:
                        logger.warning(f"Could not remove job {job_id}: {e}")
            
            # Delete from database
            conn.execute('DELETE FROM scheduled_messages WHERE id = ?', (message_id,))
            conn.commit()
        
        conn.close()
        
        await query.answer("🗑️ Message deleted")
        await show_manage_list(query, context)
        
    except Exception as e:
        logger.error(f"Error deleting message: {e}")
        await query.answer(f"❌ Error: {str(e)}")


# ============================================================================
# CORE FUNCTIONALITY - SEND RECURRING MESSAGE
# ============================================================================

async def send_recurring_message(bot, chat_id: int, message_id: int):
    """
    Send a recurring message - with pin/delete support
    This is the actual function that sends messages on schedule
    """
    try:
        # Get message config from database
        conn = database.get_sync_connection()
        cursor = conn.execute(
            '''SELECT message_text, message_media, message_buttons, pin_message, delete_last_message, 
               last_message_id, message_type FROM scheduled_messages WHERE id = ?''',
            (message_id,)
        )
        result = cursor.fetchone()
        
        if not result:
            logger.warning(f"Recurring message {message_id} not found in database")
            conn.close()
            return
        
        text, media, buttons_json, pin, delete_last, last_msg_id, msg_type = result
        
        # Delete last message if enabled
        if delete_last and last_msg_id:
            try:
                await bot.delete_message(chat_id, last_msg_id)
                logger.info(f"Deleted previous recurring message {last_msg_id}")
            except Exception as e:
                logger.warning(f"Could not delete last message: {e}")
        
        # Parse buttons
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        import json
        
        reply_markup = None
        if buttons_json:
            try:
                buttons_data = json.loads(buttons_json)
                keyboard = []
                for btn in buttons_data:
                    keyboard.append([InlineKeyboardButton(btn['text'], url=btn['url'])])
                reply_markup = InlineKeyboardMarkup(keyboard)
            except Exception as e:
                logger.error(f"Error parsing buttons: {e}")
        
        # Send new message
        sent_message = None
        if msg_type == 'text' and text:
            sent_message = await bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
        elif media:
            # Handle media messages (photo, video, etc.)
            try:
                if media.startswith('http://') or media.startswith('https://'):
                    # It's a URL
                    sent_message = await bot.send_photo(
                        chat_id=chat_id,
                        photo=media,
                        caption=text if text else None,
                        parse_mode='Markdown',
                        reply_markup=reply_markup
                    )
            except Exception as e:
                logger.error(f"Error sending media: {e}")
        
        if sent_message:
            # Pin message if enabled
            if pin:
                try:
                    await bot.pin_chat_message(chat_id, sent_message.message_id, disable_notification=True)
                    logger.info(f"Pinned recurring message {sent_message.message_id}")
                except Exception as e:
                    logger.warning(f"Could not pin message: {e}")
            
            # Update last_message_id in database
            conn.execute(
                '''UPDATE scheduled_messages SET last_message_id = ?, last_sent = CURRENT_TIMESTAMP 
                   WHERE id = ?''',
                (sent_message.message_id, message_id)
            )
            conn.commit()
            logger.info(f"Sent recurring message {message_id} to chat {chat_id}")
        
        conn.close()
        
    except Exception as e:
        logger.error(f"Error sending recurring message {message_id}: {e}")


# ============================================================================
# SAVE & SCHEDULE - CREATE ACTUAL JOBS
# ============================================================================

async def save_and_schedule_message(query, context: ContextTypes.DEFAULT_TYPE):
    """
    Save message to database and create APScheduler job
    THIS IS THE CRITICAL FIX - Actually creates working scheduled jobs!
    """
    try:
        msg_config = context.user_data.get('recur_msg_config', {})
        
        # Get chat_id - use selected_group_id if in private chat
        if query.message.chat.type == 'private' and context.user_data.get('selected_group_id'):
            chat_id = context.user_data['selected_group_id']
        else:
            chat_id = query.message.chat_id
        
        user = query.from_user
        
        # Validate configuration
        if not msg_config.get('has_text'):
            await query.answer("❌ Please set message text first!")
            return
        
        # Parse time
        time_str = msg_config.get('time', '00:00')
        hour, minute = map(int, time_str.split(':'))
        
        # Determine trigger type
        trigger = None
        repetition_type = msg_config.get('repetition_type', 'interval')
        
        if repetition_type == 'days_of_week' and msg_config.get('days_of_week'):
            # Cron trigger for specific days of week
            day_map = {
                'Monday': 'mon', 'Tuesday': 'tue', 'Wednesday': 'wed',
                'Thursday': 'thu', 'Friday': 'fri', 'Saturday': 'sat', 'Sunday': 'sun'
            }
            days = ','.join([day_map[d] for d in msg_config['days_of_week']])
            trigger = CronTrigger(
                day_of_week=days,
                hour=hour,
                minute=minute,
                timezone=pytz.timezone('Europe/Vilnius')
            )
            rep_text = f"Days: {', '.join(msg_config['days_of_week'])}"
            
        elif repetition_type == 'days_of_month' and msg_config.get('days_of_month'):
            # Cron trigger for specific days of month
            days = ','.join([str(d) for d in sorted(msg_config['days_of_month'])])
            trigger = CronTrigger(
                day=days,
                hour=hour,
                minute=minute,
                timezone=pytz.timezone('Europe/Vilnius')
            )
            rep_text = f"Dates: {days} of each month"
            
        elif repetition_type == 'multiple_times' and msg_config.get('multiple_times'):
            # Multiple cron triggers - one for each time
            # We'll handle this differently below by creating multiple jobs
            trigger = None  # Will create multiple triggers
            times = msg_config['multiple_times']
            rep_text = f"{len(times)} times per day: {', '.join(times)}"
            
        else:
            # Interval trigger (hours)
            rep_str = msg_config.get('repetition', '24 hours')
            hours = int(rep_str.split()[0])
            trigger = IntervalTrigger(
                hours=hours,
                start_date=datetime.now(pytz.timezone('Europe/Vilnius')),
                timezone=pytz.timezone('Europe/Vilnius')
            )
            rep_text = rep_str
        
        # Save to database
        import json
        
        # Prepare buttons JSON
        buttons_json = None
        if msg_config.get('buttons'):
            buttons_json = json.dumps(msg_config['buttons'])
        
        conn = database.get_sync_connection()
        cursor = conn.execute('''
            INSERT INTO scheduled_messages (
                chat_id, message_text, message_media, message_buttons, message_type, 
                repetition_type, interval_hours, pin_message, delete_last_message, 
                status, created_by, created_by_username
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            chat_id,
            msg_config.get('text', ''),
            msg_config.get('media', ''),
            buttons_json,
            'text',
            repetition_type,
            hours if repetition_type == 'interval' else 24,
            msg_config.get('pin_message', False),
            msg_config.get('delete_last', False),
            'active',
            user.id,
            user.username or user.first_name
        ))
        
        message_db_id = cursor.lastrowid
        conn.commit()
        
        # Create APScheduler job(s)
        init_scheduler()  # Ensure scheduler is initialized
        
        if repetition_type == 'multiple_times' and msg_config.get('multiple_times'):
            # Create multiple jobs - one for each time
            job_ids = []
            for i, time_str in enumerate(msg_config['multiple_times']):
                hour, minute = map(int, time_str.split(':'))
                trigger = CronTrigger(
                    hour=hour,
                    minute=minute,
                    timezone=pytz.timezone('Europe/Vilnius')
                )
                
                job_id = f"recur_{chat_id}_{message_db_id}_{i}"
                job_ids.append(job_id)
                
                scheduler.add_job(
                    send_recurring_message,
                    trigger=trigger,
                    args=[context.bot, chat_id, message_db_id],
                    id=job_id,
                    replace_existing=True
                )
            
            # Store all job IDs as comma-separated
            job_id_str = ','.join(job_ids)
            conn.execute(
                'UPDATE scheduled_messages SET job_id = ? WHERE id = ?',
                (job_id_str, message_db_id)
            )
            logger.info(f"Created {len(job_ids)} recurring message jobs for chat {chat_id}")
        else:
            # Single job
            job_id = f"recur_{chat_id}_{message_db_id}"
            
            scheduler.add_job(
                send_recurring_message,
                trigger=trigger,
                args=[context.bot, chat_id, message_db_id],
                id=job_id,
                replace_existing=True
            )
            
            # Update job_id in database
            conn.execute(
                'UPDATE scheduled_messages SET job_id = ? WHERE id = ?',
                (job_id, message_db_id)
            )
            logger.info(f"Created recurring message job {job_id} for chat {chat_id}")
        
        conn.commit()
        conn.close()
        
        # Clear user config
        context.user_data.pop('recur_msg_config', None)
        
        # Show success
        await query.edit_message_text(
            f"✅ **Recurring message saved!**\n\n"
            f"📝 Message: {msg_config.get('text', '')[:50]}...\n"
            f"🕐 Time: {time_str}\n"
            f"🔄 Repetition: {rep_text}\n"
            f"📌 Pin: {'Yes' if msg_config.get('pin_message') else 'No'}\n"
            f"🗑️ Delete last: {'Yes' if msg_config.get('delete_last') else 'No'}\n\n"
            f"The message will be sent automatically!",
            parse_mode='Markdown'
        )
        
        logger.info(f"Created recurring message job {job_id} for chat {chat_id}")
        
    except Exception as e:
        logger.error(f"Error saving recurring message: {e}")
        await query.answer(f"❌ Error: {str(e)}")


# ============================================================================
# MESSAGE PREVIEW
# ============================================================================

async def show_message_preview(query, context: ContextTypes.DEFAULT_TYPE):
    """Show formatted message preview"""
    msg_config = context.user_data.get('recur_msg_config', {})
    
    text = "👁️ **Message Preview**\n\n"
    text += "━━━━━━━━━━━━━━━━━━\n"
    
    if msg_config.get('has_text'):
        text += msg_config.get('text', '(No text)')
    else:
        text += "_(No message set yet)_"
    
    text += "\n━━━━━━━━━━━━━━━━━━\n\n"
    
    # Show settings
    if msg_config.get('pin_message'):
        text += "📌 This message will be pinned\n"
    if msg_config.get('delete_last'):
        text += "🗑️ Previous message will be deleted\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="recur_customize")]]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


# ============================================================================
# LOAD EXISTING JOBS ON STARTUP
# ============================================================================

def load_scheduled_jobs_from_db(bot):
    """
    Load all active recurring message jobs from database on bot startup
    This ensures jobs persist across bot restarts
    """
    try:
        init_scheduler()
        
        conn = database.get_sync_connection()
        cursor = conn.execute('''
            SELECT id, chat_id, message_text, repetition_type, interval_hours, job_id
            FROM scheduled_messages 
            WHERE status = 'active' AND is_active = 1
        ''')
        
        messages = cursor.fetchall()
        loaded_count = 0
        
        for msg in messages:
            msg_id, chat_id, text, rep_type, interval, old_job_id = msg
            
            try:
                # Create new job
                if rep_type == 'interval':
                    trigger = IntervalTrigger(
                        hours=interval,
                        timezone=pytz.timezone('Europe/Vilnius')
                    )
                # TODO: Recreate cron triggers for days_of_week/days_of_month
                
                job_id = f"recur_{chat_id}_{msg_id}"
                
                scheduler.add_job(
                    send_recurring_message,
                    trigger=trigger,
                    args=[bot, chat_id, msg_id],
                    id=job_id,
                    replace_existing=True
                )
                
                loaded_count += 1
                logger.info(f"Loaded recurring message job: {job_id}")
                
            except Exception as e:
                logger.error(f"Error loading job for message {msg_id}: {e}")
        
        conn.close()
        logger.info(f"Loaded {loaded_count} recurring message jobs from database")
        
    except Exception as e:
        logger.error(f"Error loading scheduled jobs: {e}")


# Export functions
__all__ = [
    'init_scheduler',
    'show_main_menu',
    'handle_callback',
    'handle_text_input',
    'send_recurring_message',
    'load_scheduled_jobs_from_db'
]

