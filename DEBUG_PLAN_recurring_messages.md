# 🐛 DEBUG PLAN: Recurring Messages System

**File:** `recurring_messages_grouphelp.py`  
**Lines:** 2,174 total  
**Complexity:** VERY HIGH (scheduler, database, UI, media handling)  
**Priority:** 🔴 CRITICAL (User-facing feature)

---

## 1. SYSTEM OVERVIEW

### Components:
1. **Command Handlers** - `/recurring` command
2. **Callback Handlers** - Button interactions
3. **Text Input Handlers** - Message text, time, URL input
4. **Media Handlers** - Photo, video, GIF, document uploads
5. **Scheduler** - APScheduler with IntervalTrigger/CronTrigger
6. **Database** - scheduled_messages table
7. **Message Sender** - send_recurring_message()

### Critical Functions:
- `show_recurring_menu()` - Main menu
- `handle_callback()` - Routes all button clicks
- `handle_text_input()` - Processes text/media/time input
- `save_and_schedule_message()` - Creates scheduler job
- `send_recurring_message()` - Sends the actual message
- `edit_message()` - Loads existing message for editing

---

## 2. TRACE POINTS (High-Level)

### Entry Points:
```python
# /recurring command
logger.info(f"📢 RECURRING: User {user_id} in {'private' if private else 'group'} chat {chat_id}")

# Callback
logger.info(f"🔘 RECURRING CALLBACK: {data}, user={user_id}, chat={chat_id}")
logger.debug(f"   msg_config before: {context.user_data.get('recurring_message_config')}")

# Text input
logger.info(f"📝 RECURRING TEXT: '{text[:50]}...', user={user_id}, state={state}")
```

### State Transitions:
```python
# When setting state
logger.info(f"🔀 STATE CHANGE: {old_state} → {new_state}")
context.user_data['recurring_state'] = new_state

# When saving config
logger.debug(f"💾 CONFIG UPDATE: {key}={value}")
context.user_data['recurring_message_config'][key] = value
```

### Scheduler Operations:
```python
# Job creation
logger.info(f"⏰ SCHEDULING JOB: job_id={job_id}, interval={interval}")
logger.debug(f"   trigger={trigger}, next_run={job.next_run_time}")

# Job execution
logger.info(f"📤 SENDING RECURRING: msg_id={msg_id}, group_id={group_id}")
logger.debug(f"   config={msg_config}")

# Job completion
logger.info(f"✅ SENT: msg_id={msg_id}, success={success}")
```

### Database Operations:
```python
# Insert
logger.info(f"💾 DB INSERT: msg_id={msg_id}, group={group_id}, interval={interval}")

# Update
logger.info(f"💾 DB UPDATE: msg_id={msg_id}, fields={updated_fields}")

# Delete
logger.info(f"🗑️ DB DELETE: msg_id={msg_id}")
```

---

## 3. COMMON BUGS & FIXES

### Bug 1: UI Not Updating After Input
**Symptom:** User sends text, no confirmation, menu doesn't update  
**Root Cause:** Missing return to menu after text processing  
**Fix:** Call `show_recurring_menu_with_checks()` after every state update  
**Test:** Send text → verify menu shows with ✅  
**Status:** ✅ FIXED

### Bug 2: Media Lost After Save
**Symptom:** Message sends as text-only, media missing  
**Root Cause:** Storing `file.file_path` (URL) instead of `file_id` (permanent)  
**Fix:** Store `file_id` for direct uploads  
**Test:** Upload photo → save → verify photo appears  
**Status:** ✅ FIXED

### Bug 3: Time Input Breaks UI
**Symptom:** After typing "21:47", UI text garbled, buttons misaligned  
**Root Cause:** Invalid time parsing, error not caught  
**Fix:** Validate HH:MM format, show error for invalid input  
**Test:** Type "invalid" → verify error message  
**Status:** ⚠️ NEEDS VALIDATION

### Bug 4: Custom Interval Buttons Don't Work
**Symptom:** Click "Custom interval", nothing happens  
**Root Cause:** Handler expects text input but doesn't set state  
**Fix:** Set `recurring_state = 'custom_interval'` on button click  
**Test:** Click custom → type "3" → verify "Every 3 hours" saved  
**Status:** ⚠️ NEEDS IMPLEMENTATION

### Bug 5: No Way to Start/Edit Message
**Symptom:** Message configured but never sends  
**Root Cause:** No "Save" button, no scheduler job created  
**Fix:** Add "Save" button that calls `save_and_schedule_message()`  
**Test:** Configure message → click Save → verify job created  
**Status:** ✅ FIXED

