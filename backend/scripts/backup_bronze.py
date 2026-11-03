"""Back up the Bronze bucket before any destructive cleanup.

Copies every object from stock-bronze into stock-bronze-backup-<UTC stamp>
using MinIO server-side copy, which is a metadata operation on the server and
does not stream bytes through this process.

Run order: backup first, migration second. If the migration turns out to have
deleted something it should not have, the backup bucket is the only way back.
"""

import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from minio import Minio
from minio.commonconfig import CopySource

from app.core.config import settings

STAMP = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
SOURCE = "stock-bronze"
BACKUP = f"stock-bronze-backup-{STAMP}"


def main() -> int:
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )

    if not client.bucket_exists(SOURCE):
        print(f"source bucket {SOURCE} does not exist - nothing to back up")
        return 1

    if client.bucket_exists(BACKUP):
        client.remove_objects(
            BACKUP,
            [o.object_name for o in client.list_objects(BACKUP, recursive=True)],
        )
        client.remove_bucket(BACKUP)
        print(f"removed stale partial backup bucket: {BACKUP}")

    client.make_bucket(BACKUP)
    print(f"created backup bucket: {BACKUP}")

    copied = 0
    failed = 0
    for obj in client.list_objects(SOURCE, recursive=True):
        target = f"{BACKUP}/{obj.object_name}"
        try:
            client.copy_object(BACKUP, target, CopySource(SOURCE, obj.object_name))
            copied += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAILED {obj.object_name}: {exc}")
        if copied % 500 == 0:
            print(f"  ... {copied} objects copied")

    print(f"\ncopied={copied} failed={failed}")
    if failed:
        print("BACKUP INCOMPLETE - do not run the migration")
        return 1
    print(f"backup verified: {BACKUP}")
    print("source objects:   " + SOURCE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())