import argparse
import json
from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass
class FileQuality:
    file: str
    rows: int
    duplicate_rows: int
    gap_count: int
    anomaly_count: int
    fixed_duplicates: bool


def load_frame(path: Path) -> pd.DataFrame:
    df = pd.read_feather(path)
    if "date" not in df.columns:
        raise ValueError(f"missing date column: {path}")
    df["date"] = pd.to_datetime(df["date"], utc=True)
    return df


def check_one(path: Path, timeframe_hours: int, auto_fix_duplicates: bool) -> FileQuality:
    df = load_frame(path)
    fixed = False
    dup = int(df["date"].duplicated(keep="last").sum())
    if dup > 0 and auto_fix_duplicates:
        df = df.sort_values("date").drop_duplicates(subset=["date"], keep="last")
        df.reset_index(drop=True, inplace=True)
        df.to_feather(path)
        fixed = True
        dup = 0

    sorted_ts = df["date"].sort_values()
    d = sorted_ts.diff().dropna()
    step = pd.Timedelta(hours=timeframe_hours)
    gaps = int((d > step).sum())

    anomaly_cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    anomaly = 0
    if {"open", "high", "low", "close"}.issubset(set(df.columns)):
        anomaly += int((df["high"] < df["low"]).sum())
        anomaly += int((df["open"] <= 0).sum())
        anomaly += int((df["high"] <= 0).sum())
        anomaly += int((df["low"] <= 0).sum())
        anomaly += int((df["close"] <= 0).sum())
    if "volume" in anomaly_cols:
        anomaly += int((df["volume"] < 0).sum())

    return FileQuality(
        file=str(path),
        rows=int(len(df)),
        duplicate_rows=dup,
        gap_count=gaps,
        anomaly_count=anomaly,
        fixed_duplicates=fixed,
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--timeframe-hours", type=int, default=4)
    parser.add_argument("--auto-fix-duplicates", action="store_true")
    parser.add_argument("--report-json", required=True)
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    files = sorted(data_dir.glob("*.feather"))
    results: list[FileQuality] = []
    for fp in files:
        try:
            results.append(check_one(fp, args.timeframe_hours, args.auto_fix_duplicates))
        except Exception:
            results.append(
                FileQuality(
                    file=str(fp),
                    rows=0,
                    duplicate_rows=0,
                    gap_count=1,
                    anomaly_count=1,
                    fixed_duplicates=False,
                )
            )

    total = {
        "files": len(results),
        "rows": int(sum(r.rows for r in results)),
        "duplicate_rows": int(sum(r.duplicate_rows for r in results)),
        "gap_count": int(sum(r.gap_count for r in results)),
        "anomaly_count": int(sum(r.anomaly_count for r in results)),
        "fixed_duplicates_files": int(sum(1 for r in results if r.fixed_duplicates)),
    }
    payload = {
        "summary": total,
        "files": [asdict(r) for r in results],
    }
    report = Path(args.report_json)
    report.parent.mkdir(parents=True, exist_ok=True)
    with open(report, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(json.dumps(total, ensure_ascii=False))
    if total["gap_count"] > 0 or total["anomaly_count"] > 0 or total["duplicate_rows"] > 0:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
