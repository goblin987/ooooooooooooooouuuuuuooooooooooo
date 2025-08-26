#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Migration script to switch from monolithic OGbotas.py to modular structure
"""

import shutil
import os
from pathlib import Path

def migrate_to_modular():
    """Migrate from monolithic to modular structure"""
    
    print("🔄 Starting migration to modular structure...")
    
    # 1. Backup the original file
    if os.path.exists('OGbotas.py'):
        backup_path = f'OGbotas_backup_{int(os.path.getmtime("OGbotas.py"))}.py'
        shutil.copy2('OGbotas.py', backup_path)
        print(f"✅ Backed up original OGbotas.py to {backup_path}")
    
    # 2. Create the new main file
    if os.path.exists('main_bot.py'):
        shutil.copy2('main_bot.py', 'OGbotas.py')
        print("✅ Created new modular OGbotas.py from main_bot.py")
    
    # 3. Verify all modules exist
    required_modules = [
        'config.py',
        'database.py', 
        'utils.py',
        'moderation.py',
        'recurring_messages.py'
    ]
    
    missing_modules = []
    for module in required_modules:
        if not os.path.exists(module):
            missing_modules.append(module)
    
    if missing_modules:
        print(f"❌ Missing required modules: {', '.join(missing_modules)}")
        return False
    
    print("✅ All required modules present")
    
    # 4. Test imports
    try:
        import config
        import database
        import utils
        import moderation
        import recurring_messages
        print("✅ All modules import successfully")
    except ImportError as e:
        print(f"❌ Import error: {e}")
        return False
    
    print("\n🎉 Migration completed successfully!")
    print("\n📁 New modular structure:")
    print("├── OGbotas.py (main bot file)")
    print("├── config.py (configuration)")
    print("├── database.py (database operations)")
    print("├── utils.py (utility functions)")
    print("├── moderation.py (ban/mute/unban commands)")
    print("├── recurring_messages.py (recurring messages)")
    print("└── OGbotas_backup_*.py (original backup)")
    
    print("\n🚀 To run the bot:")
    print("python OGbotas.py")
    
    return True

if __name__ == '__main__':
    migrate_to_modular()
