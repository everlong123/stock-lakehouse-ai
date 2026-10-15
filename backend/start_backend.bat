@echo off
cd /d D:\School\kltn\stock-lakehouse-ai\backend
set PYTHONPATH=D:\School\kltn\stock-lakehouse-ai\backend
D:\School\kltn\stock-lakehouse-ai\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload > D:\School\kltn\stock-lakehouse-ai\backend\logs\uvicorn.log 2>&1
