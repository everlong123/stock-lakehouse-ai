import time, sys, cProfile, pstats, io
sys.path.insert(0, ".")
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.silver import SilverLayer

bf = BronzeLayer().read("AAPL")
print("rows:", len(bf))

pr = cProfile.Profile()
pr.enable()
sf, q = SilverLayer().transform(bf)
pr.disable()
s = io.StringIO()
pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(22)
print(s.getvalue()[:4000])
