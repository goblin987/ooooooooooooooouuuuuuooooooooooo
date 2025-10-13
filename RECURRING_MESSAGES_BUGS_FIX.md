# 🔧 Recurring Messages - Complete Bug Fix

## 🐛 IDENTIFIED BUGS

### ❌ CRITICAL BUGS
1. **Save button doesn't create actual scheduled jobs**
   - Clicking save shows success but message never sends
   - No APScheduler job created
   - No database persistence

2. **Days of week selection doesn't work**
   - UI shows selection
   - Selection not used in job creation
   - Should create cron job with specific days

3. **Days of month selection doesn't work**
   - Same as days of week
   - Should create cron job with specific dates

4. **Time slots not saved**
   - Time selection lost after customization
   - Should persist selected time

5. **Multiple times not implemented**
   - Button exists but no handler
   - Should allow multiple jobs per day

6. **Message preview not implemented**
   - Button exists but shows placeholder
   - Should show formatted message

7. **Start/end dates not implemented**
   - No UI for this feature
   - Should restrict job execution period

8. **Pin message doesn't work**
   - Toggle works in UI
   - Not applied when message sends

9. **Delete last message doesn't work**
   - Toggle works in UI
   - Previous message not deleted

10. **Status toggle doesn't activate/deactivate jobs**
    - Just changes text
    - Should pause/resume APScheduler jobs

---

## ✅ FIXES TO IMPLEMENT

### 1. **Save Function - Create Actual Jobs**
```python
async def save_recurring_message(query, context):
    """Actually save and schedule the message"""
    config = context.user_data['recur_msg_config']
    chat_id = query.message.chat_id
    
    # Create cron or interval trigger based on config
    if config.get('days_of_week'):
        # Cron job for specific days
        trigger = CronTrigger(
            day_of_week=','.join([day_map[d] for d in config['days_of_week']]),
            hour=time_hour,
            minute=time_minute,
            timezone='Europe/Vilnius'
        )
    elif config.get('days_of_month'):
        # Cron job for specific dates
        trigger = CronTrigger(
            day=','.join([str(d) for d in config['days_of_month']]),
            hour=time_hour,
            minute=time_minute,
            timezone='Europe/Vilnius'
        )
    else:
        # Interval trigger
        trigger = IntervalTrigger(
            hours=interval_hours,
            timezone='Europe/Vilnius'
        )
    
    # Add job to scheduler
    job = scheduler.add_job(
        send_recurring_message,
        trigger=trigger,
        args=[chat_id, config],
        id=f"recur_{chat_id}_{timestamp}"
    )
    
    # Save to database
    save_to_database(chat_id, config, job.id)
```

### 2. **Send Message Function**
```python
async def send_recurring_message(chat_id, config):
    """Send the actual recurring message"""
    # Delete last message if enabled
    if config.get('delete_last') and config.get('last_message_id'):
        try:
            await bot.delete_message(chat_id, config['last_message_id'])
        except:
            pass
    
    # Send message
    message = await bot.send_message(
        chat_id,
        config['text'],
        parse_mode='Markdown'
    )
    
    # Pin if enabled
    if config.get('pin_message'):
        await bot.pin_chat_message(chat_id, message.message_id)
    
    # Store message ID
    update_last_message_id(chat_id, message.message_id)
```

### 3. **Days of Week - Working Implementation**
```python
day_map = {
    'Monday': 'mon',
    'Tuesday': 'tue',
    'Wednesday': 'wed',
    'Thursday': 'thu',
    'Friday': 'fri',
    'Saturday': 'sat',
    'Sunday': 'sun'
}

# When confirmed
if selected_days:
    day_string = ','.join([day_map[d] for d in selected_days])
    config['cron_days'] = day_string
    config['repetition_type'] = 'days_of_week'
```

### 4. **Message Preview**
```python
async def show_message_preview(query, context):
    """Show formatted message preview"""
    config = context.user_data['recur_msg_config']
    
    preview_text = "👁️ **Message Preview**\n\n"
    preview_text += "---\n"
    preview_text += config.get('text', '(No text set)')
    preview_text += "\n---\n\n"
    
    if config.get('pin_message'):
        preview_text += "📌 This message will be pinned\n"
    if config.get('delete_last'):
        preview_text += "🗑️ Previous message will be deleted\n"
    
    await query.edit_message_text(preview_text, parse_mode='Markdown')
```

### 5. **Multiple Times Per Day**
```python
async def show_multiple_times_screen(query, context):
    """Allow multiple sending times"""
    text = "⏰ **Multiple Times**\n\n"
    text += "Current times:\n"
    
    times = context.user_data['recur_msg_config'].get('times', [])
    for i, t in enumerate(times, 1):
        text += f"{i}. {t}\n"
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Time", callback_data="recur_add_time")],
        [InlineKeyboardButton("🔙 Back", callback_data="recur_config")]
    ]
    
    # Create multiple jobs, one for each time
    for time in times:
        hour, minute = time.split(':')
        scheduler.add_job(...)
```

---

## 📋 IMPLEMENTATION PLAN

1. ✅ Add `send_recurring_message()` function
2. ✅ Fix `save` callback to create actual jobs
3. ✅ Implement days of week scheduling
4. ✅ Implement days of month scheduling
5. ✅ Add message preview handler
6. ✅ Implement multiple times
7. ✅ Fix pin message functionality
8. ✅ Fix delete last message functionality
9. ✅ Add database persistence
10. ✅ Add job management (pause/resume/delete)

---

## 🚀 TESTING CHECKLIST

After fixes:
- [ ] Save message → Job created in scheduler
- [ ] Message sends at scheduled time
- [ ] Days of week selection works
- [ ] Days of month selection works
- [ ] Multiple times per day works
- [ ] Pin message works
- [ ] Delete last message works
- [ ] Preview shows correct format
- [ ] Status toggle pauses/resumes jobs
- [ ] Jobs persist after bot restart

---

**Ready to implement all fixes!**

