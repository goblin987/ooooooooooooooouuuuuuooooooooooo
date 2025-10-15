# 🧪 Testing Checklist - OGbotas Bot

**Status:** In Progress  
**Testing Environment:** Staging Render Server  
**Date Started:** {{ DATE }}  
**Tester:** {{ TESTER }}

---

## 🔧 Phase 1: Environment Validation

### 1.1 Configuration Check
- [ ] All environment variables set in Render dashboard
  - [ ] `BOT_TOKEN` - Telegram bot token
  - [ ] `OWNER_ID` - Your user ID
  - [ ] `ADMIN_CHAT_ID` - Admin chat ID
  - [ ] `NOWPAYMENTS_API_KEY` - NOWPayments API key
  - [ ] `NOWPAYMENTS_EMAIL` - NOWPayments email
  - [ ] `NOWPAYMENTS_PASSWORD` - NOWPayments password
  - [ ] `WEBHOOK_URL` - Your Render app URL
  - [ ] `PORT` - 8000 (default)
  - [ ] `DATA_DIR` - /opt/render/data
  - [ ] `BOT_USERNAME` - Your bot username
  - [ ] `VOTING_GROUP_CHAT_ID` - Voting group ID
  - [ ] `VOTING_GROUP_LINK` - Voting group invite link

### 1.2 Database Integrity
- [ ] Database created at `/opt/render/data/bot_database.db`
- [ ] All tables created:
  - [ ] `user_cache`
  - [ ] `ban_history`
  - [ ] `scheduled_messages`
  - [ ] `banned_words`
  - [ ] `helpers`
  - [ ] `scammer_reports`
  - [ ] `users`
  - [ ] `pending_bans`
  - [ ] `groups`
  - [ ] `warnings` (NEW - added during debugging)
- [ ] All indexes created successfully
- [ ] No corruption errors in logs

### 1.3 Bot Startup
- [ ] Bot starts without errors
- [ ] HTTP server listens on port 8000
- [ ] Health check endpoints respond:
  - [ ] `GET /` returns "✅ Bot is running!"
  - [ ] `GET /health` returns health status
- [ ] Telegram polling initialized
- [ ] Scheduler started successfully
- [ ] Recurring messages jobs loaded from database
- [ ] Logs show initialization complete

**Issues Found:**
```
1. ✅ FIXED: warn_system.py import error (database not imported correctly)
2. ✅ FIXED: Missing warnings table in database schema
```

---

## 📱 Phase 2: Core Commands

### 2.1 Basic Commands
- [ ] `/start` as admin - shows full command list
- [ ] `/start` as regular user - shows public commands only
- [ ] `/start pinigine` - redirects to balance command
- [ ] `/help` - lists all available commands
- [ ] `/admin` - opens admin panel (admin only)

### 2.2 User Caching
- [ ] Send message in group - user cached in `user_cache` table
- [ ] Check database: `SELECT * FROM user_cache WHERE user_id = YOUR_ID`
- [ ] Username resolution works: `/info @username`

**Test Results:**
- Start command (admin): ⬜ Pass / ⬜ Fail
- Start command (user): ⬜ Pass / ⬜ Fail
- Deep link: ⬜ Pass / ⬜ Fail
- Help command: ⬜ Pass / ⬜ Fail
- Admin panel: ⬜ Pass / ⬜ Fail
- User caching: ⬜ Pass / ⬜ Fail

**Issues Found:**
```
(Document any issues here)
```

---

## 🔨 Phase 3: Moderation System

### 3.1 User Resolution
- [ ] `/info @username` - User in cache (has sent messages)
- [ ] `/info @newuser` - User not in cache (check error message)
- [ ] `/lookup 123456789` - Lookup by user ID
- [ ] Reply to message + `/info` - User info from reply

### 3.2 Ban System
- [ ] `/ban @user Test ban` - Ban user currently in group
  - [ ] User banned successfully
  - [ ] Confirmation message sent
  - [ ] `ban_history` table updated
  - [ ] User cannot send messages
- [ ] `/ban @notingroup Preemptive` - User not in group
  - [ ] Added to `pending_bans` table
  - [ ] Confirmation message about pending ban

### 3.3 Pending Bans Execution
- [ ] User added to pending ban
- [ ] That user joins the group
- [ ] `ChatMemberHandler` triggers
- [ ] User auto-banned immediately
- [ ] Notification sent
- [ ] Removed from `pending_bans` table

### 3.4 Unban
- [ ] `/unban @user` - Unban previously banned user
- [ ] User can rejoin group
- [ ] `ban_history` updated with unban timestamp

