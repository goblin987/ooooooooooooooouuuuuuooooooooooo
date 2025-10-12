#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Casino Games Module for Group Helper Bot
Player vs Player games with points system
Games: Dice 🎲, Football ⚽, Basketball 🏀, Bowling 🎳
"""

import logging
import asyncio
from typing import Optional, Dict, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import database
from utils import data_manager

logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE FUNCTIONS (Adapted for Group Helper Bot)
# ============================================================================

def get_user_points(user_id: int) -> int:
    """Get user points from database"""
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
        logger.error(f"Error getting user points: {e}")
        return 0


def update_user_points(user_id: int, points: int) -> bool:
    """Update user points in database"""
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
        logger.error(f"Error updating user points: {e}")
        return False


def user_has_points(user_id: int) -> bool:
    """Check if user exists in points system"""
    try:
        conn = database.get_sync_connection()
        cursor = conn.execute(
            "SELECT COUNT(*) FROM users WHERE user_id = ?",
            (user_id,)
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] > 0 if result else False
    except Exception as e:
        logger.error(f"Error checking user: {e}")
        return False


# ============================================================================
# GAME HELPERS
# ============================================================================

async def send_game_dice(context, chat_id: int, emoji: str):
    """Send dice/game emoji and return the message"""
    try:
        msg = await context.bot.send_dice(chat_id=chat_id, emoji=emoji)
        return msg
    except Exception as e:
        logger.error(f"Error sending dice: {e}")
        return None


def calculate_dice_score(rolls: list, mode: str) -> int:
    """Calculate score based on game mode"""
    if mode == 'normal':
        return rolls[0] if len(rolls) > 0 else 0
    elif mode == 'double':
        return sum(rolls)
    elif mode == 'crazy':
        return 7 - rolls[0] if len(rolls) > 0 else 0
    return 0


def calculate_sports_score(rolls: list, mode: str, game_type: str) -> int:
    """Calculate score for sports games (basketball/football)"""
    if game_type == 'basketball':
        threshold = 4  # Basket scores are 4+
    else:  # football
        threshold = 3  # Goals are 3+
    
    if mode == 'normal':
        return rolls[0] if rolls[0] >= threshold else 0
    elif mode == 'double':
        return sum(roll for roll in rolls if roll >= threshold)
    elif mode == 'crazy':
        return 1 if rolls[0] == 1 else 0
    return 0


# ============================================================================
# GAME EVALUATION
# ============================================================================

async def evaluate_dice_round(game: Dict, chat_id: int, game_key: tuple, context: ContextTypes.DEFAULT_TYPE):
    """Evaluate dice game round"""
    rolls1, rolls2 = game['rolls']['player1'], game['rolls']['player2']
    required_rolls = game['rolls_needed']
    
    if len(rolls1) < required_rolls or len(rolls2) < required_rolls:
        await context.bot.send_message(chat_id, "Error: Incomplete rolls!")
        return
    
    score1 = calculate_dice_score(rolls1, game['mode'])
    score2 = calculate_dice_score(rolls2, game['mode'])
    
    if score1 > score2:
        game['scores']['player1'] += 1
    elif score2 > score1:
        game['scores']['player2'] += 1
    
    # Get usernames
    try:
        member1 = await context.bot.get_chat_member(chat_id, game['player1'])
        member2 = await context.bot.get_chat_member(chat_id, game['player2'])
        p1_name = member1.user.username or f"Player{game['player1']}"
        p2_name = member2.user.username or f"Player{game['player2']}"
    except:
        p1_name = f"Player{game['player1']}"
        p2_name = f"Player{game['player2']}"
    
    text = (
        f"🎲 Round {game['round_number']} Results\n"
        f"@{p1_name} rolled: {', '.join(map(str, rolls1))} = {score1}\n"
        f"@{p2_name} rolled: {', '.join(map(str, rolls2))} = {score2}\n\n"
        f"📊 Score:\n"
        f"@{p1_name}: {game['scores']['player1']}\n"
        f"@{p2_name}: {game['scores']['player2']}"
    )
    
    # Check if game ended
    if max(game['scores'].values()) >= game['points_to_win']:
        winner = 'player1' if game['scores']['player1'] > game['scores']['player2'] else 'player2'
        winner_id = game[winner]
        winner_name = p1_name if winner == 'player1' else p2_name
        
        # Award points
        prize = int(game['bet'] * 1.8)  # 1.8x multiplier (90% of 1.92 to keep 10% house edge)
        current_points = get_user_points(winner_id)
        update_user_points(winner_id, current_points + prize + game['bet'])
        
        text += (
            f"\n\n🏆 **GAME OVER!**\n"
            f"🎉 @{winner_name} wins {prize + game['bet']} points!\n\n"
            f"Final Score: {game['scores']['player1']}-{game['scores']['player2']}"
        )
        
        keyboard = [
            [InlineKeyboardButton("🎮 Play Again", callback_data=f"{game['game_type']}_rematch")]
        ]
        await context.bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
        # Clean up
        context.bot_data.get('games', {}).pop(game_key, None)
        context.bot_data.get('user_games', {}).pop((chat_id, game['player1']), None)
        context.bot_data.get('user_games', {}).pop((chat_id, game['player2']), None)
    else:
        # Next round
        game['rolls'] = {'player1': [], 'player2': []}
        game['roll_count'] = {'player1': 0, 'player2': 0}
        game['current_player'] = 'player1'
        game['round_number'] += 1
        
        text += f"\n\nRound {game['round_number']}: @{p1_name}, your turn!"
        
        keyboard = [[InlineKeyboardButton(
            f"🎲 Roll (Round {game['round_number']})",
            callback_data=f"{game['game_type']}_roll_{game['round_number']}"
        )]]
        
        message = await context.bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
        game['message_id'] = message.message_id


async def evaluate_sports_round(game: Dict, chat_id: int, game_key: tuple, context: ContextTypes.DEFAULT_TYPE):
    """Evaluate sports game round (basketball/football/bowling)"""
    rolls1, rolls2 = game['rolls']['player1'], game['rolls']['player2']
    required_rolls = game['rolls_needed']
    game_emoji = game['emoji']
    game_type = game['game_type']
    
    if len(rolls1) < required_rolls or len(rolls2) < required_rolls:
        await context.bot.send_message(chat_id, "Error: Incomplete rolls!")
        return
    
    # Calculate scores differently for sports
    if game_type in ['basketball', 'football']:
        score1 = calculate_sports_score(rolls1, game['mode'], game_type)
        score2 = calculate_sports_score(rolls2, game['mode'], game_type)
        # Only award point if one scores and other doesn't
        if score1 > 0 and score2 == 0:
            game['scores']['player1'] += 1
        elif score2 > 0 and score1 == 0:
            game['scores']['player2'] += 1
    else:  # bowling - use dice scoring
        score1 = calculate_dice_score(rolls1, game['mode'])
        score2 = calculate_dice_score(rolls2, game['mode'])
        if score1 > score2:
            game['scores']['player1'] += 1
        elif score2 > score1:
            game['scores']['player2'] += 1
    
    # Get usernames
    try:
        member1 = await context.bot.get_chat_member(chat_id, game['player1'])
        member2 = await context.bot.get_chat_member(chat_id, game['player2'])
        p1_name = member1.user.username or f"Player{game['player1']}"
        p2_name = member2.user.username or f"Player{game['player2']}"
    except:
        p1_name = f"Player{game['player1']}"
        p2_name = f"Player{game['player2']}"
    
    text = (
        f"{game_emoji} Round {game['round_number']} Results\n"
        f"@{p1_name}: {', '.join(map(str, rolls1))}\n"
        f"@{p2_name}: {', '.join(map(str, rolls2))}\n\n"
        f"📊 Score:\n"
        f"@{p1_name}: {game['scores']['player1']}\n"
        f"@{p2_name}: {game['scores']['player2']}"
    )
    
    # Check if game ended
    if max(game['scores'].values()) >= game['points_to_win']:
        winner = 'player1' if game['scores']['player1'] > game['scores']['player2'] else 'player2'
        winner_id = game[winner]
        winner_name = p1_name if winner == 'player1' else p2_name
        
        # Award points
        prize = int(game['bet'] * 1.8)
        current_points = get_user_points(winner_id)
        update_user_points(winner_id, current_points + prize + game['bet'])
        
        text += (
            f"\n\n🏆 **GAME OVER!**\n"
            f"🎉 @{winner_name} wins {prize + game['bet']} points!\n\n"
            f"Final Score: {game['scores']['player1']}-{game['scores']['player2']}"
        )
        
        keyboard = [
            [InlineKeyboardButton("🎮 Play Again", callback_data=f"{game_type}_rematch")]
        ]
        await context.bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
        # Clean up
        context.bot_data.get('games', {}).pop(game_key, None)
        context.bot_data.get('user_games', {}).pop((chat_id, game['player1']), None)
        context.bot_data.get('user_games', {}).pop((chat_id, game['player2']), None)
    else:
        # Next round
        game['rolls'] = {'player1': [], 'player2': []}
        game['roll_count'] = {'player1': 0, 'player2': 0}
        game['current_player'] = 'player1'
        game['round_number'] += 1
        
        text += f"\n\nRound {game['round_number']}: @{p1_name}, your turn!"
        
        keyboard = [[InlineKeyboardButton(
            f"{game_emoji} Play (Round {game['round_number']})",
            callback_data=f"{game_type}_play_{game['round_number']}"
        )]]
        
        message = await context.bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
        game['message_id'] = message.message_id


# ============================================================================
# GAME COMMANDS
# ============================================================================

async def dice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start dice game - /dice <points>"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not user_has_points(user_id):
        await update.message.reply_text(
            "❌ You don't have any points yet!\n"
            "Earn points by being active in the group."
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "🎲 **Dice Game**\n\n"
            "Usage: `/dice <points>`\n"
            "Example: `/dice 100`\n\n"
            "Play dice against other members!",
            parse_mode='Markdown'
        )
        return
    
    try:
        bet = int(context.args[0])
        if bet <= 0:
            raise ValueError("Bet must be positive")
        
        user_points = get_user_points(user_id)
        if bet > user_points:
            await update.message.reply_text(
                f"❌ Insufficient points!\n"
                f"You have: {user_points} points\n"
                f"Bet: {bet} points"
            )
            return
        
        if (chat_id, user_id) in context.bot_data.get('user_games', {}):
            await update.message.reply_text("❌ You're already in a game!")
            return
        
        # Setup game
        context.user_data['game_setup'] = {
            'game_type': 'dice',
            'bet': bet,
            'initiator': user_id
        }
        
        keyboard = [
            [InlineKeyboardButton("🎲 Normal (1 die, highest wins)", callback_data="dice_mode_normal")],
            [InlineKeyboardButton("🎲🎲 Double (2 dice, highest sum)", callback_data="dice_mode_double")],
            [InlineKeyboardButton("🔄 Crazy (inverted)", callback_data="dice_mode_crazy")],
            [InlineKeyboardButton("❌ Cancel", callback_data="game_cancel")]
        ]
        
        await update.message.reply_text(
            f"🎲 **Dice Game Setup**\n"
            f"Bet: {bet} points\n\n"
            f"Choose game mode:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except ValueError:
        await update.message.reply_text("❌ Invalid bet amount! Use a number.")


async def basketball_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start basketball game - /basketball <points>"""
    await _sports_command(update, context, 'basketball', '🏀')


