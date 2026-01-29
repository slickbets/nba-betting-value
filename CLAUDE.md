# NBA Betting Value Finder - Project Context

## What This Project Does
Finds value bets by comparing Elo-based win probability predictions to sportsbook odds. If our model says a team has a 60% chance to win but the odds imply 45%, that's a value bet.

## Architecture

```
app/                    → Streamlit UI (main.py + pages/)
src/data/               → Data fetching (NBA API, odds, injuries)
src/models/             → Predictions (Elo ratings, player impact, rest factors)
src/betting/            → Value detection, odds conversion
src/utils/              → Lightweight utilities (update status)
scripts/                → CLI tools (init_db, daily_update, backfill)
data/                   → SQLite DB
config.py               → All configuration constants
```

## Key Files

| File | Purpose |
|------|---------|
| `src/models/elo.py` | Elo rating calculations (composite + O/D Elo) |
| `src/models/predictor.py` | Game predictions with injury/rest/O-D adjustments |
| `src/models/player_impact.py` | Player impact for injury adjustments (DB-only, USG%-weighted) |
| `src/models/rest_factor.py` | Back-to-back and rest day Elo adjustments |
| `src/data/database.py` | SQLite operations (teams, games, player_impact tables) |
| `src/data/injury_fetcher.py` | Fetches injuries from ESPN API |
| `src/data/nba_fetcher.py` | Fetches games/scores/player stats from NBA API |
| `src/data/odds_fetcher.py` | Fetches live odds from The Odds API |
| `src/betting/value_finder.py` | Identifies value betting opportunities |
| `app/pages/1_Today_Bets.py` | Main UI for finding today's value bets |
| `app/pages/5_Model_Accuracy.py` | Track model prediction accuracy |
| `scripts/daily_update.py` | Daily refresh script (results, Elo, predictions, odds, player impact) |
| `scripts/backfill_od_elo.py` | Rebuild O/D Elo by replaying all season games |
| `scripts/run_daily_update.sh` | Wrapper script for launchd automation |
| `src/utils/update_status.py` | Check daily update status (lightweight, no heavy imports) |

## How to Run

```bash
# Daily update runs automatically via launchd (see below)
# To run manually:
/opt/homebrew/bin/python3.11 scripts/daily_update.py

# Force run even if already ran today:
/opt/homebrew/bin/python3.11 scripts/daily_update.py --force

# Rebuild O/D Elo from historical games (run after season change or to fix data):
/opt/homebrew/bin/python3.11 scripts/backfill_od_elo.py --season 2025-26

# Launch UI
/opt/homebrew/bin/python3.11 -m streamlit run app/main.py

# Run tests
/opt/homebrew/bin/python3.11 -m pytest tests/ -v
```

## Automated Daily Updates

Daily updates run automatically via macOS launchd:

| Trigger | When |
|---------|------|
| RunAtLoad | On login |
| StartCalendarInterval | 9:00 AM (if awake) |
| StartInterval | Every 2 hours (catches wake from sleep) |

The script has an "already ran today" check, so it only does real work once per day.

**Files:**
- Plist: `~/Library/LaunchAgents/com.nba-betting-value.daily-update.plist`
- Wrapper: `scripts/run_daily_update.sh`
- Logs: `~/Library/Logs/nba-betting-update.log`
- Run marker: `data/.last_daily_update`

**Management commands:**
```bash
# View logs
tail -50 ~/Library/Logs/nba-betting-update.log

# Disable automation
launchctl unload ~/Library/LaunchAgents/com.nba-betting-value.daily-update.plist

# Re-enable automation
launchctl load ~/Library/LaunchAgents/com.nba-betting-value.daily-update.plist

# Check status
launchctl list | grep nba-betting
```

## Recent Changes (Late January 2026)

