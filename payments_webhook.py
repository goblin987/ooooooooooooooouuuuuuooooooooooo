#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NOWPayments Webhook Handler
This module handles payment status updates from NOWPayments
"""

import logging
from database import database

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
        payment_status = data.get('payment_status')
        order_id = data.get('order_id')
        pay_amount = float(data.get('pay_amount', 0))
        price_amount = float(data.get('price_amount', 0))
        pay_currency = data.get('pay_currency', 'unknown')
        
        # Debug: Log full webhook data
        logger.info(f"📥 Webhook RAW: {data}")
        logger.info(f"📥 Webhook: order_id={order_id}, status={payment_status}, pay_amount={pay_amount} {pay_currency}, price_amount=${price_amount}")
        
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
            # Payment successful - add balance (accept partial payments too)
            logger.info(f"✅ Payment {payment_status} for user {user_id}: ${price_amount}")
            
            conn = database.get_sync_connection()
            
            # Get current balance
            cursor = conn.execute(
                "SELECT balance FROM users WHERE user_id = ?",
                (user_id,)
            )
            result = cursor.fetchone()
            current_balance = result[0] if result else 0.0
            
            # Add payment amount
            new_balance = current_balance + price_amount
            
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
                             f"💰 Suma: ${price_amount:.2f}\n"
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

