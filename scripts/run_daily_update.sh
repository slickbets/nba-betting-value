#!/bin/bash
# Wrapper script for daily_update.py - loads .env and runs the update

# Change to project directory
cd /Users/spencersolomon/nba-betting-value

# Load environment variables from .env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Run the daily update
/opt/homebrew/bin/python3.11 scripts/daily_update.py "$@"
