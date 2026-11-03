"""Print row counts for every MySQL table (used to check app-side data)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymysql

from app.core.config import settings

url = settings.database_url
# mysql+pymysql://user:pass@host:port/db -> pymysql.connect kwargs
_, _, rest = url.partition("://")
creds, _, location = rest.rpartition("@")
user, _, password = creds.partition(":")
host, _, tail = location.partition(":")
port, _, database = tail.partition("/")

conn = pymysql.connect(
    host=host,
    port=int(port),
    user=user,
    password=password,
    database=database,
    connect_timeout=10,
)
try:
    with conn.cursor() as cur:
        cur.execute("SHOW TABLES")
        tables = [row[0] for row in cur.fetchall()]
        print(f"{'table':32s} rows")
        print("-" * 44)
        for table in tables:
            cur.execute(f"SELECT COUNT(*) FROM `{table}`")
            print(f"{table:32s} {cur.fetchone()[0]}")
finally:
    conn.close()