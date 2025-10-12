#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Moderation system - GroupHelpBot Style
Improved ban/mute functions that work with users not in the group
"""

import logging
import telegram
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
from typing import Optional
from datetime import datetime, timedelta
from database import database
from utils import SecurityValidator, safe_bot_operation
from config import ADMIN_CHAT_ID

logger = logging.getLogger(__name__)


# ============================================================================
# ADMIN CHECK
# ============================================================================

async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int = None) -> bool:
    """Check if user is admin or helper with comprehensive error handling"""
    try:
        if not update or not update.effective_chat:
            logger.warning("Invalid update object in is_admin check")
            return False
            
        chat_id = update.effective_chat.id
        check_user_id = user_id or update.effective_user.id
        
        if not check_user_id:
            logger.warning("No user ID available for admin check")
            return False
        
        # Global admin check
        if check_user_id == ADMIN_CHAT_ID:
            return True
        
        # Get chat member with error handling
        try:
            member = await safe_bot_operation(context.bot.get_chat_member, chat_id, check_user_id)
            if not member:
                logger.warning(f"Could not get chat member info for user {check_user_id}")
                return False
                
            # Check if user is admin or creator
            if member.status in ['creator', 'administrator']:
                return True
                
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            return False
        
        # Check if user is helper
        conn = None
        try:
            conn = database.get_sync_connection()
            cursor = conn.execute(
                "SELECT COUNT(*) FROM helpers WHERE chat_id = ? AND user_id = ?",
                (chat_id, check_user_id)
            )
            is_helper = cursor.fetchone()[0] > 0
            return is_helper
        except Exception as e:
            logger.error(f"Error checking helper status: {e}")
            return False
        finally:
            if conn:
                conn.close()
            
    except Exception as e:
        logger.error(f"Unexpected error in is_admin: {e}")
        return False


# ============================================================================
# USER RESOLUTION (IMPROVED - GroupHelpBot Style)
# ============================================================================

async def resolve_user(context: ContextTypes.DEFAULT_TYPE, username_or_id: str, chat_id: int) -> Optional[dict]:
    """
    Universal user resolver - GroupHelpBot style
    Returns dict with: user_id, username, first_name, last_name
    Works even if user is not in the group!
    """
    
    # Clean input
    clean_input = username_or_id.strip()
    
    # Try direct ID parsing first
    if clean_input.isdigit():
        user_id = int(clean_input)
        if user_id > 0:
            # Try to get user info
            try:
                user_chat = await context.bot.get_chat(user_id)
                return {
                    'user_id': user_id,
                    'username': user_chat.username,
                    'first_name': user_chat.first_name,
                    'last_name': user_chat.last_name
                }
            except Exception as e:
                logger.warning(f"Could not get user info for ID {user_id}: {e}")
                # Return basic info even if can't get full details
                return {
                    'user_id': user_id,
                    'username': None,
                    'first_name': f'User',
                    'last_name': None
                }
    
    # Clean username (remove @)
    username = clean_input.lstrip('@').lower()
    if not username:
        return None
    
    logger.info(f"Resolving username: {username}")
    
    # Method 1: Check ban history (works for previously banned users)
    try:
        ban_records = database.get_ban_history(username=username)
        if ban_records and ban_records[0].get('user_id'):
            user_id = ban_records[0]['user_id']
            logger.info(f"Found {username} in ban history: {user_id}")
            
            # Try to get updated user info
            try:
                user_chat = await context.bot.get_chat(user_id)
                return {
                    'user_id': user_id,
                    'username': user_chat.username or username,
                    'first_name': user_chat.first_name,
                    'last_name': user_chat.last_name
                }
            except:
                # Return info from ban history
                return {
                    'user_id': user_id,
                    'username': username,
                    'first_name': ban_records[0].get('first_name', 'User'),
                    'last_name': ban_records[0].get('last_name')
                }
    except Exception as e:
        logger.warning(f"Error checking ban history: {e}")
    
    # Method 2: Check user cache
    try:
        user_info = database.get_user_by_username(username)
        if user_info:
            user_id = user_info['user_id']
            logger.info(f"Found {username} in user cache: {user_id}")
            
            # Try to get updated info
            try:
                user_chat = await context.bot.get_chat(user_id)
                return {
                    'user_id': user_id,
                    'username': user_chat.username or username,
                    'first_name': user_chat.first_name,
                    'last_name': user_chat.last_name
                }
            except:
                return {
                    'user_id': user_id,
                    'username': username,
                    'first_name': user_info.get('first_name', 'User'),
                    'last_name': user_info.get('last_name')
                }
    except Exception as e:
        logger.warning(f"Error checking user cache: {e}")
    
    # Method 3: Try to get from group members (if user is in group)
    try:
        # This won't work for users not in group, but try anyway
        chat_member = await context.bot.get_chat_member(chat_id, username)
        if chat_member and chat_member.user:
            return {
                'user_id': chat_member.user.id,
                'username': chat_member.user.username or username,
                'first_name': chat_member.user.first_name,
                'last_name': chat_member.user.last_name
            }
    except Exception as e:
        logger.debug(f"User {username} not found in group: {e}")
    
    logger.warning(f"Could not resolve user: {username}")
    return None


# ============================================================================
# BAN COMMAND (GroupHelpBot Style - Works even if user not in group!)
# ============================================================================

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Ban user - GroupHelpBot style
    Works even if user is not currently in the group!
    """
    # Check admin permissions
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Only administrators can ban users!")
        return
    
    # Check if in group
    if update.effective_chat.type == 'private':
        await update.message.reply_text("❌ This command only works in groups!")
        return
    
    # Check arguments
    if not context.args:
        await update.message.reply_text(
            "❌ **Usage:** `/ban @username [reason]` or `/ban user_id [reason]`\n\n"
            "**Examples:**\n"
            "• `/ban @spammer`\n"
            "• `/ban @user Spam messages`\n"
            "• `/ban 123456789 Rule violation`",
            parse_mode='Markdown'
        )
        return
    
    chat_id = update.effective_chat.id
    admin_user = update.effective_user
    target_input = context.args[0]
    reason = ' '.join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
    
    # Resolve user (works even if not in group!)
    user_info = await resolve_user(context, target_input, chat_id)
    
    if not user_info or not user_info.get('user_id'):
        await update.message.reply_text(
            f"❌ Could not find user: {target_input}\n\n"
            "Make sure the username is correct or use user ID."
        )
        return
    
    user_id = user_info['user_id']
    username = user_info.get('username', 'Unknown')
    first_name = user_info.get('first_name', 'User')
    last_name = user_info.get('last_name', '')
    full_name = f"{first_name} {last_name}".strip()
    
    # Check if trying to ban admin
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in ['creator', 'administrator']:
            await update.message.reply_text("❌ Cannot ban administrators!")
            return
    except Exception as e:
        # User might not be in group - that's okay, we can still ban them
        logger.info(f"User {user_id} not in group, proceeding with ban: {e}")
    
    # Execute ban (works even if user not in group!)
    try:
        await context.bot.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            revoke_messages=True  # Delete their messages
        )
        
        # Record in database
        database.add_ban_record(
            user_id=user_id,
            username=username or f"user_{user_id}",
            chat_id=chat_id,
            banned_by=admin_user.id,
            banned_by_username=admin_user.username or str(admin_user.id),
            reason=reason
        )
        
        # Success message - GroupHelpBot style
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await update.message.reply_text(
            "🚫 **VARTOTOJAS UŽDRAUSTAS** 🚫\n\n"
            f"👤 Vartotojas: {full_name} (@{username})\n"
            f"🆔 ID: `{user_id}`\n"
            f"👮 Uždraudė: {admin_user.first_name} (@{admin_user.username or 'admin'})\n"
            f"📝 Priežastis: {reason}\n"
            f"⏰ Data: {timestamp}",
            parse_mode='Markdown'
        )
        
        logger.info(f"Banned user {user_id} from chat {chat_id}. Reason: {reason}")
        
    except telegram.error.BadRequest as e:
        if "user not found" in str(e).lower():
            await update.message.reply_text(f"❌ User not found: {target_input}")
        elif "not enough rights" in str(e).lower():
            await update.message.reply_text("❌ Bot doesn't have permission to ban users!")
        else:
            await update.message.reply_text(f"❌ Error: {str(e)}")
        logger.error(f"Ban failed: {e}")
    except Exception as e:
        await update.message.reply_text(f"❌ Error banning user: {str(e)}")
        logger.error(f"Error in ban_user: {e}")


