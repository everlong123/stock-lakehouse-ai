import sys, time
sys.path.insert(0, ".")

from app.api.v1.endpoints import health

t = time.time()
storage = health.get_storage_backend()
print("STEP storage", round(time.time() - t, 2), flush=True)

t = time.time()
from app.database.session import check_database_connection  # noqa: E402
print("STEP db_conn", round(time.time() - t, 2), check_database_connection(), flush=True)

t = time.time()
from app.core.config import settings  # noqa: E402
ok = health._probe_http(f"{settings.iceberg_catalog_uri}/v1/config", expect_status=[200, 400, 404, 405])
print("STEP probe_http", round(time.time() - t, 2), ok, flush=True)

t = time.time()
ok = health._probe_tcp(settings.kafka_bootstrap_servers.split(",")[0].strip())
print("STEP probe_tcp", round(time.time() - t, 2), ok, flush=True)

t = time.time()
counts = health._layer_counts()
print("STEP layer_counts", round(time.time() - t, 2), counts, flush=True)

t = time.time()
r = health._last_pipeline_run()
print("STEP last_pipeline_run", round(time.time() - t, 2), flush=True)

t = time.time()
counts = health._layer_counts()
print("STEP layer_counts_again", round(time.time() - t, 2), counts, flush=True)
