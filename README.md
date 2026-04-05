# NBA Game Predictions

A Python application that predicts NBA game outcomes using an Elo rating system. Shows win probabilities, predicted spreads, and totals for each game, with injury and rest adjustments. Tracks model accuracy over time.

**Live at [slick-bets.com](https://slick-bets.com)**

## Features

- **Elo Rating System**: Track team strength using composite, offensive, and defensive Elo ratings
- **Win Probability Predictions**: Convert Elo differences to win probabilities, point spreads, and predicted totals
- **Injury Adjustments**: Adjust predictions based on injured players (USG%-weighted impact ratings for 320+ players)
- **Rest/B2B Factors**: Back-to-back penalty and rest advantage adjustments
- **Team-Specific Home Court**: Dynamic home court advantage based on each team's home/road performance
- **Model Accuracy Tracking**: Pick accuracy, spread error, confidence analysis over time
- **Live Odds Display**: Fetch current sportsbook odds for comparison (BallDontLie primary, The Odds API fallback)
- **Backtesting Engine**: Replay full seasons to measure model accuracy under any parameter set
- **Parameter Optimization**: Parallel sweep tool finds optimal Elo parameters across the season
- **Regression Tests**: Automated accuracy thresholds catch model regressions
- **Interactive Dashboard**: Streamlit UI with predictions visible immediately on app open
- **Feedback System**: Submit bug reports and feature requests directly to Linear from the app

## Quick Start

### 1. Install Dependencies

```bash
cd nba-betting-value
pip install -r requirements.txt
```

### 2. Configure API Keys

Create a `.env` file with your API keys:

```
BALLDONTLIE_API_KEY=your_key_here   # Required — primary data source
ODDS_API_KEY=your_key_here          # Optional — fallback odds provider
LINEAR_API_KEY=your_key_here        # Optional — feedback integration
```

[BallDontLie API](https://www.balldontlie.io) provides games, scores, injuries, odds, player stats, and standings.

### 3. Initialize Database

```bash
python scripts/init_db.py
```

This loads all NBA teams and current season games.

### 4. Build Elo Ratings

```bash
python scripts/rebuild_elo.py --all
```

This calculates composite and offensive/defensive Elo ratings from historical game results.

### 5. Launch the App

```bash
streamlit run app/main.py
```

Open http://localhost:8501 in your browser.

## Project Structure

```
nba-betting-value/
├── app/                    # Streamlit UI
│   ├── main.py            # Predictions landing page (picks + accuracy)
│   ├── shared.py          # Global CSS (dark theme), sidebar, helpers
│   └── pages/             # Multi-page app
│       ├── 1_Game_Details.py    # Elo breakdowns, injuries, rest, odds
│       ├── 2_Model_Accuracy.py  # Prediction tracking
│       ├── 3_Team_Ratings.py    # Elo rankings with W/L records
│       └── 4_Donate.py         # Support page
│
├── src/                    # Core logic
│   ├── data/              # Data fetching & storage
│   │   ├── bdl_fetcher.py     # BallDontLie API client (primary)
│   │   ├── database.py        # SQLite operations
│   │   ├── injury_fetcher.py  # Injuries (BDL primary, ESPN fallback)
│   │   ├── odds_fetcher.py    # Odds (BDL primary, The Odds API fallback)
│   │   └── nba_fetcher.py     # DEPRECATED: NBA API + ESPN fallback
│   ├── models/            # Prediction models
│   │   ├── elo.py             # Elo rating calculations (composite + O/D)
│   │   ├── predictor.py       # Game predictions with adjustments
│   │   ├── player_impact.py   # Player impact (USG%-weighted, DB-only)
│   │   ├── rest_factor.py     # Back-to-back and rest day adjustments
│   │   └── params.py          # EloParams frozen dataclass
│   ├── backtesting/       # Model evaluation
│   │   ├── engine.py          # Backtest engine (replays season)
│   │   └── sweep.py           # Parameter grid + parallel sweep
│   ├── betting/           # Odds utilities
│   │   ├── odds_converter.py
│   │   └── value_finder.py
│   └── utils/             # Lightweight utilities
│       ├── live_scores.py     # Auto-refresh live scores from ESPN
│       └── feedback.py        # Submit feedback to Linear
│
├── scripts/               # CLI scripts
│   ├── init_db.py             # Initialize database with teams + games
│   ├── daily_update.py        # Daily refresh (results, Elo, predictions, odds, player impact)
│   ├── rebuild_elo.py         # Full Elo rebuild (composite + O/D)
│   ├── backfill_od_elo.py     # Rebuild O/D Elo by replaying season
│   ├── backfill_missing_days.py  # Recover from API outages via NBA CDN
│   ├── param_sweep.py        # Parameter optimization CLI
│   └── cleanup_preseason.py   # Remove preseason games from DB
│
├── tests/                 # Unit tests (141 total)
├── assets/                # Brand assets (favicon, logo)
├── data/                  # SQLite database (gitignored)
├── config.py              # Configuration + now_ct() timezone helper
├── Dockerfile             # Production container image
├── fly.toml               # Fly.io app configuration
└── requirements.txt
```

## How It Works

### Elo Ratings

Every team starts at 1500 Elo. After each game:
- Winner gains points, loser loses points
- Amount exchanged depends on expected outcome (K-factor = 14, decays from 28 over first 300 games)
- Beating a strong team = more points gained
- Margin of victory matters (blowouts worth more, clamped 0.5–3.0x)
- 33% regression toward 1500 between seasons

### Win Probability

```
P(win) = 1 / (1 + 10^((Opponent_Elo - Your_Elo - HCA) / 400))
```

A 100 Elo advantage gives roughly 64% win probability.

### Point Spread

```
Spread = Elo_Difference / 18
```

18 Elo points ≈ 1 point of spread.

### Offensive/Defensive Elo

Each team has separate O-Elo and D-Elo ratings, enabling predicted totals:
```
Expected_Score = League_Avg + (Offense_Elo - Opponent_Defense_Elo) / 25 + HCA_points
```

### Injury Adjustments

Player impact is calculated from advanced stats:
```
elo_impact = NET_RATING × (MPG/48) × (USG%/0.20) × 1.5
```

Injury status multipliers: Out (1.0), Doubtful (0.8), Questionable (0.5), Day-to-Day (0.3), Probable (0.1).

### Rest Factors

| Situation | Elo Adjustment |
|-----------|---------------|
| Back-to-back | -35 (~1.9 pts) |
| 1 day rest | 0 (normal) |
| 2 days rest | +5 |
| 3+ days rest | +8 |

## Daily Usage

### Refresh Data

```bash
python scripts/daily_update.py
```

This:
1. Updates game results from the last 3 days
2. Recalculates Elo ratings
3. Fetches today's games
4. Generates predictions
5. Updates player impact ratings (every 3 days)

### View Predictions

1. Open the app: `streamlit run app/main.py`
2. Main page shows today's model picks with win probabilities
3. **Game Details** — Elo breakdowns, injuries, rest factors, and live odds
4. **Model Accuracy** — prediction performance over time
5. **Team Ratings** — current Elo rankings with W/L records

## Running Tests

```bash
pytest tests/ -v
```

## Deployment (Fly.io)

The app runs on [Fly.io](https://fly.io) with a persistent volume for SQLite. Daily updates run on the server via cron. Pushes to `main` trigger GitHub Actions (test + deploy).

- **Region**: `ord` (Chicago)
- **Machine**: shared-cpu-1x, 1024 MB RAM
- **Volume**: 1 GB persistent storage for SQLite DB
- **Cron**: `daily_update.py` runs at 14:00 + 15:00 UTC (~9 AM CT)

### Deploying Updates

Push to `main` triggers CI/CD. Or deploy manually:

```bash
fly deploy
```

### Useful Commands

```bash
# Run daily update manually on the server
fly ssh console -C "/usr/local/bin/python /app/scripts/daily_update.py --force"

# View daily update logs
fly ssh console -C "cat /data/daily_update.log"

# Check app status
fly status
```

### CI/CD

GitHub Actions (`.github/workflows/deploy.yml`) runs tests then deploys on every push to `main`. Add `FLY_API_TOKEN` to your GitHub repo secrets.

## Data Sources

| Data | Primary Source | Fallback |
|------|---------------|----------|
| Games & Scores | BallDontLie API | ESPN scoreboard |
| Injuries | BallDontLie API | ESPN injuries API |
| Live Scores | BallDontLie live box scores | ESPN scoreboard |
| Odds | BallDontLie v2/odds | The Odds API |
| Player Impact | BallDontLie stats/advanced | — |
| W/L Records | BallDontLie standings | ESPN standings |

## Limitations

- Elo is a simple model — backtested accuracy is ~64% on straight predictions (2025-26 season)
- This is for educational purposes — no guarantee of profit
- Player impact uses net rating which conflates team and individual quality
- O/D Elo has structural drift (~1471 offense avg, ~1529 defense avg)
- Cloud servers use UTC; app uses Central Time (DST-aware) via `now_ct()` helper

## Roadmap

### Completed
- [x] Elo rating system with home court advantage
- [x] Win probability and spread predictions
- [x] Offensive/Defensive Elo with predicted totals
- [x] Player injury adjustments (USG%-weighted impact ratings)
- [x] Back-to-back / rest day factors
- [x] Team-specific home court advantage
- [x] Margin-of-victory Elo with K-factor decay
- [x] Model accuracy tracking (pick accuracy, spread error, confidence analysis)
- [x] Backtesting engine and parameter sweep optimization
- [x] Model regression tests with automated thresholds
- [x] BallDontLie API as primary data source (ESPN fallback)
- [x] NBA CDN backfill for API outages
- [x] Predictions-focused UI with immediate visibility
- [x] Fly.io deployment with persistent volume, server-side cron, CI/CD
- [x] Linear feedback integration
- [x] Custom domain (slick-bets.com)

### Future Ideas
- [ ] Lineups endpoint for starter/bench injury weighting
- [ ] Leaders endpoint for player impact validation
- [ ] Historical injury impact analysis
- [ ] ML model using advanced stats
- [ ] Multi-sport expansion
