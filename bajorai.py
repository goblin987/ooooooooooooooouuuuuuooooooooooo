#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bajorai Command - Top Balances & Game Statistics
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from database import database

logger = logging.getLogger(__name__)


async def bajorai_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show top 5 balances and total games played statistics"""
    
    try:
        conn = database.get_sync_connection()
        
        # Get top 5 users by balance
        cursor = conn.execute("""
            SELECT u.user_id, u.username, u.balance
            FROM users u
            WHERE u.balance > 0
            ORDER BY u.balance DESC
            LIMIT 5
        """)
        top_balances = cursor.fetchall()
        
        # Get total games statistics
        cursor = conn.execute("""
            SELECT 
                SUM(dice_played) as total_dice,
                SUM(dice_won) as total_dice_won,
                SUM(basketball_played) as total_basketball,
                SUM(basketball_won) as total_basketball_won,
                SUM(football_played) as total_football,
                SUM(football_won) as total_football_won,
                SUM(bowling_played) as total_bowling,
                SUM(bowling_won) as total_bowling_won
            FROM game_stats
        """)
        game_stats = cursor.fetchone()
        
        conn.close()
        
        # Format the message - Clean and minimalistic
        message = "💰 <b>BAJORAI</b>\n\n"
        
        # Top 5 Balances
        message += "<b>TOP 5 BALANSAI:</b>\n"
        if top_balances:
            for i, (user_id, username, balance) in enumerate(top_balances, 1):
                # Get username from cache if not in users table
                if not username:
                    user_info = database.get_user_by_id(user_id)
                    username = user_info.get('username', f'user_{user_id}') if user_info else f'user_{user_id}'
                
                # Emoji for top 3
                if i == 1:
                    emoji = "🥇"
                elif i == 2:
                    emoji = "🥈"
                elif i == 3:
                    emoji = "🥉"
                else:
                    emoji = f"  {i}."
                
                message += f"{emoji} @{username} - ${balance:.2f}\n"
        else:
            message += "<i>Nėra balansų</i>\n"
        
        message += "\n<b>ŽAIDIMAI:</b>\n"
        
        if game_stats:
            total_dice = game_stats[0] or 0
            total_dice_won = game_stats[1] or 0
            total_basketball = game_stats[2] or 0
            total_basketball_won = game_stats[3] or 0
            total_football = game_stats[4] or 0
            total_football_won = game_stats[5] or 0
            total_bowling = game_stats[6] or 0
            total_bowling_won = game_stats[7] or 0
            
            # Calculate win rates
            dice_wr = (total_dice_won / total_dice * 100) if total_dice > 0 else 0
            basketball_wr = (total_basketball_won / total_basketball * 100) if total_basketball > 0 else 0
            football_wr = (total_football_won / total_football * 100) if total_football > 0 else 0
            bowling_wr = (total_bowling_won / total_bowling * 100) if total_bowling > 0 else 0
            
            message += f"🎲 Dice: {total_dice} žaidimų ({dice_wr:.1f}%)\n"
            message += f"🏀 Basketball: {total_basketball} žaidimų ({basketball_wr:.1f}%)\n"
            message += f"⚽ Football: {total_football} žaidimų ({football_wr:.1f}%)\n"
            message += f"🎳 Bowling: {total_bowling} žaidimų ({bowling_wr:.1f}%)\n"
            
            # Total games
            total_games = total_dice + total_basketball + total_football + total_bowling
            total_wins = total_dice_won + total_basketball_won + total_football_won + total_bowling_won
            overall_wr = (total_wins / total_games * 100) if total_games > 0 else 0
            
            message += f"\n📊 Viso: {total_games} žaidimų ({overall_wr:.1f}% laimėta)"
        else:
            message += "<i>Nėra žaidimų</i>"
        
        await update.message.reply_text(message, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error in bajorai command: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ Klaida gaunant statistiką. Bandykite vėliau."
        )


# Export
__all__ = ['bajorai_command']

