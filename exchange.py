#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Points Exchange System - Button-driven flow for converting points to crypto
Dummy-proof UI with multiple validation layers
"""

import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import database
import levels

logger = logging.getLogger(__name__)

# Exchange configuration (dynamic rate loaded from database)
MAX_WEEKLY_USD = 10   # $10 weekly limit per user
MIN_LEVEL = 1         # minimum level to exchange (allow from level 1)
MIN_ACCOUNT_AGE = 0   # no account age restriction

def get_exchange_rate():
    """Get current exchange rate from database"""
    return database.get_exchange_rate()

def get_min_exchange():
    """Get minimum exchange amount (always $1 worth of points)"""
    return get_exchange_rate()  # $1 minimum


def can_exchange(user_id: int) -> tuple:
    """Check if user meets basic requirements to exchange"""
    # Level requirement (always allow, just show warning if low level)
    level = database.get_user_level(user_id)
    
    # Always return True to show menu, validation happens at transaction time
    return True, None


async def exchange_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main exchange command - shows amount selection directly"""
    user_id = update.effective_user.id
    
    # Always show exchange menu (validation happens when selecting amount)
    
    # Get user stats
    user_points = levels.get_user_money(user_id)
    crypto_balance = database.get_user_balance(user_id)
    week_num = datetime.now().isocalendar()[1]
    weekly_used = database.get_weekly_exchange_total(user_id, week_num)
    weekly_remaining = MAX_WEEKLY_USD - weekly_used
    exchange_rate = get_exchange_rate()
    max_points_can_exchange = int(weekly_remaining * exchange_rate)
    
    text = (
        f"💱 <b>Keisti Taškus</b>\n\n"
        f"💎 Jūsų taškai: <b>{user_points:,}</b>\n"
        f"💵 Kripto balansas: <b>${crypto_balance:.2f}</b>\n\n"
        f"💡 Kursas: <b>{exchange_rate:,} taškų = $1.00 USD</b>\n\n"
        f"Pasirinkite sumą:"
    )
    
    keyboard = []
    
    # Preset amounts (dynamically calculated)
    presets = [
        (exchange_rate * 1, 1.00),    # $1
        (exchange_rate * 2, 2.00),    # $2
        (exchange_rate * 3, 3.00),    # $3
        (exchange_rate * 5, 5.00)     # $5
    ]
    
    for points, usd in presets:
        if points <= user_points and points <= max_points_can_exchange:
            keyboard.append([InlineKeyboardButton(
                f"💎 {points:,} pts → ${usd:.2f}",
                callback_data=f"exchange_select_{points}"
            )])
    
    if not keyboard:
        text += "\n\n⚠️ Nepakanka taškų arba pasiektas savaitinis limitas"
    
    keyboard.append([InlineKeyboardButton("🔙 Atgal", callback_data="exchange_back")])
    
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