# ============================================================================
# UNBAN COMMAND (GroupHelpBot Style)
# ============================================================================

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unban user - GroupHelpBot style"""
    
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Only administrators can unban users!")
        return
    
    if update.effective_chat.type == 'private':
        await update.message.reply_text("❌ This command only works in groups!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ **Usage:** `/unban @username` or `/unban user_id`",
            parse_mode='Markdown'
        )
        return
    
    chat_id = update.effective_chat.id
    admin_user = update.effective_user
    target_input = context.args[0]
    
    # Resolve user
    user_info = await resolve_user(context, target_input, chat_id)
    
    if not user_info or not user_info.get('user_id'):
        await update.message.reply_text(f"❌ Could not find user: {target_input}")
        return
    
    user_id = user_info['user_id']
    username = user_info.get('username', 'Unknown')
    full_name = f"{user_info.get('first_name', 'User')} {user_info.get('last_name', '')}".strip()
    
    # Execute unban
    try:
        await context.bot.unban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            only_if_banned=True
        )
        
        # Update database
        database.record_unban(
            chat_id=chat_id,
            user_id=user_id,
            unbanned_by=admin_user.username or str(admin_user.id)
        )
        
        # Success message - GroupHelpBot style
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await update.message.reply_text(
            "✅ **VARTOTOJAS ATKURTAS** ✅\n\n"
            f"👤 Vartotojas: {full_name} (@{username})\n"
            f"🆔 ID: `{user_id}`\n"
            f"👮 Atkūrė: {admin_user.first_name} (@{admin_user.username or 'admin'})\n"
            f"⏰ Data: {timestamp}",
            parse_mode='Markdown'
        )
        
        logger.info(f"Unbanned user {user_id} from chat {chat_id}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error unbanning user: {str(e)}")
        logger.error(f"Error in unban_user: {e}")


# ============================================================================
# MUTE COMMAND (GroupHelpBot Style)
# ============================================================================

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mute user - GroupHelpBot style"""
    
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Only administrators can mute users!")
        return
    
    if update.effective_chat.type == 'private':
        await update.message.reply_text("❌ This command only works in groups!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ **Usage:** `/mute @username [duration_minutes] [reason]`\n\n"
            "**Examples:**\n"
            "• `/mute @spammer` - Mute indefinitely\n"
            "• `/mute @user 60` - Mute for 60 minutes\n"
            "• `/mute @user 30 Spam` - Mute for 30 min with reason",
            parse_mode='Markdown'
        )
        return
    
    chat_id = update.effective_chat.id
    admin_user = update.effective_user
    target_input = context.args[0]
    
    # Parse duration and reason
    duration_minutes = None
    reason = "No reason provided"
    
    if len(context.args) > 1:
        if context.args[1].isdigit():
            duration_minutes = int(context.args[1])
            if len(context.args) > 2:
                reason = ' '.join(context.args[2:])
        else:
            reason = ' '.join(context.args[1:])
    
    # Resolve user
    user_info = await resolve_user(context, target_input, chat_id)
    
    if not user_info or not user_info.get('user_id'):
        await update.message.reply_text(f"❌ Could not find user: {target_input}")
        return
    
    user_id = user_info['user_id']
    username = user_info.get('username', 'Unknown')
    full_name = f"{user_info.get('first_name', 'User')} {user_info.get('last_name', '')}".strip()
    
    # Check if trying to mute admin
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        if member.status in ['creator', 'administrator']:
            await update.message.reply_text("❌ Cannot mute administrators!")
            return
    except:
        pass
    
    # Set permissions (restrict all)
    permissions = ChatPermissions(
        can_send_messages=False,
        can_send_media_messages=False,
        can_send_polls=False,
        can_send_other_messages=False,
        can_add_web_page_previews=False,
        can_change_info=False,
        can_invite_users=False,
        can_pin_messages=False
    )
    
    # Execute mute
    try:
        until_date = None
        if duration_minutes:
            until_date = datetime.now() + timedelta(minutes=duration_minutes)
        
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=permissions,
            until_date=until_date
        )
        
        # Success message - GroupHelpBot style
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        duration_text = f"{duration_minutes} minutes" if duration_minutes else "indefinitely"
        
        await update.message.reply_text(
            "🔇 **VARTOTOJAS NUTILDYTAS** 🔇\n\n"
            f"👤 Vartotojas: {full_name} (@{username})\n"
            f"🆔 ID: `{user_id}`\n"
            f"👮 Nutildė: {admin_user.first_name} (@{admin_user.username or 'admin'})\n"
            f"⏱️ Trukmė: {duration_text}\n"
            f"📝 Priežastis: {reason}\n"
            f"⏰ Data: {timestamp}",
            parse_mode='Markdown'
        )
        
        logger.info(f"Muted user {user_id} in chat {chat_id} for {duration_text}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error muting user: {str(e)}")
        logger.error(f"Error in mute_user: {e}")


