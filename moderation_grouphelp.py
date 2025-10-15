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

def parse_user_from_message(update: Update) -> Optional[tuple]:
    """
    Parse user from message - supports @mentions with entity data
    Returns: (user_info_dict, remaining_text) or (None, None)
    
    This handles Telegram's mention entities which include user_id even if user never sent messages!
    """
    # Check for text_mention entity (users without username or clickable names)
    if update.message.entities:
        for entity in update.message.entities:
            if entity.type == 'text_mention' and entity.user:
                target_user = entity.user
                user_info = {
                    'user_id': target_user.id,
                    'username': target_user.username or f"user_{target_user.id}",
                    'first_name': target_user.first_name,
                    'last_name': target_user.last_name
                }
                # Extract remaining text after mention
                text = update.message.text or ""
                reason_start = entity.offset + entity.length
                remaining = text[reason_start:].strip()
                logger.info(f"Parsed via text_mention: @{user_info['username']} (ID: {user_info['user_id']})")
                return (user_info, remaining)
    
    return (None, None)


async def resolve_user(context: ContextTypes.DEFAULT_TYPE, username_or_id: str, chat_id: int) -> Optional[dict]:
    """
    Universal user resolver - GroupHelpBot style
    Returns dict with: user_id, username, first_name, last_name
    Works even if user is not in the group!
    """
    
    # Convert to string and clean input
    clean_input = str(username_or_id).strip()
    
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
    
    # Method 3: Try to resolve username via Telegram API directly
    # This sometimes works for users with public profiles
    try:
        # Try @username format
        try:
            chat_info = await context.bot.get_chat(f"@{username}")
            if chat_info and chat_info.type == 'private':
                logger.info(f"Found {username} via get_chat API")
                return {
                    'user_id': chat_info.id,
                    'username': chat_info.username or username,
                    'first_name': chat_info.first_name,
                    'last_name': chat_info.last_name
                }
        except Exception as e:
            logger.debug(f"get_chat failed for @{username}: {e}")
    except Exception as e:
        logger.debug(f"Error trying get_chat: {e}")
    
    # Method 4: Search chat administrators (they're always accessible)
    try:
        admins = await context.bot.get_chat_administrators(chat_id)
        for admin in admins:
            admin_username = admin.user.username.lower() if admin.user.username else None
            if admin_username == username:
                logger.info(f"Found {username} in chat administrators")
                return {
                    'user_id': admin.user.id,
                    'username': admin.user.username,
                    'first_name': admin.user.first_name,
                    'last_name': admin.user.last_name
                }
    except Exception as e:
        logger.debug(f"Error checking administrators: {e}")
    
    # Method 5: All resolution methods exhausted
    # This is a Telegram API limitation - can't search members by username
    logger.warning(f"Could not resolve user: {username}")
    logger.info(f"User @{username} not found. This is a Telegram API limitation.")
    logger.info(f"Solutions: 1) Reply to their message, 2) They send a message, 3) Use their user_id")
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
    
    chat_id = update.effective_chat.id
    admin_user = update.effective_user
    user_info = None
    reason = "No reason provided"
    
    # Method 1: Reply to user's message (HIGHEST PRIORITY)
    if update.message.reply_to_message and update.message.reply_to_message.from_user:
        target_user = update.message.reply_to_message.from_user
        user_info = {
            'user_id': target_user.id,
            'username': target_user.username or f"user_{target_user.id}",
            'first_name': target_user.first_name,
            'last_name': target_user.last_name
        }
        reason = ' '.join(context.args) if context.args else "No reason provided"
        logger.info(f"Ban via reply: @{user_info['username']} (ID: {user_info['user_id']})")
    
    # Method 2: Parse @mention entity (ALWAYS TRY THIS FIRST!)
    # This works even if user never sent message IF Telegram included entity data
    elif update.message.entities:
        entity_user, entity_remaining = parse_user_from_message(update)
        if entity_user:
            user_info = entity_user
            # If there's remaining text after entity, use it as reason
            if entity_remaining:
                reason = entity_remaining
            # Otherwise use args if available
            elif context.args and len(context.args) > 1:
                reason = ' '.join(context.args[1:])
            logger.info(f"Ban via entity: @{user_info['username']} (ID: {user_info['user_id']})")
        # If entity parsing failed, fall back to text-based resolution
        elif context.args:
            target_input = context.args[0]
            reason = ' '.join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
            user_info = await resolve_user(context, target_input, chat_id)
    
    # Method 3: By username or ID (text-based, no entities)
    elif context.args:
        target_input = context.args[0]
        reason = ' '.join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
        user_info = await resolve_user(context, target_input, chat_id)
    
    # No arguments and no reply
    else:
        await update.message.reply_text(
            "❌ **Usage:**\n\n"
            "**Method 1:** `/ban @username [reason]` ⭐ **Works always!**\n"
            "**Method 2:** Reply to user's message + `/ban [reason]`\n"
            "**Method 3:** `/ban user_id [reason]`\n\n"
            "**Examples:**\n"
            "• By mention: `/ban @spammer Spam` (works even if never sent messages!)\n"
            "• By reply: Reply to message + `/ban Spam`\n"
            "• By ID: `/ban 123456789 Rule violation`\n\n"
            "💡 **@mention method works for ANY user in the group!**",
            parse_mode='Markdown'
        )
        return
    
    if not user_info or not user_info.get('user_id'):
        # User not found - add to pending bans anyway (GroupHelpBot style!)
        # This handles cases where user has never been in the group
        clean_input = target_input.strip().lstrip('@')
        
        # Try to extract user ID if it's a numeric input
        if clean_input.isdigit():
            user_id = int(clean_input)
            username = f"user_{user_id}"
        else:
            # For username-only input - add to pending bans with user_id = 0
            # Will match on join by username (GroupHelpBot behavior)
            user_id = 0  # Placeholder - will be updated when user joins
            username = clean_input.lower()
        
        # Add to pending bans with available info
        database.add_pending_ban(
            user_id=user_id,
            username=username,
            chat_id=chat_id,
            banned_by=admin_user.id,
            banned_by_username=admin_user.username or str(admin_user.id),
            reason=reason
        )
        
        # Success message - GroupHelpBot style
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        if user_id == 0:
            # Username-only ban
            await update.message.reply_text(
                "⚠️ **VARTOTOJAS NERASTAS SISTEMOJE** ⚠️\n\n"
                f"👤 Vartotojas: @{username}\n"
                f"👮 Uždraudė: {admin_user.first_name} (@{admin_user.username or 'admin'})\n"
                f"📝 Priežastis: {reason}\n"
                f"⏰ Data: {timestamp}\n\n"
                f"ℹ️ **Pridėtas į laukiančiųjų sąrašą.**\n"
                f"✅ Bus automatiškai uždraustas prisijungus prie grupės.\n\n"
                f"💡 **Jei vartotojas jau grupėje:**\n"
                f"1. Atsakykite į jo žinutę su `/ban {reason}`\n"
                f"2. Arba naudokite: `/ban [user_ID] {reason}`\n"
                f"3. Arba paprašykite jo parašyti bent vieną žinutę",
                parse_mode='Markdown'
            )
        else:
            # User ID ban
            await update.message.reply_text(
                "⏳ **VARTOTOJAS PRIDĖTAS Į UŽDRAUDIMO SĄRAŠĄ** ⏳\n\n"
                f"👤 Vartotojas: @{username}\n"
                f"🆔 ID: `{user_id}`\n"
                f"👮 Uždraudė: {admin_user.first_name} (@{admin_user.username or 'admin'})\n"
                f"📝 Priežastis: {reason}\n"
                f"⏰ Data: {timestamp}\n\n"
                f"✅ **Vartotojas bus automatiškai uždraustas, kai prisijungs prie grupės!**",
                parse_mode='Markdown'
            )
        
        logger.info(f"Added pending ban for @{username} (ID: {user_id}) in chat {chat_id} - user not found in any cache")
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
            # User not in group - add to pending ban list (GroupHelpBot style!)
            database.add_pending_ban(
                user_id=user_id,
                username=username,
                chat_id=chat_id,
                banned_by=admin_user.id,
                banned_by_username=admin_user.username or str(admin_user.id),
                reason=reason
            )
            
            # Success message - GroupHelpBot style
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            await update.message.reply_text(
                "⏳ **VARTOTOJAS PRIDĖTAS Į UŽDRAUDIMO SĄRAŠĄ** ⏳\n\n"
                f"👤 Vartotojas: {full_name} (@{username})\n"
                f"🆔 ID: `{user_id}`\n"
                f"👮 Uždraudė: {admin_user.first_name} (@{admin_user.username or 'admin'})\n"
                f"📝 Priežastis: {reason}\n"
                f"⏰ Data: {timestamp}\n\n"
                f"✅ **Vartotojas bus automatiškai uždraustas, kai prisijungs prie grupės!**",
                parse_mode='Markdown'
            )
            
            logger.info(f"Added pending ban for {username} (ID: {user_id}) in chat {chat_id}")
            
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
            "❌ **Usage:** `/lookup @username` or `/lookup user_id`\n\n"
            "💡 **To get user ID for banning:**\n"
            "• Forward their message to @userinfobot\n"
            "• Or use @getmyid_bot",
            parse_mode='Markdown'
        )
        return
    
    chat_id = update.effective_chat.id
    target_input = context.args[0]
    
    # Resolve user
    user_info = await resolve_user(context, target_input, chat_id)
    
    if not user_info or not user_info.get('user_id'):
        await update.message.reply_text(
            f"❌ Could not find user: {target_input}\n\n"
            f"**To ban this user anyway:**\n"
            f"Use their **user ID** instead of username:\n\n"
            f"**Example:** `/ban 123456789 spam`\n\n"
            f"💡 **How to get user ID:**\n"
            f"• Forward their message to @userinfobot\n"
            f"• Or use @getmyid_bot\n"
            f"• Or check if they're in ban history",
            parse_mode='Markdown'
        )
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


