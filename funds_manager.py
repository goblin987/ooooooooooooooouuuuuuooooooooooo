#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Funds Management - Deposits & Withdrawals
Admin tool to add/remove points when users deposit/withdraw real money
"""

import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database import database
from moderation_grouphelp import is_admin

logger = logging.getLogger(__name__)

# Transaction history (stored in memory, could be moved to DB)
transaction_history = []


def get_user_balance(user_id: int) -> int:
    """Get user balance from database"""
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
        logger.error(f"Error getting balance: {e}")
        return 0


def update_user_balance(user_id: int, new_balance: int) -> bool:
    """Update user balance"""
    try:
        conn = database.get_sync_connection()
        conn.execute(
            "INSERT OR REPLACE INTO users (user_id, points) VALUES (?, ?)",
            (user_id, new_balance)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error updating balance: {e}")
        return False


def log_transaction(admin_id: int, admin_username: str, user_id: int, user_username: str, 
                     amount: int, transaction_type: str, reason: str = ""):
    """Log fund transaction"""
    transaction = {
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'admin_id': admin_id,
        'admin_username': admin_username,
        'user_id': user_id,
        'user_username': user_username,
        'amount': amount,
        'type': transaction_type,  # 'deposit' or 'withdrawal'
        'reason': reason
    }
    transaction_history.append(transaction)
    
    # Keep only last 100 transactions in memory
    if len(transaction_history) > 100:
        transaction_history.pop(0)
    
    logger.info(f"Transaction logged: {transaction}")


# ============================================================================
# MAIN MENU
# ============================================================================

async def show_funds_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show funds management menu"""
    if not await is_admin(update, context):
        if update.message:
            await update.message.reply_text("❌ Only administrators can manage funds!")
        return
    
    text = (
        "💰 **Funds Management**\n\n"
        "Manage user deposits and withdrawals.\n\n"
        "**Add Points** - When user deposits money\n"
        "**Remove Points** - When user withdraws money\n"
        "**View History** - See recent transactions\n\n"
        "_This is for manual fund management only._"
    )
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Points (Deposit)", callback_data="funds_add")],
        [InlineKeyboardButton("➖ Remove Points (Withdrawal)", callback_data="funds_remove")],
        [InlineKeyboardButton("💵 Check Balance", callback_data="funds_check")],
        [InlineKeyboardButton("📊 Transaction History", callback_data="funds_history")],
        [InlineKeyboardButton("🔙 Close", callback_data="funds_close")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )


# ============================================================================
# ADD POINTS (DEPOSIT)
# ============================================================================

async def add_points_start(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start add points process"""
    text = (
        "➕ **Add Points (Deposit)**\n\n"
        "Format: `user_id amount reason`\n\n"
        "**Examples:**\n"
        "`123456789 1000 Bank transfer $10`\n"
        "`987654321 500 Cash deposit $5`\n\n"
        "Send the details or /cancel"
    )
    
    context.user_data['funds_action'] = 'add'
    await query.edit_message_text(text, parse_mode='Markdown')


async def process_add_points(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Process adding points"""
    parts = text.split(None, 2)
    
    if len(parts) < 2:
        await update.message.reply_text(
            "❌ Invalid format!\n"
            "Use: `user_id amount reason`",
            parse_mode='Markdown'
        )
        return
    
    try:
        user_id = int(parts[0])
        amount = int(parts[1])
        reason = parts[2] if len(parts) > 2 else "No reason provided"
        
        if amount <= 0:
            await update.message.reply_text("❌ Amount must be positive!")
            return
        
        # Get current balance
        current_balance = get_user_balance(user_id)
        new_balance = current_balance + amount
        
        # Update balance
        if update_user_balance(user_id, new_balance):
            # Log transaction
            admin_username = update.effective_user.username or str(update.effective_user.id)
            log_transaction(
                update.effective_user.id,
                admin_username,
                user_id,
                str(user_id),
                amount,
                'deposit',
                reason
            )
            
            await update.message.reply_text(
                f"✅ **Points Added!**\n\n"
                f"👤 User ID: `{user_id}`\n"
                f"➕ Added: {amount} points\n"
                f"💰 Previous: {current_balance} points\n"
                f"💵 New Balance: {new_balance} points\n"
                f"📝 Reason: {reason}\n\n"
                f"Transaction logged.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ Failed to update balance!")
            
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid user ID or amount!\n"
            "User ID and amount must be numbers."
        )


# ============================================================================
# REMOVE POINTS (WITHDRAWAL)
# ============================================================================

