#!/bin/bash
# Wrapper script for daily_update.py - loads .env, runs the update,
# then pushes the updated database to GitHub (triggers Railway auto-deploy)

# Change to project directory
cd /Users/spencersolomon/nba-betting-value

# Load environment variables from .env
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Run the daily update
/opt/homebrew/bin/python3.11 scripts/daily_update.py "$@"
UPDATE_EXIT=$?

# If the update succeeded, push the database to GitHub
if [ $UPDATE_EXIT -eq 0 ]; then
    echo "Pushing updated database to GitHub..."
    git add data/nba_betting.db data/.last_daily_update
    git commit -m "Daily database update $(date +%Y-%m-%d)"
    git push
    echo "Database pushed to GitHub — Railway will auto-deploy."
else
    echo "Daily update failed (exit code $UPDATE_EXIT) — skipping git push."
fi
