#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Casino Games Module - Exact copy from cacacacasino repo
Player vs Player only (no bot challenges)
Uses crypto balance from payments.py
"""

import logging
import asyncio
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from payments import get_user_balance, update_user_balance, user_exists

logger = logging.getLogger(__name__)


# ============================================================================
# DICE GAME
# ============================================================================

async def dice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a dice game - exact UI from casino repo"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    args = context.args

    if not user_exists(user_id):
        await update.message.reply_text("Please use /balance to register.")
        return

    if not args:
        await update.message.reply_text("Please use /dice <amount> to set a bet.")
        return

    try:
        amount = float(args[0])
        if amount <= 0:
            raise ValueError("Bet must be positive.")
        balance = get_user_balance(user_id)
        if amount > balance:
            await update.message.reply_text(f"Insufficient balance! You have ${balance:.2f}.")
            return
        if (chat_id, user_id) in context.bot_data.get('user_games', {}):
            await update.message.reply_text("You are already in a game!")
            return
        
        # Initialize setup state
        setup = {
            'initiator': user_id,
            'bet': amount,
            'state': 'mode_selection',
            'message_id': None
        }
        context.user_data['dice_setup'] = setup

        keyboard = [
            [InlineKeyboardButton("🎲 Normal Mode", callback_data="dice_mode_normal")],
            [InlineKeyboardButton("🎲 Double Roll", callback_data="dice_mode_double")],
            [InlineKeyboardButton("🎲 Crazy Mode", callback_data="dice_mode_crazy")],
            [InlineKeyboardButton("ℹ️ Mode Guide", callback_data="dice_mode_guide"),
             InlineKeyboardButton("❌ Cancel", callback_data="dice_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = await update.message.reply_text("🎲 Choose the game mode:", reply_markup=reply_markup)
        setup['message_id'] = message.message_id

    except ValueError as e:
        await update.message.reply_text(f"Invalid bet amount: {str(e)}. Use a positive number.")


# ============================================================================
# BASKETBALL GAME
# ============================================================================

async def basketball_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a basketball game - exact UI from casino repo"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    args = context.args

    if not user_exists(user_id):
        await update.message.reply_text("Please use /balance to register.")
        return

    if len(args) != 1:
        await update.message.reply_text("Usage: /basketball <amount>\nExample: /basketball 1")
        return

    try:
        amount = float(args[0])
        if amount <= 0:
            raise ValueError("Bet must be positive.")
        balance = get_user_balance(user_id)
        if amount > balance:
            await update.message.reply_text(f"Insufficient balance! You have ${balance:.2f}.")
            return
        if (chat_id, user_id) in context.bot_data.get('user_games', {}):
            await update.message.reply_text("You are already in a game!")
            return

        # Initialize setup state
        context.user_data['basketball_setup'] = {
            'initiator': user_id,
            'bet': amount,
            'state': 'mode_selection',
            'message_id': None
        }

        keyboard = [
            [InlineKeyboardButton("🏀 Normal Mode", callback_data="basketball_mode_normal")],
            [InlineKeyboardButton("🏀 Double Shot", callback_data="basketball_mode_double")],
            [InlineKeyboardButton("🏀 Crazy Mode", callback_data="basketball_mode_crazy")],
            [InlineKeyboardButton("ℹ️ Mode Guide", callback_data="basketball_mode_guide"),
             InlineKeyboardButton("❌ Cancel", callback_data="basketball_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = await update.message.reply_text("🏀 Choose the game mode:", reply_markup=reply_markup)
        context.user_data['basketball_setup']['message_id'] = message.message_id

    except ValueError as e:
        await update.message.reply_text(f"Invalid bet amount: {str(e)}. Use a positive number.")


# ============================================================================
# FOOTBALL GAME
# ============================================================================

async def football_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a football game - exact UI from casino repo"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    args = context.args

    if not user_exists(user_id):
        await update.message.reply_text("Please use /balance to register.")
        return

    if len(args) != 1:
        await update.message.reply_text("Usage: /football <amount>\nExample: /football 1")
        return

    try:
        amount = float(args[0])
        if amount <= 0:
            raise ValueError("Bet must be positive.")
        balance = get_user_balance(user_id)
        if amount > balance:
            await update.message.reply_text(f"Insufficient balance! You have ${balance:.2f}.")
            return
        if (chat_id, user_id) in context.bot_data.get('user_games', {}):
            await update.message.reply_text("You are already in a game!")
            return

        # Initialize setup state
        context.user_data['football_setup'] = {
            'initiator': user_id,
            'bet': amount,
            'state': 'mode_selection',
            'message_id': None
        }

        keyboard = [
            [InlineKeyboardButton("⚽ Normal Mode", callback_data="football_mode_normal")],
            [InlineKeyboardButton("⚽ Double Kick", callback_data="football_mode_double")],
            [InlineKeyboardButton("⚽ Crazy Mode", callback_data="football_mode_crazy")],
            [InlineKeyboardButton("ℹ️ Mode Guide", callback_data="football_mode_guide"),
             InlineKeyboardButton("❌ Cancel", callback_data="football_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = await update.message.reply_text("⚽ Choose the game mode:", reply_markup=reply_markup)
        context.user_data['football_setup']['message_id'] = message.message_id

    except ValueError as e:
        await update.message.reply_text(f"Invalid bet amount: {str(e)}. Use a positive number.")


# ============================================================================
# BOWLING GAME
# ============================================================================

async def bowling_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a bowling game - exact UI from casino repo"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    args = context.args

    if not user_exists(user_id):
        await update.message.reply_text("Please use /balance to register.")
        return

    if len(args) != 1:
        await update.message.reply_text("Usage: /bowling <amount>\nExample: /bowling 1")
        return

    try:
        amount = float(args[0])
        if amount <= 0:
            raise ValueError("Bet must be positive.")
        balance = get_user_balance(user_id)
        if amount > balance:
            await update.message.reply_text(f"Insufficient balance! You have ${balance:.2f}.")
            return
        if (chat_id, user_id) in context.bot_data.get('user_games', {}):
            await update.message.reply_text("You are already in a game!")
            return

        # Initialize setup state
        context.user_data['bowling_setup'] = {
            'initiator': user_id,
            'bet': amount,
            'state': 'mode_selection',
            'message_id': None
        }

        keyboard = [
            [InlineKeyboardButton("🎳 Normal Mode", callback_data="bowling_mode_normal")],
            [InlineKeyboardButton("🎳 Double Bowl", callback_data="bowling_mode_double")],
            [InlineKeyboardButton("🎳 Crazy Mode", callback_data="bowling_mode_crazy")],
            [InlineKeyboardButton("ℹ️ Mode Guide", callback_data="bowling_mode_guide"),
             InlineKeyboardButton("❌ Cancel", callback_data="bowling_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = await update.message.reply_text("🎳 Choose the game mode:", reply_markup=reply_markup)
        context.user_data['bowling_setup']['message_id'] = message.message_id

    except ValueError as e:
        await update.message.reply_text(f"Invalid bet amount: {str(e)}. Use a positive number.")


# ============================================================================
# GAME BUTTON HANDLERS (All games use same pattern)
# ============================================================================

async def handle_game_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all game-related button callbacks"""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data

    # Determine which game this is for
    game_type = None
    if data.startswith('dice_'):
        game_type = 'dice'
        emoji = '🎲'
    elif data.startswith('basketball_'):
        game_type = 'basketball'
        emoji = '🏀'
    elif data.startswith('football_'):
        game_type = 'football'
        emoji = '⚽'
    elif data.startswith('bowling_'):
        game_type = 'bowling'
        emoji = '🎳'
    else:
        return

    setup_key = f'{game_type}_setup'
    
    # Handle setup phase
    if setup_key in context.user_data:
        setup = context.user_data[setup_key]
        if setup['initiator'] != user_id or setup['message_id'] != query.message.message_id:
            await query.answer("This is not your game setup!")
            return

        # Mode guide
        if data == f"{game_type}_mode_guide":
            guide_text = {
                'dice': (
                    "🎲 **Normal Mode**: Roll one die, highest number wins the round.\n\n"
                    "🎲 **Double Roll**: Roll two dice, highest sum wins the round.\n\n"
                    "🎲 **Crazy Mode**: Roll one die, lowest number (inverted: 6=1, 1=6) wins the round."
                ),
                'basketball': (
                    "🏀 **Normal Mode**: Take one shot, highest number (must be ≥4) wins the round.\n\n"
                    "🏀 **Double Shot**: Take two shots, highest sum of successful shots (≥4) wins.\n\n"
                    "🏀 **Crazy Mode**: Take one shot, rolling a 1 scores (all others miss)."
                ),
                'football': (
                    "⚽ **Normal Mode**: Take one kick, highest number (must be ≥4) wins the round.\n\n"
                    "⚽ **Double Kick**: Take two kicks, highest sum of successful kicks (≥4) wins.\n\n"
                    "⚽ **Crazy Mode**: Take one kick, rolling a 1 scores (all others miss)."
                ),
                'bowling': (
                    "🎳 **Normal Mode**: Bowl once, highest pins (must be ≥4) wins the round.\n\n"
                    "🎳 **Double Bowl**: Bowl twice, highest sum of successful bowls (≥4) wins.\n\n"
                    "🎳 **Crazy Mode**: Bowl once, knocking 1 pin scores (all others miss)."
                )
            }
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data=f"{game_type}_back")]]
            await query.edit_message_text(guide_text[game_type], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return

        # Back button
        elif data == f"{game_type}_back":
            keyboard = [
                [InlineKeyboardButton(f"{emoji} Normal Mode", callback_data=f"{game_type}_mode_normal")],
                [InlineKeyboardButton(f"{emoji} Double {'Roll' if game_type == 'dice' else 'Shot' if game_type == 'basketball' else 'Kick' if game_type == 'football' else 'Bowl'}", callback_data=f"{game_type}_mode_double")],
                [InlineKeyboardButton(f"{emoji} Crazy Mode", callback_data=f"{game_type}_mode_crazy")],
                [InlineKeyboardButton("ℹ️ Mode Guide", callback_data=f"{game_type}_mode_guide"),
                 InlineKeyboardButton("❌ Cancel", callback_data=f"{game_type}_cancel")]
            ]
            await query.edit_message_text(f"{emoji} Choose the game mode:", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # Cancel
        elif data == f"{game_type}_cancel":
            del context.user_data[setup_key]
            await query.edit_message_text("❌ Game setup cancelled.")
            return

        # Mode selection
        elif data.startswith(f"{game_type}_mode_") and data != f"{game_type}_mode_guide":
            mode = data.split('_')[2]
            context.user_data[f'{game_type}_mode'] = mode
            keyboard = [
                [InlineKeyboardButton("🏆 First to 1 point", callback_data=f"{game_type}_points_1")],
                [InlineKeyboardButton("🏅 First to 2 points", callback_data=f"{game_type}_points_2")],
                [InlineKeyboardButton("🥇 First to 3 points", callback_data=f"{game_type}_points_3")],
                [InlineKeyboardButton("❌ Cancel", callback_data=f"{game_type}_cancel")]
            ]
            await query.edit_message_text(f"{emoji} Choose points to win:", reply_markup=InlineKeyboardMarkup(keyboard))

        # Points selection
        elif data.startswith(f"{game_type}_points_"):
            points = int(data.split('_')[2])
            context.user_data[f'{game_type}_points'] = points
            bet = setup['bet']
            mode = context.user_data[f'{game_type}_mode'].capitalize()
            text = (
                f"{emoji} **Game confirmation**\n"
                f"Game: {game_type.capitalize()} {emoji}\n"
                f"First to {points} points\n"
                f"Mode: {mode} Mode\n"
                f"Your bet: ${bet:.2f}\n"
                f"Win multiplier: 1.824x (after 5% house fee)"
            )
            keyboard = [
                [InlineKeyboardButton("✅ Confirm", callback_data=f"{game_type}_confirm_setup"),
                 InlineKeyboardButton("❌ Cancel", callback_data=f"{game_type}_cancel")]
            ]
            await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

        # Confirm setup
        elif data == f"{game_type}_confirm_setup":
            bet = setup['bet']
            mode = context.user_data[f'{game_type}_mode'].capitalize()
            points = context.user_data[f'{game_type}_points']
            username = query.from_user.username or "Someone"
            
            mode_descriptions = {
                'dice': {
                    'normal': "Roll one die, highest number wins the round.",
                    'double': "Roll two dice, highest sum wins the round.",
                    'crazy': "Roll one die, lowest number (inverted: 6=1, 1=6) wins the round."
                },
                'basketball': {
                    'normal': "Take one shot, highest number (must be ≥4) wins the round.",
                    'double': "Take two shots, highest sum of successful shots (≥4) wins.",
                    'crazy': "Take one shot, rolling a 1 scores (all others miss)."
                },
                'football': {
                    'normal': "Take one kick, highest number (must be ≥4) wins the round.",
                    'double': "Take two kicks, highest sum of successful kicks (≥4) wins.",
                    'crazy': "Take one kick, rolling a 1 scores (all others miss)."
                },
                'bowling': {
                    'normal': "Bowl once, highest pins (must be ≥4) wins the round.",
                    'double': "Bowl twice, highest sum of successful bowls (≥4) wins.",
                    'crazy': "Bowl once, knocking 1 pin scores (all others miss)."
                }
            }
            
            text = (
                f"{emoji} {username} wants to play {game_type.capitalize()}!\n\n"
                f"Bet: ${bet:.2f}\n"
                f"Win multiplier: 1.824x (after 5% house fee)\n"
                f"Mode: First to {points} points\n\n"
                f"{mode} Mode: {mode_descriptions[game_type][context.user_data[f'{game_type}_mode']]}"
            )
            keyboard = [
                [InlineKeyboardButton("🤝 Challenge a Player", callback_data=f"{game_type}_challenge")]
            ]
            await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard))

        # Challenge button
        elif data == f"{game_type}_challenge":
            context.user_data['expecting_username'] = game_type
            await context.bot.send_message(
                chat_id=chat_id,
                text="Enter the username of the player you want to challenge (e.g., @username):"
            )

    # Handle in-game phase
    elif data.startswith(f"{game_type}_roll_") or data.startswith(f"{game_type}_take_shot_") or data.startswith(f"{game_type}_take_kick_") or data.startswith(f"{game_type}_bowl_"):
        game_key = context.bot_data.get('user_games', {}).get((chat_id, user_id))
        if not game_key:
            await query.answer("No active game found!")
            return
        game = context.bot_data.get('games', {}).get(game_key)
        if not game:
            await query.answer("Game data missing!")
            return
        if query.message.message_id != game.get('message_id'):
            await query.answer("This message is not for your game!")
            return
        if max(game['scores'].values()) >= game['points_to_win']:
            await context.bot.send_message(chat_id, "The game has already ended!")
            return
        
        player_key = 'player1' if game['player1'] == user_id else 'player2' if game['player2'] == user_id else None
        if not player_key:
            return
        
        turn_round = int(data.split('_')[-1])
        if turn_round != game['round_number']:
            await context.bot.send_message(chat_id, "This button is from a previous round!")
            return
        
        if player_key != game['current_player']:
            await context.bot.send_message(chat_id, "It's not your turn!")
            return
        
        # Send the appropriate emoji
        dice_emoji_map = {
            'dice': '🎲',
            'basketball': '🏀',
            'football': '⚽',
            'bowling': '🎳'
        }
        dice_msg = await context.bot.send_dice(chat_id=chat_id, emoji=dice_emoji_map[game_type])
        await asyncio.sleep(4)
        dice_value = dice_msg.dice.value
        game['rolls'][player_key].append(dice_value)
        game['roll_count'][player_key] += 1

        if game['roll_count']['player1'] == game['rolls_needed'] and game['roll_count']['player2'] == game['rolls_needed']:
            await evaluate_round(game, chat_id, game_key, context, game_type)
        else:
            if game['roll_count'][player_key] < game['rolls_needed']:
                action_text = {
                    'dice': f"🎲 Roll Again (Round {game['round_number']})",
                    'basketball': f"🏀 Take Another Shot (Round {game['round_number']})",
                    'football': f"⚽ Take Another Kick (Round {game['round_number']})",
                    'bowling': f"🎳 Bowl Again (Round {game['round_number']})"
                }
                callback_prefix = {
                    'dice': 'dice_roll',
                    'basketball': 'basketball_take_shot',
                    'football': 'football_take_kick',
                    'bowling': 'bowling_bowl'
                }
                keyboard = [[InlineKeyboardButton(action_text[game_type], callback_data=f"{callback_prefix[game_type]}_{game['round_number']}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(chat_id, f"Round {game['round_number']}: {'Roll' if game_type == 'dice' else 'Shoot' if game_type == 'basketball' else 'Kick' if game_type == 'football' else 'Bowl'} again!", reply_markup=reply_markup)
            else:
                other_player = 'player2' if player_key == 'player1' else 'player1'
                game['current_player'] = other_player
                other_username = (await context.bot.get_chat_member(chat_id, game[other_player])).user.username or "Player"
                
                action_text = {
                    'dice': f"🎲 Roll Dice (Round {game['round_number']})",
                    'basketball': f"🏀 Take a Shot (Round {game['round_number']})",
                    'football': f"⚽ Take a Kick (Round {game['round_number']})",
                    'bowling': f"🎳 Bowl (Round {game['round_number']})"
                }
                callback_prefix = {
                    'dice': 'dice_roll',
                    'basketball': 'basketball_take_shot',
                    'football': 'football_take_kick',
                    'bowling': 'bowling_bowl'
                }
                keyboard = [[InlineKeyboardButton(action_text[game_type], callback_data=f"{callback_prefix[game_type]}_{game['round_number']}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(
                    chat_id,
                    f"Round {game['round_number']}: @{other_username}, your turn! Tap the button to {'roll the dice' if game_type == 'dice' else 'take a shot' if game_type == 'basketball' else 'take a kick' if game_type == 'football' else 'bowl'}.",
                    reply_markup=reply_markup
                )

    # Handle challenge acceptance
    elif data.startswith(f"{game_type}_accept_"):
        game_id = int(data.split('_')[2])
        if game_id not in context.bot_data.get('pending_challenges', {}):
            await query.edit_message_text("❌ Challenge no longer valid.")
            return
        game = context.bot_data['pending_challenges'][game_id]
        if user_id != game['challenged']:
            return
        if (chat_id, game['initiator']) in context.bot_data.get('user_games', {}) or (chat_id, user_id) in context.bot_data.get('user_games', {}):
            await context.bot.send_message(chat_id, "One of you is already in a game!")
            return
        
        game_key = (chat_id, game['initiator'], user_id)
        game_state = {
            'player1': game['initiator'],
            'player2': user_id,
            'mode': game['mode'],
            'points_to_win': game['points_to_win'],
            'bet': game['bet'],
            'scores': {'player1': 0, 'player2': 0},
            'current_player': 'player1',
            'rolls': {'player1': [], 'player2': []},
            'rolls_needed': 2 if game['mode'] == 'double' else 1,
            'roll_count': {'player1': 0, 'player2': 0},
            'round_number': 1,
            'message_id': None
        }
        context.bot_data.setdefault('games', {})[game_key] = game_state
        context.bot_data.setdefault('user_games', {})[(chat_id, game['initiator'])] = game_key
        context.bot_data['user_games'][(chat_id, user_id)] = game_key
        
        # Deduct bets
        update_user_balance(game['initiator'], get_user_balance(game['initiator']) - game['bet'])
        update_user_balance(user_id, get_user_balance(user_id) - game['bet'])
        
        player1_username = (await context.bot.get_chat_member(chat_id, game['initiator'])).user.username or "Player1"
        player2_username = (await context.bot.get_chat_member(chat_id, user_id)).user.username or "Player2"
        
        action_text = {
            'dice': "🎲 Roll Dice (Round 1)",
            'basketball': "🏀 Take a Shot (Round 1)",
            'football': "⚽ Take a Kick (Round 1)",
            'bowling': "🎳 Bowl (Round 1)"
        }
        callback_prefix = {
            'dice': 'dice_roll',
            'basketball': 'basketball_take_shot',
            'football': 'football_take_kick',
            'bowling': 'bowling_bowl'
        }
        
        text = (
            f"{emoji} Match started!\n"
            f"Player 1: @{player1_username}\n"
            f"Player 2: @{player2_username}\n\n"
            f"Round 1: @{player1_username}, your turn! Tap the button to {'roll the dice' if game_type == 'dice' else 'take a shot' if game_type == 'basketball' else 'take a kick' if game_type == 'football' else 'bowl'}."
        )
        keyboard = [[InlineKeyboardButton(action_text[game_type], callback_data=f"{callback_prefix[game_type]}_1")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = await context.bot.send_message(chat_id, text, reply_markup=reply_markup)
        game_state['message_id'] = message.message_id
        del context.bot_data['pending_challenges'][game_id]

    # Handle challenge cancellation
    elif data.startswith(f"{game_type}_cancel_challenge_"):
        game_id = int(data.split('_')[-1])
        if game_id not in context.bot_data.get('pending_challenges', {}):
            await query.edit_message_text("❌ Challenge no longer valid.")
            return
        game = context.bot_data['pending_challenges'][game_id]
        initiator_username = (await context.bot.get_chat_member(chat_id, game['initiator'])).user.username or "Someone"
        text = f"❌ {initiator_username}'s challenge was declined."
        await query.edit_message_text(text=text)
        del context.bot_data['pending_challenges'][game_id]

    # Handle Play Again
    elif data == f"{game_type}_play_again":
        last_games = context.bot_data.get('last_games', {}).get(chat_id, {})
        last_game = last_games.get(user_id)
        if not last_game:
            await context.bot.send_message(chat_id, "No previous game found.")
            return
        
        opponent_id = last_game['opponent']
        opponent_username = (await context.bot.get_chat_member(chat_id, opponent_id)).user.username or "Someone"
        
        if (chat_id, opponent_id) in context.bot_data.get('user_games', {}):
            await context.bot.send_message(chat_id, f"@{opponent_username} is already in a game!")
            return
        
        game_id = len(context.bot_data.get('pending_challenges', {})) + 1
        context.bot_data.setdefault('pending_challenges', {})[game_id] = {
            'initiator': user_id,
            'challenged': opponent_id,
            'mode': last_game['mode'],
            'points_to_win': last_game['points_to_win'],
            'bet': last_game['bet']
        }
        
        initiator_username = query.from_user.username or "Someone"
        text = (
            f"{emoji} {initiator_username} wants to play again with the same settings!\n"
            f"Bet: ${last_game['bet']:.2f}\n"
            f"Mode: {last_game['mode'].capitalize()}\n"
            f"First to {last_game['points_to_win']} points\n\n"
            f"@{opponent_username}, do you accept?"
        )
        keyboard = [
            [InlineKeyboardButton("Accept", callback_data=f"{game_type}_accept_{game_id}"),
             InlineKeyboardButton("Cancel", callback_data=f"{game_type}_cancel_challenge_{game_id}")]
        ]
        await context.bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard))

    # Handle Double
    elif data == f"{game_type}_double":
        last_games = context.bot_data.get('last_games', {}).get(chat_id, {})
        last_game = last_games.get(user_id)
        if not last_game:
            await context.bot.send_message(chat_id, "No previous game found.")
            return
        
        opponent_id = last_game['opponent']
        new_bet = last_game['bet'] * 2
        
        initiator_balance = get_user_balance(user_id)
        opponent_balance = get_user_balance(opponent_id)
        
        if new_bet > initiator_balance or new_bet > opponent_balance:
            await context.bot.send_message(chat_id, "One of you doesn't have enough balance for the doubled bet!")
            return
        
        if (chat_id, opponent_id) in context.bot_data.get('user_games', {}):
            opponent_username = (await context.bot.get_chat_member(chat_id, opponent_id)).user.username or "Someone"
            await context.bot.send_message(chat_id, f"@{opponent_username} is already in a game!")
            return
        
        game_id = len(context.bot_data.get('pending_challenges', {})) + 1
        context.bot_data.setdefault('pending_challenges', {})[game_id] = {
            'initiator': user_id,
            'challenged': opponent_id,
            'mode': last_game['mode'],
            'points_to_win': last_game['points_to_win'],
            'bet': new_bet
        }
        
        initiator_username = query.from_user.username or "Someone"
        opponent_username = (await context.bot.get_chat_member(chat_id, opponent_id)).user.username or "Someone"
        text = (
            f"{emoji} {initiator_username} wants to double the bet!\n"
            f"New bet: ${new_bet:.2f}\n"
            f"Mode: {last_game['mode'].capitalize()}\n"
            f"First to {last_game['points_to_win']} points\n\n"
            f"@{opponent_username}, do you accept?"
        )
        keyboard = [
            [InlineKeyboardButton("Accept", callback_data=f"{game_type}_accept_{game_id}"),
             InlineKeyboardButton("Cancel", callback_data=f"{game_type}_cancel_challenge_{game_id}")]
        ]
        await context.bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard))


# ============================================================================
# ROUND EVALUATION (Game Logic)
# ============================================================================

async def evaluate_round(game, chat_id, game_key, context, game_type):
    """Evaluate the round and determine winner"""
    rolls1, rolls2 = game['rolls']['player1'], game['rolls']['player2']
    required_rolls = game['rolls_needed']
    
    if len(rolls1) < required_rolls or len(rolls2) < required_rolls:
        await context.bot.send_message(chat_id, "Error: Rolls incomplete. Please start again.")
        game['rolls'] = {'player1': [], 'player2': []}
        game['roll_count'] = {'player1': 0, 'player2': 0}
        game['current_player'] = 'player1'
        return
    
    # Calculate effective scores based on mode
    mode = game['mode']
    if mode == 'normal':
        score1 = rolls1[0] if rolls1[0] >= 4 else 0
        score2 = rolls2[0] if rolls2[0] >= 4 else 0
    elif mode == 'double':
        score1 = sum(roll for roll in rolls1 if roll >= 4)
        score2 = sum(roll for roll in rolls2 if roll >= 4)
    elif mode == 'crazy':
        score1 = 1 if rolls1[0] == 1 else 0
        score2 = 1 if rolls2[0] == 1 else 0
    
    # Award points
    if score1 > 0 and score2 == 0:
        game['scores']['player1'] += 1
    elif score2 > 0 and score1 == 0:
        game['scores']['player2'] += 1
    
    player1_username = (await context.bot.get_chat_member(chat_id, game['player1'])).user.username or "Player1"
    player2_username = (await context.bot.get_chat_member(chat_id, game['player2'])).user.username or "Player2"
    
    emoji_map = {'dice': '🎲', 'basketball': '🏀', 'football': '⚽', 'bowling': '🎳'}
    emoji = emoji_map[game_type]
    
    # Round results
    text = (
        f"{emoji} Round Results\n"
        f"Mode: {game['mode']}\n"
        f"@{player1_username} {'rolls' if game_type == 'dice' else 'shots' if game_type == 'basketball' else 'kicks' if game_type == 'football' else 'bowls'}: {rolls1}, score: {score1}\n"
        f"@{player2_username} {'rolls' if game_type == 'dice' else 'shots' if game_type == 'basketball' else 'kicks' if game_type == 'football' else 'bowls'}: {rolls2}, score: {score2}\n"
        f"{emoji} Scoreboard\n"
        f"@{player1_username}: {game['scores']['player1']}\n"
        f"@{player2_username}: {game['scores']['player2']}"
    )
    
    if score1 > 0 and score2 == 0:
        text += f"\nPoint awarded to @{player1_username}!"
    elif score2 > 0 and score1 == 0:
        text += f"\nPoint awarded to @{player2_username}!"
    else:
        text += "\nNo points awarded."
    
    # Check for game end
    if max(game['scores'].values()) >= game['points_to_win']:
        winner = 'player1' if game['scores']['player1'] > game['scores']['player2'] else 'player2'
        winner_id = game[winner]
        
        # Calculate winnings with 5% house edge
        gross_prize = game['bet'] * 1.92
        house_cut = gross_prize * 0.05  # 5% house edge
        net_prize = gross_prize - house_cut
        
        update_user_balance(winner_id, get_user_balance(winner_id) + net_prize + game['bet'])
        winner_username = player1_username if winner == 'player1' else player2_username
        
        text = (
            f"{emoji} Final Round Results\n"
            f"Mode: {game['mode']}\n"
            f"@{player1_username} {'rolls' if game_type == 'dice' else 'shots' if game_type == 'basketball' else 'kicks' if game_type == 'football' else 'bowls'}: {rolls1}, score: {score1}\n"
            f"@{player2_username} {'rolls' if game_type == 'dice' else 'shots' if game_type == 'basketball' else 'kicks' if game_type == 'football' else 'bowls'}: {rolls2}, score: {score2}\n"
            f"{emoji} Final Scoreboard\n"
            f"@{player1_username}: {game['scores']['player1']}\n"
            f"@{player2_username}: {game['scores']['player2']}\n\n"
            f"🏆 Game over!\n"
            f"🎉 @{winner_username} wins ${net_prize:.2f}!\n"
            f"_House fee (5%): ${house_cut:.2f}_"
        )
        
        player1_balance = get_user_balance(game['player1'])
        player2_balance = get_user_balance(game['player2'])
        text += f"\n\n@{player1_username} balance: ${player1_balance:.2f}\n@{player2_username} balance: ${player2_balance:.2f}"
        
        keyboard = [
            [InlineKeyboardButton("Play Again", callback_data=f"{game_type}_play_again"),
             InlineKeyboardButton("Double", callback_data=f"{game_type}_double")]
        ]
        await context.bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
        
        # Store last game data
        last_game_p1 = {'opponent': game['player2'], 'mode': game['mode'], 'points_to_win': game['points_to_win'], 'bet': game['bet']}
        last_game_p2 = {'opponent': game['player1'], 'mode': game['mode'], 'points_to_win': game['points_to_win'], 'bet': game['bet']}
        context.bot_data.setdefault('last_games', {}).setdefault(chat_id, {})[game['player1']] = last_game_p1
        context.bot_data['last_games'][chat_id][game['player2']] = last_game_p2
        
        # Clean up
        del context.bot_data['user_games'][(chat_id, game['player2'])]
        del context.bot_data['user_games'][(chat_id, game['player1'])]
        del context.bot_data['games'][game_key]
    else:
        # Continue to next round
        game['rolls'] = {'player1': [], 'player2': []}
        game['roll_count'] = {'player1': 0, 'player2': 0}
        game['current_player'] = 'player1'
        game['round_number'] += 1
        
        action_text = {
            'dice': f"🎲 Roll Dice (Round {game['round_number']})",
            'basketball': f"🏀 Take a Shot (Round {game['round_number']})",
            'football': f"⚽ Take a Kick (Round {game['round_number']})",
            'bowling': f"🎳 Bowl (Round {game['round_number']})"
        }
        callback_prefix = {
            'dice': 'dice_roll',
            'basketball': 'basketball_take_shot',
            'football': 'football_take_kick',
            'bowling': 'bowling_bowl'
        }
        
        text += f"\n\nRound {game['round_number']}: @{player1_username}, your turn! Tap the button to {'roll the dice' if game_type == 'dice' else 'take a shot' if game_type == 'basketball' else 'take a kick' if game_type == 'football' else 'bowl'}."
        keyboard = [[InlineKeyboardButton(action_text[game_type], callback_data=f"{callback_prefix[game_type]}_{game['round_number']}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = await context.bot.send_message(chat_id, text, reply_markup=reply_markup)
        game['message_id'] = message.message_id


# ============================================================================
# TEXT INPUT HANDLER (Username challenges)
# ============================================================================

async def handle_game_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handle text input for player challenges"""
    if 'expecting_username' not in context.user_data:
        return False
    
    game_type = context.user_data['expecting_username']
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    
    # Parse username
    if text.startswith('@'):
        username = text[1:]
    else:
        username = text
    
    # Find user by username
    try:
        # Try to find user in chat
        chat_member = None
        try:
            chat_member = await context.bot.get_chat(f"@{username}")
            challenged_id = chat_member.id
        except:
            await update.message.reply_text("❌ User not found! Make sure they're in this chat.")
            del context.user_data['expecting_username']
            return True
        
        if challenged_id == user_id:
            await update.message.reply_text("❌ You can't challenge yourself!")
            del context.user_data['expecting_username']
            return True
        
        # Check if challenged user exists in system
        if not user_exists(challenged_id):
            await update.message.reply_text("❌ This user hasn't registered yet! They need to use /balance first.")
            del context.user_data['expecting_username']
            return True
        
        # Check balance
        setup_key = f'{game_type}_setup'
        setup = context.user_data.get(setup_key)
        if not setup:
            await update.message.reply_text("❌ Setup expired. Please start again.")
            del context.user_data['expecting_username']
            return True
        
        challenged_balance = get_user_balance(challenged_id)
        if setup['bet'] > challenged_balance:
            await update.message.reply_text(f"❌ @{username} doesn't have enough balance! They have ${challenged_balance:.2f}.")
            del context.user_data['expecting_username']
            return True
        
        # Create challenge
        game_id = len(context.bot_data.get('pending_challenges', {})) + 1
        context.bot_data.setdefault('pending_challenges', {})[game_id] = {
            'initiator': user_id,
            'challenged': challenged_id,
            'mode': context.user_data[f'{game_type}_mode'],
            'points_to_win': context.user_data[f'{game_type}_points'],
            'bet': setup['bet']
        }
        
        emoji_map = {'dice': '🎲', 'basketball': '🏀', 'football': '⚽', 'bowling': '🎳'}
        emoji = emoji_map[game_type]
        
        initiator_username = update.effective_user.username or "Someone"
        mode = context.user_data[f'{game_type}_mode'].capitalize()
        points = context.user_data[f'{game_type}_points']
        
        text = (
            f"{emoji} {initiator_username} challenges @{username} to {game_type.capitalize()}!\n\n"
            f"Bet: ${setup['bet']:.2f}\n"
            f"Win multiplier: 1.92x\n"
            f"Mode: {mode} Mode\n"
            f"First to {points} points\n\n"
            f"@{username}, do you accept?"
        )
        keyboard = [
            [InlineKeyboardButton("Accept", callback_data=f"{game_type}_accept_{game_id}"),
             InlineKeyboardButton("Cancel", callback_data=f"{game_type}_cancel_challenge_{game_id}")]
        ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        
        del context.user_data['expecting_username']
        return True
        
    except Exception as e:
        logger.error(f"Error in challenge: {e}")
        await update.message.reply_text("❌ Error processing challenge. Please try again.")
        del context.user_data['expecting_username']
        return True


# Export functions
__all__ = [
    'dice_command',
    'basketball_command',
    'football_command',
    'bowling_command',
    'handle_game_buttons',
    'handle_game_challenge'
]
