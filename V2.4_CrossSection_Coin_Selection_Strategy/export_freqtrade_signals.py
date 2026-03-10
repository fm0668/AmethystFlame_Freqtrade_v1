import argparse
import json
from pathlib import Path

import pandas as pd


def to_pair(symbol: str) -> str:
    if not symbol.endswith("USDT"):
        raise ValueError(f"Unsupported symbol: {symbol}")
    base = symbol[:-4]
    return f"{base}/USDT:USDT"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--detail-csv", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--output-pairs-json", required=True)
    args = parser.parse_args()

    df = pd.read_csv(args.detail_csv)
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

    payload = {
        "generated_from": str(Path(args.detail_csv).resolve()),
        "signals": signals,
    }
    output_json = Path(args.output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    pairs = sorted(signals.keys())
    pair_payload = {
        "exchange": {
            "pair_whitelist": pairs,
            "pair_blacklist": [],
        }
    }
    output_pairs = Path(args.output_pairs_json)
    output_pairs.parent.mkdir(parents=True, exist_ok=True)
    with open(output_pairs, "w", encoding="utf-8") as f:
        json.dump(pair_payload, f, ensure_ascii=False, indent=2)
    print(f"signals={len(signals)} pairs={len(pairs)}")


if __name__ == "__main__":
    main()
