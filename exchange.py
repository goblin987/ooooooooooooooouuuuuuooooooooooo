#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Points Exchange System - Convert earned points to crypto balance
Includes anti-spam measures and weekly limits
"""

import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes
from database import database
import levels

logger = logging.getLogger(__name__)

# Exchange configuration
EXCHANGE_RATE = 2000  # points per $1 USD
MIN_EXCHANGE = 2000   # $1 minimum
MAX_WEEKLY_USD = 10   # $10 weekly limit per user
MIN_LEVEL = 15        # minimum level to exchange
MIN_ACCOUNT_AGE = 30  # minimum account age in days


async def exchange_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Exchange points for crypto balance"""
    user_id = update.effective_user.id
    
    # Show info if no arguments
    if not context.args:
        return await show_exchange_info(update, user_id)
    
    # Parse amount
    try:
        points_amount = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Neteisingas kiekis! Naudokite skaičių.")
        return
    
    # Validation: minimum exchange
    if points_amount < MIN_EXCHANGE:
        await update.message.reply_text(
            f"❌ Minimalus keitimas: {MIN_EXCHANGE:,} taškų ($1 USD)\n\n"
            f"Jūsų taškai: {levels.get_user_money(user_id):,}"
        )
        return
    
    # Check if valid increment
    if points_amount % MIN_EXCHANGE != 0:
        await update.message.reply_text(
            f"❌ Suma turi būti {MIN_EXCHANGE:,} kartotinis\n"
            f"Pavyzdžiai: 2000, 4000, 10000"
        )
        return
    
    # Account age check
    account_age = database.get_account_age_days(user_id)
    if account_age < MIN_ACCOUNT_AGE:
        await update.message.reply_text(
            f"❌ Paskyra turi būti {MIN_ACCOUNT_AGE}+ dienų sena\n\n"
            f"Jūsų paskyros amžius: {account_age} dienų\n"
            f"Liko: {MIN_ACCOUNT_AGE - account_age} dienų"
        )
        return
    
    # Level check
    user_xp = levels.get_user_xp(user_id)
    level, _, _, _ = levels.get_xp_to_next_level(user_xp)
    
    if level < MIN_LEVEL:
        await update.message.reply_text(
            f"❌ Minimalus lygis: {MIN_LEVEL}\n\n"
            f"Jūsų lygis: {level}\n"
            f"Liko: {MIN_LEVEL - level} lygių"
        )
        return
    
    # Weekly limit check
    week_number = datetime.now().isocalendar()[1]
    weekly_used = database.get_weekly_exchange_total(user_id, week_number)
    usd_amount = points_amount / EXCHANGE_RATE
    
    if weekly_used + usd_amount > MAX_WEEKLY_USD:
        remaining = MAX_WEEKLY_USD - weekly_used
        await update.message.reply_text(
            f"❌ Savaitinis limitas: ${MAX_WEEKLY_USD}\n\n"
            f"Šią savaitę panaudota: ${weekly_used:.2f}\n"
            f"Liko: ${remaining:.2f}\n\n"
            f"Limitas atsinaujina pirmadienį"
        )
        return
    
    # Balance check
    user_points = levels.get_user_money(user_id)
    if points_amount > user_points:
        await update.message.reply_text(
            f"❌ Nepakanka taškų!\n\n"
            f"💎 Jūsų taškai: {user_points:,}\n"
            f"💎 Reikia: {points_amount:,}\n"
            f"💎 Trūksta: {points_amount - user_points:,}"
        )
        return
    
    # Process exchange
    success = database.process_point_exchange(user_id, points_amount, usd_amount, week_number)
    
    if success:
        new_crypto = database.get_user_balance(user_id)
        new_points = levels.get_user_money(user_id)
        
        await update.message.reply_text(
            f"✅ Keitimas sėkmingas!\n\n"
            f"💎 Išleista: {points_amount:,} taškų\n"
            f"💵 Gauta: ${usd_amount:.2f} USD\n\n"
            f"💰 Naujas kripto balansas: ${new_crypto:.2f}\n"
            f"💎 Liko taškų: {new_points:,}\n\n"
            f"Naudokite /pinigine balansui peržiūrėti"
        )
        logger.info(f"User {user_id} exchanged {points_amount} points for ${usd_amount:.2f}")
    else:
        await update.message.reply_text("❌ Klaida vykdant keitimą. Bandykite vėliau.")


async def show_exchange_info(update: Update, user_id: int):
    """Show exchange information and user stats"""
    user_points = levels.get_user_money(user_id)
    user_xp = levels.get_user_xp(user_id)
    level, xp_in_level, xp_needed, progress = levels.get_xp_to_next_level(user_xp)
    account_age = database.get_account_age_days(user_id)
    
    week_number = datetime.now().isocalendar()[1]
    weekly_used = database.get_weekly_exchange_total(user_id, week_number)
    weekly_remaining = MAX_WEEKLY_USD - weekly_used
    
    # Check requirements status
    age_ok = "✅" if account_age >= MIN_ACCOUNT_AGE else "❌"
    level_ok = "✅" if level >= MIN_LEVEL else "❌"
    
    # Calculate possible exchanges
    max_points_can_exchange = min(user_points, int(weekly_remaining * EXCHANGE_RATE))
    
    text = (
        f"💱 Taškų Keitimas\n\n"
        f"💎 Jūsų taškai: {user_points:,}\n"
        f"📊 Lygis: {level}\n"
        f"📅 Paskyros amžius: {account_age} dienų\n\n"
        f"💵 Keitimo kursas:\n"
        f"• 2,000 taškų = $1.00 USD\n"
        f"• 4,000 taškų = $2.00 USD\n"
        f"• 10,000 taškų = $5.00 USD\n\n"
        f"📋 Reikalavimai:\n"
        f"{age_ok} Paskyra {MIN_ACCOUNT_AGE}+ dienų (jūsų: {account_age})\n"
        f"{level_ok} Lygis {MIN_LEVEL}+ (jūsų: {level})\n\n"
        f"⚠️ Limitai:\n"
        f"• Maksimalus keitimas: ${MAX_WEEKLY_USD}/savaitę\n"
        f"• Šią savaitę panaudota: ${weekly_used:.2f}\n"
        f"• Liko: ${weekly_remaining:.2f}\n\n"
    )
    
    if account_age >= MIN_ACCOUNT_AGE and level >= MIN_LEVEL:
        if max_points_can_exchange >= MIN_EXCHANGE:
            text += (
                f"✅ Galite keisti iki {max_points_can_exchange:,} taškų\n\n"
                f"📝 Naudojimas:\n"
                f"/exchange <taškai>\n\n"
                f"Pavyzdžiai:\n"
                f"• /exchange 2000 → $1.00\n"
                f"• /exchange 10000 → $5.00"
            )
        else:
            text += f"⚠️ Pasiektas savaitinis limitas arba nepakanka taškų"
    else:
        text += "❌ Neatitinkate reikalavimų keitimui"
    
    await update.message.reply_text(text)


# Export
__all__ = ['exchange_command']

