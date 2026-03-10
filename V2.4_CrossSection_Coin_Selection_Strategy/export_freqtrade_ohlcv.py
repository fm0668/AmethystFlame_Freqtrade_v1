import argparse
import json
from pathlib import Path

import pandas as pd

from run_v2_walkforward_4h import load_kline_4h


def pair_to_symbol(pair: str) -> str:
    left = pair.split(":")[0]
    base, quote = left.split("/")
    return f"{base}{quote}"


def pair_to_filename(pair: str) -> str:
    s = pair
    for ch in ["/", " ", ".", "@", "$", "+", ":"]:
        s = s.replace(ch, "_")
    return s


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--signals-json", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    args = parser.parse_args()

    with open(args.signals_json, "r", encoding="utf-8") as f:
        payload = json.load(f)
    pairs = sorted(payload.get("signals", {}).keys())
    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC")
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    for pair in pairs:
        symbol = pair_to_symbol(pair)
        k = load_kline_4h(symbol)
        if k is None or k.empty:
            continue
        x = k[["ts", "open", "high", "low", "close", "quote_volume"]].copy()
        x = x.rename(columns={"ts": "date", "quote_volume": "volume"})
        x = x[(x["date"] >= start) & (x["date"] <= end)].copy()
        if x.empty:
            continue
        fn = f"{pair_to_filename(pair)}-4h-futures.feather"
        x = x.sort_values("date")
        x.to_feather(out_dir / fn)
        written += 1
    print(f"written_pairs={written}")


if __name__ == "__main__":
    main()
