# Solana Payment System Setup Guide

## Overview

The bot now uses **direct Solana blockchain monitoring** instead of NowPayments. All deposits go to a single main wallet, and withdrawals are sent from this same wallet.

## 🔑 Required Configuration

### 1. Create a Solana Wallet

You need to create a dedicated Solana wallet for the bot. You can use any Solana wallet, but we recommend:

**Option A: Using Phantom Wallet (Easiest)**
1. Install Phantom browser extension
2. Create a new wallet
3. **CRITICAL:** Export the private key:
   - Settings → Security & Privacy → Show Private Key
   - Save both the **public address** and **private key** securely

**Option B: Using Solana CLI (Advanced)**
```bash
# Install Solana CLI
sh -c "$(curl -sSfL https://release.solana.com/stable/install)"

# Generate new keypair
solana-keygen new --outfile ~/solana-wallet.json

# Get public address
solana-keygen pubkey ~/solana-wallet.json

# Get private key (base58)
cat ~/solana-wallet.json
# Copy the private key array and convert to base58 using a tool
```

### 2. Configure Environment Variables on Render

Go to your Render dashboard → Your service → Environment:

**Add these new variables:**
```bash
# Solana Main Wallet (REQUIRED)
SOLANA_MAIN_WALLET_ADDRESS=<your_wallet_public_address>
SOLANA_MAIN_WALLET_PRIVATE_KEY=<your_wallet_private_key_base58>

# Solana RPC URL (Optional - uses public endpoint by default)
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
```

**Optional: Use a paid RPC for better reliability:**
- QuickNode: `https://your-endpoint.quiknode.pro/xxxxx/`
- Helius: `https://rpc.helius.xyz/?api-key=xxxxx`
- Alchemy: `https://solana-mainnet.g.alchemy.com/v2/xxxxx`

Free tier from these providers is usually enough for most bots.

### 3. Fund Your Wallet

**IMPORTANT:** Your main wallet needs SOL to cover:
- Withdrawal transaction fees (~0.000005 SOL per transaction)
- Withdrawal amounts

**Recommended minimum balance:** 5-10 SOL

You can buy SOL on any crypto exchange (Binance, Coinbase, etc.) and send it to your wallet address.

### 4. Security Best Practices

⚠️ **CRITICAL SECURITY RULES:**

1. **NEVER** commit the private key to Git
2. **NEVER** share the private key with anyone
3. Use environment variables ONLY
4. Consider using a dedicated wallet for the bot (not your personal wallet)
5. Enable 2FA on Render dashboard
6. Regularly monitor wallet balance and transactions

### 5. Remove Old NowPayments Variables (Optional)

You can remove these old environment variables from Render:
- `NOWPAYMENTS_API_KEY`
- `NOWPAYMENTS_EMAIL`
- `NOWPAYMENTS_PASSWORD`
- `WEBHOOK_URL` (unless you need it for other purposes)

The bot will work fine with or without them.

## 📊 How It Works

### Deposits

1. User sends `/pinigine` → bot shows balance with "Įnešti" button
2. User clicks button → bot asks for amount (min $10)
3. Bot generates unique SOL amount (e.g., 0.068342 SOL for $10)
4. Bot shows QR code with wallet address and exact amount
5. User sends SOL from their wallet (Phantom, Solflare, etc.)
6. Bot monitors blockchain every 30 seconds
7. When transaction is detected, balance is credited automatically
8. No confirmation needed - fully automatic

### Withdrawals

1. User clicks "Išimti" button
2. Bot asks for: `amount address` (e.g., `50.00 DiNrF7c...`)
3. User confirms
4. Bot performs security checks:
   - Rate limit: Max 3 withdrawals per 24h
   - Amount limit: $10-$1000 per transaction
   - Balance check: User has sufficient funds
   - Wallet check: Main wallet has sufficient SOL
5. Balance is deducted FIRST (prevents double-spend)
6. Transaction is sent to blockchain
7. On success: User receives confirmation with transaction link
8. On failure: Balance is automatically restored

### Security Features

✅ **Rate Limiting:** 3 withdrawals per 24 hours per user  
✅ **Amount Limits:** $10 minimum, $1000 maximum  
✅ **Withdrawal Fee:** 1% (configurable)  
✅ **Atomic Operations:** Balance deducted before sending  
✅ **Automatic Rollback:** Balance restored if transaction fails  
✅ **Concurrent Prevention:** One withdrawal at a time per user  
✅ **Audit Logging:** All transactions logged to database  

## 🧪 Testing

### Test on Devnet First (Recommended)

Before going live, test on Solana devnet:

1. Create a devnet wallet:
   ```bash
   solana-keygen new --outfile ~/devnet-wallet.json
   solana config set --url https://api.devnet.solana.com
   ```

2. Get free devnet SOL:
   ```bash
   solana airdrop 2
   ```

3. Update environment variables:
   ```bash
   SOLANA_RPC_URL=https://api.devnet.solana.com
   SOLANA_MAIN_WALLET_ADDRESS=<devnet_address>
   SOLANA_MAIN_WALLET_PRIVATE_KEY=<devnet_private_key>
   ```

