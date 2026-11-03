# Enable a Windows pagefile on C:.
#
# WHY THIS IS NEEDED
# ------------------
# This machine had NO pagefile (AutomaticManagedPagefile=False), so the
# commit limit equalled physical RAM (31.8 GB). When the commit charge got
# close to that limit, Windows raised "low virtual memory condition"
# (Event 2004) and, if a process allocated past it, the allocation FAILED
# outright - there was no swap file to fall back to, so the process was
# simply killed.
#
# That is what happened on 2026-11-03 between 02:28 and 03:07:
#
#   Event 2004 x7 - "low virtual memory condition"
#     vmmemWSL   consumed 12.9 GB
#     python.exe consumed  1.67 GB
#   Event 1000  - wslservice.exe faulted
#   Event 1000  - wslrelay.exe faulted
#
# and the CPU-bound job workers were killed mid-rebuild, which broke the
# ProcessPoolExecutor ("the process pool is not usable anymore").
#
# A pagefile gives the kernel somewhere to put memory that does not fit, so
# an over-committed system degrades (slow) instead of crashing.
#
# 8GB initial / 16GB max on C:, which has ~29GB free. The pagefile takes
# effect after a REBOOT - Windows allocates it at boot.
#
# MUST BE RUN AS ADMINISTRATOR. The script re-launches itself elevated.

$ErrorActionPreference = "Stop"

$reportPath = Join-Path $env:TEMP "enable_pagefile_report.txt"
$report = New-Object System.Collections.Generic.List[string]
function Say($msg) {
    Write-Host $msg
    $report.Add([string]$msg)
}

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    return (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator
    )
}

if (-not (Test-Admin)) {
    Say "[pagefile] Not admin - relaunching elevated..."
    $scriptPath = $MyInvocation.MyCommand.Path
    Start-Process -FilePath "powershell.exe" `
        -Verb RunAs `
        -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$scriptPath`"" `
        -Wait
    if (Test-Path $reportPath) {
        Say "[pagefile] Elevated run reported:"
        Get-Content -LiteralPath $reportPath | ForEach-Object { Say "  $_" }
    } else {
        Say "[pagefile] Elevated run produced no report - it may have been cancelled."
    }
    $report | Set-Content -LiteralPath $reportPath -Encoding UTF8
    return
}

Say "[pagefile] Configuring pagefile on C: ..."

# 1. Let Windows manage the pagefile size system-wide.
try {
    $cs = Get-CimInstance Win32_ComputerSystem
    if (-not $cs.AutomaticManagedPagefile) {
        Set-CimInstance -InputObject $cs -Property @{ AutomaticManagedPagefile = $true } | Out-Null
        Say "[pagefile] AutomaticManagedPagefile -> True"
    } else {
        Say "[pagefile] AutomaticManagedPagefile already True"
    }
} catch {
    Say "[pagefile] WARN could not set AutomaticManagedPagefile: $($_.Exception.Message)"
}

# 2. Write the paging file list into the registry.
#
# The registry is the authoritative store, and writing it directly works even
# when the WMI class refuses to create the instance (which is what happened
# the first time this was run - New-CimInstance on Win32_PageFileSetting
# silently did nothing).
#
# "C:\pagefile.sys 0 0" = system-managed on C: (Windows picks the size).
try {
    $mm = "HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management"
    Set-ItemProperty -Path $mm -Name "PagingFiles" -Value @("C:\pagefile.sys 0 0") -Type MultiString
    Say "[pagefile] PagingFiles -> C:\pagefile.sys 0 0 (system-managed)"

    $existing = (Get-ItemProperty -Path $mm -Name "ExistingPageFiles" -EA SilentlyContinue).ExistingPageFiles
    Say "[pagefile] ExistingPageFiles (allocated at last boot): '$existing'"
} catch {
    Say "[pagefile] ERROR writing registry: $($_.Exception.Message)"
}

# 3. Report the resulting state.
$os = Get-CimInstance Win32_OperatingSystem
Say "[pagefile] Commit limit now: {0:N1} GB" -f ($os.TotalVirtualMemorySize / 1MB)
Say "[pagefile] Commit used  now: {0:N1} GB" -f (($os.TotalVirtualMemorySize - $os.FreeVirtualMemory) / 1MB)
Say ""
Say "[pagefile] A REBOOT is required for Windows to allocate the pagefile."
Say "[pagefile] After rebooting, 'ExistingPageFiles' should show C:\pagefile.sys"
Say "[pagefile] and the commit limit should be ~40 GB instead of 31.8 GB."

$report | Set-Content -LiteralPath $reportPath -Encoding UTF8
