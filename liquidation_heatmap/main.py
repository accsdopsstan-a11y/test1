import argparse

from .config import ComputationConfig
from .pipeline import pretty_print, run_sync


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute liquidation heatmap levels for a symbol.")
    parser.add_argument("symbol", type=str, help="Symbol to process, e.g. BTCUSDT")
    parser.add_argument("--intensity-threshold", type=float, default=0.1)
    parser.add_argument("--probability-threshold", type=float, default=0.1)
    parser.add_argument("--max-levels", type=int, default=5)
    parser.add_argument("--time-horizon", type=int, default=60, help="Minutes to consider for cascade probability")
    parser.add_argument("--sensitivity", type=float, default=1.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = ComputationConfig(
        intensity_threshold=args.intensity_threshold,
        probability_threshold=args.probability_threshold,
        max_levels=args.max_levels,
        time_horizon_minutes=args.time_horizon,
        sensitivity=args.sensitivity,
    )
    result = run_sync(args.symbol, config)
    pretty_print(result)


if __name__ == "__main__":
    main()
