# NBA Betting Value Finder

A Python application that finds value bets by comparing Elo-based predictions to sportsbook odds.

## Features

- **Elo Rating System**: Track team strength using Elo ratings updated after each game
- **Win Probability Predictions**: Convert Elo differences to win probabilities and point spreads
- **Live Odds Integration**: Fetch current odds from major sportsbooks via The Odds API
- **Value Bet Detection**: Identify bets where model probability exceeds implied odds probability
- **Bet Tracking**: Log bets, track results, and monitor performance over time
- **Interactive Dashboard**: Streamlit UI for exploring predictions and managing bets

## Quick Start

### 1. Install Dependencies

```bash
cd nba-betting-value
pip install -r requirements.txt
```

### 2. Configure API Key (Optional)

Sign up at [The Odds API](https://the-odds-api.com) for live odds data (free tier: 500 requests/month).

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
│   ├── main.py            # Main dashboard
│   └── pages/             # Multi-page app
│       ├── 1_Today_Bets.py
│       ├── 2_Bet_Log.py
│       ├── 3_Performance.py
│       └── 4_Team_Ratings.py
│
├── src/                    # Core logic
│   ├── data/              # Data fetching & storage
│   │   ├── database.py
│   │   ├── nba_fetcher.py
│   │   └── odds_fetcher.py
│   ├── models/            # Prediction models
│   │   ├── elo.py
│   │   └── predictor.py
│   └── betting/           # Betting utilities
│       ├── odds_converter.py
│       └── value_finder.py
│
├── scripts/               # CLI scripts
│   ├── init_db.py
│   ├── backfill_history.py
│   └── daily_update.py
│
├── tests/                 # Unit tests
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
- Home court adds 100 Elo points (~4 point spread advantage)

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

### Value Betting

A bet has value when:
```
Model_Probability > Implied_Probability_from_Odds
```

For example:
- Model says Team A has 60% win chance
- Sportsbook offers +120 odds (45.5% implied)
- Edge = 60% - 45.5% = 14.5%

The app flags bets with >3% edge.

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
5. Fetches current odds
6. Auto-settles completed bets

### Find Value Bets

1. Open the app: `streamlit run app/main.py`
2. Go to "Today's Bets" page
3. Review games with positive edge
4. Log bets you place in "Bet Log"
5. Track performance in "Performance" page

## Configuration

Edit `config.py` to adjust:

```python
# Elo Parameters
ELO_K_FACTOR = 20.0           # Rating volatility
ELO_HOME_ADVANTAGE = 100.0    # Home court bonus
ELO_INITIAL_RATING = 1500.0   # Starting rating

# Value Bet Thresholds
MIN_EDGE_PERCENT = 3.0        # Minimum edge to flag
MIN_ODDS = -300               # Don't bet heavy favorites
MAX_ODDS = 500                # Don't bet extreme underdogs
```

## Running Tests

```bash
pytest tests/ -v
```

## Limitations

- Elo is a simple model - historical accuracy is ~60-65% on straight predictions
- This is for educational purposes - no guarantee of profit
- The Odds API free tier has limited requests (500/month)
- RAPTOR player impact data requires manual updates (see `data/raptor_current.csv`)

## Roadmap

### Completed
- [x] Elo rating system with home court advantage
- [x] Win probability and spread predictions
- [x] Live odds integration (The Odds API)
- [x] Value bet detection with Kelly sizing
- [x] Bet tracking and auto-settlement
- [x] Streamlit dashboard
- [x] **Player injury adjustments** - Adjust Elo based on injured players using RAPTOR impact values

### In Progress
*(nothing currently)*

### Up Next
- [ ] **Back-to-back / rest day factors** - Reduce team Elo when on second night of back-to-back, boost when well-rested
- [ ] **Enable margin-of-victory Elo** - Code exists in `elo.py` (`update_elo_with_mov`), just needs to be wired up
- [ ] **Spread/total predictions** - Extend value finder to analyze spread and over/under markets

### Future Ideas
- [ ] Calculate own player impact metric from box scores (replace estimated RAPTOR)
- [ ] Historical injury impact analysis (backtest accuracy)
- [ ] ML model using advanced stats (scikit-learn already in requirements)
- [ ] Better odds-to-game ID matching in odds_fetcher.py
- [ ] Multi-sport expansion

### Technical Debt
- [ ] `src/data/odds_fetcher.py:192` - Match odds to internal game_id using teams + date
- [ ] `src/data/odds_fetcher.py:284` - Add spread/total support in `get_best_odds()`
