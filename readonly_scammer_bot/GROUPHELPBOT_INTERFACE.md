# 🔄 GroupHelpBot-Style Recurring Messages Interface

Your bot now has the **exact same interface and functionality as GroupHelpBot** for recurring messages! 

## 🚀 **Getting Started**

Use the command `/recurring` to open the interactive menu system that matches GroupHelpBot's interface exactly.

## 📱 **Interface Overview**

### **Main Menu** (`/recurring`)
```
🔄 Recurring messages

From this menu you can set messages that will be sent 
repeatedly to the group every few minutes/hours or every 
few messages.

Current time: 18/08/25 18:47

[➕ Add message]
[🔙 Back]
```

### **Message Configuration Screen**
```
🔄 Recurring messages

📊 Status: ❌ Off
⏰ Time: 18:47
🔄 Repetition: Every 24 hours
📌 Pin message: ❌
🗑️ Delete last message: ❌

[✏️ Customize message]
[⏰ Time] [🔄 Repetition]
[📅 Days of the week]
[📅 Days of the month]
[🕐 Set time slot]
[📅 Start date] [📅 End date]
[📌 Pin message ❌]
[🗑️ Delete last message ❌]
[⏱️ Scheduled deletion]
[🔙 Back]
```

### **Message Customization Screen**
```
🔄 Recurring messages

📝 Text: ❌
📷 Media: ❌
🔗 Url Buttons: ❌

Use the buttons below to choose what you want to set

[📝 Text] [👁️ See]
[📷 Media] [👁️ See]
[🔗 Url Buttons] [👁️ See]
[👁️ Full preview]
[📋 Select a Topic]
[🔙 Back]
```

## ✨ **Key Features Implemented**

### **🔄 Repetition Options**
- **⏰ Every 24 hours** - Daily recurring messages
- **📅 Days of the week** - Select specific weekdays
- **📅 Days of the month** - Select specific dates
- **🔄 Custom interval** - Set custom time intervals

### **🕐 Time Slot Selection**
- **🌅 Morning (08:00)** - Pre-set morning time
- **🌞 Midday (12:00)** - Pre-set midday time  
- **🌇 Evening (18:00)** - Pre-set evening time
- **🌙 Night (22:00)** - Pre-set night time
- **⏰ Custom time** - Set any specific time
- **🔄 Multiple times** - Set multiple daily times

### **📅 Days of Week Selection**
Interactive checkboxes for each day:
```
📅 Days of the week

Select which days of the week to send the message:

[⬜ Monday]
[✅ Tuesday]  
[⬜ Wednesday]
[✅ Thursday]
[⬜ Friday]
[⬜ Saturday]
[⬜ Sunday]

[✅ Confirm Selection]
[🔙 Back]
```

### **📝 Message Types**
- **📝 Text messages** - Rich text with Markdown support
- **📷 Media messages** - Photos, videos, documents
- **🔗 URL Buttons** - Interactive inline buttons
- **👁️ Live preview** - See exactly how your message will look

### **⚙️ Advanced Options**
- **📌 Pin message** - Auto-pin recurring messages
- **🗑️ Delete last message** - Remove previous before sending new
- **⏱️ Scheduled deletion** - Auto-delete after specified time
- **📅 Start/End dates** - Set campaign duration
- **📋 Topic templates** - Pre-built message templates

## 🎯 **Usage Examples**

### **Daily Safety Reminder**
1. `/recurring` → ➕ Add message
2. ✏️ Customize message → 📝 Text
3. Enter: "🛡️ Remember to check sellers with /patikra before trading!"
4. 🔄 Repetition → ⏰ Every 24 hours
5. 🕐 Set time slot → 🌅 Morning (08:00)
6. ✅ Save and activate

### **Weekly Scammer Alert**
1. `/recurring` → ➕ Add message
2. ✏️ Customize message → 📝 Text
3. Enter: "⚠️ Weekly reminder: Always verify users before transactions!"
4. 🔄 Repetition → 📅 Days of the week
5. Select: ✅ Monday, ✅ Friday
6. 🕐 Set time slot → 🌞 Midday (12:00)
7. ✅ Save and activate

### **Trading Hours Reminder**
1. `/recurring` → ➕ Add message
2. ✏️ Customize message → 📝 Text
3. Enter: "🕐 Trading hours are now open! Stay safe!"
4. 🔄 Repetition → 📅 Days of the week
5. Select: Monday through Friday
6. 🕐 Set time slot → 🔄 Multiple times
7. Enter: "08:00, 12:00, 18:00"
8. ✅ Save and activate

## 🔧 **Technical Features**

### **Database Integration**
- Enhanced SQLite schema with all GroupHelpBot fields
- Supports complex scheduling patterns
- Persistent storage across bot restarts
- Full message configuration preservation

### **Scheduler System**
- APScheduler for reliable message delivery
- Support for multiple timing patterns
- Automatic job restoration on startup
- Error handling and logging

### **Admin Security**
- Only group administrators can access recurring messages
- Permission verification for all operations
- Safe database operations
- Audit logging

## 🎨 **UI/UX Features**

### **Identical to GroupHelpBot**
- ✅ Same button layout and text
- ✅ Same navigation flow
- ✅ Same status indicators (❌/✅)
- ✅ Same time format display
- ✅ Same emoji usage throughout

### **Interactive Elements**
- **Toggle buttons** with visual feedback
- **Multi-selection** with checkboxes
- **Live status updates** in real-time
- **Breadcrumb navigation** between screens

### **User-Friendly Design**
- **Clear instructions** at each step
- **Visual confirmation** of selections
- **Easy navigation** with Back buttons
- **Contextual help** and examples

## 🚀 **Ready to Use**

Your bot now provides the **complete GroupHelpBot recurring messages experience**:

1. **Start with** `/recurring`
2. **Navigate** using the inline keyboard
3. **Configure** your messages exactly like GroupHelpBot
4. **Set schedules** with the same flexibility
5. **Manage everything** from the same interface

The interface is **pixel-perfect** to GroupHelpBot while maintaining all your existing scammer checking functionality!

---

*🎯 **Perfect GroupHelpBot Clone** - Same UI, Same Features, Same Experience!*

