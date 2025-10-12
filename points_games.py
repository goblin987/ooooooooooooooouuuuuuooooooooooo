#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Points Games - PvP betting with saved points (NO real money)
Exact same UI as crypto games but uses points balance
"""

import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import database

logger = logging.getLogger(__name__)


def get_user_points(user_id: int) -> int:
    """Get user's saved points (NOT crypto balance)"""
    try:
        conn = database.get_sync_connection()
        cursor = conn.execute(
            "SELECT points FROM users WHERE user_id = ?",
            (user_id,)
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0
    except Exception as e:
        logger.error(f"Error getting points: {e}")
        return 0


def update_user_points(user_id: int, points: int) -> bool:
    """Update user's saved points"""
    try:
        conn = database.get_sync_connection()
        conn.execute(
            "INSERT OR REPLACE INTO users (user_id, points) VALUES (?, ?)",
            (user_id, points)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error updating points: {e}")
        return False


def user_has_points(user_id: int) -> bool:
    """Check if user exists in points system"""
    try:
        conn = database.get_sync_connection()
        cursor = conn.execute(
            "SELECT user_id FROM users WHERE user_id = ?",
            (user_id,)
        )
        result = cursor.fetchone()
        conn.close()
        return result is not None
    except Exception as e:
        logger.error(f"Error checking user points: {e}")
        return False


# ============================================================================
# DICE2 COMMAND (PvP with Points - Same UI as crypto games)
# ============================================================================

async def dice2_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a dice game with POINTS (not crypto) - PvP only"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    args = context.args

    if not user_has_points(user_id):
        await update.message.reply_text("You don't have any points yet! Earn points by being active in the group.")
        return

    if not args:
        points = get_user_points(user_id)
        await update.message.reply_text(
            f"🎲 **Dice Game (Points - PvP)**\n\n"
            f"Your Points: {points}\n\n"
            f"**Usage:** `/dice2 <points>`\n"
            f"**Example:** `/dice2 100`\n\n"
            f"_Note: This uses saved points (not crypto) and is Player vs Player only!_",
            parse_mode='Markdown'
        )
        return

    try:
        amount = int(args[0])
        if amount <= 0:
            raise ValueError("Bet must be positive.")
        balance = get_user_points(user_id)
        if amount > balance:
            await update.message.reply_text(f"Insufficient points! You have {balance} points.")
            return
        if (chat_id, user_id) in context.bot_data.get('user_games_points', {}):
            await update.message.reply_text("You are already in a game!")
            return
        
        # Initialize setup state (same as crypto games)
        setup = {
            'initiator': user_id,
            'bet': amount,
            'state': 'mode_selection',
            'message_id': None
        }
        context.user_data['dice2_setup'] = setup

        keyboard = [
            [InlineKeyboardButton("🎲 Normal Mode", callback_data="dice2_mode_normal")],
            [InlineKeyboardButton("🎲 Double Roll", callback_data="dice2_mode_double")],
            [InlineKeyboardButton("🎲 Crazy Mode", callback_data="dice2_mode_crazy")],
            [InlineKeyboardButton("ℹ️ Mode Guide", callback_data="dice2_mode_guide"),
             InlineKeyboardButton("❌ Cancel", callback_data="dice2_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = await update.message.reply_text("🎲 Choose the game mode:", reply_markup=reply_markup)
        setup['message_id'] = message.message_id

    except ValueError as e:
        await update.message.reply_text(f"Invalid bet amount: {str(e)}. Use a positive number.")


# ============================================================================
# POINTS BALANCE COMMAND
# ============================================================================

async def points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check saved points balance (separate from crypto)"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    points = get_user_points(user_id)
    
    text = (
        f"💎 **Points Balance**\n\n"
        f"👤 User: @{username}\n"
        f"💰 Points: {points}\n\n"
        f"_These are reward points, separate from crypto balance._\n\n"
        f"**Play with Points:**\n"
        f"• `/dice2 <points>` - Dice PvP game\n\n"
        f"**Earn Points:**\n"
        f"• Be active in the group\n"
        f"• Complete tasks\n"
        f"• Admin rewards"
    )
    
    await update.message.reply_text(text, parse_mode='Markdown')


# ============================================================================
# DICE2 BUTTON HANDLER (Same pattern as crypto games)
# ============================================================================

async def handle_dice2_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle dice2 button callbacks - same UI flow as crypto games"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data

    if not data.startswith('dice2_'):
        return False

    setup_key = 'dice2_setup'
    
    # Handle setup phase
    if setup_key in context.user_data:
        setup = context.user_data[setup_key]
        if setup['initiator'] != user_id or setup['message_id'] != query.message.message_id:
            await query.answer("This is not your game setup!")
            return True

        # Mode guide
        if data == "dice2_mode_guide":
            guide_text = (
                "🎲 **Normal Mode**: Roll one die, highest number wins the round.\n\n"
                "🎲 **Double Roll**: Roll two dice, highest sum wins the round.\n\n"
                "🎲 **Crazy Mode**: Roll one die, lowest number (inverted: 6=1, 1=6) wins the round."
            )
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="dice2_back")]]
            await query.edit_message_text(guide_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return True

        # Back button
        elif data == "dice2_back":
            keyboard = [
                [InlineKeyboardButton("🎲 Normal Mode", callback_data="dice2_mode_normal")],
                [InlineKeyboardButton("🎲 Double Roll", callback_data="dice2_mode_double")],
                [InlineKeyboardButton("🎲 Crazy Mode", callback_data="dice2_mode_crazy")],
                [InlineKeyboardButton("ℹ️ Mode Guide", callback_data="dice2_mode_guide"),
                 InlineKeyboardButton("❌ Cancel", callback_data="dice2_cancel")]
            ]
            await query.edit_message_text("🎲 Choose the game mode:", reply_markup=InlineKeyboardMarkup(keyboard))
            return True

        # Cancel
        elif data == "dice2_cancel":
            del context.user_data[setup_key]
            await query.edit_message_text("❌ Game setup cancelled.")
            return True

        # Mode selection
        elif data.startswith("dice2_mode_") and data != "dice2_mode_guide":
            mode = data.split('_')[2]
            context.user_data['dice2_mode'] = mode
            keyboard = [
                [InlineKeyboardButton("🏆 First to 1 point", callback_data="dice2_points_1")],
                [InlineKeyboardButton("🏅 First to 2 points", callback_data="dice2_points_2")],
                [InlineKeyboardButton("🥇 First to 3 points", callback_data="dice2_points_3")],
                [InlineKeyboardButton("❌ Cancel", callback_data="dice2_cancel")]
            ]
            await query.edit_message_text("🎲 Choose points to win:", reply_markup=InlineKeyboardMarkup(keyboard))
            return True

        # Points selection
        elif data.startswith("dice2_points_"):
            points = int(data.split('_')[2])
            context.user_data['dice2_points'] = points
            bet = setup['bet']
            mode = context.user_data['dice2_mode'].capitalize()
            text = (
                f"🎲 **Game confirmation**\n"
                f"Game: Dice (Points) 🎲\n"
                f"First to {points} points\n"
                f"Mode: {mode} Mode\n"
                f"Your bet: {bet} points\n"
                f"Win multiplier: 1.92x"
            )
            keyboard = [
                [InlineKeyboardButton("✅ Confirm", callback_data="dice2_confirm_setup"),
                 InlineKeyboardButton("❌ Cancel", callback_data="dice2_cancel")]
            ]
            await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return True

        # Confirm setup
        elif data == "dice2_confirm_setup":
            bet = setup['bet']
            mode = context.user_data['dice2_mode'].capitalize()
            points = context.user_data['dice2_points']
            username = query.from_user.username or "Someone"
            
            mode_description = {
                'normal': "Roll one die, highest number wins the round.",
                'double': "Roll two dice, highest sum wins the round.",
                'crazy': "Roll one die, lowest number (inverted: 6=1, 1=6) wins the round."
            }
            
            text = (
                f"🎲 {username} wants to play Dice (Points)!\n\n"
                f"Bet: {bet} points\n"
                f"Win multiplier: 1.92x\n"
                f"Mode: First to {points} points\n\n"
                f"{mode} Mode: {mode_description[context.user_data['dice2_mode']]}"
            )
            keyboard = [
                [InlineKeyboardButton("🤝 Challenge a Player", callback_data="dice2_challenge")]
            ]
            await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard))
            return True

        # Challenge button
        elif data == "dice2_challenge":
            context.user_data['expecting_username'] = 'dice2'
            await context.bot.send_message(
                chat_id=chat_id,
                text="Enter the username of the player you want to challenge (e.g., @username):"
            )
            return True

    return False


# ============================================================================
# TEXT INPUT HANDLER (Username challenges for dice2)
# ============================================================================

async def handle_dice2_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handle text input for dice2 player challenges"""
    if 'expecting_username' not in context.user_data or context.user_data['expecting_username'] != 'dice2':
        return False
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    
    # Parse username
    if text.startswith('@'):
        username = text[1:]
    else:
        username = text
    
    try:
        # Find user by username
        chat_member = await context.bot.get_chat(f"@{username}")
        challenged_id = chat_member.id
        
        if challenged_id == user_id:
            await update.message.reply_text("❌ You can't challenge yourself!")
            del context.user_data['expecting_username']
            return True
        
        # Check if challenged user has points
        if not user_has_points(challenged_id):
            await update.message.reply_text("❌ This user hasn't earned any points yet!")
            del context.user_data['expecting_username']
            return True
        
        # Check balance
        setup = context.user_data.get('dice2_setup')
        if not setup:
            await update.message.reply_text("❌ Setup expired. Please start again.")
            del context.user_data['expecting_username']
            return True
        
        challenged_balance = get_user_points(challenged_id)
        if setup['bet'] > challenged_balance:
            await update.message.reply_text(f"❌ @{username} doesn't have enough points! They have {challenged_balance} points.")
            del context.user_data['expecting_username']
            return True
        
        # Create challenge
        game_id = len(context.bot_data.get('pending_challenges_points', {})) + 1
        context.bot_data.setdefault('pending_challenges_points', {})[game_id] = {
            'initiator': user_id,
            'challenged': challenged_id,
            'mode': context.user_data['dice2_mode'],
            'points_to_win': context.user_data['dice2_points'],
            'bet': setup['bet']
        }
        
        initiator_username = update.effective_user.username or "Someone"
        mode = context.user_data['dice2_mode'].capitalize()
        points = context.user_data['dice2_points']
        
        text = (
            f"🎲 {initiator_username} challenges @{username} to Dice (Points)!\n\n"
            f"Bet: {setup['bet']} points\n"
            f"Win multiplier: 1.92x\n"
            f"Mode: {mode} Mode\n"
            f"First to {points} points\n\n"
            f"@{username}, do you accept?"
        )
        keyboard = [
            [InlineKeyboardButton("Accept", callback_data=f"dice2_accept_{game_id}"),
             InlineKeyboardButton("Cancel", callback_data=f"dice2_cancel_challenge_{game_id}")]
        ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        
        del context.user_data['expecting_username']
        return True
        
    except Exception as e:
        logger.error(f"Error in dice2 challenge: {e}")
        await update.message.reply_text("❌ User not found! Make sure they're in this chat.")
        del context.user_data['expecting_username']
        return True


# Export functions
__all__ = [
    'dice2_command',
    'points_command',
    'handle_dice2_buttons',
    'handle_dice2_challenge',
    'get_user_points',
    'update_user_points'
]
