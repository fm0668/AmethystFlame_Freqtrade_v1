# VPS(Ubuntu 22.04 x64) 部署与运维手册

## 0. 目标与范围

- 本手册适用于：**本地训练参数**，VPS 只负责运行：
  - `live_service`（产出交易信号）
  - `Freqtrade`（读取信号并下单）
- 代码来源：GitHub 仓库 `fm0668/AmethystFlame_Freqtrade_v1`。
- 系统：Ubuntu 22.04 x64。

## 0.1 一键初始化（root 快捷方式）

本仓库根目录已提供脚本：`vps_quickstart_root.sh`。  
在 VPS 执行：

```bash
cd /root
wget -O vps_quickstart_root.sh https://raw.githubusercontent.com/fm0668/AmethystFlame_Freqtrade_v1/main/vps_quickstart_root.sh
chmod +x vps_quickstart_root.sh
sudo bash vps_quickstart_root.sh
```

执行完成后可直接查看：

```bash
sudo systemctl status live_service --no-pager
sudo systemctl status freqtrade_cs --no-pager
```

---

## 1. VPS 一次性初始化

### 1.1 安装基础依赖

```bash
sudo apt update
sudo apt install -y git curl wget unzip jq tmux htop ca-certificates gnupg lsb-release
sudo apt install -y software-properties-common
```

### 1.2 安装 Python 3.11（Freqtrade 需要 >=3.11）

```bash
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update
sudo apt install -y python3.11 python3.11-venv python3.11-dev
```

### 1.3 安装编译与常见依赖（含 TA-Lib 常见依赖链）

```bash
sudo apt install -y build-essential pkg-config libffi-dev libssl-dev
sudo apt install -y libatlas-base-dev liblapack-dev gfortran
```

---

## 2. 拉取项目代码

```bash
cd /root
git clone https://github.com/fm0668/AmethystFlame_Freqtrade_v1.git
cd /root/AmethystFlame_Freqtrade_v1
git checkout main
git pull --ff-only
```

---

## 3. 创建 Python 虚拟环境

> 建议 `live_service` 与 `freqtrade` 分开虚拟环境，便于隔离升级风险。

### 3.1 live_service 环境

```bash
cd /root/AmethystFlame_Freqtrade_v1
python3.11 -m venv .venv_live
source .venv_live/bin/activate
pip install -U pip setuptools wheel
pip install -r live_service/requirements_live_service.txt
deactivate
```

### 3.2 Freqtrade 环境

```bash
cd /root/AmethystFlame_Freqtrade_v1/freqtrade
python3.11 -m venv .venv_ft
source .venv_ft/bin/activate
pip install -U pip setuptools wheel
pip install -r requirements.txt
deactivate
```

---

## 4. 目录与配置检查

### 4.1 live_service 配置文件

路径：

- `/root/AmethystFlame_Freqtrade_v1/live_service/config.live.yaml`

关键点：

- `symbols_file` 指向 `../V2.4_CrossSection_Coin_Selection_Strategy/symbols_list.txt`
- `signals_dir` 指向 `../freqtrade/user_data/signals`
- `params_dir` 指向 `./params`
- `timeframe: 4h`
- 不需要强制写 `active_params_file`，程序会优先读取 `params_*.json` 最新文件。

### 4.2 Freqtrade 配置文件

路径：

- `/root/AmethystFlame_Freqtrade_v1/freqtrade/user_data/config_cs_backtest.json`

关键点：

- `dry_run: false` 表示实盘
- `trading_mode: futures`
- `margin_mode: isolated`
- `cs_signal_manifest_file` 与 `cs_params_manifest_file` 保持当前信号目录结构一致

---

## 5. 首次手动启动（建议先人工验证）

## 5.1 启动 live_service

```bash
cd /root/AmethystFlame_Freqtrade_v1
source .venv_live/bin/activate
python -m live_service.app --config ./live_service/config.live.yaml
```

看到类似日志即正常：

- `[live_service] sync ok=... failed=...`
- `[live_service] emitted run_id=... selected=...`

按 `Ctrl+C` 停止。

## 5.2 启动 Freqtrade

```bash
cd /root/AmethystFlame_Freqtrade_v1/freqtrade
source .venv_ft/bin/activate
export PYTHONPATH=/root/AmethystFlame_Freqtrade_v1/freqtrade
python ./freqtrade/main.py trade \
  --config ./user_data/config_cs_backtest.json \
  --strategy CrossSectionSignalStrategy \
  --strategy-path ./user_data/strategies
```

看到类似日志即启动成功：

- `Using Exchange "Binance"`
- `Worker ...` 持续运行，无 `Could not load markets`

按 `Ctrl+C` 停止。

---

## 6. 配置 systemd 后台运行（推荐）

## 6.1 live_service systemd

创建文件：

```bash
sudo tee /etc/systemd/system/live_service.service >/dev/null <<'EOF'
[Unit]
Description=Live Signal Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/AmethystFlame_Freqtrade_v1
ExecStart=/root/AmethystFlame_Freqtrade_v1/.venv_live/bin/python -m live_service.app --config /root/AmethystFlame_Freqtrade_v1/live_service/config.live.yaml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now live_service
sudo systemctl status live_service --no-pager
```

