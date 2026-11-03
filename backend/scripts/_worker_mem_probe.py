"""Measure the memory footprint of one CPU-bound pool worker."""
import ctypes
import subprocess
import sys
from ctypes import wintypes


class PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def rss_mb() -> int:
    c = PMC()
    c.cb = ctypes.sizeof(PMC)
    ctypes.windll.psapi.GetProcessMemoryInfo(
        ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb
    )
    return c.WorkingSetSize // 1024 // 1024


CHILD = r'''
import ctypes, sys
from ctypes import wintypes
sys.path.insert(0, ".")

class PMC(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]

def rss():
    c = PMC(); c.cb = ctypes.sizeof(PMC)
    ctypes.windll.psapi.GetProcessMemoryInfo(
        ctypes.windll.kernel32.GetCurrentProcess(), ctypes.byref(c), c.cb)
    return c.WorkingSetSize // 1024 // 1024

print("spawned, before imports:", rss(), "MB")
import pandas, numpy, pyarrow
print("after pandas/pyarrow   :", rss(), "MB")
from app.pipelines.worker import rebuild_silver_job
r = rebuild_silver_job("AAPL", "1d")
print("after Silver rebuild   :", rss(), "MB")
from app.backtesting.worker import run_walk_forward_job
w = run_walk_forward_job(symbol="AAPL", strategy_name="rsi_strategy")
print("after walk-forward     :", rss(), "MB")
'''


def main():
    print("parent RSS:", rss_mb(), "MB")
    subprocess.run([sys.executable, "-c", CHILD])


if __name__ == "__main__":
    main()
