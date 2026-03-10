import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def resolve_pairs_manifest(
    pairs_manifest: str | None,
    signals_manifest: str | None,
) -> Path:
    if pairs_manifest:
        return Path(pairs_manifest)
    if not signals_manifest:
        raise ValueError("pairs-manifest or signals-manifest is required")
    manifest_path = Path(signals_manifest)
    with open(manifest_path, "r", encoding="utf-8") as f:
        payload = json.load(f)
    rel = payload.get("active_universe_file") or payload.get("active_pairs_file")
    if not rel:
        raise ValueError("active_pairs_file missing in signals manifest")
    return (manifest_path.parent / rel).resolve()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--freqtrade-exe", required=True)
    parser.add_argument("--base-config", required=True)
    parser.add_argument("--pairs-manifest")
    parser.add_argument("--signals-manifest")
    parser.add_argument("--timeframes", default="4h")
    parser.add_argument("--timerange", required=True)
    parser.add_argument("--trading-mode", default="futures")
    parser.add_argument("--force-online", action="store_true")
    args = parser.parse_args()

    pairs_manifest = resolve_pairs_manifest(args.pairs_manifest, args.signals_manifest)
    with open(args.base_config, "r", encoding="utf-8") as f:
        config = json.load(f)
    with open(pairs_manifest, "r", encoding="utf-8") as f:
        pair_payload = json.load(f)

    exchange_cfg = config.setdefault("exchange", {})
    if args.force_online:
        exchange_cfg["offline_mode"] = False
    pair_whitelist = pair_payload.get("exchange", {}).get("pair_whitelist", [])
    pair_blacklist = set(pair_payload.get("exchange", {}).get("pair_blacklist", []))
    exchange_cfg["pair_whitelist"] = [p for p in pair_whitelist if p not in pair_blacklist]
    exchange_cfg["pair_blacklist"] = sorted(pair_blacklist)

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=True, indent=2)
        temp_config_path = Path(f.name)

    cmd = [
        args.freqtrade_exe,
        "download-data",
        "-c",
        str(temp_config_path),
        "--exchange",
        exchange_cfg.get("name", "binance"),
        "--trading-mode",
        args.trading_mode,
        "--timeframes",
        *[x.strip() for x in args.timeframes.split(",") if x.strip()],
        "--timerange",
        args.timerange,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr)
        raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
