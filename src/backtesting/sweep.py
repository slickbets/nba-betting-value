"""Parameter sweep for finding optimal Elo model parameters.

Generates parameter grids and runs backtests in parallel using
ProcessPoolExecutor (CPU-bound work, GIL blocks threading).
"""

import itertools
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict

import pandas as pd

from src.models.params import EloParams
from src.backtesting.engine import run_backtest


def generate_param_grid(overrides: dict[str, list]) -> list[EloParams]:
    """Generate a Cartesian product of parameter values.

    Args:
        overrides: Dict mapping EloParams field names to lists of values to try.
            Fields not specified use production defaults.

    Returns:
        List of EloParams instances (one per combination).
    """
    prod = EloParams.production()
    prod_dict = asdict(prod)

    # Validate field names
    for key in overrides:
        if key not in prod_dict:
            raise ValueError(f"Unknown parameter: {key}. Valid: {sorted(prod_dict.keys())}")

    # Build ordered lists of (field_name, values)
    sweep_fields = sorted(overrides.keys())
    sweep_values = [overrides[k] for k in sweep_fields]

    # Cartesian product
    grid = []
    for combo in itertools.product(*sweep_values):
        param_dict = dict(prod_dict)  # start from production
        for field_name, value in zip(sweep_fields, combo):
            param_dict[field_name] = type(prod_dict[field_name])(value)
        grid.append(EloParams(**param_dict))

    return grid


def _run_single(args: tuple) -> dict:
    """Worker function for parallel sweep. Must be top-level for pickling."""
    games_df, teams, params, use_od_elo, include_rest = args
    metrics = run_backtest(games_df, teams, params, use_od_elo=use_od_elo,
                           include_rest=include_rest)
    result = asdict(params)
    result.update({
        "pick_accuracy": metrics.pick_accuracy,
        "avg_spread_error": metrics.avg_spread_error,
        "median_spread_error": metrics.median_spread_error,
        "brier_score": metrics.brier_score,
        "high_conf_accuracy": metrics.high_conf_accuracy,
        "high_conf_games": metrics.high_conf_games,
        "med_conf_accuracy": metrics.med_conf_accuracy,
        "low_conf_accuracy": metrics.low_conf_accuracy,
        "avg_total_error": metrics.avg_total_error,
        "total_games": metrics.total_games,
    })
    return result


def run_sweep(games_df: pd.DataFrame, teams: dict,
              param_grid: list[EloParams],
              use_od_elo: bool = True, include_rest: bool = True,
              n_workers: int | None = None) -> pd.DataFrame:
    """Run backtests for all parameter combinations in parallel.

    Args:
        games_df: Completed games DataFrame
        teams: Teams dict from load_season_data
        param_grid: List of EloParams to evaluate
        use_od_elo: Whether to use O/D Elo
        include_rest: Whether to include rest adjustments
        n_workers: Max parallel workers (None = cpu count)

    Returns:
        DataFrame with one row per parameter set, sorted by pick_accuracy desc
    """
    args = [(games_df, teams, p, use_od_elo, include_rest) for p in param_grid]

    results = []
    if n_workers == 1:
        # Sequential mode (useful for debugging)
        for a in args:
            results.append(_run_single(a))
    else:
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            results = list(pool.map(_run_single, args))

    df = pd.DataFrame(results)
    df = df.sort_values("pick_accuracy", ascending=False).reset_index(drop=True)
    return df
