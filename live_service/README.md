# live_service 最小可运行骨架

## 1. 复制配置

将 `config.live.example.yaml` 复制为 `config.live.yaml`，按本机路径或VPS路径调整：

- `symbols_file`
- `signals_dir`
- `params_dir`
- `database_path`

## 2. 安装依赖

```powershell
python -m pip install -r .\live_service\requirements_live_service.txt
```

## 3. 启动服务

```powershell
python -m live_service.app --config .\live_service\config.live.yaml
```

或直接运行：

```powershell
.\live_service\start_live_service.ps1
```

## 4. 输出产物

服务会更新 `signals_dir` 下的：

- `manifest.json`
- `runtime_pairs.json`
- `cs_<run_id>.json`
- `pairs_<run_id>.json`
- `universe_<run_id>.json`
- `score_<run_id>.json`

`manifest` 协议见 `manifest_protocol.md`。

## 5. 固定训练评估流程（30天）

每次都按以下固定流程执行：

1. 下载最新数据
2. 用“最新闭合4H时点往回30天”做训练
3. 用最近1天数据做测试并输出评估结果
4. 输出带时间戳的参数文件到 `live_service/params`

一键命令：

```powershell
python .\v2.4_crosssection_coin_selection_strategy\run_live_train_and_eval_30d.py
```

兼容旧命令（等价入口）：

```powershell
python .\v2.4_crosssection_coin_selection_strategy\run_live_train_30d.py
```

## 6. 实盘信号生成规则

- `live_service` 在每根4H闭合后只做数据同步与信号筛选，不做在线训练
- 筛选参数来源：`params_dir` 下最新时间戳参数文件（`params_YYYYMMDD_HHMM.json`）
- 训练建议独立运行（例如每2天一次），实时服务自动读取最新参数并生效
- 已启用参数读取缓存与轻量窗口筛选（`signal_history_bars`），默认只用必要历史窗口计算最新bar信号

