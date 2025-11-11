#!/usr/bin/env python3
"""
Quick fix script to remove @vatninas from trusted sellers list
"""
import pickle
import os

def remove_vatninas():
    """Remove @vatninas from trusted_sellers.pkl"""
    pkl_file = 'trusted_sellers.pkl'
    
    if not os.path.exists(pkl_file):
        print(f"❌ File {pkl_file} not found")
        return
    
    # Load the file
    try:
        with open(pkl_file, 'rb') as f:
            trusted_sellers = pickle.load(f)
        
        print(f"📋 Current trusted sellers: {trusted_sellers}")
        print(f"📊 Type: {type(trusted_sellers)}")
        
        # Remove @vatninas (check both with and without @)
        removed = False
        
        if isinstance(trusted_sellers, list):
            if '@vatninas' in trusted_sellers:
                trusted_sellers.remove('@vatninas')
                removed = True
                print("✅ Removed '@vatninas' from list")
            if 'vatninas' in trusted_sellers:
                trusted_sellers.remove('vatninas')
                removed = True
                print("✅ Removed 'vatninas' from list")
                
        elif isinstance(trusted_sellers, dict):
            if '@vatninas' in trusted_sellers:
                del trusted_sellers['@vatninas']
                removed = True
                print("✅ Removed '@vatninas' from dict")
            if 'vatninas' in trusted_sellers:
                del trusted_sellers['vatninas']
                removed = True
                print("✅ Removed 'vatninas' from dict")
        
        if removed:
            # Save back
            with open(pkl_file, 'wb') as f:
                pickle.dump(trusted_sellers, f)
            print(f"💾 Saved updated list")
            print(f"📋 New trusted sellers: {trusted_sellers}")
        else:
            print("ℹ️ @vatninas not found in the list")
            
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == '__main__':
    remove_vatninas()

