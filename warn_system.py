#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Warn System - GroupHelpBot Style
Automatically track warnings and apply sanctions
"""

import logging
from datetime import datetime, timedelta
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
from database import database

logger = logging.getLogger(__name__)

# Default settings (can be customized per chat)
DEFAULT_MAX_WARNS = 3
DEFAULT_WARN_ACTION = "mute"  # Options: "mute", "kick", "ban"
DEFAULT_MUTE_DURATION = 12  # hours

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Check if user is admin"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ['creator', 'administrator']
    except:
        return False


async def warn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Warn a user - GroupHelpBot style
    Usage: /warn @username [reason]
    """
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Tik administratoriai gali įspėti narius.")
        return
    
    chat_id = update.effective_chat.id
    admin_user = update.effective_user
    
    # Parse command
    if not update.message.reply_to_message and not context.args:
        await update.message.reply_text(
            "💡 **Naudojimas:**\n"
            "• Atsakykite į pranešimą: `/warn [priežastis]`\n"
            "• Arba: `/warn @username [priežastis]`",
            parse_mode='Markdown'
        )
        return
    
    # Get user to warn
    if update.message.reply_to_message:
        user_id = update.message.reply_to_message.from_user.id
        username = update.message.reply_to_message.from_user.username or \
                   update.message.reply_to_message.from_user.first_name
        reason = ' '.join(context.args) if context.args else "Taisyklių pažeidimas"
    else:
        # Parse @username
        username_arg = context.args[0]
        if username_arg.startswith('@'):
            username_arg = username_arg[1:]
        
        # Try to find user in cache
        user_data = database.get_user_by_username(username_arg)
        if not user_data:
            await update.message.reply_text(
                f"❌ Naudotojas @{username_arg} nerastas!\n"
                f"💡 Patarimas: Atsakykite į jo pranešimą su /warn"
            )
            return
        
        user_id = user_data['user_id']
        username = user_data['username']
        reason = ' '.join(context.args[1:]) if len(context.args) > 1 else "Taisyklių pažeidimas"
    
    # Don't warn admins
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in ['creator', 'administrator']:
            await update.message.reply_text("❌ Negalima įspėti administratorių!")
            return
    except Exception as e:
        logger.error(f"Error checking member status: {e}")
    
    # Add warning to database
    try:
        conn = database.get_sync_connection()
        
        # Insert warning
        conn.execute('''
            INSERT INTO warnings (user_id, username, chat_id, warned_by, warned_by_username, reason, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, username, chat_id, admin_user.id, admin_user.username or str(admin_user.id), reason))
        conn.commit()
        
        # Get total warnings
        cursor = conn.execute('''
            SELECT COUNT(*) FROM warnings 
            WHERE user_id = ? AND chat_id = ? AND is_active = 1
        ''', (user_id, chat_id))
        warn_count = cursor.fetchone()[0]
        
        conn.close()
        
        # Send warning message
        text = (
            f"⚠️ **Įspėjimas #{warn_count}**\n\n"
            f"👤 Naudotojas: @{username}\n"
            f"📋 Priežastis: {reason}\n"
            f"👮 Administratorius: @{admin_user.username or admin_user.first_name}\n\n"
        )
        
        # Check if max warnings reached
        if warn_count >= DEFAULT_MAX_WARNS:
            if DEFAULT_WARN_ACTION == "mute":
                # Mute user
                until_date = datetime.now() + timedelta(hours=DEFAULT_MUTE_DURATION)
                await context.bot.restrict_chat_member(
                    chat_id,
                    user_id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=until_date
                )
                text += (
                    f"🔇 **Automatinis nutildymas!**\n"
                    f"⏱️ Trukmė: {DEFAULT_MUTE_DURATION} val.\n"
                    f"📊 Pasiektas limitas: {DEFAULT_MAX_WARNS} įspėjimai"
                )
                logger.info(f"Auto-muted user {user_id} in chat {chat_id} after {warn_count} warnings")
            
            elif DEFAULT_WARN_ACTION == "kick":
                await context.bot.ban_chat_member(chat_id, user_id)
                await context.bot.unban_chat_member(chat_id, user_id)
                text += f"👢 **Automatiškai išmestas!**\n📊 Pasiektas limitas: {DEFAULT_MAX_WARNS} įspėjimai"
                logger.info(f"Auto-kicked user {user_id} from chat {chat_id} after {warn_count} warnings")
            
            elif DEFAULT_WARN_ACTION == "ban":
                await context.bot.ban_chat_member(chat_id, user_id)
                text += f"🚫 **Automatiškai užblokuotas!**\n📊 Pasiektas limitas: {DEFAULT_MAX_WARNS} įspėjimai"
                logger.info(f"Auto-banned user {user_id} from chat {chat_id} after {warn_count} warnings")
        else:
            text += f"📊 Įspėjimų: **{warn_count}/{DEFAULT_MAX_WARNS}**"
        
        await update.message.reply_text(text, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Klaida įspėjant naudotoją: {str(e)}")
        logger.error(f"Error in warn_user: {e}")


async def unwarn_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Remove a warning from user
    Usage: /unwarn @username
    """
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Tik administratoriai gali pašalinti įspėjimus.")
        return
    
    chat_id = update.effective_chat.id
    
    # Parse command
    if not update.message.reply_to_message and not context.args:
        await update.message.reply_text(
            "💡 **Naudojimas:**\n"
            "• Atsakykite į pranešimą: `/unwarn`\n"
            "• Arba: `/unwarn @username` arba `/unwarn [user_id]`",
            parse_mode='Markdown'
        )
        return
    
    # Get user
    if update.message.reply_to_message:
        user_id = update.message.reply_to_message.from_user.id
        username = update.message.reply_to_message.from_user.username or \
                   update.message.reply_to_message.from_user.first_name
    else:
        target_input = context.args[0].strip().lstrip('@')
        
        # Try direct user_id first (more reliable for users who left)
        if target_input.isdigit():
            user_id = int(target_input)
            # Try to get username from cache
            try:
                user_data = database.get_user_by_id(user_id)
                username = user_data.get('username', f'user_{user_id}') if user_data else f'user_{user_id}'
            except:
                username = f'user_{user_id}'
        else:
            # Try username lookup
            user_data = database.get_user_by_username(target_input)
            if not user_data:
                await update.message.reply_text(f"❌ Naudotojas @{target_input} nerastas!\n\nBandykite naudoti user ID.")
                return
            
            user_id = user_data['user_id']
            username = user_data['username']
    
    try:
        conn = database.get_sync_connection()
        
        # Get last active warning
        cursor = conn.execute('''
            SELECT id FROM warnings 
            WHERE user_id = ? AND chat_id = ? AND is_active = 1
            ORDER BY timestamp DESC LIMIT 1
        ''', (user_id, chat_id))
        
        warning = cursor.fetchone()
        
        if not warning:
            await update.message.reply_text(f"ℹ️ @{username} neturi aktyvių įspėjimų.")
            conn.close()
            return
        
        # Deactivate warning
        conn.execute('''
            UPDATE warnings SET is_active = 0 WHERE id = ?
        ''', (warning[0],))
        conn.commit()
        
        # Get remaining warnings
        cursor = conn.execute('''
            SELECT COUNT(*) FROM warnings 
            WHERE user_id = ? AND chat_id = ? AND is_active = 1
        ''', (user_id, chat_id))
        remaining = cursor.fetchone()[0]
        
        conn.close()
        
        await update.message.reply_text(
            f"✅ **Įspėjimas pašalintas**\n\n"
            f"👤 Naudotojas: @{username}\n"
            f"📊 Liko įspėjimų: {remaining}/{DEFAULT_MAX_WARNS}",
            parse_mode='Markdown'
        )
        
        logger.info(f"Removed warning for user {user_id} in chat {chat_id}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Klaida: {str(e)}")
        logger.error(f"Error in unwarn_user: {e}")


async def warnings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Check user's warnings
    Usage: /warnings [@username]
    """
    chat_id = update.effective_chat.id
    
    # Get user to check
    if update.message.reply_to_message:
        user_id = update.message.reply_to_message.from_user.id
        username = update.message.reply_to_message.from_user.username or \
                   update.message.reply_to_message.from_user.first_name
    elif context.args:
        username_arg = context.args[0]
        if username_arg.startswith('@'):
            username_arg = username_arg[1:]
        
        user_data = database.get_user_by_username(username_arg)
        if not user_data:
            await update.message.reply_text(f"❌ Naudotojas @{username_arg} nerastas!")
            return
        
        user_id = user_data['user_id']
        username = user_data['username']
    else:
        # Check own warnings
        user_id = update.effective_user.id
        username = update.effective_user.username or update.effective_user.first_name
    
    try:
        conn = database.get_sync_connection()
        
        # Get active warnings
        cursor = conn.execute('''
            SELECT reason, timestamp, warned_by_username 
            FROM warnings 
            WHERE user_id = ? AND chat_id = ? AND is_active = 1
            ORDER BY timestamp DESC
        ''', (user_id, chat_id))
        
        warnings = cursor.fetchall()
        warn_count = len(warnings)
        
        conn.close()
        
        if warn_count == 0:
            await update.message.reply_text(
                f"✅ @{username} neturi aktyvių įspėjimų!",
                parse_mode='Markdown'
            )
            return
        
        text = f"⚠️ **Įspėjimai: @{username}**\n\n"
        text += f"📊 **Aktyvūs: {warn_count}/{DEFAULT_MAX_WARNS}**\n\n"
        
        for i, (reason, timestamp, admin) in enumerate(warnings, 1):
            text += f"{i}. {reason}\n"
            text += f"   └ {timestamp[:16]} | Admin: @{admin}\n\n"
        
        if warn_count >= DEFAULT_MAX_WARNS:
            text += "🚨 **PERSPĖJIMAS:** Pasiektas limitas!"
        
        await update.message.reply_text(text, parse_mode='Markdown')
        
    except Exception as e:
        await update.message.reply_text(f"❌ Klaida: {str(e)}")
        logger.error(f"Error in warnings_command: {e}")


async def resetwarns_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Reset all warnings for a user
    Usage: /resetwarns @username
    """
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Tik administratoriai gali išvalyti įspėjimus.")
        return
    
    chat_id = update.effective_chat.id
    
    # Parse command
    if not update.message.reply_to_message and not context.args:
        await update.message.reply_text(
            "💡 **Naudojimas:**\n"
            "• Atsakykite į pranešimą: `/resetwarns`\n"
            "• Arba: `/resetwarns @username`",
            parse_mode='Markdown'
        )
        return
    
    # Get user
    if update.message.reply_to_message:
        user_id = update.message.reply_to_message.from_user.id
        username = update.message.reply_to_message.from_user.username or \
                   update.message.reply_to_message.from_user.first_name
    else:
        username_arg = context.args[0]
        if username_arg.startswith('@'):
            username_arg = username_arg[1:]
        
        user_data = database.get_user_by_username(username_arg)
        if not user_data:
            await update.message.reply_text(f"❌ Naudotojas @{username_arg} nerastas!")
            return
        
        user_id = user_data['user_id']
        username = user_data['username']
    
    try:
        conn = database.get_sync_connection()
        
        # Deactivate all warnings
        conn.execute('''
            UPDATE warnings SET is_active = 0 
            WHERE user_id = ? AND chat_id = ? AND is_active = 1
        ''', (user_id, chat_id))
        
        affected = conn.total_changes
        conn.commit()
        conn.close()
        
        await update.message.reply_text(
            f"✅ **Įspėjimai išvalyti**\n\n"
            f"👤 Naudotojas: @{username}\n"
            f"🗑️ Pašalinta: {affected} įspėjimų",
            parse_mode='Markdown'
        )
        
        logger.info(f"Reset {affected} warnings for user {user_id} in chat {chat_id}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Klaida: {str(e)}")
        logger.error(f"Error in resetwarns_command: {e}")


# Export functions
__all__ = [
    'warn_user',
    'unwarn_user',
    'warnings_command',
    'resetwarns_command'
]

