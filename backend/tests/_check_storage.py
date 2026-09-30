"""Check what storage backend the system is using."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.lakehouse.storage_factory import get_storage_backend

storage = get_storage_backend()
print(f"Storage backend: {storage.backend_name}")
print(f"Storage class: {type(storage).__name__}")

# Read one row to verify
from app.lakehouse import BronzeLayer
bronze = BronzeLayer()
record = bronze.record_count("VCB")
print(f"VCB bronze records: {record}")