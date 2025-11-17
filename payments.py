#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Payment System - Solana Deposits & Withdrawals
Direct blockchain monitoring with automatic crediting
"""

import logging
import qrcode
from io import BytesIO
from decimal import Decimal
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import database

# Import Solana payment functions
try:
    from solana_payments import (
        create_deposit_request,
        send_sol_withdrawal,
        SOLANA_MAIN_WALLET_ADDRESS,
        MIN_WITHDRAWAL_USD,
        MAX_WITHDRAWAL_USD,
        MAX_WITHDRAWALS_PER_DAY,
        WITHDRAWAL_FEE_PERCENT
    )
    SOLANA_AVAILABLE = True
except Exception as e:
    logging.error(f"Failed to import solana_payments: {e}")
    SOLANA_AVAILABLE = False

try:
    from config import OWNER_ID, BOT_USERNAME
except ImportError:
    import os
    OWNER_ID = int(os.getenv('OWNER_ID', '0'))
    BOT_USERNAME = os.getenv('BOT_USERNAME', 'your_bot')

logger = logging.getLogger(__name__)

# Withdrawal toggle
from utils import data_manager
withdrawals_enabled = data_manager.load_data('withdrawals_enabled.pkl', True)


# ============================================================================
# MESSAGE AUTO-DELETION
# ============================================================================

async def delete_balance_message(context: ContextTypes.DEFAULT_TYPE):
    """Delete balance message after 2 minutes"""
    job = context.job
    chat_id = job.data['chat_id']
    message_id = job.data['message_id']
    
    try:
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
        logger.info(f"✅ Deleted balance message {message_id}")
    except Exception as e:
        logger.debug(f"Could not delete balance message: {e}")


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
            "SELECT balance FROM users WHERE user_id = ?",
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
            "UPDATE users SET balance = ? WHERE user_id = ?",
            (float(new_balance), user_id)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Error updating balance: {e}")


# ============================================================================
# BALANCE COMMAND
# ============================================================================

async def balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show balance with deposit/withdraw buttons"""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    # Ensure user exists
    if not user_exists(user_id):
        conn = database.get_sync_connection()
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, points, balance) VALUES (?, 0, 0.0)",
            (user_id,)
        )
        conn.commit()
        conn.close()
    
    balance = get_user_balance(user_id)
    
    if not SOLANA_AVAILABLE:
        text = f"💰 <b>Jūsų balansas:</b> ${balance:.2f}\n\n" \
               f"⚠️ <i>Solana sistemos klaida. Susisiekite su administratoriumi.</i>"
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode='HTML')
        return
    
    # Check if withdrawals are enabled
    if withdrawals_enabled:
        text = f"💰 <b>Jūsų balansas:</b> ${balance:.2f}\n\n" \
              f"<i>Pasirinkite veiksmą apačioje:</i>"
        keyboard = [
            [InlineKeyboardButton("💵 Įnešti", callback_data="sol_deposit"),
             InlineKeyboardButton("💸 Išimti", callback_data="sol_withdraw")]
        ]
    else:
        text = f"💰 <b>Jūsų balansas:</b> ${balance:.2f}\n\n" \
              f"⚠️ <i>Išėmimai laikinai sustabdyti</i>\n" \
              f"<i>Įnešimai veikia įprastai</i>"
        keyboard = [
            [InlineKeyboardButton("💵 Įnešti", callback_data="sol_deposit")]
        ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    msg = await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=reply_markup,
        parse_mode='HTML'
    )
    
    # Schedule deletion after 2 minutes
    context.job_queue.run_once(
        delete_balance_message,
        when=120,
        data={'chat_id': chat_id, 'message_id': msg.message_id},
        name=f"delete_balance_{chat_id}_{msg.message_id}"
    )


# ============================================================================
# ADMIN COMMANDS
# ============================================================================

