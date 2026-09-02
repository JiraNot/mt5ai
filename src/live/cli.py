"""
CLI entry point for the auto-trading system.

Usage:
    # Start auto-trader in paper mode
    python -m src.live.cli start --mode PAPER

    # Run single scan
    python -m src.live.cli scan

    # Check status
    python -m src.live.cli status

    # Train ML model
    python -m src.live.cli train

    # Backtest
    python -m src.live.cli backtest --period 6mo
"""

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


def cmd_start(args):
    """Start auto-trading loop."""
    from src.live.auto_trader import AutoTrader

    trader = AutoTrader(
        mode=args.mode,
        symbol=args.symbol,
        scan_interval=args.interval,
    )
    trader.start()


def cmd_scan(args):
    """Run single market scan."""
    from src.live.auto_trader import AutoTrader

    trader = AutoTrader(mode=args.mode, symbol=args.symbol)
    trader.run_once()


def cmd_status(args):
    """Show trading status."""
    from src.live.auto_trader import AutoTrader

    trader = AutoTrader(mode=args.mode, symbol=args.symbol)
    trader.initialize()
    status = trader.get_status()

    print("\n" + "=" * 50)
    print("AUTO TRADER STATUS")
    print("=" * 50)
    for key, value in status.items():
        print(f"  {key:25s}: {value}")
    print("=" * 50)

    trader.stop()


def cmd_train(args):
    """Train ML model on trade history."""
    from src.ai.ml_trainer import MLTrainer

    trainer = MLTrainer()

    if args.csv:
        X, y = trainer.load_from_csv(args.csv)
    else:
        X, y = trainer.load_dataset(args.db)

    if len(X) == 0:
        print("No training data found. Run paper trading first to collect data.")
        return

    results = trainer.train(X, y)
    print(trainer.generate_report())

    if results:
        trainer.save_model()
        print(f"\nModel saved to models/model.pkl")


def cmd_backtest(args):
    """Run backtest."""
    from scripts.backtest_real import run_backtest
    run_backtest(args.period, args.strategies)


def main():
    parser = argparse.ArgumentParser(description="MT5 AI Auto Trader")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start auto-trading loop")
    start_parser.add_argument("--mode", default="PAPER", choices=["PAPER", "DEMO", "LIVE"])
    start_parser.add_argument("--symbol", default="XAUUSD")
    start_parser.add_argument("--interval", type=int, default=60, help="Scan interval in seconds")

    # Scan command
    scan_parser = subparsers.add_parser("scan", help="Run single market scan")
    scan_parser.add_argument("--mode", default="PAPER", choices=["PAPER", "DEMO", "LIVE"])
    scan_parser.add_argument("--symbol", default="XAUUSD")

    # Status command
    status_parser = subparsers.add_parser("status", help="Show trading status")
    status_parser.add_argument("--mode", default="PAPER")
    status_parser.add_argument("--symbol", default="XAUUSD")

    # Train command
    train_parser = subparsers.add_parser("train", help="Train ML model")
    train_parser.add_argument("--db", default="trading.db", help="Database path")
    train_parser.add_argument("--csv", help="CSV file path")

    # Backtest command
    bt_parser = subparsers.add_parser("backtest", help="Run backtest")
    bt_parser.add_argument("--period", default="6mo", help="Data period (1mo, 3mo, 6mo, 1y, 2y)")
    bt_parser.add_argument("--strategies", nargs="+", default=["fvg_final"])

    args = parser.parse_args()

    if args.command == "start":
        cmd_start(args)
    elif args.command == "scan":
        cmd_scan(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "train":
        cmd_train(args)
    elif args.command == "backtest":
        cmd_backtest(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
