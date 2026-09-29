#!/usr/bin/env python3
"""
PySpark Jupyter Launcher for Stock Lakehouse AI

Run this script to start JupyterLab with PySpark and MinIO configuration.
"""

import subprocess
import os
import sys

# Configure environment
env = os.environ.copy()
env.update({
    'AWS_ACCESS_KEY_ID': 'minioadmin',
    'AWS_SECRET_ACCESS_KEY': 'minioadmin',
    'AWS_ENDPOINT': 'http://localhost:9000',
    'S3_ENDPOINT': 'http://localhost:9000',
    'PYSPARK_PYTHON': sys.executable,
    'PYSPARK_DRIVER_PYTHON': sys.executable,
    'PYSPARK_SUBMIT_ARGS': '--driver-memory 2g --executor-memory 2g pyspark-shell',
})

# JupyterLab arguments
jupyter_args = [
    'jupyter', 'lab',
    '--ip=0.0.0.0',
    '--port=8888',
    '--no-browser',
    '--NotebookApp.token=""',
    '--NotebookApp.allow_origin="*"',
]

print("=" * 50)
print("  PySpark JupyterLab - Stock Lakehouse AI")
print("=" * 50)
print()
print("Storage: MinIO (localhost:9000)")
print("Data: stock-silver bucket")
print()
print("Open: http://localhost:8888")
print()

# Change to notebooks directory
notebooks_dir = os.path.dirname(os.path.abspath(__file__))
os.chdir(notebooks_dir)

# Start JupyterLab
subprocess.run(jupyter_args, env=env)