async def setbalance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only: Set exact balance for user"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /setbalance @username 12.00")
        return
    
    username = context.args[0].lstrip('@')
    try:
        amount = Decimal(context.args[1])
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Invalid amount")
        return
    
    # Find user ID by username
    conn = database.get_sync_connection()
    cursor = conn.execute(
        "SELECT user_id FROM user_cache WHERE username = ?",
        (username,)
    )
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        await update.message.reply_text(f"❌ User @{username} not found")
        return
    
    target_user_id = result[0]
    
    # Update balance
    conn.execute(
        "UPDATE users SET balance = ? WHERE user_id = ?",
        (float(amount), target_user_id)
    )
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"✅ Set balance for @{username}: ${amount:.2f}",
        parse_mode='HTML'
    )
    logger.info(f"Admin {update.effective_user.id} set balance for {target_user_id}: ${amount:.2f}")


async def addbalance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only: Add to user balance"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /addbalance @username 12.00")
        return
    
    username = context.args[0].lstrip('@')
    try:
        amount = Decimal(context.args[1])
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Invalid amount")
        return
    
    # Find user
    conn = database.get_sync_connection()
    cursor = conn.execute(
        "SELECT user_id, balance FROM user_cache uc JOIN users u ON uc.user_id = u.user_id WHERE uc.username = ?",
        (username,)
    )
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        await update.message.reply_text(f"❌ User @{username} not found")
        return
    
    target_user_id = result[0]
    current_balance = Decimal(str(result[1]))
    new_balance = current_balance + amount
    
    # Update balance
    conn.execute(
        "UPDATE users SET balance = ? WHERE user_id = ?",
        (float(new_balance), target_user_id)
    )
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"✅ Added ${amount:.2f} to @{username}\n"
        f"Old: ${current_balance:.2f}\n"
        f"New: ${new_balance:.2f}",
        parse_mode='HTML'
    )
    logger.info(f"Admin {update.effective_user.id} added ${amount:.2f} to {target_user_id}")


async def removebalance_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only: Remove from user balance"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    if len(context.args) != 2:
        await update.message.reply_text("Usage: /removebalance @username 12.00")
        return
    
    username = context.args[0].lstrip('@')
    try:
        amount = Decimal(context.args[1])
    except (ValueError, IndexError):
        await update.message.reply_text("❌ Invalid amount")
        return
    
    # Find user
    conn = database.get_sync_connection()
    cursor = conn.execute(
        "SELECT u.user_id, u.balance FROM user_cache uc JOIN users u ON uc.user_id = u.user_id WHERE uc.username = ?",
        (username,)
    )
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        await update.message.reply_text(f"❌ User @{username} not found")
        return
    
    target_user_id = result[0]
    current_balance = Decimal(str(result[1]))
    new_balance = max(Decimal('0'), current_balance - amount)
    
    # Update balance
    conn.execute(
        "UPDATE users SET balance = ? WHERE user_id = ?",
        (float(new_balance), target_user_id)
    )
    conn.commit()
    conn.close()
    
    await update.message.reply_text(
        f"✅ Removed ${amount:.2f} from @{username}\n"
        f"Old: ${current_balance:.2f}\n"
        f"New: ${new_balance:.2f}",
        parse_mode='HTML'
    )
    logger.info(f"Admin {update.effective_user.id} removed ${amount:.2f} from {target_user_id}")


