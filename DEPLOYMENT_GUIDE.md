# 🚀 Deployment Guide - OGbotas Telegram Bot

**Version:** 1.0  
**Date:** October 2024  
**Platform:** Render.com

---

## 📋 Prerequisites

### 1. Telegram Bot Setup
- [ ] Create bot via [@BotFather](https://t.me/BotFather)
- [ ] Get bot token (format: `123456789:ABCdef...`)
- [ ] Set bot commands with BotFather
- [ ] Get your Telegram user ID (use [@userinfobot](https://t.me/userinfobot))

### 2. Render Account
- [ ] Sign up at [render.com](https://render.com)
- [ ] Connect your GitHub account
- [ ] Have credit card ready (free tier available)

### 3. NOWPayments Account (for crypto payments)
- [ ] Sign up at [nowpayments.io](https://nowpayments.io)
- [ ] Get API key from dashboard
- [ ] Note your account email and password
- [ ] Set up IPN (webhook) URL (you'll get this from Render)

### 4. Test Groups
- [ ] Create a test Telegram group
- [ ] Add your bot as admin with all permissions
- [ ] Create a voting group (optional)
- [ ] Get group chat IDs (use `/info` command or [@getidsbot](https://t.me/getidsbot))

---

## 🔧 Render Setup

### Step 1: Create New Web Service

1. Go to [Render Dashboard](https://dashboard.render.com)
2. Click "New +" → "Web Service"
3. Connect your GitHub repository
4. Configure:
   - **Name:** `apsisaugok-bot-staging` (or your choice)
   - **Region:** Frankfurt (EU Central) - recommended for Lithuania
   - **Branch:** `main`
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python OGbotas.py`

### Step 2: Environment Variables

Add the following in Render dashboard under "Environment":

#### **Required Variables:**

```bash
# Bot Configuration
BOT_TOKEN=123456789:ABCdef-YourBotTokenHere
TELEGRAM_TOKEN=123456789:ABCdef-YourBotTokenHere  # Same as BOT_TOKEN (for compatibility)
BOT_USERNAME=YourBotUsername  # Without @

# Admin Configuration
OWNER_ID=123456789  # Your Telegram user ID
ADMIN_CHAT_ID=123456789  # Can be same as OWNER_ID or admin group chat ID

# Server Configuration
PORT=8000
DATA_DIR=/opt/render/data
WEBHOOK_URL=https://your-app-name.onrender.com

# NOWPayments (for crypto payments)
NOWPAYMENTS_API_KEY=your_api_key_here
NOWPAYMENTS_EMAIL=your@email.com
NOWPAYMENTS_PASSWORD=your_password

# Voting System (optional)
VOTING_GROUP_CHAT_ID=-1001234567890  # Your voting group ID
VOTING_GROUP_LINK=https://t.me/+your_invite_link  # Invite link
```

#### **How to Get Each Value:**

- **BOT_TOKEN**: From [@BotFather](https://t.me/BotFather) - /mybots → select bot → API Token
- **OWNER_ID**: Your user ID from [@userinfobot](https://t.me/userinfobot)
- **ADMIN_CHAT_ID**: Same as OWNER_ID, or use group chat ID
- **WEBHOOK_URL**: Your Render app URL (shown after first deploy)
- **NOWPAYMENTS_API_KEY**: [NOWPayments Dashboard](https://nowpayments.io/app) → Settings → API Keys
- **VOTING_GROUP_CHAT_ID**: Use [@getidsbot](https://t.me/getidsbot) in your group (forward message)
- **VOTING_GROUP_LINK**: Telegram group settings → Invite Links → Create invite link

### Step 3: Persistent Disk (Important!)

1. In Render dashboard, go to your service
2. Click "Disks" in left sidebar
3. Click "Add Disk"
4. Configure:
   - **Name:** `data`
   - **Mount Path:** `/opt/render/data`
   - **Size:** 1 GB (free tier)
5. Save

**⚠️ Critical:** Without persistent disk, your database will be deleted on every deploy!

### Step 4: Deploy

1. Click "Manual Deploy" → "Deploy latest commit"
2. Wait 2-5 minutes for build
3. Monitor logs for errors

---

## ✅ Verification Steps

### 1. Check Deployment Status

```bash
# Check if bot is running
curl https://your-app-name.onrender.com/

# Expected response: "✅ Bot is running!"
```

### 2. Check Logs

In Render dashboard:
1. Go to your service
2. Click "Logs" tab
3. Look for these startup messages:

```
INFO - 🚀 Starting OGbotas...
INFO - Database initialized successfully
INFO - 🌐 HTTP Server started on port 8000
INFO - 🤖 Starting bot in POLLING mode...
INFO - 📅 Loading scheduled recurring messages...
INFO - ✅ Bot is fully operational!
```

**❌ If you see errors:**
- `BOT_TOKEN environment variable not set!` → Add BOT_TOKEN in environment variables
- `DatabaseError` → Check DATA_DIR is `/opt/render/data` and disk is mounted
- `ImportError` → Re-deploy to rebuild dependencies

### 3. Test Bot Commands

In Telegram, private message to your bot:

```
/start
```

**Expected:** Welcome message with command list (admin view if you're the owner)

```
/help
```

**Expected:** Full command list

```
/admin
```

**Expected:** Admin panel with buttons (only if OWNER_ID matches your user ID)

---

## 🔗 NOWPayments Webhook Setup

### Configure IPN (Instant Payment Notification)

1. Go to [NOWPayments Dashboard](https://nowpayments.io/app)
2. Settings → IPN Settings
3. Set IPN Callback URL to:
   ```
   https://your-app-name.onrender.com/webhook/nowpayments
   ```
4. Save

### Test Webhook

```bash
# Send test webhook (from terminal or Postman)
curl -X POST https://your-app-name.onrender.com/webhook/nowpayments \
  -H "Content-Type: application/json" \
  -d '{
    "payment_id": "test123",
    "payment_status": "finished",
    "price_amount": 1.00,
    "price_currency": "usd",
    "pay_amount": 0.001,
    "pay_currency": "ltc",
    "order_id": "user_YOUR_USER_ID"
  }'
```

**Check logs for:** `📥 Webhook RAW:`

---

## 🧪 Testing Checklist

Use the comprehensive [TESTING_CHECKLIST.md](TESTING_CHECKLIST.md) file.

**Quick Smoke Test:**

1. ✅ `/start` - Bot responds
2. ✅ `/balance` - Shows balance interface
3. ✅ `/dice2 10` - Starts points game
4. ✅ `/help` - Shows all commands
5. ✅ Create test group, add bot, make admin
6. ✅ `/ban @user` - Moderation works
7. ✅ `/recurring` - Recurring messages menu
8. ✅ Test small deposit ($1-2) ⚠️ REAL MONEY

---

## 🐛 Common Issues & Solutions

### Issue: "Bot doesn't respond"

**Cause:** Bot token incorrect or bot not started

**Solution:**
1. Verify BOT_TOKEN in environment variables
2. Check logs for "Bot is fully operational!"
3. Restart service in Render dashboard

---

### Issue: "Database errors on startup"

**Cause:** Persistent disk not mounted or wrong path

**Solution:**
1. Check disk is mounted at `/opt/render/data`
2. Verify DATA_DIR=`/opt/render/data` in environment
3. Restart service

---

### Issue: "Payment webhook not received"

**Cause:** IPN URL not configured in NOWPayments

**Solution:**
1. Verify webhook URL in NOWPayments dashboard
2. Test with curl command above
3. Check logs for incoming webhooks

---

### Issue: "Admin commands don't work"

**Cause:** OWNER_ID or ADMIN_CHAT_ID not set correctly

**Solution:**
1. Get your exact user ID from [@userinfobot](https://t.me/userinfobot)
2. Update OWNER_ID in environment variables
3. Restart service
4. Try `/admin` again

---

### Issue: "ModuleNotFoundError"

**Cause:** Dependencies not installed

**Solution:**
1. Check requirements.txt exists
2. In Render, clear build cache
3. Manually deploy again

---

### Issue: "Games don't work"

**Cause:** Could be various (user caching, balance, etc.)

**Solution:**
1. Check logs for game-related errors
2. Ensure user sent at least one message (for caching)
3. Check balance with `/balance`
4. Try `/cleargames` to reset stuck games

---

## 📊 Monitoring

### Health Check

```bash
# Automated health check (set up in monitoring service)
curl https://your-app-name.onrender.com/health
```

### Logs

**Render Dashboard:**
- Logs tab → Real-time view
- Filter by level: ERROR, WARNING, INFO

**Download logs:**
```bash
# Via Render CLI
render logs -s your-service-name
```

### Database Backup

**Manual backup (via SSH or shell):**
```bash
# If shell access available
sqlite3 /opt/render/data/bot_database.db ".backup '/tmp/backup.db'"
```

**Recommended:** Set up automated daily backups

---

## 🔄 Updates & Deployments

### Deploy New Code

1. Push changes to GitHub
2. Render auto-deploys (if enabled) OR
3. Manual deploy in Render dashboard

### Database Migrations

**If you add new tables:**

1. Update `database.py` with new table schema
2. Deploy
3. Bot will auto-create new tables on startup

**If you modify existing tables:**

1. Write migration script
2. Run before deploying new code
3. Document in CHANGELOG

---

## 🚦 Go-Live Checklist

Before switching from staging to production:

- [ ] All tests in TESTING_CHECKLIST.md passed
- [ ] Payment system tested with real crypto
- [ ] All environment variables verified
- [ ] Database backed up
- [ ] Monitoring set up
- [ ] Error logging reviewed
- [ ] Known issues documented
- [ ] Rollback plan ready

### Production Deployment

1. Create new Render service: `apsisaugok-bot-production`
2. Same configuration as staging
3. **Different BOT_TOKEN** (create new bot or use existing production bot)
4. Test thoroughly before announcing

---

## 📞 Support & Resources

- **Render Documentation:** https://render.com/docs
- **Telegram Bot API:** https://core.telegram.org/bots/api
- **NOWPayments API:** https://documenter.getpostman.com/view/7907941/S1a32n38
- **Python Telegram Bot Library:** https://python-telegram-bot.readthedocs.io

---

## 🔐 Security Best Practices

1. ✅ Keep API keys in environment variables (never commit to git)
2. ✅ Use different bots for staging and production
3. ✅ Regularly rotate NOWPayments API key
4. ✅ Monitor logs for suspicious activity
5. ✅ Keep dependencies updated (security patches)
6. ✅ Backup database regularly
7. ✅ Limit admin access (OWNER_ID)

---

**Deployment Status:** ⬜ Staging / ⬜ Production  
**Last Updated:** ___________  
**Deployed By:** ___________


