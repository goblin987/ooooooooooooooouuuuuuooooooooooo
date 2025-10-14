# 🐛 DEBUG PLAN: Moderation System

**File:** `moderation_grouphelp.py`  
**Lines:** 956 total  
**Complexity:** HIGH (multiple APIs, database, permissions)  
**Priority:** 🔴 CRITICAL (Spam/abuse prevention)

---

## 1. SYSTEM OVERVIEW

### Components:
1. **User Resolution** - Find users by username/ID
2. **Ban System** - Ban/unban with history
3. **Pending Bans** - Ban users not yet in group
4. **Mute System** - Restrict permissions temporarily
5. **Warn System** - Progressive sanctions
6. **Info Command** - User lookup

### Critical Functions:
- `resolve_user()` - Converts username/ID to user_id
- `ban_user()` - Bans user, records history
- `pending_ban_handler()` - Auto-bans on join
- `warn_user()` - Issues warning with auto-sanction
- `info_user()` - Displays user info

---

## 2. TRACE POINTS

### User Resolution:
```python
logger.info(f"🔍 Resolving: '{username_or_id}', type={type(username_or_id)}")
logger.debug(f"   Attempting cache lookup...")

# If found
logger.info(f"✅ Resolved: {username} → ID {user_id}")

# If not found
logger.warning(f"❌ Not found: {username_or_id}")
logger.debug(f"   Cache size: {cache_count}, last update: {last_update}")
```

### Ban Operations:
```python
# Before ban
logger.info(f"🔨 BAN START: User {user_id} in chat {chat_id}")
logger.debug(f"   Reason: {reason}, Duration: {duration}")
logger.debug(f"   Admin: {admin_id}")

# Telegram API call
logger.debug(f"   Calling ban_chat_member...")

# After ban
logger.info(f"✅ BAN SUCCESS: User {user_id}")
logger.debug(f"   DB record created: {ban_id}")

# If error
logger.error(f"❌ BAN FAILED: {error}", exc_info=True)
```

### Pending Bans:
```python
# When user not in group
logger.info(f"⏳ PENDING BAN: User {user_id} not in group, adding to queue")

# When user joins
logger.info(f"🎯 PENDING BAN TRIGGER: User {user_id} joined, executing ban")

# After execution
logger.info(f"✅ PENDING BAN EXECUTED: {ban_id}")
```

### Warn System:
```python
# Warn issued
logger.info(f"⚠️ WARN: User {user_id}, count={warn_count}/{max_warns}")
logger.debug(f"   Reason: {reason}")

# Threshold reached
logger.warning(f"🚨 WARN THRESHOLD: User {user_id} at {warn_count} warnings")
logger.info(f"   Auto-action: {action}")

# Warn removed
logger.info(f"✅ WARN REMOVED: User {user_id}, remaining={new_count}")
```

---

## 3. COMMON BUGS & FIXES

