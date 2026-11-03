import time, json, urllib.request, urllib.error, os, sys
sys.path.insert(0, r"d:\School\kltn\stock-lakehouse-ai\backend")
os.chdir(r"d:\School\kltn\stock-lakehouse-ai\backend")
from app.core.config import settings

url = f"{settings.gemini_base_url.rstrip('/')}/models/{settings.gemini_model}:generateContent?key={settings.gemini_api_key}"
payload = {"contents": [{"role": "user", "parts": [{"text": "Say hi in 3 words"}]}]}
req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=settings.gemini_timeout_seconds) as r:
        body = r.read().decode()
    print("OK %.1fs" % (time.time()-t0), body[:300])
except Exception as e:
    print("FAIL %.1fs: %r" % (time.time()-t0, e))
