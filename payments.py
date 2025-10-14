#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Payment System - Deposits & Withdrawals (Casino Style)
Automated crypto payments via NOWPayments API
"""

import logging
import sqlite3
import requests
import re
import time
import os
from datetime import datetime, timedelta
from decimal import Decimal
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import database

# Try to import from config, use defaults if not available
try:
    from config import (
        NOWPAYMENTS_API_KEY, 
        NOWPAYMENTS_EMAIL, 
        NOWPAYMENTS_PASSWORD,
        WEBHOOK_URL, 
        BOT_USERNAME, 
        OWNER_ID
    )
except ImportError:
    NOWPAYMENTS_API_KEY = os.environ.get("NOWPAYMENTS_API_KEY", "")
    NOWPAYMENTS_EMAIL = os.environ.get("NOWPAYMENTS_EMAIL", "")
    NOWPAYMENTS_PASSWORD = os.environ.get("NOWPAYMENTS_PASSWORD", "")
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
    BOT_USERNAME = os.environ.get("BOT_USERNAME", "your_bot")
    OWNER_ID = int(os.environ.get("OWNER_ID", "0"))

logger = logging.getLogger(__name__)

# Price cache (currency -> (price, timestamp))
price_cache = {}
CACHE_EXPIRATION_MINUTES = 10
FEE_ADJUSTMENT = 0.015  # 1.5% to cover NOWPayments fees

# ============================================================================
# DATABASE FUNCTIONS
# ============================================================================

def user_exists(user_id: int) -> bool:
    """Check if user exists in database"""
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
        logger.error(f"Error checking user existence: {e}")
        return False


def get_user_balance(user_id: int) -> Decimal:
    """Get user balance (crypto deposits/withdrawals)"""
    try:
        conn = database.get_sync_connection()
        cursor = conn.execute(
            "SELECT balance FROM users WHERE user_id = ?",  # ← FIXED: Use 'balance' column, not 'points'
            (user_id,)
        )
        result = cursor.fetchone()
        conn.close()
        return Decimal(str(result[0])) if result else Decimal('0.0')
    except Exception as e:
        logger.error(f"Error getting balance: {e}")
        return Decimal('0.0')


def update_user_balance(user_id: int, new_balance: Decimal):
    """Update user balance (crypto deposits/withdrawals)"""
    try:
        conn = database.get_sync_connection()
        conn.execute(
            "INSERT OR REPLACE INTO users (user_id, balance) VALUES (?, ?)",  # ← FIXED: Use 'balance' column
            (user_id, float(new_balance))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error updating balance: {e}")


def add_pending_deposit(payment_id: str, user_id: int, currency: str):
    """Add pending deposit record"""
    try:
        conn = database.get_sync_connection()
        conn.execute(
            "CREATE TABLE IF NOT EXISTS pending_deposits "
            "(payment_id TEXT PRIMARY KEY, user_id INTEGER, currency TEXT)"
        )
        conn.execute(
            "INSERT INTO pending_deposits (payment_id, user_id, currency) VALUES (?, ?, ?)",
            (payment_id, user_id, currency)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error adding pending deposit: {e}")


def get_pending_deposit(payment_id: str):
    """Get pending deposit"""
    try:
        conn = database.get_sync_connection()
        cursor = conn.execute(
            "SELECT user_id, currency FROM pending_deposits WHERE payment_id = ?",
            (payment_id,)
        )
        result = cursor.fetchone()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"Error getting pending deposit: {e}")
        return None


def remove_pending_deposit(payment_id: str):
    """Remove pending deposit"""
    try:
        conn = database.get_sync_connection()
        conn.execute(
            "DELETE FROM pending_deposits WHERE payment_id = ?",
            (payment_id,)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error removing pending deposit: {e}")


def get_user_by_username(username: str):
    """Get user ID by username (from user_cache table)"""
    try:
        # Use database.get_user_by_username which uses user_cache table
        return database.get_user_by_username(username)
    except Exception as e:
        logger.error(f"Error getting user by username: {e}")
        return None


# ============================================================================
# NOWPAYMENTS API
# ============================================================================

def get_currency_to_usd_price(currency: str) -> float:
    """Get crypto price in USD (with aggressive caching to avoid delays)"""
    try:
        # Always check cache first
        if currency in price_cache:
            price, timestamp = price_cache[currency]
            # Use cache if less than 5 minutes old
            if datetime.now() - timestamp < timedelta(minutes=5):
                logger.info(f"Using cached price for {currency}: ${price}")
                return price
            # Use stale cache if less than 30 minutes old (avoid delays)
            elif datetime.now() - timestamp < timedelta(minutes=30):
                logger.info(f"Using stale cached price for {currency}: ${price} (avoiding API delay)")
                return price

        currency_map = {
            'sol': 'solana',
            'usdt_trx': 'tether',
            'usdt_eth': 'tether',
            'btc': 'bitcoin',
            'eth': 'ethereum',
            'ltc': 'litecoin'
        }
        
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={currency_map[currency]}&vs_currencies=usd"
        response = requests.get(url, timeout=3)  # 3 second timeout
        
        if response.status_code == 429:
            logger.warning("Rate limit exceeded, using cached price")
            # Don't wait - immediately return cached value
            if currency in price_cache:
                price, _ = price_cache[currency]
                return price
            return 1.0
        
        response.raise_for_status()
        data = response.json()
        price = data[currency_map[currency]]['usd']
        price_cache[currency] = (price, datetime.now())
        logger.info(f"Fetched new price for {currency}: ${price}")
        return price
    except Exception as e:
        logger.error(f"Failed to fetch {currency} price: {e}")
        if currency in price_cache:
            price, _ = price_cache[currency]
            logger.info(f"Using cached price due to error: ${price}")
            return price
        return 1.0


def create_deposit_payment(user_id: int, currency: str = 'ltc'):
    """Create deposit payment via NOWPayments"""
    try:
        min_deposit_usd = 12.0  # Minimum deposit amount
        currency_price = get_currency_to_usd_price(currency)
        min_deposit_currency = min_deposit_usd / currency_price
        
        url = "https://api.nowpayments.io/v1/payment"
        headers = {"x-api-key": NOWPAYMENTS_API_KEY}
        payload = {
            "price_amount": min_deposit_usd,  # Amount in USD
            "price_currency": "usd",  # We want to receive USD value
            "pay_currency": currency,  # User pays in crypto
            "ipn_callback_url": f"{WEBHOOK_URL}/webhook/nowpayments",
            "order_id": f"deposit_{user_id}_{int(time.time())}",
        }
        
        logger.info(f"Sending deposit request for user_id: {user_id}")
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if 'pay_address' not in data or 'payment_id' not in data:
            logger.error(f"Invalid response from NOWPayments: {data}")
            raise ValueError("Invalid response from NOWPayments")
        
        logger.info(f"Received deposit response for user_id: {user_id}")
        return data
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        if e.response is not None:
            logger.error(f"Response content: {e.response.text}")
        raise
    except Exception as e:
        logger.error(f"Deposit creation failed: {e}")
        raise


def format_expiration_time(expiration_date_str: str) -> str:
    """Format expiration time"""
    try:
        expiration_time = datetime.strptime(expiration_date_str, "%Y-%m-%dT%H:%M:%S.%fZ")
        now = datetime.utcnow()
        time_left = expiration_time - now
        minutes, seconds = divmod(int(time_left.total_seconds()), 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:01d}:{minutes:02d}:{seconds:02d}"
    except:
        return "1:00:00"


def is_valid_ltc_address(address: str) -> bool:
    """Validate LTC address"""
    pattern = r'^(L|M|ltc1)[a-zA-Z0-9]{25,40}$'
    return re.match(pattern, address) is not None


def get_jwt_token() -> str:
    """Get JWT token from NOWPayments"""
    url = "https://api.nowpayments.io/v1/auth"
    
    if not NOWPAYMENTS_EMAIL or not NOWPAYMENTS_PASSWORD:
        logger.error("NOWPAYMENTS_EMAIL or NOWPAYMENTS_PASSWORD not set")
        raise ValueError("Missing NOWPAYMENTS credentials")
    
    email = NOWPAYMENTS_EMAIL
    password = NOWPAYMENTS_PASSWORD
    
    payload = {"email": email, "password": password}
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        if "token" in data:
            logger.info("JWT token obtained successfully")
            return data["token"]
        else:
            raise Exception("No token in response")
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to get JWT token: {e}")
        raise


def initiate_payout(currency: str, amount: float, address: str):
    """Initiate withdrawal payout"""
    url = "https://api.nowpayments.io/v1/payout"
    
    try:
        token = get_jwt_token()
        headers = {
            "x-api-key": NOWPAYMENTS_API_KEY,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        payload = {
            "withdrawals": [
                {
                    "address": address,
                    "currency": currency,
                    "amount": float(amount),
                    "ipn_callback_url": f"{WEBHOOK_URL}/webhook/nowpayments"
                }
            ]
        }
        
        logger.info(f"Sending payout request for address: {address}")
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        logger.info(f"Payout successful: {data}")
        return data
    except requests.exceptions.RequestException as e:
        logger.error(f"Payout request failed: {e}")
        if e.response is not None:
            logger.error(f"Response content: {e.response.text}")
        return {"status": "error", "message": str(e)}


# ============================================================================
# COMMAND HANDLERS
# ============================================================================

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show balance with deposit/withdraw buttons (works in groups and private)"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    balance = get_user_balance(user_id)
    text = f"💰 <b>Jūsų balansas:</b> ${balance:.2f}\n\n" \
          f"<i>Pasirinkite veiksmą apačioje:</i>"
    
    keyboard = [
        [InlineKeyboardButton("💵 Įnešti", callback_data="deposit"),
         InlineKeyboardButton("💸 Išimti", callback_data="withdraw")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode='HTML')


async def add_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only: Add balance to user"""
    # ONLY the owner can add balance (prevent abuse)
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text(f"❌ Unauthorized\n\nOnly the bot owner can add balance.\nYour ID: {update.effective_user.id}")
        return
    
    if len(context.args) != 2:
        await update.message.reply_text(
            "Usage: `/addbalance <username> <amount>`\n"
            "Example: `/addbalance @user 100`",
            parse_mode='Markdown'
        )
        return
    
    username = context.args[0].lstrip('@')
    
    try:
        amount = Decimal(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid amount")
        return
    
    if amount <= 0:
        await update.message.reply_text("❌ Amount must be greater than 0")
        return
    
    target_user = get_user_by_username(username)
    if not target_user:
        await update.message.reply_text(f"❌ User @{username} not found in cache.\n\nThey need to send at least one message in a group where the bot is present.")
        return
    
    # Extract user_id from the returned dict
    target_user_id = target_user if isinstance(target_user, int) else target_user.get('user_id') if isinstance(target_user, dict) else target_user
    
    logger.info(f"Adding balance to user {target_user_id} (@{username})")
    current_balance = get_user_balance(target_user_id)
    logger.info(f"Current balance for {target_user_id}: ${current_balance}")
    new_balance = current_balance + amount
    update_user_balance(target_user_id, new_balance)
    logger.info(f"Updated balance for {target_user_id}: ${new_balance}")
    
    # Verify the update
    verify_balance = get_user_balance(target_user_id)
    logger.info(f"Verified balance for {target_user_id}: ${verify_balance}")
    
    await update.message.reply_text(
        f"✅ Added ${amount:.2f} to @{username} (ID: {target_user_id})\n"
        f"New balance: ${new_balance:.2f}\n\n"
        f"Verified: ${verify_balance:.2f}"
    )


async def remove_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only: Remove balance from user"""
    # ONLY the owner can remove balance (prevent abuse)
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text(f"❌ Unauthorized\n\nOnly the bot owner can remove balance.\nYour ID: {update.effective_user.id}")
        return
    
    if len(context.args) != 2:
        await update.message.reply_text(
            "Usage: `/removebalance <username> <amount>`\n"
            "Example: `/removebalance @user 50`",
            parse_mode='Markdown'
        )
        return
    
    username = context.args[0].lstrip('@')
    
    try:
        amount = Decimal(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid amount")
        return
    
    if amount <= 0:
        await update.message.reply_text("❌ Amount must be greater than 0")
        return
    
    target_user = get_user_by_username(username)
    if not target_user:
        await update.message.reply_text(f"❌ User @{username} not found")
        return
    
    # Extract user_id from the returned dict
    target_user_id = target_user if isinstance(target_user, int) else target_user.get('user_id') if isinstance(target_user, dict) else target_user
    
    current_balance = get_user_balance(target_user_id)
    new_balance = current_balance - amount
    update_user_balance(target_user_id, new_balance)
    
    await update.message.reply_text(
        f"✅ Removed ${amount:.2f} from @{username}\n"
        f"New balance: ${new_balance:.2f}"
    )
    
    logger.info(f"Admin removed ${amount:.2f} from @{username}. New balance: ${new_balance:.2f}")


# ============================================================================
# BUTTON HANDLERS
# ============================================================================

async def handle_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle deposit/withdraw button callbacks"""
    query = update.callback_query
    
    # Safely answer callback query (handle timeout errors)
    try:
        await query.answer()
    except Exception as e:
        logger.warning(f"Failed to answer callback query: {e}")
    
    data = query.data
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    
    if data == "deposit":
        if update.effective_chat.type != 'private':
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"💰 <b>Įnešimas</b>\n\n"
                     f"Dėl privatumo, įnešimai atliekami privačiame pokalbyje.\n\n"
                     f"Pradėkite pokalbį su manimi: t.me/{BOT_USERNAME}",
                parse_mode='HTML'
            )
        else:
            text = "💳 <b>Įnešimas</b>\n\nPasirinkite kriptovaliutą:"
            keyboard = [
                [InlineKeyboardButton("SOLANA", callback_data="deposit_sol"),
                 InlineKeyboardButton("USDT TRX", callback_data="deposit_usdt_trx")],
                [InlineKeyboardButton("USDT ETH", callback_data="deposit_usdt_eth"),
                 InlineKeyboardButton("BTC", callback_data="deposit_btc")],
                [InlineKeyboardButton("ETH", callback_data="deposit_eth"),
                 InlineKeyboardButton("LTC", callback_data="deposit_ltc")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode='HTML')
    
    elif data.startswith("deposit_"):
        currency = data.split("_", 1)[1]
        
        try:
            payment_data = create_deposit_payment(user_id, currency)
            address = payment_data['pay_address']
            payment_id = payment_data['payment_id']
            expiration_time = payment_data.get('expiration_estimate_date', '')
            expires_in = format_expiration_time(expiration_time) if expiration_time else "1:00:00"
            
            add_pending_deposit(payment_id, user_id, currency)
            
            # Calculate minimum amount in crypto (must match create_deposit_payment)
            min_usd = 12.0
            currency_price = get_currency_to_usd_price(currency)
            min_crypto = min_usd / currency_price
            
            # Generate QR code for payment
            import qrcode
            from io import BytesIO
            
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(address)
            qr.make(fit=True)
            qr_img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to bytes
            qr_bytes = BytesIO()
            qr_img.save(qr_bytes, format='PNG')
            qr_bytes.seek(0)
            
            # Get expiration in minutes
            expires_minutes = expires_in.split(':')[1] if ':' in expires_in else "60"
            
            text = (
                f"✅ <b>Mokėjimo patvirtinimas yra automatiškas per webhook po tinklo patvirtinimo.</b>\n\n"
                f"❌ <b>Cancel Payment</b>\n\n"
                f"📱 <b>Scan QR Code for Easy Payment</b>\n\n"
                f"💵 <b>Minimalus įnešimas:</b> $12 USD\n\n"
                f"<i>Bet kokia suma virš $12 bus automatiškai pridėta į jūsų piniginę.</i>\n\n"
                f"📍 <b>Address:</b>\n<code>{address}</code>\n\n"
                f"⏰ <b>Galioja:</b> {expires_minutes} minutes\n\n"
                f"⚠️ <b>Sumokėkite per {expires_minutes} minutes, kitaip sąskaita nustos galioti!</b>"
            )
            
            # Create cancel button
            keyboard = [[InlineKeyboardButton("❌ Cancel Payment", callback_data=f"cancel_deposit_{payment_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Send QR code with text
            await context.bot.send_photo(
                chat_id=chat_id,
                photo=qr_bytes,
                caption=text,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg:
                await context.bot.send_message(chat_id=chat_id, text="❌ API raktas neteisingas. Susisiekite su palaikymu.")
            elif "AMOUNT_MINIMAL_ERROR" in error_msg or "amount" in error_msg.lower():
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text="❌ Suma per maža.\n\n"
                         "Minimalus įnešimas: <b>$10 USD</b>\n\n"
                         "Bandykite dar kartą.",
                    parse_mode='HTML'
                )
            elif "400" in error_msg:
                await context.bot.send_message(chat_id=chat_id, text="❌ Neteisinga užklausa. Bandykite vėliau.")
            else:
                await context.bot.send_message(chat_id=chat_id, text=f"❌ Nepavyko sugeneruoti adreso: {error_msg}")
    
    elif data.startswith("cancel_deposit_"):
        payment_id = data.replace("cancel_deposit_", "")
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Mokėjimas atšauktas."
        )
        # Optionally delete the payment message
        try:
            await query.message.delete()
        except:
            pass
    
    elif data == "withdraw":
        if update.effective_chat.type != 'private':
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"💸 <b>Išėmimas</b>\n\n"
                     f"Dėl privatumo, išėmimai atliekami privačiame pokalbyje.\n\n"
                     f"Pradėkite pokalbį su manimi: t.me/{BOT_USERNAME}",
                parse_mode='HTML'
            )
        else:
            context.user_data['expecting_withdrawal_details'] = True
            await context.bot.send_message(
                chat_id=chat_id,
                text="💸 <b>Išėmimas</b>\n\n"
                     "Įveskite sumą USD ir savo SOLANA adresą:\n"
                     "Formatas: <code>suma adresas</code>\n\n"
                     "Pavyzdys: <code>10.00 GnTV2g5D6zqXTuoPCR2UNB9SDJSUx...</code>\n\n"
                     "<i>Pastaba: Palaikomi tik SOLANA išėmimai.</i>",
                parse_mode='HTML'
            )


# ============================================================================
# TEXT HANDLER (Withdrawal)
# ============================================================================

async def handle_withdrawal_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handle withdrawal text input"""
    if update.effective_chat.type == 'private' and context.user_data.get('expecting_withdrawal_details'):
        try:
            parts = update.message.text.strip().split()
            if len(parts) < 2:
                raise ValueError("❌ Įveskite 'suma adresas', pvz.: '10.00 GnTV2g5D6...'")
            
            amount_usd = Decimal(parts[0])
            address = parts[1]
            currency = 'sol'  # Changed to SOLANA
            
            # Basic SOLANA address validation (32-44 characters, base58)
            if not (32 <= len(address) <= 44):
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ Neteisingas SOLANA adresas. Patikrinkite ir bandykite dar kartą."
                )
                return True
            
            balance = get_user_balance(update.effective_user.id)
            if amount_usd > balance:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"❌ Nepakanka lėšų išėmimui\n\n"
                         f"Jūsų balansas: ${balance:.2f}\n"
                         f"Norite išimti: ${amount_usd:.2f}"
                )
                return True
            
            sol_price_usd = get_currency_to_usd_price(currency)
            if sol_price_usd == 0:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ Nepavyko gauti SOLANA kainos. Bandykite vėliau."
                )
                return True
            
            sol_amount = float(amount_usd / Decimal(str(sol_price_usd)))
            payout_response = initiate_payout(currency, sol_amount, address)
            
            if payout_response.get('status') == 'error':
                error_msg = payout_response.get('message', 'Nežinoma klaida')
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"❌ Išėmimas nepavyko: {error_msg}"
                )
            else:
                new_balance = balance - amount_usd
                update_user_balance(update.effective_user.id, new_balance)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"✅ <b>Išėmimas sėkmingas!</b>\n\n"
                         f"Suma: ${amount_usd:.2f}\n"
                         f"Adresas: <code>{address}</code>\n"
                         f"Naujas balansas: ${new_balance:.2f}",
                    parse_mode='HTML'
                )
            
            context.user_data['expecting_withdrawal_details'] = False
            return True
        except ValueError as ve:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=str(ve))
            return True
        except Exception as e:
            logger.error(f"Withdrawal error: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Įvyko klaida. Bandykite dar kartą arba susisiekite su palaikymu."
            )
            return True
    
    return False


# Export functions
__all__ = [
    'balance_command',
    'add_balance_command',
    'remove_balance_command',
    'handle_payment_callback',
    'handle_withdrawal_text'
]

