# Helpers Feature Documentation

## Overview
The Helpers feature allows group administrators to grant moderation permissions to regular users who are not group administrators. These helpers can use ban and mute commands even without admin privileges.

## Main Features

### 🔧 Helper Management
- **Inline UI**: User-friendly interface similar to GroupHelpBot style
- **Add/Remove Helpers**: Add users by their Telegram ID
- **Status Control**: View and manage helper status
- **Permission Tracking**: Track who added each helper and when

### 🛡️ Moderation Permissions
- **Ban Commands**: Helpers can use `/ban` command
- **Mute Commands**: Helpers can use `/mute` command
- **Admin Override**: Helpers bypass admin-only restrictions
- **Permission Validation**: System checks helper status before allowing actions

### 📋 Management Interface
- **Helper List**: View all helpers with status indicators
- **Individual Management**: View details, remove helpers
- **Real-time Updates**: Changes take effect immediately

## Usage Guide

### Adding a Helper
1. Use `/helpers` command (admin only)
2. Click "➕ Add helper" button
3. Enter the user's Telegram ID
4. Helper is added and can immediately use moderation commands

### Removing a Helper
1. Use `/helpers` command
2. Find the helper in the list
3. Click "🗑️" button next to their name
4. Helper loses moderation permissions immediately

### Helper Permissions
- Can use `/ban username/id [reason]` command
- Can use `/unban username/id` command  
- Can use `/mute username/id [reason]` command
- Can use `/unmute username/id` command
- Cannot add/remove other helpers
- Cannot access other admin features

## Technical Features

### Database Storage
- **Helpers Table**: Stores helper information
- **User Tracking**: Records who added each helper
- **Timestamp Tracking**: Records when helpers were added
- **Status Management**: Active/inactive status support

### Security Features
- **Admin Only Access**: Only admins can manage helpers
- **User Validation**: System verifies user exists in group
- **Permission Checks**: Validates helper status before actions
- **Audit Trail**: Tracks who added each helper

### Performance
- **Efficient Queries**: Indexed database lookups
- **Cached Checks**: Fast permission validation
- **Minimal Overhead**: Lightweight permission system

## Configuration

### Helper Limits
- No limit on number of helpers per group
- Each helper has individual permissions
- Helpers can be added/removed at any time

### Permission Scope
- Helpers only work in the group they were added to
- Permissions don't transfer between groups
- Each group manages its own helpers independently

### Integration
- Works seamlessly with existing ban/mute commands
- No changes needed to existing moderation workflow
- Backward compatible with admin-only system

## Security Considerations

### Access Control
- Only group administrators can add/remove helpers
- Helpers cannot modify their own permissions
- System prevents privilege escalation

### Validation
- User ID validation before adding helpers
- Group membership verification
- Permission checks on every command

### Monitoring
- All helper actions are logged
- Admin can see who added each helper
- Full audit trail for accountability

## Error Handling

### Common Issues
- **Invalid User ID**: System validates before adding
- **User Not in Group**: Helper must be group member
- **Permission Denied**: Clear error messages for users

### Recovery
- **Helper Removal**: Immediate permission revocation
- **Database Integrity**: Consistent state management
- **Error Logging**: Detailed error tracking

## Best Practices

### Adding Helpers
- Only add trusted users as helpers
- Verify user ID before adding
- Monitor helper activity regularly

### Security
- Regularly review helper list
- Remove inactive helpers
- Keep helper count manageable

### Communication
- Inform helpers of their permissions
- Establish clear guidelines
- Monitor helper actions for compliance

