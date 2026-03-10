from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from live_service.app import load_symbols, sync_all
from live_service.binance_client import BinanceClient
from live_service.config import load_config
from live_service.signal_engine import add_features, build_panel
from live_service.storage import LiveStore
from run_v2_4_long_focus import derive_regime_model, evaluate, factor_ic
from run_v2_walkforward_4h import classify_regime


def sanitize_json(value):
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, dict):
        return {k: sanitize_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_json(v) for v in value]
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live-config", default="../live_service/config.live.example.yaml")
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--test-days", type=int, default=1)
    parser.add_argument("--params-file", default=None)
    parser.add_argument("--params-version-prefix", default="train")
    parser.add_argument("--output-prefix", default=None)
    args = parser.parse_args()

    root = ROOT
    cfg_path = Path(args.live_config)
    if not cfg_path.is_absolute():
        candidate1 = (root / cfg_path).resolve()
        candidate2 = (PROJECT_ROOT / cfg_path).resolve()
        cfg_path = candidate1 if candidate1.exists() else candidate2
    cfg = load_config(cfg_path)
    symbols = [s for s in load_symbols(cfg.symbols_file) if re.fullmatch(r"[A-Z0-9]+USDT", s)]
    store = LiveStore(cfg.database_path)
    client = BinanceClient(base_url=cfg.binance_futures_base_url)
    sync_all(store=store, client=client, cfg=cfg, symbols=symbols, bootstrap=True)
    bars = max(cfg.history_bars, args.lookback_days * 6 + 16)
    panel = build_panel(store=store, symbols=symbols, bars=bars)
    panel = add_features(panel)
    panel_for_train = panel.merge(classify_regime(panel), on="ts", how="left")
    latest_ts = panel["ts"].max()
    if pd.isna(latest_ts):
        raise ValueError("同步后未获得可用4H数据")
    train_end = latest_ts - pd.Timedelta(hours=4)
    train_start = train_end - pd.Timedelta(days=args.lookback_days)
    train = panel_for_train[(panel_for_train["ts"] >= train_start) & (panel_for_train["ts"] <= train_end)].copy()
    if train.empty:
        raise ValueError("训练窗口无数据")
    models = derive_regime_model(train)
    test_end = train_end
    test_start = test_end - pd.Timedelta(days=args.test_days) + pd.Timedelta(hours=4)
    stamp = latest_ts.strftime("%Y%m%d_%H%M")
    output_prefix = args.output_prefix or f"live_prod_{stamp}"
    summary, detail, weights, panel_all = evaluate(
        panel,
        test_start=test_start,
        test_end=test_end,
        output_prefix=str(root / output_prefix),
        fixed_train_start=train_start,
        fixed_train_end=train_end,
    )
    ic = factor_ic(panel_all, test_start, test_end)
    summary.to_csv(root / f"{output_prefix}_summary.csv", index=False)
    detail.to_csv(root / f"{output_prefix}_detail.csv", index=False)
    weights.to_csv(root / f"{output_prefix}_weights.csv", index=False)
    ic.to_csv(root / f"{output_prefix}_factor_ic.csv", index=False)
    if not summary.empty:
        agg = pd.DataFrame(
            [
                {
                    "avg_long_ret_4h": summary["long_ret_4h"].mean(),
                    "avg_short_ret_4h": summary["short_ret_4h"].mean(),
                    "avg_combo_ret_4h": summary["combo_ret_4h"].mean(),
                    "avg_long_hit_rate": summary["long_hit_rate"].mean(),
                    "avg_short_hit_rate": summary["short_hit_rate"].mean(),
                }
            ]
        )
    else:
        agg = pd.DataFrame([{}])
    agg.to_csv(root / f"{output_prefix}_aggregate.csv", index=False)

    params_rel = Path(args.params_file) if args.params_file else Path(f"params_{stamp}.json")
    if params_rel.is_absolute():
        raise ValueError("params-file 需为相对 params_dir 的路径")
    params_path = (cfg.params_dir / params_rel).resolve()
    params_path.parent.mkdir(parents=True, exist_ok=True)
    params_payload = {
        "version": f"{args.params_version_prefix}_{stamp}",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "latest_synced_ts": latest_ts.isoformat(),
        "train_window": {"start": train_start.isoformat(), "end": train_end.isoformat()},
        "test_window": {"start": test_start.isoformat(), "end": test_end.isoformat()},
        "models": sanitize_json(models),
    }
    with open(params_path, "w", encoding="utf-8") as f:
        json.dump(params_payload, f, ensure_ascii=False, indent=2)
    print(
        f"latest_ts={latest_ts.isoformat()} train_start={train_start.isoformat()} "
        f"train_end={train_end.isoformat()} test_start={test_start.isoformat()} "
        f"test_end={test_end.isoformat()} params_out={params_path} "
        f"output_prefix={output_prefix}"
    )


if __name__ == "__main__":
    main()