async def toggle_withdrawals_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only: Toggle withdrawals on/off"""
    global withdrawals_enabled
    
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    withdrawals_enabled = not withdrawals_enabled
    data_manager.save_data('withdrawals_enabled.pkl', withdrawals_enabled)
    
    status = "✅ ENABLED" if withdrawals_enabled else "🚫 DISABLED"
    await update.message.reply_text(f"Withdrawals: {status}")
    logger.info(f"Admin {update.effective_user.id} toggled withdrawals: {withdrawals_enabled}")


async def tip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send balance to another user"""
    user_id = update.effective_user.id
    
    if len(context.args) != 2:
        await update.message.reply_text(
            "💵 <b>Tip Command</b>\n\n"
            "Usage: <code>/tip @username 10.00</code>\n\n"
            "Send balance to another user.",
            parse_mode='HTML'
        )
        return
    
    recipient_username = context.args[0].lstrip('@')
    try:
        amount = Decimal(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ Invalid amount")
        return
    
    if amount <= Decimal('0'):
        await update.message.reply_text("❌ Amount must be positive")
        return
    
    # Check sender balance
    sender_balance = get_user_balance(user_id)
    if sender_balance < amount:
        await update.message.reply_text(
            f"❌ Insufficient balance\n\nYour balance: ${sender_balance:.2f}",
            parse_mode='HTML'
        )
        return
    
    # Find recipient
    conn = database.get_sync_connection()
    cursor = conn.execute(
        "SELECT u.user_id, u.balance FROM user_cache uc JOIN users u ON uc.user_id = u.user_id WHERE uc.username = ?",
        (recipient_username,)
    )
    result = cursor.fetchone()
    
    if not result:
        conn.close()
        await update.message.reply_text(f"❌ User @{recipient_username} not found")
        return
    
    recipient_id = result[0]
    recipient_balance = Decimal(str(result[1]))
    
    if recipient_id == user_id:
        conn.close()
        await update.message.reply_text("❌ Cannot tip yourself")
        return
    
    # Transfer
    try:
        conn.execute("BEGIN IMMEDIATE TRANSACTION")
        
        # Deduct from sender
        conn.execute(
            "UPDATE users SET balance = ? WHERE user_id = ?",
            (float(sender_balance - amount), user_id)
        )
        
        # Add to recipient
        conn.execute(
            "UPDATE users SET balance = ? WHERE user_id = ?",
            (float(recipient_balance + amount), recipient_id)
        )
        
        conn.commit()
        
        await update.message.reply_text(
            f"✅ Sent ${amount:.2f} to @{recipient_username}\n\n"
            f"Your new balance: ${sender_balance - amount:.2f}",
            parse_mode='HTML'
        )
        
        logger.info(f"Tip: {user_id} → {recipient_id}, ${amount:.2f}")
        
    except Exception as e:
        conn.rollback()
        logger.error(f"Error processing tip: {e}")
        await update.message.reply_text("❌ Transfer failed. Please try again.")
    finally:
        conn.close()


# Aliases for OGbotas compatibility
add_balance_command = addbalance_command
remove_balance_command = removebalance_command
togglewithdrawals_command = toggle_withdrawals_command


# ============================================================================
# DEPOSIT FLOW
# ============================================================================

async def handle_deposit_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle deposit button press - ask for amount"""
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    
    if not SOLANA_AVAILABLE:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Solana sistema nepasiekiama. Susisiekite su administratoriumi.",
            parse_mode='HTML'
        )
        return
    
    # Ask for deposit amount
    text = (
        "💵 <b>SOLANA Įnešimas</b>\n\n"
        "Minimali suma: <b>$10.00</b>\n"
        "Maksimali suma: <b>$10,000.00</b>\n\n"
        "Įveskite sumą USD (pvz., 25.50):"
    )
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode='HTML'
    )
    
    # Set state to expect deposit amount
    context.user_data['expecting_deposit_amount'] = True


async def handle_deposit_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handle deposit amount input"""
    if not context.user_data.get('expecting_deposit_amount'):
        return False
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    try:
        # Parse amount - handle various formats
        try:
            amount_usd = Decimal(update.message.text.strip().replace(',', '.'))
        except (ValueError, Exception):
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Neteisinga suma. Įveskite skaičių (pvz., 25.50):",
                parse_mode='HTML'
            )
            return True
        
        # Validation
        if amount_usd <= Decimal('0'):
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Suma turi būti teigiama. Bandykite dar kartą:",
                parse_mode='HTML'
            )
            return True
        
        if amount_usd < Decimal('10.0'):
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Minimali suma: $10.00\n\nBandykite dar kartą:",
                parse_mode='HTML'
            )
            return True
        
        if amount_usd > Decimal('10000.0'):
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Maksimali suma: $10,000.00\n\nBandykite dar kartą:",
                parse_mode='HTML'
            )
            return True
        
        # Create deposit request (without message_id yet)
        deposit_data = await create_deposit_request(user_id, amount_usd, chat_id=chat_id)
        
        if 'error' in deposit_data:
            error = deposit_data['error']
            if error == 'price_fetch_failed':
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Nepavyko gauti SOL kainos. Bandykite vėliau.",
                    parse_mode='HTML'
                )
            elif error == 'amount_too_low':
                min_usd = deposit_data.get('min_usd', 10)
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ Suma per maža. Minimalus įnešimas: ${min_usd:.2f}",
                    parse_mode='HTML'
                )
            else:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Sistemos klaida. Bandykite vėliau.",
                    parse_mode='HTML'
                )
            context.user_data.pop('expecting_deposit_amount', None)
            return True
        
        # Extract deposit details
        sol_amount = deposit_data['sol_amount']
        sol_price = deposit_data['sol_price_usd']
        wallet_address = deposit_data['wallet_address']
        deposit_id = deposit_data['deposit_id']
        
        # Generate QR code
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(wallet_address)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        qr_bytes = BytesIO()
        qr_img.save(qr_bytes, 'PNG')
        qr_bytes.seek(0)
        
        # Create message
        text = (
            f"💰 <b>SOLANA Įnešimas</b>\n\n"
            f"Suma: <b>${amount_usd:.2f}</b>\n"
            f"SOL kaina: <b>${sol_price:.2f}</b>\n"
            f"Reikia persiųsti: <b>{sol_amount:.6f} SOL</b>\n\n"
            f"📍 <b>Adresas:</b>\n"
            f"<code>{wallet_address}</code>\n\n"
            f"⏰ <b>Galioja:</b> 20 min\n\n"
            f"⚠️ <b>SVARBU:</b>\n"
            f"• Persiųskite <b>TIKSLIĄ</b> sumą: <code>{sol_amount:.6f} SOL</code>\n"
            f"• Balansas bus įskaitomas automatiškai per 1-2 min\n"
            f"• Nenaudokite biržos piniginės (nebūsite pripažinti)"
        )
        
        # Cancel button
        keyboard = [[InlineKeyboardButton("❌ Atšaukti", callback_data=f"cancel_deposit_{deposit_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Send QR code with text
        sent_message = await context.bot.send_photo(
            chat_id=chat_id,
            photo=qr_bytes,
            caption=text,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        
        # Update deposit with message_id
        try:
            conn = database.get_sync_connection()
            conn.execute(
                "UPDATE pending_sol_deposits SET message_id = ? WHERE deposit_id = ?",
                (sent_message.message_id, deposit_id)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to update deposit with message_id: {e}")
        
        # Clear state
        context.user_data.pop('expecting_deposit_amount', None)
        
        logger.info(f"💰 Deposit request created: User {user_id}, ${amount_usd:.2f} ({sol_amount:.6f} SOL), msg_id={sent_message.message_id}")
        
        return True
        
    except Exception as e:
        logger.error(f"Error handling deposit amount: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Klaida apdorojant užklausą. Bandykite dar kartą vėliau.",
            parse_mode='HTML'
        )
        context.user_data.pop('expecting_deposit_amount', None)
        return True


async def handle_cancel_deposit(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle deposit cancellation"""
    deposit_id = query.data.replace("cancel_deposit_", "")
    
    # Mark as cancelled in database
    try:
        conn = database.get_sync_connection()
        conn.execute(
            "UPDATE pending_sol_deposits SET status = 'cancelled' WHERE deposit_id = ?",
            (deposit_id,)
        )
        conn.commit()
        conn.close()
        
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ Įnešimas atšauktas.\n\nGalite pradėti naują naudodami /balance",
            parse_mode='HTML'
        )
        
        logger.info(f"Deposit {deposit_id} cancelled by user")
        
    except Exception as e:
        logger.error(f"Error cancelling deposit: {e}")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="❌ Klaida atšaukiant. Jei sumokėjote, lėšos bus įskaitytos automatiškai.",
            parse_mode='HTML'
        )


# ============================================================================
# WITHDRAWAL FLOW
# ============================================================================

async def handle_withdraw_callback(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdraw button press - ask for details"""
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    
    if not SOLANA_AVAILABLE:
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Solana sistema nepasiekiama. Susisiekite su administratoriumi.",
            parse_mode='HTML'
        )
        return
    
    if not withdrawals_enabled:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "🚫 <b>Išėmimai laikinai sustabdyti</b>\n\n"
                "Administratoriai laikinai išjungė išėmimus.\n"
                "Bandykite vėliau arba susisiekite su palaikymu."
            ),
            parse_mode='HTML'
        )
        return
    
    balance = get_user_balance(user_id)
    
    # Show withdrawal instructions
    text = (
        f"💸 <b>SOLANA Išėmimas</b>\n\n"
        f"Jūsų balansas: <b>${balance:.2f}</b>\n\n"
        f"📋 <b>Limittai:</b>\n"
        f"• Minimumas: <b>${MIN_WITHDRAWAL_USD:.2f}</b>\n"
        f"• Maksimumas: <b>${MAX_WITHDRAWAL_USD:.2f}</b>\n"
        f"• Dažnumas: <b>{MAX_WITHDRAWALS_PER_DAY} kartai per dieną</b>\n\n"
        f"💰 <b>Mokestis:</b> {WITHDRAWAL_FEE_PERCENT * 100:.1f}%\n\n"
        f"Įveskite: <code>suma adresas</code>\n"
        f"Pavyzdys: <code>50.00 DiNrF7cHF13eQzKD3HXi6Qh9qnxbrKZFrHuW4WFA7XVD</code>\n\n"
        f"⚠️ <b>SVARBU:</b>\n"
        f"• Patikrinkite adresą dukart - klaidų ištaisyti negalima!\n"
        f"• Transakvija užtruks 1-2 minutes"
    )
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=text,
        parse_mode='HTML'
    )
    
    # Set state to expect withdrawal details
    context.user_data['expecting_withdrawal_details'] = True


async def handle_withdrawal_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Handle withdrawal input"""
    if not context.user_data.get('expecting_withdrawal_details'):
        return False
    
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    
    if not withdrawals_enabled:
        await context.bot.send_message(
            chat_id=chat_id,
            text="🚫 Išėmimai laikinai sustabdyti",
            parse_mode='HTML'
        )
        context.user_data.pop('expecting_withdrawal_details', None)
        return True
    
    try:
        parts = update.message.text.strip().split()
        if len(parts) < 2:
            raise ValueError("Invalid format")
        
        amount_usd = Decimal(parts[0])
        address = parts[1]
        
        # Basic Solana address validation (32-44 characters)
        if not (32 <= len(address) <= 44):
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Neteisingas SOLANA adresas. Patikrinkite ir bandykite dar kartą.",
                parse_mode='HTML'
            )
            return True
        
        # Show confirmation
        balance = get_user_balance(user_id)
        fee = amount_usd * WITHDRAWAL_FEE_PERCENT
        net_amount = amount_usd - fee
        
        if amount_usd > balance:
            await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"❌ <b>Nepakanka lėšų</b>\n\n"
                    f"Jūsų balansas: ${balance:.2f}\n"
                    f"Reikalinga: ${amount_usd:.2f}"
                ),
                parse_mode='HTML'
            )
            return True
        
        text = (
            f"💸 <b>Patvirtinkite išėmimą</b>\n\n"
            f"Suma: <b>${amount_usd:.2f}</b>\n"
            f"Mokestis ({WITHDRAWAL_FEE_PERCENT * 100:.1f}%): <b>-${fee:.2f}</b>\n"
            f"Gausite: <b>${net_amount:.2f}</b>\n\n"
            f"📍 Adresas:\n<code>{address}</code>\n\n"
            f"⚠️ Ar tikrai norite tęsti?"
        )
        
        keyboard = [
            [InlineKeyboardButton("✅ Patvirtinti", callback_data=f"confirm_withdraw_{amount_usd}_{address}"),
             InlineKeyboardButton("❌ Atšaukti", callback_data="cancel_withdraw")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode='HTML'
        )
        
        # Clear state (will be set again if confirmed)
        context.user_data.pop('expecting_withdrawal_details', None)
        
        return True
        
    except ValueError:
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "❌ Neteisingas formatas.\n\n"
                "Įveskite: <code>suma adresas</code>\n"
                "Pavyzdys: <code>50.00 DiNrF7cHF13eQzKD3HXi6Qh9qnxbrKZFrHuW4WFA7XVD</code>"
            ),
            parse_mode='HTML'
        )
        return True
    except Exception as e:
        logger.error(f"Error handling withdrawal input: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Klaida apdorojant užklausą.",
            parse_mode='HTML'
        )
        context.user_data.pop('expecting_withdrawal_details', None)
        return True


async def handle_confirm_withdraw(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal confirmation"""
    user_id = query.from_user.id
    chat_id = query.message.chat_id
    
    try:
        # Parse callback data: confirm_withdraw_<amount>_<address>
        parts = query.data.split("_", 2)
        if len(parts) < 3:
            raise ValueError("Invalid callback data")
        
        amount_address = parts[2]
        amount_str, address = amount_address.split("_", 1)
        amount_usd = Decimal(amount_str)
        
        # Send processing message
        processing_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="⏳ Apdorojama... Prašome palaukti.",
            parse_mode='HTML'
        )
        
        # Execute withdrawal
        result = await send_sol_withdrawal(user_id, amount_usd, address)
        
        # Delete processing message
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=processing_msg.message_id)
        except:
            pass
        
        if 'error' in result:
            error = result['error']
            message = result.get('message', 'Nežinoma klaida')
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"❌ <b>Išėmimas nepavyko</b>\n\n{message}",
                parse_mode='HTML'
            )
            logger.warning(f"Withdrawal failed for user {user_id}: {error}")
        
        elif 'success' in result and result['success']:
            signature = result['transaction_signature']
            sol_amount = result['sol_amount']
            fee = result['fee_usd']
            
            text = (
                f"✅ <b>Išėmimas sėkmingas!</b>\n\n"
                f"Suma: <b>${amount_usd:.2f}</b>\n"
                f"Mokestis: <b>-${fee:.2f}</b>\n"
                f"Išsiųsta: <b>{sol_amount:.6f} SOL</b>\n\n"
                f"📍 Adresas:\n<code>{address}</code>\n\n"
                f"🔗 Transakcija:\n<code>{signature[:16]}...{signature[-16:]}</code>\n\n"
                f"Patikrinkite: https://solscan.io/tx/{signature}"
            )
            
            await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode='HTML'
            )
            
            logger.info(f"💸 Withdrawal completed: User {user_id}, ${amount_usd:.2f}, TX: {signature[:16]}...")
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text="❌ Nežinoma klaida. Susisiekite su palaikymu.",
                parse_mode='HTML'
            )
        
    except Exception as e:
        logger.error(f"Error confirming withdrawal: {e}", exc_info=True)
        await context.bot.send_message(
            chat_id=chat_id,
            text="❌ Klaida apdorojant išėmimą. Jei lėšos buvo nuskaitytos, jos bus grąžintos.",
            parse_mode='HTML'
        )


async def handle_cancel_withdraw(query, context: ContextTypes.DEFAULT_TYPE):
    """Handle withdrawal cancellation"""
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="❌ Išėmimas atšauktas.",
        parse_mode='HTML'
    )


# ============================================================================
# TEXT MESSAGE HANDLER
# ============================================================================

async def handle_payment_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """
    Handle payment-related text input (deposit amount or withdrawal details).
    Returns True if handled, False if not a payment input.
    """
    # Check deposit amount first
    if await handle_deposit_amount(update, context):
        return True
    
    # Check withdrawal details
    if await handle_withdrawal_text(update, context):
        return True
    
    return False


# ============================================================================
# CALLBACK HANDLER
# ============================================================================

async def payment_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all payment-related callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "sol_deposit":
        await handle_deposit_callback(query, context)
    
    elif data == "sol_withdraw":
        await handle_withdraw_callback(query, context)
    
    elif data.startswith("cancel_deposit_"):
        await handle_cancel_deposit(query, context)
    
    elif data.startswith("confirm_withdraw_"):
        await handle_confirm_withdraw(query, context)
    
    elif data == "cancel_withdraw":
        await handle_cancel_withdraw(query, context)


# Alias for OGbotas compatibility
handle_payment_callback = payment_callback_handler
