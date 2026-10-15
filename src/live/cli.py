"""Compatibility CLI that delegates trading commands to the Binance runtime."""

from __future__ import annotations

import argparse
import sys


def _run_platform(*arguments: str) -> None:
    """Run the current platform entrypoint with the requested runtime flags."""
    from src.app import main as platform_main

    original_argv = sys.argv
    try:
        sys.argv = ["freebuff-trade", *arguments]
        platform_main()
    finally:
        sys.argv = original_argv


def _train(args: argparse.Namespace) -> None:
    from src.ai.ml_trainer import MLTrainer

    trainer = MLTrainer()
    if args.csv:
        features, labels = trainer.load_from_csv(args.csv)
    else:
        features, labels = trainer.load_dataset(args.db)
    if len(features) == 0:
        print("No training data found. Run paper trading first to collect data.")
        return
    if trainer.train(features, labels):
        trainer.save_model()
        print("\nModel saved to models/model.pkl")
    print(trainer.generate_report())


def main() -> None:
    parser = argparse.ArgumentParser(description="Binance AI Trading Platform")
    commands = parser.add_subparsers(dest="command")

    start = commands.add_parser("start", help="Start the Binance trading runtime")
    start.add_argument("--cycles", type=int, default=None)
    commands.add_parser("scan", help="Run one evaluation cycle")
    commands.add_parser("status", help="Show Binance platform status")

    train = commands.add_parser("train", help="Train the ML model")
    train.add_argument("--db", default="trading.db", help="Dataset path")
    train.add_argument("--csv", help="CSV dataset path")

    backtest = commands.add_parser("backtest", help="Run the configured backtest")
    backtest.add_argument("--period", default="6mo")
    backtest.add_argument("--strategies", nargs="+", default=["fvg_final"])

    args = parser.parse_args()
    if args.command == "start":
        flags = ("--cycles", str(args.cycles)) if args.cycles is not None else ()
        _run_platform(*flags)
    elif args.command == "scan":
        _run_platform("--cycles", "1")
    elif args.command == "status":
        _run_platform("--status")
    elif args.command == "backtest":
        _run_platform("--backtest")
    elif args.command == "train":
        _train(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