### Bug 6: Group Selection Not Working
**Symptom:** After `/recurring` in private, "No groups found"  
**Root Cause:** User not fetched from DB, or groups table empty  
**Fix:** Register group when `/recurring` typed in group  
**Test:** Type `/recurring` in group → verify group registered  
**Status:** ⚠️ NEEDS VERIFICATION

### Bug 7: Scheduler Not Firing
**Symptom:** Message saved but never sent  
**Root Cause:** 
  - IntervalTrigger with `start_date` causing delay
  - Scheduler not started
  - Job ID collision
**Fix:** Remove `start_date`, verify scheduler running, unique job IDs  
**Test:** Set 1-minute interval → wait → verify message sent  
**Status:** ✅ FIXED (start_date removed)

### Bug 8: Media URL Buttons Don't Work
**Symptom:** Message has buttons, click does nothing  
**Root Cause:** Button data not parsed from JSON correctly  
**Fix:** Validate JSON before storage, parse correctly on send  
**Test:** Add button "Link|https://t.me" → send → verify button clickable  
**Status:** ⚠️ NEEDS TESTING

---

## 4. TEST SCENARIOS

### Scenario 1: Complete Happy Path
```
Steps:
1. Type /recurring in group chat
2. Verify "Group registered" message
3. Open bot private chat
4. Type /recurring
5. Click "Recurring messages"
6. Select the group
7. Enter message text
8. Verify menu shows ✅ next to Text
9. Click Time
10. Type "14:30"
11. Verify menu shows ✅ next to Time
12. Click Repetition
13. Select "Every 1 hour"
14. Verify menu shows interval
15. Click Save
16. Verify "Message scheduled" confirmation
17. Wait 1 hour (or modify for 1 minute)
18. Verify message appears in group

Expected: Message sent successfully at scheduled time

Trace: Full logs from registration to send
```

### Scenario 2: Media Message with Buttons
```
Steps:
1-6. Same as Scenario 1
7. Upload photo
8. Verify menu shows ✅ Photo
9. Enter text "Check this out"
10. Click "Media URL buttons"
11. Type "Visit|https://example.com"
12. Verify button preview
13. Set time & interval
14. Save
15. Wait for scheduled time
16. Verify message has photo, text, button

Expected: Photo with caption and working button

Trace: Media storage, JSON button parsing, send execution
```

### Scenario 3: Edit Existing Message
```
Steps:
1. Create recurring message (Scenario 1)
2. Type /recurring in private
3. Click "Recurring messages"
4. Click "Manage"
5. Select the message
6. Click "Edit"
7. Modify text
8. Click Save
9. Wait for next scheduled time
10. Verify updated text appears

Expected: Message updated, next send uses new text

Trace: Database update, scheduler job update
```

### Scenario 4: Pause & Resume
```
Steps:
1. Create recurring message
2. Click "Manage" → Select → "Pause"
3. Wait for scheduled time
4. Verify message NOT sent
5. Click "Resume"
6. Wait for next scheduled time
7. Verify message sent

Expected: Pause stops sends, resume restarts

Trace: Scheduler pause/resume, job state
```

### Scenario 5: Minute Intervals
```
Steps:
1-6. Same as Scenario 1
7. Enter text
8. Click Repetition
9. Select "Every 10 minutes"
10. Set time
11. Save
12. Wait 10 minutes
13. Verify message sent
14. Wait 10 more minutes
15. Verify second message sent

Expected: Messages sent every 10 minutes

Trace: IntervalTrigger with minutes parameter
```

---

## 5. EDGE CASES

### Edge Case 1: Bot Not Admin in Group
```
Scenario: User registers group but bot lacks send permissions

Expected: Error when trying to send, admin notified

Test: Remove bot's post permission → verify error handling
```

### Edge Case 2: Group Deleted/Bot Kicked
```
Scenario: Recurring message for non-existent group

Expected: Job disabled, admin notified, error logged

Test: Schedule message → leave group → verify job fails gracefully
```

### Edge Case 3: Very Long Text (> 4096 chars)
```
Scenario: User enters text exceeding Telegram limit

Expected: Split into multiple messages or show error

Test: Paste 5000 char text → verify handling
```

### Edge Case 4: Invalid Time Format
```
Inputs: "25:00", "12:60", "noon", "14:30:45"

Expected: Error message, request valid HH:MM

Test: Try each invalid format → verify rejection
```

### Edge Case 5: Concurrent Edits
```
Scenario: Admin A editing message while Admin B edits same message

Expected: Last edit wins, or conflict detection

Test: Two admins edit simultaneously → verify no corruption
```

