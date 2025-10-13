# Recurring Messages - Acceptance Tests

## Test Environment Setup
- Bot deployed and running
- At least 2 test groups created
- Test user has admin rights in both groups
- Bot is admin in both groups

## Test Suite

### Test 1: Group Registration
**Objective:** Verify group registration works correctly

**Steps:**
1. Go to a test group where you are admin
2. Send `/recurring` command
3. Observe the bot's response

**Expected Results:**
- ✅ Bot replies with exactly: `grupės skelbimai aktyvuoti`
- ✅ No additional text or instructions
- ✅ Group is added to `groups` table in database

**Test as non-admin:**
1. Have a non-admin user send `/recurring` in the group
2. Observe response

**Expected Results:**
- ✅ Bot replies: `❌ Tik administratoriai gali aktyvuoti skelbimus.`

---

### Test 2: Private Group Selection
**Objective:** Verify group selection menu works in private chat

**Steps:**
1. Open private chat with bot
2. Send `/recurring` command
3. Observe the menu

**Expected Results:**
- ✅ Bot shows "Pasikartojantys skelbimai" menu
- ✅ List contains the just-registered group(s)
- ✅ NO "❌ Nerasta grupių!" error
- ✅ Each group has a button with its name
- ✅ "🔙 Atšaukti" button present

**Select a group:**
1. Click on one of the group buttons
2. Observe the result

**Expected Results:**
- ✅ Main menu opens for that group
- ✅ Shows group name and current time
- ✅ "➕ Pridėti skelbimą" button visible
- ✅ "🔄 Keisti grupę" button visible (since in private chat)

---

### Test 3: Text Input and UI Flow
**Objective:** Verify text input returns to customize screen with checkmarks

**Steps:**
1. In private chat, select a group
2. Click "➕ Pridėti skelbimą"
3. Click "✏️ Pritaikyti pranešimą"
4. Click "📝 Text"
5. Send a test message: "Test recurring message"
6. Observe the response

**Expected Results:**
- ✅ Bot confirms: "✅ Message text saved!"
- ✅ Returns to customize screen automatically
- ✅ Shows "📝 Text: ✅" with green checkmark
- ✅ "📷 Media: ❌" and "🔗 Url Buttons: ❌" still show X

---

### Test 4: Media Input (File Upload)
**Objective:** Verify media file upload works

**Steps:**
1. From customize screen, click "📷 Media"
2. Upload a photo/video/document
3. Observe the response

**Expected Results:**
- ✅ Bot confirms: "✅ Photo saved!" (or Video/Document)
- ✅ Returns to customize screen automatically
- ✅ Shows "📷 Media: ✅" with green checkmark

---

### Test 5: URL Buttons
**Objective:** Verify URL button parsing and validation

**Steps:**
1. From customize screen, click "🔗 Url Buttons"
2. Send button definitions:
   ```
   Visit Website - https://example.com
   Telegram - https://t.me/example
   ```
3. Observe the response

**Expected Results:**
- ✅ Bot confirms: "✅ 2 buttons saved!"
- ✅ Returns to customize screen
- ✅ Shows "🔗 Url Buttons: ✅"

**Test invalid URL:**
1. Click "🔗 Url Buttons" again
2. Send: `Bad Button - not-a-url`
3. Observe response

**Expected Results:**
- ✅ Bot shows error about invalid URL
- ✅ Does not save the button

---

### Test 6: Time Selection
**Objective:** Verify time slot buttons work

**Steps:**
1. From message config screen, click "⏰ Laikas"
2. Click "🌇 Vakaras (18:00)"
3. Observe the response

**Expected Results:**
- ✅ Toast notification: "✅ Time set to 18:00"
- ✅ Returns to message config screen
- ✅ Shows "⏰ Laikas: 18:00" in the status

---

### Test 7: Save and Schedule
**Objective:** Verify message is saved and scheduled correctly

