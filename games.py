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
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from payments import get_user_balance, update_user_balance, user_exists
from decimal import Decimal

logger = logging.getLogger(__name__)


# ============================================================================
# UTILITY COMMANDS
# ============================================================================

async def cleargames_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to clear stuck games for a user"""
    from config import OWNER_ID
    
    if update.effective_user.id != OWNER_ID:
        return
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Clear all games for this user
    if 'user_games' in context.bot_data:
        keys_to_remove = [k for k in context.bot_data['user_games'].keys() if k[1] == user_id]
        for key in keys_to_remove:
            game_key = context.bot_data['user_games'].pop(key, None)
            if game_key and 'games' in context.bot_data:
                context.bot_data['games'].pop(game_key, None)
    
    # Clear pending challenges
    if 'pending_challenges' in context.bot_data:
        challenges_to_remove = []
        for chal_id, chal in context.bot_data['pending_challenges'].items():
            if chal.get('initiator') == user_id or chal.get('challenged') == user_id:
                challenges_to_remove.append(chal_id)
        for chal_id in challenges_to_remove:
            context.bot_data['pending_challenges'].pop(chal_id, None)
    
    await update.message.reply_text("✅ Visi jūsų žaidimai išvalyti!")


# ============================================================================
# DICE GAME
# ============================================================================

async def dice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a dice game - exact UI from casino repo"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    args = context.args

    if not user_exists(user_id):
        await update.message.reply_text("❌ Naudokite /balance registracijai.")
        return

    if not args:
        await update.message.reply_text("💡 Naudokite /dice <suma> statymui.")
        return

    try:
        amount = float(args[0])
        if amount <= 0:
            raise ValueError("Statymas turi būti teigiamas.")
        balance = get_user_balance(user_id)
        if amount > balance:
            await update.message.reply_text(f"❌ Nepakanka balansо! Turite ${balance:.2f}.")
            return
        if (chat_id, user_id) in context.bot_data.get('user_games', {}):
            await update.message.reply_text("⚠️ Jūs jau žaidžiate!")
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
            [InlineKeyboardButton("🎲 Normalus", callback_data="dice_mode_normal")],
            [InlineKeyboardButton("🎲 Dvigubas", callback_data="dice_mode_double")],
            [InlineKeyboardButton("🎲 Beprotiškas", callback_data="dice_mode_crazy")],
            [InlineKeyboardButton("ℹ️ Taisyklės", callback_data="dice_mode_guide"),
             InlineKeyboardButton("❌ Atšaukti", callback_data="dice_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = await update.message.reply_text("🎲 Pasirinkite žaidimo režimą:", reply_markup=reply_markup)
        setup['message_id'] = message.message_id

    except ValueError as e:
        await update.message.reply_text(f"❌ Neteisinga suma: {str(e)}. Naudokite teigiamą skaičių.")


# ============================================================================
# BASKETBALL GAME
# ============================================================================

async def basketball_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a basketball game - exact UI from casino repo"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    args = context.args

    if not user_exists(user_id):
        await update.message.reply_text("❌ Naudokite /balance registracijai.")
        return

    if len(args) != 1:
        await update.message.reply_text("💡 Naudojimas: /basketball <suma>\nPavyzdys: /basketball 1")
        return

    try:
        amount = float(args[0])
        if amount <= 0:
            raise ValueError("Statymas turi būti teigiamas.")
        balance = get_user_balance(user_id)
        if amount > balance:
            await update.message.reply_text(f"❌ Nepakanka balanso! Turite ${balance:.2f}.")
            return
        if (chat_id, user_id) in context.bot_data.get('user_games', {}):
            await update.message.reply_text("⚠️ Jūs jau žaidžiate!")
            return

        # Initialize setup state
        context.user_data['basketball_setup'] = {
            'initiator': user_id,
            'bet': amount,
            'state': 'mode_selection',
            'message_id': None
        }

        keyboard = [
            [InlineKeyboardButton("🏀 Normalus", callback_data="basketball_mode_normal")],
            [InlineKeyboardButton("🏀 Dvigubas", callback_data="basketball_mode_double")],
            [InlineKeyboardButton("🏀 Beprotiškas", callback_data="basketball_mode_crazy")],
            [InlineKeyboardButton("ℹ️ Taisyklės", callback_data="basketball_mode_guide"),
             InlineKeyboardButton("❌ Atšaukti", callback_data="basketball_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = await update.message.reply_text("🏀 Pasirinkite žaidimo režimą:", reply_markup=reply_markup)
        context.user_data['basketball_setup']['message_id'] = message.message_id

    except ValueError as e:
        await update.message.reply_text(f"❌ Neteisinga suma: {str(e)}. Naudokite teigiamą skaičių.")


# ============================================================================
# FOOTBALL GAME
# ============================================================================

async def football_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a football game - exact UI from casino repo"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    args = context.args

    if not user_exists(user_id):
        await update.message.reply_text("❌ Naudokite /balance registracijai.")
        return

    if len(args) != 1:
        await update.message.reply_text("💡 Naudojimas: /football <suma>\nPavyzdys: /football 1")
        return

    try:
        amount = float(args[0])
        if amount <= 0:
            raise ValueError("Statymas turi būti teigiamas.")
        balance = get_user_balance(user_id)
        if amount > balance:
            await update.message.reply_text(f"❌ Nepakanka balanso! Turite ${balance:.2f}.")
            return
        if (chat_id, user_id) in context.bot_data.get('user_games', {}):
            await update.message.reply_text("⚠️ Jūs jau žaidžiate!")
            return

        # Initialize setup state
        context.user_data['football_setup'] = {
            'initiator': user_id,
            'bet': amount,
            'state': 'mode_selection',
            'message_id': None
        }

        keyboard = [
            [InlineKeyboardButton("⚽ Normalus", callback_data="football_mode_normal")],
            [InlineKeyboardButton("⚽ Dvigubas", callback_data="football_mode_double")],
            [InlineKeyboardButton("⚽ Beprotiškas", callback_data="football_mode_crazy")],
            [InlineKeyboardButton("ℹ️ Taisyklės", callback_data="football_mode_guide"),
             InlineKeyboardButton("❌ Atšaukti", callback_data="football_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = await update.message.reply_text("⚽ Pasirinkite žaidimo režimą:", reply_markup=reply_markup)
        context.user_data['football_setup']['message_id'] = message.message_id

    except ValueError as e:
        await update.message.reply_text(f"❌ Neteisinga suma: {str(e)}. Naudokite teigiamą skaičių.")


# ============================================================================
# BOWLING GAME
# ============================================================================

async def bowling_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start a bowling game - exact UI from casino repo"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    args = context.args

    if not user_exists(user_id):
        await update.message.reply_text("❌ Naudokite /balance registracijai.")
        return

    if len(args) != 1:
        await update.message.reply_text("💡 Naudojimas: /bowling <suma>\nPavyzdys: /bowling 1")
        return

    try:
        amount = float(args[0])
        if amount <= 0:
            raise ValueError("Statymas turi būti teigiamas.")
        balance = get_user_balance(user_id)
        if amount > balance:
            await update.message.reply_text(f"❌ Nepakanka balanso! Turite ${balance:.2f}.")
            return
        if (chat_id, user_id) in context.bot_data.get('user_games', {}):
            await update.message.reply_text("⚠️ Jūs jau žaidžiate!")
            return

        # Initialize setup state
        context.user_data['bowling_setup'] = {
            'initiator': user_id,
            'bet': amount,
            'state': 'mode_selection',
            'message_id': None
        }

        keyboard = [
            [InlineKeyboardButton("🎳 Normalus", callback_data="bowling_mode_normal")],
            [InlineKeyboardButton("🎳 Dvigubas", callback_data="bowling_mode_double")],
            [InlineKeyboardButton("🎳 Beprotiškas", callback_data="bowling_mode_crazy")],
            [InlineKeyboardButton("ℹ️ Taisyklės", callback_data="bowling_mode_guide"),
             InlineKeyboardButton("❌ Atšaukti", callback_data="bowling_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message = await update.message.reply_text("🎳 Pasirinkite žaidimo režimą:", reply_markup=reply_markup)
        context.user_data['bowling_setup']['message_id'] = message.message_id

    except ValueError as e:
        await update.message.reply_text(f"❌ Neteisinga suma: {str(e)}. Naudokite teigiamą skaičių.")


# ============================================================================
# GAME BUTTON HANDLERS (All games use same pattern)
# ============================================================================

async def handle_game_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all game-related button callbacks"""
    query = update.callback_query
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    data = query.data
    
    logger.info(f"🎮 GAME BUTTON CLICKED: data={data}, user={user_id}, chat={chat_id}")
    
    await query.answer()

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
        logger.warning(f"❌ GAME BUTTON: Unknown game type for data={data}")
        return
    
    logger.info(f"✅ GAME BUTTON: Detected game_type={game_type}")

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
                    "🎲 **Normalus**: Metimas vienu kauliuku, aukštesnis skaičius laimi raundą.\n\n"
                    "🎲 **Dvigubas**: Du metimai, didesnė suma laimi raundą.\n\n"
                    "🎲 **Beprotiškas**: Vienas metimas, mažesnis skaičius laimi (apversta: 6=1, 1=6)."
                ),
                'basketball': (
                    "🏀 **Normalus**: Vienas metimas, aukštesnis skaičius (≥4) laimi raundą.\n\n"
                    "🏀 **Dvigubas**: Du metimai, didesnė sėkmingų metimų (≥4) suma laimi.\n\n"
                    "🏀 **Beprotiškas**: Vienas metimas, tik 1 taškas skaičiuojasi."
                ),
                'football': (
                    "⚽ **Normalus**: Vienas smūgis, aukštesnis skaičius (≥4) laimi raundą.\n\n"
                    "⚽ **Dvigubas**: Du smūgiai, didesnė sėkmingų smūgių (≥4) suma laimi.\n\n"
                    "⚽ **Beprotiškas**: Vienas smūgis, tik 1 taškas skaičiuojasi."
                ),
                'bowling': (
                    "🎳 **Normalus**: Vienas metimas, daugiau kėglių (≥4) laimi raundą.\n\n"
                    "🎳 **Dvigubas**: Du metimai, didesnė sėkmingų metimų (≥4) suma laimi.\n\n"
                    "🎳 **Beprotiškas**: Vienas metimas, tik 1 kėglis skaičiuojasi."
                )
            }
            keyboard = [[InlineKeyboardButton("🔙 Atgal", callback_data=f"{game_type}_back")]]
            await query.edit_message_text(guide_text[game_type], reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            return

        # Back button
        elif data == f"{game_type}_back":
            keyboard = [
                [InlineKeyboardButton(f"{emoji} Normalus", callback_data=f"{game_type}_mode_normal")],
                [InlineKeyboardButton(f"{emoji} Dvigubas", callback_data=f"{game_type}_mode_double")],
                [InlineKeyboardButton(f"{emoji} Beprotiškas", callback_data=f"{game_type}_mode_crazy")],
                [InlineKeyboardButton("ℹ️ Taisyklės", callback_data=f"{game_type}_mode_guide"),
                 InlineKeyboardButton("❌ Atšaukti", callback_data=f"{game_type}_cancel")]
            ]
            await query.edit_message_text(f"{emoji} Pasirinkite žaidimo režimą:", reply_markup=InlineKeyboardMarkup(keyboard))
            return

        # Cancel
        elif data == f"{game_type}_cancel":
            del context.user_data[setup_key]
            await query.edit_message_text("❌ Atšaukta.")
            return

        # Mode selection
        elif data.startswith(f"{game_type}_mode_") and data != f"{game_type}_mode_guide":
            mode = data.split('_')[2]
            context.user_data[f'{game_type}_mode'] = mode
            keyboard = [
                [InlineKeyboardButton("🏆 Iki 1 taško", callback_data=f"{game_type}_points_1")],
                [InlineKeyboardButton("🏅 Iki 2 taškų", callback_data=f"{game_type}_points_2")],
                [InlineKeyboardButton("🥇 Iki 3 taškų", callback_data=f"{game_type}_points_3")],
                [InlineKeyboardButton("❌ Atšaukti", callback_data=f"{game_type}_cancel")]
            ]
            await query.edit_message_text(f"{emoji} Pasirinkite pergalės taškus:", reply_markup=InlineKeyboardMarkup(keyboard))

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
                    'normal': "Metimas vienu kauliuku, aukštesnis skaičius laimi.",
                    'double': "Du metimai, didesnė suma laimi.",
                    'crazy': "Vienas metimas, mažesnis skaičius laimi (apversta)."
                },
                'basketball': {
                    'normal': "Vienas metimas, aukštesnis skaičius (≥4) laimi.",
                    'double': "Du metimai, didesnė sėkmingų metimų suma laimi.",
                    'crazy': "Vienas metimas, tik 1 taškas skaičiuojasi."
                },
                'football': {
                    'normal': "Vienas smūgis, aukštesnis skaičius (≥4) laimi.",
                    'double': "Du smūgiai, didesnė sėkmingų smūgių suma laimi.",
                    'crazy': "Vienas smūgis, tik 1 taškas skaičiuojasi."
                },
                'bowling': {
                    'normal': "Vienas metimas, daugiau kėglių (≥4) laimi.",
                    'double': "Du metimai, didesnė sėkmingų metimų suma laimi.",
                    'crazy': "Vienas metimas, tik 1 kėglis skaičiuojasi."
                }
            }
            
            game_names = {'dice': 'Kauliukai', 'basketball': 'Krepšinis', 'football': 'Futbolas', 'bowling': 'Boulingas'}
            mode_names = {'Normal': 'Normalus', 'Double': 'Dvigubas', 'Crazy': 'Beprotiškas'}
            text = (
                f"{emoji} {username} nori žaisti {game_names[game_type]}!\n\n"
                f"💰 Statymas: ${bet:.2f}\n"
                f"📈 Laimėjimo koef.: 1.824x (po 5% mokesčio)\n"
                f"🎯 Režimas: Iki {points} tšk\n\n"
                f"⚙️ {mode_names.get(mode, mode)}: {mode_descriptions[game_type][context.user_data[f'{game_type}_mode']]}"
            )
            keyboard = [
                [InlineKeyboardButton("🤝 Iššūkis žaidėjui", callback_data=f"{game_type}_challenge")]
            ]
            await query.edit_message_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard))

        # Challenge button
        elif data == f"{game_type}_challenge":
            context.user_data['expecting_username'] = game_type
            await context.bot.send_message(
                chat_id=chat_id,
                text="💬 Įveskite žaidėjo vardą (pvz., @vardas):"
            )

    # Handle in-game phase
    elif data.startswith(f"{game_type}_roll_") or data.startswith(f"{game_type}_take_shot_") or data.startswith(f"{game_type}_take_kick_") or data.startswith(f"{game_type}_bowl_"):
        logger.info(f"🎲 ROLL DICE: Starting roll handler for {game_type}")
        
        game_key = context.bot_data.get('user_games', {}).get((chat_id, user_id))
        logger.info(f"🔍 ROLL DICE: game_key={game_key}, user_games={context.bot_data.get('user_games', {})}")
        
        if not game_key:
            logger.error(f"❌ ROLL DICE: No game_key found for user {user_id} in chat {chat_id}")
            await query.answer("Žaidimas nerastas!")
            return
        
        game = context.bot_data.get('games', {}).get(game_key)
        logger.info(f"🎮 ROLL DICE: game={game}")
        
        if not game:
            logger.error(f"❌ ROLL DICE: No game data found for game_key {game_key}")
            await query.answer("Žaidimo duomenys dingo!")
            return
        
        # Only validate message_id if it's set (after first roll)
        if game.get('message_id') is not None and query.message.message_id != game['message_id']:
            logger.warning(f"⚠️ ROLL DICE: Wrong message_id. Expected {game.get('message_id')}, got {query.message.message_id}")
            await query.answer("Šis mygtukas ne tau!")
            return
        
        logger.info(f"✅ ROLL DICE: All validations passed, proceeding with roll")
        
        logger.info(f"🔍 ROLL DICE: Checking if game finished: max score={max(game['scores'].values())}, points_to_win={game['points_to_win']}")
        if max(game['scores'].values()) >= game['points_to_win']:
            logger.warning(f"⚠️ ROLL DICE: Game already finished!")
            await context.bot.send_message(chat_id, "Žaidimas jau baigtas!")
            return
        
        player_key = 'player1' if game['player1'] == user_id else 'player2' if game['player2'] == user_id else None
        logger.info(f"🔍 ROLL DICE: player_key={player_key} for user_id={user_id}")
        if not player_key:
            logger.error(f"❌ ROLL DICE: Could not determine player_key!")
            return
        
        turn_round = int(data.split('_')[-1])
        logger.info(f"🔍 ROLL DICE: turn_round={turn_round}, game round_number={game['round_number']}")
        if turn_round != game['round_number']:
            logger.warning(f"⚠️ ROLL DICE: Old button! turn_round={turn_round} != game round={game['round_number']}")
            await context.bot.send_message(chat_id, "Senas mygtukas!")
            return
        
        logger.info(f"🔍 ROLL DICE: current_player={game['current_player']}, player_key={player_key}")
        if player_key != game['current_player']:
            logger.warning(f"⚠️ ROLL DICE: Not your turn! current={game['current_player']}, you={player_key}")
            await context.bot.send_message(chat_id, "Ne tavo eilė!")
            return
        
        # Send the appropriate emoji
        logger.info(f"🎲 ROLL DICE: About to send dice emoji for {game_type}")
        dice_emoji_map = {
            'dice': '🎲',
            'basketball': '🏀',
            'football': '⚽',
            'bowling': '🎳'
        }
        dice_msg = await context.bot.send_dice(chat_id=chat_id, emoji=dice_emoji_map[game_type])
        logger.info(f"✅ ROLL DICE: Dice sent! Waiting for result...")
        await asyncio.sleep(4)
        dice_value = dice_msg.dice.value
        game['rolls'][player_key].append(dice_value)
        game['roll_count'][player_key] += 1

        if game['roll_count']['player1'] == game['rolls_needed'] and game['roll_count']['player2'] == game['rolls_needed']:
            await evaluate_round(game, chat_id, game_key, context, game_type)
        else:
            if game['roll_count'][player_key] < game['rolls_needed']:
                action_text = {
                    'dice': f"🎲 Meskite dar kartą ({game['round_number']} raundas)",
                    'basketball': f"🏀 Meskite dar kartą ({game['round_number']} raundas)",
                    'football': f"⚽ Mušimas dar kartą ({game['round_number']} raundas)",
                    'bowling': f"🎳 Meskite dar kartą ({game['round_number']} raundas)"
                }
                callback_prefix = {
                    'dice': 'dice_roll',
                    'basketball': 'basketball_take_shot',
                    'football': 'football_take_kick',
                    'bowling': 'bowling_bowl'
                }
                keyboard = [[InlineKeyboardButton(action_text[game_type], callback_data=f"{callback_prefix[game_type]}_{game['round_number']}")]]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await context.bot.send_message(chat_id, f"{game['round_number']} raundas: Meskite dar kartą!", reply_markup=reply_markup)
            else:
                other_player = 'player2' if player_key == 'player1' else 'player1'
                game['current_player'] = other_player
                other_username = (await context.bot.get_chat_member(chat_id, game[other_player])).user.username or "Žaidėjas"
                
                action_text = {
                    'dice': f"🎲 Meskite kauliuką ({game['round_number']} raundas)",
                    'basketball': f"🏀 Metimas ({game['round_number']} raundas)",
                    'football': f"⚽ Smūgis ({game['round_number']} raundas)",
                    'bowling': f"🎳 Meskite ({game['round_number']} raundas)"
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
                    f"{game['round_number']} raundas: @{other_username}, tavo eilė!",
                    reply_markup=reply_markup
                )

    # Handle challenge acceptance
    elif data.startswith(f"{game_type}_accept_"):
        game_id = int(data.split('_')[2])
        if game_id not in context.bot_data.get('pending_challenges', {}):
            await query.edit_message_text("❌ Iššūkis nebegalioja.")
            return
        game = context.bot_data['pending_challenges'][game_id]
        if user_id != game['challenged']:
            return
        if (chat_id, game['initiator']) in context.bot_data.get('user_games', {}) or (chat_id, user_id) in context.bot_data.get('user_games', {}):
            await context.bot.send_message(chat_id, "Vienas iš jūsų jau žaidžia!")
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
        
        # Deduct bets (convert to Decimal to avoid type mismatch)
        from decimal import Decimal
        bet_amount = Decimal(str(game['bet']))
        update_user_balance(game['initiator'], get_user_balance(game['initiator']) - bet_amount)
        update_user_balance(user_id, get_user_balance(user_id) - bet_amount)
        
        player1_username = (await context.bot.get_chat_member(chat_id, game['initiator'])).user.username or "Žaidėjas1"
        player2_username = (await context.bot.get_chat_member(chat_id, user_id)).user.username or "Žaidėjas2"
        
        action_text = {
            'dice': "🎲 Meskite kauliuką (1 raundas)",
            'basketball': "🏀 Metimas (1 raundas)",
            'football': "⚽ Smūgis (1 raundas)",
            'bowling': "🎳 Meskite (1 raundas)"
        }
        callback_prefix = {
            'dice': 'dice_roll',
            'basketball': 'basketball_take_shot',
            'football': 'football_take_kick',
            'bowling': 'bowling_bowl'
        }
        
        text = (
            f"{emoji} **Žaidimas prasideda!**\n\n"
            f"👤 Žaidėjas 1: @{player1_username}\n"
            f"👤 Žaidėjas 2: @{player2_username}\n\n"
            f"**1 raundas:** @{player1_username}, tavo eilė!"
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
            await query.edit_message_text("❌ Iššūkis nebegalioja.")
            return
        game = context.bot_data['pending_challenges'][game_id]
        initiator_username = (await context.bot.get_chat_member(chat_id, game['initiator'])).user.username or "Kažkas"
        text = f"❌ {initiator_username} iššūkis atmestas."
        await query.edit_message_text(text=text)
        del context.bot_data['pending_challenges'][game_id]

    # Handle Play Again
    elif data == f"{game_type}_play_again":
        last_games = context.bot_data.get('last_games', {}).get(chat_id, {})
        last_game = last_games.get(user_id)
        if not last_game:
            await context.bot.send_message(chat_id, "Ankstesnis žaidimas nerastas.")
            return
        
        opponent_id = last_game['opponent']
        opponent_username = (await context.bot.get_chat_member(chat_id, opponent_id)).user.username or "Kažkas"
        
        if (chat_id, opponent_id) in context.bot_data.get('user_games', {}):
            await context.bot.send_message(chat_id, f"@{opponent_username} jau žaidžia!")
            return
        
        game_id = len(context.bot_data.get('pending_challenges', {})) + 1
        context.bot_data.setdefault('pending_challenges', {})[game_id] = {
            'initiator': user_id,
            'challenged': opponent_id,
            'mode': last_game['mode'],
            'points_to_win': last_game['points_to_win'],
            'bet': last_game['bet']
        }
        
        mode_names = {'normal': 'Normalus', 'double': 'Dvigubas', 'crazy': 'Beprotiškas'}
        initiator_username = query.from_user.username or "Kažkas"
        text = (
            f"{emoji} {initiator_username} nori žaisti dar kartą su tais pačiais nustatymais!\n\n"
            f"💰 Statymas: ${last_game['bet']:.2f}\n"
            f"⚙️ Režimas: {mode_names.get(last_game['mode'], last_game['mode'])}\n"
            f"🎯 Iki {last_game['points_to_win']} tšk\n\n"
            f"@{opponent_username}, ar priimi?"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Priimti", callback_data=f"{game_type}_accept_{game_id}"),
             InlineKeyboardButton("❌ Atsisakyti", callback_data=f"{game_type}_cancel_challenge_{game_id}")]
        ]
        await context.bot.send_message(chat_id, text, reply_markup=InlineKeyboardMarkup(keyboard))

    # Handle Double
    elif data == f"{game_type}_double":
        last_games = context.bot_data.get('last_games', {}).get(chat_id, {})
        last_game = last_games.get(user_id)
        if not last_game:
            await context.bot.send_message(chat_id, "Ankstesnis žaidimas nerastas.")
            return
        
        opponent_id = last_game['opponent']
        new_bet = last_game['bet'] * 2
        
        initiator_balance = get_user_balance(user_id)
        opponent_balance = get_user_balance(opponent_id)
        
        if new_bet > initiator_balance or new_bet > opponent_balance:
            await context.bot.send_message(chat_id, "Vienam iš jūsų nepakanka balanso dvigubam statymui!")
            return
        
        if (chat_id, opponent_id) in context.bot_data.get('user_games', {}):
            opponent_username = (await context.bot.get_chat_member(chat_id, opponent_id)).user.username or "Kažkas"
            await context.bot.send_message(chat_id, f"@{opponent_username} jau žaidžia!")
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
        await context.bot.send_message(chat_id, "❌ Klaida: Neužbaigti metimai. Pradėkite iš naujo.")
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
    
    player1_username = (await context.bot.get_chat_member(chat_id, game['player1'])).user.username or "Žaidėjas1"
    player2_username = (await context.bot.get_chat_member(chat_id, game['player2'])).user.username or "Žaidėjas2"
    
    emoji_map = {'dice': '🎲', 'basketball': '🏀', 'football': '⚽', 'bowling': '🎳'}
    emoji = emoji_map[game_type]
    
    mode_names = {'normal': 'Normalus', 'double': 'Dvigubas', 'crazy': 'Beprotiškas'}
    # Round results
    text = (
        f"{emoji} **Raundo rezultatai**\n\n"
        f"⚙️ Režimas: {mode_names.get(mode, mode)}\n"
        f"🎲 @{player1_username}: {rolls1} → **{score1}**\n"
        f"🎲 @{player2_username}: {rolls2} → **{score2}**\n\n"
        f"📊 **Rezultatai:**\n"
        f"@{player1_username}: {game['scores']['player1']}\n"
        f"@{player2_username}: {game['scores']['player2']}"
    )
    
    if score1 > 0 and score2 == 0:
        text += f"\n\n✨ Taškas: @{player1_username}!"
    elif score2 > 0 and score1 == 0:
        text += f"\n\n✨ Taškas: @{player2_username}!"
    else:
        text += "\n\n🤝 Lygiosios!"
    
    # Check for game end
    if max(game['scores'].values()) >= game['points_to_win']:
        winner = 'player1' if game['scores']['player1'] > game['scores']['player2'] else 'player2'
        winner_id = game[winner]
        
        # Calculate winnings with 5% house edge
        gross_prize = game['bet'] * 1.92
        house_cut = gross_prize * 0.05  # 5% house edge
        net_prize = gross_prize - house_cut
        
        # Convert to Decimal to avoid type mismatch
        from decimal import Decimal
        bet_amount = Decimal(str(game['bet']))
        prize_amount = Decimal(str(net_prize))
        update_user_balance(winner_id, get_user_balance(winner_id) + prize_amount + bet_amount)
        winner_username = player1_username if winner == 'player1' else player2_username
        
        text = (
            f"{emoji} **Galutiniai rezultatai**\n\n"
            f"⚙️ Režimas: {mode_names.get(mode, mode)}\n"
            f"🎲 @{player1_username}: {rolls1} → **{score1}**\n"
            f"🎲 @{player2_username}: {rolls2} → **{score2}**\n\n"
            f"📊 **Baigiamasis rezultatas:**\n"
            f"@{player1_username}: {game['scores']['player1']}\n"
            f"@{player2_username}: {game['scores']['player2']}\n\n"
            f"🏆 **Žaidimas baigtas!**\n"
            f"🎉 @{winner_username} laimi **${net_prize:.2f}**!\n"
            f"_Mokestis (5%): ${house_cut:.2f}_"
        )
        
        player1_balance = get_user_balance(game['player1'])
        player2_balance = get_user_balance(game['player2'])
        text += f"\n\n💵 @{player1_username}: ${player1_balance:.2f}\n💵 @{player2_username}: ${player2_balance:.2f}"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Žaisti dar kartą", callback_data=f"{game_type}_play_again"),
             InlineKeyboardButton("⚡ Dvigubas", callback_data=f"{game_type}_double")]
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
            'dice': f"🎲 Meskite kauliuką ({game['round_number']} raundas)",
            'basketball': f"🏀 Metimas ({game['round_number']} raundas)",
            'football': f"⚽ Smūgis ({game['round_number']} raundas)",
            'bowling': f"🎳 Meskite ({game['round_number']} raundas)"
        }
        callback_prefix = {
            'dice': 'dice_roll',
            'basketball': 'basketball_take_shot',
            'football': 'football_take_kick',
            'bowling': 'bowling_bowl'
        }
        
        text += f"\n\n**{game['round_number']} raundas:** @{player1_username}, tavo eilė!"
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
    
    # CRITICAL: Only handle crypto games (dice, basketball, football, bowling)
    # Don't consume dice2 (points game) messages!
    if game_type not in ['dice', 'basketball', 'football', 'bowling']:
        logger.debug(f"🚫 CRYPTO GAMES: Ignoring non-crypto game type '{game_type}'")
        return False
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    text = update.message.text.strip()
    
    # Parse username
    if text.startswith('@'):
        username = text[1:]
    else:
        username = text
    
    # Find user by username (using database cache like points games)
    try:
        from database import database
        
        # Try to find user in database cache
        challenged_user = database.get_user_by_username(username)
        
        if not challenged_user:
            await update.message.reply_text(
                "❌ Naudotojas nerastas!\n\n"
                "Įsitikinkite, kad:\n"
                "• Jis yra šiame pokalbyje\n"
                "• Jis rašė bent vieną žinutę\n"
                "• Username teisingas"
            )
            del context.user_data['expecting_username']
            return True
        
        # Extract user_id from the returned dict
        challenged_id = challenged_user if isinstance(challenged_user, int) else challenged_user.get('user_id') if isinstance(challenged_user, dict) else challenged_user
        
        if challenged_id == user_id:
            await update.message.reply_text("❌ Negalite iššaukti savęs!")
            del context.user_data['expecting_username']
            return True
        
        # Get setup
        setup_key = f'{game_type}_setup'
        setup = context.user_data.get(setup_key)
        if not setup:
            await update.message.reply_text("❌ Nustatymai pasibaigė. Pradėkite iš naujo.")
            del context.user_data['expecting_username']
            return True
        
        # Check balance (create user if doesn't exist)
        if not user_exists(challenged_id):
            # Auto-create user with 0 balance
            update_user_balance(challenged_id, 0.0)
        
        challenged_balance = get_user_balance(challenged_id)
        if setup['bet'] > challenged_balance:
            await update.message.reply_text(f"❌ @{username} neturi pakankamai pinigų ir yra bomžas! 💸\n\nBalansas: ${challenged_balance:.2f}")
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
        game_names = {'dice': 'Kauliukai', 'basketball': 'Krepšinis', 'football': 'Futbolas', 'bowling': 'Boulingas'}
        
        initiator_username = update.effective_user.username or "Kažkas"
        mode = context.user_data[f'{game_type}_mode']
        mode_names = {'normal': 'Normalus', 'double': 'Dvigubas', 'crazy': 'Beprotiškas'}
        points = context.user_data[f'{game_type}_points']
        
        text = (
            f"{emoji} **{initiator_username}** išsūkis **@{username}** žaidimui **{game_names[game_type]}**!\n\n"
            f"💰 Statymas: ${setup['bet']:.2f}\n"
            f"📈 Laimėjimo koef.: 1.92x\n"
            f"⚙️ Režimas: {mode_names.get(mode, mode)}\n"
            f"🎯 Iki {points} tšk\n\n"
            f"@{username}, ar priimi?"
        )
        keyboard = [
            [InlineKeyboardButton("✅ Priimti", callback_data=f"{game_type}_accept_{game_id}"),
             InlineKeyboardButton("❌ Atsisakyti", callback_data=f"{game_type}_cancel_challenge_{game_id}")]
        ]
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        
        del context.user_data['expecting_username']
        return True
        
    except Exception as e:
        logger.error(f"Error in challenge: {e}")
        await update.message.reply_text("❌ Klaida apdorojant iššūkį. Bandykite dar kartą.")
        del context.user_data['expecting_username']
        return True


# Export functions
__all__ = [
    'cleargames_command',
    'dice_command',
    'basketball_command',
    'football_command',
    'bowling_command',
    'handle_game_buttons',
    'handle_game_challenge'
]
