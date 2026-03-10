import argparse
import json
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--python-exe", required=True)
    args = parser.parse_args()

    cfg_path = Path(args.config).resolve()
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    watcher = cfg_path.parent / "vps_param_watcher.py"
    cmd = [
        args.python_exe,
        str(watcher),
        "--repo-dir",
        cfg["repo_dir"],
        "--branch",
        cfg.get("branch", "main"),
        "--watch-files",
        cfg["watch_files"],
        "--state-json",
        cfg["state_json"],
    ]
    if cfg.get("reload_command"):
        cmd.extend(["--reload-command", cfg["reload_command"]])
    if cfg.get("health_command"):
        cmd.extend(["--health-command", cfg["health_command"]])
    proc = subprocess.run(cmd, text=True)
    raise SystemExit(proc.returncode)


if __name__ == "__main__":
    main()
