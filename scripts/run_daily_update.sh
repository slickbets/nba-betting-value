#!/bin/bash
# Wrapper script for daily_update.py (local development)
# Loads .env and runs the update. DB lives on Fly.io volume, not in git.

cd /Users/spencersolomon/nba-betting-value

if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

/opt/homebrew/bin/python3.11 scripts/daily_update.py "$@"
