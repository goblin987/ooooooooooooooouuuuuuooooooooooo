#!/usr/bin/env python3
"""
Admin module for product management with media handling
Fixed UNIQUE constraint issue for product_media table
"""

import sqlite3
import logging
import os
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class ProductMediaManager:
    """Handles product media operations with proper duplicate handling"""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize database tables for product media"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create products table if not exists
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    description TEXT,
                    price REAL,
                    category TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create product_media table with proper constraints
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS product_media (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    media_type TEXT NOT NULL,
                    file_path TEXT UNIQUE NOT NULL,
                    telegram_file_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
                )
            ''')
            
            # Create indexes for better performance
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_product_media_product_id ON product_media(product_id)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_product_media_file_path ON product_media(file_path)')
            
            conn.commit()
            logger.info("Database initialized successfully")
    
    def handle_confirm_add_drop(self, user_id: int, product_data: Dict[str, Any], media_files: List[Dict[str, Any]]) -> bool:
        """
        Handle confirmed product addition with media files
        Fixed version that handles UNIQUE constraint properly
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
                
            # Start transaction
            conn.execute('BEGIN TRANSACTION')
                
                # Insert product
                cursor.execute('''
                    INSERT INTO products (name, description, price, category)
                    VALUES (?, ?, ?, ?)
                ''', (
                    product_data.get('name', ''),
                    product_data.get('description', ''),
                    product_data.get('price', 0.0),
                    product_data.get('category', '')
                ))
                
                product_id = cursor.lastrowid
                logger.info(f"Inserted product with ID: {product_id}")
                
                # Prepare media inserts with duplicate checking
                media_inserts = []
                for media_file in media_files:
                    file_path = media_file.get('file_path')
                    media_type = media_file.get('media_type')
                    telegram_file_id = media_file.get('telegram_file_id')
                    
                    if not file_path or not media_type:
                        logger.warning(f"Skipping invalid media file: {media_file}")
                        continue
                    
                    # Check if file_path already exists
                    cursor.execute('SELECT COUNT(*) FROM product_media WHERE file_path = ?', (file_path,))
                    if cursor.fetchone()[0] == 0:
                        media_inserts.append((product_id, media_type, file_path, telegram_file_id))
                    else:
                        logger.info(f"Skipping duplicate file_path: {file_path}")
                
                # Insert media files (only unique ones)
                if media_inserts:
                    # FIXED: Use INSERT OR IGNORE to handle any remaining duplicates gracefully
                    cursor.executemany('''
                        INSERT OR IGNORE INTO product_media (product_id, media_type, file_path, telegram_file_id)
                        VALUES (?, ?, ?, ?)
                    ''', media_inserts)
                    
                    logger.info(f"Successfully inserted {len(media_inserts)} media records for product {product_id}")
                else:
                    logger.info("No unique media files to insert")
                
                # Commit transaction
                conn.commit()
                logger.info(f"Successfully added product {product_id} with media")
                return True
                
        except sqlite3.IntegrityError as e:
            logger.error(f"Database integrity error: {e}")
            if 'UNIQUE constraint failed: product_media.file_path' in str(e):
                logger.error("UNIQUE constraint failed on product_media.file_path - this should not happen with the fix")
            if conn:
                conn.rollback()
            return False
            
        except Exception as e:
            logger.error(f"Error saving confirmed drop for user {user_id}: {e}")
            if conn:
                conn.rollback()
            return False
        finally:
            if conn:
                conn.close()
    
    def cleanup_temp_directory(self, temp_dir: str):
        """Clean up temporary directory after processing"""
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned temp dir: {temp_dir}")
        except Exception as e:
            logger.error(f"Failed to clean temp dir {temp_dir}: {e}")
    
    def get_product_media(self, product_id: int) -> List[Dict[str, Any]]:
        """Get all media files for a product"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, media_type, file_path, telegram_file_id, created_at
                FROM product_media
                WHERE product_id = ?
                ORDER BY created_at
            ''', (product_id,))
            
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
    
    def remove_duplicate_media(self) -> int:
        """Remove duplicate media entries (cleanup utility)"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Find duplicates by file_path
            cursor.execute('''
                SELECT file_path, COUNT(*) as count
                FROM product_media
                GROUP BY file_path
                HAVING COUNT(*) > 1
            ''')
            
            duplicates = cursor.fetchall()
            removed_count = 0
            
            for file_path, count in duplicates:
                # Keep the first occurrence, remove the rest
                cursor.execute('''
                    DELETE FROM product_media
                    WHERE file_path = ? AND id NOT IN (
                        SELECT MIN(id) FROM product_media WHERE file_path = ?
                    )
                ''', (file_path, file_path))
                
                removed_count += cursor.rowcount
                logger.info(f"Removed {cursor.rowcount} duplicate entries for {file_path}")
            
            conn.commit()
            logger.info(f"Removed {removed_count} duplicate media entries")
            return removed_count


# Example usage and testing
def test_product_media_manager():
    """Test the ProductMediaManager with sample data"""
    manager = ProductMediaManager(':memory:')  # Use in-memory database for testing
    
    # Test data
    product_data = {
        'name': 'Test Product',
        'description': 'A test product',
        'price': 10.99,
        'category': 'test'
    }
    
    media_files = [
        {
            'file_path': '/tmp/test_image.jpg',
            'media_type': 'photo',
            'telegram_file_id': 'test_file_id_1'
        },
        {
            'file_path': '/tmp/test_video.mp4',
            'media_type': 'video',
            'telegram_file_id': 'test_file_id_2'
        },
        # Intentional duplicate to test fix
        {
            'file_path': '/tmp/test_image.jpg',
            'media_type': 'photo',
            'telegram_file_id': 'test_file_id_1_duplicate'
        }
    ]
    
    # Test the fixed function
    success = manager.handle_confirm_add_drop(12345, product_data, media_files)
    print(f"Test result: {'SUCCESS' if success else 'FAILED'}")
    
    # Check what was actually inserted
    media_list = manager.get_product_media(1)
    print(f"Inserted media files: {len(media_list)}")
    for media in media_list:
        print(f"  - {media['file_path']} ({media['media_type']})")


if __name__ == '__main__':
    # Run test if executed directly
    test_product_media_manager()
