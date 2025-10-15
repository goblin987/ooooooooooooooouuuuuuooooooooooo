#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pre-Deployment Validation Script
Run this before deploying to catch common configuration errors
"""

import os
import sys
from pathlib import Path

# Color codes for terminal output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")

def print_success(text):
    print(f"{Colors.GREEN}[OK] {text}{Colors.END}")

def print_warning(text):
    print(f"{Colors.YELLOW}[WARNING] {text}{Colors.END}")

def print_error(text):
    print(f"{Colors.RED}[ERROR] {text}{Colors.END}")

def print_info(text):
    print(f"{Colors.BLUE}[INFO] {text}{Colors.END}")

# Track overall validation status
errors = []
warnings = []

def validate_files():
    """Check that all required files exist"""
    print_header("1. File Structure Validation")
    
    required_files = [
        'OGbotas.py',
        'config.py',
        'database.py',
        'requirements.txt',
        'games.py',
        'points_games.py',
        'payments.py',
        'payments_webhook.py',
        'moderation_grouphelp.py',
        'warn_system.py',
        'voting.py',
        'recurring_messages_grouphelp.py',
        'masked_users.py',
        'admin_panel.py',
        'utils.py',
        'barygos_banners.py'
    ]
    
    for file in required_files:
        if Path(file).exists():
            print_success(f"Found: {file}")
        else:
            print_error(f"Missing: {file}")
            errors.append(f"Missing required file: {file}")

def validate_imports():
    """Check that all modules can be imported"""
    print_header("2. Import Validation")
    
    try:
        import config
        print_success("config.py imports successfully")
    except Exception as e:
        print_error(f"config.py import failed: {e}")
        errors.append(f"Config import error: {e}")
        return  # Stop here if config fails
    
    modules = [
        'database',
        'utils',
        'games',
        'points_games',
        'payments',
        'payments_webhook',
        'moderation_grouphelp',
        'warn_system',
        'voting',
        'recurring_messages_grouphelp',
        'masked_users',
        'admin_panel'
    ]
    
    for module_name in modules:
        try:
            __import__(module_name)
            print_success(f"{module_name} imports successfully")
        except Exception as e:
            print_error(f"{module_name} import failed: {e}")
            errors.append(f"Import error in {module_name}: {e}")

def validate_environment():
    """Check environment variables"""
    print_header("3. Environment Variables Validation")
    
    # Critical variables
    critical_vars = {
        'BOT_TOKEN': 'Telegram bot token',
        'OWNER_ID': 'Your Telegram user ID'
    }
    
    for var, description in critical_vars.items():
        value = os.getenv(var)
        if value:
            # Don't print actual token, just confirmation
            if var == 'BOT_TOKEN':
                if len(value) > 40 and ':' in value:
                    print_success(f"{var} is set (appears valid)")
                else:
                    print_error(f"{var} is set but appears invalid (should be format: 123:ABC...)")
                    errors.append(f"{var} appears invalid")
            elif var == 'OWNER_ID':
                if value.isdigit():
                    print_success(f"{var} is set ({value})")
                else:
                    print_error(f"{var} is set but not a valid ID")
                    errors.append(f"{var} must be numeric")
        else:
            print_error(f"{var} is NOT set ({description})")
            errors.append(f"Missing critical variable: {var}")
    
    # Important but optional variables
    optional_vars = {
        'ADMIN_CHAT_ID': 'Admin chat ID',
        'NOWPAYMENTS_API_KEY': 'NOWPayments API key (for crypto payments)',
        'WEBHOOK_URL': 'Your Render app URL',
        'PORT': 'Server port (default: 8000)',
        'DATA_DIR': 'Database directory (default: /opt/render/data)',
        'VOTING_GROUP_CHAT_ID': 'Voting group ID (optional)',
        'VOTING_GROUP_LINK': 'Voting group link (optional)'
    }
    
    for var, description in optional_vars.items():
        value = os.getenv(var)
        if value:
            print_success(f"{var} is set")
        else:
            print_warning(f"{var} not set ({description})")
            if var in ['NOWPAYMENTS_API_KEY', 'WEBHOOK_URL']:
                warnings.append(f"Optional but recommended: {var} - {description}")

def validate_database_schema():
    """Check database can be initialized"""
    print_header("4. Database Schema Validation")
    
    try:
        from database import database
        print_success("Database module loaded")
        
        # Check tables can be created
        conn = database.get_sync_connection()
        cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        expected_tables = [
            'user_cache',
            'ban_history',
            'scheduled_messages',
            'banned_words',
            'helpers',
            'scammer_reports',
            'users',
            'pending_bans',
            'groups',
            'warnings'  # Added during debugging
        ]
        
        for table in expected_tables:
            if table in tables:
                print_success(f"Table exists: {table}")
            else:
                print_warning(f"Table will be created on first run: {table}")
        
        conn.close()
        print_success("Database schema validation complete")
        
    except Exception as e:
        print_error(f"Database validation failed: {e}")
        errors.append(f"Database error: {e}")

def validate_dependencies():
    """Check required Python packages"""
    print_header("5. Dependencies Validation")
    
    required_packages = [
        ('telegram', 'python-telegram-bot'),
        ('apscheduler', 'apscheduler'),
        ('pytz', 'pytz'),
        ('aiohttp', 'aiohttp'),
        ('requests', 'requests'),
        ('qrcode', 'qrcode'),
        ('PIL', 'pillow')
    ]
    
    for package_name, pip_name in required_packages:
        try:
            __import__(package_name)
            print_success(f"{pip_name} is installed")
        except ImportError:
            print_error(f"{pip_name} is NOT installed")
            errors.append(f"Missing package: {pip_name}")
            print_info(f"   Install with: pip install {pip_name}")

def validate_configuration():
    """Check config.py settings"""
    print_header("6. Configuration Validation")
    
    try:
        import config
        
        # Check BOT_TOKEN
        if hasattr(config, 'BOT_TOKEN') and config.BOT_TOKEN:
            if len(config.BOT_TOKEN) > 40 and ':' in config.BOT_TOKEN:
                print_success("BOT_TOKEN format appears valid")
            else:
                print_error("BOT_TOKEN format appears invalid")
                errors.append("BOT_TOKEN should be format: 123456789:ABCdef...")
        else:
            print_error("BOT_TOKEN not configured")
            errors.append("BOT_TOKEN missing in config")
        
        # Check PORT
        if hasattr(config, 'PORT'):
            port = config.PORT
            if 1024 <= port <= 65535:
                print_success(f"PORT is valid ({port})")
            else:
                print_error(f"PORT is out of range ({port})")
                errors.append("PORT must be between 1024-65535")
        
        # Check OWNER_ID
        if hasattr(config, 'OWNER_ID') and config.OWNER_ID:
            if config.OWNER_ID > 0:
                print_success(f"OWNER_ID is set ({config.OWNER_ID})")
            else:
                print_warning("OWNER_ID is 0 - admin features may not work")
                warnings.append("Set OWNER_ID to your Telegram user ID")
        
        # Check TIMEZONE
        if hasattr(config, 'TIMEZONE'):
            print_success(f"TIMEZONE is configured ({config.TIMEZONE})")
        else:
            print_warning("TIMEZONE not configured")
        
    except Exception as e:
        print_error(f"Configuration validation failed: {e}")
        errors.append(f"Config error: {e}")

def validate_syntax():
    """Check Python syntax in all .py files"""
    print_header("7. Syntax Validation")
    
    import py_compile
    import glob
    
    py_files = glob.glob("*.py")
    syntax_errors = []
    
    for file in py_files:
        try:
            py_compile.compile(file, doraise=True)
            print_success(f"Syntax OK: {file}")
        except py_compile.PyCompileError as e:
            print_error(f"Syntax error in {file}")
            syntax_errors.append(f"{file}: {e}")
            errors.append(f"Syntax error in {file}")
    
    if syntax_errors:
        print_info("Details:")
        for err in syntax_errors:
            print(f"  {err}")

def print_summary():
    """Print final summary"""
    print_header("Validation Summary")
    
    if not errors and not warnings:
        print_success("All checks passed! Bot is ready for deployment.")
        return 0
    
    if warnings:
        print(f"\n{Colors.YELLOW}{Colors.BOLD}Warnings ({len(warnings)}):{Colors.END}")
        for i, warning in enumerate(warnings, 1):
            print(f"  {i}. {warning}")
    
    if errors:
        print(f"\n{Colors.RED}{Colors.BOLD}Errors ({len(errors)}):{Colors.END}")
        for i, error in enumerate(errors, 1):
            print(f"  {i}. {error}")
        print(f"\n{Colors.RED}{Colors.BOLD}[FAILED] Validation FAILED. Fix errors before deploying.{Colors.END}\n")
        return 1
    else:
        print(f"\n{Colors.YELLOW}{Colors.BOLD}[WARNING] Validation passed with warnings. Review before deploying.{Colors.END}\n")
        return 0

def main():
    """Run all validation checks"""
    print(f"{Colors.BOLD}{Colors.BLUE}")
    print("=" * 60)
    print("     OGbotas - Pre-Deployment Validation Script     ")
    print("=" * 60)
    print(f"{Colors.END}")
    
    validate_files()
    validate_dependencies()
    validate_imports()
    validate_environment()
    validate_database_schema()
    validate_configuration()
    validate_syntax()
    
    exit_code = print_summary()
    sys.exit(exit_code)

if __name__ == '__main__':
    main()

