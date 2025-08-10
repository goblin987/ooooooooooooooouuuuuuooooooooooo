#!/usr/bin/env python3
"""
API Server for syncing data with main bot
This creates endpoints that the main bot can use to push data updates
"""

import os
import json
import sqlite3
from datetime import datetime
from typing import Dict, Any
from aiohttp import web, web_request
import logging

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

DATABASE_PATH = os.getenv('DATABASE_PATH', 'scammer_reports.db')
API_SECRET = os.getenv('API_SECRET', 'your_secret_key_here')

class Database:
    """Database handler for API operations"""
    
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
            
            # Create indexes
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_scammers_username ON scammers(username)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_scammers_user_id ON scammers(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_buyers_username ON bad_buyers(username)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_buyers_user_id ON bad_buyers(user_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mappings_username ON username_mappings(username)')
            
            conn.commit()
    
    def update_scammer(self, username: str, user_id: int, reports: list):
        """Update or insert scammer data"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO scammers (username, user_id, reports, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ''', (username.lower(), user_id, json.dumps(reports)))
            conn.commit()
    
    def update_bad_buyer(self, username: str, user_id: int, reports: list):
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
    
    def bulk_update_scammers(self, scammers_data: Dict[str, Dict]):
        """Bulk update scammers data"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Clear existing data
            cursor.execute('DELETE FROM scammers')
            
            # Insert new data
            for username, data in scammers_data.items():
                cursor.execute('''
                    INSERT INTO scammers (username, user_id, reports, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ''', (username.lower(), data.get('user_id'), json.dumps(data.get('reports', []))))
            
            conn.commit()
    
    def bulk_update_bad_buyers(self, buyers_data: Dict[str, Dict]):
        """Bulk update bad buyers data"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Clear existing data
            cursor.execute('DELETE FROM bad_buyers')
            
            # Insert new data
            for username, data in buyers_data.items():
                cursor.execute('''
                    INSERT INTO bad_buyers (username, user_id, reports, updated_at)
                    VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ''', (username.lower(), data.get('user_id'), json.dumps(data.get('reports', []))))
            
            conn.commit()
    
    def bulk_update_username_mappings(self, mappings_data: Dict[str, int]):
        """Bulk update username mappings"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            # Clear existing data
            cursor.execute('DELETE FROM username_mappings')
            
            # Insert new data
            for username, user_id in mappings_data.items():
                cursor.execute('''
                    INSERT INTO username_mappings (username, user_id)
                    VALUES (?, ?)
                ''', (username.lower(), user_id))
            
            conn.commit()

# Global database instance
db = Database(DATABASE_PATH)

def verify_api_secret(request: web_request.Request) -> bool:
    """Verify API secret from request headers"""
    auth_header = request.headers.get('Authorization', '')
    return auth_header == f"Bearer {API_SECRET}"

async def health_check(request: web_request.Request) -> web.Response:
    """Health check endpoint"""
    return web.json_response({"status": "healthy", "timestamp": datetime.now().isoformat()})

async def update_scammer_endpoint(request: web_request.Request) -> web.Response:
    """Update single scammer data"""
    if not verify_api_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        data = await request.json()
        username = data.get('username')
        user_id = data.get('user_id')
        reports = data.get('reports', [])
        
        if not username:
            return web.json_response({"error": "Username required"}, status=400)
        
        db.update_scammer(username, user_id, reports)
        logger.info(f"Updated scammer: {username}")
        
        return web.json_response({"success": True, "message": "Scammer updated"})
    
    except Exception as e:
        logger.error(f"Error updating scammer: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def update_bad_buyer_endpoint(request: web_request.Request) -> web.Response:
    """Update single bad buyer data"""
    if not verify_api_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        data = await request.json()
        username = data.get('username')
        user_id = data.get('user_id')
        reports = data.get('reports', [])
        
        if not username:
            return web.json_response({"error": "Username required"}, status=400)
        
        db.update_bad_buyer(username, user_id, reports)
        logger.info(f"Updated bad buyer: {username}")
        
        return web.json_response({"success": True, "message": "Bad buyer updated"})
    
    except Exception as e:
        logger.error(f"Error updating bad buyer: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def bulk_sync_endpoint(request: web_request.Request) -> web.Response:
    """Bulk sync all data from main bot"""
    if not verify_api_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        data = await request.json()
        
        scammers = data.get('scammers', {})
        bad_buyers = data.get('bad_buyers', {})
        username_mappings = data.get('username_mappings', {})
        
        # Bulk update all data
        db.bulk_update_scammers(scammers)
        db.bulk_update_bad_buyers(bad_buyers)
        db.bulk_update_username_mappings(username_mappings)
        
        logger.info(f"Bulk sync completed: {len(scammers)} scammers, {len(bad_buyers)} bad buyers, {len(username_mappings)} mappings")
        
        return web.json_response({
            "success": True,
            "message": "Bulk sync completed",
            "counts": {
                "scammers": len(scammers),
                "bad_buyers": len(bad_buyers),
                "username_mappings": len(username_mappings)
            }
        })
    
    except Exception as e:
        logger.error(f"Error in bulk sync: {e}")
        return web.json_response({"error": str(e)}, status=500)

async def update_username_mapping_endpoint(request: web_request.Request) -> web.Response:
    """Update username to ID mapping"""
    if not verify_api_secret(request):
        return web.json_response({"error": "Unauthorized"}, status=401)
    
    try:
        data = await request.json()
        username = data.get('username')
        user_id = data.get('user_id')
        
        if not username or not user_id:
            return web.json_response({"error": "Username and user_id required"}, status=400)
        
        db.update_username_mapping(username, user_id)
        logger.info(f"Updated username mapping: {username} -> {user_id}")
        
        return web.json_response({"success": True, "message": "Username mapping updated"})
    
    except Exception as e:
        logger.error(f"Error updating username mapping: {e}")
        return web.json_response({"error": str(e)}, status=500)

def create_app() -> web.Application:
    """Create and configure the web application"""
    app = web.Application()
    
    # Add routes
    app.router.add_get('/health', health_check)
    app.router.add_post('/api/update_scammer', update_scammer_endpoint)
    app.router.add_post('/api/update_bad_buyer', update_bad_buyer_endpoint)
    app.router.add_post('/api/update_username_mapping', update_username_mapping_endpoint)
    app.router.add_post('/api/bulk_sync', bulk_sync_endpoint)
    
    return app

def main():
    """Run the API server"""
    if API_SECRET == 'your_secret_key_here':
        logger.error("❌ ERROR: Please set API_SECRET environment variable!")
        return
    
    app = create_app()
    port = int(os.getenv('PORT', 8080))
    
    logger.info(f"Starting API server on port {port}")
    web.run_app(app, host='0.0.0.0', port=port)

if __name__ == '__main__':
    main()
