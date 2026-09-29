@echo off
REM PySpark JupyterLab Launcher for Stock Lakehouse AI

cd /d "%~dp0..\stock-lakehouse-ai"

REM Set environment variables for PySpark with MinIO
set AWS_ACCESS_KEY_ID=minioadmin
set AWS_SECRET_ACCESS_KEY=minioadmin
set AWS_ENDPOINT=http://localhost:9000
set S3_ENDPOINT=http://localhost:9000
set PYSPARK_PYTHON=python
set PYSPARK_DRIVER_PYTHON=python
set JAVA_HOME=C:\Program Files\Java\jdk-17

REM Set PySpark memory
set PYSPARK_SUBMIT_ARGS=--driver-memory 2g --executor-memory 2g pyspark-shell

echo ============================================
echo   PySpark JupyterLab - Stock Lakehouse AI
echo ============================================
echo.
echo Storage: MinIO (localhost:9000)
echo Data: stock-silver bucket
echo.
echo Starting JupyterLab...
echo Open: http://localhost:8888
echo.

REM Start JupyterLab
jupyter lab --ip=0.0.0.0 --port=8888 --no-browser --NotebookApp.token=''
