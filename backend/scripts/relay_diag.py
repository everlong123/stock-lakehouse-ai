#!/usr/bin/env python3
"""Diagnose the relay: can it reach MySQL, and does it forward correctly?"""
import socket
import sys

for port, label in ((3307, "mysql-direct"), (13307, "relay-13307"), (9000, "minio-direct")):
    try:
        s = socket.create_connection(("127.0.0.1", port), timeout=5)
        # MySQL sends a handshake banner immediately; MinIO does not.
        s.settimeout(2)
        try:
            data = s.recv(64)
        except socket.timeout:
            data = b"<no banner>"
        print(f"{label:16} port {port:5}  CONNECTED  recv={data[:40]!r}")
        s.close()
    except Exception as exc:
        print(f"{label:16} port {port:5}  FAILED: {exc}")
