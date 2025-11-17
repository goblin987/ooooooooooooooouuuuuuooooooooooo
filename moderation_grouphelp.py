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


async def has_permission(update: Update, context: ContextTypes.DEFAULT_TYPE, permission: str, user_id: int = None) -> bool:
    """
    Check if user has a specific permission
    
    Args:
        permission: One of 'ban', 'mute', 'warn', 'delete'
        user_id: Optional user ID to check (defaults to update.effective_user.id)
    
    Returns:
        True if user is bot owner, Telegram admin, or helper with the permission
    """
    try:
        check_user_id = user_id or update.effective_user.id
        chat_id = update.effective_chat.id
        
        if not check_user_id:
            return False
        
        # Bot owner always has all permissions
        if check_user_id == ADMIN_CHAT_ID:
            return True
        
        # Check if user is Telegram admin or creator (they have all permissions)
        try:
            member = await safe_bot_operation(context.bot.get_chat_member, chat_id, check_user_id)
            if member and member.status in ['creator', 'administrator']:
                return True
        except Exception as e:
            logger.error(f"Error checking Telegram admin status: {e}")
        
        # Check if helper has the specific permission
        return database.has_helper_permission(chat_id, check_user_id, permission)
        
    except Exception as e:
        logger.error(f"Error checking permission '{permission}': {e}")
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
    
    # Method 5: Try get_chat_member with username (AGGRESSIVE FETCH)
    # This is what GroupHelp probably uses!
    try:
        logger.info(f"Attempting get_chat_member for @{username}...")
        # Try to get member info from the chat directly
        # This works if user is CURRENTLY in the group
        try:
            # First try to resolve the username to an ID
            chat = await context.bot.get_chat(f"@{username}")
            if chat.id > 0:  # It's a user (not a channel/group)
                # Now try to get their membership in THIS group
                member = await context.bot.get_chat_member(chat_id, chat.id)
                if member:
                    # Cache for future use
                    database.store_user_info(
                        member.user.id,
                        member.user.username or f"user_{member.user.id}",
                        member.user.first_name,
                        member.user.last_name
                    )
                    logger.info(f"✅ Found @{username} in group via get_chat_member!")
                    return {
                        'user_id': member.user.id,
                        'username': member.user.username or f"user_{member.user.id}",
                        'first_name': member.user.first_name,
                        'last_name': member.user.last_name
                    }
        except Exception as e:
            logger.debug(f"get_chat_member failed for @{username}: {e}")
    except Exception as e:
        logger.debug(f"Member fetch failed: {e}")
    
    # Method 6: All resolution methods exhausted
    # This is a Telegram API limitation - can't search all members by username
    logger.warning(f"Could not resolve user: {username}")
    logger.info(f"User @{username} not found after trying all resolution methods.")
    logger.info(f"Solutions: 1) Use /cache @{username} first, 2) Reply to their message, 3) Use their user_id")
    return None


# ============================================================================
# CACHE COMMAND - Manually cache users before moderation
# ============================================================================

