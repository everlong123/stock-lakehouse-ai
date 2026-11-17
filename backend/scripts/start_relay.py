#!/usr/bin/env python3
"""Start the WSL2 port relay and publish the reachable endpoint for Windows.

WHY THIS EXISTS
---------------
The Windows-side backend (`uvicorn` on the host) must reach the Docker stack
inside WSL2. On this machine WSL's localhost forwarding is unreliable:
`127.0.0.1:<port>` from Windows is refused (WinError 10061) even while the
listener is alive inside the VM, but the very same port reached over the VM's
own IP address (`hostname -I`) works.

`relay_ports.py` binds `0.0.0.0:<port>` inside the VM, so the VM IP is a
working path. The only missing piece is knowing that IP — and it changes every
time WSL restarts.

This wrapper therefore:
  1. starts `relay_ports.py` for the requested forwards,
  2. discovers the VM IP,
  3. writes the resulting `host:port` pairs to an endpoint file so the
     Windows side can read them instead of hard-coding a stale IP.

Usage
-----
    python3 start_relay.py                       # defaults, write endpoint file
    python3 start_relay.py 13307:3307 19000:9000
    python3 start_relay.py --endpoint-file /tmp/relay_endpoints.txt
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RELAY = HERE / "relay_ports.py"

# host_port:guest_port — must match relay_ports.DEFAULT_FORWARDS.
DEFAULT_FORWARDS = (
    (13307, 3307),  # MySQL
    (19000, 9000),  # MinIO
)

DEFAULT_ENDPOINT_FILE = Path("/tmp/relay_endpoints.txt")


def vm_ip() -> str | None:
    """Return the VM's primary IPv4 address, or None if it cannot be found."""
    try:
        out = subprocess.run(
            ["hostname", "-I"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    for token in out.stdout.split():
        candidate = token.strip()
        if candidate and not candidate.startswith("127.") and ":" not in candidate:
            return candidate
    return None


def wait_for_port(port: int, timeout: float = 20.0) -> bool:
    """Wait until `port` accepts a TCP connection on the loopback interface."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2):
                return True
        except OSError:
            time.sleep(0.4)
    return False


def parse_forwards(args: list[str]) -> list[tuple[int, int]]:
    forwards: list[tuple[int, int]] = []
    for arg in args:
        host_port, _, guest_port = arg.partition(":")
        forwards.append((int(host_port), int(guest_port)))
    return forwards


def write_endpoint_file(path: Path, forwards: list[tuple[int, int]], ip: str | None) -> None:
    """Record the reachable endpoint for each forwarded port."""
    host = ip or "127.0.0.1"
    lines = []
    for host_port, guest_port in forwards:
        lines.append(f"{host_port}={host}:{host_port} -> 127.0.0.1:{guest_port}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[start-relay] endpoint file written: {path}", flush=True)
    for line in lines:
        print(f"[start-relay]   {line}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("forwards", nargs="*", help="host_port:guest_port pairs")
    parser.add_argument(
        "--endpoint-file",
        default=str(DEFAULT_ENDPOINT_FILE),
        help="where to write the reachable endpoints",
    )
    parser.add_argument(
        "--no-spawn",
        action="store_true",
        help="only refresh the endpoint file; assume the relay is already running",
    )
    args = parser.parse_args()

    forwards = parse_forwards(args.forwards) if args.forwards else list(DEFAULT_FORWARDS)

    if not args.no_spawn:
        cmd = [sys.executable, str(RELAY)] + [
            f"{host}:{guest}" for host, guest in forwards
        ]
        print(f"[start-relay] spawning: {' '.join(cmd)}", flush=True)
        proc = subprocess.Popen(cmd)
    else:
        proc = None

    for host_port, _guest in forwards:
        if wait_for_port(host_port):
            print(f"[start-relay] port {host_port} is up", flush=True)
        else:
            print(f"[start-relay] WARNING port {host_port} did not come up", flush=True)

    ip = vm_ip()
    print(f"[start-relay] VM IP: {ip or '<not found>'}", flush=True)
    write_endpoint_file(Path(args.endpoint_file), forwards, ip)

    if proc is None:
        return 0
    try:
        return proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