async def remove_points_start(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start remove points process"""
    text = (
        "➖ **Remove Points (Withdrawal)**\n\n"
        "Format: `user_id amount reason`\n\n"
        "**Examples:**\n"
        "`123456789 500 PayPal withdrawal $5`\n"
        "`987654321 1000 Bank transfer $10`\n\n"
        "Send the details or /cancel"
    )
    
    context.user_data['funds_action'] = 'remove'
    await query.edit_message_text(text, parse_mode='Markdown')


async def process_remove_points(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Process removing points"""
    parts = text.split(None, 2)
    
    if len(parts) < 2:
        await update.message.reply_text(
            "❌ Invalid format!\n"
            "Use: `user_id amount reason`",
            parse_mode='Markdown'
        )
        return
    
    try:
        user_id = int(parts[0])
        amount = int(parts[1])
        reason = parts[2] if len(parts) > 2 else "No reason provided"
        
        if amount <= 0:
            await update.message.reply_text("❌ Amount must be positive!")
            return
        
        # Get current balance
        current_balance = get_user_balance(user_id)
        
        if current_balance < amount:
            await update.message.reply_text(
                f"❌ **Insufficient Balance!**\n\n"
                f"User has: {current_balance} points\n"
                f"Withdrawal: {amount} points\n"
                f"Short by: {amount - current_balance} points"
            )
            return
        
        new_balance = current_balance - amount
        
        # Update balance
        if update_user_balance(user_id, new_balance):
            # Log transaction
            admin_username = update.effective_user.username or str(update.effective_user.id)
            log_transaction(
                update.effective_user.id,
                admin_username,
                user_id,
                str(user_id),
                amount,
                'withdrawal',
                reason
            )
            
            await update.message.reply_text(
                f"✅ **Points Removed!**\n\n"
                f"👤 User ID: `{user_id}`\n"
                f"➖ Removed: {amount} points\n"
                f"💰 Previous: {current_balance} points\n"
                f"💵 New Balance: {new_balance} points\n"
                f"📝 Reason: {reason}\n\n"
                f"Transaction logged.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ Failed to update balance!")
            
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid user ID or amount!\n"
            "User ID and amount must be numbers."
        )


# ============================================================================
# CHECK BALANCE
# ============================================================================

async def check_balance_start(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start check balance process"""
    text = (
        "💵 **Check User Balance**\n\n"
        "Send the user ID to check:\n"
        "`123456789`\n\n"
        "Or /cancel"
    )
    
    context.user_data['funds_action'] = 'check'
    await query.edit_message_text(text, parse_mode='Markdown')


async def process_check_balance(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    """Process checking balance"""
    try:
        user_id = int(text.strip())
        balance = get_user_balance(user_id)
        
        await update.message.reply_text(
            f"💰 **Balance Check**\n\n"
            f"👤 User ID: `{user_id}`\n"
            f"💵 Balance: {balance} points\n\n"
            f"Use /funds to manage funds.",
            parse_mode='Markdown'
        )
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID! Must be a number.")


# ============================================================================
# TRANSACTION HISTORY
# ============================================================================

async def show_transaction_history(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show recent transaction history"""
    
    if not transaction_history:
        await query.edit_message_text(
            "📊 **Transaction History**\n\n"
            "No transactions recorded yet."
        )
        return
    
    text = "📊 **Recent Transactions**\n\n"
    
    # Show last 10 transactions
    recent = transaction_history[-10:]
    for i, trans in enumerate(reversed(recent), 1):
        emoji = "➕" if trans['type'] == 'deposit' else "➖"
        text += (
            f"{i}. {emoji} {trans['type'].title()}\n"
            f"   User: `{trans['user_id']}`\n"
            f"   Amount: {trans['amount']} points\n"
            f"   By: @{trans['admin_username']}\n"
            f"   Time: {trans['timestamp']}\n"
            f"   Reason: {trans['reason']}\n\n"
        )
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="funds_main")]]
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )


# ============================================================================
# CALLBACK HANDLER
# ============================================================================

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle funds management callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "funds_main":
        await show_funds_menu(update, context)
    elif data == "funds_add":
        await add_points_start(query, context)
    elif data == "funds_remove":
        await remove_points_start(query, context)
    elif data == "funds_check":
        await check_balance_start(query, context)
    elif data == "funds_history":
        await show_transaction_history(query, context)
    elif data == "funds_close":
        await query.edit_message_text("✅ Funds management closed.")
        context.user_data.pop('funds_action', None)


# ============================================================================
# TEXT INPUT HANDLER
# ============================================================================

async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text input for funds management"""
    
    action = context.user_data.get('funds_action')
    
    if not action:
        return
    
    text = update.message.text.strip()
    
    if text == '/cancel':
        context.user_data.pop('funds_action', None)
        await update.message.reply_text("❌ Cancelled")
        return
    
    if action == 'add':
        await process_add_points(update, context, text)
    elif action == 'remove':
        await process_remove_points(update, context, text)
    elif action == 'check':
        await process_check_balance(update, context, text)
    
    # Clear action
    context.user_data.pop('funds_action', None)


# Export functions
__all__ = [
    'show_funds_menu',
    'handle_callback',
    'handle_text_input'
]