**Steps:**
1. Complete setup (text, time, repetition)
2. Scroll down in config menu
3. Click "💾 Save" (if visible) or look for save option
4. Observe the response

**Expected Results:**
- ✅ Bot confirms message saved
- ✅ Job created in APScheduler
- ✅ Entry added to `scheduled_messages` table
- ✅ `job_id` field populated
- ✅ `message_buttons` and `message_media` saved as JSON if set

**Verify scheduling:**
1. Wait for scheduled time (or set to 1 minute ahead for testing)
2. Check the group

**Expected Results:**
- ✅ Message sent to group at scheduled time
- ✅ If media was set, media is included
- ✅ If buttons were set, buttons appear
- ✅ If pin was enabled, message is pinned
- ✅ If delete_last was enabled, previous message deleted

---

### Test 8: Manage Messages (Pause/Resume/Delete)
**Objective:** Verify message management works

**Steps:**
1. From main menu, click "📋 Tvarkyti skelbimus"
2. Select a scheduled message
3. Click "⏸️ Pause" (or equivalent)
4. Observe result

**Expected Results:**
- ✅ Message paused
- ✅ Job removed from scheduler
- ✅ Database status updated
- ✅ No errors

**Resume:**
1. Click "▶️ Resume"
2. Observe result

**Expected Results:**
- ✅ Message resumed
- ✅ Job recreated in scheduler
- ✅ Database status updated

**Delete:**
1. Click "🗑️ Delete"
2. Confirm deletion
3. Observe result

**Expected Results:**
- ✅ Message deleted from database
- ✅ Job removed from scheduler
- ✅ Returns to manage list (or main menu if no messages left)

---

### Test 9: No AttributeError Crashes
**Objective:** Verify no `AttributeError: 'NoneType' object has no attribute 'reply_text'`

**Steps:**
1. Perform all above tests
2. Click every button in every menu
3. Switch between private chat and group chat flows
4. Observe logs

**Expected Results:**
- ✅ No `AttributeError` in logs
- ✅ All buttons respond correctly
- ✅ All menus use `update.effective_message` or `query.edit_message_text` appropriately

---

### Test 10: Multi-Group Workflow
**Objective:** Verify multiple groups can be managed independently

**Steps:**
1. Register Group A with `/recurring`
2. Register Group B with `/recurring`
3. In private chat, send `/recurring`
4. Verify both groups appear in selection
5. Select Group A, create a message
6. Go back, select Group B, create a different message
7. Verify each message is scheduled to the correct group

**Expected Results:**
- ✅ Both groups listed
- ✅ Each group's messages are independent
- ✅ Scheduled messages go to correct groups
- ✅ No cross-contamination of configs

---

### Test 11: Persistence Across Restarts
**Objective:** Verify jobs persist after bot restart

**Steps:**
1. Create a scheduled message
2. Restart the bot
3. Wait for scheduled time

**Expected Results:**
- ✅ Message still sends after restart
- ✅ Jobs loaded from database on startup
- ✅ No errors in logs

---

## Summary Checklist

- [ ] Group registration shows only "grupės skelbimai aktyvuoti"
- [ ] Private chat shows group selection immediately
- [ ] No "Nerasta grupių!" error after registration
- [ ] Text/Media/Buttons return to customize screen with ✅
- [ ] Time buttons work and update config
- [ ] Save creates actual APScheduler jobs
- [ ] Messages send at scheduled times
- [ ] Media and buttons render correctly in sent messages
- [ ] Pause/Resume/Delete work without errors
- [ ] No AttributeError crashes anywhere
- [ ] Multi-group support works correctly
- [ ] Jobs persist across bot restarts

---

## Notes
- All user-facing text should be in Lithuanian
- Logs can remain in English for debugging
- Test with both photo, video, and document media types
- Test with multiple URL buttons (2-5 buttons)
- Test edge cases: invalid times, malformed URLs, empty text

