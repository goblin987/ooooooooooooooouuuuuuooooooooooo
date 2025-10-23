# Plan: Broadcast Recurring Messages to All Groups

## Current Behavior
- Each recurring message is tied to ONE specific group (`chat_id` in `scheduled_messages` table)
- Message only sends to that one group

## Desired Behavior
- Recurring messages broadcast to ALL groups where bot is admin
- EXCEPT the voting group (identified by `VOTING_GROUP_CHAT_ID`)

## Implementation Plan

### 1. Modify `send_recurring_message()` function

**Location:** `recurring_messages_grouphelp.py` lines 1683-1889

**Changes:**
1. Import `VOTING_GROUP_CHAT_ID` from config
2. Get all groups from `groups` table
3. Loop through each group and send message
4. Skip voting group
5. Handle errors per-group (don't fail entire broadcast if one group fails)

**Pseudocode:**
```python
async def send_recurring_message(bot, chat_id: int, message_id: int):
    # Get message config from database
    # ... (existing code) ...
    
    # Get all groups EXCEPT voting group
    conn = database.get_sync_connection()
    cursor = conn.execute('SELECT chat_id, title FROM groups')
    all_groups = cursor.fetchall()
    
    # Filter out voting group
    from config import VOTING_GROUP_CHAT_ID
    target_groups = [g for g in all_groups if g['chat_id'] != VOTING_GROUP_CHAT_ID]
    
    logger.info(f"📢 Broadcasting message {message_id} to {len(target_groups)} groups")
    
    # Send to each group
    success_count = 0
    for group in target_groups:
        try:
            # Send message to this group
            # ... (existing send logic) ...
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to send to {group['title']}: {e}")
            continue
    
    logger.info(f"✅ Broadcast complete: {success_count}/{len(target_groups)} groups")
```

### 2. Update Database Schema (Optional)

Add a `is_broadcast` flag to `scheduled_messages` table to differentiate:
- Broadcast messages (send to all groups)
- Single-group messages (send to specific group only)

**Migration:**
```sql
ALTER TABLE scheduled_messages ADD COLUMN is_broadcast INTEGER DEFAULT 1;
```

### 3. Update UI

Modify `show_message_config()` to show:
- "Broadcasting to X groups" instead of single group name
- List of target groups (excluding voting group)

### 4. Handle Group-Specific Features

**Pin/Delete Last:**
- Track `last_message_id` per group (need new table or JSON field)
- Currently only tracks one `last_message_id` - needs to be array/dict

**Possible Solutions:**
- A) Don't support pin/delete for broadcast messages
- B) Create `broadcast_message_tracking` table:
  ```sql
  CREATE TABLE broadcast_message_tracking (
      recurring_msg_id INTEGER,
      chat_id INTEGER,
      last_sent_message_id INTEGER,
      last_sent_at TIMESTAMP,
      PRIMARY KEY (recurring_msg_id, chat_id)
  )
  ```

## Files to Modify

1. **recurring_messages_grouphelp.py**
   - `send_recurring_message()` - Lines 1683-1889
   - `show_message_config()` - Lines 242-318 (update UI)
   - `save_and_schedule_message()` - Lines 1895-2145 (set is_broadcast flag)

2. **database.py**
   - Add `is_broadcast` column to `scheduled_messages` table
   - Add migration for existing database
   - Optionally add `broadcast_message_tracking` table

3. **config.py**
   - Already has `VOTING_GROUP_CHAT_ID` - no changes needed

## Testing Plan

1. Create a broadcast recurring message
2. Verify it sends to all groups except voting
3. Check logs show "Broadcasting to X groups"
4. Verify voting group does NOT receive message
5. Test with bot restart (jobs reload correctly)
6. Test error handling (if one group fails, others still receive)

## Edge Cases

1. **Bot removed from group** - Handle gracefully, log warning
2. **Bot not admin** - Can't pin, handle gracefully
3. **Voting group chat_id changes** - Update env var
4. **Empty groups table** - Log warning, don't crash
5. **Group deleted mid-broadcast** - Catch exception, continue

## Backward Compatibility

**Old single-group messages:**
- Keep existing chat_id-based messages working
- Use `is_broadcast` flag to differentiate
- Default new messages to broadcast mode

## Simplification Option

**Skip pin/delete for broadcast messages:**
- Only support basic text/media/buttons
- Remove pin/delete complexity for v1
- Can add later if needed

This keeps implementation simpler and faster to deploy.

## Estimated Changes

- **Lines of code:** ~100 modified, ~50 new
- **Risk level:** MEDIUM (core functionality change)
- **Testing time:** 30 minutes
- **Deployment time:** 5 minutes

## Recommendation

**Simplest approach:**
1. Modify `send_recurring_message()` to broadcast
2. Skip pin/delete features for broadcast (too complex)
3. Add `is_broadcast` column for future
4. Deploy and test

**This gets you working broadcast messages in ~30 minutes.**

