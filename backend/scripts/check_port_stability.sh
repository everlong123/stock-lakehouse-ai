#!/bin/bash
# Sample Windows-side reachability of the two ports a local uvicorn backend
# needs, repeated a few times so a flapping forward shows up as flapping.
#
# Why this exists: on 2026-10-22 a raw TCP connect from Windows to
# 127.0.0.1:3307 succeeded, then pymysql got ECONNREFUSED seconds later from
# the very same host. The WSL2 localhost-forwarding path for *published*
# container ports (docker-proxy) was the unstable layer: MinIO, bound via
# network_mode: host, was rock solid the whole time.
#
# Usage:  bash check_port_stability.sh [samples] [interval_seconds]
SAMPLES="${1:-10}"
INTERVAL="${2:-3}"

echo "=== $SAMPLES samples, ${INTERVAL}s apart ==="
mysql_ok=0
minio_ok=0
for i in $(seq 1 "$SAMPLES"); do
  mysql="DOWN"
  minio="DOWN"
  if timeout 3 bash -c 'exec 3<>/dev/tcp/127.0.0.1/3307' 2>/dev/null; then mysql="UP"; fi
  if timeout 3 bash -c 'exec 3<>/dev/tcp/127.0.0.1/9000' 2>/dev/null; then minio="UP"; fi
  [ "$mysql" = "UP" ] && mysql_ok=$((mysql_ok + 1))
  [ "$minio" = "UP" ] && minio_ok=$((minio_ok + 1))
  printf '  sample %2s: mysql:3307=%-4s  minio:9000=%-4s\n' "$i" "$mysql" "$minio"
  sleep "$INTERVAL"
done

echo
echo "=== summary ==="
echo "  mysql:3307  $mysql_ok/$SAMPLES up"
echo "  minio:9000  $minio_ok/$SAMPLES up"

echo
echo "=== containers ==="
docker ps --format '  {{.Names}} | {{.Status}} | {{.Ports}}'