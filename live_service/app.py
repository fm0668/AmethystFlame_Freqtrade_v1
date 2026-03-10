from __future__ import annotations

import argparse
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path

from .binance_client import BinanceClient
from .config import LiveServiceConfig, load_config
from .publisher import publish_run
from .signal_engine import add_features, build_panel, build_signal_payload, select_current_signals
from .storage import LiveStore


_PARAMS_CACHE = {
    "params_mtime": None,
    "params_path": None,
    "models": None,
    "params_version": None,
    "active_params_file": None,
}


def load_symbols(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    symbols = []
    for line in raw:
        s = line.strip().upper()
        if not s:
            continue
        if s.endswith("USDT"):
            symbols.append(s)
    return sorted(set(symbols))


def _sync_symbol(
    client: BinanceClient,
    symbol: str,
    timeframe: str,
    kline_limit: int,
    aux_limit: int,
) -> dict:
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    try:
        bars = client.fetch_klines(symbol=symbol, interval=timeframe, limit=kline_limit)
    except Exception:
        bars = []
    bars = [x for x in bars if int(x["close_time"]) < now_ms]
    try:
        funding = client.fetch_funding_rate(symbol=symbol, limit=max(20, aux_limit))
    except Exception:
        funding = []
    try:
        oi = client.fetch_open_interest_hist(symbol=symbol, period=timeframe, limit=aux_limit)
    except Exception:
        oi = []
    try:
        global_lsr = client.fetch_global_lsr(symbol=symbol, period=timeframe, limit=aux_limit)
    except Exception:
        global_lsr = []
    try:
        top_lsr = client.fetch_top_position_lsr(symbol=symbol, period=timeframe, limit=aux_limit)
    except Exception:
        top_lsr = []
    return {
        "bars": bars,
        "funding": funding,
        "oi": oi,
        "global_lsr": global_lsr,
        "top_lsr": top_lsr,
    }


def sync_all(
    store: LiveStore, client: BinanceClient, cfg: LiveServiceConfig, symbols: list[str], bootstrap: bool
) -> dict[str, int]:
    kline_limit = cfg.history_bars if bootstrap else 3
    aux_limit = min(cfg.history_bars, 120) if bootstrap else 5
    max_workers = min(8, max(2, len(symbols) // 80))
    ok = 0
    failed = 0
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_sync_symbol, client, s, cfg.timeframe, kline_limit, aux_limit): s for s in symbols
        }
        for ft in as_completed(futures):
            try:
                payload = ft.result()
            except Exception:
                failed += 1
                continue
            if not payload["bars"]:
                failed += 1
                continue
            store.upsert_bars(payload["bars"])
            store.upsert_funding(payload["funding"])
            store.upsert_oi(payload["oi"])
            store.upsert_global_lsr(payload["global_lsr"])
            store.upsert_top_lsr(payload["top_lsr"])
            ok += 1
    store.mark_sync_time(int(datetime.now(UTC).timestamp() * 1000))
    return {"ok": ok, "failed": failed}


def _timeframe_milliseconds(timeframe: str) -> int:
    unit = timeframe[-1].lower()
    val = int(timeframe[:-1])
    if unit == "m":
        return val * 60 * 1000
    if unit == "h":
        return val * 60 * 60 * 1000
    if unit == "d":
        return val * 24 * 60 * 60 * 1000
    raise ValueError(f"unsupported timeframe: {timeframe}")


def _current_closed_open_time_ms(timeframe: str) -> int:
    frame_ms = _timeframe_milliseconds(timeframe)
    now_ms = int(datetime.now(UTC).timestamp() * 1000)
    return ((now_ms // frame_ms) - 1) * frame_ms


def _latest_timestamped_json(directory: Path, prefix: str) -> Path | None:
    if not directory.exists():
        return None
    files = list(directory.glob(f"{prefix}*.json"))
    if not files:
        return None
    ts_pat = re.compile(rf"^{re.escape(prefix)}(\d{{8}}_\d{{4}})\.json$")

    def sort_key(p: Path):
        m = ts_pat.match(p.name)
        if m:
            return m.group(1), p.stat().st_mtime
        return "", p.stat().st_mtime

    files.sort(key=sort_key)
    return files[-1]


def _load_runtime_models(cfg: LiveServiceConfig) -> tuple[dict | None, str, str]:
    params_path = _latest_timestamped_json(cfg.params_dir, "params_")
    if params_path is None:
        params_path = (cfg.params_dir / cfg.active_params_file).resolve()
    if not params_path.exists():
        return None, cfg.params_version, cfg.active_params_file
    params_version = cfg.params_version
    active_params_file = params_path.name
    params_mtime = params_path.stat().st_mtime
    if (
        _PARAMS_CACHE["params_path"] == str(params_path)
        and _PARAMS_CACHE["params_mtime"] == params_mtime
        and _PARAMS_CACHE["models"] is not None
    ):
        return _PARAMS_CACHE["models"], str(_PARAMS_CACHE["params_version"]), str(_PARAMS_CACHE["active_params_file"])
    with open(params_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    models = payload.get("models")
    if not isinstance(models, dict):
        return None, params_version, active_params_file
    params_version = str(payload.get("version", params_version))
    _PARAMS_CACHE["params_path"] = str(params_path)
    _PARAMS_CACHE["params_mtime"] = params_mtime
    _PARAMS_CACHE["models"] = models
    _PARAMS_CACHE["params_version"] = params_version
    _PARAMS_CACHE["active_params_file"] = active_params_file
    return models, params_version, active_params_file


def maybe_emit_signals(store: LiveStore, cfg: LiveServiceConfig, symbols: list[str]) -> dict | None:
    latest_open_time = store.latest_closed_open_time()
    if latest_open_time <= 0:
        return None
    last_emitted = store.get_last_emitted_open_time()
    if latest_open_time <= last_emitted:
        return None
    panel = build_panel(store=store, symbols=symbols, bars=max(48, cfg.signal_history_bars))
    if panel.empty:
        return None
    panel = add_features(panel)
    models, params_version, active_params_file = _load_runtime_models(cfg)
    if models is None:
        return None
    latest_ts = datetime.fromtimestamp(latest_open_time / 1000, tz=UTC)
    selected = select_current_signals(panel=panel, latest_ts=latest_ts, models=models)
    payload, selected_pairs, score_details = build_signal_payload(
        selected=selected,
        top_n=cfg.top_n,
        long_threshold=cfg.long_threshold,
        short_threshold=cfg.short_threshold,
    )
    run_id = f"{cfg.run_tag_prefix}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    manifest = publish_run(
        signals_dir=cfg.signals_dir,
        run_id=run_id,
        signal_payload=payload,
        selected_pairs=selected_pairs,
        universe_pairs=[f"{s[:-4]}/USDT:USDT" for s in symbols if s.endswith("USDT")],
        bar_open_time_ms=latest_open_time,
        params_version=params_version,
        active_params_file=active_params_file,
        score_details=score_details,
    )
    store.set_last_emitted_open_time(latest_open_time)
    return manifest


def run(cfg: LiveServiceConfig) -> None:
    symbols = load_symbols(cfg.symbols_file)
    if not symbols:
        raise ValueError(f"no symbols loaded from {cfg.symbols_file}")
    store = LiveStore(cfg.database_path)
    client = BinanceClient(base_url=cfg.binance_futures_base_url)
    last_sync = 0.0
    bootstrap = True
    while True:
        now = time.time()
        target_closed_open = _current_closed_open_time_ms(cfg.timeframe)
        should_sync = bootstrap or (store.latest_closed_open_time() < target_closed_open)
        if should_sync and now - last_sync >= cfg.sync_interval_seconds:
            stats = sync_all(store=store, client=client, cfg=cfg, symbols=symbols, bootstrap=bootstrap)
            bootstrap = False
            last_sync = now
            print(
                f"[live_service] sync ok={stats['ok']} failed={stats['failed']} "
                f"latest_closed_open_time={datetime.fromtimestamp(store.latest_closed_open_time() / 1000, tz=UTC).strftime('%Y-%m-%dT%H:%M:%SZ')}"
            )
            manifest = maybe_emit_signals(store=store, cfg=cfg, symbols=symbols)
            if manifest:
                print(
                    f"[live_service] emitted run_id={manifest['run_id']} "
                    f"bar_open_time={manifest['bar_open_time']} selected={manifest['selected_pairs_count']}"
                )
        time.sleep(cfg.loop_sleep_seconds)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    cfg = load_config(args.config)
    run(cfg)


if __name__ == "__main__":
    main()

