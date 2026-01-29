#!/bin/bash
# Railway startup script
# Ensures the database directory exists, then launches Streamlit

# Create the directory for the database if it doesn't exist
DB_DIR=$(dirname "$DB_PATH")
mkdir -p "$DB_DIR"

echo "DB_PATH=$DB_PATH"
echo "DB directory: $DB_DIR"
ls -la "$DB_DIR" 2>/dev/null

streamlit run app/main.py