# ============================================================================
# CHAT MEMBER HANDLER (Auto-ban on join)
# ============================================================================

async def handle_new_chat_member(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle new chat members - auto-ban if in pending list"""
    try:
        new_member = update.chat_member.new_chat_member.user
        chat_id = update.effective_chat.id
        
        # Check if user is in pending ban list by user_id OR username
        pending_ban = None
        
        # Method 1: Check by user_id
        if database.is_pending_ban(new_member.id, chat_id):
            pending_ban = database.get_pending_ban(new_member.id, chat_id)
        
        # Method 2: Check by username (for username-only bans)
        if not pending_ban and new_member.username:
            try:
                conn = database.get_sync_connection()
                cursor = conn.execute(
                    "SELECT * FROM pending_bans WHERE LOWER(username) = ? AND chat_id = ?",
                    (new_member.username.lower(), chat_id)
                )
                row = cursor.fetchone()
                conn.close()
                if row:
                    pending_ban = dict(row)
            except Exception as e:
                logger.error(f"Error checking username in pending bans: {e}")
        
        if pending_ban:
            # Execute the ban immediately
            try:
                await context.bot.ban_chat_member(
                    chat_id=chat_id,
                    user_id=new_member.id,
                    revoke_messages=True
                )
                
                # Move from pending to actual ban record
                database.add_ban_record(
                    user_id=new_member.id,
                    username=new_member.username or f"user_{new_member.id}",
                    chat_id=chat_id,
                    banned_by=pending_ban['banned_by'],
                    banned_by_username=pending_ban['banned_by_username'],
                    reason=pending_ban['reason']
                )
                
                # Remove from pending list (by ID if we have it, or by username)
                if pending_ban.get('user_id', 0) > 0:
                    database.remove_pending_ban(pending_ban['user_id'], chat_id)
                else:
                    # Remove by username for username-only bans
                    try:
                        conn = database.get_sync_connection()
                        conn.execute(
                            "DELETE FROM pending_bans WHERE LOWER(username) = ? AND chat_id = ?",
                            (new_member.username.lower(), chat_id)
                        )
                        conn.commit()
                        conn.close()
                    except Exception as e:
                        logger.error(f"Error removing username-based pending ban: {e}")
                
                # Log the auto-ban
                logger.info(f"Auto-banned user @{new_member.username} (ID: {new_member.id}) on join (pending ban executed)")
                
                # Optional: Send notification to admins (can be disabled)
                # await notify_admins_auto_ban(context, new_member, pending_ban)
                
            except Exception as e:
                logger.error(f"Failed to auto-ban user {new_member.id}: {e}")
                # Keep in pending list for retry later
                
    except Exception as e:
        logger.error(f"Error in handle_new_chat_member: {e}")


# ============================================================================
# INFO COMMAND - GroupHelpBot Style
# ============================================================================

async def info_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Display detailed information about a user
    Usage: /info (as reply) or /info @username or /info user_id
    """
    try:
        chat = update.effective_chat
        user = update.effective_user
        
        # Only work in groups
        if chat.type == 'private':
            await update.message.reply_text(
                "ℹ️ **Informacija**\n\n"
                "Ši komanda veikia tik grupėse.\n"
                "Naudokite: `/info` atsakydami į pranešimą arba `/info @username`",
                parse_mode='Markdown'
            )
            return
        
        # Check if user is admin
        if not await is_admin(update, context):
            await update.message.reply_text("❌ Tik administratoriai gali naudoti šią komandą.")
            return
        
        target_user = None
        target_user_id = None
        
        # Method 1: Reply to a message
        if update.message.reply_to_message:
            target_user = update.message.reply_to_message.from_user
            target_user_id = target_user.id
            logger.info(f"Info command: target from reply - {target_user_id}")
        
        # Method 2: Username or ID provided
        elif context.args:
            identifier = str(context.args[0])  # Convert to string in case it's parsed as int
            
            # Try to resolve username or ID
            resolved = await resolve_user(context, identifier, chat.id)
            
            if resolved:
                target_user_id = resolved.get('user_id')
                
                # Create a minimal user object from resolved data
                class ResolvedUser:
                    def __init__(self, data):
                        self.id = data.get('user_id')
                        self.username = data.get('username')
                        self.first_name = data.get('first_name', 'Unknown')
                        self.last_name = data.get('last_name')
                        self.is_bot = False
                
                target_user = ResolvedUser(resolved)
                logger.info(f"Info command: target resolved - {target_user_id}")
            else:
                await update.message.reply_text(
                    f"❌ Vartotojas `{identifier}` nerastas.\n\n"
                    "Naudokite:\n"
                    "• `/info` atsakydami į pranešimą\n"
                    "• `/info @username`\n"
                    "• `/info user_id`",
                    parse_mode='Markdown'
                )
                return
        else:
            await update.message.reply_text(
                "ℹ️ **Kaip naudoti /info**\n\n"
                "• Atsakykite į vartotojo pranešimą su `/info`\n"
                "• Arba naudokite: `/info @username`\n"
                "• Arba: `/info user_id`",
                parse_mode='Markdown'
            )
            return
        
        # Get additional info from database
        user_cache = database.get_user_by_id(target_user_id) if target_user_id else None
        
        # Build info message
        info_text = "👤 **Vartotojo informacija**\n\n"
        
        # Basic info
        if target_user:
            info_text += f"**ID:** `{target_user.id}`\n"
            
            if target_user.username:
                info_text += f"**Vartotojo vardas:** @{target_user.username}\n"
            
            name = target_user.first_name
            if target_user.last_name:
                name += f" {target_user.last_name}"
            info_text += f"**Vardas:** {name}\n"
            
            if hasattr(target_user, 'is_bot') and target_user.is_bot:
                info_text += f"**Tipas:** 🤖 Botas\n"
            else:
                info_text += f"**Tipas:** 👤 Vartotojas\n"
        
        # Try to get chat member status
        try:
            member = await context.bot.get_chat_member(chat.id, target_user_id)
            
            status_emoji = {
                'creator': '👑',
                'administrator': '⭐',
                'member': '👤',
                'restricted': '🔇',
                'left': '🚪',
                'kicked': '🚫'
            }
            
            status_text = {
                'creator': 'Savininkas',
                'administrator': 'Administratorius',
                'member': 'Narys',
                'restricted': 'Apribotas',
                'left': 'Išėjo',
                'kicked': 'Užblokuotas'
            }
            
            emoji = status_emoji.get(member.status, '❓')
            status = status_text.get(member.status, member.status)
            info_text += f"**Statusas:** {emoji} {status}\n"
            
            # Join date if available
            if hasattr(member, 'joined_date') and member.joined_date:
                join_date = member.joined_date.strftime("%Y-%m-%d %H:%M")
                info_text += f"**Prisijungė:** {join_date}\n"
        
        except Exception as e:
            logger.warning(f"Could not get chat member status: {e}")
            info_text += f"**Statusas:** ❓ Nežinomas\n"
        
        # Database info
        if user_cache:
            info_text += f"\n**📊 Duomenų bazės informacija:**\n"
            
            if user_cache.get('first_seen'):
                info_text += f"**Pirmas pamatytas:** {user_cache['first_seen']}\n"
            
            if user_cache.get('last_seen'):
                info_text += f"**Paskutinį kartą matytas:** {user_cache['last_seen']}\n"
            
            if user_cache.get('message_count'):
                info_text += f"**Pranešimų skaičius:** {user_cache['message_count']}\n"
        
        # Check warnings
        try:
            warnings = database.get_warnings(target_user_id, chat.id)
            if warnings:
                info_text += f"\n**⚠️ Įspėjimai:** {len(warnings)}/3\n"
        except:
            pass
        
        # Check if pending ban
        try:
            pending_ban = database.get_pending_ban(target_user_id, chat.id)
            if pending_ban:
                info_text += f"\n**🚫 Laukiantis užblokavimas:** Taip\n"
                info_text += f"**Priežastis:** {pending_ban.get('reason', 'Nenurodyta')}\n"
        except:
            pass
        
        # Check ban history
        try:
            ban_history = database.get_ban_history(target_user_id, chat.id)
            if ban_history:
                info_text += f"\n**📜 Užblokavimų istorija:** {len(ban_history)}\n"
        except:
            pass
        
        # Send info
        await update.message.reply_text(info_text, parse_mode='Markdown')
        logger.info(f"Info displayed for user {target_user_id} by admin {user.id}")
        
    except Exception as e:
        logger.error(f"Error in info_user: {e}", exc_info=True)
        await update.message.reply_text(
            f"❌ Klaida gaunant informaciją: {str(e)}",
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
    'lookup_user',
    'handle_new_chat_member',
    'info_user'
]

