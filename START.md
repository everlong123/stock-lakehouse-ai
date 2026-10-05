# Quick Start (one-liner)

The repo now ships with `start-all.{ps1,bat}` and `stop-all.{ps1,bat}` at the project root.

## Recommended: double-click

Just double-click **`start-all.bat`**. Two cmd windows will pop up:
- `Stock-LH-Backend` — FastAPI on :8000
- `Stock-LH-Frontend` — Vite on :5173

Then open <http://127.0.0.1:5173> in your browser.

To stop: double-click `stop-all.bat`.

## From PowerShell

```powershell
cd D:\School\kltn\stock-lakehouse-ai
powershell -ExecutionPolicy Bypass -File .\start-all.ps1
# ...
powershell -ExecutionPolicy Bypass -File .\stop-all.ps1
```

## Manual (no scripts)

Open **two** separate PowerShell windows:

```powershell
# Window 1 - backend
cd D:\School\kltn\stock-lakehouse-ai\backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

```powershell
# Window 2 - frontend
cd D:\School\kltn\stock-lakehouse-ai\frontend
npm run dev
```

## URL map

| Service  | URL                          |
|----------|------------------------------|
| Frontend | http://127.0.0.1:5173        |
| Agent UI | http://127.0.0.1:5173/agent  |
| Backend  | http://127.0.0.1:8000        |
| API docs | http://127.0.0.1:8000/docs   |
