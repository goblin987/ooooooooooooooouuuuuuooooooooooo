#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Player Statistics Module
Shows detailed game statistics for each player
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from database import database
from payments import get_user_balance
from points_games import get_user_points

logger = logging.getLogger(__name__)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user statistics in Lithuanian"""
    user_id = update.effective_user.id
    
    try:
        # Get user balance and points
        balance = get_user_balance(user_id)
        points = get_user_points(user_id)
        
        # Get game stats
        stats = database.get_user_stats(user_id)
        rank = database.get_user_rank(user_id)
        
        if not stats:
            # No games played yet
            text = (
                f"📊 Jūsų Statistika\n\n"
                f"💰 Balansas: ${balance:.2f}\n"
                f"⭐ Taškai: {points}\n\n"
                f"Dar nežaidėte jokių žaidimų!\n"
                f"Pradėkite su /dice, /basketball, /football arba /bowling"
            )
        else:
            # Calculate win rate
            win_rate = (stats['games_won'] / stats['games_played'] * 100) if stats['games_played'] > 0 else 0
            
            # Build statistics message in Lithuanian
            text = f"📊 Jūsų Statistika\n\n"
            text += f"💰 Balansas: ${balance:.2f}\n"
            text += f"⭐ Taškai: {points}\n\n"
            text += f"🎮 Žaidimų sužaista: {stats['games_played']}\n"
            text += f"🏆 Žaidimų laimėta: {stats['games_won']} ({win_rate:.1f}%)\n"
            text += f"💸 Iš viso pastatyta: ${stats['total_wagered']:.2f}\n"
            text += f"📈 Didžiausias laimėjimas: ${stats['biggest_win']:.2f}\n"
            text += f"📉 Didžiausias pralaimėjimas: ${abs(stats['biggest_loss']):.2f}\n\n"
            
            # Per-game statistics
            text += "🎲 Žaidimų statistika:\n"
            
            if stats['dice_played'] > 0:
                dice_wr = (stats['dice_won'] / stats['dice_played'] * 100)
                text += f"🎲 Kauliukai: {stats['dice_played']} ({dice_wr:.0f}% laimėta)\n"
            
            if stats['basketball_played'] > 0:
                bb_wr = (stats['basketball_won'] / stats['basketball_played'] * 100)
                text += f"🏀 Krepšinis: {stats['basketball_played']} ({bb_wr:.0f}% laimėta)\n"
            
            if stats['football_played'] > 0:
                fb_wr = (stats['football_won'] / stats['football_played'] * 100)
                text += f"⚽ Futbolas: {stats['football_played']} ({fb_wr:.0f}% laimėta)\n"
            
            if stats['bowling_played'] > 0:
                bw_wr = (stats['bowling_won'] / stats['bowling_played'] * 100)
                text += f"🎳 Boulingas: {stats['bowling_played']} ({bw_wr:.0f}% laimėta)\n"
            
            # Streak and rank
            text += f"\n🔥 Dabartinė serija: {abs(stats['current_streak'])} "
            if stats['current_streak'] > 0:
                text += "laimėjimai"
            elif stats['current_streak'] < 0:
                text += "pralaimėjimai"
            else:
                text += "(nėra)"
            
            text += f"\n🏅 Reitingas: #{rank}"
        
        # Send the stats message
        msg = await update.message.reply_text(text)
        
        # Schedule deletion after 5 minutes
        context.job_queue.run_once(
            delete_stats_message,
            when=300,  # 5 minutes
            data={'chat_id': update.effective_chat.id, 'message_id': msg.message_id},
            name=f"delete_stats_{msg.message_id}"
        )
        
        logger.info(f"Stats shown for user {user_id}, scheduled for deletion in 5 minutes")
        
    except Exception as e:
        logger.error(f"Error showing stats: {e}")
        await update.message.reply_text("❌ Klaida rodant statistiką. Bandykite dar kartą.")


async def delete_stats_message(context: ContextTypes.DEFAULT_TYPE):
    """Delete stats message after 5 minutes"""
    job = context.job
    chat_id = job.data['chat_id']
    message_id = job.data['message_id']
    
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"Deleted stats message {message_id} from chat {chat_id}")
    except Exception as e:
        logger.debug(f"Could not delete stats message {message_id}: {e}")


__all__ = ['stats_command']

