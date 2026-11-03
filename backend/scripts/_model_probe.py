import json, sys, time, urllib.request, urllib.error
sys.path.insert(0, ".")
from app.core.config import settings

for model in ["gemini-3.5-flash-lite", "gemini-3-flash-preview"]:
    url = f"{settings.gemini_base_url.rstrip('/')}/models/{model}:generateContent?key={settings.gemini_api_key}"
    payload = json.dumps({"contents": [{"role": "user", "parts": [{"text": "say ok"}]}]}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            resp.read()
        print("%-26s OK %.1fs" % (model, time.time() - t0))
    except urllib.error.HTTPError as exc:
        print("%-26s HTTP %s %.1fs :: %s" % (model, exc.code, time.time() - t0, exc.read()[:120]))
    except Exception as exc:
        print("%-26s FAIL %.1fs %s" % (model, time.time() - t0, exc))
