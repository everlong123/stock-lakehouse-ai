#!/bin/bash
# Diagnose why a published container port is unreachable from Windows.
#
# Background: MinIO (network_mode: host) was reachable from Windows, but
# MySQL — published through docker-proxy as "3307:3306" — was not. A raw TCP
# connect from Windows to 127.0.0.1:3307 succeeded while pymysql got
# ECONNREFUSED, which pointed at the WSL2 localhost-forwarding proxy rather
# than at MySQL itself.
#
# This script compares the three layers:
#   1. inside the container
#   2. from inside the WSL2 VM (via the published port)
#   3. from inside the WSL2 VM (via the container's bridge IP)
echo "=== 1. inside container ==="
timeout 20 docker exec stock-lakehouse-mysql \
  mysqladmin ping -h 127.0.0.1 -uroot -p123456 2>&1 | tail -1

echo "=== 2. WSL VM -> published port 3307 ==="
timeout 8 bash -c 'exec 3<>/dev/tcp/127.0.0.1/3307 && echo "WSL -> 127.0.0.1:3307 OK"' 2>&1 \
  || echo "WSL -> 127.0.0.1:3307 FAIL"

echo "=== 3. WSL VM -> MySQL port 3306 ==="
timeout 8 bash -c 'exec 3<>/dev/tcp/127.0.0.1/3306 && echo "WSL -> 127.0.0.1:3306 OK"' 2>&1 \
  || echo "WSL -> 127.0.0.1:3306 FAIL (3306 is container-only, expected)"

echo "=== 4. listening sockets in WSL ==="
ss -tln 2>/dev/null | grep -E ':(3307|9000|3306)\b' || echo "none"

echo "=== 5. published ports ==="
docker ps --format '{{.Names}} -> {{.Ports}}'