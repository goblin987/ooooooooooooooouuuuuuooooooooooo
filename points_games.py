#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Points Games - PvP betting with saved points (NO real money)
Exact same UI as crypto games but uses points balance
"""

import logging
import asyncio
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import database

logger = logging.getLogger(__name__)


# ============================================================================
# MESSAGE AUTO-DELETION
# ============================================================================

async def delete_game_messages(context: ContextTypes.DEFAULT_TYPE):
    """Delete all tracked messages from a game after 2 minutes"""
    job = context.job
    chat_id = job.data['chat_id']
    message_ids = job.data['message_ids']
    
    logger.info(f"🗑️ Auto-deleting {len(message_ids)} game messages from chat {chat_id}")
    
    for msg_id in message_ids:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception as e:
            logger.debug(f"Could not delete message {msg_id}: {e}")
    
    logger.info(f"✅ Deleted {len(message_ids)} game messages")


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
    
    # Check if this is a reply-based challenge (PROPER SOLUTION!)
    if update.message.reply_to_message:
        return await handle_reply_dice2_challenge(update, context)

    if not user_has_points(user_id):
        await update.message.reply_text(
            "❌ Neturite taškų!\n\n"
            "Užsidirbkite taškų:\n"
            "• Balsuokite už pardavėjus (/balsuoti)\n"
            "• Būkite aktyvūs grupėje"
        )
        return

    if not args:
        points = get_user_points(user_id)
        await update.message.reply_text(
            f"🎲 **Kauliukų žaidimas (Taškai - PvP)**\n\n"
            f"💰 Jūsų taškai: {points}\n\n"
            f"**Naudojimas:**\n"
            f"• `/dice2 <taškai>` - tada įveskite @username\n"
            f"• **ARBA** atsakykite į žinutę: `/dice2 <taškai>`\n\n"
            f"**Pavyzdys:** `/dice2 10`\n\n"
            f"_💡 Patarimas: Atsakykite į žinutę, kad mesti iššūkį greičiau!_",
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
    
    logger.info(f"🔘 DICE2 BUTTON: User {user_id} clicked '{data}' in chat {chat_id}")

    if not data.startswith('dice2_'):
        return False

    setup_key = 'dice2_setup'
    
    # Handle setup phase (mode/points selection - NOT challenge or game phase!)
    # Skip this check for: challenge acceptance, game rolling, doubles
    is_setup_button = not (
        data.startswith("dice2_accept_") or 
        data.startswith("dice2_cancel_challenge_") or
        data.startswith("dice2_roll_") or
        data == "dice2_double"
    )
    
    if setup_key in context.user_data and is_setup_button:
        setup = context.user_data[setup_key]
        # Only check message_id if it exists in setup (it won't exist after challenge creation)
        if setup.get('initiator') != user_id or (setup.get('message_id') and setup.get('message_id') != query.message.message_id):
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
            # Store state with initiator ID (like casino bot!)
            context.user_data['expecting_username'] = 'dice2'
            context.user_data['dice2_setup'] = {
                'initiator': user_id,
                'chat_id': chat_id,
                'bet': setup.get('bet'),  # Changed from 'bet_amount' to 'bet' (matches initial setup)
                'win_condition': setup.get('win_condition'),
                'mode': setup.get('mode')
            }
            logger.info(f"💾 DICE2 STATE: User {user_id} expecting username input (chat: {chat_id})")
            await context.bot.send_message(
                chat_id=chat_id,
                text="👤 **Įveskite žaidėjo vardą:**\n"
                     "Pavyzdžiui: `@username`",
                parse_mode='Markdown'
            )
            return True

    # Handle in-game phase (rolling dice)
    elif data.startswith("dice2_roll_"):
        logger.info(f"🎲 DICE2 ROLL: User {user_id} clicked {data} in chat {chat_id}")
        game_key = context.bot_data.get('user_games_points', {}).get((chat_id, user_id))
        logger.info(f"🎲 DICE2 ROLL: Found game_key: {game_key}, all games: {list(context.bot_data.get('user_games_points', {}).keys())}")
        if not game_key:
            logger.warning(f"🎲 DICE2 ROLL: No game found for user {user_id} in chat {chat_id}")
            await query.answer("Žaidimas nerastas!")
            return True
        game = context.bot_data.get('games_points', {}).get(game_key)
        if not game:
            await query.answer("Žaidimo duomenys dingo!")
            return True
        if query.message.message_id != game.get('message_id'):
            await query.answer("Šis mygtukas ne tau!")
            return True
        if max(game['scores'].values()) >= game['points_to_win']:
            await context.bot.send_message(chat_id, "Žaidimas jau baigtas!")
            return True
        
        # Check if user is one of the players
        player_key = 'player1' if game['player1'] == user_id else 'player2' if game['player2'] == user_id else None
        if not player_key:
            logger.warning(f"⚠️ DICE2 ROLL: User {user_id} is not a player in this game!")
            await query.answer("⚠️ Šis žaidimas ne tau!", show_alert=True)
            return True
        
        turn_round = int(data.split('_')[2])
        if turn_round != game['round_number']:
            await context.bot.send_message(chat_id, "Senas mygtukas!")
            return True
        
        if player_key != game['current_player']:
            await context.bot.send_message(chat_id, "Ne tavo eilė!")
            return True
        
        # Send dice
        dice_msg = await context.bot.send_dice(chat_id=chat_id, emoji='🎲')
        game['message_ids'].append(dice_msg.message_id)  # Track dice message for deletion
        await asyncio.sleep(4)
        dice_value = dice_msg.dice.value
        game['rolls'][player_key].append(dice_value)
        game['roll_count'][player_key] += 1

        if game['roll_count']['player1'] == game['rolls_needed'] and game['roll_count']['player2'] == game['rolls_needed']:
            await evaluate_dice2_round(game, chat_id, game_key, context)
        else:
            if game['roll_count'][player_key] < game['rolls_needed']:
                keyboard = [[InlineKeyboardButton(f"🎲 Meskite dar kartą ({game['round_number']} raundas)", callback_data=f"dice2_roll_{game['round_number']}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                message = await context.bot.send_message(chat_id, f"{game['round_number']} raundas: Meskite dar kartą!", reply_markup=reply_markup)
                game['message_id'] = message.message_id  # Update message_id for next click
            else:
                other_player = 'player2' if player_key == 'player1' else 'player1'
                game['current_player'] = other_player
                other_username = (await context.bot.get_chat_member(chat_id, game[other_player])).user.username or "Žaidėjas"
                keyboard = [[InlineKeyboardButton(f"🎲 Meskite kauliuką ({game['round_number']} raundas)", callback_data=f"dice2_roll_{game['round_number']}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                message = await context.bot.send_message(
                    chat_id,
                    f"{game['round_number']} raundas: @{other_username}, tavo eilė!",
                    reply_markup=reply_markup
                )
                game['message_id'] = message.message_id  # Update message_id for next click
        return True

    # Handle challenge acceptance
    elif data.startswith("dice2_accept_"):
        game_id = int(data.split('_')[2])
        if game_id not in context.bot_data.get('pending_challenges_points', {}):
            await query.edit_message_text("❌ Iššūkis nebegalioja.")
            return True
        game = context.bot_data['pending_challenges_points'][game_id]
        if user_id != game['challenged']:
            return True
        if (chat_id, game['initiator']) in context.bot_data.get('user_games_points', {}) or (chat_id, user_id) in context.bot_data.get('user_games_points', {}):
            await context.bot.send_message(chat_id, "Vienas iš jūsų jau žaidžia!")
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
            'message_id': None,
            'message_ids': [],  # Track all messages for auto-deletion
            'chat_id': chat_id  # Store chat_id for deletion
        }
        context.bot_data.setdefault('games_points', {})[game_key] = game_state
        context.bot_data.setdefault('user_games_points', {})[(chat_id, game['initiator'])] = game_key
        context.bot_data['user_games_points'][(chat_id, user_id)] = game_key
        logger.info(f"🎲 GAME CREATED: game_key={game_key}, player1={game['initiator']}, player2={user_id}")
        logger.info(f"🎲 GAME STORED: Keys registered: {list(context.bot_data['user_games_points'].keys())}")
        
        # Deduct bets
        p1_points = get_user_points(game['initiator'])
        p2_points = get_user_points(user_id)
        update_user_points(game['initiator'], p1_points - game['bet'])
        update_user_points(user_id, p2_points - game['bet'])
        
        player1_username = (await context.bot.get_chat_member(chat_id, game['initiator'])).user.username or "Žaidėjas1"
        player2_username = (await context.bot.get_chat_member(chat_id, user_id)).user.username or "Žaidėjas2"
        
        text = (
            f"🎲 **Žaidimas prasideda!**\n\n"
            f"👤 Žaidėjas 1: @{player1_username}\n"
            f"👤 Žaidėjas 2: @{player2_username}\n\n"
            f"**1 raundas:** @{player1_username}, tavo eilė!"
        )
        keyboard = [[InlineKeyboardButton("🎲 Meskite kauliuką (1 raundas)", callback_data="dice2_roll_1")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = await context.bot.send_message(chat_id, text, reply_markup=reply_markup)
        game_state['message_id'] = message.message_id
        game_state['message_ids'].append(message.message_id)  # Track for deletion
        
        # Track the challenge message for deletion too
        if query.message:
            game_state['message_ids'].append(query.message.message_id)
        del context.bot_data['pending_challenges_points'][game_id]
        return True

    # Handle challenge cancellation
    elif data.startswith("dice2_cancel_challenge_"):
        game_id = int(data.split('_')[-1])
        if game_id not in context.bot_data.get('pending_challenges_points', {}):
            await query.edit_message_text("❌ Iššūkis nebegalioja.")
            return True
        game = context.bot_data['pending_challenges_points'][game_id]
        initiator_username = (await context.bot.get_chat_member(chat_id, game['initiator'])).user.username or "Kažkas"
        text = f"❌ {initiator_username} iššūkis atmestas."
        await query.edit_message_text(text=text)
        del context.bot_data['pending_challenges_points'][game_id]
        return True

    # Handle Play Again
    elif data == "dice2_play_again":
        last_games = context.bot_data.get('last_games_points', {}).get(chat_id, {})
        last_game = last_games.get(user_id)
        if not last_game:
            await context.bot.send_message(chat_id, "Ankstesnis žaidimas nerastas.")
            return True
        
        opponent_id = last_game['opponent']
        opponent_username = (await context.bot.get_chat_member(chat_id, opponent_id)).user.username or "Kažkas"
        
        if (chat_id, opponent_id) in context.bot_data.get('user_games_points', {}):
            await context.bot.send_message(chat_id, f"@{opponent_username} jau žaidžia!")
            return True
        
        game_id = len(context.bot_data.get('pending_challenges_points', {})) + 1
        context.bot_data.setdefault('pending_challenges_points', {})[game_id] = {
            'initiator': user_id,
            'challenged': opponent_id,
            'mode': last_game['mode'],
            'points_to_win': last_game['points_to_win'],
            'bet': last_game['bet']
        }
        
        initiator_username = query.from_user.username or "Kažkas"
        mode_names = {'normal': 'Normalus', 'double': 'Dvigubas', 'crazy': 'Beprotiškas'}
        mode_lt = mode_names.get(last_game['mode'], last_game['mode'].capitalize())
        
        text = (
            f"🎲 {initiator_username} nori žaisti dar kartą su tais pačiais nustatymais!\n"
            f"Statymas: {last_game['bet']} tšk\n"
            f"Režimas: {mode_lt}\n"
            f"Iki {last_game['points_to_win']} tšk\n\n"
            f"@{opponent_username}, ar priimi?"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Priimti", callback_data=f"dice2_accept_{game_id}"),
             InlineKeyboardButton("❌ Atsisakyti", callback_data=f"dice2_cancel_challenge_{game_id}")]
        ]
        await context.bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
        return True

    # Handle Double
    elif data == "dice2_double":
        last_games = context.bot_data.get('last_games_points', {}).get(chat_id, {})
        last_game = last_games.get(user_id)
        if not last_game:
            await context.bot.send_message(chat_id, "Ankstesnis žaidimas nerastas.")
            return True
        
        opponent_id = last_game['opponent']
        new_bet = last_game['bet'] * 2
        
        initiator_points = get_user_points(user_id)
        opponent_points = get_user_points(opponent_id)
        
        if new_bet > initiator_points or new_bet > opponent_points:
            await context.bot.send_message(chat_id, "Vienam iš jūsų nepakanka taškų dvigubam statymui!")
            return True
        
        if (chat_id, opponent_id) in context.bot_data.get('user_games_points', {}):
            opponent_username = (await context.bot.get_chat_member(chat_id, opponent_id)).user.username or "Kažkas"
            await context.bot.send_message(chat_id, f"@{opponent_username} jau žaidžia!")
            return True
        
        game_id = len(context.bot_data.get('pending_challenges_points', {})) + 1
        context.bot_data.setdefault('pending_challenges_points', {})[game_id] = {
            'initiator': user_id,
            'challenged': opponent_id,
            'mode': last_game['mode'],
            'points_to_win': last_game['points_to_win'],
            'bet': new_bet
        }
        
        initiator_username = query.from_user.username or "Kažkas"
        opponent_username = (await context.bot.get_chat_member(chat_id, opponent_id)).user.username or "Kažkas"
        mode_names = {'normal': 'Normalus', 'double': 'Dvigubas', 'crazy': 'Beprotiškas'}
        mode_lt = mode_names.get(last_game['mode'], last_game['mode'].capitalize())
        
        text = (
            f"🎲 {initiator_username} nori padvigubinti statymą!\n"
            f"Naujas statymas: {new_bet} tšk\n"
            f"Režimas: {mode_lt}\n"
            f"Iki {last_game['points_to_win']} tšk\n\n"
            f"@{opponent_username}, ar priimi?"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Priimti", callback_data=f"dice2_accept_{game_id}"),
             InlineKeyboardButton("❌ Atsisakyti", callback_data=f"dice2_cancel_challenge_{game_id}")]
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
        await context.bot.send_message(chat_id, "❌ Klaida: Neužbaigti metimai. Pradėkite iš naujo.")
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
    
    player1_username = (await context.bot.get_chat_member(chat_id, game['player1'])).user.username or "Žaidėjas1"
    player2_username = (await context.bot.get_chat_member(chat_id, game['player2'])).user.username or "Žaidėjas2"
    
    # Round results
    mode_lt = {'normal': 'Normalus', 'double': 'Dvigubas', 'crazy': 'Beprotiškas'}.get(game['mode'], game['mode'])
    text = (
        f"🎲 **Raundo rezultatai**\n\n"
        f"⚙️ Režimas: {mode_lt}\n"
        f"🎲 @{player1_username}: {rolls1} → **{score1}**\n"
        f"🎲 @{player2_username}: {rolls2} → **{score2}**\n\n"
        f"📊 **Rezultatai:**\n"
        f"@{player1_username}: {game['scores']['player1']}\n"
        f"@{player2_username}: {game['scores']['player2']}"
    )
    
    if score1 > score2:
        text += f"\n\n✨ Taškas: @{player1_username}!"
    elif score2 > score1:
        text += f"\n\n✨ Taškas: @{player2_username}!"
    else:
        text += "\n\n🤝 Lygiosios!"
    
    # Check for game end
    if max(game['scores'].values()) >= game['points_to_win']:
        winner = 'player1' if game['scores']['player1'] > game['scores']['player2'] else 'player2'
        winner_id = game[winner]
        prize = int(game['bet'] * 1.92)
        
        winner_points = get_user_points(winner_id)
        update_user_points(winner_id, winner_points + prize + game['bet'])
        winner_username = player1_username if winner == 'player1' else player2_username
        
        text = (
            f"🎲 **Galutiniai rezultatai**\n\n"
            f"⚙️ Režimas: {mode_lt}\n"
            f"🎲 @{player1_username}: {rolls1} → **{score1}**\n"
            f"🎲 @{player2_username}: {rolls2} → **{score2}**\n\n"
            f"📊 **Baigiamasis rezultatas:**\n"
            f"@{player1_username}: {game['scores']['player1']}\n"
            f"@{player2_username}: {game['scores']['player2']}\n\n"
            f"🏆 **Žaidimas baigtas!**\n"
            f"🎉 @{winner_username} laimi **{prize}** taškus!"
        )
        
        player1_points = get_user_points(game['player1'])
        player2_points = get_user_points(game['player2'])
        text += f"\n\n💎 @{player1_username}: {player1_points} tšk\n💎 @{player2_username}: {player2_points} tšk"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Žaisti dar kartą", callback_data="dice2_play_again"),
             InlineKeyboardButton("⚡ Dvigubas", callback_data="dice2_double")]
        ]
        final_msg = await context.bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard))
        game['message_ids'].append(final_msg.message_id)  # Track final message
        
        # Schedule deletion of all game messages after 2 minutes
        context.job_queue.run_once(
            delete_game_messages,
            when=120,  # 2 minutes
            data={'chat_id': chat_id, 'message_ids': game['message_ids'].copy()},
            name=f"delete_game_{chat_id}_{game_key}"
        )
        logger.info(f"🗑️ Scheduled deletion of {len(game['message_ids'])} messages in 2 minutes")
        
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
        
        text += f"\n\n**{game['round_number']} raundas:** @{player1_username}, tavo eilė!"
        keyboard = [[InlineKeyboardButton(f"🎲 Meskite kauliuką ({game['round_number']} raundas)", callback_data=f"dice2_roll_{game['round_number']}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = await context.bot.send_message(chat_id, text, reply_markup=reply_markup)
        game['message_id'] = message.message_id
        game['message_ids'].append(message.message_id)  # Track round continuation message


# ============================================================================
# TEXT INPUT HANDLER (Username challenges for dice2)
# ============================================================================

async def handle_dice2_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handle text input for dice2 player challenges"""
    # Check state like casino bot: expecting_username AND correct initiator
    if not context.user_data.get('expecting_username') == 'dice2':
        return False
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Verify it's the same user who initiated the challenge (like casino bot!)
    dice2_setup = context.user_data.get('dice2_setup', {})
    if dice2_setup.get('initiator') != user_id:
        logger.warning(f"🚫 DICE2 STATE: Wrong user responding (expected {dice2_setup.get('initiator')}, got {user_id})")
        return False
    
    logger.info(f"✅ DICE2 STATE: Correct initiator {user_id} responding with username")
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
        
        # Method 1: Database lookup (PRIMARY - like cacacacasino-main/dice.py!)
        logger.info(f"🔍 CHALLENGE DEBUG: Looking up username '@{username}'")
        
        conn = database.get_sync_connection()
        try:
            # First, check if ANY users exist in cache
            cursor = conn.execute("SELECT COUNT(*) FROM user_cache")
            total_users = cursor.fetchone()[0]
            logger.info(f"📊 CHALLENGE DEBUG: Total users in cache: {total_users}")
            
            # Show all cached usernames for debugging
            cursor = conn.execute("SELECT user_id, username FROM user_cache LIMIT 10")
            cached_users = cursor.fetchall()
            logger.info(f"📋 CHALLENGE DEBUG: Cached users (sample): {cached_users}")
            
            # Now try to find the specific user
            cursor = conn.execute(
                "SELECT user_id FROM user_cache WHERE LOWER(username) = LOWER(?)",
                (username,)
            )
            result = cursor.fetchone()
            if result:
                challenged_id = result['user_id'] if isinstance(result, sqlite3.Row) else result[0]
                challenged_username = username
                logger.info(f"✅ CHALLENGE DEBUG: Found @{username} in database: ID {challenged_id}")
            else:
                logger.warning(f"❌ CHALLENGE DEBUG: @{username} NOT in database (needs to send a message first)")
        except Exception as e:
            logger.error(f"❌ CHALLENGE DEBUG: Database lookup failed: {e}", exc_info=True)
        finally:
            conn.close()
        
        # Method 2: Try direct user ID lookup if input looks like an ID
        if not challenged_id and text.strip().isdigit():
            challenged_id = int(text.strip())
            challenged_username = f"user_{challenged_id}"
            logger.info(f"Using direct user ID: {challenged_id}")
        
        if not challenged_id:
            await update.message.reply_text(
                f"❌ Vartotojas **@{username}** nerastas!\n\n"
                f"**💡 Geriau:**\n"
                f"Atsakykite į jo žinutę ir parašykite:\n"
                f"`/dice2 <taškai>`\n\n"
                f"Arba palaukite, kol jis parašys bet ką grupėje!",
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
        
        bet = setup.get('bet', 0)  # Changed from 'bet_amount' to 'bet' (matches crypto games)
        challenged_balance = get_user_points(challenged_id)
        if bet > challenged_balance:
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
            'bet': bet  # Changed from 'bet_amount' to 'bet'
        }
        
        initiator_username = update.effective_user.username or "Žaidėjas"
        mode_lt = {'normal': 'Normalus', 'double': 'Dvigubas', 'crazy': 'Beprotiškas'}.get(context.user_data['dice2_mode'], 'Normalus')
        points = context.user_data['dice2_points']
        
        text = (
            f"🎲 **{initiator_username}** meta iššūkį **@{challenged_username}!**\n\n"
            f"💰 Statymas: {bet} tšk\n"  # Changed from 'bet_amount' to 'bet'
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
        await update.message.reply_text(
            "❌ Vartotojas nerastas!\n\n"
            "**💡 Geriau:**\n"
            "Atsakykite į jo žinutę ir parašykite:\n"
            "`/dice2 <taškai>`\n\n"
            "Arba palaukite, kol jis parašys bet ką grupėje!",
            parse_mode='Markdown'
        )
        del context.user_data['expecting_username']
        return True


# ============================================================================
# REPLY-BASED CHALLENGE (PROPER SOLUTION)
# ============================================================================

async def handle_reply_dice2_challenge(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle reply-based dice2 challenges - ALWAYS WORKS!"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    challenged_user = update.message.reply_to_message.from_user
    
    # Check if trying to challenge yourself
    if challenged_user.id == user_id:
        await update.message.reply_text("❌ Negalite mesti iššūkio sau!")
        return
    
    # Check if user has points
    if not user_has_points(user_id):
        await update.message.reply_text(
            "❌ Neturite taškų!\n\n"
            "Užsidirbkite taškų:\n"
            "• Balsuokite už pardavėjus (/balsuoti)\n"
            "• Būkite aktyvūs grupėje"
        )
        return
    
    # Parse bet amount
    args = context.args
    if not args:
        await update.message.reply_text(
            "❌ Nurodykite statymo sumą!\n\n"
            "**Pavyzdys:** `/dice2 10` (atsakant į žinutę)"
        )
        return
    
    try:
        bet = int(args[0])
        if bet <= 0:
            raise ValueError("Bet must be positive")
        
        balance = get_user_points(user_id)
        if bet > balance:
            await update.message.reply_text(
                f"❌ Neturite tiek taškų!\n\n"
                f"💰 Jūsų taškai: {balance}"
            )
            return
        
        # Check if challenged user has points
        if not user_has_points(challenged_user.id):
            await update.message.reply_text(
                f"❌ {challenged_user.first_name} dar neturi taškų!"
            )
            return
        
        challenged_balance = get_user_points(challenged_user.id)
        if bet > challenged_balance:
            await update.message.reply_text(
                f"❌ {challenged_user.first_name} neturi pakankamai taškų!\n"
                f"Turi: {challenged_balance} tšk."
            )
            return
        
        # Create challenge directly (skip mode selection for reply-based)
        game_id = len(context.bot_data.get('pending_challenges_points', {})) + 1
        context.bot_data.setdefault('pending_challenges_points', {})[game_id] = {
            'initiator': user_id,
            'challenged': challenged_user.id,
            'mode': 'normal',  # Default to normal mode for reply-based
            'points_to_win': 1,  # Default to first-to-1
            'bet': bet
        }
        
        initiator_username = update.effective_user.username or update.effective_user.first_name
        challenged_username = challenged_user.username or challenged_user.first_name
        
        text = (
            f"🎲 **{initiator_username}** meta iššūkį **{challenged_username}!**\n\n"
            f"💰 Statymas: {bet} tšk\n"
            f"🎯 Pirmas iki: 1 tšk\n"
            f"⚙️ Režimas: Normalus\n\n"
            f"{challenged_username}, ar priimi iššūkį?"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Priimti", callback_data=f"dice2_accept_{game_id}"),
             InlineKeyboardButton("❌ Atsisakyti", callback_data=f"dice2_cancel_challenge_{game_id}")]
        ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        
        logger.info(f"Reply-based challenge created: {initiator_username} -> {challenged_username}, bet={bet}")
        
    except ValueError:
        await update.message.reply_text("❌ Neteisingas statymas! Naudokite skaičių.")


# Export functions
__all__ = [
    'dice2_command',
    'points_command',
    'handle_dice2_buttons',
    'handle_dice2_challenge',
    'handle_reply_dice2_challenge',
    'get_user_points',
    'update_user_points'
]
