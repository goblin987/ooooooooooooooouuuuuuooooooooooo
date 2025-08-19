# 🚫 Banned Words Feature - Automatic Word Filtering

Your bot now includes a powerful banned words system that automatically detects and punishes users who use forbidden words!

## 🎯 **Main Features**

### **📋 Banned Words Management**
- **Inline UI** - Beautiful interface matching GroupHelpBot style
- **Add/Remove words** - Easy management of banned words
- **Multiple actions** - Choose what happens when words are used
- **Status control** - Activate/deactivate words without deleting

### **⚡ Automatic Detection**
- **Real-time checking** - Every message is scanned instantly
- **Case insensitive** - Works regardless of capitalization
- **Admin protection** - Administrators are exempt from filtering
- **Message deletion** - Offensive messages are automatically removed

## 🛡️ **Action Types**

### **⚠️ Warn**
- **Message deleted** - Offensive content removed
- **Warning sent** - User receives a warning message
- **No punishment** - User can continue chatting

### **🔇 Mute**
- **Message deleted** - Offensive content removed
- **User muted** - User cannot send messages
- **Notification sent** - Group informed of the action
- **Manual unmute** - Admin must manually unmute

### **🚫 Ban**
- **Message deleted** - Offensive content removed
- **User banned** - User removed from group permanently
- **Notification sent** - Group informed of the action
- **Manual unban** - Admin must manually unban

## 🎮 **Usage Guide**

### **Opening Banned Words Menu**
```
/bannedwords
```

### **Adding a Banned Word**
1. Click **"➕ Add word"**
2. Send the word you want to ban
3. Choose action: **⚠️ Warn**, **🔇 Mute**, or **🚫 Ban**
4. Word is added and active immediately

### **Managing Existing Words**
- **[Word Number]** - View detailed information
- **[Status Button]** - Toggle active/inactive
- **[🗑️ Delete]** - Remove word permanently

## 📱 **Interface Layout**

### **Main Menu**
```
🚫 Banned words

From this menu you can manage words that are banned 
in this group. Users who use these words will be 
automatically punished.

Current time: 18/08/25 18:58

📋 Banned words (2):

1 • ✅ Active ✅
   Word: `spam`
   Action: ⚠️ Warn
   Added by: @admin

2 • ❌ Inactive ❌
   Word: `badword`
   Action: 🚫 Ban
   Added by: @moderator

[➕ Add word]
[1] [❌ Inactive] [🗑️]
[2] [✅ Active] [🗑️]
[🔙 Back]
```

### **Word Details View**
```
📋 Banned Word #1 Details

📝 Word: `spam`
📊 Status: ✅ Active
⚡ Action: ⚠️ Warn
👤 Added by: @admin
📅 Added: 2025-08-18 18:47:00

[🔙 Back to Manage]
```

### **Action Selection**
```
🚫 Add banned word: `spam`

Choose what action to take when this word is used:

[⚠️ Warn]
[🔇 Mute]
[🚫 Ban]
[🔙 Back]
```

## 🔧 **Technical Features**

### **Database Storage**
- **Persistent storage** - Words survive bot restarts
- **Chat-specific** - Each group has its own word list
- **User tracking** - Records who added each word
- **Timestamp logging** - When words were added

### **Performance Optimized**
- **Fast detection** - Efficient word matching
- **Indexed database** - Quick lookups
- **Minimal overhead** - Lightweight processing

### **Error Handling**
- **Graceful failures** - Bot continues working if actions fail
- **Permission checks** - Respects admin permissions
- **Safe operations** - Won't crash on invalid input

## 🚀 **Example Scenarios**

### **Scenario 1: Warning System**
1. User types: "This is spam content"
2. Bot detects "spam" (warn action)
3. Message deleted
4. Warning sent: "⚠️ WARNING - Used banned word: spam"
5. User can continue chatting

### **Scenario 2: Mute System**
1. User types: "badword here"
2. Bot detects "badword" (mute action)
3. Message deleted
4. User muted automatically
5. Notification: "🔇 USER MUTED - Used banned word: badword"

### **Scenario 3: Ban System**
1. User types: "inappropriate content"
2. Bot detects "inappropriate" (ban action)
3. Message deleted
4. User banned automatically
5. Notification: "🚫 USER BANNED - Used banned word: inappropriate"

## ⚙️ **Configuration**

### **Word Limits**
- **Maximum length**: 50 characters
- **Case handling**: Automatically converted to lowercase
- **Special characters**: Allowed (emojis, symbols, etc.)

### **Admin Protection**
- **Administrators**: Exempt from all filtering
- **Group owners**: Exempt from all filtering
- **Bot admins**: Can manage words without restrictions

### **Message Handling**
- **Deletion**: Offensive messages are removed
- **Notifications**: Group is informed of actions
- **User info**: Shows username and display name
- **Message preview**: Shows truncated original message

## 🔒 **Security Features**

### **Permission System**
- **Admin only**: Only admins can manage banned words
- **Action permissions**: Respects bot's permissions in group
- **Safe operations**: Won't attempt actions without proper permissions

### **Data Protection**
- **Local storage**: Words stored in local database
- **No external sharing**: Data stays within the bot
- **Secure handling**: Proper error handling and validation

---

*🎯 **Powerful Word Filtering** - Keep your group clean and safe with automatic content moderation!*

