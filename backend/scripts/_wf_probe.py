"""Time the walk-forward validation through the service layer.

Runs both strategies twice: the first call pays the child-process spawn
cost, the second uses the warm pool.
"""
import sys, time
sys.path.insert(0, ".")


def main():
    from app.services.backtest_service import WalkForwardService

    svc = WalkForwardService()
    for strat in ("ma_crossover", "rsi_strategy"):
        for attempt in (1, 2):
            t0 = time.time()
            res = svc.run({
                "symbol": "AAPL",
                "strategy": strat,
                "train_period_days": 180,
                "test_period_days": 30,
                "initial_capital": 10000,
            })
            label = "cold" if attempt == 1 else "warm"
            print(
                "%-14s %s %.2fs windows=%s"
                % (strat, label, time.time() - t0, res.get("summary", {}).get("total_windows"))
            )


if __name__ == "__main__":
    main()
