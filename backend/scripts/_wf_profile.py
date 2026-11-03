import sys, time, cProfile, pstats, io
sys.path.insert(0, ".")
from app.backtesting.walk_forward import WalkForwardValidator

pr = cProfile.Profile()
pr.enable()
res = WalkForwardValidator().run(symbol="AAPL", strategy_name="rsi_strategy")
pr.disable()
s = io.StringIO()
ps = pstats.Stats(pr, stream=s).sort_stats("cumulative")
ps.print_stats(22)
print(s.getvalue())
