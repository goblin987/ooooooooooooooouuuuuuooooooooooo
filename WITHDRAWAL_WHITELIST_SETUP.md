# 🔐 How to Whitelist Withdrawal Addresses in NowPayments

## Why Address Whitelisting?

For security, NowPayments requires all withdrawal addresses to be **pre-approved (whitelisted)** before users can withdraw funds to them. This prevents unauthorized withdrawals.

---

## ⚠️ Error You'll See

When a user tries to withdraw to a non-whitelisted address, they'll see:

```
⚠️ Adresas nepatvirtintas

Šis SOLANA adresas dar nėra patvirtintas išėmimams.

📍 Adresas:
DiNrF7cHF13eQzKD3HXi6Qh9qnxbrKZFrHuW4WFA7XVD

🔐 Ką daryti?
Susisiekite su administratoriumi, kad patvirtintų šį adresą sistemoje.

💡 Tai saugumo priemonė, skirta apsaugoti jūsų lėšas.
```

---

## 📋 How to Whitelist an Address

### Step 1: Go to NowPayments Dashboard

1. Log in to https://account.nowpayments.io/
2. Go to **Settings** → **API** → **Payout**

### Step 2: Add Withdrawal Address

1. Find the **"Whitelisted Addresses"** section
2. Click **"Add Address"**
3. Enter the details:
   - **Currency**: Select `SOL` (Solana)
   - **Address**: Paste the user's address (e.g., `DiNrF7cHF13eQzKD3HXi6Qh9qnxbrKZFrHuW4WFA7XVD`)
   - **Label** (optional): User identifier (e.g., "User @username")
4. Click **"Save"** or **"Add"**

### Step 3: Verify

1. The address should now appear in your whitelist
2. User can retry the withdrawal - it should now work! ✅

---

## 🎯 Best Practices

### Option A: Pre-Whitelist Common Addresses
- If you have regular users, add their addresses proactively
- Saves support requests

### Option B: Whitelist On-Demand
- When user gets the error, they contact you
- You whitelist their address
- They retry - works immediately

### Option C: Allow Multiple Addresses Per User
- Users may have multiple wallets
- Whitelist each one as requested

---

## 🔧 For Developers

The bot now handles whitelist errors gracefully:

```python
# In initiate_payout() function:
if 'not whitelisted' in error_message.lower():
    return {
        "status": "error",
        "code": "NOT_WHITELISTED",
        "message": "Adresas nepatvirtintas sistemoje. Susisiekite su administratoriumi."
    }
```

Users see a clear message instead of a generic error.

---

## 🆘 Troubleshooting

### "Address is already whitelisted but still getting error"
- **Solution**: Wait 1-2 minutes after whitelisting (cache delay)
- Or try logging out and back into NowPayments dashboard

### "Can't find whitelist settings"
- **Solution**: Make sure you have **Payout API** enabled in your NowPayments account
- Contact NowPayments support if the option is missing

### "Multiple addresses need whitelisting"
- **Solution**: You can add up to 50-100 addresses (check your plan limit)
- Consider upgrading if you hit the limit

---

## 📞 Support

If users continue having issues after whitelisting:
1. Double-check the address is typed correctly
2. Verify it's a valid Solana address
3. Check NowPayments dashboard for any pending verifications
4. Contact NowPayments support: support@nowpayments.io

---

**Remember:** This is a security feature, not a bug! It protects both you and your users from unauthorized withdrawals. 🔒

