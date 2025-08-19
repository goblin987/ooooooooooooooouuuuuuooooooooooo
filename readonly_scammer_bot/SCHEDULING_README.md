# 🔄 Repeated Messages Feature

This bot now includes the same repeated messages functionality as GroupHelpBot, allowing administrators to schedule messages that repeat automatically at specified intervals.

## ✨ Features

### 📝 Schedule Messages
- **Command:** `/schedule <interval> <message>`
- **Admin Only:** Only group administrators can use this command
- **Flexible Intervals:** Support for various time formats

### 📋 List Scheduled Messages
- **Command:** `/list_schedules`
- **Shows:** All active scheduled messages in the current group
- **Details:** Message preview, interval, creator, status, last sent time

### 🗑️ Delete Scheduled Messages
- **Command:** `/delete_schedule <ID>`
- **Removes:** Both from database and scheduler
- **Safe:** Only works for messages in the current group

## 🕐 Interval Formats

The bot supports flexible interval formats:

| Format | Description | Example |
|--------|-------------|---------|
| `30m` | 30 minutes | `/schedule 30m Daily reminder!` |
| `2h` | 2 hours | `/schedule 2h Check for updates` |
| `1h30m` | 1 hour 30 minutes | `/schedule 1h30m Mixed format` |
| `180` | 180 minutes | `/schedule 180 Pure number format` |

### ⚠️ Limits
- **Minimum:** 10 minutes
- **Maximum:** 24 hours (1440 minutes)
- **Message length:** 4000 characters max

## 📋 Usage Examples

```bash
# Schedule a message every 3 hours
/schedule 3h 🛡️ Remember to verify sellers before trading!

# Schedule a reminder every 30 minutes
/schedule 30m ⚠️ Always check user reports: /patikra username

# View all scheduled messages
/list_schedules

# Delete a scheduled message (ID from list_schedules)
/delete_schedule 1
```

## 🔧 Technical Details

### Database Schema
The bot uses SQLite with a `scheduled_messages` table containing:
- Message text and intervals
- Creator information
- Job IDs for scheduler management
- Activity status and timestamps

### Scheduler
- Uses APScheduler (AsyncIOScheduler) for reliable message scheduling
- Jobs persist across bot restarts
- Automatic job restoration from database on startup
- Error handling with logging

### Permissions
- Only group administrators can manage scheduled messages
- In private chats, all users are considered "admins"
- Permission checks use Telegram's built-in admin status

## 🚀 Getting Started

1. **Add the bot to your group**
2. **Make the bot an admin** (optional, but recommended for better functionality)
3. **Use `/schedule` command** as a group administrator
4. **Manage messages** with `/list_schedules` and `/delete_schedule`

## 🛡️ Security Features

- Admin-only access to scheduling commands
- Input validation for intervals and message length
- Safe job management with unique IDs
- Database integrity with proper indexing

## 🔄 Integration with Existing Features

The scheduling functionality works alongside all existing scammer/buyer checking features:

- All original commands remain unchanged
- Scheduled messages can include scammer check reminders
- Perfect for community safety announcements
- Compatible with existing database and API sync features

---

*This feature brings GroupHelpBot-like functionality to your scammer checking bot, making it a complete community management solution!*

