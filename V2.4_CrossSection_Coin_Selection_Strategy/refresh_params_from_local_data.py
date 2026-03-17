from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import pandas as pd

from run_v2_walkforward_4h import build_panel, classify_regime, read_symbols
from run_v2_4_long_focus import add_features, derive_regime_model


def sanitize(value):
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(value, dict):
        return {k: sanitize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize(v) for v in value]
    return value


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lookback-days", type=int, default=30)
    parser.add_argument("--params-dir", default="../live_service/params")
    parser.add_argument("--replace-file", default="params_20260309_1200.json")
    parser.add_argument("--version-prefix", default="train")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    project_root = root.parent
    params_dir = Path(args.params_dir)
    if not params_dir.is_absolute():
        params_dir = (project_root / params_dir).resolve()
    params_dir.mkdir(parents=True, exist_ok=True)

    symbols = read_symbols()
    panel = build_panel(symbols)
    panel = add_features(panel)
    panel = panel.merge(classify_regime(panel), on="ts", how="left")
    latest_ts = pd.to_datetime(panel["ts"], utc=True).max()
    if pd.isna(latest_ts):
        raise ValueError("本地数据为空，无法训练")
    train_end = latest_ts - pd.Timedelta(hours=4)
    train_start = train_end - pd.Timedelta(days=args.lookback_days)
    train = panel[(panel["ts"] >= train_start) & (panel["ts"] <= train_end)].copy()
    if train.empty:
        raise ValueError("训练窗口无数据")
    models = derive_regime_model(train)

    train_stamp = pd.Timestamp.now("UTC").strftime("%Y%m%d_%H%M")
    payload = {
        "version": f"{args.version_prefix}_{train_stamp}",
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "latest_synced_ts": latest_ts.isoformat(),
        "train_window": {"start": train_start.isoformat(), "end": train_end.isoformat()},
        "test_window": {
            "start": (train_end - pd.Timedelta(days=1) + pd.Timedelta(hours=4)).isoformat(),
            "end": train_end.isoformat(),
        },
        "models": sanitize(models),
    }

    dated_path = params_dir / f"params_{train_stamp}.json"
    with open(dated_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    replace_path = Path(args.replace_file)
    if not replace_path.is_absolute():
        replace_path = params_dir / replace_path
    with open(replace_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(
        f"latest_ts={latest_ts.isoformat()} train_start={train_start.isoformat()} "
        f"train_end={train_end.isoformat()} params_out={dated_path} replaced={replace_path}"
    )


if __name__ == "__main__":
    main()
