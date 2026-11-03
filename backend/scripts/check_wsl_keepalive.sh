#!/bin/bash
# Verify the WSL2 distro stays up, and that Docker Engine + all containers
# survive with it.
#
# ── What actually goes wrong (measured 2026-10-26) ─────────────────────────
# The symptom is that every container restarts every ~30s and `docker ps`
# always shows "Up N seconds". The tempting diagnosis is "the WSL2 VM is
# rebooting", but /proc/uptime keeps climbing across those restarts — the
# kernel never reboots. What restarts is *userspace*: systemd was told to
# power off and the next WSL client re-initialised the distro.
#
# The WSL journal shows the real culprit, repeated hundreds of times:
#
#   WSL (2 - init-systemd(Ubuntu-24.04)) ERROR:
#     InitTerminateInstanceInternal:2901: systemctl poweroff did not
#     terminate the instance in 10000 ms, calling reboot(RB_POWER_OFF)
#
# WSL tears the instance down whenever the last wsl.exe client exits (this is
# by design, `vmIdleTimeout` does not cover it), and its own shutdown path then
# times out and hard-resets. systemd-logind logs "The system will power off
# now!" right before each teardown, and every `docker.service` stop is a
# *consequence* of that teardown, not the cause.
#
# `wsl-keepalive.service` (sleep infinity inside the distro) does NOT help:
# it is a guest-side unit, and WSL kills userspace from the outside. The fix
# has to hold an *attached session* from the Windows side:
#
#   Scheduled Task "WSL-Distro-Keepalive"
#     wscript.exe "D:\School\kltn\stock-lakehouse-ai\backend\scripts\wsl_keepalive.vbs"
#   which runs, hidden:
#     wsl.exe -d Ubuntu-24.04 -u root -- bash -c "while true; do sleep 3600; done"
#
# The task must launch wsl.exe through a VBS wrapper, not directly. Calling
# wsl.exe straight from Task Scheduler opens a visible console window every
# time it fires, and this task fires every minute, so the desktop flickers
# constantly. wscript.exe with a WScript.Shell.Run(..., 0, True) call runs it
# with no window at all.
#
# It repeats every minute with MultipleInstances=IgnoreNew so a new client
# re-attaches immediately after any teardown. Create it with:
#
#   $a = New-ScheduledTaskAction -Execute "C:\Windows\System32\wscript.exe" `
#          -Argument '"D:\School\kltn\stock-lakehouse-ai\backend\scripts\wsl_keepalive.vbs"'
#   $t = New-ScheduledTaskTrigger -Once -At (Get-Date) `
#          -RepetitionInterval (New-TimeSpan -Minutes 1) `
#          -RepetitionDuration (New-TimeSpan -Days 3650)
#   $s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) `
#          -MultipleInstances IgnoreNew -StartWhenAvailable -RestartCount 999 `
#          -RestartInterval (New-TimeSpan -Minutes 1) -Hidden
#   Register-ScheduledTask -TaskName "WSL-Distro-Keepalive" `
#          -Action $a -Trigger $t -Settings $s -Force
#
# For one-off commands, backend/scripts/wslc.cmd (on PATH as "wslc") does the
# same thing without a window:
#   wslc -d Ubuntu-24.04 -u root -- bash -lc "docker ps"
#
# Two host-side problems found on 2026-10-26/27 that kill the VM on their own:
#
# 1. The host had NO pagefile, so the commit limit equalled physical RAM
#    (31.8GB). Event ID 2004 in the Windows System log recorded `vmmemWSL` at
#    9.1GB triggering "low virtual memory condition".
#
# 2. WSL was capped at 10GB, and the Silver/Gold backfill pins it: each worker
#    reads a full symbol history into pandas. At the cap the VM pinned 9.9GB and
#    the WSL service stopped accepting new wsl.exe calls entirely — every
#    command timed out with WSAETIMEDOUT, even ones touching no files. The cap
#    is now 14GB with 4GB of swap, and the backfill runs with 2 workers.
set -u

echo "=== Windows-side session holder ==="
echo "  (0 attached clients means the next teardown will not be repaired)"

echo "=== distro identity + uptime ==="
printf '  boot_id=%s\n' "$(cut -c1-8 /proc/sys/kernel/random/boot_id)"
printf '  vm_uptime=%s\n' "$(cut -d' ' -f1 /proc/uptime)"

echo "=== docker engine ==="
printf '  docker_started=%s\n' "$(systemctl show docker -p ExecMainStartTimestamp --value)"

echo "=== teardown evidence ==="
echo "  Historical counts (whole boot — these include the pre-fix failures):"
printf '    InitTerminateInstanceInternal errors: %s\n' \
  "$(journalctl -b --no-pager 2>/dev/null | grep -c 'InitTerminateInstanceInternal')"
printf '    systemd "will power off now" events:  %s\n' \
  "$(journalctl -b --no-pager 2>/dev/null | grep -c 'will power off now')"
printf '    docker.service starts this boot:      %s\n' \
  "$(journalctl -u docker -b --no-pager 2>/dev/null | grep -c 'Started docker.service')"
echo "  Recent counts (last 10 minutes — this is what tells you if the fix holds):"
printf '    docker.service starts:  %s\n' \
  "$(journalctl -u docker -b --since '10 min ago' --no-pager 2>/dev/null | grep -c 'Started docker.service')"
printf '    poweroff requests:      %s\n' \
  "$(journalctl -b --since '10 min ago' --no-pager 2>/dev/null | grep -c 'will power off now')"

echo "=== docker uptime ==="
docker_since=$(date -d "$(systemctl show docker -p ExecMainStartTimestamp --value)" +%s 2>/dev/null || echo 0)
if [ "$docker_since" -gt 0 ]; then
  printf '  docker has been up for %s seconds\n' "$(( $(date +%s) - docker_since ))"
else
  echo "  could not read docker start time"
fi


echo "=== uptime samples every 15s (90s window) ==="
for i in 1 2 3 4 5 6 7; do
  printf '  sample %s: uptime=%s docker_started=%s\n' \
    "$i" \
    "$(cut -d' ' -f1 /proc/uptime)" \
    "$(systemctl show docker -p ExecMainStartTimestamp --value)"
  sleep 15
done

echo "=== containers ==="
timeout 25 docker ps --format '  {{.Names}} | {{.Status}}'

echo
echo "=== verdict ==="
recent_starts=$(journalctl -u docker -b --since '10 min ago' --no-pager 2>/dev/null | grep -c 'Started docker.service')
if [ "$recent_starts" -gt 1 ]; then
  echo "  DEGRADED: docker.service restarted $recent_starts times in the last 10 minutes."
  echo "  Check that the WSL-Distro-Keepalive scheduled task is running:"
  echo "    Get-ScheduledTask -TaskName 'WSL-Distro-Keepalive' | Select State"
  echo "    (Get-CimInstance Win32_Process -Filter \"Name='wsl.exe'\" | Measure).Count"
else
  echo "  OK: docker.service has been stable for the last 10 minutes."
fi