### 3.5 Mute System
- [ ] `/mute @user 30` - Mute for 30 minutes
- [ ] User's permissions restricted
- [ ] User cannot send messages
- [ ] `/unmute @user` - Restore permissions
- [ ] User can send messages again

### 3.6 Warn System
- [ ] `/warn @user Spam` - Issue first warning
  - [ ] Warning recorded in `warnings` table
  - [ ] User notified (1/3 warnings)
- [ ] `/warn @user` again - Second warning (2/3)
- [ ] `/warn @user` third time - Third warning (3/3)
  - [ ] Auto-sanction triggered (mute/kick/ban)
- [ ] `/warnings @user` - View warning count
- [ ] `/unwarn @user` - Remove one warning
- [ ] `/resetwarns @user` - Clear all warnings

**Test Results:**
- User resolution: ⬜ Pass / ⬜ Fail
- Ban (in group): ⬜ Pass / ⬜ Fail
- Ban (pending): ⬜ Pass / ⬜ Fail
- Pending ban execution: ⬜ Pass / ⬜ Fail
- Unban: ⬜ Pass / ⬜ Fail
- Mute/Unmute: ⬜ Pass / ⬜ Fail
- Warn system: ⬜ Pass / ⬜ Fail
- Auto-sanction: ⬜ Pass / ⬜ Fail

**Issues Found:**
```
(Document any issues here)
```

---

## 🎲 Phase 4: Points & Games System

### 4.1 Points Balance
- [ ] `/points` - Check initial points (0 for new user)
- [ ] Award points (vote for seller or admin command)
- [ ] `/points` - Verify points updated

### 4.2 Dice2 Game (Points PvP)
- [ ] `/dice2` without args - Shows usage instructions
- [ ] `/dice2 10` - Start game with 10 points bet
  - [ ] Mode selection buttons appear
  - [ ] Select "Normal" mode
  - [ ] Points selection (or skip if bet already set)
  - [ ] Confirm setup
  - [ ] Challenge message sent

**Challenge via Username:**
- [ ] Type `@opponent` to challenge
- [ ] Challenge notification sent to opponent
- [ ] Opponent receives "Accept" button

**Challenge via Reply (PREFERRED METHOD):**
- [ ] Reply to opponent's message
- [ ] `/dice2 10` in the reply
- [ ] Challenge created instantly
- [ ] Opponent gets notification

**Gameplay:**
- [ ] Opponent clicks "Accept"
- [ ] Game board displayed
- [ ] Player 1 clicks "Roll Dice"
- [ ] Dice animation sent
- [ ] Player 2's turn
- [ ] Player 2 clicks "Roll Dice"
- [ ] Round evaluated
- [ ] Winner announced
- [ ] Points transferred

**Edge Cases:**
- [ ] Insufficient points - Error message
- [ ] Challenge user already in game - Error
- [ ] Cancel challenge - Works correctly
- [ ] Wrong turn click - "Not your turn" message
- [ ] Click old message button - Validation error

### 4.3 Crypto Casino Games

**Dice Game:**
- [ ] `/dice 1` - Start with $1 bet
- [ ] Select mode (Normal/Double/Crazy)
- [ ] Challenge opponent
- [ ] Play through game
- [ ] Balance updated correctly

**Basketball:**
- [ ] `/basketball 2` - $2 bet
- [ ] Complete game flow
- [ ] Scoring works correctly

**Football:**
- [ ] `/football 3` - $3 bet
- [ ] Complete game flow
- [ ] Scoring works correctly

**Bowling:**
- [ ] `/bowling 1` - $1 bet
- [ ] Complete game flow
- [ ] Scoring works correctly

**Multi-Round Games:**
- [ ] Play "First to 3 points" mode
- [ ] Scores persist across rounds
- [ ] Game ends at 3 points
- [ ] Correct winner determination

**Test Results:**
- Points command: ⬜ Pass / ⬜ Fail
- Dice2 (username challenge): ⬜ Pass / ⬜ Fail
- Dice2 (reply challenge): ⬜ Pass / ⬜ Fail
- Dice2 gameplay: ⬜ Pass / ⬜ Fail
- Crypto dice: ⬜ Pass / ⬜ Fail
- Basketball: ⬜ Pass / ⬜ Fail
- Football: ⬜ Pass / ⬜ Fail
- Bowling: ⬜ Pass / ⬜ Fail
- Edge cases: ⬜ Pass / ⬜ Fail

