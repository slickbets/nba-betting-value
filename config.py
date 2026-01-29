"""Configuration settings for NBA Betting Value Finder."""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = Path(os.getenv("DB_PATH", str(DATA_DIR / "nba_betting.db")))

# API Keys
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
BALLDONTLIE_API_KEY = os.getenv("BALLDONTLIE_API_KEY", "")

# Elo Parameters
ELO_K_FACTOR = 20.0
ELO_HOME_ADVANTAGE = 35.0  # ~1.4 points spread (based on 2025-26 actual home margin of +1.36)
ELO_INITIAL_RATING = 1500.0
ELO_SPREAD_DIVISOR = 25.0  # Elo diff / this = predicted spread

# O/D Elo Parameters
LEAGUE_AVG_SCORE = 114.5  # League average points per game (for O/D Elo calculations)
USE_OD_ELO = True  # Feature flag for O/D Elo (set to False to fall back to composite)

# Value Bet Thresholds
MIN_EDGE_PERCENT = 3.0
MIN_ODDS = -300  # Don't bet heavy favorites
MAX_ODDS = 500   # Don't bet extreme underdogs

# Preferred sportsbooks (in order of preference)
PREFERRED_BOOKMAKERS = ["draftkings", "fanduel", "betmgm", "caesars"]

# API Settings
ODDS_API_BASE_URL = "https://api.the-odds-api.com/v4"
NBA_SPORT_KEY = "basketball_nba"

# Season settings
CURRENT_SEASON = "2025-26"