## 6.2 Freqtrade systemd

创建文件：

```bash
sudo tee /etc/systemd/system/freqtrade_cs.service >/dev/null <<'EOF'
[Unit]
Description=Freqtrade CS Live
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/AmethystFlame_Freqtrade_v1/freqtrade
Environment=PYTHONPATH=/root/AmethystFlame_Freqtrade_v1/freqtrade
ExecStart=/root/AmethystFlame_Freqtrade_v1/freqtrade/.venv_ft/bin/python /root/AmethystFlame_Freqtrade_v1/freqtrade/freqtrade/main.py trade --config /root/AmethystFlame_Freqtrade_v1/freqtrade/user_data/config_cs_backtest.json --strategy CrossSectionSignalStrategy --strategy-path /root/AmethystFlame_Freqtrade_v1/freqtrade/user_data/strategies
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
```

启用并启动：

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now freqtrade_cs
sudo systemctl status freqtrade_cs --no-pager
```

---

## 7. 日常运维命令

## 7.1 服务状态

```bash
sudo systemctl status live_service --no-pager
sudo systemctl status freqtrade_cs --no-pager
```

## 7.2 启停重启

```bash
sudo systemctl restart live_service
sudo systemctl restart freqtrade_cs

sudo systemctl stop live_service
sudo systemctl stop freqtrade_cs

sudo systemctl start live_service
sudo systemctl start freqtrade_cs
```

## 7.3 实时日志

```bash
sudo journalctl -u live_service -f
sudo journalctl -u freqtrade_cs -f
```

最近 200 行：

```bash
sudo journalctl -u live_service -n 200 --no-pager
sudo journalctl -u freqtrade_cs -n 200 --no-pager
```

---

## 8. 参数文件更新流程（本地训练 -> VPS生效）

## 8.1 本地训练生成参数

本地执行你已使用的训练脚本后，得到新文件：

- `params_YYYYMMDD_HHMM.json`

## 8.2 上传到 VPS

示例（在本地执行）：

```bash
scp D:\AmethystFlame_Freqtrade_v1\live_service\params\params_20260318_1200.json root@<VPS_IP>:/root/AmethystFlame_Freqtrade_v1/live_service/params/
```

## 8.3 重启 live_service 使参数立即刷新

```bash
ssh root@<VPS_IP> "sudo systemctl restart live_service && sudo systemctl status live_service --no-pager"
```

## 8.4 验证是否加载到新参数

查看 live_service 日志中 `params_version` / `active_params_file`（manifest 与日志）是否切到新文件。

同时可检查信号目录：

```bash
ls -lt /root/AmethystFlame_Freqtrade_v1/freqtrade/user_data/signals | head
cat /root/AmethystFlame_Freqtrade_v1/freqtrade/user_data/signals/params_manifest.json
```

---

## 9. 代码更新流程（VPS）

```bash
cd /root/AmethystFlame_Freqtrade_v1
git fetch origin
git checkout main
git pull --ff-only

source .venv_live/bin/activate
pip install -U -r live_service/requirements_live_service.txt
deactivate

cd /root/AmethystFlame_Freqtrade_v1/freqtrade
source .venv_ft/bin/activate
pip install -U -r requirements.txt
deactivate

sudo systemctl restart live_service
sudo systemctl restart freqtrade_cs
```

---

## 10. 常见故障与处理

## 10.1 Freqtrade 报 `Could not load markets`

常见根因：

- VPS 到 `api.binance.com` 网络链路不稳
- DNS 超时或区域限制

快速检查：

```bash
python3 - <<'PY'
import requests
for u in [
    "https://api.binance.com/api/v3/time",
    "https://fapi.binance.com/fapi/v1/time",
    "https://fapi.binance.com/fapi/v1/exchangeInfo",
]:
    try:
        r = requests.get(u, timeout=10)
        print(u, r.status_code, r.text[:120].replace("\n", " "))
    except Exception as e:
        print(u, "ERR", e)
PY
```

## 10.2 live_service 没有发新信号

排查：

- `live_service` 服务是否在运行
- `signals/manifest.json` 时间戳是否更新
- `params` 是否可读且 `models` 字段有效

---

## 11. 建议的标准操作顺序

- 先启动 `live_service`
- 确认有 `sync/emitted` 日志
- 再启动 `freqtrade_cs`
- 观察 5-10 分钟日志，确认无交易所连接错误后再离开

---

## 12. 关键路径速查

- 项目根目录：`/root/AmethystFlame_Freqtrade_v1`
- live 配置：`/root/AmethystFlame_Freqtrade_v1/live_service/config.live.yaml`
- 参数目录：`/root/AmethystFlame_Freqtrade_v1/live_service/params`
- Freqtrade 配置：`/root/AmethystFlame_Freqtrade_v1/freqtrade/user_data/config_cs_backtest.json`
- 策略文件：`/root/AmethystFlame_Freqtrade_v1/freqtrade/user_data/strategies/CrossSectionSignalStrategy.py`
- 信号目录：`/root/AmethystFlame_Freqtrade_v1/freqtrade/user_data/signals`
