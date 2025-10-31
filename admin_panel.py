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
from config import ADMIN_CHAT_ID

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
    """Show main admin panel menu - only bot owner can access"""
    user_id = update.effective_user.id
    
    # Only bot owner can access admin panel
    if user_id != ADMIN_CHAT_ID:
        await update.message.reply_text("❌ Only bot owner can access the admin panel!")
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
        [InlineKeyboardButton("📈 Barygos Auto-Post", callback_data="admin_barygos_auto")],
        [InlineKeyboardButton("👥 Helpers", callback_data="admin_helpers")],
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
    
    # Show list of trusted sellers (handle both list and dict formats)
    if trusted_sellers:
        text += "**Current List:**\n"
        # Handle both list and dict formats
        if isinstance(trusted_sellers, dict):
            seller_list = list(trusted_sellers.keys())[:5]
        else:
            seller_list = list(trusted_sellers)[:5]
        
        for username in seller_list:
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
    """Start process to remove trusted seller - shows all sellers as buttons"""
    text = (
        "➖ **REMOVE TRUSTED SELLER**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Click on a seller below to remove them:\n\n"
    )
    
    # Build keyboard with all sellers
    keyboard = []
    
    if trusted_sellers:
        # Handle both list and dict formats
        seller_list = list(trusted_sellers.keys()) if isinstance(trusted_sellers, dict) else list(trusted_sellers)
        
        # Add button for each seller
        for seller in seller_list:
            seller_display = seller[1:] if seller.startswith('@') else seller
            keyboard.append([InlineKeyboardButton(f"❌ Remove @{seller_display}", callback_data=f"seller_remove_confirm_{seller}")])
        
        text += f"**Total Sellers:** {len(seller_list)}\n\n"
        text += "_Click a seller to remove them_"
    else:
        text += "_No trusted sellers to remove_"
    
    # Add finish button at the bottom
    keyboard.append([InlineKeyboardButton("✅ Finish", callback_data="seller_manage")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


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
        # Handle both list and dict formats
        if isinstance(trusted_sellers, dict):
            for username, data in trusted_sellers.items():
                if isinstance(data, dict):
                    added_date = data.get('added_date', 'Unknown')
                else:
                    added_date = 'Unknown'
                text += f"✅ @{username}\n"
                text += f"   Added: {added_date}\n\n"
        else:
            # It's a list
            for username in trusted_sellers:
                text += f"✅ @{username}\n\n"
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
        "➖ PAŠALINTI IŠ VAGIŲ SĄRAŠO\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Įveskite vartotojo vardą:\n"
        "`@username`\n\n"
        "⚠️ **DĖMESIO:** Tai pašalins visus pranešimus apie šį vartotoją.\n"
        "Naudokite tik jei vartotojas buvo klaidingai pažymėtas.\n\n"
        "Arba atsakykite /cancel kad grįžti."
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
        await query.answer("❌ Pranešimas nerastas!")
        return
    
    report = pending_scammer_reports[report_id]
    username = report.get('reported_username')
    reporter_id = report.get('reporter_id')
    
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
    
    # Notify reporter about confirmation
    try:
        await context.bot.send_message(
            chat_id=reporter_id,
            text=f"✅ Jūsų pranešimas patvirtintas\n\n"
                 f"@{username} pridėtas į vagių sąrašą."
        )
    except Exception as e:
        logger.error(f"Failed to notify reporter {reporter_id}: {e}")
    
    # Answer callback and show updated claims list
    await query.answer("✅ Vagis patvirtintas!")
    
    # Redirect to updated claims list
    await show_claims_menu(query, context)


async def dismiss_claim(query, context: ContextTypes.DEFAULT_TYPE, report_id: str) -> None:
    """Dismiss a false report"""
    if report_id not in pending_scammer_reports:
        await query.answer("❌ Pranešimas nerastas!")
        return
    
    report = pending_scammer_reports[report_id]
    username = report.get('reported_username')
    reporter_id = report.get('reporter_id')
    
    # Remove from pending
    del pending_scammer_reports[report_id]
    
    # Save data
    data_manager.save_data(pending_scammer_reports, 'pending_scammer_reports.pkl')
    
    # Notify reporter about dismissal
    try:
        await context.bot.send_message(
            chat_id=reporter_id,
            text=f"❌ Jūsų pranešimas atmestas\n\n"
                 f"Pranešimas apie @{username} atmestas dėl nepakankamų įrodymų."
        )
    except Exception as e:
        logger.error(f"Failed to notify reporter {reporter_id}: {e}")
    
    # Answer callback and show updated claims list
    await query.answer("❌ Pranešimas atmestas!")
    
    # Redirect to updated claims list
    await show_claims_menu(query, context)


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
# SETTINGS MENU
# ============================================================================

async def show_settings_menu(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show admin settings menu"""
    # Import withdrawals_enabled from payments
    import payments
    
    withdrawal_status = "✅ ĮJUNGTI" if payments.withdrawals_enabled else "🚫 IŠJUNGTI"
    withdrawal_emoji = "✅" if payments.withdrawals_enabled else "🚫"
    
    text = (
        "⚙️ **SETTINGS**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "Manage bot settings and configurations.\n\n"
        f"**Withdrawal Status:** {withdrawal_status}\n\n"
        "Select an option below:"
    )
    
    keyboard = [
        [InlineKeyboardButton(f"{withdrawal_emoji} Toggle Withdrawals", callback_data="settings_toggle_withdrawals")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="admin_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')


async def toggle_withdrawals_setting(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle withdrawal enable/disable"""
    import payments
    
    # Toggle the setting
    payments.withdrawals_enabled = not payments.withdrawals_enabled
    data_manager.save_data(payments.withdrawals_enabled, 'withdrawals_enabled.pkl')
    
    status = "✅ ĮJUNGTI" if payments.withdrawals_enabled else "🚫 IŠJUNGTI"
    
    # Show confirmation
    await query.answer(f"Išėmimai dabar {status}")
    
    # Refresh settings menu
    await show_settings_menu(query, context)
    
    logger.info(f"Withdrawals toggled via admin panel: {payments.withdrawals_enabled}")


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
    elif action == 'barygos_voting_link':
        await process_barygos_voting_link(update, context, text)
    
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
    
    # Add to trusted sellers (handle both list and dict)
    if isinstance(trusted_sellers, dict):
        trusted_sellers[username] = {
            'added_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'added_by': update.effective_user.username or str(update.effective_user.id)
        }
    else:
        trusted_sellers.append(username)
    
    # Save
    data_manager.save_data(trusted_sellers, 'trusted_sellers.pkl')
    
    await update.message.reply_text(
        f"✅ **Trusted Seller Added!**\n\n"
        f"@{username} is now a trusted seller ⭐",
        parse_mode='Markdown'
    )


async def seller_remove_confirm(query, context: ContextTypes.DEFAULT_TYPE, seller_username: str) -> None:
    """Remove a trusted seller and show updated list"""
    # Normalize: check both with and without @ symbol
    username_with_at = seller_username if seller_username.startswith('@') else f'@{seller_username}'
    username_without_at = seller_username.lstrip('@')
    
    # Find which format is used in the list
    actual_username = None
    if username_with_at in trusted_sellers:
        actual_username = username_with_at
    elif username_without_at in trusted_sellers:
        actual_username = username_without_at
    
    if not actual_username:
        await query.answer(f"❌ Seller not found!")
        return
    
    # Remove (handle both list and dict)
    if isinstance(trusted_sellers, dict):
        del trusted_sellers[actual_username]
    else:
        trusted_sellers.remove(actual_username)
    
    # Save
    data_manager.save_data(trusted_sellers, 'trusted_sellers.pkl')
    
    # Update voting buttons in voting group
    import voting
    try:
        await voting.update_voting_message(context)
    except Exception as e:
        logger.error(f"Failed to update voting message: {e}")
    
    # Show success and updated list
    await query.answer(f"✅ Removed @{username_without_at}")
    
    # Show updated seller removal interface
    await seller_remove_start(query, context)


async def process_seller_remove(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Process removing trusted seller (legacy text input - kept for compatibility)"""
    username = text.strip()
    
    # Normalize: check both with and without @ symbol
    username_with_at = username if username.startswith('@') else f'@{username}'
    username_without_at = username.lstrip('@')
    
    # Find which format is used in the list
    actual_username = None
    if username_with_at in trusted_sellers:
        actual_username = username_with_at
    elif username_without_at in trusted_sellers:
        actual_username = username_without_at
    
    if not actual_username:
        await update.message.reply_text(f"❌ {username_with_at} is not in the trusted sellers list!")
        return
    
    # Remove (handle both list and dict)
    if isinstance(trusted_sellers, dict):
        del trusted_sellers[actual_username]
    else:
        trusted_sellers.remove(actual_username)
    
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
        
        old_input = parts[0].strip()
        new_input = parts[1].strip()
        
        # Normalize: check both with and without @ symbol for old username
        old_with_at = old_input if old_input.startswith('@') else f'@{old_input}'
        old_without_at = old_input.lstrip('@')
        
        # Find which format is used in the list for old username
        old_username = None
        if old_with_at in trusted_sellers:
            old_username = old_with_at
        elif old_without_at in trusted_sellers:
            old_username = old_without_at
        
        if not old_username:
            await update.message.reply_text(f"❌ {old_with_at} is not in the trusted sellers list!")
            return
        
        # Determine format for new username (match the format of the list)
        # If old username has @, new username should have @ too
        if old_username.startswith('@'):
            new_username = new_input if new_input.startswith('@') else f'@{new_input}'
        else:
            new_username = new_input.lstrip('@')
        
        # Check if new username already exists
        new_with_at = new_username if new_username.startswith('@') else f'@{new_username}'
        new_without_at = new_username.lstrip('@')
        
        if (new_with_at in trusted_sellers or new_without_at in trusted_sellers) and new_username != old_username:
            await update.message.reply_text(f"❌ {new_with_at} is already in the trusted sellers list!")
            return
        
        # Load voting data from voting.py
        import voting
        
        # Transfer votes from old name to new name (check both formats)
        # Weekly votes
        for old_format in [old_username, old_with_at, old_without_at]:
            if old_format in voting.votes_weekly:
                voting.votes_weekly[new_username] = voting.votes_weekly.pop(old_format, 0)
                break
        
        # Monthly votes
        for old_format in [old_username, old_with_at, old_without_at]:
            if old_format in voting.votes_monthly:
                voting.votes_monthly[new_username] = voting.votes_monthly.pop(old_format, [])
                break
        
        # All-time votes
        for old_format in [old_username, old_with_at, old_without_at]:
            if old_format in voting.votes_alltime:
                voting.votes_alltime[new_username] = voting.votes_alltime.pop(old_format, 0)
                break
        
        # Vote history
        for old_format in [old_username, old_with_at, old_without_at]:
            if old_format in voting.vote_history:
                voting.vote_history[new_username] = voting.vote_history.pop(old_format, [])
                break
        
        # Update trusted sellers list (handle both list and dict)
        if isinstance(trusted_sellers, dict):
            # It's a dict
            if old_username in trusted_sellers:
                seller_data = trusted_sellers.pop(old_username, None)
                if isinstance(seller_data, dict):
                    trusted_sellers[new_username] = seller_data
                else:
                    trusted_sellers[new_username] = {"added_date": datetime.now().strftime("%Y-%m-%d")}
        else:
            # It's a list - convert to dict with new username
            if old_username in trusted_sellers:
                trusted_sellers.remove(old_username)
                if new_username not in trusted_sellers:
                    trusted_sellers.append(new_username)
        
        # Update voting.py's module-level trusted_sellers BEFORE saving
        # (both admin_panel.py and voting.py need the same updated list)
        voting.trusted_sellers = trusted_sellers
        
        # Save all changes (save once, not twice!)
        data_manager.save_data(voting.votes_weekly, 'votes_weekly.pkl')
        data_manager.save_data(voting.votes_monthly, 'votes_monthly.pkl')
        data_manager.save_data(voting.votes_alltime, 'votes_alltime.pkl')
        data_manager.save_data(voting.vote_history, 'vote_history.pkl')
        data_manager.save_data(trusted_sellers, 'trusted_sellers.pkl')  # Save updated list
        
        # Get vote counts for confirmation
        weekly_votes = voting.votes_weekly.get(new_username, 0)
        alltime_votes = voting.votes_alltime.get(new_username, 0)
        
        # Automatically update voting buttons
        try:
            await voting.update_voting_message(context)
            button_status = "✅ Voting buttons updated automatically!"
        except Exception as e:
            logger.error(f"Failed to auto-update voting buttons: {e}")
            button_status = "⚠️ Run `/updatevoting` in voting group to update buttons manually"
        
        await update.message.reply_text(
            f"✅ **Seller Renamed Successfully!**\n\n"
            f"Old name: {old_with_at}\n"
            f"New name: {new_with_at}\n\n"
            f"📊 **Votes Preserved:**\n"
            f"• Weekly: {weekly_votes}\n"
            f"• All-time: {alltime_votes}\n\n"
            f"{button_status}",
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
        await update.message.reply_text(f"❌ @{username} nėra vagių sąraše!")
        return
    
    # Get report count before removing
    reports_count = len(confirmed_scammers[username].get('reports', []))
    
    # Remove
    del confirmed_scammers[username]
    
    # Save
    data_manager.save_data(confirmed_scammers, 'confirmed_scammers.pkl')
    
    await update.message.reply_text(
        f"✅ Pašalinta iš vagių sąrašo\n\n"
        f"@{username} pašalintas iš vagių sąrašo.\n"
        f"Visi pranešimai ({reports_count}) ištrinti."
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


# ============================================================================
# BARYGOS AUTO-POST HANDLERS
# ============================================================================

async def show_barygos_auto_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show barygos auto-post settings"""
    import json
    from database import database
    
    settings = database.get_barygos_auto_settings()
    enabled = settings.get('enabled', 0)
    interval_hours = settings.get('interval_hours', 2)
    target_groups_json = settings.get('target_groups', '[]')
    voting_group_link = settings.get('voting_group_link', '')
    
    try:
        target_groups = json.loads(target_groups_json)
    except:
        target_groups = []
    
    status_emoji = "✅" if enabled else "🚫"
    status_text = "Enabled" if enabled else "Disabled"
    
    # Format interval display
    if interval_hours < 1:
        interval_display = f"{int(interval_hours * 60)} minutes"
    else:
        interval_display = f"{int(interval_hours)} hours"
    
    # Format voting link display
    if voting_group_link:
        link_display = f"✅ Set ({voting_group_link[:30]}...)" if len(voting_group_link) > 30 else f"✅ Set"
    else:
        link_display = "❌ Not set"
    
    text = (
        "📈 **BARYGOS AUTO-POST**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"**Status:** {status_emoji} {status_text}\n"
        f"**Interval:** Every {interval_display}\n"
        f"**Target Groups:** {len(target_groups)} selected\n"
        f"**Voting Button:** {link_display}\n\n"
        "Automatically posts /barygos leaderboard\n"
        "to selected groups at set intervals.\n\n"
        "**Select an action:**"
    )
    
    keyboard = [
        [InlineKeyboardButton(f"{'🚫 Disable' if enabled else '✅ Enable'}", callback_data="admin_barygos_auto_toggle")],
        [InlineKeyboardButton("⏰ Set Interval", callback_data="admin_barygos_auto_interval")],
        [InlineKeyboardButton("📍 Select Groups", callback_data="admin_barygos_auto_groups")],
        [InlineKeyboardButton("🗳️ Set Voting Link", callback_data="admin_barygos_auto_voting_link")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_main")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    try:
        await update.callback_query.edit_message_text(
            text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    except Exception as e:
        # Silently ignore "Message is not modified" errors
        if "Message is not modified" not in str(e):
            raise


async def handle_barygos_auto_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Toggle barygos auto-post on/off"""
    from database import database
    import recurring_messages_grouphelp
    
    settings = database.get_barygos_auto_settings()
    current_enabled = settings.get('enabled', 0)
    new_enabled = 0 if current_enabled else 1
    
    # Update database
    database.update_barygos_auto_settings(
        enabled=new_enabled,
        interval_hours=settings.get('interval_hours', 2),
        target_groups=settings.get('target_groups', '[]'),
        voting_group_link=settings.get('voting_group_link', '')
    )
    
    # Schedule or stop the job
    if new_enabled:
        recurring_messages_grouphelp.schedule_barygos_auto_job()
        status = "✅ Enabled"
    else:
        recurring_messages_grouphelp.stop_barygos_auto_job()
        status = "🚫 Disabled"
    
    await update.callback_query.answer(f"Barygos auto-post {status}!", show_alert=True)
    
    # Refresh the settings screen
    await show_barygos_auto_settings(update, context)


async def show_barygos_auto_interval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show interval selection menu"""
    text = (
        "⏰ **SELECT INTERVAL**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "How often should the barygos leaderboard\n"
        "be posted automatically?\n\n"
        "**Choose interval:**"
    )
    
    keyboard = [
        [InlineKeyboardButton("5 Minutes (Test)", callback_data="admin_barygos_auto_interval_0")],
        [InlineKeyboardButton("1 Hour", callback_data="admin_barygos_auto_interval_1")],
        [InlineKeyboardButton("2 Hours", callback_data="admin_barygos_auto_interval_2")],
        [InlineKeyboardButton("4 Hours", callback_data="admin_barygos_auto_interval_4")],
        [InlineKeyboardButton("6 Hours", callback_data="admin_barygos_auto_interval_6")],
        [InlineKeyboardButton("12 Hours", callback_data="admin_barygos_auto_interval_12")],
        [InlineKeyboardButton("24 Hours", callback_data="admin_barygos_auto_interval_24")],
        [InlineKeyboardButton("🔙 Back", callback_data="admin_barygos_auto")]
    ]
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def handle_barygos_auto_interval_set(update: Update, context: ContextTypes.DEFAULT_TYPE, hours: int) -> None:
    """Set the interval for barygos auto-post"""
    from database import database
    import recurring_messages_grouphelp
    
    settings = database.get_barygos_auto_settings()
    
    # Convert 0 to 5 minutes (1/12 hour)
    actual_hours = 5/60 if hours == 0 else hours
    display_text = "5 minutes" if hours == 0 else f"{hours} hours"
    
    # Update database
    database.update_barygos_auto_settings(
        enabled=settings.get('enabled', 0),
        interval_hours=actual_hours,
        target_groups=settings.get('target_groups', '[]'),
        voting_group_link=settings.get('voting_group_link', '')
    )
    
    # Reschedule if enabled
    if settings.get('enabled', 0):
        recurring_messages_grouphelp.schedule_barygos_auto_job()
    
    await update.callback_query.answer(f"Interval set to {display_text}!", show_alert=True)
    
    # Go back to settings
    await show_barygos_auto_settings(update, context)


async def show_barygos_auto_groups(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show group selection menu"""
    import json
    from database import database
    
    # Get all groups from database (groups where bot is admin)
    all_groups = database.get_all_groups()
    
    settings = database.get_barygos_auto_settings()
    try:
        selected_groups = json.loads(settings.get('target_groups', '[]'))
    except:
        selected_groups = []
    
    # Build text based on whether we have groups
    if all_groups:
        text = (
            "📍 **SELECT GROUPS**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Selected: {len(selected_groups)}/{len(all_groups)}\n\n"
            "Click groups to toggle selection:\n"
        )
    else:
        text = (
            "📍 **SELECT GROUPS**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"Selected: {len(selected_groups)} manually added\n\n"
            "⚠️ No auto-detected groups.\n\n"
            "**To add manually:**\n"
            "Use /barygos command in target group,\n"
            "then get chat ID from bot logs.\n"
            "Or play a game in the group first.\n"
        )
    
    keyboard = []
    
    # Show detected groups
    for group in all_groups[:10]:  # Limit to 10 groups to avoid huge menus
        chat_id = group.get('chat_id')
        title = group.get('title', f'Group {chat_id}')
        is_selected = chat_id in selected_groups
        checkbox = "✅" if is_selected else "⬜"
        keyboard.append([InlineKeyboardButton(
            f"{checkbox} {title[:30]}",
            callback_data=f"admin_barygos_auto_group_toggle_{chat_id}"
        )])
    
    # Show manually selected groups that aren't in the detected list
    detected_ids = [g['chat_id'] for g in all_groups]
    for chat_id in selected_groups:
        if chat_id not in detected_ids:
            keyboard.append([InlineKeyboardButton(
                f"✅ Manual: {chat_id}",
                callback_data=f"admin_barygos_auto_group_toggle_{chat_id}"
            )])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_barygos_auto")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def handle_barygos_auto_group_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """Toggle group selection"""
    import json
    from database import database
    
    settings = database.get_barygos_auto_settings()
    try:
        selected_groups = json.loads(settings.get('target_groups', '[]'))
    except:
        selected_groups = []
    
    # Toggle selection
    if chat_id in selected_groups:
        selected_groups.remove(chat_id)
        action = "removed from"
    else:
        selected_groups.append(chat_id)
        action = "added to"
    
    # Update database
    database.update_barygos_auto_settings(
        enabled=settings.get('enabled', 0),
        interval_hours=settings.get('interval_hours', 2),
        target_groups=json.dumps(selected_groups),
        voting_group_link=settings.get('voting_group_link', '')
    )
    
    await update.callback_query.answer(f"Group {action} selection!", show_alert=False)
    
    # Refresh the group selection screen
    await show_barygos_auto_groups(update, context)


async def show_barygos_auto_voting_link(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show interface to set voting group link"""
    from database import database
    
    settings = database.get_barygos_auto_settings()
    current_link = settings.get('voting_group_link', '')
    
    text = (
        "🗳️ **SET VOTING BUTTON LINK**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    )
    
    if current_link:
        text += f"**Current Link:**\n`{current_link}`\n\n"
    else:
        text += "**Current Link:** Not set\n\n"
    
    text += (
        "This button will appear under the barygos\n"
        "leaderboard when auto-posted to groups.\n\n"
        "**Send the voting group link:**\n"
        "Example: `https://t.me/yourgroup`\n\n"
        "Or send `/remove` to remove the button.\n"
        "Or send `/cancel` to go back."
    )
    
    context.user_data['admin_action'] = 'barygos_voting_link'
    
    await update.callback_query.edit_message_text(text, parse_mode='Markdown')


async def process_barygos_voting_link(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Process voting link input"""
    from database import database
    
    settings = database.get_barygos_auto_settings()
    
    # Check if user wants to remove the link
    if text.strip().lower() == '/remove':
        voting_link = ''
        message = "✅ **Voting button removed!**\n\nThe barygos auto-post will no longer show a voting button."
    else:
        # Validate URL format
        if not text.startswith(('http://', 'https://', 't.me/')):
            await update.message.reply_text(
                "❌ Invalid link format!\n\n"
                "Please send a valid Telegram link:\n"
                "`https://t.me/yourgroup`",
                parse_mode='Markdown'
            )
            return
        
        voting_link = text.strip()
        message = f"✅ **Voting button link set!**\n\n**Link:** `{voting_link}`\n\nUsers will see this button under the barygos leaderboard."
    
    # Update database
    database.update_barygos_auto_settings(
        enabled=settings.get('enabled', 0),
        interval_hours=settings.get('interval_hours', 2),
        target_groups=settings.get('target_groups', '[]'),
        voting_group_link=voting_link
    )
    
    await update.message.reply_text(message, parse_mode='Markdown')


# ============================================================================
# HELPERS MANAGEMENT
# ============================================================================

async def show_helpers_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show group selection for helpers management"""
    
    # Get all groups with helpers
    try:
        conn = database.get_sync_connection()
        try:
            cursor = conn.execute('''
                SELECT DISTINCT chat_id, COUNT(user_id) as helper_count
                FROM helpers
                GROUP BY chat_id
                ORDER BY helper_count DESC
            ''')
            groups_with_helpers = cursor.fetchall()
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error getting groups: {e}")
        groups_with_helpers = []
    
    if not groups_with_helpers:
        text = (
            "👥 **HELPERS MANAGEMENT**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "No helpers added in any group.\n\n"
            "To add helpers, go to a group and use:\n"
            "/addhelper @username"
        )
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_main")]]
    else:
        text = (
            "👥 **HELPERS MANAGEMENT**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Select a group to manage helpers:\n\n"
            f"Total Groups: {len(groups_with_helpers)}"
        )
        
        keyboard = []
        for chat_id, helper_count in groups_with_helpers[:10]:  # Limit to 10 groups
            # Try to get group title
            try:
                conn = database.get_sync_connection()
                cursor = conn.execute('SELECT title FROM groups WHERE chat_id = ?', (chat_id,))
                row = cursor.fetchone()
                conn.close()
                group_title = row[0] if row else f"Group {chat_id}"
            except:
                group_title = f"Group {chat_id}"
            
            button_text = f"📍 {group_title} ({helper_count} helpers)"
            keyboard.append([InlineKeyboardButton(
                button_text,
                callback_data=f"admin_helpers_group_{chat_id}"
            )])
        
        keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_main")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def show_helpers_for_group(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    """Show list of helpers for a specific group"""
    
    # Get all helpers for this chat
    try:
        conn = database.get_sync_connection()
        try:
            cursor = conn.execute('''
                SELECT user_id, username, permissions, added_at
                FROM helpers
                WHERE chat_id = ?
                ORDER BY added_at DESC
            ''', (chat_id,))
            helpers = cursor.fetchall()
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error getting helpers: {e}")
        helpers = []
    
    # Get group title
    try:
        conn = database.get_sync_connection()
        cursor = conn.execute('SELECT title FROM groups WHERE chat_id = ?', (chat_id,))
        row = cursor.fetchone()
        conn.close()
        group_title = row[0] if row else f"Group {chat_id}"
    except:
        group_title = f"Group {chat_id}"
    
    text = (
        f"👥 **HELPERS: {group_title}**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"Total Helpers: {len(helpers)}\n\n"
        "Click a helper to manage permissions:"
    )
    
    keyboard = []
    for helper in helpers[:10]:  # Limit to 10 for UI
        user_id, username, permissions, added_at = helper
        perms = permissions.split(',') if permissions else []
        perm_count = len(perms)
        
        # Show permission count
        button_text = f"👤 @{username} ({perm_count} perms)"
        keyboard.append([InlineKeyboardButton(
            button_text,
            callback_data=f"admin_helper_{chat_id}_{user_id}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Groups", callback_data="admin_helpers")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def show_helper_detail(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    """Show detailed permissions for a specific helper"""
    
    # Get helper info
    try:
        conn = database.get_sync_connection()
        try:
            cursor = conn.execute('''
                SELECT username, permissions, added_by, added_at
                FROM helpers
                WHERE chat_id = ? AND user_id = ?
            ''', (chat_id, user_id))
            helper = cursor.fetchone()
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error getting helper: {e}")
        helper = None
    
    if not helper:
        await update.callback_query.answer("❌ Helper not found!")
        await show_helpers_list(update, context)
        return
    
    username, permissions, added_by, added_at = helper
    perms = permissions.split(',') if permissions else []
    
    # Build permission status text
    all_permissions = ['ban', 'mute', 'warn', 'delete']
    perm_status = []
    for perm in all_permissions:
        if perm in perms:
            perm_status.append(f"✅ {perm.capitalize()}")
        else:
            perm_status.append(f"❌ {perm.capitalize()}")
    
    text = (
        f"👤 **HELPER: @{username}**\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🆔 User ID: {user_id}\n"
        f"📅 Added: {added_at[:10]}\n\n"
        "**Permissions:**\n"
        + "\n".join(perm_status) + "\n\n"
        "Click to toggle permissions:"
    )
    
    keyboard = []
    for perm in all_permissions:
        if perm in perms:
            button_text = f"✅ {perm.capitalize()}"
        else:
            button_text = f"❌ {perm.capitalize()}"
        
        keyboard.append([InlineKeyboardButton(
            button_text,
            callback_data=f"admin_helper_perm_{chat_id}_{user_id}_{perm}"
        )])
    
    keyboard.append([
        InlineKeyboardButton("🗑️ Remove Helper", callback_data=f"admin_helper_remove_{chat_id}_{user_id}")
    ])
    keyboard.append([
        InlineKeyboardButton("🔙 Back to Helpers", callback_data=f"admin_helpers_group_{chat_id}")
    ])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.callback_query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode='Markdown'
    )


async def toggle_helper_permission(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, permission: str) -> None:
    """Toggle a specific permission for a helper"""
    
    try:
        conn = database.get_sync_connection()
        try:
            # Get current permissions
            cursor = conn.execute(
                "SELECT permissions FROM helpers WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            row = cursor.fetchone()
            
            if not row:
                await update.callback_query.answer("❌ Helper not found!")
                return
            
            current_perms = row[0].split(',') if row[0] else []
            
            # Toggle permission
            if permission in current_perms:
                current_perms.remove(permission)
                action = "removed"
            else:
                current_perms.append(permission)
                action = "added"
            
            # Update database
            new_perms = ','.join(current_perms)
            conn.execute(
                "UPDATE helpers SET permissions = ? WHERE chat_id = ? AND user_id = ?",
                (new_perms, chat_id, user_id)
            )
            conn.commit()
            
            await update.callback_query.answer(f"✅ Permission {permission} {action}!")
            
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error toggling permission: {e}")
        await update.callback_query.answer("❌ Error updating permission!")
        return
    
    # Refresh the helper detail view
    await show_helper_detail(update, context, chat_id, user_id)


async def remove_helper(update: Update, context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    """Remove a helper from the database"""
    
    try:
        conn = database.get_sync_connection()
        try:
            cursor = conn.execute(
                "SELECT username FROM helpers WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            row = cursor.fetchone()
            
            if not row:
                await update.callback_query.answer("❌ Helper not found!")
                return
            
            username = row[0]
            
            # Delete helper
            conn.execute(
                "DELETE FROM helpers WHERE chat_id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            conn.commit()
            
            await update.callback_query.answer(f"✅ Removed @{username} from helpers!")
            
        finally:
            conn.close()
    except Exception as e:
        logger.error(f"Error removing helper: {e}")
        await update.callback_query.answer("❌ Error removing helper!")
        return
    
    # Go back to group's helpers list
    await show_helpers_for_group(update, context, chat_id)


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
    'seller_remove_confirm',
    'seller_rename_start',
    'show_all_sellers',
    'scammer_add_start',
    'scammer_remove_start',
    'show_all_scammers',
    'show_claim_detail',
    'confirm_claim',
    'dismiss_claim',
    'show_barygos_auto_settings',
    'handle_barygos_auto_toggle',
    'show_barygos_auto_interval',
    'handle_barygos_auto_interval_set',
    'show_barygos_auto_groups',
    'handle_barygos_auto_group_toggle',
    'show_barygos_auto_voting_link',
    'show_helpers_list',
    'show_helpers_for_group',
    'show_helper_detail',
    'toggle_helper_permission',
    'remove_helper'
]

