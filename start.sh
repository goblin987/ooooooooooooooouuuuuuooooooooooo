#!/bin/bash

# Render.com startup script for Telegram bot
echo "Starting Telegram Bot on Render.com..."

# Set environment variables for Render detection
export RENDER=true

# Ensure data directory exists
mkdir -p /opt/render/data
mkdir -p /opt/render/data/logs

# Start the bot
python OGbotas.py 