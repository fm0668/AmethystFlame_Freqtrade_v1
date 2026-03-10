#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="${1:-/opt/AmethystFlame_Freqtrade_v1/v2.4_crosssection_coin_selection_strategy}"
PYTHON_EXE="${2:-/opt/AmethystFlame_Freqtrade_v1/.venv/bin/python}"
CONFIG_PATH="${3:-$PROJECT_DIR/pipeline_config.template.json}"
STATE_PATH="${4:-$PROJECT_DIR/.runtime/pipeline_state.json}"

CRON_LINE="0 22 * * * cd $PROJECT_DIR && $PYTHON_EXE $PROJECT_DIR/pipeline_runner.py --config $CONFIG_PATH --state $STATE_PATH >> $PROJECT_DIR/.runtime/pipeline_cron.log 2>&1"
(crontab -l 2>/dev/null; echo "$CRON_LINE") | awk '!seen[$0]++' | crontab -
echo "Registered cron at 22:00 local time"
