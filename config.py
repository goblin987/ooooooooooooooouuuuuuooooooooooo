#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration and constants for OGbotas
"""

import os
import pytz
from pathlib import Path

# Bot Configuration
# Support both BOT_TOKEN and TELEGRAM_TOKEN for compatibility
BOT_TOKEN = os.getenv('BOT_TOKEN') or os.getenv('TELEGRAM_TOKEN')

# Validate critical configuration
if not BOT_TOKEN:
    raise ValueError("ERROR: BOT_TOKEN or TELEGRAM_TOKEN environment variable not set!")

# Payment system configuration (optional - for crypto deposits/withdrawals)
NOWPAYMENTS_API_KEY = os.getenv('NOWPAYMENTS_API_KEY', '')
NOWPAYMENTS_EMAIL = os.getenv('NOWPAYMENTS_EMAIL', '')
NOWPAYMENTS_PASSWORD = os.getenv('NOWPAYMENTS_PASSWORD', '')
BOT_USERNAME = os.getenv('BOT_USERNAME', 'your_bot')
OWNER_ID = int(os.getenv('OWNER_ID', '0'))

# Voting system configuration (REQUIRED for voting features - from old bot)
VOTING_GROUP_CHAT_ID = int(os.getenv('VOTING_GROUP_CHAT_ID', '0'))
VOTING_GROUP_LINK = os.getenv('VOTING_GROUP_LINK', '')

if len(BOT_TOKEN) < 40 or ':' not in BOT_TOKEN:
    raise ValueError("ERROR: BOT_TOKEN appears to be invalid! Should be format: 123456789:ABCdefGHI...")

ADMIN_CHAT_ID = int(os.getenv('ADMIN_CHAT_ID', '0'))
if ADMIN_CHAT_ID == 0:
    print("WARNING: ADMIN_CHAT_ID not set - admin features may not work properly")

WEBHOOK_URL = os.getenv('WEBHOOK_URL')
PORT = int(os.getenv('PORT', 8000))

if PORT < 1024 or PORT > 65535:
    raise ValueError(f"ERROR: Invalid PORT {PORT}. Must be between 1024-65535")

# Data Directory
DATA_DIR = os.getenv('DATA_DIR', '/opt/render/data')

# Timezone
TIMEZONE = pytz.timezone('Europe/Vilnius')

# Database Configuration
DATABASE_PATH = Path(DATA_DIR) / 'bot_database.db'

# File paths for pickle data
PICKLE_FILES = {
    'user_points': 'user_points.pkl',
    'trusted_sellers': 'trusted_sellers.pkl',
    'confirmed_scammers': 'confirmed_scammers.pkl',
    'username_to_id': 'username_to_id.pkl',
    'user_id_to_scammer': 'user_id_to_scammer.pkl',
    'pending_scammer_reports': 'pending_scammer_reports.pkl',
    'scammer_report_id': 'scammer_report_id.pkl',
    'coinflip_challenges': 'coinflip_challenges.pkl',
    'allowed_groups': 'allowed_groups.pkl'
}

# Rate limiting configuration
RATE_LIMITS = {
    'default': 5,  # 5 requests per minute
    'admin': 20,   # 20 requests per minute for admins
    'moderation': 10  # 10 moderation actions per minute
}

# Message deletion timeouts (in seconds)
DELETE_TIMEOUTS = {
    'short': 30,
    'medium': 45,
    'long': 90
}

# Points system configuration
POINTS_CONFIG = {
    'daily_award': 10,
    'scammer_report': 3,
    'coinflip_min': 1,
    'coinflip_max': 10000
}

# Logging configuration
LOG_CONFIG = {
    'max_bytes': 10 * 1024 * 1024,  # 10MB
    'backup_count': 5,
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
}