### Edge Case 6: Media File Expired
```
Scenario: file_id expires after weeks/months

Expected: Fallback to error message, notify admin

Test: Simulate expired file_id → verify handling
```

---

## 6. DEBUGGING CHECKLIST

When recurring messages fail:

**Configuration Issues:**
- [ ] Is group registered in database?
- [ ] Is user an admin of the group?
- [ ] Is message fully configured (text, time, interval)?
- [ ] Are required fields (text OR media) present?

**Scheduler Issues:**
- [ ] Is scheduler running? (`scheduler.running`)
- [ ] Does job exist? (`scheduler.get_jobs()`)
- [ ] Is job_id correct format?
- [ ] Is next_run_time in the future?
- [ ] Check for job exceptions in logs

**Database Issues:**
- [ ] Does scheduled_messages table exist?
- [ ] Is message row inserted?
- [ ] Are JSON fields (buttons, media) valid?
- [ ] Check for SQLite errors

**Permission Issues:**
- [ ] Is bot still in group?
- [ ] Does bot have send message permission?
- [ ] Can bot send media type (photo/video/GIF)?
- [ ] Check for Telegram API errors

**Media Issues:**
- [ ] Is file_id stored (not file_path)?
- [ ] Is media type correctly detected?
- [ ] For URLs: Is URL valid and accessible?
- [ ] Check for download/upload errors

**Button Issues:**
- [ ] Is button data valid JSON?
- [ ] Are URLs properly encoded?
- [ ] Max 8 buttons per row, 100 total?
- [ ] Check for InlineKeyboard errors

---

## 7. MONITORING QUERIES

```sql
-- Active recurring messages
SELECT id, group_id, interval_hours, next_send_time, is_active
FROM scheduled_messages
WHERE is_active = 1
ORDER BY next_send_time;

-- Failed sends (if you add attempt tracking)
SELECT id, group_id, last_error, failed_attempts
FROM scheduled_messages
WHERE failed_attempts > 0
ORDER BY failed_attempts DESC;

-- Messages by group
SELECT g.group_name, COUNT(sm.id) as message_count
FROM groups g
LEFT JOIN scheduled_messages sm ON g.group_id = sm.group_id
WHERE sm.is_active = 1
GROUP BY g.group_id;

-- Next scheduled sends (in next hour)
SELECT id, group_id, text, next_send_time
FROM scheduled_messages
WHERE is_active = 1
AND next_send_time BETWEEN datetime('now') AND datetime('now', '+1 hour')
ORDER BY next_send_time;
```

---

## 8. RECOMMENDED IMPROVEMENTS

### High Priority:
1. **Add input validation** for all user inputs
2. **Implement error recovery** for failed sends
3. **Add send attempt tracking** (success/failure history)
4. **Create admin notification** for persistent failures

### Medium Priority:
1. **Add message preview** before saving
2. **Implement message templates** for common messages
3. **Add analytics** (sends per day, engagement if possible)
4. **Better error messages** (Lithuanian, user-friendly)

### Low Priority:
1. **Add A/B testing** for message variations
2. **Implement smart scheduling** (avoid night hours)
3. **Add message expiration** (auto-delete old messages)
4. **Create bulk operations** (pause all, delete all)

---

## 9. REFACTORING PLAN

### Current Structure (2,174 lines - TOO LARGE):
```
recurring_messages_grouphelp.py (everything in one file)
```

### Proposed Structure:
```
recurring_messages/
├── __init__.py (exports)
├── commands.py (100 lines)
│   └── recurring_command()
├── callbacks.py (300 lines)
│   ├── handle_callback()
│   └── route_*_callbacks()
├── text_input.py (200 lines)
│   ├── handle_text_input()
│   └── validate_*_input()
├── ui.py (400 lines)
│   ├── show_recurring_menu()
│   ├── show_*_screen()
│   └── build_*_keyboard()
├── scheduler.py (300 lines)
│   ├── save_and_schedule_message()
│   ├── send_recurring_message()
│   ├── pause_message()
│   └── resume_message()
├── database.py (200 lines)
│   ├── create_message()
│   ├── update_message()
│   ├── delete_message()
│   └── get_messages()
└── validators.py (100 lines)
    ├── validate_time()
    ├── validate_buttons()
    └── validate_media()
```

**Benefit:** Each file < 400 lines, clear separation of concerns

---

**Status:** ✅ DEBUG PLAN COMPLETE  
**Last Updated:** 2025-10-14  
**Complexity:** Very High - Refactoring highly recommended  
**Next Action:** Split into modules per refactoring plan