**Player Impact Formula Overhaul:**
- Added USG% weighting to reduce team-context bias in NET_RATING
- New formula: `elo_impact = NET_RATING × (MPG / 48) × (USG% / 0.20) × 1.5`
  - `USG% / 0.20`: Usage weighting (20% is ~league avg) - separates stars from role players who inflate NET_RATING by playing on good/bad teams
  - Before: Alex Caruso (OKC) had +19.4 impact (inflated by OKC's dominance)
  - After: Alex Caruso has +8.5 impact (properly reflects his role player status)
  - SGA stays at +26.5 (high usage star correctly weighted)
- New `usg_pct` column stored in `player_impact` database table
- Files: `src/data/nba_fetcher.py`, `src/data/database.py`, `scripts/daily_update.py`

**Negative-Impact Player Fix:**
- Players with negative NET_RATING no longer penalize their team when injured
- `get_player_elo_impact()` clamps negative values to 0
- Rationale: if a player hurts the team when playing (negative NET_RATING), losing them shouldn't make the team's Elo worse
- Example: Russell Westbrook (SAC, -13.8 raw impact) now returns 0 instead of penalizing Sacramento when he's out
- File: `src/models/player_impact.py`

**Lowered Games Played Minimum:**
- Changed from 15 GP to 10 GP to qualify for player_impact database
- Captures players returning from injury: Trae Young (10 GP), Tyler Herro (11 GP), Zach Edey (11 GP)
- Now 320 qualified players (up from 312)
- File: `src/data/nba_fetcher.py`

**Removed RAPTOR CSV Fallback:**
- Deleted the stale `data/raptor_current.csv` fallback system entirely
- The CSV was prior-season data for 60 players, causing false matches
  - Bug: "Terrance Shannon Jr." matched "Jaren Jackson Jr." via last-name "jr" suffix matching, giving a bench player -40 Elo impact
- Player impact is now DB-only; players not in DB get 0 impact (conservative)
- Removed: `load_raptor_data()`, `get_player_raptor_from_csv()`, `RAPTOR_TO_ELO_FACTOR`, `RAPTOR_CSV_PATH`
- Simplified internal API: `get_player_elo_impact()` returns Elo impact directly (no more divide-by-10-then-multiply-by-10 RAPTOR conversion)
- File: `src/models/player_impact.py`

**Updated Home Court Advantage:**
- Changed from 67.5 Elo (~2.7 points) to 35 Elo (~1.4 points)
- Based on 2025-26 season analysis (729 games): actual home margin is +1.36 points
- Previous setting caused +3.9 point systematic home team bias in spread predictions
- File: `config.py` - `ELO_HOME_ADVANTAGE`

**Elo System Validation (729 games, 2025-26):**
- Composite Elo vs Win%: r = 0.907, vs Point Diff: r = 0.963
- Offense Elo vs actual PPG: r = 0.926
- Defense Elo vs actual Opp PPG: r = -0.969
- Predicted totals vs actual: r = 0.233 (weak - single-game variance too high)
- Overall pick accuracy: 63.1%, scales with confidence (80%+ picks hit 79.7%)
- Close-game luck explains largest Elo-vs-record divergences (e.g., Charlotte 1-9 in games within 5 pts)

## Earlier Changes (January 2026)

**Season Configuration Fixed:**
- Updated `CURRENT_SEASON` from "2024-25" to "2025-26" in config.py
- Database had mixed season data; now properly using 2025-26 season only
- Player impact data cleared and refreshed for correct season (311 players)

**O/D Elo Backfill Script:**
- New script: `scripts/backfill_od_elo.py`
- Resets all O/D Elo to 1500 and replays season games chronologically
- Applies proper K-factor decay and game-by-game updates
- Use instead of API seeding for consistent methodology with composite Elo
- Run with: `/opt/homebrew/bin/python3.11 scripts/backfill_od_elo.py --season 2025-26`
- Options: `--dry-run` to preview without saving

**Offensive/Defensive Elo System:**
- Split single Elo into separate Offensive Elo (O-Elo) and Defensive Elo (D-Elo)
- Each team now has 3 ratings: `current_elo` (composite), `offense_elo`, `defense_elo`
- O/D Elo updated after each game based on scoring vs expectations
- Enables predicted totals calculation (not just spreads)
- Formula: `Expected_Score = 114.5 + (O_Elo - Opp_D_Elo) / 25`
- Feature flag `USE_OD_ELO` in config.py (defaults to True)
- Files: `src/models/elo.py`, `src/data/database.py`, `scripts/daily_update.py`, `config.py`
- **Recommended:** Use `backfill_od_elo.py` to build O/D Elo from game history (consistent with composite Elo methodology)
- **Alternative:** Seed from NBA API ratings (quick but doesn't match our K-factor/MOV methodology):
  ```python
  from src.data.nba_fetcher import fetch_team_offensive_defensive_ratings
  from src.data.database import get_all_teams, update_team_od_elo
  od_df = fetch_team_offensive_defensive_ratings('2025-26')
  teams_df = get_all_teams()
  team_map = {r['abbreviation']: r['team_id'] for _, r in teams_df.iterrows()}
  for _, r in od_df.iterrows():
      if r['team_abbr'] in team_map:
          update_team_od_elo(team_map[r['team_abbr']], r['offense_elo'], r['defense_elo'])
  ```

**Auto-Calculated Player Impact:**
- Replaced manual 60-player CSV with auto-populated database table (`player_impact`)
- Fetches NET_RATING, MPG, GP, USG_PCT for 320 qualified players from NBA API (`leaguedashplayerstats`)
- Qualification: 15+ MPG and 10+ games played
- Formula: `elo_impact = NET_RATING × (MPG / 48) × (USG% / 0.20) × 1.5`
  - `NET_RATING`: Team's point differential per 100 possessions when player is on court
  - `MPG / 48`: Playing time factor (starter at 36 MPG = 0.75, bench at 18 MPG = 0.375)
  - `USG% / 0.20`: Usage weighting (league avg ~20%) - reduces team-context bias
  - `1.5`: Scaling factor to convert to Elo points
- Top players (2025-26): SGA (+26.5), Jokic (+19.4), Wembanyama (+17.2), Cade (+16.9)
- Negative-impact players clamped to 0 (losing a bad player shouldn't penalize the team)
- Includes fuzzy name matching (85% threshold) for injury report lookups
- DB-only (no CSV fallback); players not in DB get 0 impact
- Updated daily via `update_player_impact()` in daily_update.py
- Files: `src/data/nba_fetcher.py`, `src/models/player_impact.py`, `src/data/database.py`

**UI Updates for O/D Elo:**
- Game details expanders now show O-Elo and D-Elo for each team
- All Game Predictions table includes predicted total (when O/D Elo available)
- Prediction section shows predicted total alongside spread

**Updated Home Court Advantage (earlier):**
- Changed from 100 Elo (~3.5 points) to 67.5 Elo (~2.7 points)
- Later reduced to 35 Elo (~1.4 points) based on 2025-26 season analysis (see Late January 2026 changes)
- File: `config.py` - `ELO_HOME_ADVANTAGE`

**Automated Daily Updates:**
- Added launchd automation to run `daily_update.py` automatically
- Runs on login, at 9 AM, and every 2 hours (to catch wake from sleep)
- Script checks if already ran today to avoid duplicate work
- Added `--force` flag to override the daily check
- Files: `scripts/run_daily_update.sh`, `~/Library/LaunchAgents/com.nba-betting-value.daily-update.plist`

**Game Start Times on Today's Bets Page:**
- Added `game_time` column to games database table
- Displays game start times in Central Time (converted from ET)
- Shows "In Progress" for live games, "Final" for completed games
- Time displayed in Value Bets table, All Game Predictions table, and Game Details expanders
- Files: `src/data/database.py`, `src/data/nba_fetcher.py`, `app/pages/1_Today_Bets.py`

**Hide Started Games Filter:**
- Added checkbox to hide in-progress and final games from Value Bets section
- Enabled by default (since you can't bet on started games)
- Only affects Value Bets table, not All Game Predictions
- File: `app/pages/1_Today_Bets.py`

**Live Refresh for Game Status:**
- "Refresh Data" button now fetches fresh game data from NBA API
- Updates game statuses (scheduled → in_progress → final) in real-time
- No longer requires running daily_update.py to see status changes
- File: `app/pages/1_Today_Bets.py`

**Model Accuracy Page Improvements:**
- "When Picking Team to Win/Lose" tables now show data with fewer games
- Dynamic threshold: shows all teams when data is limited, filters to 3+ games when plentiful
- File: `app/pages/5_Model_Accuracy.py`

**Elo Model Improvements (Phase 1):**
- Enabled Margin of Victory (MOV) Elo - blowout wins now worth more than close games
- Added K-factor decay through season - early season K is 50% higher (more uncertainty)
- MOV multiplier: `ln(margin + 1) × (2.2 / (elo_diff × 0.001 + 2.2))`, clamped 0.5-3.0
- K-decay: Starts at 30 (1.5× base), decays linearly to 20 over first 400 league games
- Files: `src/models/elo.py`, `scripts/daily_update.py`

**Elo Model Improvements (Phase 2) - Rest Days:**
- Added back-to-back (B2B) penalty: -25 Elo (~1 point spread penalty)
- Added rest advantage: +5 Elo for 2 days rest, +8 Elo for 3+ days
- Rest adjustments applied at prediction time (not stored in team Elo)
- UI shows B2B alerts, rest columns in predictions table, rest details in game expanders
- Files: `src/models/rest_factor.py` (new), `src/models/predictor.py`, `src/data/database.py`, `app/pages/1_Today_Bets.py`

**Daily Update Status Indicator:**
- Shows when daily update last ran at top of Today's Bets page
- Green checkmark if ran today (with time), warning if outdated, error if never ran
- Timestamp now stored with full date and time in `data/.last_daily_update`
- Files: `src/utils/update_status.py` (new), `scripts/daily_update.py`, `app/pages/1_Today_Bets.py`

**Model Picks (Win/Loss) Section:**
- New section on Today's Bets page showing straight win/loss predictions
- Displays: Time, Matchup, Predicted Winner, Win Probability, Confidence, Spread
- Separate from Value Bets (which shows edge over sportsbook odds)
- Clarifies difference: Value Bets = mispriced odds, Model Picks = who model thinks will win
- File: `app/pages/1_Today_Bets.py`

## Recent Changes (January 2025)

**Switched Injury Data Source to ESPN:**
- Replaced `nbainjuries` package (was blocked by NBA, required Java)
- Now uses ESPN's free public API: `https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries`
- No API key required, no Java dependency
- File: `src/data/injury_fetcher.py`

**Model Accuracy Page Added:**
- New page: `app/pages/5_Model_Accuracy.py`
- Tracks pick accuracy (% correct winner predictions)
- Tracks spread error (how far off predicted spreads are)
- Accuracy by confidence level, by team, over time
- User-selectable time periods (7/14/30/60 days, season, custom)

**Fixed NBA API Score Fetching:**
- Was reading GameHeader table (no scores)
- Now reads LineScore table which has actual PTS values
- File: `src/data/nba_fetcher.py` - `fetch_games_by_date()`

**Predictions No Longer Overwrite:**
- Predictions only saved for games with status='scheduled'
- Games that have started keep their original pre-game prediction
- Important for accurate Model Accuracy tracking
- File: `src/models/predictor.py` - `predict_games_for_date()`

**Injury Tracking System:**
- Predictions adjust team Elo based on injured players
- Formula: `Elo adjustment = -abs(elo_impact) × status_multiplier`
  - Out: 1.0, Doubtful: 0.8, Questionable: 0.5, Day-to-Day: 0.3, Probable: 0.1
- Negative-impact players clamped to 0 (losing a bad player doesn't hurt the team)
- UI shows injury impact per game with icons (🏥 major, 🩹 moderate)
- Player impact sourced from database only (320 players, USG%-weighted)
- Players not in database get 0 adjustment (conservative fallback)

## Elo System Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| K-factor (base) | 20 | FiveThirtyEight methodology |
| K-factor (season start) | 30 | 1.5× base, decays over 400 games |
| Home advantage | 35 Elo | ~1.4 points spread (2025-26 actual) |
| Spread divisor | 25 | 25 Elo = 1 point |
| Season regression | 33% toward 1500 | Accounts for roster turnover |
| MOV adjustment | Yes | Blowouts worth more than close games |
| B2B penalty | -25 Elo | ~1 point spread penalty |
| Rest bonus (2d) | +5 Elo | Extra rest advantage |
| Rest bonus (3d+) | +8 Elo | Well-rested team cap |
| League avg score | 114.5 | For O/D Elo expected score calc |

Win probability formula:
```
P(win) = 1 / (1 + 10^((Opponent_Elo - Your_Elo - Home_Advantage) / 400))
```

MOV multiplier formula:
```
multiplier = ln(margin + 1) × (2.2 / (elo_diff × 0.001 + 2.2))
Clamped to range [0.5, 3.0]
```

O/D Elo expected score formula:
```
Expected_Score = LEAGUE_AVG + (Offense_Elo - Opponent_Defense_Elo) / 25 + Home_Advantage_Points
```

O/D Elo update formula (after game):
```
offense_change = (K / 2) × (actual_score - expected_score) / 10
defense_change = (K / 2) × (expected_opponent_score - actual_opponent_score) / 10
```

Player impact formula:
```
elo_impact = NET_RATING × (MPG / 48) × (USG% / 0.20) × 1.5
Negative values clamped to 0
```

## Current Priorities (from README Roadmap)

### Up Next
1. **Spread/total value betting** - Find value on spreads and totals (not just moneyline)
2. **Historical backtesting** - Validate O/D Elo and player impact accuracy on past seasons

### Recently Completed
- ✅ **Player impact USG% weighting** - Reduces team-context bias (Caruso 19→8, SGA stays 27)
- ✅ **Negative impact clamping** - Bad players no longer penalize team when injured
- ✅ **HCA recalibrated** - Reduced to 35 Elo based on actual 2025-26 data
- ✅ **RAPTOR CSV removed** - Eliminated stale fallback causing false matches
- ✅ **Elo validation analysis** - Confirmed strong correlations (r=0.96 vs pt diff)
- ✅ **O/D Elo backfill script** - Rebuild O/D Elo by replaying historical games
- ✅ **Offensive/Defensive Elo** - Separate O-Elo and D-Elo for better matchup modeling
- ✅ **Auto player impact** - Replaced manual CSV with NBA API-sourced ratings for 320+ players
- ✅ **Predicted totals** - O/D Elo enables total points predictions
- ✅ **Back-to-back / rest day factors** - B2B teams get -25 Elo penalty
- ✅ **Margin-of-victory Elo** - Blowout wins now worth more
- ✅ **K-factor decay** - Higher K early season for faster calibration

### Future Ideas
- Historical injury impact analysis (backtest accuracy)
- ML model using advanced stats
- Multi-sport expansion

### Technical Debt
- `odds_fetcher.py:192` - Better odds-to-game matching
- `odds_fetcher.py:284` - Add spread/total support

## API Keys (in .env)

| Key | Purpose | Required |
|-----|---------|----------|
| `ODDS_API_KEY` | The Odds API for live betting odds | Optional (but needed for value bets) |
| `BALLDONTLIE_API_KEY` | BallDontLie API (injuries endpoint is paid tier) | Not used currently |

## Data Sources

| Data | Source | Update Frequency |
|------|--------|------------------|
| Games & Scores | NBA API (`nba_api` package) | On daily_update.py run |
| Injuries | ESPN public API | On daily_update.py run |
| Odds | The Odds API | On page load (costs API credits) |
| Player Impact | NBA API (`leaguedashplayerstats`) | On daily_update.py run |
| Team O/D Elo | Calculated from game history | On backfill_od_elo.py run, then daily_update.py |

## Known Limitations

- Model is pre-game only (doesn't update with live scores)
- Only finds value on moneyline bets (spreads/totals not yet implemented)
- Odds API has limited free tier (500 requests/month)
- After changing seasons, must run `backfill_od_elo.py` to rebuild O/D Elo ratings
- O/D Elo predicted totals have weak game-level correlation (r=0.233) - single-game variance is too high
- Players with 0 GP this season (season-long injuries, mid-season acquisitions) have no impact data, which is correct since their absence is already baked into team Elo
- Some stars missing from NBA API Advanced stats endpoint entirely (Tatum, Irving, Haliburton, Lillard) - likely 0 GP this season
- NET_RATING still has residual team-context bias even with USG% weighting
