# 🛡️ Moderation Features - Ban & Mute Commands

Your bot now includes powerful moderation features that allow administrators to manage group members effectively!

## 🚫 **Ban Commands**

### **Ban User** - `/ban`
Bans a user from the group permanently.

**Usage:**
```
/ban username/id [reason]
```

**Examples:**
- `/ban @username` - Ban without reason
- `/ban 123456789` - Ban by ID without reason
- `/ban @username Spam` - Ban with reason
- `/ban 123456789 Įžeidžiantis elgesys` - Ban by ID with reason

**Features:**
- ✅ Works with usernames (@username) or user IDs
- ✅ Optional reason parameter
- ✅ Prevents banning administrators/creators
- ✅ Detailed success message with timestamp
- ✅ Error handling for invalid users

### **Unban User** - `/unban`
Unbans a previously banned user.

**Usage:**
```
/unban username/id
```

**Examples:**
- `/unban @username` - Unban by username
- `/unban 123456789` - Unban by ID

**Features:**
- ✅ Works with usernames (@username) or user IDs
- ✅ Restores user access to the group
- ✅ Detailed success message with timestamp

## 🔇 **Mute Commands**

### **Mute User** - `/mute`
Mutes a user (prevents them from sending messages).

**Usage:**
```
/mute username/id [reason]
```

**Examples:**
- `/mute @username` - Mute without reason
- `/mute 123456789` - Mute by ID without reason
- `/mute @username Spam` - Mute with reason
- `/mute 123456789 Įžeidžiantis elgesys` - Mute by ID with reason

**Features:**
- ✅ Works with usernames (@username) or user IDs
- ✅ Optional reason parameter
- ✅ Prevents muting administrators/creators
- ✅ Restricts all message types (text, media, links)
- ✅ Detailed success message with timestamp

### **Unmute User** - `/unmute`
Unmutes a previously muted user.

**Usage:**
```
/unmute username/id
```

**Examples:**
- `/unmute @username` - Unmute by username
- `/unmute 123456789` - Unmute by ID

**Features:**
- ✅ Works with usernames (@username) or user IDs
- ✅ Restores all messaging permissions
- ✅ Detailed success message with timestamp

## 🔐 **Security Features**

### **Permission Checks**
- ✅ Only administrators with ban/mute permissions can use these commands
- ✅ Cannot ban/mute group creators or other administrators
- ✅ Proper error messages for insufficient permissions
- ✅ Works only in groups (not in private chats)

### **User Validation**
- ✅ Validates usernames and user IDs
- ✅ Checks if user exists in the group
- ✅ Handles invalid input gracefully
- ✅ Clear error messages for troubleshooting

### **Audit Trail**
- ✅ Records who performed the action
- ✅ Includes timestamps for all actions
- ✅ Shows target user information (name, username, ID)
- ✅ Displays reason when provided

## 📋 **Success Messages**

### **Ban Success:**
```
🚫 VARTOTOJAS UŽDRAUSTAS 🚫

👤 Vartotojas: John Doe (@johndoe)
🆔 ID: 123456789
👮 Uždraudė: Admin (@admin)
📝 Priežastis: Spam
⏰ Data: 2025-01-18 15:30:45
```

### **Mute Success:**
```
🔇 VARTOTOJAS NUTILDYTAS 🔇

👤 Vartotojas: John Doe (@johndoe)
🆔 ID: 123456789
👮 Nutildė: Admin (@admin)
📝 Priežastis: Spam
⏰ Data: 2025-01-18 15:30:45
```

### **Unban/Unmute Success:**
```
✅ VARTOTOJAS ATKURTAS ✅

👤 Vartotojas: John Doe (@johndoe)
🆔 ID: 123456789
👮 Atkūrė: Admin (@admin)
⏰ Data: 2025-01-18 15:30:45
```

## 🎯 **Usage Scenarios**

### **Spam Control:**
```
/ban @spammer Spam
/mute @spammer Spam
```

### **Rule Violations:**
```
/ban @user Įžeidžiantis elgesys
/mute @user Neatitinka grupių taisyklių
```

### **Temporary Discipline:**
```
/mute @user Laikinas nutildymas
/unmute @user
```

### **Permanent Removal:**
```
/ban @user Nuolatinis pašalinimas
```

## ⚠️ **Important Notes**

### **Permissions Required:**
- **Ban/Unban:** Administrator with "Ban Users" permission
- **Mute/Unmute:** Administrator with "Restrict Users" permission
- **All commands:** Must be used in groups only

### **Limitations:**
- Cannot ban/mute group creators
- Cannot ban/mute other administrators
- Cannot use in private chats
- Requires bot to have appropriate permissions

### **Best Practices:**
- Always provide a reason for transparency
- Use mute for temporary issues, ban for serious violations
- Document actions for group management
- Be consistent with enforcement

## 🔧 **Technical Implementation**

### **Error Handling:**
- Invalid usernames/IDs
- Users not found in group
- Insufficient permissions
- Network/API errors

### **User Lookup:**
- Supports both username and user ID formats
- Handles @ symbol in usernames
- Validates numeric IDs
- Graceful fallback for errors

### **Telegram API Integration:**
- Uses `ban_chat_member()` for bans
- Uses `unban_chat_member()` for unbans
- Uses `restrict_chat_member()` for mutes
- Proper permission management

---

*🛡️ **Professional Moderation Tools** - Keep your group safe and well-managed!*
