"""Determine the correct SSI field offsets empirically.

Hypothesis: `parse_quote` reads the wrong field index, so `vn_ws` rows carry
another symbol's matched price and a meaningless timestamp.

Evidence: VCB vn_ws close=56.9 while the true VCB price is 56600 (SSI reports
in thousand VND, so 56600/1000 = 56.6 - the magnitude matches, so the value IS
a VND price, just for a different instrument or a different field).

The file's own docstring admits the offsets were taken from decompiled
vnstock-js output and may be wrong. This captures a live tick if the socket is
up and prints every field with its index, so the right offsets can be read off
directly instead of guessed. If trading is closed the socket yields nothing and
this reports that instead of inventing numbers.
"""

import sys

sys.path.insert(0, "/app")

import json
import time

from app.streaming.vn_websocket import (
    IDX_EXCHANGE,
    IDX_ID,
    IDX_LAST_UPDATED,
    IDX_MATCHED_P,
    IDX_SIDE,
    VNWebSocketClient,
    _build_subscribe_message,
)

captured = []


def on_raw(raw: str) -> None:
    if raw and "|" in raw and not raw.startswith("{"):
        captured.append(raw)


print("attempting live capture from SSI iBoard (20s)...")
try:
    import websocket

    ws = websocket.create_connection("wss://iboard-pushstream.ssi.com.vn/realtime", timeout=15)
    ws.send(_build_subscribe_message(["VCB", "FPT"], ["MAIN", "HNX", "UPCOM"]))
    ws.settimeout(5)
    deadline = time.time() + 20
    while time.time() < deadline and not captured:
        try:
            raw = ws.recv()
        except Exception:
            continue
        if raw and "|" in raw and not raw.startswith("{"):
            captured.append(raw)
    ws.close()
except Exception as exc:
    print(f"socket unavailable: {type(exc).__name__}: {exc}")

if not captured:
    print("NO LIVE TICK CAPTURED - market closed or socket refused.")
    print("Falling back to offsets declared in vn_websocket.py:")
    print(f"  IDX_MATCHED_P   = {IDX_MATCHED_P}")
    print(f"  IDX_LAST_UPDATED= {IDX_LAST_UPDATED}")
    print(f"  IDX_SIDE        = {IDX_SIDE}")
    sys.exit(0)

raw = captured[0]
parts = raw.split("|")
print(f"\ncaptured tick with {len(parts)} fields\n")
print(f"{'idx':>4s}  {'value':>28s}   note")
for i, v in enumerate(parts):
    note = ""
    if i == IDX_EXCHANGE:
        note = "<- IDX_EXCHANGE"
    elif i == IDX_ID:
        note = "<- IDX_ID"
    elif i == IDX_MATCHED_P:
        note = f"<- IDX_MATCHED_P  => parsed price {v}/1000 = {int(v)/1000 if v.strip().lstrip('-').isdigit() else '?'}"
    elif i == IDX_LAST_UPDATED:
        note = f"<- IDX_LAST_UPDATED  => /1000 = {(int(v)/1000 if v.strip().lstrip('-').isdigit() else '?')}"
    elif i == IDX_SIDE:
        note = "<- IDX_SIDE"
    print(f"{i:4d}  {v[:28]:>28s}   {note}")

print("\ninterpretation hints:")
print("  VCB last price ~ 56000-58000 (thousand VND) => field should hold ~56600")
print("  a field holding a 1970-era epoch => small integer like 1-60")