import time, os, sys
sys.path.insert(0, r"d:\School\kltn\stock-lakehouse-ai\backend")
os.chdir(r"d:\School\kltn\stock-lakehouse-ai\backend")

from app.lakehouse.gold import GoldLayer
from app.backtesting.strategies import STRATEGY_MAP
from app.backtesting.portfolio import Portfolio
from app.backtesting.metrics import compute_metrics, drawdown_series
import pandas as pd

t0=time.time(); frame = GoldLayer().read("AAPL"); print("1. gold read: %.1fs" % (time.time()-t0))

t0=time.time()
sig = STRATEGY_MAP["ma_crossover"](parameters={}).generate_signals(frame)
print("2. signals: %.1fs" % (time.time()-t0))

t0=time.time()
portfolio = Portfolio(initial_capital=10000, cash=10000)
exec_sig = sig.shift(1).fillna(0)
for index in range(len(frame)):
    row = frame.iloc[index]
    exec_price = float(row["open"]) if pd.notna(row["open"]) else float(row["close"])
    signal = float(exec_sig.iloc[index])
    ts = row["timestamp"]
    if signal > 0:
        portfolio.buy(ts, exec_price, 0.001, 0.0005)
    elif signal < 0:
        portfolio.sell(ts, exec_price, 0.001, 0.0005)
    portfolio.mark_to_market(ts, float(row["close"]))
print("3. loop: %.1fs" % (time.time()-t0))

t0=time.time(); m = compute_metrics(portfolio.equity_curve, portfolio.realized_trades, 10000); print("4. metrics: %.1fs" % (time.time()-t0))

# now the write_json of the full result
from app.lakehouse.local_storage import LocalStorageBackend
res = {"equity_curve":[{"timestamp":str(p["timestamp"]),"equity":float(p["equity"]),"price":float(p["price"])} for p in portfolio.equity_curve],
       "drawdown":[{"timestamp":str(p["timestamp"]),"drawdown":float(p["drawdown"])} for p in drawdown_series(portfolio.equity_curve)]}
t0=time.time(); LocalStorageBackend().write_json("backtests","AAPL_ma_crossover_latest.json",res); print("5. write_json: %.1fs" % (time.time()-t0))

# mysql persist
t0=time.time()
from app.database.session import check_database_connection
from app.database.repositories.backtest_repository import BacktestRepository
from app.database.session import get_session_factory
print("6. db conn check: %.1fs -> %s" % (time.time()-t0, check_database_connection()))
t0=time.time()
db = get_session_factory()()
try:
    BacktestRepository(db).create({"symbol":"AAPL","strategy":"ma_crossover","start_date":None,"end_date":None,
        "initial_capital":10000,"final_capital":10000,"total_return":0.0,"win_rate":0.0,"sharpe_ratio":0.0,
        "maximum_drawdown":0.0,"number_of_trades":0,"profit_factor":0.0,"parameters":"{}"})
    db.commit()
    print("7. mysql insert: %.1fs" % (time.time()-t0))
except Exception as e:
    print("7. mysql insert FAILED after %.1fs: %s" % (time.time()-t0, e))
finally:
    db.close()
