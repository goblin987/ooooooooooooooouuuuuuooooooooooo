#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NOWPayments Webhook Handler
This module handles payment status updates from NOWPayments
"""

import logging
from database import database
from payments import get_currency_to_usd_price

logger = logging.getLogger(__name__)


async def handle_nowpayments_webhook(data: dict, bot=None) -> bool:
    """
    Handle NOWPayments webhook callback
    
    Webhook structure:
    {
        "payment_id": "123456",
        "payment_status": "finished",
        "pay_amount": 0.001,
        "pay_currency": "ltc",
        "price_amount": 10.00,
        "price_currency": "usd",
        "order_id": "user_12345",
        ...
    }
    """
    try:
        payment_id = data.get('payment_id')
        payment_status = data.get('payment_status')
        order_id = data.get('order_id')
        pay_amount = float(data.get('pay_amount', 0))
        price_amount = float(data.get('price_amount', 0))
        outcome_amount = float(data.get('outcome_amount', 0))
        actually_paid = float(data.get('actually_paid', 0))
        pay_currency = data.get('pay_currency', 'unknown')
        price_currency = data.get('price_currency', 'unknown')
        
        # Debug: Log full webhook data
        logger.info(f"📥 Webhook RAW: {data}")
        logger.info(f"📥 Webhook DETAILED: order_id={order_id}, status={payment_status}")
        logger.info(f"   pay_amount={pay_amount} {pay_currency}")
        logger.info(f"   price_amount={price_amount} {price_currency}")
        logger.info(f"   outcome_amount={outcome_amount}")
        logger.info(f"   actually_paid={actually_paid}")
        
        # Extract user_id from order_id (format: "deposit_12345_timestamp" or "user_12345")
        if not order_id:
            logger.warning(f"Missing order_id")
            return False
        
        parts = order_id.split('_')
        if parts[0] == 'deposit':
            # Format: deposit_USERID_TIMESTAMP
            user_id = int(parts[1])
        elif parts[0] == 'user':
            # Format: user_USERID
            user_id = int(parts[1])
        else:
            logger.warning(f"Invalid order_id format: {order_id}")
            return False
        
        # Handle payment status
        if payment_status in ['finished', 'partially_paid']:
            # Determine the correct USD amount to credit
            # PRIORITY: Use actually_paid (what user sent), not price_amount (invoice amount)
            credit_amount = 0.0
            
            # Method 1: Use actually_paid (convert crypto to USD) - PREFERRED
            if actually_paid > 0 and pay_currency and pay_currency != 'usd':
                try:
                    crypto_price_usd = get_currency_to_usd_price(pay_currency)
                    credit_amount = actually_paid * crypto_price_usd
                    logger.info(f"💰 Using actually_paid: {actually_paid} {pay_currency} × ${crypto_price_usd} = ${credit_amount:.2f}")
                except Exception as e:
                    logger.error(f"Failed to convert actually_paid to USD: {e}")
                    credit_amount = 0.0
            
            # Method 2: If actually_paid is already in USD (rare)
            if credit_amount == 0.0 and price_currency == 'usd' and price_amount > 0:
                credit_amount = price_amount
                logger.info(f"💰 Using price_amount (USD invoice): ${credit_amount}")
            
            # Method 3: Fallback to outcome_amount
            elif credit_amount == 0.0 and outcome_amount > 0:
                credit_amount = outcome_amount
                logger.warning(f"⚠️ Fallback to outcome_amount: ${credit_amount}")
            
            # Method 4: Last resort - use pay_amount
            elif credit_amount == 0.0 and pay_amount > 0:
                credit_amount = pay_amount
                logger.warning(f"⚠️ Last resort - using pay_amount: ${credit_amount}")
            
            # Safety check
            if credit_amount <= 0:
                logger.error(f"❌ Cannot credit $0.00 or negative amount for payment {payment_id}")
                return False
            
            # Payment successful - add balance (accept partial payments too)
            logger.info(f"✅ Payment {payment_status} for user {user_id}: ${credit_amount:.2f}")
            
            conn = database.get_sync_connection()
            
            # IDEMPOTENCY CHECK: Check if this payment_id was already processed
            try:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS processed_payments (
                        payment_id TEXT PRIMARY KEY,
                        user_id INTEGER,
                        amount REAL,
                        processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM processed_payments WHERE payment_id = ?",
                    (payment_id,)
                )
                already_processed = cursor.fetchone()[0] > 0
                
                if already_processed:
                    logger.warning(f"⚠️ DUPLICATE WEBHOOK: payment_id {payment_id} already processed, ignoring")
                    conn.close()
                    return True  # Return success but don't process again
                    
                # Mark as processed FIRST (before crediting balance)
                conn.execute(
                    "INSERT INTO processed_payments (payment_id, user_id, amount) VALUES (?, ?, ?)",
                    (payment_id, user_id, credit_amount)
                )
                conn.commit()
                logger.info(f"✅ Marked payment {payment_id} as processed")
                
            except Exception as e:
                logger.error(f"❌ Idempotency check failed: {e}")
                conn.close()
                return False
            
            # Get current balance
            cursor = conn.execute(
                "SELECT balance FROM users WHERE user_id = ?",
                (user_id,)
            )
            result = cursor.fetchone()
            current_balance = result[0] if result else 0.0
            
            # Add payment amount
            new_balance = current_balance + credit_amount
            
            # Update balance
            conn.execute(
                "INSERT OR REPLACE INTO users (user_id, balance) VALUES (?, ?)",
                (user_id, new_balance)
            )
            conn.commit()
            conn.close()
            
            logger.info(f"✅ Balance updated: user {user_id} → ${new_balance}")
            
            # Send notification to user
            if bot:
                try:
                    await bot.send_message(
                        chat_id=user_id,
                        text=f"✅ <b>Įnešimas sėkmingas!</b>\n\n"
                             f"💰 Suma: ${credit_amount:.2f}\n"
                             f"📊 Naujas balansas: ${new_balance:.2f}\n\n"
                             f"Ačiū! 🎉",
                        parse_mode='HTML'
                    )
                    logger.info(f"✅ Sent notification to user {user_id}")
                except Exception as e:
                    logger.error(f"Failed to send notification: {e}")
            
            return True
            
        elif payment_status in ['failed', 'expired', 'refunded']:
            logger.warning(f"❌ Payment {payment_status} for user {user_id}")
            return True
            
        else:
            # Waiting, confirming, sending, etc.
            logger.info(f"⏳ Payment status: {payment_status} for user {user_id}")
            return True
            
    except Exception as e:
        logger.error(f"❌ Webhook processing error: {e}", exc_info=True)
        return False


__all__ = ['handle_nowpayments_webhook']

