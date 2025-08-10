#!/usr/bin/env python3
"""
Read-Only Scammer Check Bot for Render Hosting
A standalone bot that provides read-only access to scammer and buyer reports.
"""

import logging
import os
import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
import telegram
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
import asyncio
import aiohttp
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration from environment variables
BOT_TOKEN = os.getenv('BOT_TOKEN')
MAIN_BOT_API_URL = os.getenv('MAIN_BOT_API_URL', '')  # URL to sync data from main bot
DATABASE_PATH = os.getenv('DATABASE_PATH', 'scammer_reports.db')

class Database:
    """Database handler for scammer and buyer reports"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Scammers table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS scammers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    user_id INTEGER,
                    reports TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Bad buyers table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bad_buyers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL,
                    user_id INTEGER,
                    reports TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Username to ID mappings
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS username_mappings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    user_id INTEGER NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create indexes for better performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_scammers_username ON scammers(username)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_scammers_user_id ON scammers(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_buyers_username ON bad_buyers(username)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_buyers_user_id ON bad_buyers(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mappings_username ON username_mappings(username)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mappings_user_id ON username_mappings(user_id)')
            
            conn.commit()
    
    def get_scammer(self, username: str) -> Optional[Dict[str, Any]]:
        """Get scammer data by username"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT username, user_id, reports FROM scammers WHERE username = ?', (username.lower(),))
            row = cursor.fetchone()
            if row:
                return {
                    'username': row[0],
                    'user_id': row[1],
                    'reports': json.loads(row[2])
                }
        return None
    
    def get_bad_buyer(self, username: str) -> Optional[Dict[str, Any]]:
        """Get bad buyer data by username"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT username, user_id, reports FROM bad_buyers WHERE username = ?', (username.lower(),))
            row = cursor.fetchone()
            if row:
                return {
                    'username': row[0],
                    'user_id': row[1],
                    'reports': json.loads(row[2])
                }
        return None
    
    def get_user_id(self, username: str) -> Optional[int]:
        """Get user ID by username"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM username_mappings WHERE username = ?', (username.lower(),))
            row = cursor.fetchone()
            return row[0] if row else None
    
    def find_scammer_by_user_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Find scammer by user ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT username, user_id, reports FROM scammers WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'username': row[0],
                    'user_id': row[1],
                    'reports': json.loads(row[2])
                }
        return None
    
    def find_bad_buyer_by_user_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Find bad buyer by user ID"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT username, user_id, reports FROM bad_buyers WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            if row:
                return {
                    'username': row[0],
                    'user_id': row[1],
                    'reports': json.loads(row[2])
                }
        return None
    
    def get_statistics(self) -> Dict[str, int]:
        """Get overall statistics"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Count scammers
            cursor.execute('SELECT COUNT(*) FROM scammers')
            total_scammers = cursor.fetchone()[0]
            
            # Count bad buyers
            cursor.execute('SELECT COUNT(*) FROM bad_buyers')
            total_bad_buyers = cursor.fetchone()[0]
            
            # Count total scammer reports
            cursor.execute('SELECT reports FROM scammers')
            scammer_reports = cursor.fetchall()
            total_scammer_reports = sum(len(json.loads(row[0])) for row in scammer_reports)
            
            # Count total buyer reports
            cursor.execute('SELECT reports FROM bad_buyers')
            buyer_reports = cursor.fetchall()
            total_buyer_reports = sum(len(json.loads(row[0])) for row in buyer_reports)
            
            return {
                'total_scammers': total_scammers,
                'total_bad_buyers': total_bad_buyers,
                'total_scammer_reports': total_scammer_reports,
                'total_buyer_reports': total_buyer_reports
            }
    
    def update_scammer(self, username: str, user_id: Optional[int], reports: List[Dict]):
        """Update or insert scammer data"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO scammers (username, user_id, reports, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (username.lower(), user_id, json.dumps(reports)))
            conn.commit()
    
    def update_bad_buyer(self, username: str, user_id: Optional[int], reports: List[Dict]):
        """Update or insert bad buyer data"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO bad_buyers (username, user_id, reports, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (username.lower(), user_id, json.dumps(reports)))
            conn.commit()
    
    def update_username_mapping(self, username: str, user_id: int):
        """Update username to ID mapping"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO username_mappings (username, user_id)
                VALUES (?, ?)
            ''', (username.lower(), user_id))
            conn.commit()

# Global database instance
db = Database(DATABASE_PATH)

def sanitize_username(username: str) -> str:
    """Sanitize username input"""
    if not username:
        return ""
    # Remove @ symbol if present
    username = username.lstrip('@')
    # Remove any whitespace and convert to lowercase
    username = username.strip().lower()
    return username

async def sync_data_from_main_bot():
    """Sync data from main bot API (if available)"""
    if not MAIN_BOT_API_URL:
        logger.info("No main bot API URL configured, skipping sync")
        return
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{MAIN_BOT_API_URL}/api/scammers") as response:
                if response.status == 200:
                    scammers = await response.json()
                    for username, data in scammers.items():
                        db.update_scammer(username, data.get('user_id'), data.get('reports', []))
            
            async with session.get(f"{MAIN_BOT_API_URL}/api/bad_buyers") as response:
                if response.status == 200:
                    buyers = await response.json()
                    for username, data in buyers.items():
                        db.update_bad_buyer(username, data.get('user_id'), data.get('reports', []))
            
            async with session.get(f"{MAIN_BOT_API_URL}/api/username_mappings") as response:
                if response.status == 200:
                    mappings = await response.json()
                    for username, user_id in mappings.items():
                        db.update_username_mapping(username, user_id)
                        
        logger.info("Data sync completed successfully")
    except Exception as e:
        logger.error(f"Error syncing data from main bot: {e}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    welcome_text = """
🔍 **SCAMMER & BUYER CHECK BOT** 🔍

Šis botas leidžia patikrinti scamerius ir blogus pirkėjus:

📋 **KOMANDOS:**
• `/patikra username` - Patikrinti vartotoją
• `/scameris username` - Peržiūrėti scamer pranešimus  
• `/vagis username` - Peržiūrėti pirkėjų pranešimus
• `/stats` - Statistikos
• `/help` - Pagalba

⚠️ **SVARBU:**
• Šis botas yra tik skaitymo režimu
• Duomenys sinchronizuojami su pagrindiniu botu
• Negalite pridėti naujų pranešimų per šį botą

🛡️ Apsaugokite save nuo sukčių!
    """
    
    await update.message.reply_text(welcome_text, parse_mode='Markdown')

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send help message"""
    help_text = """
🔍 **SCAMMER & BUYER CHECK BOT - PAGALBA** 

📋 **GALIMOS KOMANDOS:**

🔍 `/patikra username` 
   • Patikrinti ar vartotojas yra scamer arba blogas pirkėjas
   • Pavyzdys: `/patikra @username`

📊 `/scameris username`
   • Peržiūrėti visus scamer pranešimus apie vartotoją
   • Rodo kas pranešė ir kodėl

📊 `/vagis username` 
   • Peržiūrėti visus pirkėjų pranešimus apie vartotoją
   • Rodo pardavėjų skundus

📈 `/stats`
   • Peržiūrėti bendrą statistiką

⚠️ **PASTABOS:**
• Galite naudoti username su @ arba be @
• Botas ieško tiek pagal username, tiek pagal ID
• Duomenys atnaujinami realiu laiku

🛡️ **SAUGUMAS:**
• Visada patikrinkite vartotojus prieš sandorius
• Nepasitikėkite nepažįstamais pardavėjais
• Naudokite saugius mokėjimo būdus
    """
    
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def patikra(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Check if user is a scammer or bad buyer"""
    if not context.args:
        await update.message.reply_text(
            "❌ Nenurodėte vartotojo vardo!\n"
            "Naudojimas: `/patikra username`\n"
            "Pavyzdys: `/patikra @username`",
            parse_mode='Markdown'
        )
        return
    
    check_username = sanitize_username(context.args[0])
    
    if not check_username:
        await update.message.reply_text("❌ Neteisingas vartotojo vardas!")
        return
    
    # Check if user is a confirmed scammer
    scammer_info = db.get_scammer(check_username)
    if scammer_info:
        reports = scammer_info.get('reports', [])
        msg_text = f"🚨 **PATVIRTINTAS SCAMER** 🚨\n\n"
        msg_text += f"👤 Vartotojas: `{check_username}`\n"
        msg_text += f"📊 Pranešimų kiekis: **{len(reports)}**\n"
        msg_text += f"⚠️ **ATSARGIAI! Šis vartotojas yra patvirtintas scamer!**\n\n"
        msg_text += f"🛡️ Rekomenduojame vengti sandorių su šiuo vartotoju."
        
        await update.message.reply_text(msg_text, parse_mode='Markdown')
        return
    
    # Check if user is a confirmed bad buyer
    buyer_info = db.get_bad_buyer(check_username)
    if buyer_info:
        reports = buyer_info.get('reports', [])
        msg_text = f"⚠️ **BLOGAS PIRKĖJAS** ⚠️\n\n"
        msg_text += f"👤 Vartotojas: `{check_username}`\n"
        msg_text += f"📊 Pranešimų kiekis: **{len(reports)}**\n"
        msg_text += f"🛒 **Šis pirkėjas turi neigiamų atsiliepimų!**\n\n"
        msg_text += f"💡 Patartina būti atsargiems su šiuo pirkėju."
        
        await update.message.reply_text(msg_text, parse_mode='Markdown')
        return
    
    # Check by user ID if available
    user_id = db.get_user_id(check_username)
    if user_id:
        # Check scammers by ID
        scammer_by_id = db.find_scammer_by_user_id(user_id)
        if scammer_by_id:
            reports = scammer_by_id.get('reports', [])
            original_username = scammer_by_id.get('username', check_username)
            msg_text = f"🚨 **PATVIRTINTAS SCAMER** 🚨\n\n"
            msg_text += f"👤 Vartotojas: `{check_username}` (aka `{original_username}`)\n"
            msg_text += f"📊 Pranešimų kiekis: **{len(reports)}**\n"
            msg_text += f"⚠️ **ATSARGIAI! Šis vartotojas yra patvirtintas scamer!**\n\n"
            msg_text += f"🛡️ Rekomenduojame vengti sandorių su šiuo vartotoju."
            await update.message.reply_text(msg_text, parse_mode='Markdown')
            return
        
        # Check bad buyers by ID
        buyer_by_id = db.find_bad_buyer_by_user_id(user_id)
        if buyer_by_id:
            reports = buyer_by_id.get('reports', [])
            original_username = buyer_by_id.get('username', check_username)
            msg_text = f"⚠️ **BLOGAS PIRKĖJAS** ⚠️\n\n"
            msg_text += f"👤 Vartotojas: `{check_username}` (aka `{original_username}`)\n"
            msg_text += f"📊 Pranešimų kiekis: **{len(reports)}**\n"
            msg_text += f"🛒 **Šis pirkėjas turi neigiamų atsiliepimų!**\n\n"
            msg_text += f"💡 Patartina būti atsargiems su šiuo pirkėju."
            await update.message.reply_text(msg_text, parse_mode='Markdown')
            return
    
    # User is clean
    await update.message.reply_text(
        f"✅ **VARTOTOJAS ŠVARUS** ✅\n\n"
        f"👤 Vartotojas: `{check_username}`\n"
        f"🛡️ Nerasta jokių pranešimų apie šį vartotoją\n"
        f"💚 Galite saugiai bendrauti su šiuo vartotoju",
        parse_mode='Markdown'
    )

async def scameris_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View scammer reports for a user"""
    if not context.args:
        await update.message.reply_text(
            "❌ Nenurodėte vartotojo vardo!\n"
            "Naudojimas: `/scameris username`\n"
            "Pavyzdys: `/scameris @username`",
            parse_mode='Markdown'
        )
        return
    
    check_username = sanitize_username(context.args[0])
    
    if not check_username:
        await update.message.reply_text("❌ Neteisingas vartotojo vardas!")
        return
    
    scammer_info = None
    found_username = check_username
    
    # Direct username check
    scammer_info = db.get_scammer(check_username)
    if not scammer_info:
        # Check by user ID
        user_id = db.get_user_id(check_username)
        if user_id:
            scammer_info = db.find_scammer_by_user_id(user_id)
            if scammer_info:
                found_username = scammer_info.get('username', check_username)
    
    if not scammer_info:
        await update.message.reply_text(
            f"ℹ️ **PRANEŠIMŲ NERASTA**\n\n"
            f"👤 Vartotojas: `{check_username}`\n"
            f"📊 Nerasta jokių scamer pranešimų apie šį vartotoją",
            parse_mode='Markdown'
        )
        return
    
    reports = scammer_info.get('reports', [])
    msg_text = f"🚨 **SCAMER PRANEŠIMAI** 🚨\n\n"
    msg_text += f"👤 Vartotojas: `{found_username}`\n"
    msg_text += f"📊 Pranešimų kiekis: **{len(reports)}**\n\n"
    
    if scammer_info.get('user_id'):
        msg_text += f"🆔 User ID: `{scammer_info['user_id']}`\n\n"
    
    msg_text += "📋 **PRANEŠIMŲ SĄRAŠAS:**\n"
    
    for i, report in enumerate(reports, 1):
        reporter = report.get('reporter', 'Nežinomas')
        reason = report.get('reason', 'Nenurodyta')
        timestamp = report.get('timestamp', 'Nežinoma data')
        
        msg_text += f"\n**{i}.** 👤 `{reporter}`\n"
        msg_text += f"   📅 {timestamp}\n"
        msg_text += f"   📝 {reason}\n"
    
    # Split message if too long
    await send_long_message(update, msg_text)

async def vagis_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """View buyer reports for a user"""
    if not context.args:
        await update.message.reply_text(
            "❌ Nenurodėte vartotojo vardo!\n"
            "Naudojimas: `/vagis username`\n"
            "Pavyzdys: `/vagis @username`",
            parse_mode='Markdown'
        )
        return
    
    check_username = sanitize_username(context.args[0])
    
    if not check_username:
        await update.message.reply_text("❌ Neteisingas vartotojo vardas!")
        return
    
    buyer_info = None
    found_username = check_username
    
    # Direct username check
    buyer_info = db.get_bad_buyer(check_username)
    if not buyer_info:
        # Check by user ID
        user_id = db.get_user_id(check_username)
        if user_id:
            buyer_info = db.find_bad_buyer_by_user_id(user_id)
            if buyer_info:
                found_username = buyer_info.get('username', check_username)
    
    if not buyer_info:
        await update.message.reply_text(
            f"ℹ️ **PRANEŠIMŲ NERASTA**\n\n"
            f"👤 Vartotojas: `{check_username}`\n"
            f"📊 Nerasta jokių pirkėjų pranešimų apie šį vartotoją",
            parse_mode='Markdown'
        )
        return
    
    reports = buyer_info.get('reports', [])
    msg_text = f"🛒 **PIRKĖJŲ PRANEŠIMAI** 🛒\n\n"
    msg_text += f"👤 Vartotojas: `{found_username}`\n"
    msg_text += f"📊 Pranešimų kiekis: **{len(reports)}**\n\n"
    
    if buyer_info.get('user_id'):
        msg_text += f"🆔 User ID: `{buyer_info['user_id']}`\n\n"
    
    msg_text += "📋 **PRANEŠIMŲ SĄRAŠAS:**\n"
    
    for i, report in enumerate(reports, 1):
        reporter = report.get('reporter', 'Nežinomas')
        reason = report.get('reason', 'Nenurodyta')
        timestamp = report.get('timestamp', 'Nežinoma data')
        
        msg_text += f"\n**{i}.** 👤 `{reporter}`\n"
        msg_text += f"   📅 {timestamp}\n"
        msg_text += f"   📝 {reason}\n"
    
    # Split message if too long
    await send_long_message(update, msg_text)

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show statistics about scammers and bad buyers"""
    stats_data = db.get_statistics()
    
    msg_text = f"📊 **STATISTIKOS** 📊\n\n"
    msg_text += f"🚨 **SCAMERIAI:**\n"
    msg_text += f"   • Patvirtinti scameriai: **{stats_data['total_scammers']}**\n"
    msg_text += f"   • Viso pranešimų: **{stats_data['total_scammer_reports']}**\n\n"
    msg_text += f"🛒 **BLOGI PIRKĖJAI:**\n"
    msg_text += f"   • Patvirtinti blogi pirkėjai: **{stats_data['total_bad_buyers']}**\n"
    msg_text += f"   • Viso pranešimų: **{stats_data['total_buyer_reports']}**\n\n"
    msg_text += f"🛡️ **BENDRA INFORMACIJA:**\n"
    msg_text += f"   • Viso problematiškų vartotojų: **{stats_data['total_scammers'] + stats_data['total_bad_buyers']}**\n"
    msg_text += f"   • Viso pranešimų: **{stats_data['total_scammer_reports'] + stats_data['total_buyer_reports']}**\n\n"
    msg_text += f"⚠️ Visada patikrinkite vartotojus prieš sandorius!"
    
    await update.message.reply_text(msg_text, parse_mode='Markdown')

async def send_long_message(update: Update, text: str):
    """Send long message by splitting it into chunks"""
    if len(text) <= 4000:
        await update.message.reply_text(text, parse_mode='Markdown')
        return
    
    # Split message if too long
    lines = text.split('\n')
    current_chunk = ""
    
    for line in lines:
        if len(current_chunk + line + '\n') > 4000:
            await update.message.reply_text(current_chunk, parse_mode='Markdown')
            current_chunk = line + '\n'
        else:
            current_chunk += line + '\n'
    
    if current_chunk:
        await update.message.reply_text(current_chunk, parse_mode='Markdown')

async def periodic_sync():
    """Periodically sync data from main bot"""
    while True:
        try:
            await sync_data_from_main_bot()
            await asyncio.sleep(300)  # Sync every 5 minutes
        except Exception as e:
            logger.error(f"Error in periodic sync: {e}")
            await asyncio.sleep(60)  # Wait 1 minute on error

def main() -> None:
    """Start the bot."""
    if not BOT_TOKEN:
        logger.error("❌ ERROR: BOT_TOKEN environment variable not set!")
        logger.error("Please set BOT_TOKEN in your environment variables")
        return
    
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("patikra", patikra))
    application.add_handler(CommandHandler("scameris", scameris_check))
    application.add_handler(CommandHandler("vagis", vagis_check))
    application.add_handler(CommandHandler("stats", stats))

    # Log that the bot is starting
    logger.info("Read-Only Scammer Check Bot is starting...")
    
    # Start periodic sync task
    if MAIN_BOT_API_URL:
        asyncio.create_task(periodic_sync())
        logger.info("Periodic data sync enabled")

    # Run the bot until the user presses Ctrl-C
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
