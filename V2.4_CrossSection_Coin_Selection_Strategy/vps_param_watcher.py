import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def run_cmd(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess:
    proc = subprocess.run(cmd, cwd=str(cwd), text=True, capture_output=True)
    if proc.stdout:
        print(proc.stdout)
    if proc.returncode != 0 and proc.stderr:
        print(proc.stderr)
    return proc


def file_hash(path: Path) -> str:
    if not path.exists():
        return ""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(65536)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-dir", required=True)
    parser.add_argument("--branch", default="main")
    parser.add_argument("--watch-files", required=True)
    parser.add_argument("--health-command")
    parser.add_argument("--reload-command")
    parser.add_argument("--state-json", required=True)
    args = parser.parse_args()

    repo = Path(args.repo_dir).resolve()
    watch_files = [repo / x.strip() for x in args.watch_files.split(",") if x.strip()]
    before = {str(p): file_hash(p) for p in watch_files}
    head_before = run_cmd(["git", "rev-parse", "HEAD"], repo)
    if head_before.returncode != 0:
        raise SystemExit(head_before.returncode)
    head_before_sha = head_before.stdout.strip()

    proc_fetch = run_cmd(["git", "fetch", "origin", args.branch], repo)
    if proc_fetch.returncode != 0:
        raise SystemExit(proc_fetch.returncode)
    proc_pull = run_cmd(["git", "pull", "--ff-only", "origin", args.branch], repo)
    if proc_pull.returncode != 0:
        raise SystemExit(proc_pull.returncode)

    after = {str(p): file_hash(p) for p in watch_files}
    changed = [p for p in before if before[p] != after[p]]
    if not changed:
        print("no manifest changes")
        return

    if args.reload_command:
        parts = [x for x in args.reload_command.split(" ") if x]
        proc_reload = run_cmd(parts, repo)
        if proc_reload.returncode != 0:
            raise SystemExit(proc_reload.returncode)

    if args.health_command:
        health_parts = [x for x in args.health_command.split(" ") if x]
        proc_health = run_cmd(health_parts, repo)
        if proc_health.returncode != 0:
            run_cmd(["git", "reset", "--hard", head_before_sha], repo)
            raise SystemExit(proc_health.returncode)

    state_path = Path(args.state_json).resolve()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"changed_files": changed}, f, ensure_ascii=False, indent=2)
    print(json.dumps({"changed_files": changed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
