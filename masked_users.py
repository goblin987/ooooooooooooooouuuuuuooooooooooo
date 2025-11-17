#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Masked Users Management - GroupHelpBot Style
Manage anonymous/masked users in the group
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any, List
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import database
from moderation_grouphelp import is_admin
from utils import data_manager

logger = logging.getLogger(__name__)

# Load masked users data
masked_users = data_manager.load_data('masked_users.pkl', {})


# ============================================================================
# MAIN MENU
# ============================================================================

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show masked users main menu - GroupHelpBot style"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Only administrators can manage masked users!")
        return
    
    # Get chat info
    try:
        if update.callback_query:
            chat_id = update.callback_query.message.chat_id
            chat = await context.bot.get_chat(chat_id)
        else:
            chat_id = update.effective_chat.id
            chat = await context.bot.get_chat(chat_id)
        group_name = chat.title or "Group"
    except:
        group_name = "Group"
        chat_id = update.effective_chat.id
    
    # Get masked users for this group
    group_masked = masked_users.get(str(chat_id), {})
    
    text = (
        "👤 **Masked Users**\n\n"
        "This feature allows you to manage users who can send messages anonymously in the group. "
        "Masked users' identities will be hidden when they post.\n\n"
        f"**Group:** {group_name}\n"
        f"**Total Masked Users:** {len(group_masked)}\n\n"
    )
    
    if group_masked:
        text += "**Current Masked Users:**\n"
        for i, (user_id, user_data) in enumerate(list(group_masked.items())[:5], 1):
            username = user_data.get('username', f'User{user_id}')
            mask_name = user_data.get('mask_name', 'Anonymous')
            text += f"{i}. @{username} → {mask_name}\n"
        
        if len(group_masked) > 5:
            text += f"\n_...and {len(group_masked) - 5} more_\n"
    else:
        text += "_No masked users in this group._\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Masked User", callback_data="mask_add")],
        [InlineKeyboardButton("➖ Remove Masked User", callback_data="mask_remove")],
        [InlineKeyboardButton("📋 View All Masked Users", callback_data="mask_list")],
        [InlineKeyboardButton("✏️ Edit Mask Name", callback_data="mask_edit")],
        [InlineKeyboardButton("🔄 Toggle Masking", callback_data="mask_toggle")],
        [InlineKeyboardButton("🔙 Back", callback_data="mask_close")]
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
# VIEW ALL MASKED USERS
# ============================================================================

