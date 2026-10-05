"""Test notebook cells in a simulated way (shared namespace)."""

from pathlib import Path
import json

NB = Path("d:/School/kltn/stock-lakehouse-ai/docs/notebooks/lakehouse_demo.ipynb")
nb = json.loads(NB.read_text(encoding="utf-8"))

import sys
sys.path.insert(0, "d:/School/kltn/stock-lakehouse-ai/backend")

# Set matplotlib to non-interactive so show() doesn't try to open windows
import matplotlib
matplotlib.use("Agg")

# Shared namespace
ns = {"__name__": "__main__"}
ok, fail = [], []

for i, cell in enumerate(nb["cells"]):
    if cell["cell_type"] != "code":
        continue
    src = "\n".join(cell["source"])
    if not src.strip():
        continue
    print(f"\n--- Cell {i} ---")
    try:
        exec(compile(src, f"<cell-{i}>", "exec"), ns)
        ok.append(i)
        print(f"  -> OK")
    except Exception as e:
        print(f"  [FAIL] {type(e).__name__}: {str(e)[:200]}")
        fail.append((i, e))

print(f"\n=== Summary: {len(ok)} ok, {len(fail)} fail ===")
if fail:
    print("\nFailed cells:")
    for i, e in fail:
        print(f"  Cell {i}: {type(e).__name__}: {str(e)[:100]}")