**Issues Found:**
```
(Document any issues here)
```

---

## 💰 Phase 5: Payment System

### 5.1 Balance Command
- [ ] `/balance` or `/pinigine` - Show wallet
- [ ] Balance displays correctly (USD format)
- [ ] "Įnešti" (Deposit) button works
- [ ] "Išimti" (Withdraw) button works

### 5.2 Deposits (⚠️ REAL CRYPTO!)
- [ ] Click "Įnešti" button
- [ ] Amount selection menu appears
- [ ] Select $5 (or custom amount)
- [ ] Currency selection menu
- [ ] Select cryptocurrency (LTC recommended for testing)
- [ ] NOWPayments invoice created
- [ ] QR code displayed
- [ ] Payment address shown
- [ ] Amount in crypto calculated correctly

**Payment Processing:**
- [ ] Send SMALL test payment ($1-2) ⚠️
- [ ] Payment detected by NOWPayments
- [ ] Webhook received at `/webhook/nowpayments`
- [ ] Webhook logs show payment data
- [ ] Balance credited with CORRECT amount
  - [ ] Check: Uses `price_amount` not `pay_amount`
  - [ ] USD amount matches what user paid
- [ ] Notification sent to user
- [ ] Check database: `SELECT balance FROM users WHERE user_id = YOUR_ID`

### 5.3 Withdrawals
- [ ] Click "Išimti" button
- [ ] Enter withdrawal amount
- [ ] Enter crypto address (valid format)
- [ ] Withdrawal request created
- [ ] Admin notification sent
- [ ] (Manual processing by admin)

### 5.4 Admin Balance Management
- [ ] `/addbalance @user 10` - Add $10 to user balance
  - [ ] Balance updated correctly
  - [ ] User notified
- [ ] `/removebalance @user 5` - Remove $5
  - [ ] Balance decreased
  - [ ] User notified
- [ ] `/setbalance @user 100` - Set exact balance
  - [ ] Balance set to $100
  - [ ] User notified

**Test Results:**
- Balance display: ⬜ Pass / ⬜ Fail
- Deposit creation: ⬜ Pass / ⬜ Fail
- Payment processing: ⬜ Pass / ⬜ Fail
- Correct amount credited: ⬜ Pass / ⬜ Fail
- Notification sent: ⬜ Pass / ⬜ Fail
- Withdrawal request: ⬜ Pass / ⬜ Fail
- Admin balance commands: ⬜ Pass / ⬜ Fail

**Payment Test Record:**
```
Date: _______
Amount Sent: $_______
Crypto: _______
Amount Credited: $_______
Match: ⬜ Yes / ⬜ No
Issues: _______
```

**Issues Found:**
```
(Document any issues here)
```

---

## 🔄 Phase 6: Recurring Messages

### 6.1 Group Registration
- [ ] In test group: `/recurring`
- [ ] Message: "grupės skelbimai aktyvuoti"
- [ ] Check database: `SELECT * FROM groups WHERE chat_id = GROUP_ID`

### 6.2 Message Creation (Private Chat)
- [ ] In private chat with bot: `/recurring`
- [ ] Group selection menu appears
- [ ] Select your test group
- [ ] Message management interface shown
- [ ] Click "pridėti" (add message)

**Setting up Message:**
- [ ] Click "Set Text"
- [ ] Send test message: "Test recurring message"
- [ ] Checkmark ✅ appears next to "Text"
- [ ] Click "Set Time"
  - [ ] Hour selection menu
  - [ ] Select hour
  - [ ] Minute selection menu
  - [ ] Select minute
  - [ ] Checkmark ✅ appears next to "Time"
- [ ] Click "Set Interval"
  - [ ] Interval options displayed
  - [ ] Select "1 hour" (for testing)
  - [ ] Checkmark ✅ appears next to "Interval"
- [ ] Click "Save & Schedule"
- [ ] Confirmation message
- [ ] Check database: `SELECT * FROM scheduled_messages WHERE chat_id = GROUP_ID`

### 6.3 Message Sending
- [ ] Wait for scheduled time (or use test send button if available)
- [ ] Message appears in group
- [ ] Content matches configured text
- [ ] Check `last_sent` timestamp updated in database
- [ ] Wait for interval period
- [ ] Message sent again (verify interval repeat)

### 6.4 Advanced Features

**Media Messages:**
- [ ] Create new message
- [ ] Set text
- [ ] Click "Add Media"
- [ ] Send photo/video
- [ ] Media file ID stored
- [ ] Test send - media displays correctly