### Bug 1: "User not found" for Users in Group
**Symptom:** `/ban @username` says user not found, but user is active  
**Root Cause:** User not in cache (hasn't sent message recently)  
**Fix:** Implement fallback to Telegram API `get_chat_member()`  
**Status:** ⚠️ PARTIAL (cache-dependent)

### Bug 2: Pending Bans Not Executing
**Symptom:** User added to pending, joins group, not banned  
**Root Cause:** `ChatMemberHandler` not registered or missing logic  
**Fix:** Verify handler registered, check `pending_ban_handler()` logs  
**Status:** ✅ SHOULD WORK (verify in production)

### Bug 3: Ban with Duration Not Unbanning
**Symptom:** `/ban @user 1d` bans permanently  
**Root Cause:** Telegram `until_date` not passed correctly  
**Fix:** Pass `until_date=datetime.now() + duration`  
**Status:** ⚠️ NEEDS VERIFICATION

### Bug 4: Mute Not Restricting
**Symptom:** Muted user can still send messages  
**Root Cause:** 
  - Bot not admin
  - Insufficient permissions
  - Permissions not set correctly
**Fix:** Check bot status, verify `can_send_messages=False`  
**Status:** ⚠️ NEEDS PERMISSION AUDIT

### Bug 5: Warn Auto-Ban Not Firing
**Symptom:** User reaches 3 warnings, no ban  
**Root Cause:** Auto-sanction logic not implemented  
**Fix:** Add sanction check in `warn_user()`  
**Status:** ⚠️ NEEDS IMPLEMENTATION

### Bug 6: Can't Ban by Username Only
**Symptom:** Pending ban requires reply or user in group  
**Root Cause:** Username resolution requires cache entry  
**Fix:** Accept username-only, add to pending with username  
**Status:** ⚠️ NEEDS FEATURE ADDITION

---

## 4. TEST SCENARIOS

### Scenario 1: Ban User in Group
```
Setup: User A is in group, sent messages (cached)

Steps:
1. Admin: /ban @UserA Test ban
2. Verify "Banned" confirmation
3. Verify User A can't send messages
4. Check ban_history table

Expected: User banned, record created

Trace: resolve_user → ban_chat_member → DB insert
```

### Scenario 2: Pending Ban (User Not in Group)
```
Setup: User B not in group

Steps:
1. Admin: /ban @UserB Preemptive ban
2. Verify "Added to pending bans"
3. User B joins group
4. Verify auto-ban triggers
5. Verify User B kicked immediately

Expected: User auto-banned on join

Trace: add_pending_ban → ChatMemberHandler → ban_chat_member
```

### Scenario 3: Temporary Ban (1 Day)
```
Steps:
1. Admin: /ban @UserC 1d Timeout
2. Verify "Banned for 1 day"
3. Wait 24 hours (or use time travel in test)
4. Verify User C can rejoin

Expected: Ban expires after 1 day

Trace: until_date calculation, Telegram unban
```

### Scenario 4: Warn Escalation
```
Setup: Max warnings = 3

Steps:
1. Admin: /warn @UserD Spam
2. Verify "1/3 warnings"
3. Admin: /warn @UserD Spam again
4. Verify "2/3 warnings"
5. Admin: /warn @UserD Third time
6. Verify "3/3 warnings - Auto-muted"

Expected: Third warning triggers auto-sanction

Trace: warn_count check → auto-sanction → mute_user
```

### Scenario 5: Unban
```
Setup: User E is banned

Steps:
1. Admin: /unban @UserE
2. Verify "Unbanned" confirmation
3. User E rejoins group
4. Verify User E can send messages
5. Check ban_history updated

Expected: Ban lifted, user can participate

Trace: unban_chat_member → DB update
```

### Scenario 6: Info Command
```
Steps:
1. Admin: /info @UserF
2. Verify info card shows:
   - User ID
   - Username
   - Name
   - Join date (if available)
   - Message count (if tracked)
   - Warnings
   - Ban history

Expected: Comprehensive user info displayed

Trace: Database queries, Telegram API calls
```

---

## 5. EDGE CASES

### Edge Case 1: Ban Bot Admin
```
Scenario: Admin tries /ban @OtherAdmin

Expected: Error "Can't ban other admins"

Test: Verify admin check before ban
```

### Edge Case 2: Self-Ban
```
Scenario: Admin tries /ban @self

Expected: Error "Can't ban yourself"

Test: Verify user_id != admin_id
```

### Edge Case 3: Ban Without Admin Rights
```
Scenario: Non-admin user tries /ban

Expected: "You need admin rights"

Test: Verify admin check at command entry
```

### Edge Case 4: Duplicate Pending Ban
```
Scenario: /ban @UserG twice before they join

Expected: Update existing pending ban, not duplicate

Test: Check pending_bans table for UNIQUE constraint
```

### Edge Case 5: Username Changed
```
Scenario: User H changes username from @oldname to @newname

Expected: Cache update on next message, ban still works by ID

Test: Verify cache refresh mechanism
```

### Edge Case 6: Private Profile
```
Scenario: User I has private profile, never sent message

Expected: Can't resolve by username, need reply or ID

Test: Verify error message guides admin
```

---

## 6. PERMISSION MATRIX

| Action | Bot Permission Required | Admin Permission Required |
|--------|------------------------|---------------------------|
| Ban user | `can_restrict_members` | `can_restrict_members` |
| Unban user | `can_restrict_members` | `can_restrict_members` |
| Mute user | `can_restrict_members` | `can_restrict_members` |
| Warn user | None (just message) | `can_restrict_members` |
| Delete message | `can_delete_messages` | `can_delete_messages` |
| Pin message | `can_pin_messages` | `can_pin_messages` |

### Permission Check Template:
```python
async def check_permissions(chat_id: int, user_id: int, permission: str) -> bool:
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return getattr(member, permission, False)
    except Exception as e:
        logger.error(f"Permission check failed: {e}")
        return False
```

---

## 7. DEBUGGING CHECKLIST

When moderation fails:

**User Resolution:**
- [ ] Is username formatted correctly? (@username)
- [ ] Is user in cache? (check last message time)
- [ ] Try by user_id instead of username
- [ ] Check database.get_user_by_username() logs

**Ban Issues:**
- [ ] Is bot admin in group?
- [ ] Does bot have `can_restrict_members`?
- [ ] Is target user an admin?
- [ ] Check Telegram API error response
- [ ] Verify ban_history table updated

**Pending Ban Issues:**
- [ ] Is ChatMemberHandler registered?
- [ ] Check pending_bans table for entry
- [ ] Verify handler logs when user joins
- [ ] Check for race condition (ban before handler)

**Warn Issues:**
- [ ] Verify warnings table exists
- [ ] Check warn_count accuracy
- [ ] Verify auto-sanction threshold
- [ ] Check if sanctions execute

---

## 8. MONITORING QUERIES

```sql
-- Recent bans
SELECT user_id, username, reason, banned_at, banned_by, duration
FROM ban_history
WHERE banned_at > datetime('now', '-7 days')
ORDER BY banned_at DESC;

-- Pending bans (not executed)
SELECT user_id, username, reason, created_at
FROM pending_bans
WHERE executed = 0
ORDER BY created_at DESC;

-- Users with warnings
SELECT user_id, username, COUNT(*) as warn_count
FROM warnings
WHERE reset_at IS NULL
GROUP BY user_id
HAVING warn_count >= 2
ORDER BY warn_count DESC;

-- Ban effectiveness (did they return?)
SELECT bh.user_id, bh.username, bh.banned_at, ub.unbanned_at,
       CASE WHEN EXISTS (
           SELECT 1 FROM messages m 
           WHERE m.user_id = bh.user_id 
           AND m.sent_at > ub.unbanned_at
       ) THEN 'Returned' ELSE 'Stayed away' END as status
FROM ban_history bh
LEFT JOIN unban_history ub ON bh.user_id = ub.user_id
WHERE ub.unbanned_at IS NOT NULL;
```

---

## 9. RECOMMENDED IMPROVEMENTS

### High Priority:
1. **Implement user resolution fallback** (Telegram API when cache misses)
2. **Add permission audit** before actions
3. **Create moderation log channel** (all actions logged)
4. **Implement warn auto-sanctions**

### Medium Priority:
1. **Add appeal system** (users can request unban)
2. **Create moderation dashboard** (stats, history)
3. **Implement soft-ban** (ban + delete history)
4. **Add ban reason categories** (spam, abuse, etc.)

### Low Priority:
1. **Auto-mod rules** (ban on keywords, excessive mentions)
2. **Captcha for new users**
3. **Slow mode enforcement**
4. **Raid mode** (lock group temporarily)

---

## 10. SECURITY CONSIDERATIONS

### Privilege Escalation:
- ⚠️ Ensure non-admins can't use commands
- ⚠️ Verify bot can't be tricked into banning admins
- ⚠️ Protect against mass ban exploits

### Data Privacy:
- ⚠️ Ban reasons should be visible only to admins
- ⚠️ User cache should expire (GDPR)
- ⚠️ Provide data export for banned users

### Audit Trail:
- ✅ All bans logged with admin ID
- ✅ Timestamp for all actions
- ⚠️ Add IP logging for appeals (if possible)

---

**Status:** ✅ DEBUG PLAN COMPLETE  
**Last Updated:** 2025-10-14  
**Next Action:** Implement missing features (auto-sanctions, permission checks)

