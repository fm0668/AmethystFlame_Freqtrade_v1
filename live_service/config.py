from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(slots=True)
class LiveServiceConfig:
    symbols_file: Path
    signals_dir: Path
    params_dir: Path
    database_path: Path
    timeframe: str
    history_bars: int
    signal_history_bars: int
    top_n: int
    long_threshold: float
    short_threshold: float
    sync_interval_seconds: int
    loop_sleep_seconds: int
    run_tag_prefix: str
    binance_futures_base_url: str
    active_params_file: str
    params_version: str


def load_config(path: str | Path) -> LiveServiceConfig:
    p = Path(path)
    payload = yaml.safe_load(p.read_text(encoding="utf-8"))
    base = p.parent.resolve()

    def resolve_local(value: str) -> Path:
        q = Path(value)
        return q if q.is_absolute() else (base / q).resolve()

    return LiveServiceConfig(
        symbols_file=resolve_local(payload["symbols_file"]),
        signals_dir=resolve_local(payload["signals_dir"]),
        params_dir=resolve_local(payload.get("params_dir", "./params")),
        database_path=resolve_local(payload["database_path"]),
        timeframe=str(payload.get("timeframe", "4h")),
        history_bars=int(payload.get("history_bars", 200)),
        signal_history_bars=int(payload.get("signal_history_bars", 72)),
        top_n=int(payload.get("top_n", 10)),
        long_threshold=float(payload.get("long_threshold", 0.0)),
        short_threshold=float(payload.get("short_threshold", 0.0)),
        sync_interval_seconds=int(payload.get("sync_interval_seconds", 120)),
        loop_sleep_seconds=int(payload.get("loop_sleep_seconds", 2)),
        run_tag_prefix=str(payload.get("run_tag_prefix", "live_realtime")),
        binance_futures_base_url=str(payload.get("binance_futures_base_url", "https://fapi.binance.com")),
        active_params_file=str(payload.get("active_params_file", "params_v1.json")),
        params_version=str(payload.get("params_version", "v1")),
    )