4. Test deposits and withdrawals with devnet SOL (no real money)

### Switch to Mainnet

When ready for production:

1. Update `SOLANA_RPC_URL` to mainnet
2. Update wallet credentials to mainnet wallet
3. Fund wallet with real SOL
4. Deploy and monitor logs

## 📈 Monitoring

### Check Bot Logs

Watch for these log messages:

```
✅ Solana payment system ready
🔍 Starting Solana deposit monitoring...
💰 Main wallet balance: 10.234567 SOL
✅ INCOMING: abc123... +0.068342 SOL
✅ MATCH! SOL_DEP_123_abc: 0.068342 SOL
💰 User 123456 credited $10.00
💸 Withdrawal completed: User 789, $50.00, TX: def456...
```

### Database Tables

New tables created automatically:
- `pending_sol_deposits` - Pending deposit requests
- `withdrawal_history` - All withdrawal attempts
- `withdrawal_rate_limits` - Rate limiting data

### Useful SQL Queries

```sql
-- Check pending deposits
SELECT * FROM pending_sol_deposits WHERE status = 'pending';

-- Check recent withdrawals
SELECT * FROM withdrawal_history ORDER BY created_at DESC LIMIT 10;

-- Check user withdrawal count today
SELECT user_id, COUNT(*) as count 
FROM withdrawal_history 
WHERE created_at >= date('now') AND status = 'completed'
GROUP BY user_id;
```

## 🚨 Troubleshooting

### Bot fails to start: "Failed to initialize Solana"

**Cause:** Invalid wallet credentials  
**Fix:** Check that `SOLANA_MAIN_WALLET_PRIVATE_KEY` is valid base58 format

### Deposits not detecting

**Cause:** RPC connection issues or wrong wallet address  
**Fix:**
1. Check logs for "Fetching transactions for..."
2. Verify `SOLANA_MAIN_WALLET_ADDRESS` is correct
3. Try a different RPC URL (QuickNode, Helius, etc.)

### Withdrawal fails: "Wallet insufficient funds"

**Cause:** Main wallet doesn't have enough SOL  
**Fix:** Send more SOL to your main wallet

### Rate limit errors

**Cause:** Free RPC providers have rate limits  
**Fix:** Upgrade to paid RPC plan or reduce `SOL_CHECK_INTERVAL` in config.py

## 🎯 Admin Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/pinigine` | Show balance | `/pinigine` |
| `/setbalance` | Set user balance | `/setbalance @user 100.00` |
| `/addbalance` | Add to balance | `/addbalance @user 50.00` |
| `/removebalance` | Remove from balance | `/removebalance @user 25.00` |
| `/togglewithdrawals` | Enable/disable withdrawals | `/togglewithdrawals` |
| `/tip` | Send balance to user | `/tip @user 10.00` |

## 📝 Configuration Options

Edit `solana_payments.py` to customize:

```python
# Withdrawal limits
MIN_WITHDRAWAL_USD = Decimal('10.0')      # Minimum $10
MAX_WITHDRAWAL_USD = Decimal('1000.0')    # Maximum $1000
MAX_WITHDRAWALS_PER_DAY = 3                # 3 per 24h
WITHDRAWAL_FEE_PERCENT = Decimal('0.01')   # 1% fee

# Deposit expiration
expires = now + timedelta(minutes=20)      # 20 minute timeout

# Monitoring interval
SOL_CHECK_INTERVAL = 30  # Check every 30 seconds
```

Edit `config.py` to change RPC URL:
```python
SOL_CHECK_INTERVAL = 30  # Seconds between blockchain checks
```

## ✅ Post-Deployment Checklist

- [ ] Environment variables set on Render
- [ ] Main wallet funded with SOL
- [ ] Bot successfully starts (check logs)
- [ ] Deposit monitoring running (see "🔍 Starting Solana deposit monitoring...")
- [ ] Test deposit with small amount ($10)
- [ ] Verify automatic crediting works
- [ ] Test withdrawal with small amount ($10)
- [ ] Verify transaction on solscan.io
- [ ] Monitor logs for errors
- [ ] Set up wallet balance alerts (recommended)

## 🆘 Support

If you encounter issues:

1. Check Render logs for error messages
2. Verify environment variables are set correctly
3. Test wallet credentials with Solana CLI
4. Check Solana network status: https://status.solana.com/
5. Verify transactions on Solscan: https://solscan.io/

## 🔄 Rollback to NowPayments (Emergency)

If you need to revert to NowPayments:

```bash
# Restore old payments.py
git checkout HEAD~1 payments.py

# Re-add NowPayments config
# Set NOWPAYMENTS_API_KEY, NOWPAYMENTS_EMAIL, etc. in Render

# Push changes
git add payments.py
git commit -m "revert: Rollback to NowPayments"
git push origin main
```

The old NowPayments code is backed up in `payments_nowpayments_backup.py`.

