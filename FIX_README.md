# Fix for UNIQUE Constraint Error in Product Media

## Problem
When adding products with media files, the system was encountering this error:
```
sqlite3.IntegrityError: UNIQUE constraint failed: product_media.file_path
```

This occurred in the `handle_confirm_add_drop` function at line 883 in `admin.py`.

## Root Cause
- The `product_media` table has a UNIQUE constraint on the `file_path` column
- When processing media files for products, the same file path was being inserted multiple times
- This caused the SQLite database to reject the duplicate entries

## Solution Applied

### 1. Quick Fix (Immediate)
Changed the SQL INSERT statement from:
```python
c.executemany("INSERT INTO product_media (product_id, media_type, file_path, telegram_file_id) VALUES (?, ?, ?, ?)", media_inserts)
```

To:
```python
c.executemany("INSERT OR IGNORE INTO product_media (product_id, media_type, file_path, telegram_file_id) VALUES (?, ?, ?, ?)", media_inserts)
```

### 2. Comprehensive Fix (Recommended)
The `admin.py` file in this repository contains a complete implementation with:

- **Pre-insertion duplicate checking**: Filters out duplicates before attempting to insert
- **INSERT OR IGNORE**: As a safety net for any remaining duplicates  
- **Proper error handling**: Enhanced logging for constraint violations
- **Database cleanup utilities**: Functions to remove existing duplicates
- **Transaction management**: Proper rollback on errors

## Files Added/Modified

1. **`admin.py`** - Complete admin module with the fix
2. **`fix_product_media_constraint.patch`** - Patch file showing the minimal change needed
3. **`FIX_README.md`** - This documentation

## How to Apply the Fix

### Option 1: Use the Complete Module
Replace your existing admin.py with the new `admin.py` file provided.

### Option 2: Apply the Patch
If you have the original admin.py file:
```bash
patch admin.py < fix_product_media_constraint.patch
```

### Option 3: Manual Fix
Simply change line 883 in your admin.py file to use `INSERT OR IGNORE` instead of `INSERT`.

## Testing
The new admin.py includes a test function that demonstrates:
- Handling duplicate file paths gracefully
- Proper insertion of unique media files
- Error handling and logging

Run the test with:
```python
python admin.py
```

## Prevention
To prevent this issue in the future:
1. Generate unique file paths using timestamps or UUIDs
2. Always check for existing entries before insertion
3. Use appropriate SQL constraints (INSERT OR IGNORE, INSERT OR REPLACE)
4. Implement proper error handling for constraint violations

## Database Schema
The product_media table structure:
```sql
CREATE TABLE product_media (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id INTEGER NOT NULL,
    media_type TEXT NOT NULL,
    file_path TEXT UNIQUE NOT NULL,  -- This is where the constraint exists
    telegram_file_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE CASCADE
);
```

The UNIQUE constraint on `file_path` is intentional to prevent duplicate media files, but the insertion logic needed to handle this properly.
