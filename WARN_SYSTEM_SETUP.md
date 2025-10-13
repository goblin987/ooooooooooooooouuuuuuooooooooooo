# ⚠️ Warn System Setup - GroupHelpBot Style

## 📋 What Was Added

### 1. **warn_system.py** - Complete Warning System
Features:
- `/warn @username [reason]` - Warn a user
- `/unwarn @username` - Remove last warning  
- `/warnings [@username]` - Check warnings
- `/resetwarns @username` - Clear all warnings

**Auto-sanctions after 3 warnings:**
- Default: 12-hour mute
- Configurable: Can be set to kick or ban instead

### 2. **add_warnings_table.py** - Database Migration
Creates the `warnings` table with:
- user_id, username, chat_id
- warned_by, reason, timestamp
- is_active flag (for soft deletes)
- Proper indexes for performance

---

## 🚀 Setup Instructions

### Step 1: Run Database Migration
```bash
python add_warnings_table.py
```

### Step 2: Add to OGbotas.py

**Add import (around line 50):**
```python
import warn_system
```

**Register commands (around line 445, after ban/unban):**
```python
# Warn system commands
application.add_handler(CommandHandler("warn", warn_system.warn_user))
application.add_handler(CommandHandler("unwarn", warn_system.unwarn_user))
application.add_handler(CommandHandler("warnings", warn_system.warnings_command))
application.add_handler(CommandHandler("resetwarns", warn_system.resetwarns_command))
```

### Step 3: Deploy
```bash
git add warn_system.py add_warnings_table.py WARN_SYSTEM_SETUP.md
git commit -m "feat: Add GroupHelpBot-style warn system with auto-sanctions"
git push origin main
```

---

## 📖 Usage Examples

### Warn a User
```
/warn @username Spam
/warn @username Nesidėkite taisyklių
```

Or reply to their message:
```
(Reply to message)
/warn Netinkamas elgesys
```

### Check Warnings
```
/warnings              # Check your own
/warnings @username    # Check someone else's
```

### Remove Warning
```
/unwarn @username      # Remove last warning
/resetwarns @username  # Clear all warnings
```

---

## ⚙️ Configuration

Edit `warn_system.py` to customize:

```python
DEFAULT_MAX_WARNS = 3           # Warnings before action
DEFAULT_WARN_ACTION = "mute"    # Options: "mute", "kick", "ban"
DEFAULT_MUTE_DURATION = 12      # Hours
```

---

## 🎯 Features

✅ **Auto-sanctions** - Automatic mute/kick/ban after max warnings
✅ **Admin-only** - Only admins can warn users
✅ **Admin protection** - Can't warn other admins
✅ **History tracking** - Full warning history per user
✅ **Soft deletes** - Warnings can be removed but history preserved
✅ **Lithuanian UI** - All messages in clean Lithuanian
✅ **Reply support** - Warn by replying to messages
✅ **Username support** - Warn by @username (uses user cache)

---

## 📊 Database Schema

```sql
CREATE TABLE warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    username TEXT,
    chat_id INTEGER NOT NULL,
    warned_by INTEGER NOT NULL,
    warned_by_username TEXT,
    reason TEXT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT 1
);
```

---

## 🔄 Integration with Existing Systems

The warn system integrates seamlessly with:
- **User cache** - Uses existing username lookup
- **Admin system** - Uses existing admin checks
- **Database** - Uses existing database connection
- **Moderation** - Works alongside ban/mute commands

---

## 🐛 Troubleshooting

**"User not found"** → User must send at least one message first (for cache)
**"Can't warn admins"** → This is intentional (admins can't be warned)
**Warnings not counting** → Check database migration ran successfully

---

## 📝 Notes

- Warnings are **per-chat** (not global)
- Inactive warnings don't count toward limit
- Admin can reset warnings anytime
- System automatically mutes after 3 warnings (default)

---

**Ready to deploy!** 🚀

