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
            [InlineKeyboardButton("🎲 Normalus", callback_data="dice2_mode_normal")],
            [InlineKeyboardButton("🎲 Dvigubas", callback_data="dice2_mode_double")],
            [InlineKeyboardButton("🎲 Beprotiškas", callback_data="dice2_mode_crazy")],
            [InlineKeyboardButton("ℹ️ Režimų gidas", callback_data="dice2_mode_guide"),
             InlineKeyboardButton("❌ Atšaukti", callback_data="dice2_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = await update.message.reply_text("🎲 **Pasirinkite žaidimo režimą:**", reply_markup=reply_markup, parse_mode='Markdown')
        setup['message_id'] = message.message_id

    except ValueError as e:
        await update.message.reply_text(f"❌ Neteisingas statymas: {str(e)}. Naudokite teigiamą skaičių.")


# ============================================================================
# POINTS BALANCE COMMAND
# ============================================================================

async def points_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check saved points balance (separate from crypto)"""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    
    points = get_user_points(user_id)
    
    text = (
        f"💎 **Jūsų Taškai**\n\n"
        f"👤 Vartotojas: @{username}\n"
        f"💰 Taškai: {points}\n\n"
        f"_Tai atlygio taškai, atskirti nuo kripto balanso._\n\n"
        f"**Žaisti su taškais:**\n"
        f"• `/dice2 <taškai>` - Kauliukų PvP žaidimas\n\n"
        f"**Užsidirbti taškų:**\n"
        f"• Būti aktyviam grupėje\n"
        f"• Balsuoti už pardavėjus\n"
        f"• Administratorių atlygis"
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
                "🎲 **Normalus režimas**\n"
                "Metami 1 kauliukas, didžiausias skaičius laimi raundą.\n\n"
                "🎲 **Dvigubas režimas**\n"
                "Metami 2 kauliukai, didžiausia suma laimi raundą.\n\n"
                "🎲 **Beprotiškas režimas**\n"
                "Metamas 1 kauliukas, mažiausias skaičius laimi (invertuota: 6=1, 1=6)."
            )
            keyboard = [[InlineKeyboardButton("🔙 Atgal", callback_data="dice2_back")]]
            await query.edit_message_text(guide_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return True

        # Back button
        elif data == "dice2_back":
            keyboard = [
                [InlineKeyboardButton("🎲 Normalus", callback_data="dice2_mode_normal")],
                [InlineKeyboardButton("🎲 Dvigubas", callback_data="dice2_mode_double")],
                [InlineKeyboardButton("🎲 Beprotiškas", callback_data="dice2_mode_crazy")],
                [InlineKeyboardButton("ℹ️ Režimų gidas", callback_data="dice2_mode_guide"),
                 InlineKeyboardButton("❌ Atšaukti", callback_data="dice2_cancel")]
            ]
            await query.edit_message_text("🎲 **Pasirinkite žaidimo režimą:**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return True

        # Cancel
        elif data == "dice2_cancel":
            del context.user_data[setup_key]
            await query.edit_message_text("❌ Žaidimo nustatymas atšauktas.")
            return True

        # Mode selection
        elif data.startswith("dice2_mode_") and data != "dice2_mode_guide":
            mode = data.split('_')[2]
            context.user_data['dice2_mode'] = mode
            keyboard = [
                [InlineKeyboardButton("🏆 Pirmas iki 1 tšk", callback_data="dice2_points_1")],
                [InlineKeyboardButton("🏅 Pirmas iki 2 tšk", callback_data="dice2_points_2")],
                [InlineKeyboardButton("🥇 Pirmas iki 3 tšk", callback_data="dice2_points_3")],
                [InlineKeyboardButton("❌ Atšaukti", callback_data="dice2_cancel")]
            ]
            await query.edit_message_text("🎲 **Iki kiek taškų žaisti?**", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return True

        # Points selection
        elif data.startswith("dice2_points_"):
            points = int(data.split('_')[2])
            context.user_data['dice2_points'] = points
            bet = setup['bet']
            mode_lt = {'normal': 'Normalus', 'double': 'Dvigubas', 'crazy': 'Beprotiškas'}.get(context.user_data['dice2_mode'], 'Normalus')
            text = (
                f"🎲 **Patvirtinkite žaidimą**\n\n"
                f"💰 Statymas: {bet} tšk\n"
                f"🎯 Pirmas iki: {points} tšk\n"
                f"⚙️ Režimas: {mode_lt}\n"
                f"📈 Laimėjimo koeficientas: 1.92x"
            )
            keyboard = [
                [InlineKeyboardButton("✅ Patvirtinti", callback_data="dice2_confirm_setup"),
                 InlineKeyboardButton("❌ Atšaukti", callback_data="dice2_cancel")]
            ]
            await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return True

        # Confirm setup
        elif data == "dice2_confirm_setup":
            bet = setup['bet']
            mode_lt = {'normal': 'Normalus', 'double': 'Dvigubas', 'crazy': 'Beprotiškas'}.get(context.user_data['dice2_mode'], 'Normalus')
            points = context.user_data['dice2_points']
            username = query.from_user.username or "Žaidėjas"
            
            mode_description = {
                'normal': "Metamas 1 kauliukas, didžiausias skaičius laimi.",
                'double': "Metami 2 kauliukai, didžiausia suma laimi.",
                'crazy': "Metamas 1 kauliukas, mažiausias skaičius laimi (6→1, 1→6)."
            }
            
            text = (
                f"🎲 **{username}** nori žaisti kauliukus!\n\n"
                f"💰 Statymas: **{bet} tšk**\n"
                f"🎯 Pirmas iki: **{points} tšk**\n"
                f"⚙️ Režimas: {mode_lt}\n\n"
                f"_{mode_description[context.user_data['dice2_mode']]}_"
            )
            keyboard = [
                [InlineKeyboardButton("🤝 Mesti iššūkį", callback_data="dice2_challenge")]
            ]
            await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
            return True

        # Challenge button
        elif data == "dice2_challenge":
            context.user_data['expecting_username'] = 'dice2'
            await context.bot.send_message(
                chat_id=chat_id,
                text="👤 **Įveskite žaidėjo vardą:**\n"
                     "Pavyzdžiui: `@username`",
                parse_mode='Markdown'
            )
            return True

    # Handle in-game phase (rolling dice)
    elif data.startswith("dice2_roll_"):
        game_key = context.bot_data.get('user_games_points', {}).get((chat_id, user_id))
        if not game_key:
            await query.answer("No active game found!")
            return True
        game = context.bot_data.get('games_points', {}).get(game_key)
        if not game:
            await query.answer("Game data missing!")
            return True
        if query.message.message_id != game.get('message_id'):
            await query.answer("This message is not for your game!")
            return True
        if max(game['scores'].values()) >= game['points_to_win']:
            await context.bot.send_message(chat_id, "The game has already ended!")
            return True
        
        player_key = 'player1' if game['player1'] == user_id else 'player2' if game['player2'] == user_id else None
        if not player_key:
            return True
        
        turn_round = int(data.split('_')[2])
        if turn_round != game['round_number']:
            await context.bot.send_message(chat_id, "This button is from a previous round!")
            return True
        
        if player_key != game['current_player']:
            await context.bot.send_message(chat_id, "It's not your turn!")
            return True
        
        # Send dice
        dice_msg = await context.bot.send_dice(chat_id=chat_id, emoji='🎲')
        await asyncio.sleep(4)
        dice_value = dice_msg.dice.value
        game['rolls'][player_key].append(dice_value)
        game['roll_count'][player_key] += 1

        if game['roll_count']['player1'] == game['rolls_needed'] and game['roll_count']['player2'] == game['rolls_needed']:
            await evaluate_dice2_round(game, chat_id, game_key, context)
        else:
            if game['roll_count'][player_key] < game['rolls_needed']:
                keyboard = [[InlineKeyboardButton(f"🎲 Roll Again (Round {game['round_number']})", callback_data=f"dice2_roll_{game['round_number']}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(chat_id, f"Round {game['round_number']}: Roll again!", reply_markup=reply_markup)
            else:
                other_player = 'player2' if player_key == 'player1' else 'player1'
                game['current_player'] = other_player
                other_username = (await context.bot.get_chat_member(chat_id, game[other_player])).user.username or "Player"
                keyboard = [[InlineKeyboardButton(f"🎲 Roll Dice (Round {game['round_number']})", callback_data=f"dice2_roll_{game['round_number']}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(
                    chat_id,
                    f"Round {game['round_number']}: @{other_username}, your turn! Tap the button to roll the dice.",
                    reply_markup=reply_markup
                )
        return True

    # Handle challenge acceptance
    elif data.startswith("dice2_accept_"):
        game_id = int(data.split('_')[2])
        if game_id not in context.bot_data.get('pending_challenges_points', {}):
            await query.edit_message_text("❌ Challenge no longer valid.")
            return True
        game = context.bot_data['pending_challenges_points'][game_id]
        if user_id != game['challenged']:
            return True
        if (chat_id, game['initiator']) in context.bot_data.get('user_games_points', {}) or (chat_id, user_id) in context.bot_data.get('user_games_points', {}):
            await context.bot.send_message(chat_id, "One of you is already in a game!")
            return True
        
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
        context.bot_data.setdefault('games_points', {})[game_key] = game_state
        context.bot_data.setdefault('user_games_points', {})[(chat_id, game['initiator'])] = game_key
        context.bot_data['user_games_points'][(chat_id, user_id)] = game_key
        
        # Deduct bets
        p1_points = get_user_points(game['initiator'])
        p2_points = get_user_points(user_id)
        update_user_points(game['initiator'], p1_points - game['bet'])
        update_user_points(user_id, p2_points - game['bet'])
        
        player1_username = (await context.bot.get_chat_member(chat_id, game['initiator'])).user.username or "Player1"
        player2_username = (await context.bot.get_chat_member(chat_id, user_id)).user.username or "Player2"
        
        text = (
            f"🎲 Match started!\n"
            f"Player 1: @{player1_username}\n"
            f"Player 2: @{player2_username}\n\n"
            f"Round 1: @{player1_username}, your turn! Tap the button to roll the dice."
        )
        keyboard = [[InlineKeyboardButton("🎲 Roll Dice (Round 1)", callback_data="dice2_roll_1")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = await context.bot.send_message(chat_id, text, reply_markup=reply_markup)
        game_state['message_id'] = message.message_id
        del context.bot_data['pending_challenges_points'][game_id]
        return True

    # Handle challenge cancellation
    elif data.startswith("dice2_cancel_challenge_"):
        game_id = int(data.split('_')[-1])
        if game_id not in context.bot_data.get('pending_challenges_points', {}):
            await query.edit_message_text("❌ Challenge no longer valid.")
            return True
        game = context.bot_data['pending_challenges_points'][game_id]
        initiator_username = (await context.bot.get_chat_member(chat_id, game['initiator'])).user.username or "Someone"
        text = f"❌ {initiator_username}'s challenge was declined."
        await query.edit_message_text(text=text)
        del context.bot_data['pending_challenges_points'][game_id]
        return True

    # Handle Play Again
    elif data == "dice2_play_again":
        last_games = context.bot_data.get('last_games_points', {}).get(chat_id, {})
        last_game = last_games.get(user_id)
        if not last_game:
            await context.bot.send_message(chat_id, "No previous game found.")
            return True
        
        opponent_id = last_game['opponent']
        opponent_username = (await context.bot.get_chat_member(chat_id, opponent_id)).user.username or "Someone"
        
        if (chat_id, opponent_id) in context.bot_data.get('user_games_points', {}):
            await context.bot.send_message(chat_id, f"@{opponent_username} is already in a game!")
            return True
        
        game_id = len(context.bot_data.get('pending_challenges_points', {})) + 1
        context.bot_data.setdefault('pending_challenges_points', {})[game_id] = {
            'initiator': user_id,
            'challenged': opponent_id,
            'mode': last_game['mode'],
            'points_to_win': last_game['points_to_win'],
            'bet': last_game['bet']
        }
        
        initiator_username = query.from_user.username or "Someone"
        text = (
            f"🎲 {initiator_username} wants to play again with the same settings!\n"
            f"Bet: {last_game['bet']} points\n"
            f"Mode: {last_game['mode'].capitalize()}\n"
            f"First to {last_game['points_to_win']} points\n\n"
            f"@{opponent_username}, do you accept?"
        )
        keyboard = [
            [InlineKeyboardButton("Accept", callback_data=f"dice2_accept_{game_id}"),
             InlineKeyboardButton("Cancel", callback_data=f"dice2_cancel_challenge_{game_id}")]
        ]
        await context.bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
        return True

    # Handle Double
    elif data == "dice2_double":
        last_games = context.bot_data.get('last_games_points', {}).get(chat_id, {})
        last_game = last_games.get(user_id)
        if not last_game:
            await context.bot.send_message(chat_id, "No previous game found.")
            return True
        
        opponent_id = last_game['opponent']
        new_bet = last_game['bet'] * 2
        
        initiator_points = get_user_points(user_id)
        opponent_points = get_user_points(opponent_id)
        
        if new_bet > initiator_points or new_bet > opponent_points:
            await context.bot.send_message(chat_id, "One of you doesn't have enough points for the doubled bet!")
            return True
        
        if (chat_id, opponent_id) in context.bot_data.get('user_games_points', {}):
            opponent_username = (await context.bot.get_chat_member(chat_id, opponent_id)).user.username or "Someone"
            await context.bot.send_message(chat_id, f"@{opponent_username} is already in a game!")
            return True
        
        game_id = len(context.bot_data.get('pending_challenges_points', {})) + 1
        context.bot_data.setdefault('pending_challenges_points', {})[game_id] = {
            'initiator': user_id,
            'challenged': opponent_id,
            'mode': last_game['mode'],
            'points_to_win': last_game['points_to_win'],
            'bet': new_bet
        }
        
        initiator_username = query.from_user.username or "Someone"
        opponent_username = (await context.bot.get_chat_member(chat_id, opponent_id)).user.username or "Someone"
        text = (
            f"🎲 {initiator_username} wants to double the bet!\n"
            f"New bet: {new_bet} points\n"
            f"Mode: {last_game['mode'].capitalize()}\n"
            f"First to {last_game['points_to_win']} points\n\n"
            f"@{opponent_username}, do you accept?"
        )
        keyboard = [
            [InlineKeyboardButton("Accept", callback_data=f"dice2_accept_{game_id}"),
             InlineKeyboardButton("Cancel", callback_data=f"dice2_cancel_challenge_{game_id}")]
        ]
        await context.bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
        return True

    return False


# ============================================================================
# ROUND EVALUATION (Game Logic for dice2)
# ============================================================================

async def evaluate_dice2_round(game, chat_id, game_key, context):
    """Evaluate the dice2 round and determine winner"""
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
        score1 = rolls1[0]
        score2 = rolls2[0]
    elif mode == 'double':
        score1 = sum(rolls1)
        score2 = sum(rolls2)
    elif mode == 'crazy':
        # Inverted: lower is better
        score1 = 7 - rolls1[0]
        score2 = 7 - rolls2[0]
    
    # Award points (highest score wins)
    if score1 > score2:
        game['scores']['player1'] += 1
    elif score2 > score1:
        game['scores']['player2'] += 1
    
    player1_username = (await context.bot.get_chat_member(chat_id, game['player1'])).user.username or "Player1"
    player2_username = (await context.bot.get_chat_member(chat_id, game['player2'])).user.username or "Player2"
    
    # Round results
    text = (
        f"🎲 Round Results\n"
        f"Mode: {game['mode']}\n"
        f"@{player1_username} rolls: {rolls1}, score: {score1}\n"
        f"@{player2_username} rolls: {rolls2}, score: {score2}\n"
        f"🎲 Scoreboard\n"
        f"@{player1_username}: {game['scores']['player1']}\n"
        f"@{player2_username}: {game['scores']['player2']}"
    )
    
    if score1 > score2:
        text += f"\nPoint awarded to @{player1_username}!"
    elif score2 > score1:
        text += f"\nPoint awarded to @{player2_username}!"
    else:
        text += "\nTie - No points awarded."
    
    # Check for game end
    if max(game['scores'].values()) >= game['points_to_win']:
        winner = 'player1' if game['scores']['player1'] > game['scores']['player2'] else 'player2'
        winner_id = game[winner]
        prize = int(game['bet'] * 1.92)
        
        winner_points = get_user_points(winner_id)
        update_user_points(winner_id, winner_points + prize + game['bet'])
        winner_username = player1_username if winner == 'player1' else player2_username
        
        text = (
            f"🎲 Final Round Results\n"
            f"Mode: {game['mode']}\n"
            f"@{player1_username} rolls: {rolls1}, score: {score1}\n"
            f"@{player2_username} rolls: {rolls2}, score: {score2}\n"
            f"🎲 Final Scoreboard\n"
            f"@{player1_username}: {game['scores']['player1']}\n"
            f"@{player2_username}: {game['scores']['player2']}\n\n"
            f"🏆 Game over!\n"
            f"🎉 @{winner_username} wins {prize} points!"
        )
        
        player1_points = get_user_points(game['player1'])
        player2_points = get_user_points(game['player2'])
        text += f"\n\n@{player1_username} points: {player1_points}\n@{player2_username} points: {player2_points}"
        
        keyboard = [
            [InlineKeyboardButton("Play Again", callback_data="dice2_play_again"),
             InlineKeyboardButton("Double", callback_data="dice2_double")]
        ]
        await context.bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
        
        # Store last game data
        last_game_p1 = {'opponent': game['player2'], 'mode': game['mode'], 'points_to_win': game['points_to_win'], 'bet': game['bet']}
        last_game_p2 = {'opponent': game['player1'], 'mode': game['mode'], 'points_to_win': game['points_to_win'], 'bet': game['bet']}
        context.bot_data.setdefault('last_games_points', {}).setdefault(chat_id, {})[game['player1']] = last_game_p1
        context.bot_data['last_games_points'][chat_id][game['player2']] = last_game_p2
        
        # Clean up
        del context.bot_data['user_games_points'][(chat_id, game['player2'])]
        del context.bot_data['user_games_points'][(chat_id, game['player1'])]
        del context.bot_data['games_points'][game_key]
    else:
        # Continue to next round
        game['rolls'] = {'player1': [], 'player2': []}
        game['roll_count'] = {'player1': 0, 'player2': 0}
        game['current_player'] = 'player1'
        game['round_number'] += 1
        
        text += f"\n\nRound {game['round_number']}: @{player1_username}, your turn! Tap the button to roll the dice."
        keyboard = [[InlineKeyboardButton(f"🎲 Roll Dice (Round {game['round_number']})", callback_data=f"dice2_roll_{game['round_number']}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = await context.bot.send_message(chat_id, text, reply_markup=reply_markup)
        game['message_id'] = message.message_id


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
        # Find user by username (check multiple sources)
        challenged_id = None
        challenged_username = username
        
        # Method 1: Check user cache in database
        try:
            user_info = database.get_user_by_username(username)
            if user_info:
                challenged_id = user_info['user_id']
                challenged_username = user_info.get('username', username)
                logger.info(f"Found {username} in user cache: {challenged_id}")
        except Exception as e:
            logger.debug(f"User cache lookup failed: {e}")
        
        # Method 2: Try direct user ID lookup if input looks like an ID
        if not challenged_id and text.strip().isdigit():
            challenged_id = int(text.strip())
            logger.info(f"Using direct user ID: {challenged_id}")
        
        if not challenged_id:
            await update.message.reply_text(
                f"❌ Vartotojas **@{username}** nerastas!\n\n"
                f"💡 Patarimai:\n"
                f"• Įsitikinkite, kad vartotojas yra šioje grupėje\n"
                f"• Patikrinkite vartotojo vardo rašybą\n"
                f"• Vartotojas turi būti aktyvus grupėje",
                parse_mode='Markdown'
            )
            del context.user_data['expecting_username']
            return True
        
        if challenged_id == user_id:
            await update.message.reply_text("❌ Negalite mesti iššūkio sau!")
            del context.user_data['expecting_username']
            return True
        
        # Check if challenged user has points
        if not user_has_points(challenged_id):
            await update.message.reply_text("❌ Šis vartotojas dar neturi taškų!")
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
            await update.message.reply_text(f"❌ @{challenged_username} neturi pakankamai taškų!\nTuri: {challenged_balance} tšk.")
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
        
        initiator_username = update.effective_user.username or "Žaidėjas"
        mode_lt = {'normal': 'Normalus', 'double': 'Dvigubas', 'crazy': 'Beprotiškas'}.get(context.user_data['dice2_mode'], 'Normalus')
        points = context.user_data['dice2_points']
        
        text = (
            f"🎲 **{initiator_username}** meta iššūkį **@{challenged_username}!**\n\n"
            f"💰 Statymas: {setup['bet']} tšk\n"
            f"🎯 Pirmas iki: {points} tšk\n"
            f"⚙️ Režimas: {mode_lt}\n\n"
            f"@{challenged_username}, ar priimi iššūkį?"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Priimti", callback_data=f"dice2_accept_{game_id}"),
             InlineKeyboardButton("❌ Atsisakyti", callback_data=f"dice2_cancel_challenge_{game_id}")]
        ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
        del context.user_data['expecting_username']
        return True
        
    except Exception as e:
        logger.error(f"Error in dice2 challenge: {e}")
        await update.message.reply_text("❌ Vartotojas nerastas! Įsitikinkite, kad jis yra šiame pokalbyje.")
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
