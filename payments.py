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
    from config import NOWPAYMENTS_API_KEY, WEBHOOK_URL, BOT_USERNAME, OWNER_ID
except ImportError:
    NOWPAYMENTS_API_KEY = os.environ.get("NOWPAYMENTS_API_KEY", "")
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

def get_user_balance(user_id: int) -> Decimal:
    """Get user balance"""
    try:
        conn = database.get_sync_connection()
        cursor = conn.execute(
            "SELECT points FROM users WHERE user_id = ?",
            (user_id,)
        )
        result = cursor.fetchone()
        conn.close()
        return Decimal(str(result[0])) if result else Decimal('0.0')
    except Exception as e:
        logger.error(f"Error getting balance: {e}")
        return Decimal('0.0')


def update_user_balance(user_id: int, new_balance: Decimal):
    """Update user balance"""
    try:
        conn = database.get_sync_connection()
        conn.execute(
            "INSERT OR REPLACE INTO users (user_id, points) VALUES (?, ?)",
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
    """Get user ID by username"""
    try:
        conn = database.get_sync_connection()
        # Assuming we need to check the database for username
        # This might need adjustment based on your actual database schema
        cursor = conn.execute(
            "SELECT user_id FROM users WHERE username = ? COLLATE NOCASE",
            (username,)
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
    except Exception as e:
        logger.error(f"Error getting user by username: {e}")
        return None


# ============================================================================
# NOWPAYMENTS API
# ============================================================================

def get_currency_to_usd_price(currency: str) -> float:
    """Get crypto price in USD"""
    try:
        if currency in price_cache:
            price, timestamp = price_cache[currency]
            if datetime.now() - timestamp < timedelta(minutes=CACHE_EXPIRATION_MINUTES):
                logger.info(f"Using cached price for {currency}: ${price}")
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
        response = requests.get(url)
        
        if response.status_code == 429:
            logger.warning("Rate limit exceeded, waiting 60 seconds")
            time.sleep(60)
            response = requests.get(url)
        
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
            return price
        return 1.0


def create_deposit_payment(user_id: int, currency: str = 'ltc'):
    """Create deposit payment via NOWPayments"""
    try:
        min_deposit_usd = 1.0
        currency_price = get_currency_to_usd_price(currency)
        min_deposit_currency = min_deposit_usd / currency_price
        
        url = "https://api.nowpayments.io/v1/payment"
        headers = {"x-api-key": NOWPAYMENTS_API_KEY}
        payload = {
            "price_amount": min_deposit_currency,
            "price_currency": currency,
            "pay_currency": currency,
            "ipn_callback_url": f"{WEBHOOK_URL}/webhook",
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
    email = os.environ.get("NOWPAYMENTS_EMAIL")
    password = os.environ.get("NOWPAYMENTS_PASSWORD")
    
    if not email or not password:
        logger.error("NOWPAYMENTS_EMAIL or NOWPAYMENTS_PASSWORD not set")
        raise ValueError("Missing NOWPAYMENTS credentials")
    
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
                    "ipn_callback_url": f"{WEBHOOK_URL}/payout_webhook"
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
    """Show balance with deposit/withdraw buttons"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    balance = get_user_balance(user_id)
    text = f"💰 Your balance: ${balance:.2f}"
    
    keyboard = [
        [InlineKeyboardButton("💵 Deposit", callback_data="deposit"),
         InlineKeyboardButton("💸 Withdraw", callback_data="withdraw")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


async def add_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only: Add balance to user"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Unauthorized")
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
    
    target_user_id = get_user_by_username(username)
    if not target_user_id:
        await update.message.reply_text(f"❌ User @{username} not found")
        return
    
    current_balance = get_user_balance(target_user_id)
    new_balance = current_balance + amount
    update_user_balance(target_user_id, new_balance)
    
    await update.message.reply_text(
        f"✅ Added ${amount:.2f} to @{username}\n"
        f"New balance: ${new_balance:.2f}"
    )


async def remove_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only: Remove balance from user"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Unauthorized")
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
    
    target_user_id = get_user_by_username(username)
    if not target_user_id:
        await update.message.reply_text(f"❌ User @{username} not found")
        return
    
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
    await query.answer()
    
    data = query.data
    chat_id = query.message.chat_id
    user_id = query.from_user.id
    
    if data == "deposit":
        if update.effective_chat.type != 'private':
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Please start a private chat with me: t.me/{BOT_USERNAME}"
            )
        else:
            text = "💳 **Deposit**\n\nChoose your preferred deposit method:"
            keyboard = [
                [InlineKeyboardButton("SOLANA", callback_data="deposit_sol"),
                 InlineKeyboardButton("USDT TRX", callback_data="deposit_usdt_trx")],
                [InlineKeyboardButton("USDT ETH", callback_data="deposit_usdt_eth"),
                 InlineKeyboardButton("BTC", callback_data="deposit_btc")],
                [InlineKeyboardButton("ETH", callback_data="deposit_eth"),
                 InlineKeyboardButton("LTC", callback_data="deposit_ltc")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup, parse_mode='Markdown')
    
    elif data.startswith("deposit_"):
        currency = data.split("_", 1)[1]
        
        try:
            payment_data = create_deposit_payment(user_id, currency)
            address = payment_data['pay_address']
            payment_id = payment_data['payment_id']
            expiration_time = payment_data.get('expiration_estimate_date', '')
            expires_in = format_expiration_time(expiration_time) if expiration_time else "1:00:00"
            
            add_pending_deposit(payment_id, user_id, currency)
            
            text = (
                f"💳 **Deposit {currency.upper()}**\n\n"
                f"To top up your balance, transfer the desired amount to this address.\n\n"
                f"**Please note:**\n"
                f"1. The address is temporary and valid for 1 hour\n"
                f"2. One address accepts only one payment\n\n"
                f"**{currency.upper()} address:**\n`{address}`\n\n"
                f"**Expires in:** {expires_in}"
            )
            
            await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg:
                await context.bot.send_message(chat_id=chat_id, text="❌ API key invalid. Contact support.")
            elif "400" in error_msg:
                await context.bot.send_message(chat_id=chat_id, text="❌ Invalid request. Try again later.")
            else:
                await context.bot.send_message(chat_id=chat_id, text=f"❌ Failed to generate address: {error_msg}")
    
    elif data == "withdraw":
        if update.effective_chat.type != 'private':
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Please start a private chat with me: t.me/{BOT_USERNAME}"
            )
        else:
            context.user_data['expecting_withdrawal_details'] = True
            await context.bot.send_message(
                chat_id=chat_id,
                text="💸 **Withdrawal**\n\n"
                     "Please enter the amount in USD and your LTC address:\n"
                     "Format: `amount address`\n\n"
                     "Example: `9.87 LTC123...`\n\n"
                     "_Note: Only Litecoin withdrawals are supported._",
                parse_mode='Markdown'
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
                raise ValueError("Please enter 'amount address', e.g., '9.87 LTC123...'")
            
            amount_usd = Decimal(parts[0])
            address = parts[1]
            currency = 'ltc'
            
            if not is_valid_ltc_address(address):
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ Invalid LTC address. Please check and try again."
                )
                return True
            
            balance = get_user_balance(update.effective_user.id)
            if amount_usd > balance:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ Insufficient balance for withdrawal"
                )
                return True
            
            ltc_price_usd = get_currency_to_usd_price(currency)
            if ltc_price_usd == 0:
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="❌ Failed to fetch LTC price. Try again later."
                )
                return True
            
            ltc_amount = float(amount_usd / Decimal(str(ltc_price_usd)))
            payout_response = initiate_payout(currency, ltc_amount, address)
            
            if payout_response.get('status') == 'error':
                error_msg = payout_response.get('message', 'Unknown error')
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"❌ Withdrawal failed: {error_msg}"
                )
            else:
                new_balance = balance - amount_usd
                update_user_balance(update.effective_user.id, new_balance)
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"✅ Withdrawal of ${amount_usd:.2f} to {address} successful!\n"
                         f"New balance: ${new_balance:.2f}"
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
                text="❌ An error occurred. Try again or contact support."
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

