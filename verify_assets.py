#!/usr/bin/env python3
"""
Diagnostic script to verify all assets are loadable.
Run this to check if fonts and images are corrupted.
"""

import os
from PIL import Image, ImageFont

def check_assets():
    """Verify all required assets can be loaded"""
    
    print("=" * 60)
    print("ASSET VERIFICATION REPORT")
    print("=" * 60)
    
    # Check fonts
    fonts = [
        "assets/impact.ttf",
        "assets/OldEnglishFive.ttf",
        "assets/Pricedown Bl.otf",
    ]
    
    print("\n📝 FONTS:")
    for font_path in fonts:
        try:
            if not os.path.exists(font_path):
                print(f"❌ {font_path} - FILE NOT FOUND")
                continue
            
            # Try to load the font
            test_font = ImageFont.truetype(font_path, 40)
            file_size = os.path.getsize(font_path)
            print(f"✅ {font_path} - OK ({file_size:,} bytes)")
        except Exception as e:
            print(f"❌ {font_path} - CORRUPTED: {e}")
    
    # Check images
    images = [
        "background.jpg",
        "background3.jpg",
        "background4.jpg",
    ]
    
    print("\n🖼️  IMAGES:")
    for img_path in images:
        try:
            if not os.path.exists(img_path):
                print(f"❌ {img_path} - FILE NOT FOUND")
                continue
            
            img = Image.open(img_path)
            file_size = os.path.getsize(img_path)
            print(f"✅ {img_path} - OK ({img.size[0]}x{img.size[1]}, {file_size:,} bytes)")
        except Exception as e:
            print(f"❌ {img_path} - CORRUPTED: {e}")
    
    print("\n" + "=" * 60)
    print("If any files show as CORRUPTED, re-download them fresh")
    print("=" * 60)

if __name__ == "__main__":
    check_assets()

