#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Admin Panel for OGbotas
Beautiful UI with inline keyboards for all admin operations
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database import database
from utils import data_manager, SecurityValidator
from moderation_grouphelp import is_admin

logger = logging.getLogger(__name__)

# Helper functions for points (USE DATABASE, not pickle!)
def get_user_points(user_id: int) -> int:
    """Get user points from database"""
    try:
        conn = database.get_sync_connection()
        cursor = conn.execute(
            "SELECT points FROM users WHERE user_id = ?",
            (user_id,)
        )
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else 0
    except Exception as e:
        logger.error(f"Error getting points: {e}")
        return 0


def update_user_points(user_id: int, points: int) -> bool:
    """Update user points in database"""
    try:
        conn = database.get_sync_connection()
        conn.execute(
            "INSERT OR REPLACE INTO users (user_id, points) VALUES (?, ?)",
            (user_id, points)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error updating points: {e}")
        return False

# Load global data
user_points = data_manager.load_data('user_points.pkl', {})
trusted_sellers = data_manager.load_data('trusted_sellers.pkl', {})
confirmed_scammers = data_manager.load_data('confirmed_scammers.pkl', {})
pending_scammer_reports = data_manager.load_data('pending_scammer_reports.pkl', {})
username_to_id = data_manager.load_data('username_to_id.pkl', {})


# ============================================================================
# MAIN ADMIN PANEL MENU
# ============================================================================

async def show_admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show main admin panel menu"""
    if not await is_admin(update, context):
        await update.message.reply_text("❌ Only administrators can access the admin panel!")
        return
    
    # Get statistics for display
    stats = get_admin_stats()
    
    text = (
        "🎛️ **ADMIN PANEL**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📊 **Statistics:**\n"
        f"👥 Total Users: {stats['total_users']}\n"
        f"⭐ Trusted Sellers: {stats['trusted_sellers']}\n"
        f"🚨 Confirmed Scammers: {stats['confirmed_scammers']}\n"
        f"⏳ Pending Reports: {stats['pending_reports']}\n"
        f"💰 Total Points Distributed: {stats['total_points']}\n\n"
        "**Select an action:**"
    )
    
    keyboard = [
        [InlineKeyboardButton("💰 Points Management", callback_data="admin_points")],
        [InlineKeyboardButton("⭐ Trusted Sellers", callback_data="admin_sellers")],
        [InlineKeyboardButton("🚨 Scammer List", callback_data="admin_scammers")],
        [InlineKeyboardButton("📋 Review Claims", callback_data="admin_claims")],
        [InlineKeyboardButton("🔍 User Lookup", callback_data="admin_lookup")],
        [InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")],
        [InlineKeyboardButton("🔄 Recurring Messages", callback_data="admin_recurring")],
        [InlineKeyboardButton("👤 Masked Users", callback_data="admin_masked")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")],
        [InlineKeyboardButton("❌ Close", callback_data="admin_close")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )


def get_admin_stats() -> Dict[str, int]:
    """Get statistics for admin panel"""
    return {
        'total_users': len(user_points),
        'trusted_sellers': len(trusted_sellers),
        'confirmed_scammers': len(confirmed_scammers),
        'pending_reports': len(pending_scammer_reports),
        'total_points': sum(user_points.values())
    }


# ============================================================================
# POINTS MANAGEMENT
# ============================================================================

async def show_points_menu(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show points management menu - reads LIVE data from database"""
    # Get live stats from database (not cached pickle)
    try:
        conn = database.get_sync_connection()
        cursor = conn.execute("SELECT COUNT(*), SUM(points) FROM users WHERE points > 0")
        result = cursor.fetchone()
        conn.close()
        
        users_with_points = result[0] if result[0] else 0
        total_points = result[1] if result[1] else 0
    except Exception as e:
        logger.error(f"Error getting points stats: {e}")
        users_with_points = 0
        total_points = 0
    
    text = (
        "💰 **POINTS MANAGEMENT**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Manage user points for the rewards system.\n\n"
        "**Total Points Distributed:** {}\n"
        "**Users with Points:** {}\n\n"
        "**Select an action:**"
    ).format(int(total_points), users_with_points)
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Points to User", callback_data="points_add")],
        [InlineKeyboardButton("➖ Remove Points from User", callback_data="points_remove")],
        [InlineKeyboardButton("👤 Check User Points", callback_data="points_check")],
        [InlineKeyboardButton("🏆 Top Users Leaderboard", callback_data="points_leaderboard")],
        [InlineKeyboardButton("🔄 Reset User Points", callback_data="points_reset")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="admin_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def points_add_start(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start process to add points"""
    text = (
        "➕ **ADD POINTS TO USER**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please send the username and points in this format:\n"
        "`@username 100`\n\n"
        "Or reply with /cancel to go back."
    )
    
    context.user_data['admin_action'] = 'points_add'
    await query.edit_message_text(text, parse_mode='Markdown')


async def points_remove_start(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start process to remove points"""
    text = (
        "➖ **REMOVE POINTS FROM USER**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please send the username and points in this format:\n"
        "`@username 50`\n\n"
        "Or reply with /cancel to go back."
    )
    
    context.user_data['admin_action'] = 'points_remove'
    await query.edit_message_text(text, parse_mode='Markdown')


async def show_points_leaderboard(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show top users by points"""
    try:
        # Get top users from database
        conn = database.get_sync_connection()
        cursor = conn.execute(
            "SELECT user_id, points FROM users WHERE points > 0 ORDER BY points DESC LIMIT 10"
        )
        sorted_users = cursor.fetchall()
        conn.close()
        
        text = (
            "🏆 **TOP USERS LEADERBOARD**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )
        
        if sorted_users:
            for i, (user_id, points) in enumerate(sorted_users, 1):
                # Try to get username
                username = "Unknown"
                for uname, uid in username_to_id.items():
                    if uid == user_id:
                        username = f"@{uname}"
                        break
                
                medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
                text += f"{medal} {username}: **{points}** points\n"
        else:
            text += "_No users with points yet._\n"
        
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_points")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error showing leaderboard: {e}")
        await query.edit_message_text("❌ Error loading leaderboard!")


# ============================================================================
# TRUSTED SELLERS MANAGEMENT
# ============================================================================

async def show_sellers_menu(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show trusted sellers management menu"""
    text = (
        "⭐ **TRUSTED SELLERS MANAGEMENT**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**Current Trusted Sellers:** {len(trusted_sellers)}\n\n"
    )
    
    # Show list of trusted sellers
    if trusted_sellers:
        text += "**Current List:**\n"
        for username in list(trusted_sellers.keys())[:5]:
            text += f"✅ @{username}\n"
        
        if len(trusted_sellers) > 5:
            text += f"_...and {len(trusted_sellers) - 5} more_\n"
    else:
        text += "_No trusted sellers yet._\n"
    
    text += "\n**Select an action:**"
    
    keyboard = [
        [InlineKeyboardButton("➕ Add Trusted Seller", callback_data="seller_add")],
        [InlineKeyboardButton("✏️ Rename Seller Button", callback_data="seller_rename")],
        [InlineKeyboardButton("➖ Remove Trusted Seller", callback_data="seller_remove")],
        [InlineKeyboardButton("📋 View All Sellers", callback_data="seller_list")],
        [InlineKeyboardButton("🔍 Check Seller Status", callback_data="seller_check")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="admin_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def seller_add_start(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start process to add trusted seller"""
    text = (
        "➕ **ADD TRUSTED SELLER**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please send the username of the seller to add:\n"
        "`@username`\n\n"
        "Or reply with /cancel to go back."
    )
    
    context.user_data['admin_action'] = 'seller_add'
    await query.edit_message_text(text, parse_mode='Markdown')


async def seller_remove_start(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start process to remove trusted seller"""
    text = (
        "➖ **REMOVE TRUSTED SELLER**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please send the username of the seller to remove:\n"
        "`@username`\n\n"
        "Or reply with /cancel to go back."
    )
    
    context.user_data['admin_action'] = 'seller_remove'
    await query.edit_message_text(text, parse_mode='Markdown')


async def seller_rename_start(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start process to rename seller button (keeps votes!)"""
    text = (
        "✏️ **RENAME SELLER BUTTON**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Change the button text WITHOUT losing votes!\n\n"
        "Send in format:\n"
        "`@old_username @new_username`\n\n"
        "**Example:** `@johndoe @john_new`\n\n"
        "⚠️ This updates:\n"
        "• Voting button text in group\n"
        "• `/barygos` leaderboard display\n"
        "• Keeps ALL existing votes\n\n"
        "Or reply with /cancel to go back."
    )
    
    context.user_data['admin_action'] = 'seller_rename'
    await query.edit_message_text(text, parse_mode='Markdown')


async def show_all_sellers(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show complete list of trusted sellers"""
    text = (
        "📋 **ALL TRUSTED SELLERS**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    if trusted_sellers:
        for username, data in trusted_sellers.items():
            added_date = data.get('added_date', 'Unknown')
            text += f"✅ @{username}\n"
            text += f"   Added: {added_date}\n\n"
    else:
        text += "_No trusted sellers in the system._\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_sellers")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


# ============================================================================
# SCAMMER LIST MANAGEMENT
# ============================================================================

async def show_scammers_menu(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show scammer list management menu"""
    text = (
        "🚨 **SCAMMER LIST MANAGEMENT**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**Confirmed Scammers:** {len(confirmed_scammers)}\n"
        f"**Pending Reports:** {len(pending_scammer_reports)}\n\n"
    )
    
    # Show some recent scammers
    if confirmed_scammers:
        text += "**Recent Scammers:**\n"
        for username in list(confirmed_scammers.keys())[:5]:
            reports = len(confirmed_scammers[username].get('reports', []))
            text += f"🚫 @{username} ({reports} reports)\n"
        
        if len(confirmed_scammers) > 5:
            text += f"_...and {len(confirmed_scammers) - 5} more_\n"
    else:
        text += "_No confirmed scammers yet._\n"
    
    text += "\n**Select an action:**"
    
    keyboard = [
        [InlineKeyboardButton("➕ Add to Scammer List", callback_data="scammer_add")],
        [InlineKeyboardButton("➖ Remove from List", callback_data="scammer_remove")],
        [InlineKeyboardButton("📋 View All Scammers", callback_data="scammer_list")],
        [InlineKeyboardButton("🔍 Check User Status", callback_data="scammer_check")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="admin_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def scammer_add_start(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start process to add scammer"""
    text = (
        "➕ **ADD TO SCAMMER LIST**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please send the username and reason:\n"
        "`@username | Scammed user X for $100`\n\n"
        "Or reply with /cancel to go back."
    )
    
    context.user_data['admin_action'] = 'scammer_add'
    await query.edit_message_text(text, parse_mode='Markdown')


async def scammer_remove_start(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start process to remove scammer"""
    text = (
        "➖ **REMOVE FROM SCAMMER LIST**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Please send the username to remove:\n"
        "`@username`\n\n"
        "**Warning:** This will remove all reports for this user.\n\n"
        "Or reply with /cancel to go back."
    )
    
    context.user_data['admin_action'] = 'scammer_remove'
    await query.edit_message_text(text, parse_mode='Markdown')


async def show_all_scammers(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show complete list of confirmed scammers"""
    text = (
        "📋 **ALL CONFIRMED SCAMMERS**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    if confirmed_scammers:
        for username, data in list(confirmed_scammers.items())[:20]:
            reports = data.get('reports', [])
            text += f"🚫 @{username}\n"
            text += f"   Reports: {len(reports)}\n"
            if reports:
                text += f"   Latest: {reports[-1].get('reason', 'No reason')[:50]}\n"
            text += "\n"
        
        if len(confirmed_scammers) > 20:
            text += f"_...and {len(confirmed_scammers) - 20} more_\n"
    else:
        text += "_No confirmed scammers in the system._\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_scammers")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


# ============================================================================
# CLAIMS REVIEW SYSTEM
# ============================================================================

async def show_claims_menu(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show pending claims for review"""
    text = (
        "📋 **REVIEW PENDING CLAIMS**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**Pending Reports:** {len(pending_scammer_reports)}\n\n"
    )
    
    if pending_scammer_reports:
        text += "**Select a report to review:**\n\n"
        
        keyboard = []
        for report_id, report in list(pending_scammer_reports.items())[:10]:
            reported_user = report.get('reported_username', 'Unknown')
            reporter = report.get('reporter_username', 'Unknown')
            
            button_text = f"🔍 {reported_user} (by {reporter})"
            keyboard.append([InlineKeyboardButton(
                button_text,
                callback_data=f"claim_review_{report_id}"
            )])
        
        if len(pending_scammer_reports) > 10:
            text += f"_Showing 10 of {len(pending_scammer_reports)} reports_\n"
        
        keyboard.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="admin_main")])
    else:
        text += "✅ _No pending reports to review!_\n"
        keyboard = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="admin_main")]]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def show_claim_detail(query, context: ContextTypes.DEFAULT_TYPE, report_id: str) -> None:
    """Show detailed view of a specific claim"""
    if report_id not in pending_scammer_reports:
        await query.answer("❌ Report not found or already processed!")
        return
    
    report = pending_scammer_reports[report_id]
    
    text = (
        "🔍 **REPORT DETAILS**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**Report ID:** `{report_id}`\n"
        f"**Reported User:** @{report.get('reported_username', 'Unknown')}\n"
        f"**Reported By:** @{report.get('reporter_username', 'Unknown')}\n"
        f"**Date:** {report.get('timestamp', 'Unknown')}\n\n"
        f"**Reason:**\n{report.get('reason', 'No reason provided')}\n\n"
        "**Action Required:**"
    )
    
    keyboard = [
        [InlineKeyboardButton("✅ Confirm - Add to Scammer List", callback_data=f"claim_confirm_{report_id}")],
        [InlineKeyboardButton("❌ Dismiss - False Report", callback_data=f"claim_dismiss_{report_id}")],
        [InlineKeyboardButton("📝 Request More Info", callback_data=f"claim_info_{report_id}")],
        [InlineKeyboardButton("🔙 Back to Claims List", callback_data="admin_claims")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def confirm_claim(query, context: ContextTypes.DEFAULT_TYPE, report_id: str) -> None:
    """Confirm a claim and add user to scammer list"""
    if report_id not in pending_scammer_reports:
        await query.answer("❌ Report not found!")
        return
    
    report = pending_scammer_reports[report_id]
    username = report.get('reported_username')
    
    # Add to confirmed scammers
    if username not in confirmed_scammers:
        confirmed_scammers[username] = {
            'reports': [],
            'confirmed_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    
    # Add this report
    confirmed_scammers[username]['reports'].append(report)
    
    # Remove from pending
    del pending_scammer_reports[report_id]
    
    # Save data
    data_manager.save_data(confirmed_scammers, 'confirmed_scammers.pkl')
    data_manager.save_data(pending_scammer_reports, 'pending_scammer_reports.pkl')
    
    text = (
        "✅ **CLAIM CONFIRMED**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"User @{username} has been added to the scammer list.\n\n"
        f"**Total Reports:** {len(confirmed_scammers[username]['reports'])}\n"
        f"**Status:** Confirmed Scammer 🚫"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Claims", callback_data="admin_claims")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    await query.answer("✅ User added to scammer list!")


async def dismiss_claim(query, context: ContextTypes.DEFAULT_TYPE, report_id: str) -> None:
    """Dismiss a false report"""
    if report_id not in pending_scammer_reports:
        await query.answer("❌ Report not found!")
        return
    
    report = pending_scammer_reports[report_id]
    username = report.get('reported_username')
    
    # Remove from pending
    del pending_scammer_reports[report_id]
    
    # Save data
    data_manager.save_data(pending_scammer_reports, 'pending_scammer_reports.pkl')
    
    text = (
        "❌ **CLAIM DISMISSED**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Report against @{username} has been dismissed as false or insufficient evidence.\n\n"
        f"**Remaining Pending Reports:** {len(pending_scammer_reports)}"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Back to Claims", callback_data="admin_claims")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    await query.answer("❌ Report dismissed!")


# ============================================================================
# USER LOOKUP
# ============================================================================

async def show_lookup_menu(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show user lookup menu"""
    text = (
        "🔍 **USER LOOKUP**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Search for any user to see their complete profile:\n"
        "• Points balance\n"
        "• Trusted seller status\n"
        "• Scammer reports\n"
        "• Activity history\n\n"
        "Please send a username to lookup:\n"
        "`@username`\n\n"
        "Or reply with /cancel to go back."
    )
    
    context.user_data['admin_action'] = 'user_lookup'
    await query.edit_message_text(text, parse_mode='Markdown')


# ============================================================================
# STATISTICS DASHBOARD
# ============================================================================

async def show_statistics(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show detailed statistics dashboard"""
    stats = get_admin_stats()
    
    # Calculate additional stats
    avg_points = stats['total_points'] / max(stats['total_users'], 1)
    
    text = (
        "📊 **STATISTICS DASHBOARD**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "**Users & Points:**\n"
        f"👥 Total Users: {stats['total_users']}\n"
        f"💰 Total Points: {stats['total_points']}\n"
        f"📊 Average Points: {avg_points:.1f}\n\n"
        "**Trust System:**\n"
        f"⭐ Trusted Sellers: {stats['trusted_sellers']}\n"
        f"🚨 Confirmed Scammers: {stats['confirmed_scammers']}\n"
        f"⏳ Pending Reports: {stats['pending_reports']}\n\n"
        "**System Health:**\n"
        "✅ Database: Operational\n"
        "✅ Bot Status: Running\n"
        f"🕐 Uptime: Active\n"
    )
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("📥 Export Data", callback_data="admin_export")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="admin_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


# ============================================================================
# INPUT HANDLER FOR ADMIN ACTIONS
# ============================================================================

async def handle_admin_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text input for admin actions"""
    if not await is_admin(update, context):
        return
    
    action = context.user_data.get('admin_action')
    if not action:
        return
    
    text = update.message.text.strip()
    
    # Handle cancel
    if text.lower() == '/cancel':
        context.user_data.pop('admin_action', None)
        await update.message.reply_text("❌ Action cancelled.")
        return
    
    # Route to appropriate handler
    if action == 'points_add':
        await process_points_add(update, context, text)
    elif action == 'points_remove':
        await process_points_remove(update, context, text)
    elif action == 'seller_add':
        await process_seller_add(update, context, text)
    elif action == 'seller_remove':
        await process_seller_remove(update, context, text)
    elif action == 'seller_rename':
        await process_seller_rename(update, context, text)
    elif action == 'scammer_add':
        await process_scammer_add(update, context, text)
    elif action == 'scammer_remove':
        await process_scammer_remove(update, context, text)
    elif action == 'user_lookup':
        await process_user_lookup(update, context, text)
    
    # Clear action
    context.user_data.pop('admin_action', None)


async def process_points_add(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Process adding points to user"""
    try:
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text("❌ Invalid format. Use: `@username 100`", parse_mode='Markdown')
            return
        
        username = parts[0].lstrip('@')
        points = int(parts[1])
        
        if points <= 0:
            await update.message.reply_text("❌ Points must be positive!")
            return
        
        # Get or create user ID
        user_id = username_to_id.get(username)
        if not user_id:
            # Create new ID
            user_id = len(username_to_id) + 1000000
            username_to_id[username] = user_id
        
        # Add points to database
        current_points = get_user_points(user_id)
        new_balance = current_points + points
        update_user_points(user_id, new_balance)
        
        # Save username mapping
        data_manager.save_data(username_to_id, 'username_to_id.pkl')
        
        await update.message.reply_text(
            f"✅ **Points Added!**\n\n"
            f"User: @{username}\n"
            f"Added: +{points} points\n"
            f"New Balance: {new_balance} points",
            parse_mode='Markdown'
        )
        
    except ValueError:
        await update.message.reply_text("❌ Invalid number format!")
    except Exception as e:
        logger.error(f"Error adding points: {e}")
        await update.message.reply_text("❌ Error adding points. Please try again.")


async def process_points_remove(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Process removing points from user"""
    try:
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text("❌ Invalid format. Use: `@username 50`", parse_mode='Markdown')
            return
        
        username = parts[0].lstrip('@')
        points = int(parts[1])
        
        if points <= 0:
            await update.message.reply_text("❌ Points must be positive!")
            return
        
        user_id = username_to_id.get(username)
        if not user_id:
            await update.message.reply_text(f"❌ User @{username} not found!")
            return
        
        current_points = get_user_points(user_id)
        if current_points == 0:
            await update.message.reply_text(f"❌ User @{username} has no points!")
            return
        
        new_points = max(0, current_points - points)
        update_user_points(user_id, new_points)
        
        await update.message.reply_text(
            f"✅ **Points Removed!**\n\n"
            f"User: @{username}\n"
            f"Removed: -{points} points\n"
            f"New Balance: {new_points} points",
            parse_mode='Markdown'
        )
        
    except ValueError:
        await update.message.reply_text("❌ Invalid number format!")
    except Exception as e:
        logger.error(f"Error removing points: {e}")
        await update.message.reply_text("❌ Error removing points. Please try again.")


async def process_seller_add(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Process adding trusted seller"""
    username = text.lstrip('@').strip()
    
    if username in trusted_sellers:
        await update.message.reply_text(f"ℹ️ @{username} is already a trusted seller!")
        return
    
    # Add to trusted sellers
    trusted_sellers[username] = {
        'added_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'added_by': update.effective_user.username or str(update.effective_user.id)
    }
    
    # Save
    data_manager.save_data(trusted_sellers, 'trusted_sellers.pkl')
    
    await update.message.reply_text(
        f"✅ **Trusted Seller Added!**\n\n"
        f"@{username} is now a trusted seller ⭐",
        parse_mode='Markdown'
    )


async def process_seller_remove(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Process removing trusted seller"""
    username = text.lstrip('@').strip()
    
    if username not in trusted_sellers:
        await update.message.reply_text(f"❌ @{username} is not in the trusted sellers list!")
        return
    
    # Remove
    del trusted_sellers[username]
    
    # Save
    data_manager.save_data(trusted_sellers, 'trusted_sellers.pkl')
    
    await update.message.reply_text(
        f"✅ **Trusted Seller Removed!**\n\n"
        f"@{username} has been removed from trusted sellers.",
        parse_mode='Markdown'
    )


async def process_seller_rename(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Process renaming seller button (keeps all votes!)"""
    try:
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text("❌ Invalid format. Use: `@old_username @new_username`", parse_mode='Markdown')
            return
        
        old_username = parts[0].lstrip('@').strip()
        new_username = parts[1].lstrip('@').strip()
        
        if not old_username or not new_username:
            await update.message.reply_text("❌ Both usernames are required!")
            return
        
        if old_username not in trusted_sellers:
            await update.message.reply_text(f"❌ @{old_username} is not in the trusted sellers list!")
            return
        
        if new_username in trusted_sellers and new_username != old_username:
            await update.message.reply_text(f"❌ @{new_username} is already in the trusted sellers list!")
            return
        
        # Load voting data from voting.py
        import voting
        
        # Transfer votes from old name to new name
        # Weekly votes
        if old_username in voting.votes_weekly:
            voting.votes_weekly[new_username] = voting.votes_weekly.pop(old_username, 0)
        
        # Monthly votes
        if old_username in voting.votes_monthly:
            voting.votes_monthly[new_username] = voting.votes_monthly.pop(old_username, [])
        
        # All-time votes
        if old_username in voting.votes_alltime:
            voting.votes_alltime[new_username] = voting.votes_alltime.pop(old_username, 0)
        
        # Vote history
        if old_username in voting.vote_history:
            voting.vote_history[new_username] = voting.vote_history.pop(old_username, [])
        
        # Update trusted sellers list
        if old_username in trusted_sellers:
            seller_data = trusted_sellers.pop(old_username, None)
            if seller_data:
                trusted_sellers[new_username] = seller_data
            else:
                # It was a simple list, just add the new username
                trusted_sellers[new_username] = {"added_date": datetime.now().strftime("%Y-%m-%d")}
        
        # Save all changes
        data_manager.save_data(voting.votes_weekly, 'votes_weekly.pkl')
        data_manager.save_data(voting.votes_monthly, 'votes_monthly.pkl')
        data_manager.save_data(voting.votes_alltime, 'votes_alltime.pkl')
        data_manager.save_data(voting.vote_history, 'vote_history.pkl')
        data_manager.save_data(trusted_sellers, 'trusted_sellers.pkl')
        data_manager.save_data(voting.trusted_sellers, 'trusted_sellers.pkl')  # voting.py also has this
        
        # Get vote counts for confirmation
        weekly_votes = voting.votes_weekly.get(new_username, 0)
        alltime_votes = voting.votes_alltime.get(new_username, 0)
        
        await update.message.reply_text(
            f"✅ **Seller Renamed Successfully!**\n\n"
            f"Old name: @{old_username}\n"
            f"New name: @{new_username}\n\n"
            f"📊 **Votes Preserved:**\n"
            f"• Weekly: {weekly_votes}\n"
            f"• All-time: {alltime_votes}\n\n"
            f"⚠️ **Important:** Run `/updatevoting` in voting group to update buttons!",
            parse_mode='Markdown'
        )
        
    except Exception as e:
        logger.error(f"Error renaming seller: {e}")
        await update.message.reply_text("❌ Error renaming seller. Please try again.")


async def process_scammer_add(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Process adding user to scammer list"""
    parts = text.split('|', 1)
    if len(parts) != 2:
        await update.message.reply_text("❌ Invalid format. Use: `@username | reason`", parse_mode='Markdown')
        return
    
    username = parts[0].strip().lstrip('@')
    reason = parts[1].strip()
    
    # Add to confirmed scammers
    if username not in confirmed_scammers:
        confirmed_scammers[username] = {
            'reports': [],
            'confirmed_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    
    confirmed_scammers[username]['reports'].append({
        'reason': reason,
        'reporter_username': update.effective_user.username,
        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'added_by_admin': True
    })
    
    # Save
    data_manager.save_data(confirmed_scammers, 'confirmed_scammers.pkl')
    
    await update.message.reply_text(
        f"✅ **Added to Scammer List!**\n\n"
        f"@{username} has been added to the scammer list 🚫\n"
        f"Total Reports: {len(confirmed_scammers[username]['reports'])}",
        parse_mode='Markdown'
    )


async def process_scammer_remove(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Process removing user from scammer list"""
    username = text.lstrip('@').strip()
    
    if username not in confirmed_scammers:
        await update.message.reply_text(f"❌ @{username} is not in the scammer list!")
        return
    
    # Remove
    del confirmed_scammers[username]
    
    # Save
    data_manager.save_data(confirmed_scammers, 'confirmed_scammers.pkl')
    
    await update.message.reply_text(
        f"✅ **Removed from Scammer List!**\n\n"
        f"@{username} has been removed from the scammer list.\n"
        f"All reports have been cleared.",
        parse_mode='Markdown'
    )


async def process_user_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Process user lookup request"""
    username = text.lstrip('@').strip()
    
    # Gather all info
    user_id = username_to_id.get(username)
    points = user_points.get(user_id, 0) if user_id else 0
    is_trusted = username in trusted_sellers
    is_scammer = username in confirmed_scammers
    scammer_reports = len(confirmed_scammers.get(username, {}).get('reports', []))
    
    status_emoji = "✅" if is_trusted else "🚫" if is_scammer else "➖"
    
    response = (
        f"👤 **USER PROFILE: @{username}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**Status:** {status_emoji}\n"
    )
    
    if is_trusted:
        response += f"⭐ **Trusted Seller**\n"
    elif is_scammer:
        response += f"🚫 **Confirmed Scammer**\n"
        response += f"📋 Reports: {scammer_reports}\n"
    else:
        response += f"➖ Regular User\n"
    
    response += f"\n💰 **Points:** {points}\n"
    
    if user_id:
        response += f"🆔 **ID:** `{user_id}`\n"
    
    await update.message.reply_text(response, parse_mode='Markdown')


# Export all handler functions
__all__ = [
    'show_admin_panel',
    'show_points_menu',
    'show_sellers_menu',
    'show_scammers_menu',
    'show_claims_menu',
    'show_lookup_menu',
    'show_statistics',
    'handle_admin_input',
    'points_add_start',
    'points_remove_start',
    'show_points_leaderboard',
    'seller_add_start',
    'seller_remove_start',
    'show_all_sellers',
    'scammer_add_start',
    'scammer_remove_start',
    'show_all_scammers',
    'show_claim_detail',
    'confirm_claim',
    'dismiss_claim'
]

