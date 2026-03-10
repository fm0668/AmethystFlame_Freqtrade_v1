# 运行编排建议

## 时区策略

- 统一以 UTC 作为状态机与训练窗口时间基准。
- 调度触发可以用本地时区。
- 北京时间 22:00 可作为每日补下载触发点，对应 UTC 14:00。
- 若需紧贴 4H 收线后执行，建议用 UTC 的 00:05 / 04:05 / 08:05 / 12:05 / 16:05 / 20:05。

## 本地 Windows

- 先复制 `pipeline_config.template.json` 为 `pipeline_config.local.json` 并按环境改路径。
- 运行 `scheduler_windows.ps1` 注册每天 22:00 任务。
- 任务会执行 `pipeline_runner.py`，按状态机决定补下载与是否训练发布。

## VPS

- 在 VPS 上使用同一套 `pipeline_runner.py` 与配置文件。
- 用 `cron` 调度 `scheduler_linux.sh` 或直接写定时任务。
- 可增加每小时一次的下载任务，训练保持每 48 小时。

## 参数分发

- 本地训练完成后由 `publish_signal_bundle.py` 发布 signal/params manifest。
- 若启用私有 GitHub 分发，VPS 用 `run_vps_watcher.py` 周期拉取并生效。
- watcher 失败时会回滚到拉取前 commit。
