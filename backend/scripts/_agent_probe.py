import json, sys, time, urllib.request

url = "http://127.0.0.1:8000/api/v1/agent/chat"
payload = json.dumps({
    "session_id": sys.argv[1],
    "message": sys.argv[2],
    "symbol": sys.argv[3] if len(sys.argv) > 3 else None,
}).encode("utf-8")

req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=180) as resp:
        body = resp.read().decode("utf-8", "replace")
        print("HTTP", resp.status, "elapsed %.1fs" % (time.time() - t0))
        print(body[:1200])
except Exception as exc:
    print("FAIL %.1fs" % (time.time() - t0), exc)
    if hasattr(exc, "read"):
        print(exc.read().decode("utf-8", "replace")[:1200])
