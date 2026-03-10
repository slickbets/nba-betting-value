#!/bin/bash
# Production startup script for Fly.io
# Starts cron for daily_update.py and runs Streamlit

set -e

# Ensure data directory exists (Fly volume mount)
mkdir -p "${DATA_DIR:-/data}"

# Seed DB from repo if volume is empty (first deploy)
if [ ! -f "${DB_PATH:-/data/nba_betting.db}" ] && [ -f /app/data/nba_betting.db ]; then
    cp /app/data/nba_betting.db "${DB_PATH:-/data/nba_betting.db}"
    echo "Seeded database from repo to volume."
fi

# Export env vars for cron (cron doesn't inherit the shell environment)
printenv | grep -E '^(BALLDONTLIE_API_KEY|ODDS_API_KEY|LINEAR_API_KEY|DATA_DIR|DB_PATH)=' > /etc/environment

# Set up cron for daily_update.py
# 14:00 UTC = 9 AM CDT / 8 AM CST; 15:00 UTC as DST safety net
# daily_update.py has "already ran today" check so double-run is safe
cat > /etc/cron.d/daily-update <<'CRON'
0 14 * * * root . /etc/environment; cd /app && /usr/local/bin/python scripts/daily_update.py >> /data/daily_update.log 2>&1
0 15 * * * root . /etc/environment; cd /app && /usr/local/bin/python scripts/daily_update.py >> /data/daily_update.log 2>&1
CRON
chmod 0644 /etc/cron.d/daily-update

# Start cron daemon
service cron start

# Start Streamlit
exec python -m streamlit run app/main.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true
