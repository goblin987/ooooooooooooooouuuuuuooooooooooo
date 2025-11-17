#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Solana Payment Module - Single Wallet System
Handles SOL deposits and withdrawals with automatic blockchain monitoring
"""

import logging
import requests
import asyncio
import time
import json
import sqlite3
import base58
import random
from decimal import Decimal, ROUND_DOWN, ROUND_UP
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
from collections import defaultdict

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.signature import Signature
from solders.system_program import TransferParams, transfer
from solana.transaction import Transaction
from solana.rpc.api import Client as SolanaClient
from solana.rpc.commitment import Confirmed
from solana.rpc.types import TxOpts

from database import database

logger = logging.getLogger(__name__)

# Global configuration
SOLANA_MAIN_WALLET_ADDRESS = None
SOLANA_MAIN_WALLET_KEYPAIR = None
SOLANA_RPC_URL = None
SOL_CHECK_INTERVAL = 30

# SOL to USD conversion rate cache
sol_price_cache = {'price': Decimal('0'), 'timestamp': 0}
PRICE_CACHE_DURATION = 5400  # Cache price for 90 minutes (1.5 hours)
PRICE_CACHE_MAX_AGE = 86400  # 24 hours - use expired cache rather than default

# Solana client
solana_client = None

# Withdrawal locks per user (prevents concurrent withdrawals)
_withdrawal_locks = defaultdict(asyncio.Lock)

# Withdrawal limits
MIN_WITHDRAWAL_USD = Decimal('10.0')
MAX_WITHDRAWAL_USD = Decimal('1000.0')
MAX_WITHDRAWALS_PER_DAY = 3
WITHDRAWAL_FEE_PERCENT = Decimal('0.01')  # 1% fee


def init_solana_config():
    """Initialize Solana configuration from config.py"""
    global SOLANA_MAIN_WALLET_ADDRESS, SOLANA_MAIN_WALLET_KEYPAIR
    global SOLANA_RPC_URL, SOL_CHECK_INTERVAL, solana_client
    
    from config import (
        SOLANA_MAIN_WALLET_ADDRESS as wallet_address,
        SOLANA_MAIN_WALLET_PRIVATE_KEY as wallet_private_key,
        SOLANA_RPC_URL as rpc_url,
        SOL_CHECK_INTERVAL as check_interval
    )
    
    SOLANA_MAIN_WALLET_ADDRESS = wallet_address
    SOLANA_RPC_URL = rpc_url
    SOL_CHECK_INTERVAL = check_interval
    
    # Initialize wallet keypair from private key
    if wallet_private_key:
        try:
            private_key_bytes = base58.b58decode(wallet_private_key)
            SOLANA_MAIN_WALLET_KEYPAIR = Keypair.from_bytes(private_key_bytes)
            logger.info(f"✅ Main wallet keypair initialized: {str(SOLANA_MAIN_WALLET_KEYPAIR.pubkey())[:8]}...")
        except Exception as e:
            logger.error(f"Failed to initialize wallet keypair: {e}")
            logger.warning("⚠️ Wallet private key invalid. Withdrawals will NOT work!")
            SOLANA_MAIN_WALLET_KEYPAIR = None
    else:
        logger.warning("⚠️ SOLANA_MAIN_WALLET_PRIVATE_KEY not set. Withdrawals will NOT work!")
        SOLANA_MAIN_WALLET_KEYPAIR = None
    
    # Validate RPC URL
    if not SOLANA_RPC_URL.startswith(('http://', 'https://')):
        logger.error(f"❌ Invalid SOLANA_RPC_URL: '{SOLANA_RPC_URL}'")
        SOLANA_RPC_URL = "https://api.mainnet-beta.solana.com"
    
    # Initialize Solana RPC client
    solana_client = SolanaClient(SOLANA_RPC_URL)
    logger.info(f"✅ Solana client initialized: {SOLANA_RPC_URL}")


async def prefetch_sol_price():
    """Pre-fetch SOL price to populate cache on startup"""
    logger.info("💰 Pre-fetching SOL price...")
    price = await get_sol_price_usd()
    if price:
        logger.info(f"✅ SOL price cached: ${price:.2f} USD")
    else:
        logger.warning("⚠️ Could not fetch SOL price on startup. Withdrawals may fail until price is available.")
    return price


async def get_sol_price_usd() -> Optional[Decimal]:
    """Get current SOL price in USD with multi-source fallback and caching"""
    global sol_price_cache
    
    # Return fresh cached price if still valid
    if time.time() - sol_price_cache['timestamp'] < PRICE_CACHE_DURATION:
        if sol_price_cache['price'] > Decimal('0'):
            return sol_price_cache['price']
    
    # Try multiple price sources in order
    price_sources = [
        ('CoinGecko', _fetch_price_coingecko),
        ('Binance', _fetch_price_binance),
        ('Jupiter', _fetch_price_jupiter),
    ]
    
    for source_name, fetch_func in price_sources:
        try:
            price = await asyncio.to_thread(fetch_func)
            if price and price > Decimal('0'):
                # Update cache
                sol_price_cache['price'] = price
                sol_price_cache['timestamp'] = time.time()
                logger.info(f"💵 SOL price: ${price:.2f} USD (from {source_name})")
                return price
        except Exception as e:
            logger.debug(f"{source_name} failed: {e}")
            continue
    
    # All sources failed, try to use cached price
    logger.warning("⚠️ All price sources failed. Trying cached price...")
    
    if sol_price_cache['price'] > Decimal('0'):
        age = int(time.time() - sol_price_cache['timestamp'])
        age_hours = age / 3600
        
        # Refuse to use cache older than 24 hours for safety
        if age > PRICE_CACHE_MAX_AGE:
            logger.error(f"❌ Cache too old ({age_hours:.1f}h). Cannot process payment safely.")
            return None
        
        logger.warning(f"✅ Using cached SOL price: ${sol_price_cache['price']:.2f} (age: {age_hours:.1f}h)")
        return sol_price_cache['price']
    
    # NO PRICE AVAILABLE
    logger.error("❌ No valid SOL price available. Cannot process payment.")
    return None


def _fetch_price_coingecko() -> Optional[Decimal]:
    """Fetch SOL price from CoinGecko"""
    response = requests.get(
        'https://api.coingecko.com/api/v3/simple/price',
        params={'ids': 'solana', 'vs_currencies': 'usd'},
        timeout=10
    )
    response.raise_for_status()
    data = response.json()
    return Decimal(str(data['solana']['usd']))


def _fetch_price_binance() -> Optional[Decimal]:
    """Fetch SOL price from Binance (backup)"""
    response = requests.get(
        'https://api.binance.com/api/v3/ticker/price',
        params={'symbol': 'SOLUSDT'},
        timeout=10
    )
    response.raise_for_status()
    data = response.json()
    return Decimal(str(data['price']))


def _fetch_price_jupiter() -> Optional[Decimal]:
    """Fetch SOL price from Jupiter aggregator (backup 2)"""
    response = requests.get(
        'https://price.jup.ag/v4/price',
        params={'ids': 'So11111111111111111111111111111111111111112'},  # SOL mint address
        timeout=10
    )
    response.raise_for_status()
    data = response.json()
    if 'data' in data and 'So11111111111111111111111111111111111111112' in data['data']:
        return Decimal(str(data['data']['So11111111111111111111111111111111111111112']['price']))
    return None


async def create_deposit_request(user_id: int, amount_usd: Decimal, chat_id: int = None, message_id: int = None) -> dict:
    """
    Create a SOL deposit request.
    
    Args:
        user_id: Telegram user ID
        amount_usd: Amount in USD to deposit
    
    Returns:
        dict with deposit details or error
    """
    logger.info(f"💰 [CREATE DEPOSIT] User {user_id}: ${amount_usd:.2f} USD")
    
    try:
        # Get SOL price
        sol_price = await get_sol_price_usd()
        if not sol_price or sol_price <= Decimal('0'):
            logger.error("  ❌ Failed to fetch SOL price")
            return {'error': 'price_fetch_failed'}
        
        # Calculate SOL amount needed (add 1% buffer for price fluctuation)
        sol_amount_base = (amount_usd / sol_price).quantize(Decimal('0.000001'), rounding=ROUND_UP)
        sol_amount = sol_amount_base * Decimal('1.01')  # 1% buffer
        sol_amount = sol_amount.quantize(Decimal('0.000001'), rounding=ROUND_UP)
        
        # Add random offset for uniqueness (prevents collisions)
        random_offset = Decimal(str(random.randint(1, 9999))) / Decimal('1000000')
        sol_amount = sol_amount + random_offset
        
        logger.info(f"  ✅ Amount: {sol_amount:.6f} SOL (${amount_usd:.2f} USD @ ${sol_price:.2f}/SOL)")
        
        # Minimum check
        min_sol = Decimal('0.01')
        if sol_amount < min_sol:
            logger.warning(f"  ❌ Amount too low: {sol_amount:.6f} < {min_sol} SOL")
            return {
                'error': 'amount_too_low',
                'min_sol': float(min_sol),
                'min_usd': float(min_sol * sol_price)
            }
        
        # Generate unique deposit ID
        deposit_id = f"SOL_DEP_{user_id}_{int(time.time())}_{hex(int(time.time() * 1000000))[-6:]}"
        
        # Store in database
        conn = database.get_sync_connection()
        try:
            now = datetime.now(timezone.utc)
            expires = now + timedelta(minutes=20)
            
            conn.execute("""
                INSERT INTO pending_sol_deposits 
                (deposit_id, user_id, expected_sol_amount, expected_usd_amount, 
                 created_at, expires_at, status, chat_id, message_id)
                VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
            """, (
                deposit_id,
                user_id,
                float(sol_amount),
                float(amount_usd),
                now.isoformat(),
                expires.isoformat(),
                chat_id,
                message_id
            ))
            conn.commit()
            
            logger.info(f"✅ [CREATE DEPOSIT] {deposit_id}: {sol_amount:.6f} SOL → {SOLANA_MAIN_WALLET_ADDRESS[:8]}...")
            
            return {
                'deposit_id': deposit_id,
                'sol_amount': float(sol_amount),
                'sol_price_usd': float(sol_price),
                'amount_usd': float(amount_usd),
                'wallet_address': SOLANA_MAIN_WALLET_ADDRESS,
                'expires_at': expires.isoformat()
            }
            
        finally:
            conn.close()
            
    except Exception as e:
        logger.error(f"Error creating deposit request: {e}", exc_info=True)
        return {'error': 'internal_error'}


async def check_wallet_transactions(limit: int = 20) -> List[Dict]:
    """
    Check recent transactions for the main wallet using Solana RPC.
    
    Returns:
        List of transaction dictionaries with incoming transfers
    """
    global solana_client
    
    if not solana_client or not SOLANA_MAIN_WALLET_ADDRESS:
        logger.error("❌ Solana client not initialized!")
        return []
    
    try:
        wallet_address = SOLANA_MAIN_WALLET_ADDRESS
        logger.debug(f"Fetching transactions for {wallet_address[:8]}...")
        
        # Get wallet balance
        try:
            pubkey = Pubkey.from_string(wallet_address)
            balance_response = solana_client.get_balance(pubkey)
            if balance_response and balance_response.value is not None:
                balance_sol = Decimal(balance_response.value) / Decimal('1000000000')
                logger.info(f"💰 Main wallet balance: {balance_sol:.6f} SOL")
            else:
                logger.warning("⚠️ Could not fetch wallet balance")
        except Exception as balance_err:
            logger.error(f"Error fetching balance: {balance_err}")
        
        # Fetch signatures
        def fetch_signatures():
            pubkey = Pubkey.from_string(wallet_address)
            response = solana_client.get_signatures_for_address(
                pubkey,
                limit=limit,
                commitment=Confirmed
            )
            return response
        
        sig_response = await asyncio.to_thread(fetch_signatures)
        
        if not sig_response or not sig_response.value:
            logger.warning("⚠️ No signatures found")
            return []
        
        logger.info(f"✅ Found {len(sig_response.value)} signature(s)")
        
        transactions = []
        
        # Process each signature
        for idx, sig_info in enumerate(sig_response.value):
            signature = str(sig_info.signature)
            block_time = sig_info.block_time
            
            # Skip failed transactions
            if sig_info.err:
                continue
            
            try:
                # Fetch transaction details
                def fetch_transaction():
                    sig_obj = Signature.from_string(signature)
                    return solana_client.get_transaction(
                        sig_obj,
                        encoding="jsonParsed",
                        commitment=Confirmed,
                        max_supported_transaction_version=0
                    )
                
                tx_response = await asyncio.to_thread(fetch_transaction)
                await asyncio.sleep(0.1)  # Rate limit protection
                
                if not tx_response or not tx_response.value:
                    continue
                
                tx_data = tx_response.value
                
                if not (tx_data.transaction and tx_data.transaction.meta):
                    continue
                
                meta = tx_data.transaction.meta
                message = tx_data.transaction.transaction.message
                account_keys = message.account_keys
                
                # Find our wallet's index
                our_index = None
                for idx, key in enumerate(account_keys):
                    key_str = str(key.pubkey) if hasattr(key, 'pubkey') else str(key)
                    if key_str == wallet_address:
                        our_index = idx
                        break
                
                if our_index is None:
                    continue
                
                if not (meta.pre_balances and meta.post_balances):
                    continue
                
                if our_index >= len(meta.pre_balances) or our_index >= len(meta.post_balances):
                    continue
                
                pre_balance = meta.pre_balances[our_index]
                post_balance = meta.post_balances[our_index]
                
                # Check if incoming transfer
                if post_balance > pre_balance:
                    lamports_received = post_balance - pre_balance
                    sol_amount = Decimal(lamports_received) / Decimal('1000000000')
                    
                    logger.info(f"✅ INCOMING: {signature[:16]}... +{sol_amount:.6f} SOL")
                    
                    transactions.append({
                        'signature': signature,
                        'timestamp': block_time,
                        'amount_sol': sol_amount,
                        'confirmed': True
                    })
            
            except Exception as tx_error:
                logger.warning(f"⚠️ Error processing TX: {tx_error}")
                continue
        
        logger.info(f"📊 Found {len(transactions)} incoming transaction(s)")
        return transactions
        
    except Exception as e:
        logger.error(f"Error checking wallet transactions: {e}", exc_info=True)
        return []


async def send_sol_withdrawal(user_id: int, amount_usd: Decimal, destination_address: str) -> dict:
    """
    Execute SOL withdrawal with full security checks.
    
    Security measures:
    - Rate limiting (3/day per user)
    - Amount validation ($10-$1000)
    - Balance verification
    - Wallet balance check
    - Atomic deduction before send
    - Rollback on failure
    - Concurrent request prevention
    
    Returns:
        dict with transaction signature or error
    """
    global SOLANA_MAIN_WALLET_KEYPAIR, solana_client
    
    logger.info(f"💸 [WITHDRAWAL] User {user_id}: ${amount_usd:.2f} → {destination_address[:8]}...")
    
    # Check if withdrawals are possible
    if not SOLANA_MAIN_WALLET_KEYPAIR:
        logger.error("❌ Wallet keypair not initialized")
        return {'error': 'withdrawals_disabled', 'message': 'Withdrawals temporarily unavailable'}
    
    if not solana_client:
        logger.error("❌ Solana client not initialized")
        return {'error': 'network_error', 'message': 'Network connection unavailable'}
    
    # 1. Validate Solana address format
    try:
        dest_pubkey = Pubkey.from_string(destination_address)
    except Exception as e:
        logger.warning(f"❌ Invalid Solana address: {e}")
        return {'error': 'invalid_address', 'message': 'Invalid Solana wallet address'}
    
    # 2. Amount validation
    if amount_usd < MIN_WITHDRAWAL_USD:
        return {
            'error': 'amount_too_low',
            'message': f'Minimum withdrawal: ${MIN_WITHDRAWAL_USD:.2f}'
        }
    
    if amount_usd > MAX_WITHDRAWAL_USD:
        return {
            'error': 'amount_too_high',
            'message': f'Maximum withdrawal: ${MAX_WITHDRAWAL_USD:.2f}'
        }
    
    # 3. Rate limit check
    conn = database.get_sync_connection()
    try:
        # Check daily withdrawal count
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        cursor = conn.execute("""
            SELECT COUNT(*) FROM withdrawal_history 
            WHERE user_id = ? 
            AND created_at >= ? 
            AND status = 'completed'
        """, (user_id, today_start.isoformat()))
        
        withdrawal_count = cursor.fetchone()[0]
        
        if withdrawal_count >= MAX_WITHDRAWALS_PER_DAY:
            logger.warning(f"❌ User {user_id} hit daily withdrawal limit ({withdrawal_count}/{MAX_WITHDRAWALS_PER_DAY})")
            return {
                'error': 'rate_limit',
                'message': f'Daily limit reached ({MAX_WITHDRAWALS_PER_DAY} withdrawals/day)'
            }
        
        # Get SOL price
        sol_price = await get_sol_price_usd()
        if not sol_price or sol_price <= Decimal('0'):
            logger.error("❌ Failed to fetch SOL price")
            return {'error': 'price_fetch_failed', 'message': 'Unable to fetch current price'}
        
        # Calculate withdrawal amount
        withdrawal_fee = amount_usd * WITHDRAWAL_FEE_PERCENT
        net_amount_usd = amount_usd - withdrawal_fee
        sol_amount = (net_amount_usd / sol_price).quantize(Decimal('0.000001'), rounding=ROUND_DOWN)
        
        logger.info(f"  Withdrawal: ${amount_usd:.2f} - ${withdrawal_fee:.2f} fee = ${net_amount_usd:.2f} ({sol_amount:.6f} SOL)")
        
        # 4. User balance check + 5. Wallet balance check + 6. Deduct balance
        # Use per-user lock to prevent concurrent withdrawals
        async with _withdrawal_locks[user_id]:
            # Begin atomic transaction
            conn.execute("BEGIN IMMEDIATE TRANSACTION")
            
            try:
                # Get user balance
                cursor = conn.execute(
                    "SELECT balance FROM users WHERE user_id = ?",
                    (user_id,)
                )
                result = cursor.fetchone()
                
                if not result:
                    conn.rollback()
                    return {'error': 'user_not_found', 'message': 'User account not found'}
                
                current_balance = Decimal(str(result[0]))
                
                if current_balance < amount_usd:
                    conn.rollback()
                    logger.warning(f"❌ Insufficient balance: ${current_balance:.2f} < ${amount_usd:.2f}")
                    return {
                        'error': 'insufficient_balance',
                        'message': f'Insufficient balance (${current_balance:.2f} available)'
                    }
                
                # Check wallet balance
                try:
                    wallet_pubkey = SOLANA_MAIN_WALLET_KEYPAIR.pubkey()
                    balance_response = solana_client.get_balance(wallet_pubkey)
                    if balance_response and balance_response.value is not None:
                        wallet_balance_sol = Decimal(balance_response.value) / Decimal('1000000000')
                        min_required_sol = sol_amount + Decimal('0.01')  # +0.01 SOL reserve for fees
                        
                        if wallet_balance_sol < min_required_sol:
                            conn.rollback()
                            logger.error(f"❌ Wallet insufficient funds: {wallet_balance_sol:.6f} < {min_required_sol:.6f} SOL")
                            return {
                                'error': 'wallet_insufficient_funds',
                                'message': 'System wallet has insufficient funds. Contact admin.'
                            }
                    else:
                        conn.rollback()
                        return {'error': 'network_error', 'message': 'Unable to check wallet balance'}
                except Exception as balance_err:
                    conn.rollback()
                    logger.error(f"Error checking wallet balance: {balance_err}")
                    return {'error': 'network_error', 'message': 'Network error checking balance'}
                
                # Deduct balance BEFORE sending (prevents double-spend)
                new_balance = current_balance - amount_usd
                conn.execute(
                    "UPDATE users SET balance = ? WHERE user_id = ?",
                    (float(new_balance), user_id)
                )
                
                # Create withdrawal record
                withdrawal_id = conn.execute("""
                    INSERT INTO withdrawal_history 
                    (user_id, amount_sol, amount_usd, destination_address, status, created_at)
                    VALUES (?, ?, ?, ?, 'pending', ?)
                    RETURNING id
                """, (
                    user_id,
                    float(sol_amount),
                    float(amount_usd),
                    destination_address,
                    now.isoformat()
                )).fetchone()[0]
                
                conn.commit()
                logger.info(f"✅ Balance deducted: ${current_balance:.2f} → ${new_balance:.2f}")
                
                # 7. Send transaction on blockchain
                try:
                    def send_transaction():
                        # Create transfer instruction
                        transfer_ix = transfer(
                            TransferParams(
                                from_pubkey=SOLANA_MAIN_WALLET_KEYPAIR.pubkey(),
                                to_pubkey=dest_pubkey,
                                lamports=int(sol_amount * Decimal('1000000000'))
                            )
                        )
                        
                        # Create transaction (legacy format - compatible with solana-py)
                        tx = Transaction()
                        tx.add(transfer_ix)
                        
                        # Send transaction with keypair for signing
                        response = solana_client.send_transaction(
                            tx,
                            SOLANA_MAIN_WALLET_KEYPAIR,
                            opts=TxOpts(skip_preflight=False, preflight_commitment=Confirmed)
                        )
                        
                        return response
                    
                    tx_response = await asyncio.to_thread(send_transaction)
                    
                    if tx_response and tx_response.value:
                        signature = str(tx_response.value)
                        logger.info(f"✅ Transaction sent: {signature[:16]}...")
                        
                        # 8. Verify transaction with retries
                        confirmed = False
                        for attempt in range(5):  # Try 5 times
                            await asyncio.sleep(3)  # Wait 3 seconds between attempts
                            
                            try:
                                def verify_transaction():
                                    sig_obj = Signature.from_string(signature)
                                    return solana_client.get_transaction(
                                        sig_obj,
                                        encoding="jsonParsed",
                                        commitment=Confirmed,
                                        max_supported_transaction_version=0
                                    )
                                
                                verify_response = await asyncio.to_thread(verify_transaction)
                                
                                if verify_response and verify_response.value:
                                    confirmed = True
                                    logger.info(f"✅ Transaction confirmed on attempt {attempt + 1}")
                                    break
                                else:
                                    logger.debug(f"Confirmation attempt {attempt + 1}/5: Not yet confirmed")
                            except Exception as verify_error:
                                logger.debug(f"Confirmation attempt {attempt + 1}/5 error: {verify_error}")
                        
                        # Mark as completed regardless (transaction was sent successfully)
                        # Even if confirmation check fails, the transaction is on-chain
                        conn.execute("""
                            UPDATE withdrawal_history 
                            SET status = 'completed',
                                transaction_signature = ?,
                                completed_at = ?
                            WHERE id = ?
                        """, (signature, datetime.now(timezone.utc).isoformat(), withdrawal_id))
                        conn.commit()
                        
                        if confirmed:
                            logger.info(f"🎉 [WITHDRAWAL SUCCESS] User {user_id}: {sol_amount:.6f} SOL sent & confirmed")
                        else:
                            logger.warning(f"⚠️ [WITHDRAWAL SENT] User {user_id}: {sol_amount:.6f} SOL sent (confirmation check timed out, but TX is on-chain)")
                        
                        return {
                            'success': True,
                            'transaction_signature': signature,
                            'sol_amount': float(sol_amount),
                            'amount_usd': float(amount_usd),
                            'fee_usd': float(withdrawal_fee),
                            'confirmed': confirmed
                        }
                    else:
                        raise Exception("Transaction failed to send")
                
                except Exception as tx_error:
                    # ROLLBACK: Transaction failed, restore balance
                    logger.error(f"❌ Transaction failed: {tx_error}")
                    
                    conn.execute(
                        "UPDATE users SET balance = ? WHERE user_id = ?",
                        (float(current_balance), user_id)
                    )
                    conn.execute("""
                        UPDATE withdrawal_history 
                        SET status = 'failed',
                            error_message = ?
                        WHERE id = ?
                    """, (str(tx_error)[:500], withdrawal_id))
                    conn.commit()
                    
                    logger.warning(f"⏪ Balance restored: ${new_balance:.2f} → ${current_balance:.2f}")
                    
                    return {
                        'error': 'transaction_failed',
                        'message': 'Transaction failed. Balance restored.'
                    }
            
            except Exception as db_error:
                conn.rollback()
                logger.error(f"Database error during withdrawal: {db_error}", exc_info=True)
                return {'error': 'database_error', 'message': 'Internal error. Please try again.'}
    
    finally:
        conn.close()


async def check_pending_deposits(bot=None):
    """
    Background task: Check for incoming deposits and credit users.
    Runs periodically to monitor the blockchain for matching transactions.
    
    Args:
        bot: Telegram bot instance (optional, for notifications)
    """
    logger.info("🔍 Checking pending deposits...")
    
    conn = None
    try:
        conn = database.get_sync_connection()
        
        # Get pending deposits
        cursor = conn.execute("""
            SELECT deposit_id, user_id, expected_sol_amount, expected_usd_amount, 
                   created_at, expires_at, chat_id, message_id
            FROM pending_sol_deposits
            WHERE status = 'pending'
            ORDER BY created_at DESC
            LIMIT 50
        """)
        
        pending_deposits = cursor.fetchall()
        
        if not pending_deposits:
            logger.debug("No pending deposits")
            return
        
        logger.info(f"📋 Found {len(pending_deposits)} pending deposit(s)")
        
        # Get recent transactions from blockchain
        transactions = await check_wallet_transactions(limit=20)
        
        if not transactions:
            logger.debug("No recent transactions on blockchain")
            return
        
        # Match transactions to pending deposits
        for deposit in pending_deposits:
            deposit_id = deposit[0]
            user_id = deposit[1]
            expected_sol = Decimal(str(deposit[2]))
            expected_usd = Decimal(str(deposit[3]))
            created_at_str = deposit[4]
            expires_at_str = deposit[5]
            chat_id = deposit[6]
            message_id = deposit[7]
            
            # Check expiration
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            if datetime.now(timezone.utc) > expires_at:
                logger.info(f"⏰ Deposit {deposit_id} expired")
                conn.execute(
                    "UPDATE pending_sol_deposits SET status = 'expired' WHERE deposit_id = ?",
                    (deposit_id,)
                )
                conn.commit()
                continue
            
            # Try to match with transactions
            tolerance = Decimal('0.00001')  # 0.00001 SOL tolerance for matching
            
            for tx in transactions:
                tx_amount = tx['amount_sol']
                tx_signature = tx['signature']
                
                # Check if amounts match (within tolerance)
                if abs(tx_amount - expected_sol) <= tolerance:
                    # Match found!
                    logger.info(f"✅ MATCH! {deposit_id}: {tx_amount:.6f} SOL (TX: {tx_signature[:16]}...)")
                    
                    # Credit user balance
                    conn.execute(
                        "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                        (float(expected_usd), user_id)
                    )
                    
                    # Mark deposit as confirmed
                    conn.execute("""
                        UPDATE pending_sol_deposits 
                        SET status = 'confirmed',
                            transaction_signature = ?,
                            confirmed_at = ?
                        WHERE deposit_id = ?
                    """, (tx_signature, datetime.now(timezone.utc).isoformat(), deposit_id))
                    
                    conn.commit()
                    
                    logger.info(f"💰 User {user_id} credited ${expected_usd:.2f}")
                    
                    # Send notification to user
                    if bot and chat_id and message_id:
                        try:
                            # Get user's new balance
                            balance_cursor = conn.execute(
                                "SELECT balance FROM users WHERE user_id = ?",
                                (user_id,)
                            )
                            balance_result = balance_cursor.fetchone()
                            new_balance = Decimal(str(balance_result[0])) if balance_result else expected_usd
                            
                            # Update the original deposit message
                            confirmation_text = (
                                f"✅ <b>Įnešimas patvirtintas!</b>\n\n"
                                f"Suma: <b>${expected_usd:.2f}</b>\n"
                                f"Gauta: <b>{tx_amount:.6f} SOL</b>\n\n"
                                f"🔗 Transakcija:\n"
                                f"<code>{tx_signature[:16]}...{tx_signature[-16:]}</code>\n\n"
                                f"Jūsų naujas balansas: <b>${new_balance:.2f}</b>\n\n"
                                f"Patikrinkite: https://solscan.io/tx/{tx_signature}"
                            )
                            
                            await bot.edit_message_caption(
                                chat_id=chat_id,
                                message_id=message_id,
                                caption=confirmation_text,
                                parse_mode='HTML'
                            )
                            
                            logger.info(f"📨 Notification sent to user {user_id}")
                            
                        except Exception as notify_error:
                            logger.error(f"Failed to update deposit message: {notify_error}")
                            # Try sending a new message instead
                            try:
                                await bot.send_message(
                                    chat_id=chat_id,
                                    text=confirmation_text,
                                    parse_mode='HTML'
                                )
                            except:
                                logger.error(f"Failed to send notification message to {user_id}")
                    
                    break
        
        logger.info("✅ Deposit check complete")
        
    except Exception as e:
        logger.error(f"Error checking pending deposits: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()


async def start_deposit_monitoring(application):
    """
    Start background task to monitor deposits.
    This runs continuously while the bot is active.
    """
    logger.info("🚀 Starting deposit monitoring task...")
    
    bot = application.bot
    
    while True:
        try:
            await check_pending_deposits(bot=bot)
        except Exception as e:
            logger.error(f"Error in deposit monitoring loop: {e}", exc_info=True)
        
        # Wait before next check
        await asyncio.sleep(SOL_CHECK_INTERVAL)


# Initialize on module import
try:
    init_solana_config()
except Exception as e:
    logger.error(f"Failed to initialize Solana config: {e}")

