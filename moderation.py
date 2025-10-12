#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Moderation system for OGbotas
"""

import logging
import telegram
from telegram import Update
from telegram.ext import ContextTypes
from typing import Optional
from database import database
from utils import SecurityValidator, safe_bot_operation
from config import ADMIN_CHAT_ID

logger = logging.getLogger(__name__)

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

async def resolve_username_to_id(context: ContextTypes.DEFAULT_TYPE, username_or_id: str, chat_id: int) -> Optional[int]:
    """Universal username resolver - tries multiple methods"""
    
    # Clean input
    clean_input = username_or_id.strip()
    
    # Try direct ID parsing first
    if clean_input.isdigit():
        user_id = int(clean_input)
        if user_id > 0:
            return user_id
    
    # Clean username (remove @)
    username = clean_input.lstrip('@').lower()
    if not username:
        return None
    
    logger.info(f"Resolving username: {username}")
    
    # Method 1: Check ban history first (most reliable for banned users)
    try:
        ban_records = database.get_ban_history(username=username)
        if ban_records:
            user_id = ban_records[0]['user_id']
            logger.info(f"Found {username} in ban history: {user_id}")
            return user_id
    except Exception as e:
        logger.warning(f"Error checking ban history: {e}")
    
    # Method 2: Check user cache
    try:
        user_info = database.get_user_by_username(username)
        if user_info:
            user_id = user_info['user_id']
            logger.info(f"Found {username} in user cache: {user_id}")
            return user_id
    except Exception as e:
        logger.warning(f"Error checking user cache: {e}")
    
    # Method 3: Try get_chat API call
    try:
        chat = await safe_bot_operation(context.bot.get_chat, f"@{username}")
        if chat and chat.id:
            user_id = chat.id
            logger.info(f"Found {username} via get_chat: {user_id}")
            # Store in cache
            database.store_user_info(user_id, username, chat.first_name, chat.last_name)
            return user_id
    except Exception as e:
        logger.debug(f"get_chat failed for {username}: {e}")
    
    # Method 4: Try without @ prefix
    try:
        chat = await safe_bot_operation(context.bot.get_chat, username)
        if chat and chat.id:
            user_id = chat.id
            logger.info(f"Found {username} via get_chat (no @): {user_id}")
            database.store_user_info(user_id, username, chat.first_name, chat.last_name)
            return user_id
    except Exception as e:
        logger.debug(f"get_chat without @ failed for {username}: {e}")
    
    # Method 5: Check chat administrators
    try:
        admins = await safe_bot_operation(context.bot.get_chat_administrators, chat_id)
        if admins:
            for admin in admins:
                if admin.user.username and admin.user.username.lower() == username:
                    user_id = admin.user.id
                    logger.info(f"Found {username} in chat admins: {user_id}")
                    database.store_user_info(user_id, username, admin.user.first_name, admin.user.last_name)
                    return user_id
    except Exception as e:
        logger.debug(f"Error checking chat administrators: {e}")
    
    logger.warning(f"Could not resolve username: {username}")
    return None

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ban user command with robust username resolution"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Tik adminai ir pagalbininkai gali naudoti šią komandą!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Naudojimas: /ban @username [priežastis]")
        return
    
    chat_id = update.effective_chat.id
    admin_id = update.effective_user.id
    admin_username = update.effective_user.username or f"User{admin_id}"
    
    target_input = context.args[0]
    reason = " ".join(context.args[1:]) if len(context.args) > 1 else "No reason provided"
    
    # Sanitize inputs
    reason = SecurityValidator.sanitize_text(reason)[:200]  # Limit reason length
    
    try:
        # Check if it's a reply to a message
        if update.message.reply_to_message:
            target_user = update.message.reply_to_message.from_user
            user_id = target_user.id
            username = target_user.username or f"User{user_id}"
            logger.info(f"Banning user from reply: {username} (ID: {user_id})")
        else:
            # Resolve username/ID
            user_id = await resolve_username_to_id(context, target_input, chat_id)
            if not user_id:
                await update.message.reply_text(f"❌ Negaliu rasti vartotojo ID pagal {target_input}")
                return
            username = target_input.lstrip('@')
        
        # Check if trying to ban admin
        if user_id == admin_id:
            await update.message.reply_text("❌ Negalite užbaninti savęs!")
            return
        
        if user_id == ADMIN_CHAT_ID:
            await update.message.reply_text("❌ Negalite užbaninti pagrindinio admin!")
            return
        
        # Execute ban
        success = await safe_bot_operation(context.bot.ban_chat_member, chat_id, user_id)
        if success:
            # Store ban record
            database.add_ban_record(user_id, username, chat_id, admin_id, admin_username, reason)
            
            # Escape markdown characters in the response
            safe_username = username.replace('*', '\\*').replace('_', '\\_').replace('`', '\\`')
            safe_reason = reason.replace('*', '\\*').replace('_', '\\_').replace('`', '\\`')
            
            await update.message.reply_text(
                f"✅ Vartotojas {safe_username} sėkmingai užbanintas\\!\n"
                f"👤 Admin: @{admin_username}\n"
                f"📝 Priežastis: {safe_reason}",
                parse_mode='MarkdownV2'
            )
            logger.info(f"User {username} (ID: {user_id}) banned by {admin_username} in chat {chat_id}")
        else:
            await update.message.reply_text(f"❌ Nepavyko užbaninti vartotojo {username}")
            
    except telegram.error.BadRequest as e:
        error_msg = str(e)
        if "User not found" in error_msg:
            await update.message.reply_text(f"❌ Vartotojas nerastas arba nėra grupės narys!")
        elif "Not enough rights" in error_msg:
            await update.message.reply_text("❌ Neturiu teisių baninti šį vartotoją!")
        else:
            # Escape special characters in error message
            safe_error = error_msg.replace('*', '\\*').replace('_', '\\_').replace('`', '\\`')
            await update.message.reply_text(f"❌ Klaida: {safe_error}")
        logger.error(f"BadRequest in ban_user: {e}")
    except Exception as e:
        await update.message.reply_text("❌ Įvyko nežinoma klaida!")
        logger.error(f"Error in ban_user: {e}")

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unban user command with GroupHelpBot-style functionality"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Tik adminai ir pagalbininkai gali naudoti šią komandą!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Naudojimas: /unban @username")
        return
    
    chat_id = update.effective_chat.id
    admin_id = update.effective_user.id
    admin_username = update.effective_user.username or f"User{admin_id}"
    
    target_input = context.args[0]
    
    try:
        # First try to find user in ban history (most reliable)
        username = target_input.lstrip('@').lower()
        user_id = None
        
        # Check ban history first
        ban_records = database.get_ban_history(username=username)
        if ban_records:
            # Find the most recent active ban
            for record in ban_records:
                if record['is_active']:
                    user_id = record['user_id']
                    break
            
            if not user_id and ban_records:
                # Use most recent ban even if not active
                user_id = ban_records[0]['user_id']
        
        # If not found in ban history, try username resolution
        if not user_id:
            user_id = await resolve_username_to_id(context, target_input, chat_id)
        
        if not user_id or user_id is None:
            await update.message.reply_text(f"❌ Negaliu rasti vartotojo ID pagal {target_input}")
            return
        
        # Execute unban
        success = await safe_bot_operation(context.bot.unban_chat_member, chat_id, user_id)
        if success:
            # Update ban records - mark as inactive
            try:
                conn = database.get_sync_connection()
                try:
                    conn.execute('''
                        UPDATE ban_history 
                        SET is_active = 0, unban_timestamp = datetime('now')
                        WHERE user_id = ? AND chat_id = ? AND is_active = 1
                    ''', (user_id, chat_id))
                    conn.commit()
                finally:
                    conn.close()
            except Exception as e:
                logger.error(f"Error updating ban history: {e}")
            
            # Escape markdown characters
            safe_username = username.replace('*', '\\*').replace('_', '\\_').replace('`', '\\`')
            
            await update.message.reply_text(
                f"✅ Vartotojas {safe_username} sėkmingai atbanintas\\!\n"
                f"👤 Admin: @{admin_username}",
                parse_mode='MarkdownV2'
            )
            logger.info(f"User {username} (ID: {user_id}) unbanned by {admin_username} in chat {chat_id}")
        else:
            await update.message.reply_text(f"❌ Nepavyko atbaninti vartotojo {username}")
            
    except telegram.error.BadRequest as e:
        error_msg = str(e)
        if "User not found" in error_msg:
            await update.message.reply_text(f"❌ Vartotojas nerastas!")
        elif "Not enough rights" in error_msg:
            await update.message.reply_text("❌ Neturiu teisių atbaninti šį vartotoją!")
        else:
            safe_error = error_msg.replace('*', '\\*').replace('_', '\\_').replace('`', '\\`')
            await update.message.reply_text(f"❌ Klaida: {safe_error}")
        logger.error(f"BadRequest in unban_user: {e}")
    except Exception as e:
        await update.message.reply_text("❌ Įvyko nežinoma klaida!")
        logger.error(f"Error in unban_user: {e}")

async def mute_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mute user command"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Tik adminai ir pagalbininkai gali naudoti šią komandą!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Naudojimas: /mute @username [laikas_minutėmis]")
        return
    
    chat_id = update.effective_chat.id
    admin_username = update.effective_user.username or f"User{update.effective_user.id}"
    
    target_input = context.args[0]
    mute_duration = 60  # Default 1 hour in minutes
    
    if len(context.args) > 1:
        try:
            mute_duration = int(context.args[1])
            if mute_duration <= 0 or mute_duration > 10080:  # Max 1 week
                mute_duration = 60
        except ValueError:
            mute_duration = 60
    
    try:
        # Check if it's a reply to a message
        if update.message.reply_to_message:
            target_user = update.message.reply_to_message.from_user
            user_id = target_user.id
            username = target_user.username or f"User{user_id}"
        else:
            # Resolve username/ID
            user_id = await resolve_username_to_id(context, target_input, chat_id)
            if not user_id or user_id is None:
                await update.message.reply_text(f"❌ Negaliu rasti vartotojo ID pagal {target_input}")
                return
            username = target_input.lstrip('@')
        
        # Execute mute (restrict permissions)
        from datetime import datetime, timedelta
        until_date = datetime.now() + timedelta(minutes=mute_duration)
        
        permissions = telegram.ChatPermissions(
            can_send_messages=False,
            can_send_media_messages=False,
            can_send_polls=False,
            can_send_other_messages=False,
            can_add_web_page_previews=False,
            can_change_info=False,
            can_invite_users=False,
            can_pin_messages=False
        )
        
        success = await safe_bot_operation(
            context.bot.restrict_chat_member,
            chat_id, user_id, permissions, until_date=until_date
        )
        
        if success:
            safe_username = username.replace('*', '\\*').replace('_', '\\_').replace('`', '\\`')
            await update.message.reply_text(
                f"🔇 Vartotojas {safe_username} nutildytas {mute_duration} min\\!\n"
                f"👤 Admin: @{admin_username}",
                parse_mode='MarkdownV2'
            )
            logger.info(f"User {username} (ID: {user_id}) muted for {mute_duration} minutes by {admin_username}")
        else:
            await update.message.reply_text(f"❌ Nepavyko nutildyti vartotojo {username}")
            
    except telegram.error.BadRequest as e:
        error_msg = str(e)
        if "User not found" in error_msg:
            await update.message.reply_text(f"❌ Vartotojas nerastas arba nėra grupės narys!")
        elif "Not enough rights" in error_msg:
            await update.message.reply_text("❌ Neturiu teisių nutildyti šį vartotoją!")
        else:
            safe_error = error_msg.replace('*', '\\*').replace('_', '\\_').replace('`', '\\`')
            await update.message.reply_text(f"❌ Klaida: {safe_error}")
        logger.error(f"BadRequest in mute_user: {e}")
    except Exception as e:
        await update.message.reply_text("❌ Įvyko nežinoma klaida!")
        logger.error(f"Error in mute_user: {e}")

async def unmute_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Unmute user command"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Tik adminai ir pagalbininkai gali naudoti šią komandą!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Naudojimas: /unmute @username")
        return
    
    chat_id = update.effective_chat.id
    admin_username = update.effective_user.username or f"User{update.effective_user.id}"
    
    target_input = context.args[0]
    
    try:
        # Check if it's a reply to a message
        if update.message.reply_to_message:
            target_user = update.message.reply_to_message.from_user
            user_id = target_user.id
            username = target_user.username or f"User{user_id}"
        else:
            # Resolve username/ID
            user_id = await resolve_username_to_id(context, target_input, chat_id)
            if not user_id or user_id is None:
                await update.message.reply_text(f"❌ Negaliu rasti vartotojo ID pagal {target_input}")
                return
            username = target_input.lstrip('@')
        
        # Restore permissions
        permissions = telegram.ChatPermissions(
            can_send_messages=True,
            can_send_media_messages=True,
            can_send_polls=True,
            can_send_other_messages=True,
            can_add_web_page_previews=True,
            can_change_info=False,
            can_invite_users=True,
            can_pin_messages=False
        )
        
        success = await safe_bot_operation(
            context.bot.restrict_chat_member,
            chat_id, user_id, permissions
        )
        
        if success:
            safe_username = username.replace('*', '\\*').replace('_', '\\_').replace('`', '\\`')
            await update.message.reply_text(
                f"🔊 Vartotojas {safe_username} atšauktas\\!\n"
                f"👤 Admin: @{admin_username}",
                parse_mode='MarkdownV2'
            )
            logger.info(f"User {username} (ID: {user_id}) unmuted by {admin_username}")
        else:
            await update.message.reply_text(f"❌ Nepavyko atšaukti vartotojo {username}")
            
    except telegram.error.BadRequest as e:
        error_msg = str(e)
        if "User not found" in error_msg:
            await update.message.reply_text(f"❌ Vartotojas nerastas arba nėra grupės narys!")
        elif "Not enough rights" in error_msg:
            await update.message.reply_text("❌ Neturiu teisių atšaukti šį vartotoją!")
        else:
            safe_error = error_msg.replace('*', '\\*').replace('_', '\\_').replace('`', '\\`')
            await update.message.reply_text(f"❌ Klaida: {safe_error}")
        logger.error(f"BadRequest in unmute_user: {e}")
    except Exception as e:
        await update.message.reply_text("❌ Įvyko nežinoma klaida!")
        logger.error(f"Error in unmute_user: {e}")

async def lookup_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lookup and cache user information (admin only)"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Tik adminai gali naudoti šią komandą!")
        return
    
    if not context.args:
        await update.message.reply_text("❌ Naudojimas: /lookup @username")
        return
    
    chat_id = update.effective_chat.id
    target_input = context.args[0]
    
    try:
        user_id = await resolve_username_to_id(context, target_input, chat_id)
        if user_id and user_id is not None:
            # Try to get additional info
            try:
                chat = await safe_bot_operation(context.bot.get_chat, user_id)
                if chat:
                    info_text = f"✅ Vartotojas rastas:\n"
                    info_text += f"👤 ID: `{user_id}`\n"
                    if chat.username:
                        info_text += f"📝 Username: @{chat.username}\n"
                    if chat.first_name:
                        info_text += f"🏷️ Vardas: {chat.first_name}\n"
                    if chat.last_name:
                        info_text += f"🏷️ Pavardė: {chat.last_name}\n"
                    
                    await update.message.reply_text(info_text, parse_mode='Markdown')
                else:
                    await update.message.reply_text(f"✅ Vartotojo ID: `{user_id}`", parse_mode='Markdown')
            except Exception as e:
                await update.message.reply_text(f"✅ Vartotojo ID: `{user_id}`\n❌ Nepavyko gauti papildomos informacijos", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Negaliu rasti vartotojo: {target_input}")
    
    except Exception as e:
        await update.message.reply_text("❌ Įvyko klaida ieškant vartotojo!")
        logger.error(f"Error in lookup_user: {e}")
