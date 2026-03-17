#!/usr/bin/env bash
set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

apt update
apt install -y git curl wget unzip jq tmux htop ca-certificates gnupg lsb-release software-properties-common
add-apt-repository ppa:deadsnakes/ppa -y
apt update
apt install -y python3.11 python3.11-venv python3.11-dev
apt install -y build-essential pkg-config libffi-dev libssl-dev libatlas-base-dev liblapack-dev gfortran

cd /root
if [ ! -d /root/AmethystFlame_Freqtrade_v1/.git ]; then
  git clone https://github.com/fm0668/AmethystFlame_Freqtrade_v1.git
fi
cd /root/AmethystFlame_Freqtrade_v1
git checkout main
git pull --ff-only

mkdir -p /root/AmethystFlame_Freqtrade_v1/freqtrade/user_data/strategies
mkdir -p /root/AmethystFlame_Freqtrade_v1/freqtrade/user_data/signals
if [ -f "/root/AmethystFlame_Freqtrade_v1/freqtrade策略配置/CrossSectionSignalStrategy.py" ]; then
  cp -f "/root/AmethystFlame_Freqtrade_v1/freqtrade策略配置/CrossSectionSignalStrategy.py" "/root/AmethystFlame_Freqtrade_v1/freqtrade/user_data/strategies/CrossSectionSignalStrategy.py"
fi
if [ -f "/root/AmethystFlame_Freqtrade_v1/freqtrade策略配置/config_cs_backtest.json" ]; then
  cp -f "/root/AmethystFlame_Freqtrade_v1/freqtrade策略配置/config_cs_backtest.json" "/root/AmethystFlame_Freqtrade_v1/freqtrade/user_data/config_cs_backtest.json"
fi
if [ ! -f "/root/AmethystFlame_Freqtrade_v1/freqtrade/user_data/signals/runtime_pairs.json" ]; then
  cat >/root/AmethystFlame_Freqtrade_v1/freqtrade/user_data/signals/runtime_pairs.json <<'EOF'
{
  "exchange": {
    "pair_whitelist": ["BTC/USDT:USDT"],
    "pair_blacklist": []
  }
}
EOF
fi

python3.11 -m venv /root/AmethystFlame_Freqtrade_v1/.venv_live
source /root/AmethystFlame_Freqtrade_v1/.venv_live/bin/activate
pip install -U pip setuptools wheel
pip install -r /root/AmethystFlame_Freqtrade_v1/live_service/requirements_live_service.txt
deactivate

python3.11 -m venv /root/AmethystFlame_Freqtrade_v1/freqtrade/.venv_ft
source /root/AmethystFlame_Freqtrade_v1/freqtrade/.venv_ft/bin/activate
pip install -U pip setuptools wheel
pip install -r /root/AmethystFlame_Freqtrade_v1/freqtrade/requirements.txt
deactivate

cat >/etc/systemd/system/live_service.service <<'EOF'
[Unit]
Description=Live Signal Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/AmethystFlame_Freqtrade_v1
ExecStart=/root/AmethystFlame_Freqtrade_v1/.venv_live/bin/python -u -m live_service.app --config /root/AmethystFlame_Freqtrade_v1/live_service/config.live.yaml
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/freqtrade_cs.service <<'EOF'
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

systemctl daemon-reload
systemctl enable live_service
systemctl enable freqtrade_cs
systemctl restart live_service
systemctl restart freqtrade_cs
systemctl --no-pager --full status live_service || true
systemctl --no-pager --full status freqtrade_cs || true