async def show_all_masked_users(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show complete list of masked users"""
    
    chat_id = str(query.message.chat_id)
    group_masked = masked_users.get(chat_id, {})
    
    text = (
        "📋 **All Masked Users**\n\n"
    )
    
    if group_masked:
        for i, (user_id, user_data) in enumerate(group_masked.items(), 1):
            username = user_data.get('username', f'User{user_id}')
            mask_name = user_data.get('mask_name', 'Anonymous')
            status = "🟢 Active" if user_data.get('active', True) else "❌ Inactive"
            added_date = user_data.get('added_date', 'Unknown')
            
            text += f"**{i}. @{username}**\n"
            text += f"   Mask: {mask_name}\n"
            text += f"   Status: {status}\n"
            text += f"   Added: {added_date}\n\n"
    else:
        text += "_No masked users in this group._\n"
    
    keyboard = [
        [InlineKeyboardButton("🔙 Back", callback_data="mask_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


# ============================================================================
# ADD MASKED USER
# ============================================================================

async def add_masked_user_start(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start process to add masked user"""
    
    text = (
        "➕ **Add Masked User**\n\n"
        "Please send the username and mask name in this format:\n"
        "`@username | Mask Name`\n\n"
        "Example:\n"
        "`@john | Secret Agent`\n\n"
        "The user will be able to post anonymously as 'Secret Agent'\n\n"
        "Or /cancel to go back."
    )
    
    context.user_data['mask_action'] = 'add'
    await query.edit_message_text(text, parse_mode='Markdown')


async def process_add_masked_user(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Process adding masked user"""
    
    parts = text.split('|', 1)
    if len(parts) != 2:
        await update.message.reply_text(
            "❌ Invalid format. Use: `@username | Mask Name`",
            parse_mode='Markdown'
        )
        return
    
    username = parts[0].strip().lstrip('@')
    mask_name = parts[1].strip()
    
    if not username or not mask_name:
        await update.message.reply_text("❌ Both username and mask name are required!")
        return
    
    chat_id = str(update.effective_chat.id)
    
    # Get or create user ID
    from utils import data_manager
    username_to_id = data_manager.load_data('username_to_id.pkl', {})
    user_id = username_to_id.get(username)
    if not user_id:
        user_id = len(username_to_id) + 1000000
        username_to_id[username] = user_id
        data_manager.save_data(username_to_id, 'username_to_id.pkl')
    
    # Add to masked users
    if chat_id not in masked_users:
        masked_users[chat_id] = {}
    
    masked_users[chat_id][str(user_id)] = {
        'username': username,
        'mask_name': mask_name,
        'active': True,
        'added_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'added_by': update.effective_user.username or str(update.effective_user.id)
    }
    
    # Save
    data_manager.save_data(masked_users, 'masked_users.pkl')
    
    await update.message.reply_text(
        f"✅ **Masked User Added!**\n\n"
        f"@{username} can now post anonymously as **{mask_name}**\n\n"
        f"Use /masked to manage masked users.",
        parse_mode='Markdown'
    )


# ============================================================================
# REMOVE MASKED USER
# ============================================================================

async def remove_masked_user_start(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start process to remove masked user"""
    
    text = (
        "➖ **Remove Masked User**\n\n"
        "Please send the username of the masked user to remove:\n"
        "`@username`\n\n"
        "Or /cancel to go back."
    )
    
    context.user_data['mask_action'] = 'remove'
    await query.edit_message_text(text, parse_mode='Markdown')


async def process_remove_masked_user(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Process removing masked user"""
    
    username = text.lstrip('@').strip()
    
    chat_id = str(update.effective_chat.id)
    group_masked = masked_users.get(chat_id, {})
    
    # Find user
    user_id = None
    for uid, data in group_masked.items():
        if data.get('username') == username:
            user_id = uid
            break
    
    if not user_id:
        await update.message.reply_text(f"❌ @{username} is not a masked user in this group!")
        return
    
    # Remove
    mask_name = group_masked[user_id]['mask_name']
    del masked_users[chat_id][user_id]
    
    # Save
    data_manager.save_data(masked_users, 'masked_users.pkl')
    
    await update.message.reply_text(
        f"✅ **Masked User Removed!**\n\n"
        f"@{username} (was {mask_name}) can no longer post anonymously.\n\n"
        f"Use /masked to manage masked users.",
        parse_mode='Markdown'
    )


# ============================================================================
# EDIT MASK NAME
# ============================================================================

async def edit_mask_name_start(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start process to edit mask name"""
    
    text = (
        "✏️ **Edit Mask Name**\n\n"
        "Please send the username and new mask name:\n"
        "`@username | New Mask Name`\n\n"
        "Or /cancel to go back."
    )
    
    context.user_data['mask_action'] = 'edit'
    await query.edit_message_text(text, parse_mode='Markdown')


async def process_edit_mask_name(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Process editing mask name"""
    
    parts = text.split('|', 1)
    if len(parts) != 2:
        await update.message.reply_text(
            "❌ Invalid format. Use: `@username | New Mask Name`",
            parse_mode='Markdown'
        )
        return
    
    username = parts[0].strip().lstrip('@')
    new_mask_name = parts[1].strip()
    
    chat_id = str(update.effective_chat.id)
    group_masked = masked_users.get(chat_id, {})
    
    # Find user
    user_id = None
    for uid, data in group_masked.items():
        if data.get('username') == username:
            user_id = uid
            break
    
    if not user_id:
        await update.message.reply_text(f"❌ @{username} is not a masked user!")
        return
    
    old_mask = masked_users[chat_id][user_id]['mask_name']
    masked_users[chat_id][user_id]['mask_name'] = new_mask_name
    
    # Save
    data_manager.save_data(masked_users, 'masked_users.pkl')
    
    await update.message.reply_text(
        f"✅ **Mask Name Updated!**\n\n"
        f"@{username}\n"
        f"Old: {old_mask}\n"
        f"New: {new_mask_name}\n\n"
        f"Use /masked to manage masked users.",
        parse_mode='Markdown'
    )


# ============================================================================
# TOGGLE MASKING
# ============================================================================

async def toggle_masking_start(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start process to toggle masking"""
    
    text = (
        "🔄 **Toggle Masking**\n\n"
        "Please send the username to toggle:\n"
        "`@username`\n\n"
        "This will enable/disable masking for the user.\n\n"
        "Or /cancel to go back."
    )
    
    context.user_data['mask_action'] = 'toggle'
    await query.edit_message_text(text, parse_mode='Markdown')


async def process_toggle_masking(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Process toggling masking"""
    
    username = text.lstrip('@').strip()
    
    chat_id = str(update.effective_chat.id)
    group_masked = masked_users.get(chat_id, {})
    
    # Find user
    user_id = None
    for uid, data in group_masked.items():
        if data.get('username') == username:
            user_id = uid
            break
    
    if not user_id:
        await update.message.reply_text(f"❌ @{username} is not a masked user!")
        return
    
    # Toggle
    current_status = masked_users[chat_id][user_id].get('active', True)
    new_status = not current_status
    masked_users[chat_id][user_id]['active'] = new_status
    
    # Save
    data_manager.save_data(masked_users, 'masked_users.pkl')
    
    status_text = "enabled" if new_status else "disabled"
    status_icon = "🟢" if new_status else "❌"
    
    await update.message.reply_text(
        f"✅ **Masking {status_text.title()}!**\n\n"
        f"{status_icon} Masking for @{username} is now {status_text}.\n\n"
        f"Use /masked to manage masked users.",
        parse_mode='Markdown'
    )


# ============================================================================
# CALLBACK HANDLER
# ============================================================================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle masked users callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "mask_main":
        await show_main_menu(update, context)
    elif data == "mask_add":
        await add_masked_user_start(query, context)
    elif data == "mask_remove":
        await remove_masked_user_start(query, context)
    elif data == "mask_list":
        await show_all_masked_users(query, context)
    elif data == "mask_edit":
        await edit_mask_name_start(query, context)
    elif data == "mask_toggle":
        await toggle_masking_start(query, context)
    elif data == "mask_close":
        await query.edit_message_text("✅ Masked users menu closed.")


# ============================================================================
# TEXT INPUT HANDLER
# ============================================================================

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text input for masked users"""
    
    action = context.user_data.get('mask_action')
    
    if not action:
        return
    
    text = update.message.text
    
    if text == '/cancel':
        context.user_data.pop('mask_action', None)
        await update.message.reply_text("❌ Cancelled")
        return
    
    if action == 'add':
        await process_add_masked_user(update, context, text)
    elif action == 'remove':
        await process_remove_masked_user(update, context, text)
    elif action == 'edit':
        await process_edit_mask_name(update, context, text)
    elif action == 'toggle':
        await process_toggle_masking(update, context, text)
    
    # Clear action
    context.user_data.pop('mask_action', None)


# Export functions
__all__ = [
    'show_main_menu',
    'handle_callback',
    'handle_text_input'
]

