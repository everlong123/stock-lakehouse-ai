"""Kill a pool worker mid-job and verify the pool recovers.

This reproduces the failure from 2026-11-03: the OS killed the workers under
memory pressure, the ProcessPoolExecutor became permanently broken, and
every later rebuild failed with "the process pool is not usable anymore".
"""
import os
import signal
import sys
import time
sys.path.insert(0, ".")


def slow_job(delay: float = 30.0) -> dict:
    import time
    time.sleep(delay)
    return {"ok": True, "pid": os.getpid()}


def main():
    from app.core.heavy_worker import get_pool, run_in_process, shutdown_pool

    pool = get_pool("interactive")
    print("pool started with", pool._max_workers, "workers")

    # Submit a long job, then kill its worker process.
    future = pool.submit(slow_job, 30.0)
    time.sleep(2)
    # Find the worker process and kill it the way the OOM killer would.
    import subprocess
    out = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | "
         "Where-Object { $_.CommandLine -like '*multiprocessing.spawn*' } | "
         "ForEach-Object { $_.ProcessId }"],
        capture_output=True, text=True,
    ).stdout
    pids = [int(tok) for tok in out.split() if tok.isdigit()]
    print("worker pids:", pids)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
            print("killed", pid)
        except Exception as exc:
            print("could not kill", pid, exc)

    time.sleep(1)
    try:
        future.result(timeout=10)
        print("UNEXPECTED: the job survived")
    except Exception as exc:
        print("job died as expected:", type(exc).__name__, exc)

    # The important part: the NEXT job must succeed on a fresh pool.
    print("submitting a new job after the break...")
    result = run_in_process(slow_job, 1.0)
    print("RECOVERED:", result)
    shutdown_pool()


if __name__ == "__main__":
    main()
