#!/usr/bin/env python3
"""Copy the trained models from this machine to a VPS over SSH.

WHY THIS SCRIPT EXISTS
----------------------
The models are trained locally, on the machine that holds the full history
in ``backend/data/models/<SYMBOL>/<MODEL>/``. The VPS is where the system
runs 24/7: the ``scheduler`` container fires the EOD batch every evening,
and that batch loads a trained model to produce the next-session forecast.

A trained model is a directory of files:

    backend/data/models/AAPL/arima/
        arima_result.pkl     fitted ARIMA state
        history.npy          the training series, used for the next step
        metadata.json        symbol, model name, training date, metrics
        predictions.parquet  the in-sample predictions (audit trail)
        registry.json        which artefacts belong to which run

Two things make syncing non-trivial:

1. **The file set is small but not trivial.** A plain ``scp -r`` of the
   whole tree also copies the ``predictions.parquet`` audit files and the
   ``history.npy`` arrays, which for a long history are the bulk of the
   bytes. The VPS only needs the artefacts that ``load_model`` actually
   reads, so this script can restrict the copy with ``--include-predictions``.

2. **A partial copy is worse than no copy.** If the transfer dies halfway,
   the VPS is left with a half-written ``arima_result.pkl`` that loads
   without error and then produces nonsense. So the copy goes to a
   temporary directory on the VPS first, and only a complete, verified
   staging directory is swapped into place with a single ``mv``.

WHAT IT DOES
------------
1. Lists the local models, grouped by symbol and model name.
2. For each selected model, packs it into a ``tar.gz`` archive.
3. Uploads the archive to the VPS over ``scp``.
4. On the VPS, extracts it into a staging directory and verifies that the
   expected artefacts are present and non-empty.
5. Swaps the staging directory into the live model directory.
6. Writes a manifest (``sync_manifest.json``) so a later run can tell
   what was deployed and when.

USAGE
-----
    python scripts/sync_models_to_vps.py --list
    python scripts/sync_models_to_vps.py --host user@vps --symbol AAPL
    python scripts/sync_models_to_vps.py --host user@vps --all
    python scripts/sync_models_to_vps.py --host user@vps --dry-run

The remote destination defaults to ``/opt/stock-lakehouse/backend/data/models``
and the remote project root to ``/opt/stock-lakehouse``.

NO FAKE DATA
------------
This script only moves files that already exist on disk. It never creates a
placeholder model, and it refuses to publish a model whose artefacts are
missing or empty.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / "data" / "models"

# The artefacts that `app.forecasting.predictor.load_model` actually reads.
# A model directory missing any of these is not deployable.
REQUIRED_ARTEFACTS = {
    "arima": ("arima_result.pkl", "metadata.json"),
    "lstm": ("lstm.pt", "metadata.json", "scalers.joblib"),
    "linear_regression": ("model.joblib", "metadata.json"),
}


def run_ssh(
    host: str,
    command: str,
    *,
    port: int | None = None,
    identity: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """Run a shell command on the remote host over SSH."""
    ssh = ["ssh", "-o", "BatchMode=yes"]
    if port:
        ssh += ["-p", str(port)]
    if identity:
        ssh += ["-i", identity]
    ssh += [host, command]
    result = subprocess.run(ssh, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"ssh command failed ({result.returncode}): {command}\n"
            f"stdout: {result.stdout.strip()}\nstderr: {result.stderr.strip()}"
        )
    return result


def discover_models(models_dir: Path) -> dict[str, dict[str, Path]]:
    """Map ``{symbol: {model_name: directory}}`` for every trained model."""
    found: dict[str, dict[str, Path]] = {}
    if not models_dir.exists():
        return found
    for symbol_dir in sorted(models_dir.iterdir()):
        if not symbol_dir.is_dir():
            continue
        for model_dir in sorted(symbol_dir.iterdir()):
            if not model_dir.is_dir():
                continue
            if not (model_dir / "metadata.json").exists():
                # A directory without metadata is a leftover, not a model.
                continue
            found.setdefault(symbol_dir.name, {})[model_dir.name] = model_dir
    return found


def missing_artefacts(model_name: str, model_dir: Path) -> list[str]:
    """Return the required artefact names that are missing or empty."""
    required = REQUIRED_ARTEFACTS.get(model_name, ("metadata.json",))
    missing: list[str] = []
    for name in required:
        path = model_dir / name
        if not path.exists() or path.stat().st_size == 0:
            missing.append(name)
    return missing


def pack_model(model_dir: Path, archive_path: Path) -> int:
    """Pack a model directory into a ``tar.gz`` and return its byte size."""
    with tarfile.open(archive_path, "w:gz") as tar:
        for item in sorted(model_dir.iterdir()):
            if item.is_file():
                tar.add(item, arcname=item.name)
    return archive_path.stat().st_size


def deploy_model(
    host: str,
    symbol: str,
    model_name: str,
    archive_path: Path,
    *,
    remote_root: str,
    remote_port: int | None,
    identity: str | None,
    include_predictions: bool,
) -> dict:
    """Upload one model archive and swap it into place on the VPS."""
    remote_models = f"{remote_root.rstrip('/')}/data/models"
    remote_target = f"{remote_models}/{symbol}/{model_name}"
    staging = f"{remote_models}/.staging_{symbol}_{model_name}"
    remote_archive = f"/tmp/model_{symbol}_{model_name}.tar.gz"

    # 1. Clean any stale staging directory, then create a fresh one.
    run_ssh(
        host,
        f"rm -rf {staging} && mkdir -p {staging}",
        port=remote_port,
        identity=identity,
    )

    # 2. Upload the archive.
    scp = ["scp", "-q"]
    if remote_port:
        scp += ["-P", str(remote_port)]
    if identity:
        scp += ["-i", identity]
    scp += [str(archive_path), f"{host}:{remote_archive}"]
    upload = subprocess.run(scp, capture_output=True, text=True)
    if upload.returncode != 0:
        raise RuntimeError(
            f"scp failed for {symbol}/{model_name}: {upload.stderr.strip()}"
        )

    # 3. Extract into staging and verify the artefacts landed.
    required = REQUIRED_ARTEFACTS.get(model_name, ("metadata.json",))
    verify_expr = " && ".join(
        f'test -s {staging}/{name}' for name in required
    )
    extract = run_ssh(
        host,
        f"tar -xzf {remote_archive} -C {staging} && {verify_expr} && rm -f {remote_archive}",
        port=remote_port,
        identity=identity,
    )

    # 4. Swap staging into the live location.
    run_ssh(
        host,
        f"mkdir -p {remote_models}/{symbol} && rm -rf {remote_target} && "
        f"mv {staging} {remote_target}",
        port=remote_port,
        identity=identity,
    )

    return {
        "symbol": symbol,
        "model": model_name,
        "remote_path": remote_target,
        "verified": True,
        "output": extract.stdout.strip(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=None, help="SSH target, e.g. user@vps")
    parser.add_argument("--port", type=int, default=None, help="SSH port")
    parser.add_argument("--identity", default=None, help="SSH private key file")
    parser.add_argument(
        "--remote-root",
        default="/opt/stock-lakehouse",
        help="Project root on the VPS (default: /opt/stock-lakehouse)",
    )
    parser.add_argument(
        "--symbol",
        action="append",
        default=[],
        help="Sync only this symbol (repeatable)",
    )
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="Sync only this model name (repeatable)",
    )
    parser.add_argument(
        "--all", action="store_true", help="Sync every trained model found locally"
    )
    parser.add_argument(
        "--list", action="store_true", help="List the local models and exit"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Pack and report, but do not upload anything",
    )
    parser.add_argument(
        "--include-predictions",
        action="store_true",
        help="Also copy predictions.parquet (the audit trail)",
    )
    args = parser.parse_args(argv)

    models = discover_models(MODELS_DIR)
    if not models:
        print("No trained models found locally. Train one first:", file=sys.stderr)
        print(f"  expected layout: {MODELS_DIR / '<SYMBOL>' / '<MODEL>'}", file=sys.stderr)
        return 1

    if args.list:
        print(f"{'SYMBOL':10} {'MODEL':20} {'ARTEFACTS':40} STATE")
        for symbol, per_model in models.items():
            for model_name, model_dir in per_model.items():
                missing = missing_artefacts(model_name, model_dir)
                state = "INCOMPLETE " + ",".join(missing) if missing else "ok"
                names = ",".join(sorted(p.name for p in model_dir.iterdir() if p.is_file()))
                print(f"{symbol:10} {model_name:20} {names[:40]:40} {state}")
        return 0

    if not args.host:
        print("--host is required (or use --list).", file=sys.stderr)
        return 2

    selected: list[tuple[str, str, Path]] = []
    for symbol, per_model in models.items():
        if args.symbol and symbol.upper() not in {s.upper() for s in args.symbol}:
            continue
        for model_name, model_dir in per_model.items():
            if args.model and model_name not in args.model:
                continue
            selected.append((symbol, model_name, model_dir))

    if not selected:
        print("Nothing matched the given filters.", file=sys.stderr)
        return 1

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": args.host,
        "remote_root": args.remote_root,
        "include_predictions": args.include_predictions,
        "deployed": [],
        "skipped": [],
    }

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        for symbol, model_name, model_dir in selected:
            missing = missing_artefacts(model_name, model_dir)
            if missing:
                # NEVER publish a half-model. Skip it and say so.
                manifest["skipped"].append(
                    {"symbol": symbol, "model": model_name, "reason": f"missing artefacts: {missing}"}
                )
                print(f"SKIP  {symbol}/{model_name} - missing {missing}")
                continue

            # Pack only what is needed.
            with tempfile.TemporaryDirectory() as pack_dir:
                pack_dir_path = Path(pack_dir)
                for item in model_dir.iterdir():
                    if item.is_file():
                        if item.name == "predictions.parquet" and not args.include_predictions:
                            continue
                        shutil.copy2(item, pack_dir_path / item.name)
                archive = tmpdir / f"{symbol}_{model_name}.tar.gz"
                size = pack_model(pack_dir_path, archive)

            if args.dry_run:
                manifest["deployed"].append(
                    {"symbol": symbol, "model": model_name, "bytes": size, "dry_run": True}
                )
                print(f"DRY   {symbol}/{model_name} - {size} bytes")
                continue

            result = deploy_model(
                args.host,
                symbol,
                model_name,
                archive,
                remote_root=args.remote_root,
                remote_port=args.port,
                identity=args.identity,
                include_predictions=args.include_predictions,
            )
            result["bytes"] = size
            manifest["deployed"].append(result)
            print(f"OK    {symbol}/{model_name} -> {result['remote_path']} ({size} bytes)")

    manifest_path = MODELS_DIR / "sync_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\nManifest: {manifest_path}")
    print(
        f"deployed={len(manifest['deployed'])} skipped={len(manifest['skipped'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
