import sys
sys.path.insert(0, ".")
import pandas as pd
sys.path.insert(0, "scripts")
from _canonical_golden import reference_canonicalize
from app.lakehouse.bronze import BronzeLayer
from app.lakehouse.session import canonicalize_daily_sessions

bf = BronzeLayer().read("AAPL")
ref, _ = reference_canonicalize(bf)
new, _ = canonicalize_daily_sessions(bf)
print("ref dtypes:\n", ref[["timestamp", "ingestion_time"]].dtypes)
print("new dtypes:\n", new[["timestamp", "ingestion_time"]].dtypes)
print("\nref head:\n", ref[["timestamp", "ingestion_time"]].head(3))
print("\nnew head:\n", new[["timestamp", "ingestion_time"]].head(3))
print("\nsame values (ns-normalised)?")
r = pd.to_datetime(ref["timestamp"], utc=True)
n = pd.to_datetime(new["timestamp"], utc=True)
print("timestamp equal:", r.reset_index(drop=True).equals(n.reset_index(drop=True)))
r2 = pd.to_datetime(ref["ingestion_time"], utc=True)
n2 = pd.to_datetime(new["ingestion_time"], utc=True)
print("ingest equal:", r2.reset_index(drop=True).equals(n2.reset_index(drop=True)))
diff = r.reset_index(drop=True) != n.reset_index(drop=True)
print("timestamp differing rows:", int(diff.sum()))
if diff.any():
    idx = diff[diff].index[:5]
    print(pd.DataFrame({"ref": r.reset_index(drop=True)[idx], "new": n.reset_index(drop=True)[idx]}))
