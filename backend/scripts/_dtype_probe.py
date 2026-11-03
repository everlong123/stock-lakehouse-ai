import sys
sys.path.insert(0, ".")
import pandas as pd
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.session import canonicalize_daily_sessions

bf = BronzeLayer().read("AAPL")
print("bronze dtypes:")
print(bf.dtypes)
out, rep = canonicalize_daily_sessions(bf)
print("\ncanonical out dtypes (slow path):")
print(out.dtypes)
print("\nreport:", rep)
print("\nbronze nulls:", bf[["open","high","low","close","volume","timestamp"]].isna().any(axis=1).sum())
print("dup days:", len(bf) - bf.groupby(["symbol", bf["timestamp"].dt.date]).ngroups)
