import argparse
import json
import subprocess
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from pathlib import Path


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_ts(val: str | None) -> datetime | None:
    if not val:
        return None
    return datetime.fromisoformat(val.replace("Z", "+00:00"))


def to_ts(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_command(cmd: list[str], cwd: Path) -> None:
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)
    if proc.stdout:
        print(proc.stdout)
    if proc.returncode != 0:
        if proc.stderr:
            print(proc.stderr)
        raise RuntimeError(f"command failed: {' '.join(cmd)}")


def should_run(last_ts: str | None, interval_hours: int, now: datetime) -> bool:
    last = parse_ts(last_ts)
    if last is None:
        return True
    return now - last >= timedelta(hours=interval_hours)


def load_json(path: Path, default: dict) -> dict:
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--state", required=True)
    args = parser.parse_args()

    cfg_path = Path(args.config).resolve()
    state_path = Path(args.state).resolve()
    cfg = load_json(cfg_path, {})
    state = load_json(
        state_path,
        {
            "last_download_utc": None,
            "last_train_utc": None,
            "last_publish_utc": None,
            "last_publish_tag": None,
        },
    )
    now = utc_now()
    project_dir = Path(cfg["project_dir"]).resolve()
    py_train = cfg.get("python_train_exe")
    py_ops = cfg.get("python_ops_exe", py_train)
    freqtrade_exe = cfg["freqtrade_exe"]
    base_config = str((project_dir / cfg["base_config"]).resolve())
    signals_manifest = str((project_dir / cfg["signals_manifest"]).resolve())
    signals_dir = str((project_dir / cfg["signals_dir"]).resolve())
    detail_csv = str((project_dir / cfg["detail_csv"]).resolve())
    refresh_script = str((project_dir / cfg["refresh_script"]).resolve())
    quality_script = str((project_dir / cfg["quality_script"]).resolve())
    publish_script = str((project_dir / cfg["publish_script"]).resolve())
    train_cwd = Path((project_dir / cfg.get("train_cwd", ".")).resolve())
    train_interval_hours = int(cfg.get("train_interval_hours", 48))
    download_interval_hours = int(cfg.get("download_interval_hours", 24))
    download_lookback_days = int(cfg.get("download_lookback_days", 35))
    timeframe_hours = int(cfg.get("timeframe_hours", 4))
    report_json = str((project_dir / cfg["quality_report_json"]).resolve())
    timeframes = cfg.get("timeframes", "4h")
    trading_mode = cfg.get("trading_mode", "futures")

    if should_run(state.get("last_download_utc"), download_interval_hours, now):
        timerange = f"{(now - timedelta(days=download_lookback_days)).strftime('%Y%m%d')}-{now.strftime('%Y%m%d')}"
        run_command(
            [
                py_ops,
                refresh_script,
                "--freqtrade-exe",
                freqtrade_exe,
                "--base-config",
                base_config,
                "--signals-manifest",
                signals_manifest,
                "--timeframes",
                timeframes,
                "--timerange",
                timerange,
                "--trading-mode",
                trading_mode,
            ],
            project_dir,
        )
        run_command(
            [
                py_ops,
                quality_script,
                "--data-dir",
                str((Path(base_config).parent / "data" / "binance" / "futures").resolve()),
                "--timeframe-hours",
                str(timeframe_hours),
                "--auto-fix-duplicates",
                "--report-json",
                report_json,
            ],
            project_dir,
        )
        state["last_download_utc"] = to_ts(now)

    if should_run(state.get("last_train_utc"), train_interval_hours, now):
        train_cmd = cfg.get("train_command")
        if not train_cmd:
            raise RuntimeError("train_command is empty")
        run_command(train_cmd, train_cwd)
        state["last_train_utc"] = to_ts(now)

        tag = now.strftime("%Y%m%d_%H%M")
        publish_cmd = [
            py_ops,
            publish_script,
            "--detail-csv",
            detail_csv,
            "--signals-dir",
            signals_dir,
            "--tag",
            tag,
            "--active-params-file",
            cfg.get("active_params_file", "params_v1.json"),
            "--params-version",
            cfg.get("params_version", "v1"),
        ]
        if cfg.get("universe_symbols_file"):
            publish_cmd.extend(
                [
                    "--universe-symbols-file",
                    str((project_dir / cfg["universe_symbols_file"]).resolve()),
                ]
            )
        if cfg.get("excluded_symbols"):
            publish_cmd.extend(["--excluded-symbols", cfg["excluded_symbols"]])
        run_command(publish_cmd, project_dir)
        state["last_publish_utc"] = to_ts(now)
        state["last_publish_tag"] = tag

        if cfg.get("git_publish_enabled", False):
            repo = Path(cfg.get("git_repo_dir", project_dir)).resolve()
            branch = cfg.get("git_branch", "main")
            commit_prefix = cfg.get("git_commit_prefix", "auto-publish")
            run_command(["git", "add", "-A"], repo)
            run_command(["git", "commit", "-m", f"{commit_prefix} {tag}"], repo)
            run_command(["git", "push", "origin", branch], repo)

    save_json(state_path, state)
    print(json.dumps(state, ensure_ascii=False))


if __name__ == "__main__":
    main()
