# 🔍 Read-Only Scammer Check Bot for Render

A standalone Telegram bot that provides read-only access to scammer and buyer reports. Designed for hosting on Render with SQLite database and API sync capabilities.

## 🚀 Features

- **🔍 `/patikra username`** - Check if user is scammer/bad buyer
- **📊 `/scameris username`** - View all scammer reports
- **🛒 `/vagis username`** - View all buyer reports  
- **📈 `/stats`** - Overall statistics
- **❓ `/help`** - Help message
- **🔄 API Sync** - Syncs data from main bot via API

## 🏗️ Architecture

- **SQLite Database** - Persistent data storage
- **API Server** - Receives data updates from main bot
- **Telegram Bot** - User interface
- **Render Hosting** - Cloud deployment

## 📋 Render Deployment

### 1. Create New Render Service

1. Go to [Render.com](https://render.com)
2. Connect your GitHub repository
3. Create a **Web Service**
4. Select this directory: `readonly_scammer_bot/`

### 2. Configure Environment Variables

In Render dashboard, set these environment variables:

```
BOT_TOKEN=your_telegram_bot_token_from_botfather
API_SECRET=your_very_secure_random_secret_key
DATABASE_PATH=scammer_reports.db
MAIN_BOT_API_URL=https://your-main-bot-url.com
```

### 3. Deployment Settings

- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `python main.py`
- **Environment**: Python 3.11
- **Plan**: Free tier works fine

## 🔧 Setup Instructions

### Step 1: Get Bot Token
1. Message [@BotFather](https://t.me/BotFather) on Telegram
2. Use `/newbot` to create a new bot
3. Choose name: "Scammer Check Bot" (or similar)
4. Choose username: "your_scammer_check_bot"
5. Copy the bot token

### Step 2: Generate API Secret
```bash
# Generate a secure random key
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Step 3: Deploy to Render
1. Fork this repository to your GitHub
2. Create new Web Service on Render
3. Connect to your GitHub repo
4. Set environment variables
5. Deploy!

### Step 4: Configure Main Bot Sync
Add this to your main bot to sync data:

```python
# Add to your main bot
from sync_client import ReadOnlyBotSync, sync_all_data_to_readonly_bot

# Configuration
READONLY_BOT_API_URL = "https://your-readonly-bot.onrender.com"
READONLY_BOT_API_SECRET = "your_api_secret"

# Initialize sync client
readonly_bot_sync = ReadOnlyBotSync(READONLY_BOT_API_URL, READONLY_BOT_API_SECRET)

# After approving scammer
await readonly_bot_sync.sync_scammer(username, user_id, reports)

# After approving bad buyer
await readonly_bot_sync.sync_bad_buyer(username, user_id, reports)

# Periodic full sync (every hour)
async def periodic_sync():
    while True:
        await sync_all_data_to_readonly_bot(READONLY_BOT_API_URL, READONLY_BOT_API_SECRET)
        await asyncio.sleep(3600)
```

## 📁 File Structure

```
readonly_scammer_bot/
├── main.py              # Main bot application
├── api_server.py        # API server for data sync
├── sync_client.py       # Client for main bot integration
├── requirements.txt     # Python dependencies
├── render.yaml         # Render configuration
├── Procfile            # Process configuration
├── runtime.txt         # Python version
├── env_example.txt     # Environment variables example
└── README.md           # This file
```

## 🔄 Data Sync

### Automatic Sync
- Main bot pushes updates via API
- Periodic full sync every 5 minutes
- Real-time updates for new reports

### Manual Sync
```bash
# Bulk sync all data
curl -X POST https://your-readonly-bot.onrender.com/api/bulk_sync \
  -H "Authorization: Bearer your_api_secret" \
  -H "Content-Type: application/json" \
  -d '{
    "scammers": {...},
    "bad_buyers": {...},
    "username_mappings": {...}
  }'
```

## 🛡️ Security

- **API Authentication** - Bearer token required
- **Read-only access** - Cannot modify data via bot
- **Environment variables** - Sensitive data not in code
- **HTTPS only** - Secure communication

## 📱 Usage Examples

```
User: /patikra @suspicious_user
Bot: ✅ VARTOTOJAS ŠVARUS ✅
     👤 Vartotojas: suspicious_user
     🛡️ Nerasta jokių pranešimų

User: /scameris badguy123
Bot: 🚨 SCAMER PRANEŠIMAI 🚨
     👤 Vartotojas: badguy123
     📊 Pranešimų kiekis: 3
     📋 PRANEŠIMŲ SĄRAŠAS:
     1. 👤 seller1
        📅 2024-01-15 10:30
        📝 Nepateikė prekės

User: /stats
Bot: 📊 STATISTIKOS 📊
     🚨 SCAMERIAI:
        • Patvirtinti scameriai: 25
        • Viso pranešimų: 87
```

## 🔧 Troubleshooting

### Bot Not Responding
- Check BOT_TOKEN in environment variables
- Verify bot is running in Render logs
- Test with `/start` command

### Data Not Syncing
- Check API_SECRET matches between bots
- Verify MAIN_BOT_API_URL is correct
- Check API server logs

### Database Issues
- Database recreates automatically
- Check file permissions on Render
- Verify DATABASE_PATH setting

## 📞 Support

- Check Render service logs for errors
- Verify all environment variables are set
- Test API endpoints with curl
- Monitor database file size

## 🔄 Updates

To update the bot:
1. Push changes to GitHub
2. Render auto-deploys from main branch
3. Check deployment logs
4. Test functionality

## 💰 Costs

- **Render Free Tier**: Perfect for this bot
- **No database costs**: Uses SQLite
- **Minimal resources**: Very lightweight

The bot uses minimal resources and works perfectly on Render's free tier! 🚀
