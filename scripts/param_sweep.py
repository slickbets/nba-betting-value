#!/usr/bin/env python3
"""CLI tool for running Elo parameter sweeps.

Usage:
    python scripts/param_sweep.py                            # Full sweep (2-3 params at a time)
    python scripts/param_sweep.py --quick                    # Smaller grid (~100 combos)
    python scripts/param_sweep.py --param k_factor 18 20 22  # Custom params
    python scripts/param_sweep.py --param k_factor 18 20 --param home_advantage 30 35 40
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import CURRENT_SEASON
from src.models.params import EloParams
from src.backtesting.engine import load_season_data, run_backtest
from src.backtesting.sweep import generate_param_grid, run_sweep


# ---------------------------------------------------------------------------
# Default sweep ranges
# ---------------------------------------------------------------------------

FULL_RANGES = {
    "k_factor": [15, 18, 20, 22, 25],
    "k_decay_max_multiplier": [1.0, 1.25, 1.5, 1.75, 2.0],
    "k_decay_games": [200, 300, 400, 500],
    "home_advantage": [25, 30, 35, 40, 50],
    "rest_b2b": [-35, -30, -25, -20, -15],
    "rest_2day": [0, 3, 5, 8, 10],
    "rest_3day": [5, 8, 10, 12, 15],
    "mov_min": [0.3, 0.5, 0.7],
    "mov_max": [2.0, 2.5, 3.0, 3.5],
    "spread_divisor": [20, 25, 28, 30],
    "season_regression_factor": [0.25, 0.33, 0.40, 0.50],
    "player_impact_scaling": [1.0, 1.25, 1.5, 1.75, 2.0],
}

QUICK_RANGES = {
    "k_factor": [18, 20, 22],
    "home_advantage": [30, 35, 40],
    "rest_b2b": [-30, -25, -20],
    "mov_max": [2.5, 3.0, 3.5],
    "spread_divisor": [23, 25, 28],
}

# Groups for full sweep (sweep 2-3 params at a time, others at production)
SWEEP_GROUPS = [
    ["k_factor", "k_decay_max_multiplier", "k_decay_games"],
    ["home_advantage", "spread_divisor"],
    ["rest_b2b", "rest_2day", "rest_3day"],
    ["mov_min", "mov_max"],
    ["season_regression_factor"],
]


def parse_args():
    parser = argparse.ArgumentParser(description="Elo parameter sweep")
    parser.add_argument("--quick", action="store_true",
                        help="Use smaller grid (~100 combos)")
    parser.add_argument("--param", nargs="+", action="append", default=[],
                        metavar="VALUE",
                        help="Custom param: --param name val1 val2 ...")
    parser.add_argument("--season", default=CURRENT_SEASON,
                        help=f"Season to backtest (default: {CURRENT_SEASON})")
    parser.add_argument("--workers", type=int, default=None,
                        help="Max parallel workers (default: CPU count)")
    parser.add_argument("--output-dir", default="data/sweep_results",
                        help="Directory for CSV output")
    return parser.parse_args()


def print_comparison(baseline_metrics, best_row):
    """Print comparison between production baseline and best sweep result."""
    print("\n" + "=" * 60)
    print("Production Baseline vs Best Sweep Result")
    print("=" * 60)

    metrics = [
        ("Pick Accuracy", f"{baseline_metrics.pick_accuracy:.1f}%",
         f"{best_row['pick_accuracy']:.1f}%"),
        ("Avg Spread Error", f"{baseline_metrics.avg_spread_error:.1f}",
         f"{best_row['avg_spread_error']:.1f}"),
        ("Brier Score", f"{baseline_metrics.brier_score:.4f}",
         f"{best_row['brier_score']:.4f}"),
        ("High Conf Acc", f"{baseline_metrics.high_conf_accuracy:.1f}%",
         f"{best_row['high_conf_accuracy']:.1f}%"),
    ]

    print(f"{'Metric':<20} {'Production':>12} {'Best Sweep':>12}")
    print("-" * 46)
    for name, prod_val, sweep_val in metrics:
        print(f"{name:<20} {prod_val:>12} {sweep_val:>12}")

    # Show which params differ from production
    prod = EloParams.production()
    prod_dict = {
        "k_factor": prod.k_factor,
        "k_decay_max_multiplier": prod.k_decay_max_multiplier,
        "k_decay_games": prod.k_decay_games,
        "home_advantage": prod.home_advantage,
        "spread_divisor": prod.spread_divisor,
        "season_regression_factor": prod.season_regression_factor,
        "mov_min": prod.mov_min,
        "mov_max": prod.mov_max,
        "rest_b2b": prod.rest_b2b,
        "rest_normal": prod.rest_normal,
        "rest_2day": prod.rest_2day,
        "rest_3day": prod.rest_3day,
        "player_impact_scaling": prod.player_impact_scaling,
    }

    changed = []
    for key, prod_val in prod_dict.items():
        if key in best_row and best_row[key] != prod_val:
            changed.append((key, prod_val, best_row[key]))

    if changed:
        print("\nChanged parameters:")
        for name, old, new in changed:
            print(f"  {name}: {old} -> {new}")
    else:
        print("\nProduction params are already optimal!")


def main():
    args = parse_args()

    # Load data
    print(f"Loading {args.season} data...")
    games_df, teams = load_season_data(args.season)
    if games_df.empty:
        print("No completed games found. Run daily_update.py first.")
        sys.exit(1)
    print(f"Loaded {len(games_df)} completed games")

    # Run production baseline
    print("\nRunning production baseline...")
    prod_params = EloParams.production()
    baseline = run_backtest(games_df, teams, prod_params)
    print(f"Baseline: {baseline.pick_accuracy:.1f}% accuracy, "
          f"{baseline.avg_spread_error:.1f} avg spread error, "
          f"Brier {baseline.brier_score:.4f}")

    # Build parameter grid
    if args.param:
        # Custom params from CLI
        overrides = {}
        for p in args.param:
            name = p[0]
            values = [float(v) for v in p[1:]]
            overrides[name] = values
        groups = [overrides]
    elif args.quick:
        groups = [QUICK_RANGES]
    else:
        # Full sweep: run each group separately
        groups = [{k: FULL_RANGES[k] for k in group} for group in SWEEP_GROUPS]

    # Run sweeps
    all_results = []
    for i, overrides in enumerate(groups):
        grid = generate_param_grid(overrides)
        param_names = ", ".join(overrides.keys())
        print(f"\nSweep {i+1}/{len(groups)}: {param_names} ({len(grid)} combos)")

        start = time.time()
        results = run_sweep(games_df, teams, grid, n_workers=args.workers)
        elapsed = time.time() - start
        print(f"  Completed in {elapsed:.1f}s")

        # Show top 3 for this group
        for j, row in results.head(3).iterrows():
            changed = {k: row[k] for k in overrides if row[k] != getattr(prod_params, k)}
            print(f"  #{j+1}: {row['pick_accuracy']:.1f}% acc, "
                  f"{row['avg_spread_error']:.1f} spread err — {changed}")

        all_results.append(results)

    # Combine and save
    combined = pd.concat(all_results, ignore_index=True)
    combined = combined.sort_values("pick_accuracy", ascending=False).reset_index(drop=True)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"sweep_{timestamp}.csv"
    combined.to_csv(output_path, index=False)
    print(f"\nResults saved to {output_path}")

    # Print top 10 overall
    print("\n" + "=" * 60)
    print("Top 10 Results by Pick Accuracy")
    print("=" * 60)
    display_cols = ["pick_accuracy", "avg_spread_error", "brier_score",
                    "high_conf_accuracy"]
    # Add sweep param columns that vary
    param_cols = [c for c in combined.columns if c not in display_cols
                  and c not in ["total_games", "high_conf_games", "med_conf_accuracy",
                                "low_conf_accuracy", "avg_total_error",
                                "median_spread_error"]]
    for _, row in combined.head(10).iterrows():
        changed = {k: row[k] for k in param_cols
                   if hasattr(prod_params, k) and row[k] != getattr(prod_params, k)}
        print(f"  {row['pick_accuracy']:.1f}% | spread {row['avg_spread_error']:.1f} | "
              f"brier {row['brier_score']:.4f} | hi-conf {row['high_conf_accuracy']:.1f}% | "
              f"{changed if changed else 'PRODUCTION'}")

    # Compare best to production
    best = combined.iloc[0]
    print_comparison(baseline, best)

    print(f"\nTotal combinations tested: {len(combined)}")


if __name__ == "__main__":
    main()
