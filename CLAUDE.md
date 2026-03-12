# NBA Game Predictions - Project Context

## What This Project Does
Predicts NBA game outcomes using an Elo rating system. Shows win probabilities, predicted spreads, and totals for each game, with injury and rest adjustments. Tracks model accuracy over time.

## Architecture

```
app/                    → Streamlit UI (main.py + pages/)
  main.py                → Predictions landing page (today's picks + accuracy)
  shared.py              → Global CSS (dark theme), sidebar, confidence/result badge helpers
  pages/1_Game_Details.py → Detailed Elo breakdowns, injuries, rest, odds
  pages/2_Model_Accuracy.py → Model prediction tracking
  pages/3_Team_Ratings.py → Team Elo rankings
  pages/4_Donate.py       → Donation page (Cash App + Venmo)
src/data/               → Data fetching (BDL primary, ESPN/NBA API fallback)
src/models/             → Predictions (Elo ratings, player impact, rest factors, params)
src/backtesting/        → Backtest engine, parameter sweep
src/betting/            → Value detection, odds conversion
src/utils/              → Lightweight utilities (update status, live scores, feedback)
scripts/                → CLI tools (init_db, daily_update, backfill, param_sweep)
data/                   → SQLite DB (NOT in git) + sweep_results/
config.py               → All configuration constants + now_ct() timezone helper
.streamlit/config.toml  → Dark theme config (bg #141414, accent #C9A84C)
```

## Key Files

| File | Purpose |
|------|---------|
| `src/models/elo.py` | Elo rating calculations (composite + O/D Elo) |
| `src/models/predictor.py` | Game predictions with injury/rest/O-D adjustments |
| `src/models/player_impact.py` | Player impact for injury adjustments (DB-only, USG%-weighted) |
| `src/models/rest_factor.py` | Back-to-back and rest day Elo adjustments |
| `src/models/params.py` | EloParams frozen dataclass (all tunable parameters) |
| `src/data/bdl_fetcher.py` | BallDontLie API client — games, stats, odds, injuries, standings |
| `src/data/database.py` | SQLite operations (teams, games, player_impact tables) |
| `src/data/injury_fetcher.py` | Injuries (BDL primary, ESPN fallback) |
| `src/data/nba_fetcher.py` | DEPRECATED: NBA API + ESPN fallback (kept for local use) |
| `src/data/odds_fetcher.py` | Odds (BDL primary, The Odds API fallback) |
| `src/utils/live_scores.py` | Auto-refresh live scores from ESPN (cached 60s) |
| `src/utils/feedback.py` | Submit feedback to Linear via GraphQL API |
| `scripts/daily_update.py` | Daily refresh (results, Elo, predictions, odds, player impact) |
| `scripts/rebuild_elo.py` | Full Elo rebuild: composite + O/D from scratch |
| `scripts/backfill_od_elo.py` | Rebuild O/D Elo only by replaying season games |
| `scripts/backfill_missing_days.py` | Backfill from NBA CDN when API is down |
| `src/backtesting/engine.py` | Backtest engine: replays season, measures accuracy |
| `src/backtesting/sweep.py` | Parameter grid + parallel sweep execution |
| `Dockerfile` | Production container image |
| `fly.toml` | Fly.io app configuration |
| `.github/workflows/deploy.yml` | CI/CD: test + deploy on push to main |

## How to Run

```bash
/opt/homebrew/bin/python3.11 scripts/daily_update.py          # Daily update
/opt/homebrew/bin/python3.11 scripts/daily_update.py --force   # Force re-run
/opt/homebrew/bin/python3.11 scripts/rebuild_elo.py --all      # Full Elo rebuild
/opt/homebrew/bin/python3.11 scripts/backfill_od_elo.py --season 2025-26
/opt/homebrew/bin/python3.11 -m streamlit run app/main.py      # Launch UI
/opt/homebrew/bin/python3.11 -m pytest tests/ -v               # Run tests
/opt/homebrew/bin/python3.11 scripts/param_sweep.py --quick    # Quick sweep (~243 combos)
```

## Deployment (Fly.io)

App runs on Fly.io (`ord` region) with persistent volume for SQLite. Pushes to `main` trigger GitHub Actions (test + deploy).

- **App**: `nba-predictions-slick` at slick-bets.com
- **Machine**: shared-cpu-1x, 1024 MB RAM, Streamlit on port 8501
- **Volume**: `nba_data` (1 GB) mounted at `/data` — holds `nba_betting.db` and `.last_daily_update`
- **Cron**: `daily_update.py` at 14:00 + 15:00 UTC (~9 AM CT)
- **Env vars**: `DATA_DIR=/data`, `DB_PATH=/data/nba_betting.db` (defaults to local `data/` for dev)
- **DB not in git** — seeded to volume via `fly sftp shell`

