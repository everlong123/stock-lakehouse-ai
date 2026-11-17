"""Cross-check that the backend and the frontend agree on a symbol's currency.

WHY this test exists
--------------------
The quote currency is resolved TWICE, in two languages:

  * ``backend/app/core/constants.py::currency_for_symbol``
  * ``frontend/src/utils/format.ts::currencyForSymbol``

The frontend needs its own copy because the stream endpoints return a bare
bar with no currency field, and the frontend cannot import from the backend
package. Two copies of a lookup table WILL drift - a suffix added to one and
not the other produces a wrong unit on screen for a whole market, which is
exactly the kind of error that looks plausible and is never caught by a
"does the page render" check.

So this test parses the TypeScript source and compares its suffix table
against the Python one, symbol by symbol, over the whole universe the
lakehouse actually serves.

Run it:

    cd backend
    .venv/Scripts/python.exe tests/test_currency_consistency.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.constants import (  # noqa: E402
    ALL_SYMBOLS,
    CRYPTO_SYMBOLS,
    VN_SYMBOLS,
    currency_for_symbol,
)

FRONTEND_FORMAT = ROOT.parent / "frontend" / "src" / "utils" / "format.ts"

# The suffix table the frontend declares, extracted from the TypeScript.
_TS_SUFFIX_BLOCK = re.compile(
    r"const bySuffix:\s*Record<string,\s*string>\s*=\s*\{(.*?)\}", re.DOTALL
)
_TS_SUFFIX_ENTRY = re.compile(r"(\w+)\s*:\s*\"(\w+)\"")


def frontend_suffix_table() -> dict[str, str]:
    """The suffix -> currency table declared in the frontend."""
    if not FRONTEND_FORMAT.exists():
        raise AssertionError(f"frontend format.ts not found at {FRONTEND_FORMAT}")
    source = FRONTEND_FORMAT.read_text(encoding="utf-8")
    match = _TS_SUFFIX_BLOCK.search(source)
    if not match:
        raise AssertionError(
            "could not find `const bySuffix: Record<string, string>` in "
            f"{FRONTEND_FORMAT}. If the frontend table was renamed or "
            "restructured, update the regex in this test to match."
        )
    return {m.group(1): m.group(2) for m in _TS_SUFFIX_ENTRY.finditer(match.group(1))}


def main() -> int:
    failures: list[str] = []

    # 1. The two suffix tables must be identical.
    from app.core.constants import _CURRENCY_BY_SUFFIX

    ts_table = frontend_suffix_table()
    py_table = dict(_CURRENCY_BY_SUFFIX)

    only_py = {k: v for k, v in py_table.items() if k not in ts_table}
    only_ts = {k: v for k, v in ts_table.items() if k not in py_table}
    differing = {
        k: (py_table[k], ts_table[k])
        for k in py_table
        if k in ts_table and py_table[k] != ts_table[k]
    }

    if only_py:
        failures.append(
            f"suffixes in the Python table but missing from the frontend: {only_py}"
        )
    if only_ts:
        failures.append(
            f"suffixes in the frontend table but missing from Python: {only_ts}"
        )
    if differing:
        failures.append(
            f"suffixes mapped to different currencies (python, frontend): {differing}"
        )

    # 2. Every symbol in the universe must resolve to a currency in both.
    #    The frontend's fallback for an unknown symbol is "USD", so a symbol
    #    that Python resolves as VND but the frontend as USD is a real bug:
    #    the page would show "72,300" for a VN stock with no dong sign.
    frontend_vn = set()
    vn_match = re.search(
        r"const VN_TICKERS = new Set\(\[(.*?)\]\)", FRONTEND_FORMAT.read_text(encoding="utf-8"), re.DOTALL
    )
    if vn_match:
        frontend_vn = set(re.findall(r'"([A-Z0-9\-]+)"', vn_match.group(1)))
    else:
        failures.append("could not find `VN_TICKERS` in the frontend format.ts")

    python_vn = set(VN_SYMBOLS)
    only_py_vn = python_vn - frontend_vn
    only_ts_vn = frontend_vn - python_vn
    if only_py_vn:
        failures.append(f"VN tickers known to Python but not the frontend: {sorted(only_py_vn)}")
    if only_ts_vn:
        failures.append(f"VN tickers known to the frontend but not Python: {sorted(only_ts_vn)}")

    # 3. Spot-check the resolution itself across every market in the universe.
    checked = 0
    for symbol in ALL_SYMBOLS:
        code = currency_for_symbol(symbol)
        if not re.fullmatch(r"[A-Z]{3}", code):
            failures.append(f"{symbol}: resolved to a non-ISO code {code!r}")
        checked += 1

    print(f"suffixes compared      : {len(py_table)}")
    print(f"VN tickers compared     : {len(python_vn)}")
    print(f"symbols resolved        : {checked}")
    print(f"crypto symbols          : {len(CRYPTO_SYMBOLS)}")

    if failures:
        print()
        for failure in failures:
            print(f"FAIL: {failure}")
        return 1

    print()
    print("PASS: backend and frontend resolve every symbol to the same currency.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
