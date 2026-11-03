#!/usr/bin/env python3
"""Expose a TCP port from inside the WSL2 VM to the Windows host.

WHY THIS EXISTS
---------------
A local dev backend (`uvicorn` on Windows) needs to reach the Docker stack at
127.0.0.1:3307 (MySQL) and 127.0.0.1:9000 (MinIO). On this machine the WSL2
localhost-forwarding path is unreliable:

  * The guest can reach its own ports fine (verified in-VM with /dev/tcp).
  * Windows gets WinError 10061 (connection refused) on both 127.0.0.1 and the
    WSL IP, even though `ss -tln` inside the VM shows the listeners.
  * ICMP to the WSL IP succeeds, so the route exists and only TCP is dropped.
  * The WSL VM firewall reports DefaultInboundAction=Block, and adding an
    allow rule requires Administrator, which is not available here.

`networkingMode=mirrored` was tried and made it worse: the VM moved onto the
Windows LAN stack, where the *host* firewall's inbound rules then refuse
traffic originating from the host itself.

This relay sidesteps the problem. It binds `0.0.0.0:<listen_port>` inside the
VM, which is exactly the traffic path that has been observed to work (the
published MySQL port is reachable over the VM's own interface), and it keeps
one socket per connection so nothing depends on WSL's forwarding daemon.

Usage
-----
    python3 relay_ports.py                     # forward the defaults
    python3 relay_ports.py 13307:3307 19000:9000

Run it inside WSL, then point the Windows-side backend at 127.0.0.1:<listen_port>.
"""

from __future__ import annotations

import socket
import sys
import threading

# host_port:guest_port
DEFAULT_FORWARDS = (
    (13307, 3307),  # MySQL
    (19000, 9000),  # MinIO
)

_BACKLOG = 64
_CHUNK = 65536


def _pump(src: socket.socket, dst: socket.socket) -> None:
    """Copy bytes in one direction until either side closes."""
    try:
        while True:
            data = src.recv(_CHUNK)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for sock in (src, dst):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def _handle(host_port: int, guest_port: int) -> None:
    """Accept connections forever and relay each one to the guest port."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("0.0.0.0", host_port))
    listener.listen(_BACKLOG)
    print(f"[relay] listening 0.0.0.0:{host_port} -> 127.0.0.1:{guest_port}", flush=True)

    while True:
        try:
            client, addr = listener.accept()
        except OSError:
            continue
        threading.Thread(target=_session, args=(client, guest_port, addr), daemon=True).start()


def _session(client: socket.socket, guest_port: int, addr: tuple) -> None:
    try:
        upstream = socket.create_connection(("127.0.0.1", guest_port), timeout=10)
    except OSError as exc:
        print(f"[relay] {addr} -> :{guest_port} failed: {exc}", flush=True)
        client.close()
        return

    client.settimeout(None)
    upstream.settimeout(None)
    print(f"[relay] {addr} -> :{guest_port}", flush=True)
    for a, b in ((client, upstream), (upstream, client)):
        threading.Thread(target=_pump, args=(a, b), daemon=True).start()


def main() -> int:
    forwards = DEFAULT_FORWARDS
    if len(sys.argv) > 1:
        forwards = []
        for arg in sys.argv[1:]:
            host_port, _, guest_port = arg.partition(":")
            forwards.append((int(host_port), int(guest_port)))

    print(f"[relay] forwarding {len(forwards)} port(s)", flush=True)
    for host_port, guest_port in forwards:
        threading.Thread(
            target=_handle, args=(host_port, guest_port), daemon=True
        ).start()

    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("[relay] stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())