async def show_main_menu(query, user_id: int):
    """Show main start menu (for back button)"""
    user_points = levels.get_user_money(user_id)
    crypto_balance = database.get_user_balance(user_id)
    level = database.get_user_level(user_id)
    
    text = (
        f"🤖 <b>ApsisaugokRobot</b>\n\n"
        f"📊 Jūsų statistika:\n"
        f"• Lygis: {level}\n"
        f"• Taškai: {user_points:,}\n"
        f"• Kripto: ${crypto_balance:.2f}\n\n"
        f"Pasirinkite funkciją:"
    )
    
    keyboard = [
        [InlineKeyboardButton("💰 Piniginė", callback_data="start_pinigine")],
        [InlineKeyboardButton("💱 Keisti Taškus", callback_data="exchange_start")],
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


async def handle_exchange_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all exchange button callbacks"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    if not data.startswith('exchange_'):
        return False
    
    # Main menu / start
    if data == "exchange_start":
        await show_amount_selection(query, context, user_id)
        return True
    
    # Amount selection buttons
    elif data.startswith("exchange_select_"):
        points_str = data.replace("exchange_select_", "")
        try:
            points_amount = int(points_str)
            await show_confirmation(query, context, user_id, points_amount)
        except ValueError:
            await query.answer("❌ Klaida!", show_alert=True)
        return True
    
    # Confirmation
    elif data.startswith("exchange_confirm_"):
        points_str = data.replace("exchange_confirm_", "")
        try:
            points_amount = int(points_str)
            await process_exchange(query, context, user_id, points_amount)
        except ValueError:
            await query.answer("❌ Klaida!", show_alert=True)
        return True
    
    # Cancel
    elif data == "exchange_cancel":
        await query.edit_message_text("❌ Keitimas atšauktas.")
        return True
    
    # Close
    elif data == "exchange_close":
        await query.delete_message()
        return True
    
    # History
    elif data == "exchange_history":
        await show_exchange_history(query, user_id)
        return True
    
    # Back to main menu
    elif data == "exchange_back":
        await show_main_menu(query, user_id)
        return True
    
    return False


async def show_amount_selection(query, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    """Show amount selection buttons"""
    user_points = levels.get_user_money(user_id)
    week_num = datetime.now().isocalendar()[1]
    weekly_used = database.get_weekly_exchange_total(user_id, week_num)
    weekly_remaining = MAX_WEEKLY_USD - weekly_used
    exchange_rate = get_exchange_rate()
    max_points_can_exchange = int(weekly_remaining * exchange_rate)
    
    text = (
        f"💱 <b>Pasirinkite Sumą</b>\n\n"
        f"💎 Turimi taškai: <b>{user_points:,}</b>\n\n"
        f"Pasirinkite keitimo sumą:"
    )
    
    keyboard = []
    
    # Preset amounts (dynamically calculated based on current rate)
    presets = [
        (exchange_rate * 1, 1.00),    # $1
        (exchange_rate * 2, 2.00),    # $2
        (exchange_rate * 3, 3.00),    # $3
        (exchange_rate * 5, 5.00)     # $5
    ]
    
    for points, usd in presets:
        if points <= user_points and points <= max_points_can_exchange:
            keyboard.append([InlineKeyboardButton(
                f"💎 {points:,} pts → ${usd:.2f}",
                callback_data=f"exchange_select_{points}"
            )])
    
    if not keyboard:
        text += "\n\n⚠️ Nepakanka taškų arba pasiektas savaitinis limitas"
    
    keyboard.append([InlineKeyboardButton("🔙 Atgal", callback_data="exchange_back")])
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


async def show_confirmation(query, context: ContextTypes.DEFAULT_TYPE, user_id: int, points_amount: int):
    """Show confirmation screen with preview"""
    # Re-validate before showing confirmation
    user_points = levels.get_user_money(user_id)
    crypto_balance = database.get_user_balance(user_id)
    usd_amount = points_amount / get_exchange_rate()
    
    if points_amount > user_points:
        await query.answer("❌ Nepakanka taškų!", show_alert=True)
        await show_amount_selection(query, context, user_id)
        return
    
    # Check weekly limit
    week_num = datetime.now().isocalendar()[1]
    weekly_used = database.get_weekly_exchange_total(user_id, week_num)
    if weekly_used + usd_amount > MAX_WEEKLY_USD:
        await query.answer("❌ Viršytas savaitinis limitas!", show_alert=True)
        await show_amount_selection(query, context, user_id)
        return
    
    new_points = user_points - points_amount
    new_crypto = crypto_balance + usd_amount
    
    text = (
        f"⚠️ <b>Patvirtinkite Keitimą</b>\n\n"
        f"💎 Išleisti: <b>{points_amount:,}</b> taškų\n"
        f"💵 Gauti: <b>${usd_amount:.2f}</b> USD\n\n"
        f"<b>Po keitimo:</b>\n"
        f"💎 Taškai: {new_points:,}\n"
        f"💵 Kripto: ${new_crypto:.2f}\n\n"
        f"Ar tikrai norite keisti?"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Patvirtinti", callback_data=f"exchange_confirm_{points_amount}")],
        [InlineKeyboardButton("🔙 Atgal", callback_data="exchange_start")]
    ]
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


async def process_exchange(query, context: ContextTypes.DEFAULT_TYPE, user_id: int, points_amount: int):
    """Process the exchange with atomic transaction"""
    usd_amount = points_amount / get_exchange_rate()
    week_num = datetime.now().isocalendar()[1]
    
    # Final validation before processing
    user_points = levels.get_user_money(user_id)
    
    if points_amount > user_points:
        await query.edit_message_text("❌ Klaida: Nepakanka taškų!")
        return
    
    weekly_used = database.get_weekly_exchange_total(user_id, week_num)
    if weekly_used + usd_amount > MAX_WEEKLY_USD:
        await query.edit_message_text("❌ Klaida: Viršytas savaitinis limitas!")
        return
    
    # Process with atomic transaction
    success = database.process_point_exchange(user_id, points_amount, usd_amount, week_num)
    
    if success:
        new_points = levels.get_user_money(user_id)
        new_crypto = database.get_user_balance(user_id)
        
        text = (
            f"✅ <b>Keitimas Sėkmingas!</b>\n\n"
            f"💎 Išleista: <b>{points_amount:,}</b> taškų\n"
            f"💵 Gauta: <b>${usd_amount:.2f}</b> USD\n\n"
            f"<b>Nauji balansai:</b>\n"
            f"💎 Taškai: {new_points:,}\n"
            f"💵 Kripto: ${new_crypto:.2f}\n\n"
            f"Naudokite /pinigine balansui peržiūrėti"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔄 Keisti Dar", callback_data="exchange_start")],
            [InlineKeyboardButton("🔙 Grįžti", callback_data="exchange_back")]
        ]
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        logger.info(f"✅ Exchange successful: User {user_id} exchanged {points_amount} pts for ${usd_amount:.2f}")
    else:
        await query.edit_message_text(
            "❌ Keitimas nepavyko!\n\nPabandykite vėliau arba susisiekite su administratoriumi."
        )
        logger.error(f"❌ Exchange failed for user {user_id}")


async def show_exchange_history(query, user_id: int):
    """Show user's exchange history"""
    try:
        conn = database.get_sync_connection()
        cursor = conn.execute("""
            SELECT points_spent, usd_amount, timestamp 
            FROM point_exchanges 
            WHERE user_id = ? 
            ORDER BY timestamp DESC 
            LIMIT 10
        """, (user_id,))
        
        exchanges = cursor.fetchall()
        conn.close()
        
        if not exchanges:
            text = "📜 <b>Keitimo Istorija</b>\n\nNėra keitimų"
        else:
            text = "📜 <b>Keitimo Istorija</b>\n\n"
            for points, usd, timestamp in exchanges:
                dt = datetime.fromisoformat(timestamp) if isinstance(timestamp, str) else timestamp
                date_str = dt.strftime("%Y-%m-%d %H:%M")
                text += f"• {date_str}\n  {points:,} pts → ${usd:.2f}\n\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Atgal", callback_data="exchange_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Error showing history: {e}")
        await query.answer("❌ Klaida!", show_alert=True)


# Export
__all__ = ['exchange_command', 'handle_exchange_buttons']