```bash
fly deploy                                                    # Manual deploy
fly ssh console -C "/usr/local/bin/python /app/scripts/daily_update.py --force"  # Run update
fly ssh console -C "cat /data/daily_update.log"                                  # View logs
fly status                                                     # Check status
```

**Operational gotchas:**
- `fly ssh console -C` doesn't support shell builtins (`cd`) — always use absolute paths
- SSH sessions timeout after ~10 min for long-running commands
- Cron doesn't inherit Fly.io secrets — `start_production.sh` exports keys to `/etc/environment`, cron jobs source it
- Only use `/etc/cron.d/` for cron (not also `crontab`) — dual registration causes double runs
- OOM history: 256→512→1024 MB. Concurrent Streamlit + player impact fetch needs ≥1024 MB

**Local automation (legacy):** launchd plist at `~/Library/LaunchAgents/com.nba-betting-value.daily-update.plist`

## Elo System Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| K-factor (base) | 14 | Sweep-optimized (was 15) |
| K-factor (season start) | 28 | 2.0x base, decays over 300 games |
| Home advantage | 25 Elo (~1.4 pts) | Sweep-optimized (was 35) |
| Spread divisor | 18 | 18 Elo = 1 point (was 25) |
| Season regression | 33% toward 1500 | Accounts for roster turnover |
| MOV adjustment | Yes | `ln(margin+1) * (2.2 / (elo_diff*0.001 + 2.2))`, clamped [0.5, 3.0] |
| B2B penalty | -35 Elo (~1.9 pts) | Sweep-optimized (was -25) |
| Rest bonus (2d/3d+) | +5/+8 Elo | Applied at prediction time |
| League avg score | 115.5 | Auto-updated from DB at runtime |

**Key formulas:**
```
Win prob:   P = 1 / (1 + 10^((Opp_Elo - Your_Elo - HCA) / 400))
O/D score:  Expected = LEAGUE_AVG + (Off_Elo - Opp_Def_Elo) / 25 + HCA_pts
Player:     elo_impact = NET_RATING * (MPG/48) * (USG%/0.20) * 1.5  [clamped >= 0]
Injury:     Elo adjustment = -abs(elo_impact) * status_multiplier
            (Out: 1.0, Doubtful: 0.8, Questionable: 0.5, DTD: 0.3, Probable: 0.1)
```

## API Keys (in .env)

| Key | Purpose | Required |
|-----|---------|----------|
| `BALLDONTLIE_API_KEY` | BallDontLie GOAT tier — primary data source | Required |
| `ODDS_API_KEY` | The Odds API (fallback for odds) | Optional |
| `LINEAR_API_KEY` | Linear feedback integration | Optional |

## Data Sources

| Data | Primary Source | Fallback | Frequency |
|------|---------------|----------|-----------|
| Games & Scores | BallDontLie API | ESPN scoreboard | daily_update.py |
| Injuries | BallDontLie API | ESPN injuries API | daily_update.py |
| Live Status | BallDontLie live box scores | ESPN scoreboard | Page load |
| Odds | BallDontLie v2/odds | The Odds API | Page load |
| Player Impact | BallDontLie stats/advanced | — | daily_update.py (every 3 days) |
| W/L Records | BallDontLie standings | ESPN standings | Team Ratings page (cached 1hr) |

## Known Limitations

- **Player impact**: Uses `season_averages/general?type=advanced` (~7s) + `players/active` for team mapping. Runs every 3 days via staleness check.
- **Home spread bias**: Reduced by sweep (HCA lowered from 35→25, DIV from 25→18).
- **O/D Elo drift**: Offense avg ~1471, Defense avg ~1529. Structural; total conserved at 3000.
- **O/D total correlation**: r=0.233 game-level (single-game variance too high).
- **Season change**: Run `scripts/rebuild_elo.py --all` after changing seasons.
- **Deprecated**: `nba_fetcher.py` — kept as local/fallback. `backfill_history.py` — use `rebuild_elo.py` instead.

## Streamlit HTML Warning

**CRITICAL**: Never use indented multi-line f-strings for HTML in `st.markdown()`. Streamlit treats 4+ leading spaces as code blocks, rendering raw HTML in production. Always use single-line concatenated strings:
```python
# WRONG - will show raw HTML
st.markdown(
    f"""
    <div class="card">
        <div class="title">{value}</div>
    </div>
    """, unsafe_allow_html=True)

# CORRECT
st.markdown(
    f'<div class="card">'
    f'<div class="title">{value}</div>'
    f'</div>',
    unsafe_allow_html=True)
```

## Technical Debt

- `odds_fetcher.py:281` — Add spread/total support in `get_best_odds()`
- `daily_update.py` silently degrades when API keys are missing — needs fail-fast + startup validation (SLB-17)

## Future Ideas

- Lineups endpoint for starter/bench injury weighting (SLB-18)
- Leaders endpoint for player impact validation (SLB-19)
- Historical injury impact analysis
- ML model using advanced stats
- Multi-sport expansion
