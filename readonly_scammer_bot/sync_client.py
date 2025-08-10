#!/usr/bin/env python3
"""
Data Sync Client for Main Bot
Add this to your main bot to sync data with the readonly bot
"""

import asyncio
import aiohttp
import json
import pickle
import os
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class ReadOnlyBotSync:
    """Client to sync data with readonly bot API"""
    
    def __init__(self, api_url: str, api_secret: str):
        self.api_url = api_url.rstrip('/')
        self.api_secret = api_secret
        self.headers = {
            'Authorization': f'Bearer {api_secret}',
            'Content-Type': 'application/json'
        }
    
    async def sync_scammer(self, username: str, user_id: int, reports: list) -> bool:
        """Sync single scammer to readonly bot"""
        try:
            data = {
                'username': username,
                'user_id': user_id,
                'reports': reports
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/api/update_scammer",
                    headers=self.headers,
                    json=data
                ) as response:
                    if response.status == 200:
                        logger.info(f"Synced scammer {username} to readonly bot")
                        return True
                    else:
                        logger.error(f"Failed to sync scammer {username}: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Error syncing scammer {username}: {e}")
            return False
    
    async def sync_bad_buyer(self, username: str, user_id: int, reports: list) -> bool:
        """Sync single bad buyer to readonly bot"""
        try:
            data = {
                'username': username,
                'user_id': user_id,
                'reports': reports
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/api/update_bad_buyer",
                    headers=self.headers,
                    json=data
                ) as response:
                    if response.status == 200:
                        logger.info(f"Synced bad buyer {username} to readonly bot")
                        return True
                    else:
                        logger.error(f"Failed to sync bad buyer {username}: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Error syncing bad buyer {username}: {e}")
            return False
    
    async def sync_username_mapping(self, username: str, user_id: int) -> bool:
        """Sync username mapping to readonly bot"""
        try:
            data = {
                'username': username,
                'user_id': user_id
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/api/update_username_mapping",
                    headers=self.headers,
                    json=data
                ) as response:
                    if response.status == 200:
                        logger.debug(f"Synced username mapping {username} -> {user_id}")
                        return True
                    else:
                        logger.error(f"Failed to sync username mapping {username}: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Error syncing username mapping {username}: {e}")
            return False
    
    async def bulk_sync_all_data(self, scammers: Dict, bad_buyers: Dict, username_mappings: Dict) -> bool:
        """Bulk sync all data to readonly bot"""
        try:
            data = {
                'scammers': scammers,
                'bad_buyers': bad_buyers,
                'username_mappings': username_mappings
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/api/bulk_sync",
                    headers=self.headers,
                    json=data
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"Bulk sync completed: {result.get('counts', {})}")
                        return True
                    else:
                        logger.error(f"Failed to bulk sync data: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"Error in bulk sync: {e}")
            return False

def load_data(filename, default_value):
    """Load data from pickle file"""
    try:
        if os.path.exists(filename):
            with open(filename, 'rb') as f:
                return pickle.load(f)
        return default_value
    except Exception as e:
        logger.error(f"Error loading {filename}: {e}")
        return default_value

async def sync_all_data_to_readonly_bot(api_url: str, api_secret: str):
    """
    Function to add to your main bot for syncing all data
    Call this function periodically or after data updates
    """
    if not api_url or not api_secret:
        logger.warning("Readonly bot sync not configured")
        return
    
    try:
        # Load all data from pickle files (adjust paths as needed)
        confirmed_scammers = load_data('confirmed_scammers.pkl', {})
        confirmed_bad_buyers = load_data('confirmed_bad_buyers.pkl', {})
        username_to_id = load_data('username_to_id.pkl', {})
        
        # Create sync client
        sync_client = ReadOnlyBotSync(api_url, api_secret)
        
        # Perform bulk sync
        success = await sync_client.bulk_sync_all_data(
            confirmed_scammers,
            confirmed_bad_buyers,
            username_to_id
        )
        
        if success:
            logger.info("Successfully synced all data to readonly bot")
        else:
            logger.error("Failed to sync data to readonly bot")
            
    except Exception as e:
        logger.error(f"Error syncing data to readonly bot: {e}")

# Example usage in your main bot:
"""
# Add this to your main bot after approving scammers/buyers:

# After approving a scammer
if readonly_bot_sync:
    await readonly_bot_sync.sync_scammer(username, user_id, reports)

# After approving a bad buyer  
if readonly_bot_sync:
    await readonly_bot_sync.sync_bad_buyer(username, user_id, reports)

# Periodic full sync (run every hour)
async def periodic_readonly_sync():
    while True:
        await sync_all_data_to_readonly_bot(READONLY_BOT_API_URL, READONLY_BOT_API_SECRET)
        await asyncio.sleep(3600)  # 1 hour

# Initialize sync client in your main bot
READONLY_BOT_API_URL = "https://your-readonly-bot.onrender.com"
READONLY_BOT_API_SECRET = "your_secret_key"
readonly_bot_sync = ReadOnlyBotSync(READONLY_BOT_API_URL, READONLY_BOT_API_SECRET) if READONLY_BOT_API_URL else None
"""