async def football_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start football game - /football <points>"""
    await _sports_command(update, context, 'football', '⚽')


async def bowling_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start bowling game - /bowling <points>"""
    await _sports_command(update, context, 'bowling', '🎳')


async def _sports_command(update: Update, context: ContextTypes.DEFAULT_TYPE, game_type: str, emoji: str):
    """Generic sports game command"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not user_has_points(user_id):
        await update.message.reply_text(
            "❌ You don't have any points yet!\n"
            "Earn points by being active in the group."
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            f"{emoji} **{game_type.title()} Game**\n\n"
            f"Usage: `/{game_type} <points>`\n"
            f"Example: `/{game_type} 100`\n\n"
            f"Play {game_type} against other members!",
            parse_mode='Markdown'
        )
        return
    
    try:
        bet = int(context.args[0])
        if bet <= 0:
            raise ValueError("Bet must be positive")
        
        user_points = get_user_points(user_id)
        if bet > user_points:
            await update.message.reply_text(
                f"❌ Insufficient points!\n"
                f"You have: {user_points} points\n"
                f"Bet: {bet} points"
            )
            return
        
        if (chat_id, user_id) in context.bot_data.get('user_games', {}):
            await update.message.reply_text("❌ You're already in a game!")
            return
        
        # Setup game
        context.user_data['game_setup'] = {
            'game_type': game_type,
            'bet': bet,
            'initiator': user_id,
            'emoji': emoji
        }
        
        keyboard = [
            [InlineKeyboardButton(f"{emoji} Normal", callback_data=f"{game_type}_mode_normal")],
            [InlineKeyboardButton(f"{emoji}{emoji} Double", callback_data=f"{game_type}_mode_double")],
            [InlineKeyboardButton(f"🔄 Crazy", callback_data=f"{game_type}_mode_crazy")],
            [InlineKeyboardButton("❌ Cancel", callback_data="game_cancel")]
        ]
        
        await update.message.reply_text(
            f"{emoji} **{game_type.title()} Game Setup**\n"
            f"Bet: {bet} points\n\n"
            f"Choose game mode:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        
    except ValueError:
        await update.message.reply_text("❌ Invalid bet amount! Use a number.")


# ============================================================================
# GAME BUTTONS HANDLER
# ============================================================================

async def handle_game_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all game button callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    
    # Setup phase
    if 'game_setup' in context.user_data:
        setup = context.user_data['game_setup']
        if setup['initiator'] != user_id:
            await query.answer("This is not your game!", show_alert=True)
            return
        
        # Mode selection
        if data.endswith('_mode_normal') or data.endswith('_mode_double') or data.endswith('_mode_crazy'):
            mode = data.split('_')[-1]
            context.user_data['game_mode'] = mode
            
            keyboard = [
                [InlineKeyboardButton("🏆 First to 1", callback_data=f"{setup['game_type']}_points_1")],
                [InlineKeyboardButton("🏅 First to 2", callback_data=f"{setup['game_type']}_points_2")],
                [InlineKeyboardButton("🥇 First to 3", callback_data=f"{setup['game_type']}_points_3")],
                [InlineKeyboardButton("❌ Cancel", callback_data="game_cancel")]
            ]
            
            await query.edit_message_text(
                f"{setup.get('emoji', '🎲')} **{setup['game_type'].title()} - {mode.title()} Mode**\n"
                f"Bet: {setup['bet']} points\n\n"
                f"First to win:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode='Markdown'
            )
        
        # Points selection
        elif '_points_' in data:
            points = int(data.split('_')[-1])
            context.user_data['game_points'] = points
            
            mode = context.user_data['game_mode']
            username = query.from_user.username or f"User{user_id}"
            
            text = (
                f"{setup.get('emoji', '🎲')} **Challenge**\n\n"
                f"@{username} wants to play {setup['game_type'].title()}!\n"
                f"Bet: {setup['bet']} points\n"
                f"Mode: {mode.title()}\n"
                f"First to: {points} points\n\n"
                f"Reply with @username to challenge someone!"
            )
            
            await query.edit_message_text(text, parse_mode='Markdown')
            context.user_data['awaiting_challenge'] = True
        
        # Cancel
        elif data == "game_cancel":
            context.user_data.pop('game_setup', None)
            context.user_data.pop('game_mode', None)
            context.user_data.pop('game_points', None)
            await query.edit_message_text("❌ Game cancelled.")
    
    # Challenge acceptance
    elif data.startswith('challenge_accept_'):
        challenge_id = int(data.split('_')[2])
        challenge = context.bot_data.get('pending_challenges', {}).get(challenge_id)
        
        if not challenge:
            await query.edit_message_text("❌ Challenge expired.")
            return
        
        if user_id != challenge['opponent']:
            await query.answer("This challenge is not for you!", show_alert=True)
            return
        
        # Deduct points
        initiator_points = get_user_points(challenge['initiator'])
        opponent_points = get_user_points(challenge['opponent'])
        
        update_user_points(challenge['initiator'], initiator_points - challenge['bet'])
        update_user_points(challenge['opponent'], opponent_points - challenge['bet'])
        
        # Create game
        game_key = (challenge['chat_id'], challenge['initiator'], challenge['opponent'])
        game_data = {
            'player1': challenge['initiator'],
            'player2': challenge['opponent'],
            'game_type': challenge['game_type'],
            'emoji': challenge['emoji'],
            'mode': challenge['mode'],
            'bet': challenge['bet'],
            'points_to_win': challenge['points_to_win'],
            'scores': {'player1': 0, 'player2': 0},
            'current_player': 'player1',
            'rolls': {'player1': [], 'player2': []},
            'rolls_needed': 2 if challenge['mode'] == 'double' else 1,
            'roll_count': {'player1': 0, 'player2': 0},
            'round_number': 1,
            'message_id': None
        }
        
        context.bot_data.setdefault('games', {})[game_key] = game_data
        context.bot_data.setdefault('user_games', {})[(challenge['chat_id'], challenge['initiator'])] = game_key
        context.bot_data['user_games'][(challenge['chat_id'], challenge['opponent'])] = game_key
        
        # Get usernames
        try:
            member1 = await context.bot.get_chat_member(challenge['chat_id'], challenge['initiator'])
            member2 = await context.bot.get_chat_member(challenge['chat_id'], challenge['opponent'])
            p1_name = member1.user.username or f"Player{challenge['initiator']}"
            p2_name = member2.user.username or f"Player{challenge['opponent']}"
        except:
            p1_name = f"Player{challenge['initiator']}"
            p2_name = f"Player{challenge['opponent']}"
        
        # Start game
        if challenge['game_type'] == 'dice':
            button_text = f"🎲 Roll (Round 1)"
            callback = "dice_roll_1"
        else:
            button_text = f"{challenge['emoji']} Play (Round 1)"
            callback = f"{challenge['game_type']}_play_1"
        
        keyboard = [[InlineKeyboardButton(button_text, callback_data=callback)]]
        
        text = (
            f"{challenge['emoji']} **Game Started!**\n\n"
            f"Player 1: @{p1_name}\n"
            f"Player 2: @{p2_name}\n\n"
            f"Mode: {challenge['mode'].title()}\n"
            f"Bet: {challenge['bet']} points each\n"
            f"First to: {challenge['points_to_win']} points\n\n"
            f"Round 1: @{p1_name}, your turn!"
        )
        
        message = await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        game_data['message_id'] = message.message_id
        
        # Remove challenge
        context.bot_data['pending_challenges'].pop(challenge_id, None)
    
    # Challenge decline
    elif data.startswith('challenge_decline_'):
        challenge_id = int(data.split('_')[2])
        challenge = context.bot_data.get('pending_challenges', {}).get(challenge_id)
        
        if not challenge:
            await query.edit_message_text("❌ Challenge expired.")
            return
        
        if user_id != challenge['opponent']:
            await query.answer("This challenge is not for you!", show_alert=True)
            return
        
        await query.edit_message_text("❌ Challenge declined.")
        context.bot_data['pending_challenges'].pop(challenge_id, None)
    
    # In-game phase
    elif data.startswith(('dice_roll_', 'basketball_play_', 'football_play_', 'bowling_play_')):
        game_key = context.bot_data.get('user_games', {}).get((chat_id, user_id))
        if not game_key:
            await query.answer("No active game!", show_alert=True)
            return
        
        game = context.bot_data.get('games', {}).get(game_key)
        if not game:
            await query.answer("Game data missing!", show_alert=True)
            return
        
        # Check turn
        player_key = 'player1' if game['player1'] == user_id else 'player2'
        if player_key != game['current_player']:
            await query.answer("Not your turn!", show_alert=True)
            return
        
        # Send dice/emoji
        emoji_map = {
            'dice': '🎲',
            'basketball': '🏀',
            'football': '⚽',
            'bowling': '🎳'
        }
        emoji = emoji_map.get(game['game_type'], '🎲')
        
        dice_msg = await send_game_dice(context, chat_id, emoji)
        if not dice_msg:
            await query.answer("Error rolling!", show_alert=True)
            return
        
        await asyncio.sleep(4)  # Wait for animation
        
        value = dice_msg.dice.value
        game['rolls'][player_key].append(value)
        game['roll_count'][player_key] += 1
        
        # Check if need more rolls
        if game['roll_count'][player_key] < game['rolls_needed']:
            # Player needs to roll again
            pass
        else:
            # Switch to other player or evaluate
            other_player = 'player2' if player_key == 'player1' else 'player1'
            game['current_player'] = other_player
            
            if game['roll_count']['player1'] == game['rolls_needed'] and game['roll_count']['player2'] == game['rolls_needed']:
                # Both players done, evaluate
                if game['game_type'] == 'dice':
                    await evaluate_dice_round(game, chat_id, game_key, context)
                else:
                    await evaluate_sports_round(game, chat_id, game_key, context)


# ============================================================================
# TEXT HANDLER (Challenge)
# ============================================================================

async def handle_game_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle challenge text input"""
    if not context.user_data.get('awaiting_challenge'):
        return
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    setup = context.user_data.get('game_setup')
    
    if not setup or setup['initiator'] != user_id:
        return
    
    text = update.message.text.strip()
    if not text.startswith('@'):
        await update.message.reply_text("❌ Use @username format!")
        return
    
    opponent_username = text[1:].lower()
    
    # Find opponent
    opponent_id = None
    try:
        # Try to get from recent chat members
        async for member in context.bot.get_chat(chat_id).iter_members():
            if member.user.username and member.user.username.lower() == opponent_username:
                opponent_id = member.user.id
                break
    except:
        pass
    
    if not opponent_id:
        await update.message.reply_text(
            f"❌ User @{opponent_username} not found!\n"
            "Make sure they're in the group and have sent messages recently."
        )
        return
    
    if opponent_id == user_id:
        await update.message.reply_text("❌ You can't challenge yourself!")
        return
    
    # Check opponent points
    opponent_points = get_user_points(opponent_id)
    if opponent_points < setup['bet']:
        await update.message.reply_text(
            f"❌ @{opponent_username} doesn't have enough points!\n"
            f"They have: {opponent_points} points\n"
            f"Needed: {setup['bet']} points"
        )
        return
    
    # Check if opponent already in game
    if (chat_id, opponent_id) in context.bot_data.get('user_games', {}):
        await update.message.reply_text(f"❌ @{opponent_username} is already in a game!")
        return
    
    # Create challenge
    challenge_id = len(context.bot_data.get('pending_challenges', {})) + 1
    context.bot_data.setdefault('pending_challenges', {})[challenge_id] = {
        'initiator': user_id,
        'opponent': opponent_id,
        'bet': setup['bet'],
        'mode': context.user_data['game_mode'],
        'points_to_win': context.user_data['game_points'],
        'game_type': setup['game_type'],
        'emoji': setup.get('emoji', '🎲'),
        'chat_id': chat_id
    }
    
    initiator_username = update.effective_user.username or f"User{user_id}"
    
    keyboard = [
        [InlineKeyboardButton("✅ Accept", callback_data=f"challenge_accept_{challenge_id}")],
        [InlineKeyboardButton("❌ Decline", callback_data=f"challenge_decline_{challenge_id}")]
    ]
    
    await update.message.reply_text(
        f"{setup.get('emoji', '🎲')} **Challenge!**\n\n"
        f"@{initiator_username} challenges @{opponent_username}!\n\n"
        f"Game: {setup['game_type'].title()}\n"
        f"Bet: {setup['bet']} points\n"
        f"Mode: {context.user_data['game_mode'].title()}\n"
        f"First to: {context.user_data['game_points']} points\n\n"
        f"@{opponent_username}, do you accept?",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )
    
    # Clear setup
    context.user_data.pop('awaiting_challenge', None)
    context.user_data.pop('game_setup', None)
    context.user_data.pop('game_mode', None)
    context.user_data.pop('game_points', None)


# Export functions
__all__ = [
    'dice_command',
    'basketball_command',
    'football_command',
    'bowling_command',
    'handle_game_buttons',
    'handle_game_challenge'
]

