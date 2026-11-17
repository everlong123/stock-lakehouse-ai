"""Comprehensive API smoke test - every REST route on the running backend.

Paths from openapi.json already include the /api/v1 prefix.
Body payloads follow the real Pydantic schemas (see openapi components).
Usage: python scripts/smoke_all_routes.py [base_url]

WHY IT IS NAMED THIS AND NOT `_apitest.py`
-------------------------------------------
A leading underscore marks a throwaway probe. This one is not: it is the
smoke test that proves every REST route answers, and the QA report cites
it by path. The name says what it does.
"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

# Endpoints that take minutes and monopolise the server (tested separately).
HEAVY = {
    "/api/v1/data/ingest/all",
    "/api/v1/data/stocks/ingest",
    "/api/v1/forecast/train",
    "/api/v1/pipeline/run",
}

BODIES = {
    "/api/v1/agent/chat": {"session_id": "test-session-0001", "message": "RSI cua VCB la bao nhieu?", "symbol": "VCB"},
    "/api/v1/forecast/train": {"symbol": "AAPL", "model_name": "linear_regression", "horizon": 1},
    "/api/v1/forecast/predict": {"symbol": "AAPL", "model_name": "linear_regression", "horizon": 5},
    "/api/v1/backtests/run": {"symbol": "AAPL", "strategy": "ma_crossover"},
    "/api/v1/pipeline/run": {"symbols": ["AAPL"], "use_minio": True, "interval": "1d", "lookback_days": 30},
    "/api/v1/data/stocks/ingest": ["AAPL"],
    "/api/v1/data/fundamental/ingest": ["AAPL"],
}


def call(url, method="GET", body=None, timeout=120):
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, method=method, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return -1, str(e).encode()


def describe(raw):
    try:
        j = json.loads(raw)
    except Exception:
        return None, raw[:70].decode("utf-8", "replace"), "NON-JSON"
    if isinstance(j, dict):
        okv = j.get("success")
        msg = str(j.get("message"))[:70]
        d = j.get("data")
        if isinstance(d, dict):
            dk = "{" + ",".join(list(d.keys())[:7]) + "}"
        elif isinstance(d, list):
            dk = f"list[{len(d)}]"
        else:
            dk = type(d).__name__
        return okv, msg, dk
    return None, "", type(j).__name__


def main():
    st, body = call(BASE + "/openapi.json")
    spec = json.loads(body)
    paths = spec["paths"]
    print(f"openapi: {st}, {len(paths)} paths\n")

    sym = "AAPL"
    replacements = {
        "{symbol}": sym, "{s_symbol}": sym,
        "{model_name}": "linear_regression",
        "{strategy}": "ma_crossover",
        "{task_id}": "nonexistent-task-id",
        "{session_id}": "nonexistent-session",
        "{message_id}": "nonexistent-message",
        "{layer}": "gold",
        "{job_id}": "nonexistent-job",
        "{run_id}": "nonexistent-run",
        "{bucket}": "stock-gold",
    }

    rows = []
    for path, methods in sorted(paths.items()):
        if path in HEAVY:
            rows.append(("SKIP", "", "", path, None, 0, "", ""))
            continue
        url_path = path
        for k, v in replacements.items():
            url_path = url_path.replace(k, v)
        for method in methods:
            if method not in ("get", "post", "delete", "put"):
                continue
            url = BASE + url_path
            body_in = BODIES.get(path) if method == "post" else None
            t0 = time.time()
            code, raw = call(url, method.upper(), body_in)
            dt = (time.time() - t0) * 1000
            okv, msg, dk = describe(raw)
            rows.append((code, method.upper(), str(okv), path, okv, dt, msg, dk))

    print(f"{'CODE':<7}{'MS':>8}  {'M':<7}{'OK':<7} PATH")
    print("-" * 122)
    n_ok = n_exp = n_rev = n_err = n_skip = 0
    for code, method, okv, path, real_ok, dt, msg, dk in rows:
        if code == "SKIP":
            n_skip += 1
            print(f"{'SKIP':<7}{'':>8}  {'':<7}{'':<7} {path}")
            continue
        if code == 200 and real_ok is not False:
            n_ok += 1
            flag = "PASS"
        elif code in (400, 404, 422) and real_ok is False:
            n_exp += 1
            flag = "PASS(err)"
        elif code == -1:
            n_err += 1
            flag = "FAIL(conn)"
        else:
            n_rev += 1
            flag = "REVIEW"
        print(f"{code:<7}{dt:>8.0f}  {method:<7}{okv:<7} {path}\n{'':>25}-> {dk[:90]} | {msg[:60]} [{flag}]")
    print("-" * 122)
    print(f"total={len(rows)}  200-ok={n_ok}  expected-4xx={n_exp}  review={n_rev}  conn-error={n_err}  skipped={n_skip}")


if __name__ == "__main__":
    main()
