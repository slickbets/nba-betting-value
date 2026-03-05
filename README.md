# NBA Game Predictions

A Python application that predicts NBA game outcomes using an Elo rating system. Shows win probabilities, predicted spreads, and totals for each game, with injury and rest adjustments.

## Features

- **Elo Rating System**: Track team strength using composite, offensive, and defensive Elo ratings
- **Win Probability Predictions**: Convert Elo differences to win probabilities, point spreads, and predicted totals
- **Injury Adjustments**: Adjust predictions based on injured players (USG%-weighted impact ratings for 320+ players)
- **Rest/B2B Factors**: Back-to-back penalty and rest advantage adjustments
- **Model Accuracy Tracking**: Pick accuracy, spread error, confidence analysis over time
- **Live Odds Display**: Fetch current sportsbook odds for comparison (optional, via The Odds API)
- **Backtesting Engine**: Replay full seasons to measure model accuracy under any parameter set
- **Parameter Optimization**: Parallel sweep tool finds optimal Elo parameters across the season
- **Regression Tests**: Automated accuracy thresholds catch model regressions
- **Interactive Dashboard**: Streamlit UI with predictions visible immediately on app open

## Quick Start

### 1. Install Dependencies

```bash
cd nba-betting-value
pip install -r requirements.txt
```

### 2. Configure API Key (Optional)

Sign up at [The Odds API](https://the-odds-api.com) for live odds display in game details (free tier: 500 requests/month).

Add your key to `.env`:
```
ODDS_API_KEY=your_key_here
```

### 3. Initialize Database

```bash
python scripts/init_db.py
```

This loads all NBA teams and current season games.

### 4. Backfill Historical Data

```bash
python scripts/backfill_history.py
```

This calculates Elo ratings from historical game results (takes a few minutes).

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
│   └── pages/             # Multi-page app
│       ├── 1_Game_Details.py   # Elo breakdowns, injuries, rest, odds
│       ├── 2_Model_Accuracy.py # Prediction tracking
│       └── 3_Team_Ratings.py   # Elo rankings
│
├── src/                    # Core logic
│   ├── data/              # Data fetching & storage
│   │   ├── database.py
│   │   ├── nba_fetcher.py
│   │   └── odds_fetcher.py
│   ├── models/            # Prediction models
│   │   ├── elo.py
│   │   ├── predictor.py
│   │   └── params.py         # EloParams dataclass (all tunable params)
│   ├── backtesting/       # Model evaluation
│   │   ├── engine.py         # Backtest engine (replays season)
│   │   └── sweep.py          # Parameter grid + parallel sweep
│   └── betting/           # Odds utilities
│       ├── odds_converter.py
│       └── value_finder.py
│
├── scripts/               # CLI scripts
│   ├── init_db.py
│   ├── backfill_history.py
│   ├── backfill_missing_days.py # Recover from NBA API outages via CDN
│   ├── daily_update.py
│   └── param_sweep.py        # Parameter optimization CLI
│
├── tests/                 # Unit tests (141 total)
├── data/                  # SQLite database (gitignored)
├── config.py              # Configuration
└── requirements.txt
```

## How It Works

### Elo Ratings

Every team starts at 1500 Elo. After each game:
- Winner gains points, loser loses points
- Amount exchanged depends on expected outcome
- Beating a strong team = more points gained
- Margin of victory matters (blowouts worth more)
- Home court adds 35 Elo points (~1.4 point spread advantage)

### Win Probability

```
P(win) = 1 / (1 + 10^((Opponent_Elo - Your_Elo) / 400))
```

A 100 Elo advantage gives roughly 64% win probability.

### Point Spread

```
Spread = Elo_Difference / 25
```

A 125 Elo advantage (100 base + 25 from skill) equals a 5-point spread.

### Offensive/Defensive Elo

Each team has separate O-Elo and D-Elo ratings, enabling predicted totals:
```
Expected_Score = League_Avg + (Offense_Elo - Opponent_Defense_Elo) / 25
```

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
5. Updates player impact ratings

### View Predictions

1. Open the app: `streamlit run app/main.py`
2. Main page shows today's model picks with win probabilities
3. "Game Details" page shows Elo breakdowns, injuries, rest factors, and live odds
4. "Model Accuracy" page tracks prediction performance
5. "Team Ratings" page shows current Elo rankings

## Configuration

Edit `config.py` to adjust:

```python
# Elo Parameters
ELO_K_FACTOR = 15.0           # Rating volatility (optimized via parameter sweep)
ELO_HOME_ADVANTAGE = 35.0     # Home court bonus
ELO_INITIAL_RATING = 1500.0   # Starting rating
```

## Running Tests

```bash
pytest tests/ -v
```

## Limitations

- Elo is a simple model - backtested accuracy is ~63% on straight predictions (838 games, 2025-26)
- This is for educational purposes - no guarantee of profit
- The Odds API free tier has limited requests (500/month)
- Player impact data depends on NBA API availability (players with 0 GP not tracked)
- NBA API (`stats.nba.com`) is behind Akamai WAF requiring browser-like headers; if requests start timing out, update `NBA_API_HEADERS` in `nba_fetcher.py`
- Cloud servers use UTC; app uses Central Time (DST-aware) via `now_ct()` helper for correct date defaults

## Roadmap

### Completed
- [x] Elo rating system with home court advantage
- [x] Win probability and spread predictions
- [x] Offensive/Defensive Elo with predicted totals
- [x] Player injury adjustments (USG%-weighted impact ratings)
- [x] Back-to-back / rest day factors
- [x] Margin-of-victory Elo with K-factor decay
- [x] Model accuracy tracking (pick accuracy, spread error, confidence analysis)
- [x] Backtesting engine and parameter sweep optimization
- [x] Model regression tests with automated thresholds
- [x] ESPN scoreboard fallback for cloud deployments
- [x] NBA CDN backfill for API outages
- [x] Predictions-focused UI with immediate visibility

### Future Ideas
- [ ] Historical injury impact analysis (backtest accuracy)
- [ ] ML model using advanced stats
- [ ] Multi-sport expansion

### Technical Debt
- [ ] `src/data/odds_fetcher.py:192` - Better odds-to-game matching
- [ ] `src/data/odds_fetcher.py:284` - Add spread/total support