# ============================================================================
# UNMUTE COMMAND (GroupHelpBot Style)
# ============================================================================

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unmute user - GroupHelpBot style"""
    
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Only administrators can unmute users!")
        return
    
    if update.effective_chat.type == 'private':
        await update.message.reply_text("❌ This command only works in groups!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ **Usage:** `/unmute @username` or `/unmute user_id`",
            parse_mode='Markdown'
        )
        return
    
    chat_id = update.effective_chat.id
    admin_user = update.effective_user
    target_input = context.args[0]
    
    # Resolve user
    user_info = await resolve_user(context, target_input, chat_id)
    
    if not user_info or not user_info.get('user_id'):
        await update.message.reply_text(f"❌ Could not find user: {target_input}")
        return
    
    user_id = user_info['user_id']
    username = user_info.get('username', 'Unknown')
    full_name = f"{user_info.get('first_name', 'User')} {user_info.get('last_name', '')}".strip()
    
    # Restore permissions
    permissions = ChatPermissions(
        can_send_messages=True,
        can_send_media_messages=True,
        can_send_polls=True,
        can_send_other_messages=True,
        can_add_web_page_previews=True,
        can_change_info=False,
        can_invite_users=True,
        can_pin_messages=False
    )
    
    # Execute unmute
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=permissions
        )
        
        # Success message - GroupHelpBot style
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await update.message.reply_text(
            "✅ **VARTOTOJAS ATKURTAS** ✅\n\n"
            f"👤 Vartotojas: {full_name} (@{username})\n"
            f"🆔 ID: `{user_id}`\n"
            f"👮 Atkūrė: {admin_user.first_name} (@{admin_user.username or 'admin'})\n"
            f"⏰ Data: {timestamp}",
            parse_mode='Markdown'
        )
        
        logger.info(f"Unmuted user {user_id} in chat {chat_id}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error unmuting user: {str(e)}")
        logger.error(f"Error in unmute_user: {e}")


# ============================================================================
# LOOKUP COMMAND
# ============================================================================

async def lookup_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lookup user information"""
    
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Only administrators can lookup users!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ **Usage:** `/lookup @username` or `/lookup user_id`",
            parse_mode='Markdown'
        )
        return
    
    chat_id = update.effective_chat.id
    target_input = context.args[0]
    
    # Resolve user
    user_info = await resolve_user(context, target_input, chat_id)
    
    if not user_info or not user_info.get('user_id'):
        await update.message.reply_text(f"❌ Could not find user: {target_input}")
        return
    
    user_id = user_info['user_id']
    username = user_info.get('username', 'Unknown')
    full_name = f"{user_info.get('first_name', 'User')} {user_info.get('last_name', '')}".strip()
    
    # Get additional info
    status = "Unknown"
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        status_map = {
            'creator': '👑 Creator',
            'administrator': '⭐ Administrator',
            'member': '👤 Member',
            'restricted': '🔇 Restricted',
            'left': '🚪 Left',
            'kicked': '🚫 Banned'
        }
        status = status_map.get(member.status, member.status)
    except:
        status = "Not in group"
    
    # Check ban history
    ban_count = 0
    try:
        ban_records = database.get_ban_history(user_id=user_id)
        ban_count = len(ban_records) if ban_records else 0
    except:
        pass
    
    await update.message.reply_text(
        f"👤 **USER INFORMATION**\n\n"
        f"**Name:** {full_name}\n"
        f"**Username:** @{username}\n"
        f"**ID:** `{user_id}`\n"
        f"**Status:** {status}\n"
        f"**Ban History:** {ban_count} records",
        parse_mode='Markdown'
    )


# Export functions
__all__ = [
    'is_admin',
    'resolve_user',
    'ban_user',
    'unban_user',
    'mute_user',
    'unmute_user',
    'lookup_user'
]

