#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Points Games - Simple betting with saved points (NO real money)
Replaces coinflip functionality with dice
"""

import logging
import random
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


# ============================================================================
# DICE2 COMMAND (Simple Points Betting)
# ============================================================================

async def dice2_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Dice game with saved points (coinflip replacement)
    Usage: /dice2 <points> <prediction>
    Example: /dice2 100 high
    """
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    username = update.effective_user.username or update.effective_user.first_name
    
    # Check if user has points
    user_points = get_user_points(user_id)
    
    if not context.args:
        await update.message.reply_text(
            "🎲 **Dice Game (Points)**\n\n"
            "Roll the dice and predict the outcome!\n\n"
            "**Usage:** `/dice2 <points> <prediction>`\n\n"
            "**Predictions:**\n"
            "• `high` - Roll 4, 5, or 6 (2x win)\n"
            "• `low` - Roll 1, 2, or 3 (2x win)\n"
            "• `even` - Roll 2, 4, or 6 (2x win)\n"
            "• `odd` - Roll 1, 3, or 5 (2x win)\n"
            "• `exact <number>` - Roll exact number (6x win)\n\n"
            "**Examples:**\n"
            "• `/dice2 100 high` - Bet 100 points on high\n"
            "• `/dice2 50 even` - Bet 50 points on even\n"
            "• `/dice2 200 exact 6` - Bet 200 on rolling 6\n\n"
            f"**Your Points:** {user_points}",
            parse_mode='Markdown'
        )
        return
    
    # Parse bet amount
    try:
        bet = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid bet amount! Use a number.")
        return
    
    if bet <= 0:
        await update.message.reply_text("❌ Bet must be greater than 0!")
        return
    
    if bet > user_points:
        await update.message.reply_text(
            f"❌ Insufficient points!\n"
            f"You have: {user_points} points\n"
            f"Bet: {bet} points"
        )
        return
    
    # Parse prediction
    if len(context.args) < 2:
        await update.message.reply_text(
            "❌ Please specify a prediction!\n"
            "Options: `high`, `low`, `even`, `odd`, or `exact <number>`",
            parse_mode='Markdown'
        )
        return
    
    prediction_type = context.args[1].lower()
    
    # Validate prediction
    valid_predictions = ['high', 'low', 'even', 'odd', 'exact']
    if prediction_type not in valid_predictions:
        await update.message.reply_text(
            "❌ Invalid prediction!\n"
            "Options: `high`, `low`, `even`, `odd`, or `exact <number>`",
            parse_mode='Markdown'
        )
        return
    
    # Handle exact number prediction
    exact_number = None
    if prediction_type == 'exact':
        if len(context.args) < 3:
            await update.message.reply_text("❌ Please specify a number for exact prediction (1-6)")
            return
        try:
            exact_number = int(context.args[2])
            if exact_number < 1 or exact_number > 6:
                await update.message.reply_text("❌ Number must be between 1 and 6!")
                return
        except ValueError:
            await update.message.reply_text("❌ Invalid number!")
            return
    
    # Deduct bet from user
    new_balance = user_points - bet
    update_user_points(user_id, new_balance)
    
    # Send dice
    dice_msg = await context.bot.send_dice(chat_id=chat_id, emoji='🎲')
    dice_value = dice_msg.dice.value
    
    # Wait for animation
    import asyncio
    await asyncio.sleep(4)
    
    # Check win/loss
    won = False
    multiplier = 0
    
    if prediction_type == 'high':
        won = dice_value >= 4
        multiplier = 2
    elif prediction_type == 'low':
        won = dice_value <= 3
        multiplier = 2
    elif prediction_type == 'even':
        won = dice_value % 2 == 0
        multiplier = 2
    elif prediction_type == 'odd':
        won = dice_value % 2 == 1
        multiplier = 2
    elif prediction_type == 'exact':
        won = dice_value == exact_number
        multiplier = 6
    
    # Calculate winnings
    if won:
        winnings = bet * multiplier
        new_balance = new_balance + winnings
        update_user_points(user_id, new_balance)
        
        result_text = (
            f"🎉 **YOU WIN!**\n\n"
            f"🎲 Rolled: {dice_value}\n"
            f"🎯 Prediction: {prediction_type.title()}" +
            (f" {exact_number}" if exact_number else "") + "\n"
            f"💰 Bet: {bet} points\n"
            f"✨ Won: {winnings} points\n"
            f"💵 New Balance: {new_balance} points"
        )
    else:
        result_text = (
            f"❌ **YOU LOSE!**\n\n"
            f"🎲 Rolled: {dice_value}\n"
            f"🎯 Prediction: {prediction_type.title()}" +
            (f" {exact_number}" if exact_number else "") + "\n"
            f"💰 Lost: {bet} points\n"
            f"💵 New Balance: {new_balance} points"
        )
    
    await update.message.reply_text(result_text, parse_mode='Markdown')
    
    logger.info(
        f"Dice2 game: User {user_id} bet {bet} on {prediction_type}, "
        f"rolled {dice_value}, {'won' if won else 'lost'}"
    )


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
        f"• `/dice2` - Dice betting game\n\n"
        f"**Earn Points:**\n"
        f"• Be active in the group\n"
        f"• Complete tasks\n"
        f"• Admin rewards"
    )
    
    await update.message.reply_text(text, parse_mode='Markdown')


