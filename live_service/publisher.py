from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.flush()
    tmp.replace(path)


def payload_sha256(payload: dict) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def publish_run(
    signals_dir: Path,
    run_id: str,
    signal_payload: dict,
    selected_pairs: list[str],
    universe_pairs: list[str],
    bar_open_time_ms: int,
    params_version: str,
    active_params_file: str,
    score_details: list[dict],
) -> dict:
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    bar_open_iso = datetime.fromtimestamp(bar_open_time_ms / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    signal_file = f"cs_{run_id}.json"
    pairs_file = f"pairs_{run_id}.json"
    universe_file = f"universe_{run_id}.json"
    runtime_pairs_file = "runtime_pairs.json"
    score_file = f"score_{run_id}.json"
    runtime_pairs = sorted(set(selected_pairs))

    atomic_write_json(signals_dir / signal_file, signal_payload)
    atomic_write_json(
        signals_dir / pairs_file,
        {"exchange": {"pair_whitelist": selected_pairs, "pair_blacklist": []}},
    )
    atomic_write_json(
        signals_dir / universe_file,
        {"exchange": {"pair_whitelist": universe_pairs, "pair_blacklist": []}},
    )
    atomic_write_json(
        signals_dir / runtime_pairs_file,
        {"exchange": {"pair_whitelist": runtime_pairs, "pair_blacklist": []}},
    )
    atomic_write_json(signals_dir / score_file, {"run_id": run_id, "items": score_details})

    manifest = {
        "version": run_id,
        "run_id": run_id,
        "updated_at": now,
        "bar_open_time": bar_open_iso,
        "bar_open_time_ms": bar_open_time_ms,
        "active_signal_file": signal_file,
        "active_pairs_file": pairs_file,
        "active_universe_file": universe_file,
        "active_runtime_pairs_file": runtime_pairs_file,
        "active_score_file": score_file,
        "selected_pairs_count": len(selected_pairs),
        "signal_checksum": payload_sha256(signal_payload),
        "manifest_schema_version": "2.0",
    }
    atomic_write_json(signals_dir / "manifest.json", manifest)

    return manifest

