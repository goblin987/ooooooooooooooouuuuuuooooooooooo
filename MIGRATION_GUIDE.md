# 🔄 Migration Guide - From Old Bot to New Bot

## ✅ What's Been Done

Your new bot is ready! It includes:
1. ✅ **ALL old features** from your running bot
2. ✅ **NEW features** we built (casino games, crypto payments, admin panel)
3. ✅ **Data preservation** - All 3 months of voting data will be kept

---

## 📦 Features Comparison

### Old Bot Features (PRESERVED):
- ✅ `/balsuoti` - Link to voting group
- ✅ `/barygos` - Seller leaderboards (weekly, monthly, all-time)
- ✅ Voting buttons in voting group
- ✅ 7-day voting cooldown
- ✅ Vote history tracking
- ✅ User points system
- ✅ Trusted sellers list

### NEW Features Added:
- ✅ **Casino Games** (Dice, Basketball, Football, Bowling) - PvP with crypto
- ✅ **Points Games** (Dice2) - PvP with saved points
- ✅ **Crypto Payments** - NOWPayments integration (deposit/withdraw)
- ✅ **Admin Panel** - Beautiful inline keyboard UI
- ✅ **Recurring Messages** - GroupHelpBot style
- ✅ **Masked Users** - Anonymous mode
- ✅ **Advanced Moderation** - Better ban/mute system
- ✅ **5% House Edge** - Covers withdrawal fees

---

## 🗂️ Data Files That Will Be Preserved

When you swap repos, Render will keep these files (in `/opt/render/data`):

**Voting Data** (3 months of history):
- `votes_weekly.pkl` - Weekly votes
- `votes_monthly.pkl` - Monthly votes  
- `votes_alltime.pkl` - All-time votes
- `vote_history.pkl` - Vote history
- `last_vote_attempt.pkl` - User cooldowns
- `voters.pkl` - List of voters

**User Data**:
- `user_points.pkl` - User points
- `trusted_sellers.pkl` - Seller list
- `confirmed_scammers.pkl` - Scammer list

**Database**:
- `bot_database.db` - SQLite database (users, balances, etc.)

**Media**:
- `featured_media_id.pkl` - Featured seller media
- `barygos_media_id.pkl` - Barygos command media
- `voting_message_id.pkl` - Pinned voting message

✅ **All this data will be preserved when you swap repos!**

---

## 🚀 Migration Steps

### Step 1: Update Environment Variables in Render

Go to your Render dashboard → Your service → Environment tab

**KEEP these existing variables:**
```
TELEGRAM_TOKEN=your_bot_token
ADMIN_CHAT_ID=your_telegram_id
VOTING_GROUP_CHAT_ID=your_voting_group_chat_id
VOTING_GROUP_LINK=https://t.me/your_voting_group
DATA_DIR=/opt/render/data
```

**ADD these new variables** (optional, for new features):
```
# For crypto games/payments:
NOWPAYMENTS_API_KEY=your_nowpayments_key (optional)
BOT_USERNAME=your_bot_username (optional)
OWNER_ID=your_telegram_id (optional)

# For webhook (if using):
WEBHOOK_URL=https://your-app.onrender.com (optional)
```

### Step 2: Change GitHub Repository in Render

1. Go to Render dashboard
2. Select your bot service
3. Go to **Settings** tab
4. Find **Repository** section
5. Click **"Disconnect"** or **"Change Repository"**
6. Connect to: `https://github.com/YOUR_USERNAME/ooooooooooooooouuuuuuooooooooooo`
7. Click **"Save"**

### Step 3: Wait for Deployment

Render will automatically:
1. Pull the new code
2. Install dependencies
3. Keep your data directory intact
4. Start the bot

Expected time: ~3-5 minutes

### Step 4: Verify Everything Works

Test these commands in your group:
```
/start
/help
/balsuoti  ← OLD FEATURE (should work!)
/barygos   ← OLD FEATURE (should show 3 months of data!)
/dice 10   ← NEW FEATURE (crypto game)
/dice2 100 ← NEW FEATURE (points game)
/balance   ← NEW FEATURE (crypto payments)
/admin     ← NEW FEATURE (admin panel)
```

---

## 🔍 What To Check After Migration

### ✅ Old Features Still Work:
- [ ] `/balsuoti` sends link to voting group
- [ ] Voting buttons work in voting group
- [ ] `/barygos` shows correct vote counts
- [ ] User points are preserved
- [ ] Trusted sellers list is intact
- [ ] Vote cooldowns still work (7 days)

### ✅ New Features Work:
- [ ] `/dice 10` starts crypto game
- [ ] `/dice2 100` starts points game
- [ ] `/balance` shows balance/deposit/withdraw
- [ ] `/admin` opens admin panel
- [ ] `/recurring` manages recurring messages
- [ ] All games work properly

---

## 📊 Voting Data Will Be Preserved

Your new bot uses **THE EXACT SAME** pickle files as the old bot:

| Old Bot File | New Bot File | Status |
|--------------|--------------|--------|
| `votes_weekly.pkl` | `votes_weekly.pkl` | ✅ Same |
| `votes_monthly.pkl` | `votes_monthly.pkl` | ✅ Same |
| `votes_alltime.pkl` | `votes_alltime.pkl` | ✅ Same |
| `vote_history.pkl` | `vote_history.pkl` | ✅ Same |
| `last_vote_attempt.pkl` | `last_vote_attempt.pkl` | ✅ Same |
| `user_points.pkl` | `user_points.pkl` | ✅ Same |
| `trusted_sellers.pkl` | `trusted_sellers.pkl` | ✅ Same |

**Result:** No data loss! All votes, points, and sellers preserved! 🎉

---

## 🆘 Troubleshooting

### Issue: Bot doesn't start
**Check Render logs:**
```
ValueError: BOT_TOKEN or TELEGRAM_TOKEN environment variable not set!
```
**Fix:** Make sure `TELEGRAM_TOKEN` is set in environment variables

### Issue: Voting doesn't work
**Check Render logs:**
```
WARNING: VOTING_GROUP_CHAT_ID not set
```
**Fix:** Add `VOTING_GROUP_CHAT_ID` and `VOTING_GROUP_LINK` environment variables

### Issue: No voting data showing
**Possible cause:** Data directory not persisted
**Fix:** Make sure `DATA_DIR=/opt/render/data` is set in Render

### Issue: Module not found errors
**Check:** Run `pip install -r requirements.txt`
**Fix:** All dependencies should auto-install on Render

---

## 🎯 Summary

### What You're Doing:
1. Swapping GitHub repo URL in Render
2. Adding a few new environment variables
3. Letting Render redeploy

### What Happens:
1. ✅ Old bot stops
2. ✅ New bot deploys
3. ✅ All data preserved (voting, points, sellers)
4. ✅ Old features still work
5. ✅ New features added

### What You Get:
- ✅ Everything from old bot
- ✅ Casino games with crypto
- ✅ Points games
- ✅ Crypto payments
- ✅ Better admin panel
- ✅ Better moderation
- ✅ More features!

---

## 📞 Need Help?

If anything goes wrong:
1. Check Render logs for errors
2. Verify all environment variables are set
3. Make sure data directory exists: `/opt/render/data`
4. Test with `/start` command first

---

**Ready to migrate? Just swap the GitHub repo URL in Render! 🚀**

All your voting data and sellers will be preserved!