# ============================================================================
# COINFLIP COMMAND (Alias for dice2)
# ============================================================================

async def coinflip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Coinflip game (heads/tails)"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    user_points = get_user_points(user_id)
    
    if not context.args:
        await update.message.reply_text(
            "🪙 **Coinflip Game (Points)**\n\n"
            "Flip a coin and predict the outcome!\n\n"
            "**Usage:** `/coinflip <points> <prediction>`\n\n"
            "**Predictions:**\n"
            "• `heads` - Heads (2x win)\n"
            "• `tails` - Tails (2x win)\n\n"
            "**Examples:**\n"
            "• `/coinflip 100 heads`\n"
            "• `/coinflip 50 tails`\n\n"
            f"**Your Points:** {user_points}",
            parse_mode='Markdown'
        )
        return
    
    # Parse bet
    try:
        bet = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid bet amount!")
        return
    
    if bet <= 0:
        await update.message.reply_text("❌ Bet must be greater than 0!")
        return
    
    if bet > user_points:
        await update.message.reply_text(
            f"❌ Insufficient points!\n"
            f"You have: {user_points} points"
        )
        return
    
    # Parse prediction
    if len(context.args) < 2:
        await update.message.reply_text("❌ Please specify heads or tails!")
        return
    
    prediction = context.args[1].lower()
    if prediction not in ['heads', 'tails', 'h', 't']:
        await update.message.reply_text("❌ Invalid prediction! Use 'heads' or 'tails'")
        return
    
    # Normalize prediction
    if prediction == 'h':
        prediction = 'heads'
    elif prediction == 't':
        prediction = 'tails'
    
    # Deduct bet
    new_balance = user_points - bet
    update_user_points(user_id, new_balance)
    
    # Flip coin
    result = random.choice(['heads', 'tails'])
    emoji = "👑" if result == 'heads' else "💰"
    
    # Check win
    won = result == prediction
    
    if won:
        winnings = bet * 2
        new_balance = new_balance + winnings
        update_user_points(user_id, new_balance)
        
        result_text = (
            f"🎉 **YOU WIN!**\n\n"
            f"🪙 Result: {emoji} {result.title()}\n"
            f"🎯 Prediction: {prediction.title()}\n"
            f"💰 Bet: {bet} points\n"
            f"✨ Won: {winnings} points\n"
            f"💵 New Balance: {new_balance} points"
        )
    else:
        result_text = (
            f"❌ **YOU LOSE!**\n\n"
            f"🪙 Result: {emoji} {result.title()}\n"
            f"🎯 Prediction: {prediction.title()}\n"
            f"💰 Lost: {bet} points\n"
            f"💵 New Balance: {new_balance} points"
        )
    
    await update.message.reply_text(result_text, parse_mode='Markdown')


# Export functions
__all__ = [
    'dice2_command',
    'points_command',
    'coinflip_command'
]

