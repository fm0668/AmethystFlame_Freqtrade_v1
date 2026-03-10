import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


def to_pair(symbol: str) -> str:
    if not symbol.endswith("USDT"):
        raise ValueError(f"Unsupported symbol: {symbol}")
    return f"{symbol[:-4]}/USDT:USDT"


def atomic_write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=True, indent=2)
    tmp.replace(path)


def build_signals(detail_csv: Path) -> tuple[dict, list[str]]:
    df = pd.read_csv(detail_csv)
    if df.empty:
        raise ValueError("detail csv is empty")
    df["pair"] = df["symbol"].map(to_pair)
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    df["abs_score"] = df["score"].abs()
    dedup = df.sort_values("abs_score", ascending=False).drop_duplicates(["pair", "ts"], keep="first")
    signals: dict[str, dict[str, list[str]]] = {}
    for pair, g in dedup.groupby("pair"):
        long_ts = g[g["side"] == "long"]["ts"].sort_values().dt.strftime("%Y-%m-%dT%H:%M:%SZ").tolist()
        short_ts = g[g["side"] == "short"]["ts"].sort_values().dt.strftime("%Y-%m-%dT%H:%M:%SZ").tolist()
        signals[pair] = {"long": long_ts, "short": short_ts}
    return {"generated_from": str(detail_csv.resolve()), "signals": signals}, sorted(signals.keys())


def build_universe_pairs(symbols_file: Path | None, excluded_symbols: set[str]) -> list[str]:
    if not symbols_file:
        return []
    symbols: list[str] = []
    try:
        with open(symbols_file, "r", encoding="utf-8") as f:
            symbols = [x.strip() for x in f if x.strip()]
    except UnicodeDecodeError:
        with open(symbols_file, "r", encoding="gbk") as f:
            symbols = [x.strip() for x in f if x.strip()]
    universe = []
    for s in symbols:
        if s in excluded_symbols:
            continue
        try:
            universe.append(to_pair(s))
        except ValueError:
            continue
    return sorted(set(universe))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--detail-csv", required=True)
    parser.add_argument("--signals-dir", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--active-params-file")
    parser.add_argument("--params-version")
    parser.add_argument("--universe-symbols-file")
    parser.add_argument("--excluded-symbols", default="BTCDOMUSDT,DEFIUSDT,FOOTBALLUSDT,BLUEBIRDUSDT")
    args = parser.parse_args()

    detail_csv = Path(args.detail_csv)
    signals_dir = Path(args.signals_dir)
    excluded_symbols = {x.strip() for x in args.excluded_symbols.split(",") if x.strip()}
    symbols_file = Path(args.universe_symbols_file) if args.universe_symbols_file else None
    signal_payload, pairs = build_signals(detail_csv)
    universe_pairs = build_universe_pairs(symbols_file, excluded_symbols)
    if not universe_pairs:
        universe_pairs = pairs
    signal_file = signals_dir / f"cs_{args.tag}.json"
    pairs_file = signals_dir / f"pairs_{args.tag}.json"
    universe_file = signals_dir / f"universe_{args.tag}.json"
    runtime_pairs_file = signals_dir / "runtime_pairs.json"

    atomic_write_json(signal_file, signal_payload)
    atomic_write_json(
        pairs_file,
        {"exchange": {"pair_whitelist": pairs, "pair_blacklist": []}},
    )
    atomic_write_json(
        universe_file,
        {"exchange": {"pair_whitelist": universe_pairs, "pair_blacklist": []}},
    )
    atomic_write_json(
        runtime_pairs_file,
        {"exchange": {"pair_whitelist": universe_pairs, "pair_blacklist": []}},
    )

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    atomic_write_json(
        signals_dir / "manifest.json",
        {
            "version": args.tag,
            "updated_at": now,
            "active_signal_file": signal_file.name,
            "active_pairs_file": pairs_file.name,
            "active_universe_file": universe_file.name,
            "active_runtime_pairs_file": runtime_pairs_file.name,
            "source_detail_csv": str(detail_csv.resolve()),
        },
    )

    if args.active_params_file:
        atomic_write_json(
            signals_dir / "params_manifest.json",
            {
                "version": args.params_version or args.tag,
                "updated_at": now,
                "active_params_file": args.active_params_file,
            },
        )

    print(f"published signals={len(pairs)} universe={len(universe_pairs)} version={args.tag}")


if __name__ == "__main__":
    main()
