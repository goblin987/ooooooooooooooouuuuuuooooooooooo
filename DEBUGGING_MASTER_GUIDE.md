# 🔧 MASTER DEBUGGING GUIDE
**OGbotas Telegram Bot - Complete Debugging Reference**

---

## 📚 TABLE OF CONTENTS

1. [Quick Reference](#quick-reference)
2. [Debug Plans by Module](#debug-plans-by-module)
3. [Common Issues & Solutions](#common-issues--solutions)
4. [Logging Best Practices](#logging-best-practices)
5. [Testing Checklist](#testing-checklist)
6. [Emergency Procedures](#emergency-procedures)
7. [Performance Monitoring](#performance-monitoring)

---

## 🚀 QUICK REFERENCE

### Most Common Bugs (Ranked by Frequency):

| Rank | Issue | Module | Fix Time | Reference |
|------|-------|--------|----------|-----------|
| 1 | "User not found" | Moderation | 5 min | [Debug Plan](DEBUG_PLAN_moderation.md#bug-1) |
| 2 | Balance not credited | Payments | 10 min | [Debug Plan](DEBUG_PLAN_webhook_balance_crediting.md#issue-1) |
| 3 | Game button not working | Games | 15 min | [Debug Plan](DEBUG_PLAN_handle_game_buttons.md#issue-1) |
| 4 | Recurring message not sending | Recurring | 20 min | [Debug Plan](DEBUG_PLAN_recurring_messages.md#bug-7) |
| 5 | Media lost in message | Recurring | 10 min | [Debug Plan](DEBUG_PLAN_recurring_messages.md#bug-2) |

### Emergency Commands:

```bash
# Check if bot is running
curl https://grpbot9999.onrender.com/

# View recent logs (Render dashboard)
# Navigate to: Logs → Filter by "ERROR"

# Check database integrity
sqlite3 bot_data.db "PRAGMA integrity_check;"

# Clear stuck games (in bot)
/cleargames

# Restart bot (Render)
# Dashboard → Manual Deploy → Clear build cache → Deploy
```

---

## 📖 DEBUG PLANS BY MODULE

### 1. Games System
**File:** `games.py` (925 lines)  
**Debug Plan:** [DEBUG_PLAN_handle_game_buttons.md](DEBUG_PLAN_handle_game_buttons.md)

**Key Functions:**
- `handle_game_buttons()` - All button interactions
- `evaluate_round()` - Scoring logic
- `handle_game_challenge()` - Challenge flow

**Common Issues:**
- ✅ Message ID validation
- ✅ Turn validation
- ⚠️ Game timeout (not implemented)
- ⚠️ Balance sync

**Quick Debug:**
```python
# Add at top of handle_game_buttons()
logger.info(f"🎮 BUTTON: data={query.data}, user={user_id}")
logger.debug(f"game_key={game_key}, game={game}")
```

### 2. Payments System
**File:** `payments_webhook.py` (135 lines)  
**Debug Plan:** [DEBUG_PLAN_webhook_balance_crediting.md](DEBUG_PLAN_webhook_balance_crediting.md)

**Key Functions:**
- `handle_nowpayments_webhook()` - Process webhooks
- `create_deposit_payment()` - Generate payment address
- `handle_withdrawal_text()` - Process withdrawals

**Common Issues:**
- ✅ Amount field priority (fixed)
- ⚠️ Idempotency check (missing)
- ⚠️ Float precision
- ⚠️ Notification retry

**Quick Debug:**
```python
# In webhook handler
logger.info(f"📥 Webhook: {data}")
logger.info(f"💰 Amounts: price={price_amount} pay={pay_amount} outcome={outcome_amount}")
```

### 3. Recurring Messages
**File:** `recurring_messages_grouphelp.py` (2,174 lines)  
**Debug Plan:** [DEBUG_PLAN_recurring_messages.md](DEBUG_PLAN_recurring_messages.md)

**Key Functions:**
- `handle_callback()` - Button routing
- `handle_text_input()` - Input processing
- `save_and_schedule_message()` - Job creation
- `send_recurring_message()` - Message sender

**Common Issues:**
- ✅ UI not updating
- ✅ Media storage
- ⚠️ Custom interval buttons
- ⚠️ Scheduler not firing
- ⚠️ Media URL buttons

**Quick Debug:**
```python
# In send_recurring_message()
logger.info(f"📤 Sending: msg_id={msg_id}, group={group_id}")
logger.debug(f"config={msg_config}")
logger.info(f"Result: {sent_successfully}")
```

### 4. Moderation System
**File:** `moderation_grouphelp.py` (956 lines)  
**Debug Plan:** [DEBUG_PLAN_moderation.md](DEBUG_PLAN_moderation.md)

**Key Functions:**
- `resolve_user()` - User lookup
- `ban_user()` - Ban execution
- `pending_ban_handler()` - Auto-ban on join
- `warn_user()` - Warning system

**Common Issues:**
- ⚠️ Cache-only user resolution
- ⚠️ Pending bans not executing
- ⚠️ Permission checks
- ⚠️ Warn auto-sanctions

**Quick Debug:**
```python
# In resolve_user()
logger.info(f"🔍 Resolving: {username_or_id}")
result = database.get_user_by_username(username)
logger.info(f"Result: {result}")
```

---

## 🔍 COMMON ISSUES & SOLUTIONS

### Issue Category: User Resolution

#### Problem: "User not found" error
**Symptoms:**
- `/ban @username` fails
- `/dice @username` can't find opponent
- User clearly visible in chat

**Diagnosis:**
```python
# Check cache
cursor.execute("SELECT * FROM user_cache WHERE username = ?", (username,))
print(cursor.fetchone())
```

**Solutions:**
1. User hasn't sent message → Ask user to send message
2. Private profile → Use user_id or reply method
3. Cache stale → Implement fallback to `get_chat_member()`

**Prevention:**
- Cache messages from all group members
- Implement periodic cache refresh
- Add fallback resolution methods

---

### Issue Category: Balance Discrepancies

#### Problem: Deposit not credited or wrong amount
**Symptoms:**
- User deposits $12, gets $0.12
- Payment shows "finished" but balance unchanged
- Notification not sent

**Diagnosis:**
```sql
-- Check webhook logs
SELECT * FROM logs WHERE message LIKE '%Webhook%' ORDER BY timestamp DESC LIMIT 10;

-- Check balance history
SELECT * FROM users WHERE user_id = 12345;
```

**Solutions:**
1. Wrong amount field → Use `price_amount` not `pay_amount`
2. Database error → Check SQLite logs
3. Notification failed → Retry manually

**Prevention:**
- Add payment_history table
- Implement idempotency check
- Use Decimal for all currency

---

### Issue Category: Stuck Games

#### Problem: Game doesn't complete, buttons don't work
**Symptoms:**
- Click "Roll Dice", nothing happens
- Game in user_games but no progression
- Turn never switches

**Diagnosis:**
```python
# In bot chat
/cleargames  # User command

# Or check bot_data
print(context.bot_data['games'])
print(context.bot_data['user_games'])
```

**Solutions:**
1. Message ID mismatch → Update `message_id` after new message
2. Turn validation failing → Check `current_player` vs `player_key`
3. Balance insufficient → Check balance before allowing roll

**Prevention:**
- Implement 10-minute timeout
- Add game state persistence (database)
- Better error messages to user

---

### Issue Category: Scheduler Not Firing

#### Problem: Recurring message configured but not sending
**Symptoms:**
- Message saved in database
- Job appears in scheduler
- Time passes, no message sent

**Diagnosis:**
```python
# Check scheduler status
print(f"Scheduler running: {scheduler.running}")

# List jobs
for job in scheduler.get_jobs():
    print(f"Job: {job.id}, Next run: {job.next_run_time}")

# Check triggers
job = scheduler.get_job(job_id)
print(f"Trigger: {job.trigger}")
```

**Solutions:**
1. Scheduler not started → Call `scheduler.start()`
2. `start_date` in past → Remove `start_date` from trigger
3. Job ID collision → Use unique IDs (timestamp)
4. Interval wrong → Verify hours vs minutes

**Prevention:**
- Verify scheduler.running on bot start
- Use IntervalTrigger correctly
- Add "test send" button

---

## 📝 LOGGING BEST PRACTICES

### Log Levels Guide:

```python
# DEBUG - Detailed diagnostic info (dev only)
logger.debug(f"Variable state: x={x}, y={y}")

# INFO - Confirm things working as expected
logger.info(f"✅ User {user_id} completed action")

# WARNING - Something unexpected but recoverable
logger.warning(f"⚠️ Cache miss for user {user_id}, using fallback")

# ERROR - Something failed but bot continues
logger.error(f"❌ Failed to send message: {e}", exc_info=True)

# CRITICAL - Bot can't continue (rare)
logger.critical(f"🚨 Database connection lost!")
```

### Structured Logging Template:

```python
# Entry point
logger.info(f"🎯 FUNCTION_NAME: param1={p1}, param2={p2}")

# Key decision points
logger.debug(f"   Condition check: {condition} = {result}")

# Database operations
logger.info(f"💾 DB OPERATION: {operation}, affected={rows}")

# API calls
logger.info(f"📡 API CALL: {endpoint}, status={status}")

# Exit point (success)
logger.info(f"✅ FUNCTION_NAME: Success, result={result}")

# Exit point (error)
logger.error(f"❌ FUNCTION_NAME: Failed - {error}", exc_info=True)
```

### Emoji Guide for Logs:

```
🎯 Entry point
🔍 Searching/querying
✅ Success
❌ Error/failure
⚠️ Warning
💾 Database operation
📡 API call
🎮 Game event
💰 Payment event
📤 Outgoing message
📥 Incoming webhook
🔨 Moderation action
⏰ Scheduler event
🚨 Critical alert
```

---

## ✅ TESTING CHECKLIST

### Before Each Deploy:

#### 1. Core Commands
- [ ] `/start` - Shows correct menu
- [ ] `/help` - Lists all commands
- [ ] `/balance` - Shows balance (if logged in)

#### 2. Games
- [ ] `/dice 1` - Setup, challenge, roll, winner
- [ ] `/basketball 2` - Different game type works
- [ ] `/dice2` - Points game works
- [ ] `/cleargames` - Clears stuck games

#### 3. Moderation
- [ ] `/ban @user` - Bans successfully
- [ ] `/ban @notingroup` - Adds to pending
- [ ] `/unban @user` - Unbans successfully
- [ ] `/warn @user` - Issues warning
- [ ] `/info @user` - Shows user info

#### 4. Payments
- [ ] `/pinigine` - Shows balance
- [ ] Click "Įnešti" → Generates invoice
- [ ] Send test payment → Balance credited
- [ ] Click "Išimti" → Withdrawal flow works

#### 5. Recurring Messages
- [ ] `/recurring` in group → Registers
- [ ] `/recurring` in private → Shows menu
- [ ] Add text → ✅ appears
- [ ] Set time → ✅ appears
- [ ] Set interval → Shows correctly
- [ ] Click "Save" → Job created
- [ ] Wait for interval → Message sent

#### 6. Admin Panel
- [ ] `/admin` → Opens panel
- [ ] Points management works
- [ ] Seller list updates
- [ ] Statistics load

---

## 🚨 EMERGENCY PROCEDURES

### Scenario 1: Bot Crashed / Won't Start

**Symptoms:** Render shows "Exited with status 1"

**Steps:**
1. Check Render logs for error message
2. Identify error type:
   - `ImportError` → Missing dependency
   - `NameError` → Typo in code
   - `DatabaseError` → Corrupted database
3. Fix and redeploy
4. If urgent: Rollback to previous deploy

**Commands:**
```bash
# Rollback (Render dashboard)
# Navigate to: Deploys → Find last working → Redeploy

# Check syntax locally
python -m py_compile OGbotas.py
```

### Scenario 2: Mass Balance Discrepancy

**Symptoms:** Multiple users report wrong balance

**Steps:**
1. **DO NOT PANIC** - Balance is in database
2. Check webhook logs for anomalies
3. Query balance history:
```sql
SELECT user_id, balance, last_updated 
FROM users 
WHERE last_updated > datetime('now', '-1 hour')
ORDER BY last_updated DESC;
```
4. If needed, manual correction:
```sql
UPDATE users SET balance = <correct_amount> WHERE user_id = <id>;
```
5. Document in incident log

### Scenario 3: Scheduler Stopped

**Symptoms:** No recurring messages sent for >1 hour

**Steps:**
1. Check if bot restarted (jobs lost)
2. Restart bot to reload jobs
3. Verify jobs recreated:
```python
# In Python console (if accessible)
scheduler.get_jobs()
```
4. If jobs missing, manual reload:
```python
# Call resume_all_messages() on startup
```

### Scenario 4: Database Corruption

**Symptoms:** SQLite errors, queries failing

**Steps:**
1. **BACKUP IMMEDIATELY**:
```bash
cp bot_data.db bot_data_backup_$(date +%s).db
```
2. Check integrity:
```bash
sqlite3 bot_data.db "PRAGMA integrity_check;"
```
3. If corrupted, restore from backup
4. Prevent: Add regular backups to cron

---

## 📊 PERFORMANCE MONITORING

### Key Metrics to Track:

| Metric | Target | Alert Threshold | Check Frequency |
|--------|--------|-----------------|-----------------|
| Response time | < 2s | > 5s | Real-time |
| Error rate | < 1% | > 5% | Hourly |
| Active games | varies | > 100 | Hourly |
| Database size | < 100MB | > 500MB | Daily |
| Webhook success | > 99% | < 95% | Real-time |
| Scheduler uptime | 100% | < 99% | Real-time |

### Health Check Endpoints:

```python
# Add to OGbotas.py
@app.route('/health')
def health_check():
    return jsonify({
        'status': 'healthy',
        'uptime': time.time() - start_time,
        'scheduler_running': scheduler.running,
        'active_games': len(context.bot_data.get('games', {})),
        'db_size': os.path.getsize('bot_data.db')
    })
```

### Monitoring Queries:

```sql
-- Games completed in last hour
SELECT COUNT(*) FROM game_history 
WHERE completed_at > datetime('now', '-1 hour');

-- Average game duration
SELECT AVG(JULIANDAY(completed_at) - JULIANDAY(started_at)) * 24 * 60 as avg_minutes
FROM game_history
WHERE completed_at > datetime('now', '-1 day');

-- Payments in last 24 hours
SELECT COUNT(*), SUM(amount) 
FROM payment_history
WHERE credited_at > datetime('now', '-1 day');

-- Active users (last 7 days)
SELECT COUNT(DISTINCT user_id) 
FROM user_cache
WHERE last_seen > datetime('now', '-7 days');
```

---

## 🔗 QUICK LINKS

- [Cleanup Plan](CLEANUP_PLAN.md)
- [Progress Tracker](PROGRESS_TRACKER.txt)
- [Payment Setup](PAYMENT_SETUP.md)
- [Render Dashboard](https://dashboard.render.com)
- [NOWPayments Dashboard](https://nowpayments.io/dashboard)
- [Telegram Bot API Docs](https://core.telegram.org/bots/api)

---

## 📞 SUPPORT ESCALATION

### Level 1: Common Issues (Self-service)
- Check this guide
- Review debug plans
- Search logs
- Test in staging

### Level 2: Module-Specific Issues
- Consult relevant DEBUG_PLAN_*.md
- Review function-level trace points
- Run test scenarios

### Level 3: Critical Issues
- Emergency procedures above
- Database backup and restore
- Manual balance corrections
- Rollback deploy

---

**Status:** ✅ MASTER GUIDE COMPLETE  
**Last Updated:** 2025-10-14  
**Version:** 1.0  
**Maintainer:** Development Team