async def cache_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Force cache a user by username or ID
    Usage: /cache @username OR /cache 123456789
    
    This is ESSENTIAL for large groups (10k+ members) where autocomplete doesn't work!
    Use this to ban users who never sent messages.
    """
    if not await is_admin(update, context):
        await update.message.reply_text("⛔ Ši komanda tik administratoriams!")
        return
    
    if update.effective_chat.type == 'private':
        await update.message.reply_text("⚠️ Ši komanda veikia tik grupėse!")
        return
    
    if not context.args:
        message_text = (
            "💡 KAIP NAUDOTI /cache\n\n"
            "Naudokite dideliuose grupėse (10k+ narių)\n"
            "kai reikia uždrausti tylų vartotoją!\n\n"
            "Pavyzdžiai:\n"
            "/cache @blogas_useris\n"
            "/cache 987654321\n\n"
            "Po to:\n"
            "/ban @blogas_useris priežastis"
        )
        await update.message.reply_text(message_text)
        return
    
    chat_id = update.effective_chat.id
    target_input = context.args[0].lstrip('@')
    
    # Try to resolve the user first with existing methods
    user_info = await resolve_user(context, target_input, chat_id)
    
    if user_info:
        message_text = (
            f"✅ Vartotojas jau užkešuotas\n\n"
            f"👤 {user_info.get('first_name', 'N/A')}\n"
            f"🆔 {user_info['user_id']}\n"
            f"📛 @{user_info['username']}\n\n"
            f"Galite naudoti: /ban @{user_info['username']}"
        )
        await update.message.reply_text(message_text)
        return
    
    # If not found, try to fetch from Telegram API using getChatMember
    # This works if:
    # 1. User has interacted with the group in any way (even just joined)
    # 2. Bot has been in the group when that happened
    try:
        # For username-based lookup
        if not target_input.isdigit():
            # Try using get_chat to force Telegram to resolve username
            logger.info(f"Attempting to fetch @{target_input} from Telegram API...")
            
            try:
                # This might work for some users
                chat = await context.bot.get_chat(f"@{target_input}")
                if chat.id > 0:  # It's a user
                    # Now try to get their member info in this group
                    member = await context.bot.get_chat_member(chat_id, chat.id)
                    
                    # Cache the user!
                    database.store_user_info(
                        member.user.id,
                        member.user.username or f"user_{member.user.id}",
                        member.user.first_name,
                        member.user.last_name
                    )
                    
                    message_text = (
                        f"✅ Vartotojas užkešuotas\n\n"
                        f"👤 {member.user.first_name}\n"
                        f"🆔 {member.user.id}\n"
                        f"📛 @{member.user.username or 'N/A'}\n"
                        f"📊 {member.status}\n\n"
                        f"Galite naudoti: /ban @{member.user.username}"
                    )
                    await update.message.reply_text(message_text)
                    logger.info(f"✅ Successfully cached @{target_input} (ID: {member.user.id})")
                    return
            except Exception as e:
                logger.debug(f"Username-based cache failed: {e}")
        
        # For ID-based lookup
        else:
            user_id = int(target_input)
            logger.info(f"Attempting to fetch user {user_id} from Telegram API...")
            
            member = await context.bot.get_chat_member(chat_id, user_id)
            
            # Cache the user!
            database.store_user_info(
                member.user.id,
                member.user.username or f"user_{member.user.id}",
                member.user.first_name,
                member.user.last_name
            )
            
            message_text = (
                f"✅ Vartotojas užkešuotas\n\n"
                f"👤 {member.user.first_name}\n"
                f"🆔 {member.user.id}\n"
                f"📛 @{member.user.username or 'N/A'}\n"
                f"📊 {member.status}\n\n"
                f"Galite naudoti: /ban @{member.user.username}"
            )
            await update.message.reply_text(message_text)
            logger.info(f"✅ Successfully cached user {user_id}")
            return
            
    except Exception as e:
        logger.error(f"Failed to cache user {target_input}: {e}")
        message_text = (
            f"❌ NEPAVYKO UŽKEŠUOTI VARTOTOJO\n\n"
            f"👤 Įvestis: {target_input}\n"
            f"❌ Klaida: {str(e)}\n\n"
            f"Galimos priežastys:\n"
            f"• Vartotojas niekada nebuvo šioje grupėje\n"
            f"• Neteisingas username arba ID\n"
            f"• Vartotojas užblokavo botą\n\n"
            f"Alternatyvos:\n"
            f"• Paprašykite vartotojo parašyti bent vieną žinutę\n"
            f"• Atsakykite į jo žinutę su /ban\n"
            f"• Naudokite /ban [user_id] jei žinote ID"
        )
        await update.message.reply_text(message_text)


# ============================================================================
# BAN COMMAND (GroupHelpBot Style - Works even if user not in group!)
# ============================================================================

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Ban user - GroupHelpBot style
    Works even if user is not currently in the group!
    """
    # Check ban permission
    if not await has_permission(update, context, 'ban'):
        await update.message.reply_text("❌ Neturite leidimo uždrausti vartotojus!")
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
    
    # No arguments and no reply - GroupHelp style
    else:
        await update.message.reply_text(
            "How to use /ban:\n"
            "• Reply to user + /ban [reason]\n"
            "• /ban @username [reason]\n"
            "• /ban [user_id] [reason]"
        )
        return
    
    if not user_info or not user_info.get('user_id'):
        # User not found - TRY AUTOMATIC CACHING FIRST!
        logger.info(f"User not found in cache - attempting automatic cache before pending ban...")
        clean_input = target_input.strip().lstrip('@')
        
        # TRY TO CACHE AUTOMATICALLY using getChatMember
        try:
            # Try with username
            if not clean_input.isdigit():
                try:
                    chat = await context.bot.get_chat(f"@{clean_input}")
                    if chat.id > 0:
                        member = await context.bot.get_chat_member(chat_id, chat.id)
                        database.store_user_info(
                            member.user.id,
                            member.user.username or f"user_{member.user.id}",
                            member.user.first_name,
                            member.user.last_name
                        )
                        # Success! Now use this info
                        user_info = {
                            'user_id': member.user.id,
                            'username': member.user.username or f"user_{member.user.id}",
                            'first_name': member.user.first_name,
                            'last_name': member.user.last_name
                        }
                        logger.info(f"✅ Auto-cached @{clean_input} (ID: {member.user.id}) - proceeding with ban")
                except Exception as e:
                    logger.debug(f"Auto-cache by username failed: {e}")
            
            # Try with user ID
            else:
                user_id = int(clean_input)
                member = await context.bot.get_chat_member(chat_id, user_id)
                database.store_user_info(
                    member.user.id,
                    member.user.username or f"user_{member.user.id}",
                    member.user.first_name,
                    member.user.last_name
                )
                user_info = {
                    'user_id': member.user.id,
                    'username': member.user.username or f"user_{member.user.id}",
                    'first_name': member.user.first_name,
                    'last_name': member.user.last_name
                }
                logger.info(f"✅ Auto-cached user {user_id} - proceeding with ban")
                
        except Exception as e:
            logger.debug(f"Auto-cache failed: {e}")
    
    # STILL not found after auto-cache attempt? Add to pending bans
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
            # Username-only ban - Clean simple style
            message_text = (
                f"⚠️ Vartotojas nerastas grupėje\n\n"
                f"@{username} pridėtas į laukiančių uždraudimų sąrašą.\n"
                f"Bus automatiškai uždraustas prisijungus.\n\n"
                f"Uždrausti dabar:\n"
                f"• Atsakyti į žinutę: /ban\n"
                f"• /cache @{username} tada /ban"
            )
            await update.message.reply_text(message_text)
        else:
            # User ID ban - Clean simple style
            message_text = (
                f"⏳ Vartotojas pridėtas į uždraudimų sąrašą\n\n"
                f"👤 @{username}\n"
                f"🆔 {user_id}\n"
                f"👮 {admin_user.first_name}\n"
                f"📝 {reason}\n"
                f"⏰ {timestamp}\n\n"
                f"Bus automatiškai uždraustas prisijungus."
            )
            await update.message.reply_text(message_text)
        
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
        
        # Success message - GroupHelp style (simple & clean)
        await update.message.reply_text(
            f"🚫 User Banned\n\n"
            f"User: {full_name} (@{username})\n"
            f"ID: {user_id}\n"
            f"Banned by: {admin_user.first_name}\n"
            f"Reason: {reason}"
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
            
            # Success message - GroupHelp style
            await update.message.reply_text(
                f"⏳ User Added to Pending Bans\n\n"
                f"User: {full_name} (@{username})\n"
                f"ID: {user_id}\n"
                f"Banned by: {admin_user.first_name}\n"
                f"Reason: {reason}\n\n"
                f"✅ User will be automatically banned when they join the group."
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
    """Unban user - GroupHelpBot style - works even if user is not in group!"""
    
    if not await has_permission(update, context, 'ban'):
        await update.message.reply_text("❌ Neturite leidimo atblokuoti vartotojus!")
        return
    
    if update.effective_chat.type == 'private':
        await update.message.reply_text("❌ This command only works in groups!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "How to use /unban:\n"
            "• /unban @username\n"
            "• /unban [user_id]"
        )
        return
    
    chat_id = update.effective_chat.id
    admin_user = update.effective_user
    target_input = context.args[0].strip().lstrip('@')
    
    user_id = None
    username = None
    full_name = "User"
    
    # Method 1: Direct user_id (most reliable for banned users)
    if target_input.isdigit():
        user_id = int(target_input)
        # Try to get user info from cache/ban history
        try:
            user_data = database.get_user_by_id(user_id)
            if user_data:
                username = user_data.get('username', f'user_{user_id}')
                full_name = f"{user_data.get('first_name', 'User')} {user_data.get('last_name', '')}".strip()
            else:
                # Check ban history
                ban_records = database.get_ban_history_for_user(user_id, chat_id)
                if ban_records:
                    username = ban_records[0].get('username', f'user_{user_id}')
                    full_name = f"{ban_records[0].get('first_name', 'User')} {ban_records[0].get('last_name', '')}".strip()
                else:
                    username = f'user_{user_id}'
        except:
            username = f'user_{user_id}'
    
    # Method 2: Username lookup (from cache or ban history)
    else:
        # Try cache first
        user_data = database.get_user_by_username(target_input)
        if user_data:
            user_id = user_data['user_id']
            username = user_data.get('username', target_input)
            full_name = f"{user_data.get('first_name', 'User')} {user_data.get('last_name', '')}".strip()
        else:
            # Try ban history
            try:
                conn = database.get_sync_connection()
                cursor = conn.execute('''
                    SELECT DISTINCT user_id, username, first_name, last_name
                    FROM ban_history
                    WHERE chat_id = ? AND LOWER(username) = LOWER(?)
                    ORDER BY timestamp DESC LIMIT 1
                ''', (chat_id, target_input))
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    user_id = row[0]
                    username = row[1] or target_input
                    full_name = f"{row[2] or 'User'} {row[3] or ''}".strip()
            except Exception as e:
                logger.error(f"Error checking ban history: {e}")
    
    if not user_id:
        await update.message.reply_text(f"❌ Could not find user: {target_input}\n\nTry using their user ID instead.")
        return
    
    username = username or f'user_{user_id}'
    
    # Execute unban
    try:
        await context.bot.unban_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            only_if_banned=True
        )
        
        # Success message - GroupHelp style
        await update.message.reply_text(
            f"✅ User Unbanned\n\n"
            f"User: {full_name} (@{username})\n"
            f"ID: {user_id}\n"
            f"Unbanned by: {admin_user.first_name}"
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
    
    if not await has_permission(update, context, 'mute'):
        await update.message.reply_text("❌ Neturite leidimo nutildyti vartotojus!")
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
    
    # Set permissions (restrict all) - Updated for python-telegram-bot v20+
    permissions = ChatPermissions(
        can_send_messages=False,
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
        
        # Success message - GroupHelp style
        duration_text = f"{duration_minutes} minutes" if duration_minutes else "indefinitely"
        
        await update.message.reply_text(
            f"🔇 User Muted\n\n"
            f"User: {full_name} (@{username})\n"
            f"ID: {user_id}\n"
            f"Muted by: {admin_user.first_name}\n"
            f"Duration: {duration_text}\n"
            f"Reason: {reason}"
        )
        
        logger.info(f"Muted user {user_id} in chat {chat_id} for {duration_text}")
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error muting user: {str(e)}")
        logger.error(f"Error in mute_user: {e}")


# ============================================================================
# UNMUTE COMMAND (GroupHelpBot Style)
# ============================================================================

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unmute user - GroupHelpBot style - works even if user left the group!"""
    
    if not await has_permission(update, context, 'mute'):
        await update.message.reply_text("❌ Neturite leidimo panaikinti nutildymą!")
        return
    
    if update.effective_chat.type == 'private':
        await update.message.reply_text("❌ This command only works in groups!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "How to use /unmute:\n"
            "• /unmute @username\n"
            "• /unmute [user_id]"
        )
        return
    
    chat_id = update.effective_chat.id
    admin_user = update.effective_user
    target_input = context.args[0].strip().lstrip('@')
    
    user_id = None
    username = None
    full_name = "User"
    
    # Method 1: Direct user_id (most reliable for muted users who left)
    if target_input.isdigit():
        user_id = int(target_input)
        # Try to get user info from cache
        try:
            user_data = database.get_user_by_id(user_id)
            if user_data:
                username = user_data.get('username', f'user_{user_id}')
                full_name = f"{user_data.get('first_name', 'User')} {user_data.get('last_name', '')}".strip()
            else:
                username = f'user_{user_id}'
        except:
            username = f'user_{user_id}'
    
    # Method 2: Username lookup (from cache)
    else:
        user_data = database.get_user_by_username(target_input)
        if user_data:
            user_id = user_data['user_id']
            username = user_data.get('username', target_input)
            full_name = f"{user_data.get('first_name', 'User')} {user_data.get('last_name', '')}".strip()
    
    if not user_id:
        await update.message.reply_text(f"❌ Could not find user: {target_input}\n\nTry using their user ID instead.")
        return
    
    username = username or f'user_{user_id}'
    
    # Restore permissions - Updated for python-telegram-bot v20+
    permissions = ChatPermissions(
        can_send_messages=True,
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
        
        # Success message - GroupHelp style
        await update.message.reply_text(
            f"✅ User Unmuted\n\n"
            f"User: {full_name} (@{username})\n"
            f"ID: {user_id}\n"
            f"Unmuted by: {admin_user.first_name}"
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
    """
    Handle new chat members - cache them and auto-ban if in pending list
    THIS IS THE KEY: Cache users when they JOIN so we can find them by username later!
    """
    try:
        new_member = update.chat_member.new_chat_member.user
        chat_id = update.effective_chat.id
        
        # CRITICAL: Cache the user immediately when they join!
        # This allows /ban @username to work even if they never sent a message
        try:
            database.store_user_info(
                new_member.id,
                new_member.username or f"user_{new_member.id}",
                new_member.first_name,
                new_member.last_name
            )
            logger.info(f"✅ Cached new member: @{new_member.username or new_member.id} (ID: {new_member.id})")
        except Exception as e:
            logger.error(f"Failed to cache new member: {e}")
        
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


# ============================================================================
# HELPER MANAGEMENT COMMANDS
# ============================================================================

async def add_helper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add a helper to the group - bot owner and Telegram admins can do this"""
    
    # Check if user is bot owner or Telegram admin
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Bot owner can always add helpers
    if user_id != ADMIN_CHAT_ID:
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status not in ['creator', 'administrator']:
                await update.message.reply_text("❌ Tik administratoriai gali pridėti helperius!")
                return
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            await update.message.reply_text("❌ Klaida tikrinant teises!")
            return
    
    if update.effective_chat.type == 'private':
        await update.message.reply_text("❌ Ši komanda veikia tik grupėse!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Naudojimas: /addhelper @username\n\n"
            "Pavyzdys: /addhelper @jonas"
        )
        return
    
    # Parse username
    username = context.args[0].lstrip('@')
    
    # Resolve user
    user_info = await resolve_user(context, username, chat_id)
    
    if not user_info:
        await update.message.reply_text(
            f"❌ Vartotojas @{username} nerastas!\n\n"
            "💡 Patarimas:\n"
            "Vartotojas turi parašyti bent vieną žinutę grupėje\n"
            "arba naudokite /cache @{username} pirmiausia."
        )
        return
    
    helper_id = user_info['user_id']
    helper_username = user_info['username']
    
    # Check if already a helper
    try:
        conn = database.get_sync_connection()
        try:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM helpers WHERE chat_id = ? AND user_id = ?",
                (chat_id, helper_id)
            )
            if cursor.fetchone()[0] > 0:
                await update.message.reply_text(f"❌ @{helper_username} jau yra helperis!")
                return
            
            # Add helper with default permissions
            conn.execute('''
                INSERT INTO helpers (chat_id, user_id, username, added_by, added_at)
                VALUES (?, ?, ?, ?, datetime('now'))
            ''', (chat_id, helper_id, helper_username, user_id))
            conn.commit()
            
            await update.message.reply_text(
                f"✅ Helperis pridėtas!\n\n"
                f"👤 @{helper_username}\n"
                f"🆔 {helper_id}\n\n"
                f"Leidimai (pagal nutylėjimą):\n"
                f"✅ Ban\n"
                f"✅ Mute\n"
                f"✅ Warn\n"
                f"✅ Delete\n\n"
                f"Valdyti leidimus: /admin → 👥 Helpers"
            )
            logger.info(f"Added helper @{helper_username} (ID: {helper_id}) to chat {chat_id}")
            
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error adding helper: {e}")
        await update.message.reply_text(f"❌ Klaida pridedant helperį: {str(e)}")


async def remove_helper(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove a helper from the group - bot owner and Telegram admins can do this"""
    
    # Check if user is bot owner or Telegram admin
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    
    # Bot owner can always remove helpers
    if user_id != ADMIN_CHAT_ID:
        try:
            member = await context.bot.get_chat_member(chat_id, user_id)
            if member.status not in ['creator', 'administrator']:
                await update.message.reply_text("❌ Tik administratoriai gali pašalinti helperius!")
                return
        except Exception as e:
            logger.error(f"Error checking admin status: {e}")
            await update.message.reply_text("❌ Klaida tikrinant teises!")
            return
    
    if update.effective_chat.type == 'private':
        await update.message.reply_text("❌ Ši komanda veikia tik grupėse!")
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ Naudojimas: /removehelper @username\n\n"
            "Pavyzdys: /removehelper @jonas"
        )
        return
    
    # Parse username
    username = context.args[0].lstrip('@')
    
    # Resolve user
    user_info = await resolve_user(context, username, chat_id)
    
    if not user_info:
        await update.message.reply_text(f"❌ Vartotojas @{username} nerastas!")
        return
    
    helper_id = user_info['user_id']
    helper_username = user_info['username']
    
    # Remove helper
    try:
        conn = database.get_sync_connection()
        try:
            cursor = conn.execute(
                "DELETE FROM helpers WHERE chat_id = ? AND user_id = ?",
                (chat_id, helper_id)
            )
            
            if cursor.rowcount == 0:
                await update.message.reply_text(f"❌ @{helper_username} nėra helperis!")
                return
            
            conn.commit()
            
            await update.message.reply_text(
                f"✅ Helperis pašalintas!\n\n"
                f"👤 @{helper_username}"
            )
            logger.info(f"Removed helper @{helper_username} (ID: {helper_id}) from chat {chat_id}")
            
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error removing helper: {e}")
        await update.message.reply_text(f"❌ Klaida šalinant helperį: {str(e)}")


async def delete_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Delete a message by replying to it with /delete - requires 'delete' permission"""
    
    # Check delete permission
    if not await has_permission(update, context, 'delete'):
        await update.message.reply_text("❌ Neturite leidimo trinti žinutes!")
        return
    
    if update.effective_chat.type == 'private':
        await update.message.reply_text("❌ Ši komanda veikia tik grupėse!")
        return
    
    # Check if replying to a message
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Atsakykite į žinutę, kurią norite ištrinti!")
        return
    
    chat_id = update.effective_chat.id
    message_to_delete = update.message.reply_to_message.message_id
    command_message = update.message.message_id
    
    try:
        # Delete the target message
        await context.bot.delete_message(chat_id=chat_id, message_id=message_to_delete)
        # Delete the command message too
        await context.bot.delete_message(chat_id=chat_id, message_id=command_message)
        logger.info(f"Helper {update.effective_user.id} deleted message {message_to_delete} in chat {chat_id}")
    except Exception as e:
        logger.error(f"Error deleting message: {e}")
        await update.message.reply_text(f"❌ Nepavyko ištrinti žinutės: {str(e)}")


# Export functions
__all__ = [
    'is_admin',
    'has_permission',
    'resolve_user',
    'ban_user',
    'unban_user',
    'mute_user',
    'unmute_user',
    'lookup_user',
    'handle_new_chat_member',
    'info_user',
    'add_helper',
    'remove_helper',
    'delete_message_command'
]