**URL Buttons:**
- [ ] Click "Add URL Buttons"
- [ ] Follow format: `Text - https://example.com`
- [ ] Multiple buttons (one per line)
- [ ] Save message
- [ ] Test send - buttons appear and work

**Message Options:**
- [ ] Toggle "Pin message" - message pinned when sent
- [ ] Toggle "Delete previous" - old message deleted
- [ ] Set custom interval (e.g., "2.5 hours")
- [ ] Pause message - stops sending
- [ ] Resume message - starts sending again

**Test Results:**
- Group registration: ⬜ Pass / ⬜ Fail
- Message creation: ⬜ Pass / ⬜ Fail
- Text setting: ⬜ Pass / ⬜ Fail
- Time setting: ⬜ Pass / ⬜ Fail
- Interval setting: ⬜ Pass / ⬜ Fail
- Message sending: ⬜ Pass / ⬜ Fail
- Interval repeat: ⬜ Pass / ⬜ Fail
- Media messages: ⬜ Pass / ⬜ Fail
- URL buttons: ⬜ Pass / ⬜ Fail
- Advanced options: ⬜ Pass / ⬜ Fail

**Issues Found:**
```
(Document any issues here)
```

---

## 🗳️ Phase 7: Voting & Sellers

### 7.1 Voting Commands
- [ ] `/balsuoti` - Link to voting group displayed
- [ ] Link works (joins voting group)
- [ ] In voting group: seller voting buttons appear
- [ ] Vote for a seller
- [ ] Points awarded (check `/points`)
- [ ] Cooldown active - can't vote again immediately

### 7.2 Seller Leaderboards
- [ ] `/barygos` - Leaderboard displayed
- [ ] Top sellers shown
- [ ] Vote counts accurate
- [ ] Banner image displays (if available)

### 7.3 Admin Voting Management
- [ ] `/updatevoting` - Voting buttons updated
- [ ] New sellers appear in voting interface
- [ ] `/resetvotes` - Cooldowns cleared (admin only)

**Test Results:**
- Balsuoti command: ⬜ Pass / ⬜ Fail
- Voting works: ⬜ Pass / ⬜ Fail
- Points awarded: ⬜ Pass / ⬜ Fail
- Cooldown: ⬜ Pass / ⬜ Fail
- Leaderboard: ⬜ Pass / ⬜ Fail
- Admin commands: ⬜ Pass / ⬜ Fail

**Issues Found:**
```
(Document any issues here)
```

---

## 🎛️ Phase 8: Admin Panel

### 8.1 Panel Navigation
- [ ] `/admin` - Panel opens
- [ ] All buttons present:
  - [ ] 💰 Points Management
  - [ ] ⭐ Sellers Management
  - [ ] 🚨 Scammers Management
  - [ ] 📋 Claims Review
  - [ ] 🔍 User Lookup
  - [ ] 📊 Statistics
  - [ ] 🔄 Recurring Messages
  - [ ] 👤 Masked Users

### 8.2 Data Management

**Points Management:**
- [ ] Click 💰 Points
- [ ] Add points to user
- [ ] Remove points from user
- [ ] View leaderboard

**Sellers Management:**
- [ ] Click ⭐ Sellers
- [ ] Add trusted seller
- [ ] Remove seller
- [ ] View all sellers

**Scammers Management:**
- [ ] Click 🚨 Scammers
- [ ] Add confirmed scammer
- [ ] Remove from list
- [ ] View all scammers

**Test Results:**
- Admin panel opens: ⬜ Pass / ⬜ Fail
- Navigation works: ⬜ Pass / ⬜ Fail
- Points management: ⬜ Pass / ⬜ Fail
- Sellers management: ⬜ Pass / ⬜ Fail
- Scammers management: ⬜ Pass / ⬜ Fail

**Issues Found:**
```
(Document any issues here)
```

---

## ⚠️ Phase 9: Error Handling & Edge Cases

### 9.1 Permission Errors
- [ ] Temporarily demote bot from admin
- [ ] Try `/ban @user` - Error message about permissions
- [ ] Try `/mute @user` - Error message
- [ ] Restore bot admin rights
- [ ] Commands work again

### 9.2 Invalid Inputs
- [ ] `/dice abc` - Error about invalid amount
- [ ] `/dice -10` - Error about negative amount
- [ ] `/dice2 @nonexistentuser123456` - User not found error
- [ ] Send malformed crypto address for withdrawal - Validation error

