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
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from database import database
from moderation_grouphelp import is_admin
from config import VOTING_GROUP_CHAT_ID

logger = logging.getLogger(__name__)

# Global scheduler and bot instance
scheduler = None
_scheduler_lock = None
_bot_instance = None

def init_scheduler():
    """Initialize scheduler (thread-safe)"""
    global scheduler, _scheduler_lock
    
    if _scheduler_lock is None:
        import threading
        _scheduler_lock = threading.Lock()
    
    with _scheduler_lock:
        if scheduler is None:
            scheduler = BackgroundScheduler(timezone=pytz.UTC)
            scheduler.start()
            logger.info("✅ Recurring messages scheduler initialized (BackgroundScheduler)")

def set_bot_instance(bot):
    """Store bot instance for scheduler jobs"""
    global _bot_instance
    _bot_instance = bot
    logger.info("Bot instance stored for recurring messages")


# ============================================================================
# MAIN MENU - GroupHelpBot Style
# ============================================================================

async def show_group_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show group selection menu - GroupHelpBot style"""
    user_id = update.effective_user.id
    
    # Get all registered groups from the groups table
    try:
        # Get groups from database
        registered_groups = database.get_all_groups()
        
        # Verify user is admin in each group and bot is still present
        groups = []
        for group_data in registered_groups:
            chat_id = group_data['chat_id']
            try:
                # Check if bot is still in the group
                chat = await context.bot.get_chat(chat_id)
                # Check if user is admin
                member = await context.bot.get_chat_member(chat_id, user_id)
                if member.status in ['creator', 'administrator']:
                    groups.append({
                        'id': chat_id,
                        'title': group_data['title'] or chat.title or f"Group {chat_id}"
                    })
            except Exception as e:
                logger.debug(f"Could not access group {chat_id}: {e}")
                continue
        
        if not groups:
            text = (
                "❌ **Nerasta grupių!**\n\n"
                "Norėdami naudoti pasikartojančius skelbimus:\n"
                "1. Pridėkite mane į grupę\n"
                "2. Padarykite mane administratoriumi\n"
                "3. Naudokite /recurring grupėje\n\n"
                "Arba naudokite /recurring tiesiogiai grupės pokalbyje."
            )
            
            if update.callback_query:
                await update.callback_query.edit_message_text(text, parse_mode='Markdown')
            else:
                await update.effective_message.reply_text(text, parse_mode='Markdown')
            return
        
        # Build selection menu
        text = (
            "🔄 **Pasikartojantys skelbimai**\n\n"
            "Pasirinkite grupę pasikartojančių skelbimų tvarkymui:\n\n"
        )
        
        keyboard = []
        for group in groups:
            keyboard.append([
                InlineKeyboardButton(
                    f"💬 {group['title']}", 
                    callback_data=f"recur_select_group_{group['id']}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 Atšaukti", callback_data="recur_close")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await update.effective_message.reply_text(
                text,
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
            
    except Exception as e:
        logger.error(f"Error showing group selection: {e}")
        
        text = "❌ Klaida įkeliant grupes. Naudokite /recurring tiesiogiai grupės pokalbyje."
        
        if update.callback_query:
            await update.callback_query.edit_message_text(text, parse_mode='Markdown')
        else:
            await update.effective_message.reply_text(text, parse_mode='Markdown')


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
                    text = "❌ You are no longer an admin in that group!"
                    if update.callback_query:
                        await update.callback_query.edit_message_text(text)
                    else:
                        await update.effective_message.reply_text(text)
                    context.user_data.pop('selected_group_id', None)
                    return
            except Exception as e:
                text = "❌ Could not access that group!"
                if update.callback_query:
                    await update.callback_query.edit_message_text(text)
                else:
                    await update.effective_message.reply_text(text)
                context.user_data.pop('selected_group_id', None)
                return
    else:
        # In group chat, use current chat
        chat_id = update.effective_chat.id
        
        # Check if user is admin
        if not await is_admin(update, context):
            text = "❌ Tik administratoriai gali tvarkyti pasikartojančius skelbimus!"
            if update.callback_query:
                await update.callback_query.edit_message_text(text)
            else:
                await update.effective_message.reply_text(text)
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
        "🔄 **Pasikartojantys skelbimai**\n\n"
        "Iš šio meniu galite nustatyti pranešimus, kurie bus siunčiami "
        "pakartotinai į grupę kas kelias minutes/valandas arba kas "
        "kelis pranešimus.\n\n"
        f"**Grupė:** {group_name}\n"
        f"**Dabartinis laikas:** {current_time}\n\n"
    )
    
    if messages:
        text += f"**Aktyvūs skelbimai:** {len(messages)}\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ Pridėti skelbimą", callback_data="recur_add_message")]
    ]
    
    # Add buttons for existing messages
    if messages:
        keyboard.append([InlineKeyboardButton("📋 Tvarkyti skelbimus", callback_data="recur_manage_list")])
    
    # If in private chat, add "Change group" button
    if update.effective_chat.type == 'private':
        keyboard.append([InlineKeyboardButton("🔄 Keisti grupę", callback_data="recur_change_group")])
    
    keyboard.append([InlineKeyboardButton("🔙 Atgal", callback_data="recur_close")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.effective_message.reply_text(
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
        "🔄 **Pasikartojantys skelbimai**\n\n"
        f"Iš šio meniu galite nustatyti pranešimus, kurie bus siunčiami pakartotinai į grupę kas kelias minutes/valandas.\n\n"
        f"**Dabartinis laikas:** {current_time}\n\n"
        f"💬 **{group_name}** • {status_icon} **{status}**\n"
        f"⏰ Laikas: {msg_config['time']}\n"
        f"🔄 Kas {msg_config['repetition']}\n"
        f"📝 Pranešimas {'ne' if not msg_config['has_text'] else ''}nustatytas.\n\n"
        f"📌 Prisegti pranešimą: {pin_icon}\n"
        f"🗑️ Ištrinti paskutinį pranešimą: {delete_icon}"
    )
    
    keyboard = [
        [InlineKeyboardButton("✏️ Pritaikyti pranešimą", callback_data="recur_customize")],
        [
            InlineKeyboardButton("⏰ Laikas", callback_data="recur_time"),
            InlineKeyboardButton("🔄 Pasikartojimas", callback_data="recur_repetition")
        ],
        [InlineKeyboardButton("📅 Savaitės dienos", callback_data="recur_days_week")],
        [InlineKeyboardButton("📅 Mėnesio dienos", callback_data="recur_days_month")],
        [InlineKeyboardButton("🕐 Nustatyti laiko tarpą", callback_data="recur_time_slot")],
        [
            InlineKeyboardButton("📅 Pradžios data", callback_data="recur_start_date"),
            InlineKeyboardButton("📅 Pabaigos data", callback_data="recur_end_date")
        ],
        [InlineKeyboardButton(f"📌 Prisegti pranešimą {pin_icon}", callback_data="recur_toggle_pin")],
        [InlineKeyboardButton(f"🗑️ Ištrinti paskutinį {delete_icon}", callback_data="recur_toggle_delete")],
        [InlineKeyboardButton("⏱️ Suplanuotas ištrynimas", callback_data="recur_sched_deletion")],
        [InlineKeyboardButton("👁️ Peržiūra", callback_data="recur_preview")],
        [InlineKeyboardButton("💾 Išsaugoti", callback_data="recur_save")],
        [InlineKeyboardButton("🔙 Atgal", callback_data="recur_main")]
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
        "🔄 **Pasikartojantys skelbimai**\n\n"
        f"📝 Tekstas: {text_icon}\n"
        f"📷 Medija: {media_icon}\n"
        f"🔗 URL Mygtukai: {buttons_icon}\n\n"
        "Naudokite mygtukus žemiau, kad pasirinktumėte ką norite nustatyti"
    )
    
    keyboard = [
        [
            InlineKeyboardButton("📝 Tekstas", callback_data="recur_set_text"),
            InlineKeyboardButton("👁️ Žiūrėti", callback_data="recur_see_text")
        ],
        [
            InlineKeyboardButton("📷 Medija", callback_data="recur_set_media"),
            InlineKeyboardButton("👁️ Žiūrėti", callback_data="recur_see_media")
        ],
        [
            InlineKeyboardButton("🔗 URL Mygtukai", callback_data="recur_set_buttons"),
            InlineKeyboardButton("👁️ Žiūrėti", callback_data="recur_see_buttons")
        ],
        [InlineKeyboardButton("👁️ Pilna peržiūra", callback_data="recur_preview")],
        [InlineKeyboardButton("📋 Pasirinkti temą", callback_data="recur_topics")],
        [InlineKeyboardButton("🔙 Atgal", callback_data="recur_config")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


# ============================================================================
# TIME SLOT SELECTION
# ============================================================================

async def show_time_slot_screen(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show time slot selection - EXACTLY like GroupHelpBot"""
    
    text = (
        "🕐 **Nustatyti laiko tarpą**\n\n"
        "Pasirinkite iš anksto nustatytą laiką arba nustatykite savo:"
    )
    
    keyboard = [
        [InlineKeyboardButton("🌅 Rytas (08:00)", callback_data="recur_time_08:00")],
        [InlineKeyboardButton("🌞 Diena (12:00)", callback_data="recur_time_12:00")],
        [InlineKeyboardButton("🌇 Vakaras (18:00)", callback_data="recur_time_18:00")],
        [InlineKeyboardButton("🌙 Naktis (22:00)", callback_data="recur_time_22:00")],
        [InlineKeyboardButton("⏰ Pasirinkti laiką", callback_data="recur_time_custom")],
        [InlineKeyboardButton("🔄 Keli laikai", callback_data="recur_time_multiple")],
        [InlineKeyboardButton("🔙 Atgal", callback_data="recur_config")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


# ============================================================================
# REPETITION OPTIONS
# ============================================================================

async def show_repetition_screen(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show repetition options - EXACTLY like GroupHelpBot"""
    
    text = (
        "🔄 **Pasikartojimas**\n\n"
        "Pasirinkite, kaip dažnai siųsti pasikartojantį skelbimą:"
    )
    
    keyboard = [
        [InlineKeyboardButton("⏰ Kas 10 minučių", callback_data="recur_rep_10m")],
        [InlineKeyboardButton("⏰ Kas 15 minučių", callback_data="recur_rep_15m")],
        [InlineKeyboardButton("⏰ Kas 30 minučių", callback_data="recur_rep_30m")],
        [InlineKeyboardButton("⏰ Kas 1 valandą", callback_data="recur_rep_1h")],
        [InlineKeyboardButton("⏰ Kas 2 valandas", callback_data="recur_rep_2h")],
        [InlineKeyboardButton("⏰ Kas 3 valandas", callback_data="recur_rep_3h")],
        [InlineKeyboardButton("⏰ Kas 6 valandas", callback_data="recur_rep_6h")],
        [InlineKeyboardButton("⏰ Kas 12 valandų", callback_data="recur_rep_12h")],
        [InlineKeyboardButton("⏰ Kas 24 valandas", callback_data="recur_rep_24h")],
        [InlineKeyboardButton("📅 Savaitės dienos", callback_data="recur_days_week")],
        [InlineKeyboardButton("📅 Mėnesio dienos", callback_data="recur_days_month")],
        [InlineKeyboardButton("⏱️ Pasirinkti intervalą", callback_data="recur_rep_custom")],
        [InlineKeyboardButton("💬 Kas keletą pranešimų", callback_data="recur_rep_messages")],
        [InlineKeyboardButton("🔙 Atgal", callback_data="recur_config")]
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
                "⏰ **Pasirinkti laiką**\n\n"
                "Atsiųskite laiką HH:MM formatu (24 valandų)\n"
                "Pavyzdys: 14:30\n\n"
                "Arba /cancel grįžti atgal",
                parse_mode='Markdown'
            )
    
    # Handle repetition selection
    elif data.startswith("recur_rep_"):
        rep_type = data.replace("recur_rep_", "")
        if rep_type.endswith("m"):
            # Minute intervals (10m, 15m, 30m)
            minutes = int(rep_type[:-1])
            context.user_data['recur_msg_config']['repetition'] = f"{minutes} minutes"
            context.user_data['recur_msg_config']['repetition_type'] = 'interval'
            context.user_data['recur_msg_config']['interval_hours'] = minutes / 60  # Store as fractional hours
            await query.answer(f"✅ Nustatyta kas {minutes} min.")
            await show_message_config(query, context)
        elif rep_type.endswith("h"):
            hours = rep_type[:-1]
            context.user_data['recur_msg_config']['repetition'] = f"{hours} hours"
            context.user_data['recur_msg_config']['repetition_type'] = 'interval'
            context.user_data['recur_msg_config']['interval_hours'] = int(hours)
            await query.answer(f"✅ Nustatyta kas {hours} val.")
            await show_message_config(query, context)
        elif rep_type == "custom":
            # Custom interval - ask user to input hours or minutes
            context.user_data['awaiting_input'] = 'custom_interval'
            await query.edit_message_text(
                "⏱️ **Pasirinkti intervalą**\n\n"
                "Atsiųskite intervalą:\n"
                "• Valandomis: 4 (kas 4 valandas)\n"
                "• Minutėmis: 45m (kas 45 minutes)\n\n"
                "Arba /cancel grįžti atgal",
                parse_mode='Markdown'
            )
        elif rep_type == "messages":
            # Every few messages - not implemented yet
            await query.answer("❌ Ši funkcija dar neveikia")
            await show_repetition_screen(query, context)
    
    # Multiple times screen
    elif data == "recur_time_multiple":
        if 'multiple_times' not in context.user_data['recur_msg_config']:
            context.user_data['recur_msg_config']['multiple_times'] = []
        await show_multiple_times_screen(query, context)
    
    # Add time to multiple times
    elif data == "recur_add_time":
        context.user_data['awaiting_input'] = 'add_time'
        await query.edit_message_text(
            "⏰ **Pridėti laiką**\n\n"
            "Atsiųskite laiką HH:MM formatu (24 valandų)\n"
            "Pavyzdys: 14:30\n\n"
            "Arba /cancel grįžti atgal",
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
    
    # Edit message
    elif data.startswith("recur_edit_"):
        msg_id = int(data.replace("recur_edit_", ""))
        await edit_message(query, context, msg_id)
    
    # Close
    elif data == "recur_close":
        await query.edit_message_text("✅ Pasikartojančių skelbimų meniu uždarytas.")


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
    
    logger.info(f"📥 handle_text_input called: awaiting={awaiting}, has_photo={bool(update.message.photo if update.message else False)}, has_video={bool(update.message.video if update.message else False)}, has_animation={bool(update.message.animation if update.message else False)}")
    
    # Check for media files (photo, video, animation/GIF, document)
    if awaiting == 'message_media':
        if update.message.photo:
            # Get the largest photo
            photo = update.message.photo[-1]
            # Store file_id, not file_path - file_id is what we need to resend
            context.user_data['recur_msg_config']['media'] = photo.file_id
            context.user_data['recur_msg_config']['media_type'] = 'photo'
            context.user_data['recur_msg_config']['has_media'] = True
            context.user_data.pop('awaiting_input')
            
            await update.message.reply_text("✅ Nuotrauka išsaugota!")
            await show_customize_screen_after_input(update, context)
            return
            
        elif update.message.video:
            video = update.message.video
            # Store file_id
            context.user_data['recur_msg_config']['media'] = video.file_id
            context.user_data['recur_msg_config']['media_type'] = 'video'
            context.user_data['recur_msg_config']['has_media'] = True
            context.user_data.pop('awaiting_input')
            
            await update.message.reply_text("✅ Video išsaugotas!")
            await show_customize_screen_after_input(update, context)
            return
            
        elif update.message.animation:
            # GIF/Animation
            animation = update.message.animation
            # Store file_id
            context.user_data['recur_msg_config']['media'] = animation.file_id
            context.user_data['recur_msg_config']['media_type'] = 'animation'
            context.user_data['recur_msg_config']['has_media'] = True
            context.user_data.pop('awaiting_input')
            
            await update.message.reply_text("✅ GIF išsaugotas!")
            await show_customize_screen_after_input(update, context)
            return
            
        elif update.message.document:
            document = update.message.document
            # Store file_id
            context.user_data['recur_msg_config']['media'] = document.file_id
            context.user_data['recur_msg_config']['media_type'] = 'document'
            context.user_data['recur_msg_config']['has_media'] = True
            context.user_data.pop('awaiting_input')
            
            await update.message.reply_text("✅ Dokumentas išsaugotas!")
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
                    
                    # Send confirmation
                    await update.message.reply_text(f"✅ Laikas nustatytas: {text}")
                    
                    # Return to config screen by creating a fake query
                    from telegram import InlineKeyboardMarkup
                    
                    # Get chat_id for the config
                    if update.effective_chat.type == 'private' and context.user_data.get('selected_group_id'):
                        chat_id = context.user_data['selected_group_id']
                    else:
                        chat_id = update.effective_chat.id
                    
                    # Show config screen directly
                    msg_config = context.user_data.get('recur_msg_config', {})
                    status = msg_config.get('status', 'Off')
                    status_icon = "🟢" if status == "On" else "❌"
                    pin_icon = "✅" if msg_config.get('pin_message') else "❌"
                    delete_icon = "✅" if msg_config.get('delete_last') else "❌"
                    
                    try:
                        chat = await context.bot.get_chat(chat_id)
                        group_name = chat.title or "Group"
                    except:
                        group_name = "Group"
                    
                    import pytz
                    from datetime import datetime
                    lithuanian_tz = pytz.timezone('Europe/Vilnius')
                    current_time = datetime.now(lithuanian_tz).strftime("%d/%m/%y %H:%M")
                    
                    config_text = (
                        "🔄 **Pasikartojantys skelbimai**\n\n"
                        f"Iš šio meniu galite nustatyti pranešimus, kurie bus siunčiami pakartotinai į grupę kas kelias minutes/valandas.\n\n"
                        f"**Dabartinis laikas:** {current_time}\n\n"
                        f"💬 **{group_name}** • {status_icon} **{status}**\n"
                        f"⏰ Laikas: {msg_config['time']}\n"
                        f"🔄 Kas {msg_config.get('repetition', '24 hours')}\n"
                        f"📝 Pranešimas {'ne' if not msg_config.get('has_text') else ''}nustatytas.\n\n"
                        f"📌 Prisegti pranešimą: {pin_icon}\n"
                        f"🗑️ Ištrinti paskutinį pranešimą: {delete_icon}"
                    )
                    
                    keyboard = [
                        [InlineKeyboardButton("✏️ Pritaikyti pranešimą", callback_data="recur_customize")],
                        [
                            InlineKeyboardButton("⏰ Laikas", callback_data="recur_time"),
                            InlineKeyboardButton("🔄 Pasikartojimas", callback_data="recur_repetition")
                        ],
                        [InlineKeyboardButton("📅 Savaitės dienos", callback_data="recur_days_week")],
                        [InlineKeyboardButton("📅 Mėnesio dienos", callback_data="recur_days_month")],
                        [InlineKeyboardButton("🕐 Nustatyti laiko tarpą", callback_data="recur_time_slot")],
                        [
                            InlineKeyboardButton("📅 Pradžios data", callback_data="recur_start_date"),
                            InlineKeyboardButton("📅 Pabaigos data", callback_data="recur_end_date")
                        ],
                        [InlineKeyboardButton(f"📌 Prisegti pranešimą {pin_icon}", callback_data="recur_toggle_pin")],
                        [InlineKeyboardButton(f"🗑️ Ištrinti paskutinį {delete_icon}", callback_data="recur_toggle_delete")],
                        [InlineKeyboardButton("⏱️ Suplanuotas ištrynimas", callback_data="recur_sched_deletion")],
                        [InlineKeyboardButton("👁️ Peržiūra", callback_data="recur_preview")],
                        [InlineKeyboardButton("💾 Išsaugoti", callback_data="recur_save")],
                        [InlineKeyboardButton("🔙 Atgal", callback_data="recur_main")]
                    ]
                    
                    reply_markup = InlineKeyboardMarkup(keyboard)
                    await update.message.reply_text(config_text, reply_markup=reply_markup, parse_mode='Markdown')
                else:
                    await update.message.reply_text("❌ Neteisingas laikas. Naudokite HH:MM formatą (00:00 - 23:59)")
            else:
                await update.message.reply_text("❌ Neteisingas formatas. Naudokite HH:MM formatą")
        except ValueError:
            await update.message.reply_text("❌ Neteisingas laiko formatas. Naudokite HH:MM (pvz., 14:30)")
    
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
                        await update.message.reply_text(f"✅ Pridėtas laikas: {text}")
                        
                        # Return to multiple times screen
                        from telegram import InlineKeyboardMarkup
                        
                        selected_times = context.user_data['recur_msg_config'].get('multiple_times', [])
                        
                        times_text = (
                            "🔄 **Keli laikai per dieną**\n\n"
                            f"Pasirinkti laikai: {', '.join(selected_times) if selected_times else 'Nėra'}\n\n"
                            "Pridėkite daugiau laikų arba patvirtinkite."
                        )
                        
                        keyboard = [[InlineKeyboardButton("➕ Pridėti laiką", callback_data="recur_add_time")]]
                        
                        for i, time in enumerate(selected_times):
                            keyboard.append([
                                InlineKeyboardButton(f"🗑️ Pašalinti {time}", callback_data=f"recur_remove_time_{i}")
                            ])
                        
                        keyboard.append([InlineKeyboardButton("✅ Patvirtinti", callback_data="recur_times_confirm")])
                        keyboard.append([InlineKeyboardButton("🔙 Atgal", callback_data="recur_config")])
                        
                        reply_markup = InlineKeyboardMarkup(keyboard)
                        await update.message.reply_text(times_text, reply_markup=reply_markup, parse_mode='Markdown')
                    else:
                        await update.message.reply_text("❌ Šis laikas jau pridėtas!")
                else:
                    await update.message.reply_text("❌ Neteisingas laikas. Naudokite HH:MM formatą (00:00 - 23:59)")
            else:
                await update.message.reply_text("❌ Neteisingas formatas. Naudokite HH:MM formatą")
        except ValueError:
            await update.message.reply_text("❌ Neteisingas laiko formatas. Naudokite HH:MM (pvz., 14:30)")
    
    elif awaiting == 'custom_interval':
        try:
            # Check if input ends with 'm' for minutes
            if text.endswith('m'):
                # Minutes format (e.g., "45m")
                minutes = int(text[:-1])
                if minutes > 0 and minutes <= 10080:  # Max 1 week (10080 minutes)
                    context.user_data['recur_msg_config']['repetition'] = f"{minutes} minutes"
                    context.user_data['recur_msg_config']['repetition_type'] = 'interval'
                    context.user_data['recur_msg_config']['interval_hours'] = minutes / 60
                    context.user_data.pop('awaiting_input')
                    
                    # Send confirmation
                    await update.message.reply_text(f"✅ Intervalas nustatytas: kas {minutes} min.")
                else:
                    await update.message.reply_text("❌ Neteisingas intervalas. Įveskite skaičių nuo 1 iki 10080 (minutės)")
                    return
            else:
                # Hours format (e.g., "4")
                hours = int(text)
                if hours > 0 and hours <= 168:  # Max 1 week (168 hours)
                    context.user_data['recur_msg_config']['repetition'] = f"{hours} hours"
                    context.user_data['recur_msg_config']['repetition_type'] = 'interval'
                    context.user_data['recur_msg_config']['interval_hours'] = hours
                    context.user_data.pop('awaiting_input')
                    
                    # Send confirmation
                    await update.message.reply_text(f"✅ Intervalas nustatytas: kas {hours} val.")
                else:
                    await update.message.reply_text("❌ Neteisingas intervalas. Įveskite skaičių nuo 1 iki 168 (valandos)")
                    return
            
            # Return to config screen
            from telegram import InlineKeyboardMarkup
            import pytz
            from datetime import datetime
            
            # Get chat_id for the config
            if update.effective_chat.type == 'private' and context.user_data.get('selected_group_id'):
                chat_id = context.user_data['selected_group_id']
            else:
                chat_id = update.effective_chat.id
            
            # Show config screen directly
            msg_config = context.user_data.get('recur_msg_config', {})
            status = msg_config.get('status', 'Off')
            status_icon = "🟢" if status == "On" else "❌"
            pin_icon = "✅" if msg_config.get('pin_message') else "❌"
            delete_icon = "✅" if msg_config.get('delete_last') else "❌"
            
            try:
                chat = await context.bot.get_chat(chat_id)
                group_name = chat.title or "Group"
            except:
                group_name = "Group"
            
            lithuanian_tz = pytz.timezone('Europe/Vilnius')
            current_time = datetime.now(lithuanian_tz).strftime("%d/%m/%y %H:%M")
            
            config_text = (
                "🔄 **Pasikartojantys skelbimai**\n\n"
                f"Iš šio meniu galite nustatyti pranešimus, kurie bus siunčiami pakartotinai į grupę kas kelias minutes/valandas.\n\n"
                f"**Dabartinis laikas:** {current_time}\n\n"
                f"💬 **{group_name}** • {status_icon} **{status}**\n"
                f"⏰ Laikas: {msg_config['time']}\n"
                f"🔄 Kas {msg_config['repetition']}\n"
                f"📝 Pranešimas {'ne' if not msg_config.get('has_text') else ''}nustatytas.\n\n"
                f"📌 Prisegti pranešimą: {pin_icon}\n"
                f"🗑️ Ištrinti paskutinį pranešimą: {delete_icon}"
            )
            
            keyboard = [
                [InlineKeyboardButton("✏️ Pritaikyti pranešimą", callback_data="recur_customize")],
                [
                    InlineKeyboardButton("⏰ Laikas", callback_data="recur_time"),
                    InlineKeyboardButton("🔄 Pasikartojimas", callback_data="recur_repetition")
                ],
                [InlineKeyboardButton("📅 Savaitės dienos", callback_data="recur_days_week")],
                [InlineKeyboardButton("📅 Mėnesio dienos", callback_data="recur_days_month")],
                [InlineKeyboardButton("🕐 Nustatyti laiko tarpą", callback_data="recur_time_slot")],
                [
                    InlineKeyboardButton("📅 Pradžios data", callback_data="recur_start_date"),
                    InlineKeyboardButton("📅 Pabaigos data", callback_data="recur_end_date")
                ],
                [InlineKeyboardButton(f"📌 Prisegti pranešimą {pin_icon}", callback_data="recur_toggle_pin")],
                [InlineKeyboardButton(f"🗑️ Ištrinti paskutinį {delete_icon}", callback_data="recur_toggle_delete")],
                [InlineKeyboardButton("⏱️ Suplanuotas ištrynimas", callback_data="recur_sched_deletion")],
                [InlineKeyboardButton("👁️ Peržiūra", callback_data="recur_preview")],
                [InlineKeyboardButton("💾 Išsaugoti", callback_data="recur_save")],
                [InlineKeyboardButton("🔙 Atgal", callback_data="recur_main")]
            ]
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(config_text, reply_markup=reply_markup, parse_mode='Markdown')
        except ValueError:
            await update.message.reply_text("❌ Neteisingas formatas. Įveskite skaičių (pvz., 4 arba 45m)")
    
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
    # Get chat_id - use selected_group_id if in private chat
    if query.message.chat.type == 'private' and context.user_data.get('selected_group_id'):
        chat_id = context.user_data['selected_group_id']
    else:
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
            "📋 **Nėra pasikartojančių skelbimų**\n\nJūs dar nesukūrėte jokių pasikartojančių skelbimų.",
            parse_mode='Markdown'
        )
        return
    
    text = "📋 **Tvarkyti pasikartojančius skelbimus**\n\n"
    text += "Paspauskite ant skelbimo, kad jį tvarkytumėte:\n\n"
    
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
    
    keyboard.append([InlineKeyboardButton("🔙 Atgal", callback_data="recur_main")])
    
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
           pin_message, delete_last_message, interval_hours FROM scheduled_messages WHERE id = ?''',
        (message_id,)
    )
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        await query.answer("❌ Skelbimas nerastas")
        return
    
    msg_text, rep_type, status, is_active, last_sent, pin, delete_last, interval = result
    
    text = "⚙️ **Tvarkyti skelbimą**\n\n"
    text += f"**Tekstas:** {msg_text[:100]}...\n" if len(msg_text) > 100 else f"**Tekstas:** {msg_text}\n"
    text += f"**Tipas:** {rep_type}\n"
    text += f"**Statusas:** {'Aktyvus' if is_active else 'Pristabdytas'}\n"
    
    if rep_type == 'interval' and interval:
        if interval < 1:
            # It's in minutes
            minutes = int(interval * 60)
            text += f"**Kartojimas:** Kas {minutes} min.\n"
        else:
            # It's in hours
            text += f"**Kartojimas:** Kas {int(interval)} val.\n"
    
    text += f"**Prisegti:** {'Taip' if pin else 'Ne'}\n"
    text += f"**Ištrinti paskutinį:** {'Taip' if delete_last else 'Ne'}\n"
    
    if last_sent:
        text += f"**Paskutinį kartą išsiųsta:** {last_sent}\n"
    
    keyboard = []
    
    # Edit button
    keyboard.append([InlineKeyboardButton("✏️ Redaguoti", callback_data=f"recur_edit_{message_id}")])
    
    # Pause/Resume button
    if is_active:
        keyboard.append([InlineKeyboardButton("⏸️ Pristabdyti", callback_data=f"recur_pause_{message_id}")])
    else:
        keyboard.append([InlineKeyboardButton("▶️ Tęsti", callback_data=f"recur_resume_{message_id}")])
    
    # Delete button
    keyboard.append([InlineKeyboardButton("🗑️ Ištrinti", callback_data=f"recur_delete_{message_id}")])
    keyboard.append([InlineKeyboardButton("🔙 Atgal", callback_data="recur_manage_list")])
    
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
        
        await query.answer("⏸️ Skelbimas pristabdytas")
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
                # Check if interval is less than 1 hour (fractional hours = minutes)
                if interval < 1:
                    # It's in minutes
                    minutes = int(interval * 60)
                    trigger = IntervalTrigger(minutes=minutes)
                else:
                    # It's in hours
                    trigger = IntervalTrigger(hours=int(interval))
                
                job_id = f"recur_{query.message.chat_id}_{message_id}"
                
                init_scheduler()
                scheduler.add_job(
                    send_recurring_message_sync,
                    trigger=trigger,
                    args=[query.message.chat_id, message_id],
                    id=job_id,
                    replace_existing=True
                )
                
                # Update status
                conn.execute('UPDATE scheduled_messages SET is_active = 1 WHERE id = ?', (message_id,))
                conn.commit()
                
                logger.info(f"Resumed job {job_id}")
        
        conn.close()
        
        await query.answer("▶️ Skelbimas tęsiamas")
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
        
        await query.answer("🗑️ Skelbimas ištrintas")
        await show_manage_list(query, context)
        
    except Exception as e:
        logger.error(f"Error deleting message: {e}")
        await query.answer(f"❌ Error: {str(e)}")


async def edit_message(query, context: ContextTypes.DEFAULT_TYPE, message_id: int):
    """Edit an existing recurring message"""
    try:
        # Load message config from database
        conn = database.get_sync_connection()
        cursor = conn.execute(
            '''SELECT message_text, message_media, message_buttons, message_type, 
               repetition_type, interval_hours, days_of_week, days_of_month, 
               time_slots, pin_message, delete_last_message, chat_id 
               FROM scheduled_messages WHERE id = ?''',
            (message_id,)
        )
        result = cursor.fetchone()
        conn.close()
        
        if not result:
            await query.answer("❌ Skelbimas nerastas")
            return
        
        # Unpack result
        msg_text, msg_media, msg_buttons, msg_type, rep_type, interval, \
        days_week, days_month, time_slots, pin, delete_last, chat_id = result
        
        # Load into user context for editing
        import json
        
        # Determine repetition display text
        if rep_type == 'interval':
            if interval < 1:
                # It's in minutes
                minutes = int(interval * 60)
                repetition_text = f'{minutes} minutes'
            else:
                # It's in hours
                repetition_text = f'{int(interval)} hours'
        else:
            repetition_text = '24 hours'
        
        msg_config = {
            'editing_message_id': message_id,  # Mark as editing mode
            'status': 'On',
            'time': '20:28',  # Default, will be updated
            'repetition': repetition_text,
            'repetition_type': rep_type,
            'interval_hours': interval,
            'pin_message': bool(pin),
            'delete_last': bool(delete_last),
            'has_text': bool(msg_text),
            'has_media': bool(msg_media),
            'has_buttons': bool(msg_buttons),
            'text': msg_text or '',
            'media': msg_media or '',
            'buttons': json.loads(msg_buttons) if msg_buttons else [],
            'days_of_week': json.loads(days_week) if days_week else [],
            'days_of_month': json.loads(days_month) if days_month else [],
            'start_date': None,
            'end_date': None,
            'scheduled_deletion': None
        }
        
        context.user_data['recur_msg_config'] = msg_config
        context.user_data['selected_group_id'] = chat_id  # Set the group context
        
        # Show config screen for editing
        await query.answer("✏️ Redagavimo režimas")
        
        # Build config screen
        import pytz
        from datetime import datetime
        lithuanian_tz = pytz.timezone('Europe/Vilnius')
        current_time = datetime.now(lithuanian_tz).strftime("%d/%m/%y %H:%M")
        
        try:
            chat = await context.bot.get_chat(chat_id)
            group_name = chat.title or "Group"
        except:
            group_name = "Group"
        
        status_icon = "🟢"
        pin_icon = "✅" if pin else "❌"
        delete_icon = "✅" if delete_last else "❌"
        
        config_text = (
            "🔄 **Pasikartojantys skelbimai** (Redagavimas)\n\n"
            f"Iš šio meniu galite nustatyti pranešimus, kurie bus siunčiami pakartotinai į grupę kas kelias minutes/valandas.\n\n"
            f"**Dabartinis laikas:** {current_time}\n\n"
            f"💬 **{group_name}** • {status_icon} **On**\n"
            f"⏰ Laikas: {msg_config['time']}\n"
            f"🔄 Kas {msg_config['repetition']}\n"
            f"📝 Pranešimas {'ne' if not msg_config['has_text'] else ''}nustatytas.\n\n"
            f"📌 Prisegti pranešimą: {pin_icon}\n"
            f"🗑️ Ištrinti paskutinį pranešimą: {delete_icon}"
        )
        
        keyboard = [
            [InlineKeyboardButton("✏️ Pritaikyti pranešimą", callback_data="recur_customize")],
            [
                InlineKeyboardButton("⏰ Laikas", callback_data="recur_time"),
                InlineKeyboardButton("🔄 Pasikartojimas", callback_data="recur_repetition")
            ],
            [InlineKeyboardButton("📅 Savaitės dienos", callback_data="recur_days_week")],
            [InlineKeyboardButton("📅 Mėnesio dienos", callback_data="recur_days_month")],
            [InlineKeyboardButton("🕐 Nustatyti laiko tarpą", callback_data="recur_time_slot")],
            [
                InlineKeyboardButton("📅 Pradžios data", callback_data="recur_start_date"),
                InlineKeyboardButton("📅 Pabaigos data", callback_data="recur_end_date")
            ],
            [InlineKeyboardButton(f"📌 Prisegti pranešimą {pin_icon}", callback_data="recur_toggle_pin")],
            [InlineKeyboardButton(f"🗑️ Ištrinti paskutinį {delete_icon}", callback_data="recur_toggle_delete")],
            [InlineKeyboardButton("⏱️ Suplanuotas ištrynimas", callback_data="recur_sched_deletion")],
            [InlineKeyboardButton("👁️ Peržiūra", callback_data="recur_preview")],
            [InlineKeyboardButton("💾 Išsaugoti", callback_data="recur_save")],
            [InlineKeyboardButton("🔙 Atgal", callback_data=f"recur_manage_{message_id}")]
        ]
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(config_text, reply_markup=reply_markup, parse_mode='Markdown')
        
    except Exception as e:
        logger.error(f"Error editing message: {e}")
        await query.answer(f"❌ Klaida: {str(e)}")


# ============================================================================
# CORE FUNCTIONALITY - SEND RECURRING MESSAGE
# ============================================================================

def send_recurring_message_sync(chat_id: int, message_id: int):
    """
    Synchronous wrapper for send_recurring_message that APScheduler can call
    Creates an event loop to run the async function
    """
    import asyncio
    
    logger.info(f"🔔 SCHEDULER TRIGGERED: Starting send_recurring_message_sync for message_id={message_id}")
    
    try:
        # Get or create event loop
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        # Run the async function
        loop.run_until_complete(_send_recurring_message_async(chat_id, message_id))
        logger.info(f"✅ SCHEDULER COMPLETED: message_id={message_id}")
        
    except Exception as e:
        logger.error(f"❌ SCHEDULER ERROR: Failed to send recurring message {message_id}: {e}", exc_info=True)


async def _send_recurring_message_async(chat_id: int, message_id: int):
    """
    BROADCAST recurring message to ALL groups (except voting group)
    Simple version - supports text, media, buttons (NO pin/delete for broadcasts)
    Uses global bot instance stored via set_bot_instance()
    """
    global _bot_instance
    
    if _bot_instance is None:
        logger.error(f"❌ CRITICAL: Bot instance not set! Cannot send recurring message {message_id}")
        return
    
    bot = _bot_instance
    conn = None
    try:
        logger.info(f"📤 send_recurring_message called: message_id={message_id} (BROADCAST MODE)")
        
        # Get message config from database
        conn = database.get_sync_connection()
        cursor = conn.execute(
            '''SELECT message_text, message_media, message_buttons, message_type FROM scheduled_messages WHERE id = ?''',
            (message_id,)
        )
        result = cursor.fetchone()
        
        if not result:
            logger.warning(f"❌ Recurring message {message_id} not found in database")
            conn.close()
            return
        
        text, media, buttons_json, msg_type = result
        logger.info(f"📋 Retrieved message config: text_len={len(text) if text else 0}, has_media={bool(media)}, type={msg_type}")
        
        # Get all groups EXCEPT voting group
        cursor = conn.execute('SELECT chat_id, title FROM groups')
        all_groups = cursor.fetchall()
        
        # Filter out voting group
        target_groups = [g for g in all_groups if g[0] != VOTING_GROUP_CHAT_ID]
        
        if not target_groups:
            logger.warning(f"❌ No target groups found for broadcast!")
            conn.close()
            return
        
        logger.info(f"📢 Broadcasting message {message_id} to {len(target_groups)} groups (excluding voting group)")
        
        # Parse buttons (once, for all groups)
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
        
        # Broadcast to each group
        success_count = 0
        failed_groups = []
        
        for group in target_groups:
            target_chat_id = group[0]
            group_title = group[1] or f"Group {target_chat_id}"
            
            try:
                logger.debug(f"  📤 Sending to {group_title} ({target_chat_id})")
                sent_message = None
                
                # Send media or text
                if media:
                    # Try sending as photo first (most common)
                    try:
                        sent_message = await bot.send_photo(
                            chat_id=target_chat_id,
                            photo=media,
                            caption=text if text else None,
                            parse_mode='Markdown',
                            reply_markup=reply_markup
                        )
                    except Exception:
                        # Try as video
                        try:
                            sent_message = await bot.send_video(
                                chat_id=target_chat_id,
                                video=media,
                                caption=text if text else None,
                                parse_mode='Markdown',
                                reply_markup=reply_markup
                            )
                        except Exception:
                            # Try as animation/GIF
                            try:
                                sent_message = await bot.send_animation(
                                    chat_id=target_chat_id,
                                    animation=media,
                                    caption=text if text else None,
                                    parse_mode='Markdown',
                                    reply_markup=reply_markup
                                )
                            except Exception:
                                # Last resort: document
                                try:
                                    sent_message = await bot.send_document(
                                        chat_id=target_chat_id,
                                        document=media,
                                        caption=text if text else None,
                                        parse_mode='Markdown',
                                        reply_markup=reply_markup
                                    )
                                except Exception:
                                    # Media failed completely, send text only
                                    if text:
                                        sent_message = await bot.send_message(
                                            chat_id=target_chat_id,
                                            text=text,
                                            parse_mode='Markdown',
                                            reply_markup=reply_markup
                                        )
                elif text:
                    # Text-only message
                    sent_message = await bot.send_message(
                        chat_id=target_chat_id,
                        text=text,
                        parse_mode='Markdown',
                        reply_markup=reply_markup
                    )
                
                if sent_message:
                    success_count += 1
                    logger.debug(f"  ✅ Sent to {group_title}")
                else:
                    failed_groups.append(group_title)
                    logger.warning(f"  ❌ Failed to send to {group_title}: No message sent")
                    
            except Exception as e:
                failed_groups.append(group_title)
                logger.warning(f"  ❌ Failed to send to {group_title}: {e}")
                continue
        
        # Update last_sent timestamp
        conn.execute(
            '''UPDATE scheduled_messages SET last_sent = CURRENT_TIMESTAMP WHERE id = ?''',
            (message_id,)
        )
        conn.commit()
        
        # Log summary
        logger.info(f"✅ Broadcast complete: {success_count}/{len(target_groups)} groups successful")
        if failed_groups:
            logger.warning(f"❌ Failed groups: {', '.join(failed_groups)}")
        
        conn.close()
        
    except Exception as e:
        logger.error(f"❌ Error in broadcast: {e}")
        logger.exception(e)
        if conn:
            conn.close()




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
        
        # Check if we're editing an existing message
        editing_message_id = msg_config.get('editing_message_id')
        
        # Validate configuration
        if not msg_config.get('has_text'):
            await query.answer("❌ Pirmiausia nustatykite pranešimo tekstą!")
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
                timezone=pytz.UTC
            )
            rep_text = f"Days: {', '.join(msg_config['days_of_week'])}"
            
        elif repetition_type == 'days_of_month' and msg_config.get('days_of_month'):
            # Cron trigger for specific days of month
            days = ','.join([str(d) for d in sorted(msg_config['days_of_month'])])
            trigger = CronTrigger(
                day=days,
                hour=hour,
                minute=minute,
                timezone=pytz.UTC
            )
            rep_text = f"Dates: {days} of each month"
            
        elif repetition_type == 'multiple_times' and msg_config.get('multiple_times'):
            # Multiple cron triggers - one for each time
            # We'll handle this differently below by creating multiple jobs
            trigger = None  # Will create multiple triggers
            times = msg_config['multiple_times']
            rep_text = f"{len(times)} times per day: {', '.join(times)}"
            
        else:
            # Interval trigger (hours or minutes)
            rep_str = msg_config.get('repetition', '24 hours')
            interval_hours = msg_config.get('interval_hours', 24)
            
            # Use interval_hours from config (more reliable than parsing string)
            if interval_hours < 1:
                # It's in minutes (fractional hours)
                minutes = int(interval_hours * 60)
                logger.info(f"⏱️ Creating MINUTE interval trigger: {minutes} minutes (interval_hours={interval_hours})")
                trigger = IntervalTrigger(minutes=minutes)
                rep_text = f"{minutes} minutes"
            else:
                # It's in hours
                hours = int(interval_hours)
                logger.info(f"⏱️ Creating HOUR interval trigger: {hours} hours")
                trigger = IntervalTrigger(hours=hours)
                rep_text = f"{hours} hours"
        
        # Save to database
        import json
        
        # Prepare buttons JSON
        buttons_json = None
        if msg_config.get('buttons'):
            buttons_json = json.dumps(msg_config['buttons'])
        
        conn = database.get_sync_connection()
        
        if editing_message_id:
            # UPDATE existing message
            # First, remove old job(s)
            cursor = conn.execute('SELECT job_id FROM scheduled_messages WHERE id = ?', (editing_message_id,))
            result = cursor.fetchone()
            if result and result[0]:
                job_id_str = result[0]
                job_ids = job_id_str.split(',')
                for job_id in job_ids:
                    try:
                        if scheduler:
                            scheduler.remove_job(job_id.strip())
                            logger.info(f"Removed old job {job_id}")
                    except Exception as e:
                        logger.warning(f"Could not remove old job {job_id}: {e}")
            
            # Update the message
            cursor = conn.execute('''
                UPDATE scheduled_messages SET
                    message_text = ?, message_media = ?, message_buttons = ?, 
                    repetition_type = ?, interval_hours = ?, 
                    pin_message = ?, delete_last_message = ?, 
                    is_active = 1
                WHERE id = ?
            ''', (
                msg_config.get('text', ''),
                msg_config.get('media', ''),
                buttons_json,
                repetition_type,
                msg_config.get('interval_hours', 24),
                msg_config.get('pin_message', False),
                msg_config.get('delete_last', False),
                editing_message_id
            ))
            message_id = editing_message_id
        else:
            # INSERT new message
            cursor = conn.execute('''
                INSERT INTO scheduled_messages (
                    chat_id, message_text, message_media, message_buttons, message_type, 
                    repetition_type, interval_hours, pin_message, delete_last_message, 
                    status, is_active, created_by, created_by_username
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                chat_id,
                msg_config.get('text', ''),
                msg_config.get('media', ''),
                buttons_json,
                'text',
                repetition_type,
                msg_config.get('interval_hours', 24),
                msg_config.get('pin_message', False),
                msg_config.get('delete_last', False),
                'active',
                1,  # is_active = 1
                user.id,
                user.username or user.first_name
            ))
            message_id = cursor.lastrowid
            logger.info(f"✅ Saved recurring message to database: message_id={message_id}, status=active, is_active=1")
        
        conn.commit()
        
        # Verify the message was saved with is_active = 1
        cursor = conn.execute(
            'SELECT status, is_active FROM scheduled_messages WHERE id = ?',
            (message_id,)
        )
        verify_result = cursor.fetchone()
        if verify_result:
            status, is_active = verify_result
            logger.info(f"🔍 Verified database save: status={status}, is_active={is_active}")
            if status != 'active' or is_active != 1:
                logger.error(f"❌ CRITICAL: Message saved with wrong status! status={status}, is_active={is_active}")
        else:
            logger.error(f"❌ CRITICAL: Could not find saved message {message_id} in database!")
        
        # Create APScheduler job(s)
        set_bot_instance(context.bot)  # Store bot instance for jobs
        init_scheduler()  # Ensure scheduler is initialized
        
        if repetition_type == 'multiple_times' and msg_config.get('multiple_times'):
            # Create multiple jobs - one for each time
            job_ids = []
            for i, time_str in enumerate(msg_config['multiple_times']):
                hour, minute = map(int, time_str.split(':'))
                trigger = CronTrigger(
                    hour=hour,
                    minute=minute,
                    timezone=pytz.UTC
                )
                
                job_id = f"recur_{chat_id}_{message_id}_{i}"
                job_ids.append(job_id)
                
                scheduler.add_job(
                    send_recurring_message_sync,
                    trigger=trigger,
                    args=[chat_id, message_id],
                    id=job_id,
                    replace_existing=True
                )
            
            # Store all job IDs as comma-separated
            job_id_str = ','.join(job_ids)
            conn.execute(
                'UPDATE scheduled_messages SET job_id = ? WHERE id = ?',
                (job_id_str, message_id)
            )
            logger.info(f"Created {len(job_ids)} recurring message jobs for chat {chat_id}")
        else:
            # Single job
            job_id = f"recur_{chat_id}_{message_id}"
            
            logger.info(f"🔧 Creating scheduler job: job_id={job_id}, trigger={trigger}, chat_id={chat_id}")
            scheduler.add_job(
                send_recurring_message_sync,
                trigger=trigger,
                args=[chat_id, message_id],
                id=job_id,
                replace_existing=True,
                misfire_grace_time=3600  # 1 hour grace time for misfires
            )
            
            # Verify the job was created
            created_job = scheduler.get_job(job_id)
            if created_job:
                next_run = created_job.next_run_time
                logger.info(f"✅ Job {job_id} created successfully, next run: {next_run}")
            else:
                logger.error(f"❌ CRITICAL: Job {job_id} was not added to scheduler!")
            
            # Update job_id in database
            conn.execute(
                'UPDATE scheduled_messages SET job_id = ? WHERE id = ?',
                (job_id, message_id)
            )
            
            # Final verification - list all jobs
            all_jobs = scheduler.get_jobs()
            logger.info(f"📊 Scheduler now has {len(all_jobs)} total jobs after save")
        
        conn.commit()
        conn.close()
        
        # Send the message immediately (first time)
        try:
            logger.info(f"🚀 Attempting to send initial recurring message: chat_id={chat_id}, message_id={message_id}")
            await _send_recurring_message_async(chat_id, message_id)
            logger.info(f"✅ Successfully sent initial recurring message for chat {chat_id}, message_id {message_id}")
        except Exception as e:
            logger.error(f"❌ Error sending initial recurring message: {e}", exc_info=True)
            # Don't fail the save if initial send fails
        
        # Clear user config
        context.user_data.pop('recur_msg_config', None)
        
        # Show success
        action_text = "atnaujintas ir išsiųstas" if editing_message_id else "išsaugotas ir išsiųstas"
        await query.edit_message_text(
            f"✅ **Pasikartojantis skelbimas {action_text}!**\n\n"
            f"📝 Pranešimas: {msg_config.get('text', '')[:50]}...\n"
            f"🕐 Laikas: {time_str}\n"
            f"🔄 Kartojimas: {rep_text}\n"
            f"📌 Prisegti: {'Taip' if msg_config.get('pin_message') else 'Ne'}\n"
            f"🗑️ Ištrinti paskutinį: {'Taip' if msg_config.get('delete_last') else 'Ne'}\n\n"
            f"✅ Pirmas pranešimas išsiųstas!\n"
            f"🔄 Pranešimas kartosis automatiškai kas {rep_text}",
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
        logger.info("🔄 Starting to load scheduled jobs from database...")
        
        # Store bot instance globally for scheduler jobs
        set_bot_instance(bot)
        
        init_scheduler()
        
        # Verify scheduler is running
        if scheduler is None:
            logger.error("❌ CRITICAL: Scheduler is None after init_scheduler()!")
            return
        
        if not scheduler.running:
            logger.warning("⚠️ Scheduler not running, starting it now...")
            scheduler.start()
        
        logger.info(f"✅ Scheduler state: running={scheduler.running}, state={scheduler.state}")
        
        conn = database.get_sync_connection()
        cursor = conn.execute('''
            SELECT id, chat_id, message_text, repetition_type, interval_hours, job_id
            FROM scheduled_messages 
            WHERE status = 'active' AND is_active = 1
        ''')
        
        messages = cursor.fetchall()
        logger.info(f"📊 Found {len(messages)} active recurring messages in database")
        
        loaded_count = 0
        
        for msg in messages:
            msg_id, chat_id, text, rep_type, interval, old_job_id = msg
            
            try:
                logger.info(f"📥 Loading message {msg_id}: chat={chat_id}, type={rep_type}, interval={interval}")
                
                # Create new job
                trigger = None
                if rep_type == 'interval':
                    if interval < 1:
                        # It's in minutes (fractional hours)
                        minutes = int(interval * 60)
                        trigger = IntervalTrigger(minutes=minutes)
                        logger.info(f"  ⏱️ Created {minutes}-minute interval trigger")
                    else:
                        # It's in hours
                        trigger = IntervalTrigger(hours=int(interval))
                        logger.info(f"  ⏱️ Created {int(interval)}-hour interval trigger")
                else:
                    logger.warning(f"  ⚠️ Unsupported repetition type: {rep_type}, skipping")
                    continue
                
                if trigger is None:
                    logger.error(f"  ❌ Failed to create trigger for message {msg_id}")
                    continue
                
                job_id = f"recur_{chat_id}_{msg_id}"
                
                scheduler.add_job(
                    send_recurring_message_sync,
                    trigger=trigger,
                    args=[chat_id, msg_id],
                    id=job_id,
                    replace_existing=True,
                    misfire_grace_time=3600  # 1 hour grace time for misfires
                )
                
                # Verify the job was added
                job = scheduler.get_job(job_id)
                if job:
                    loaded_count += 1
                    next_run = job.next_run_time
                    logger.info(f"  ✅ Job {job_id} loaded successfully, next run: {next_run}")
                else:
                    logger.error(f"  ❌ Job {job_id} was not added to scheduler!")
                
            except Exception as e:
                logger.error(f"  ❌ Error loading job for message {msg_id}: {e}", exc_info=True)
        
        conn.close()
        
        # Final verification
        all_jobs = scheduler.get_jobs()
        logger.info(f"✅ Loaded {loaded_count} recurring message jobs from database")
        logger.info(f"📊 Scheduler now has {len(all_jobs)} total jobs")
        
        if all_jobs:
            logger.info("📋 Current jobs:")
            for job in all_jobs:
                logger.info(f"  - {job.id}: next_run={job.next_run_time}, trigger={job.trigger}")
        else:
            logger.warning("⚠️ No jobs in scheduler after loading!")
        
    except Exception as e:
        logger.error(f"❌ Error loading scheduled jobs: {e}", exc_info=True)


# Export functions
# ============================================================================
# BARYGOS AUTO-POST FUNCTIONALITY
# ============================================================================

_barygos_job_id = None

async def send_barygos_to_groups():
    """Send barygos leaderboard to configured groups"""
    import json
    from database import database
    import voting
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    # Get settings
    settings = database.get_barygos_auto_settings()
    if not settings or not settings.get('enabled'):
        logger.info("Barygos auto-post disabled, skipping")
        return
    
    # Parse target groups
    try:
        target_groups = json.loads(settings.get('target_groups', '[]'))
    except:
        logger.error("Failed to parse target_groups JSON")
        return
    
    if not target_groups:
        logger.warning("No target groups configured for barygos auto-post")
        return
    
    # Generate leaderboard text
    full_message = voting.generate_barygos_text()
    
    # Create button linking to voting group (if configured)
    reply_markup = None
    voting_link = settings.get('voting_group_link', '')
    if voting_link:
        keyboard = [[InlineKeyboardButton("🗳️ Balsuoti už pardavėją", url=voting_link)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Send to each group
    successful = 0
    for chat_id in target_groups:
        try:
            # Send with media if available
            if voting.barygos_media_id and voting.barygos_media_type:
                if len(full_message) > 1000:
                    # Send media and text separately if too long
                    if voting.barygos_media_type == 'photo':
                        await _bot_instance.send_photo(chat_id=chat_id, photo=voting.barygos_media_id)
                    elif voting.barygos_media_type == 'animation':
                        await _bot_instance.send_animation(chat_id=chat_id, animation=voting.barygos_media_id)
                    elif voting.barygos_media_type == 'video':
                        await _bot_instance.send_video(chat_id=chat_id, video=voting.barygos_media_id)
                    
                    await _bot_instance.send_message(chat_id=chat_id, text=full_message, reply_markup=reply_markup)
                else:
                    # Send with caption and button
                    if voting.barygos_media_type == 'photo':
                        await _bot_instance.send_photo(chat_id=chat_id, photo=voting.barygos_media_id, caption=full_message, reply_markup=reply_markup)
                    elif voting.barygos_media_type == 'animation':
                        await _bot_instance.send_animation(chat_id=chat_id, animation=voting.barygos_media_id, caption=full_message, reply_markup=reply_markup)
                    elif voting.barygos_media_type == 'video':
                        await _bot_instance.send_video(chat_id=chat_id, video=voting.barygos_media_id, caption=full_message, reply_markup=reply_markup)
                    else:
                        await _bot_instance.send_message(chat_id=chat_id, text=full_message, reply_markup=reply_markup)
            else:
                await _bot_instance.send_message(chat_id=chat_id, text=full_message, reply_markup=reply_markup)
            
            successful += 1
            logger.info(f"✅ Sent barygos leaderboard to {chat_id}")
        except Exception as e:
            logger.error(f"Failed to send barygos to {chat_id}: {e}")
    
    logger.info(f"Barygos auto-post complete: {successful}/{len(target_groups)} groups")


def schedule_barygos_auto_job():
    """Schedule barygos auto-post job"""
    global _barygos_job_id
    from database import database
    import asyncio
    
    # Remove existing job if any
    stop_barygos_auto_job()
    
    # Get settings
    settings = database.get_barygos_auto_settings()
    if not settings or not settings.get('enabled'):
        logger.info("Barygos auto-post is disabled")
        return
    
    interval_hours = settings.get('interval_hours', 2)
    
    # Format display text
    if interval_hours < 1:
        display_text = f"{int(interval_hours * 60)} minutes"
        job_name = f'Barygos Auto-Post (every {int(interval_hours * 60)}min)'
    else:
        display_text = f"{int(interval_hours)} hours"
        job_name = f'Barygos Auto-Post (every {int(interval_hours)}h)'
    
    # Create wrapper function for sync scheduler
    def sync_wrapper():
        """Wrapper to run async function in sync context"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(send_barygos_to_groups())
            loop.close()
        except Exception as e:
            logger.error(f"Error in barygos auto-post job: {e}")
    
    # Schedule the job
    job = scheduler.add_job(
        sync_wrapper,
        trigger=IntervalTrigger(hours=interval_hours),
        id='barygos_auto_post',
        replace_existing=True,
        name=job_name
    )
    
    _barygos_job_id = job.id
    logger.info(f"✅ Scheduled barygos auto-post: every {display_text}")


def stop_barygos_auto_job():
    """Stop barygos auto-post job"""
    global _barygos_job_id
    
    if _barygos_job_id:
        try:
            scheduler.remove_job(_barygos_job_id)
            logger.info(f"Removed barygos auto-post job: {_barygos_job_id}")
        except Exception as e:
            logger.debug(f"Could not remove barygos job: {e}")
        _barygos_job_id = None


__all__ = [
    'init_scheduler',
    'set_bot_instance',
    'show_main_menu',
    'handle_callback',
    'handle_text_input',
    'send_recurring_message',
    'load_scheduled_jobs_from_db',
    'schedule_barygos_auto_job',
    'stop_barygos_auto_job'
]

