#!/bin/bash
# Railway startup script
# Initializes the database on first deploy, then launches Streamlit

if [ ! -f "$DB_PATH" ]; then
    echo "Database not found at $DB_PATH — running first-time setup..."
    python scripts/init_db.py
    python scripts/backfill_history.py
    python scripts/daily_update.py --force
fi

streamlit run app/main.py