### 9.3 Race Conditions
- [ ] Two users challenge same person simultaneously
  - [ ] Second challenge rejected (already in game)
- [ ] Rapid button clicking
  - [ ] No duplicate actions
  - [ ] "Please wait" or similar message
- [ ] (If possible) Send duplicate webhook
  - [ ] Idempotency check prevents double-crediting

### 9.4 Database Failures
- [ ] Check logs for any database errors
- [ ] Verify retry logic on connection timeout
- [ ] No data loss reported

**Test Results:**
- Permission errors: ⬜ Pass / ⬜ Fail
- Invalid inputs: ⬜ Pass / ⬜ Fail
- Race conditions: ⬜ Pass / ⬜ Fail
- Database resilience: ⬜ Pass / ⬜ Fail

**Issues Found:**
```
(Document any issues here)
```

---

## 🐛 Phase 10: Bug Tracking

### Bugs Found During Testing

| # | Severity | Module | Description | Status | Fix |
|---|----------|--------|-------------|--------|-----|
| 1 | Critical | warn_system | Import error: `import database` → `from database import database` | ✅ Fixed | Changed import |
| 2 | Critical | database | Missing `warnings` table in schema | ✅ Fixed | Added table + indexes |
| 3 |  |  |  |  |  |
| 4 |  |  |  |  |  |
| 5 |  |  |  |  |  |

### Bug Severity Levels:
- **Critical:** Bot crashes, data loss, security issue
- **High:** Core feature broken (games, payments, moderation)
- **Medium:** Minor feature issue, UI problem
- **Low:** Cosmetic, enhancement

---

## 📊 Phase 11: Performance & Monitoring

### 11.1 Health Checks
- [ ] `curl https://your-staging-bot.onrender.com/` - Returns "✅ Bot is running!"
- [ ] `curl https://your-staging-bot.onrender.com/health` - Returns health status
- [ ] Webhook endpoint accessible: `/webhook/nowpayments`

### 11.2 Log Analysis
- [ ] No ERROR level logs (or all are handled)
- [ ] WARNING logs are reasonable
- [ ] INFO logs comprehensive
- [ ] DEBUG logs helpful (if enabled)
- [ ] No memory leak indicators

### 11.3 Database Queries
- [ ] Database size reasonable (< 100MB initially)
- [ ] Queries execute quickly (< 1s)
- [ ] Indexes being used (check EXPLAIN QUERY PLAN)
- [ ] Clean up test data before production

**Performance Metrics:**
```
Bot Response Time: _______ ms
Database Size: _______ MB
Active Games: _______
Scheduled Messages: _______
```

---

## ✅ Phase 12: Production Readiness

### 12.1 Pre-Deploy Validation
- [ ] All critical bugs fixed
- [ ] All high-priority bugs fixed
- [ ] Medium bugs documented (acceptable for v1.0)
- [ ] Commands work as expected
- [ ] Payment system tested with real crypto
- [ ] Recurring messages sending reliably
- [ ] Moderation system functional
- [ ] Games complete without errors
- [ ] Error handling graceful
- [ ] Logs clean and informative

### 12.2 Configuration Review
- [ ] Environment variables reviewed and secure
- [ ] No sensitive data in logs
- [ ] Database backed up
- [ ] Webhook URLs verified
- [ ] Rate limits configured
- [ ] Admin IDs correct
- [ ] All API keys valid

### 12.3 Documentation
- [ ] README updated with:
  - [ ] Deployment steps
  - [ ] Environment variables list
  - [ ] Known limitations
  - [ ] Troubleshooting guide
  - [ ] Bot permissions requirements

### 12.4 Deployment Checklist
- [ ] Final comprehensive test on staging
- [ ] Backup production database (if replacing existing bot)
- [ ] Note production environment variables
- [ ] Deploy to production Render instance
- [ ] Monitor logs for first hour
- [ ] Test critical features in production:
  - [ ] `/start` works
  - [ ] `/balance` works
  - [ ] Test small payment ($1)
  - [ ] Start one game
  - [ ] Send one recurring message
- [ ] Create announcement for users (if needed)

---

## 📝 Testing Notes

### General Observations:
```
(Write overall impressions, patterns noticed, etc.)
```

### Recommendations for Production:
```
(Suggestions for improvements, monitoring, etc.)
```

### Known Limitations:
```
(Document any features that don't work as expected but are acceptable)
```

---

**Testing Complete:** ⬜ Yes / ⬜ No  
**Ready for Production:** ⬜ Yes / ⬜ No  
**Approval:** ___________  
**Date:** ___________


