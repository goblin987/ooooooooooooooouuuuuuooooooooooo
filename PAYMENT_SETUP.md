# 💰 Payment System Setup Guide

## Required Environment Variables

Add these to your Render.com environment variables:

### 1. **NOWPAYMENTS_API_KEY** ⭐ REQUIRED
- **Where to get it:** https://account.nowpayments.io/settings/api-keys
- **What it is:** Your NOWPayments API key for creating payment addresses
- **Example:** `ABC123XYZ456...`

### 2. **NOWPAYMENTS_EMAIL** ⭐ REQUIRED (for withdrawals)
- **Where to get it:** Your NOWPayments account email
- **What it is:** Email used to login to NOWPayments
- **Example:** `your-email@example.com`

### 3. **NOWPAYMENTS_PASSWORD** ⭐ REQUIRED (for withdrawals)
- **Where to get it:** Your NOWPayments account password
- **What it is:** Password used to login to NOWPayments
- **Example:** `YourSecurePassword123`

### 4. **WEBHOOK_URL** ⭐ REQUIRED
- **Where to get it:** Your Render.com service URL
- **What it is:** Your bot's public URL for receiving payment notifications
- **Example:** `https://grpbot9999.onrender.com`

### 5. **BOT_USERNAME** ⭐ REQUIRED
- **Where to get it:** Your bot's @username (without the @)
- **What it is:** Used in deposit/withdraw redirect messages
- **Example:** `your_bot_name`

### 6. **OWNER_ID** (Recommended)
- **Where to get it:** Your Telegram user ID (use @userinfobot)
- **What it is:** Your Telegram ID for admin commands
- **Example:** `123456789`

---

## Step-by-Step Setup

### Step 1: Create NOWPayments Account
1. Go to https://nowpayments.io/
2. Sign up for an account
3. Complete KYC verification (if required)
4. Go to Settings → API Keys
5. Create a new API key
6. Copy the API key

### Step 2: Configure NOWPayments Webhooks
1. In NOWPayments dashboard, go to Settings → IPN/Callbacks
2. Set IPN Callback URL to: `https://YOUR-RENDER-URL.onrender.com/payment_webhook`
3. Example: `https://grpbot9999.onrender.com/payment_webhook`
4. Save the settings

### Step 3: Add Environment Variables to Render
Go to your Render.com dashboard → Your service → Environment tab

Add these variables:

```
NOWPAYMENTS_API_KEY=your_api_key_here
NOWPAYMENTS_EMAIL=your-email@example.com
NOWPAYMENTS_PASSWORD=YourSecurePassword123
WEBHOOK_URL=https://grpbot9999.onrender.com
BOT_USERNAME=your_bot_name
OWNER_ID=123456789
```

### Step 4: Test Deposits
1. Type `/pinigine` or `/balance` in your bot
2. Click "💵 Įnešti" button
3. Select a cryptocurrency (e.g., LTC)
4. Send a small test amount to the generated address
5. Wait for confirmation (usually 1-10 minutes)
6. Check your balance with `/pinigine`

### Step 5: Test Withdrawals
1. Make sure you have balance (from test deposit)
2. Type `/pinigine` in private chat with bot
3. Click "💸 Išimti" button
4. Enter: `amount LTC_address`
   - Example: `5 LTC1ABC123...`
5. Bot will process the withdrawal
6. Check your wallet for the funds

---

## Database Setup (Automatic)

The bot will automatically create these tables on first run:

```sql
CREATE TABLE IF NOT EXISTS pending_deposits (
    payment_id TEXT PRIMARY KEY,
    user_id INTEGER,
    currency TEXT
);
```

No manual database setup needed! ✅

---

## Webhook Endpoint

The bot creates this endpoint automatically:
- **URL:** `https://YOUR-URL.onrender.com/payment_webhook`
- **Method:** POST
- **Purpose:** Receives payment notifications from NOWPayments

---

## Supported Cryptocurrencies

- ✅ **SOLANA** (SOL)
- ✅ **USDT TRX** (Tether on TRON)
- ✅ **USDT ETH** (Tether on Ethereum)
- ✅ **BTC** (Bitcoin)
- ✅ **ETH** (Ethereum)
- ✅ **LTC** (Litecoin) - For deposits AND withdrawals

---

## Admin Commands

Once `OWNER_ID` is set, you can use:

- `/addbalance @username 100` - Add $100 to user's balance
- `/removebalance @username 50` - Remove $50 from user's balance

---

## Troubleshooting

### ❌ "API key is invalid"
- Check that `NOWPAYMENTS_API_KEY` is correct
- Make sure you copied the entire key
- Check that the key is active in NOWPayments dashboard

### ❌ "Failed to generate deposit address"
- Check that `WEBHOOK_URL` is set correctly
- Make sure your Render service is running
- Check NOWPayments API status

### ❌ "Withdrawal failed"
- Check that `NOWPAYMENTS_EMAIL` and `NOWPAYMENTS_PASSWORD` are correct
- Make sure you have sufficient funds in NOWPayments account
- Check that the LTC address is valid

### ❌ Deposit not credited
- Wait 10-15 minutes for blockchain confirmation
- Check the transaction on blockchain explorer
- Check Render logs for webhook errors: `payment_webhook`
- Make sure the payment was sent to the correct address

---

## Testing Checklist

- [ ] Environment variables added to Render
- [ ] Bot redeployed after adding env vars
- [ ] NOWPayments IPN callback URL set
- [ ] Test deposit with small amount (e.g., $1)
- [ ] Deposit credited to balance
- [ ] Test withdrawal with small amount
- [ ] Withdrawal received in wallet
- [ ] Admin commands work (`/addbalance`)

---

## Security Notes

⚠️ **IMPORTANT:**
- Never share your `NOWPAYMENTS_API_KEY`
- Never share your `NOWPAYMENTS_PASSWORD`
- Keep `OWNER_ID` private (only for trusted admins)
- Use strong passwords for NOWPayments account
- Enable 2FA on NOWPayments account

---

## Fee Structure

- **Deposit fees:** Covered by NOWPayments (1.5% deducted automatically)
- **Withdrawal fees:** Check NOWPayments current rates
- **Network fees:** Paid by user (blockchain transaction fees)

---

## Need Help?

1. Check Render logs for errors
2. Check NOWPayments dashboard for payment status
3. Test with small amounts first
4. Make sure all environment variables are set correctly

---

## Current Environment Variables Summary

Based on your screenshot, you have:
- ✅ `TELEGRAM_TOKEN` (BOT_TOKEN)
- ✅ `ADMIN_CHAT_ID`
- ✅ `DATA_DIR`
- ✅ `GROUP_CHAT_ID`
- ✅ `HELPER_IDS`
- ✅ `PASSWORD`
- ✅ `VOTING_GROUP_CHAT_ID`
- ✅ `VOTING_GROUP_LINK`

**Still need to add:**
- ❌ `NOWPAYMENTS_API_KEY`
- ❌ `NOWPAYMENTS_EMAIL`
- ❌ `NOWPAYMENTS_PASSWORD`
- ❌ `WEBHOOK_URL`
- ❌ `BOT_USERNAME`
- ❌ `OWNER_ID` (optional but recommended)

---

Good luck! 🚀

