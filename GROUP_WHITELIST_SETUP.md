# 🔒 Group Whitelist Setup Guide

## Overview
Your bot now has a **group whitelist** system that prevents unauthorized groups from using the bot.

## How It Works

### ✅ Whitelisted Groups
- Bot responds to ALL commands
- Members earn XP and points
- All features work normally
- Silently ignores unauthorized groups (no error messages)

### ❌ Non-Whitelisted Groups
- Bot completely ignores all messages and commands
- No error messages sent (stays invisible)
- Logged on server for monitoring

## Setup Instructions

### Step 1: Get Your Group IDs

To find a group ID:
1. Add the bot to your group
2. Send any message in the group
3. Check the bot logs for: `Unauthorized group -1001234567890 (GroupName) - ignoring`
4. Copy the negative number (e.g., `-1001234567890`)

**Alternative method:**
1. Forward a message from the group to [@JsonDumpBot](https://t.me/JsonDumpBot)
2. Look for `"chat":{"id":-1001234567890}`

### Step 2: Add Groups to Whitelist

On **Render.com** (your hosting):

1. Go to your bot service
2. Click **"Environment"** tab
3. Add a new environment variable:
   - **Key**: `ALLOWED_GROUPS`
   - **Value**: Your group IDs separated by commas

**Example:**
```
-1001234567890,-1009876543210,-1005555666777
```

### Step 3: Redeploy

After adding the environment variable:
1. Click **"Manual Deploy"** → **"Deploy latest commit"**
2. Wait for deployment to complete (~2 minutes)
3. Bot will now only work in whitelisted groups!

## Configuration Examples

### Single Group
```
ALLOWED_GROUPS=-1001234567890
```

### Multiple Groups (Main + Backups)
```
ALLOWED_GROUPS=-1001234567890,-1009876543210,-1005555666777
```

### Allow All Groups (Not Recommended)
```
# Don't set ALLOWED_GROUPS variable at all
# Or leave it empty
ALLOWED_GROUPS=
```

## Verification

After setup:

1. **Test in whitelisted group:**
   - Send `/barygos` → Should work ✅
   - Send message → Should earn XP ✅

2. **Test in non-whitelisted group:**
   - Send `/barygos` → No response (silently ignored) ✅
   - Send message → No XP earned ✅

3. **Check logs:**
   - Render logs will show: `🚫 Unauthorized group -1001234567890 (GroupName) tried to use /barygos`

## Adding New Groups

To add a new group:
1. Get the group ID (see Step 1)
2. Add it to `ALLOWED_GROUPS` variable (comma-separated)
3. **Save** environment variables
4. Bot automatically reloads - no manual deploy needed!

## Removing Groups

To remove a group:
1. Edit `ALLOWED_GROUPS` variable
2. Remove the group ID
3. **Save** environment variables
4. Bot automatically reloads

## Security Features

✅ **Silent Operation**: No error messages in unauthorized groups (bot stays invisible)
✅ **Logging**: All unauthorized attempts logged for monitoring
✅ **Private Chats**: Always allowed (for admin panel, etc.)
✅ **Flexible**: Easy to add/remove groups anytime

## Troubleshooting

### Bot not responding in ANY group
- Check if `ALLOWED_GROUPS` is set correctly
- Verify group IDs are negative numbers
- Check for typos in group IDs
- View logs for "Group whitelist enabled" message

### Bot responding in unauthorized groups
- Verify `ALLOWED_GROUPS` variable is set
- Check spelling: must be `ALLOWED_GROUPS` (not `ALLOWED_GROUP`)
- Ensure comma-separated format with NO SPACES

### Can't find group ID
- Use [@JsonDumpBot](https://t.me/JsonDumpBot) method
- Or check Render logs after sending a message

## Quick Reference

| Action | Command |
|--------|---------|
| Find group ID | Forward message to [@JsonDumpBot](https://t.me/JsonDumpBot) |
| Add groups | Edit `ALLOWED_GROUPS` in Render environment |
| View logs | Render Dashboard → Logs tab |
| Test whitelist | Send `/barygos` in test group |

## Your Current Groups

When you deploy, the bot will log:
```
✅ Group whitelist enabled: 3 allowed groups
```

Check Render logs to verify your groups are loaded!

---

**Need Help?**
- Check Render logs for detailed error messages
- Group IDs must be negative numbers starting with `-100`
- No spaces in the `ALLOWED_GROUPS` variable

