from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy


class CrossSectionSignalStrategy(IStrategy):
    timeframe = "4h"
    can_short = True
    startup_candle_count = 1
    process_only_new_candles = False
    minimal_roi = {"0": 10.0}
    stoploss = -0.99
    use_custom_stoploss = False
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False
    position_adjustment_enable = False

    long_stoploss = -0.33
    long_takeprofit = None
    short_stoploss = -0.25
    short_trail_activate = 0.06
    short_trail_gap = 0.05
    force_exit_bars = 1
    time_exit_buffer_seconds = 60
    leverage_value = 3.0
    order_types = {
        "entry": "market",
        "exit": "market",
        "stoploss": "market",
        "stoploss_on_exchange": False,
        "stoploss_on_exchange_interval": 60,
    }

    _signals_loaded = False
    _long_map: dict[str, set[pd.Timestamp]] = {}
    _short_map: dict[str, set[pd.Timestamp]] = {}
    _short_peak_profit: dict[int, float] = {}
    _pair_blacklist: set[str] = set()
    _last_signal_file: Path | None = None
    _last_params_file: Path | None = None
    _last_signal_mtime: float | None = None
    _last_params_mtime: float | None = None
    _last_runtime_pairs_mtime: float | None = None
    _active_signal_version: str = ""
    _active_params_version: str = ""
    _active_signal_bar_open: pd.Timestamp | None = None
    _consumed_signal_keys: set[str] = set()

    def _resolve_path(self, raw: str | None, fallback: str) -> Path:
        val = raw if raw else fallback
        p = Path(val)
        if p.is_absolute():
            return p
        return Path(self.config["user_data_dir"]) / p

    def _latest_timestamped_json(self, directory: Path, prefix: str) -> Path | None:
        if not directory.exists():
            return None
        files = list(directory.glob(f"{prefix}*.json"))
        if not files:
            return None
        pat = re.compile(rf"^{re.escape(prefix)}(\d{{8}}_\d{{6}}|\d{{8}}_\d{{4}})\.json$")

        def key(p: Path):
            m = pat.match(p.name)
            return (m.group(1) if m else "", p.stat().st_mtime)

        files.sort(key=key)
        return files[-1]

    def _load_signal_map(self, signal_path: Path) -> pd.Timestamp | None:
        if not signal_path.exists():
            self._long_map = {}
            self._short_map = {}
            self._signals_loaded = True
            self._last_signal_file = signal_path
            self._last_signal_mtime = None
            return None
        with open(signal_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        signals = payload.get("signals", {})
        long_map: dict[str, set[pd.Timestamp]] = {}
        short_map: dict[str, set[pd.Timestamp]] = {}
        all_ts: list[pd.Timestamp] = []
        for pair, data in signals.items():
            long_ts = pd.to_datetime(data.get("long", []), utc=True).floor("4h")
            short_ts = pd.to_datetime(data.get("short", []), utc=True).floor("4h")
            long_map[pair] = set(long_ts.to_list())
            short_map[pair] = set(short_ts.to_list())
            all_ts.extend(long_ts.to_list())
            all_ts.extend(short_ts.to_list())
        self._long_map = long_map
        self._short_map = short_map
        self._signals_loaded = True
        self._last_signal_file = signal_path
        self._last_signal_mtime = signal_path.stat().st_mtime
        if not all_ts:
            return None
        return max(all_ts)

    def _apply_params(self, params: dict) -> None:
        self.long_stoploss = -0.33
        self.long_takeprofit = None
        self.short_stoploss = -0.25
        self.short_trail_activate = 0.06
        self.short_trail_gap = 0.05
        if "force_exit_bars" in params:
            self.force_exit_bars = int(params["force_exit_bars"])
        if "time_exit_buffer_seconds" in params:
            self.time_exit_buffer_seconds = int(params["time_exit_buffer_seconds"])
        if "pair_blacklist" in params:
            self._pair_blacklist = set(params["pair_blacklist"])
        else:
            self._pair_blacklist = set()

    def _resolve_active_signal_file(self) -> tuple[Path, str]:
        signal_dir = self._resolve_path(self.config.get("cs_signal_dir"), "signals")
        latest = self._latest_timestamped_json(signal_dir, "cs_")
        if latest:
            return latest, latest.name
        direct_signal = self._resolve_path(self.config.get("cs_signal_file"), "signals/cs_20260303_0304.json")
        return direct_signal, direct_signal.name

    def _resolve_active_params_file(self) -> tuple[Path | None, str]:
        params_dir = self._resolve_path(self.config.get("cs_params_dir"), "../../live_service/params")
        latest = self._latest_timestamped_json(params_dir, "params_")
        if latest:
            return latest, latest.name
        direct = self.config.get("cs_params_file")
        if direct:
            p = self._resolve_path(direct, "signals/params_v1.json")
            return p, p.name
        return None, ""

    def _sync_runtime_pairs(self) -> None:
        runtime_pairs_path = self._resolve_path("signals/runtime_pairs.json", "signals/runtime_pairs.json")
        if not runtime_pairs_path.exists():
            self._last_runtime_pairs_mtime = None
            return
        mtime = runtime_pairs_path.stat().st_mtime
        if self._last_runtime_pairs_mtime == mtime:
            return
        with open(runtime_pairs_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        exchange_cfg = payload.get("exchange", {})
        whitelist = exchange_cfg.get("pair_whitelist", [])
        blacklist = exchange_cfg.get("pair_blacklist", [])
        self.config.setdefault("exchange", {})
        self.config["exchange"]["pair_whitelist"] = whitelist
        self.config["exchange"]["pair_blacklist"] = blacklist
        self._last_runtime_pairs_mtime = mtime

    def _ensure_signals_and_params(self) -> None:
        self._sync_runtime_pairs()
        signal_path, signal_version = self._resolve_active_signal_file()
        should_reload_signal = False
        if not self._signals_loaded:
            should_reload_signal = True
        elif self._last_signal_file != signal_path:
            should_reload_signal = True
        elif signal_path.exists() and self._last_signal_mtime != signal_path.stat().st_mtime:
            should_reload_signal = True
        if should_reload_signal:
            self._active_signal_bar_open = self._load_signal_map(signal_path)
            self._active_signal_version = signal_version

        params_path, params_version = self._resolve_active_params_file()
        if params_path and params_path.exists():
            should_reload_params = False
            if self._last_params_file != params_path:
                should_reload_params = True
            elif self._last_params_mtime != params_path.stat().st_mtime:
                should_reload_params = True
            if should_reload_params:
                with open(params_path, "r", encoding="utf-8") as f:
                    payload = json.load(f)
                self._apply_params(payload)
                self._last_params_file = params_path
                self._last_params_mtime = params_path.stat().st_mtime
                self._active_params_version = str(payload.get("version", params_version))

    def populate_indicators(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        self._ensure_signals_and_params()
        return dataframe

    def populate_entry_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        self._ensure_signals_and_params()
        pair = metadata["pair"]
        if pair in self._pair_blacklist:
            dataframe["enter_long"] = 0
            dataframe["enter_short"] = 0
            dataframe["enter_tag"] = ""
            return dataframe
        long_ts = self._long_map.get(pair, set())
        short_ts = self._short_map.get(pair, set())
        ts = pd.to_datetime(dataframe["date"], utc=True).dt.floor("4h")
        long_sig = ts.isin(long_ts)
        short_sig = ts.isin(short_ts)
        conflict = long_sig & short_sig
        dataframe["enter_long"] = (long_sig & ~conflict).astype(int)
        dataframe["enter_short"] = (short_sig & ~conflict).astype(int)
        dataframe["enter_tag"] = ""
        return dataframe

    def populate_exit_trend(self, dataframe: pd.DataFrame, metadata: dict) -> pd.DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe

    def confirm_trade_entry(
        self,
        pair: str,
        order_type: str,
        amount: float,
        rate: float,
        time_in_force: str,
        current_time,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> bool:
        self._ensure_signals_and_params()
        signal_bar = self._active_signal_bar_open
        if signal_bar is None:
            signal_bar = pd.to_datetime(current_time, utc=True).floor("4h")
        key = f"{pair}|{signal_bar.isoformat()}"
        if key in self._consumed_signal_keys:
            return False
        long_hit = signal_bar in self._long_map.get(pair, set())
        short_hit = signal_bar in self._short_map.get(pair, set())
        if long_hit and short_hit:
            return False
        if side == "long":
            if not long_hit:
                return False
        elif side == "short":
            if not short_hit:
                return False
        else:
            return False
        return True

    def order_filled(self, pair: str, trade: Trade, order, current_time, **kwargs) -> None:
        if order.ft_order_side != trade.entry_side:
            return
        bar_open = pd.to_datetime(trade.open_date_utc, utc=True).floor("4h")
        key = f"{pair}|{bar_open.isoformat()}"
        self._consumed_signal_keys.add(key)

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ):
        trade_bar_open = pd.to_datetime(trade.open_date_utc, utc=True).floor("4h")
        if trade.is_short:
            peak = self._short_peak_profit.get(trade.id, current_profit)
            if current_profit > peak:
                peak = current_profit
            self._short_peak_profit[trade.id] = peak
            if current_profit <= self.short_stoploss:
                self._short_peak_profit.pop(trade.id, None)
                return "short_sl"
            if (
                self.short_trail_activate is not None
                and self.short_trail_gap > 0
                and peak >= self.short_trail_activate
                and current_profit <= peak - self.short_trail_gap
            ):
                self._short_peak_profit.pop(trade.id, None)
                return "short_trail"
        else:
            if current_profit <= self.long_stoploss:
                return "long_sl"
            if self.long_takeprofit is not None and current_profit >= self.long_takeprofit:
                return "long_tp"
        time_exit_at = trade_bar_open + pd.Timedelta(hours=4 * self.force_exit_bars)
        buffered_exit_at = time_exit_at - pd.Timedelta(seconds=self.time_exit_buffer_seconds)
        now_ts = pd.to_datetime(current_time, utc=True)
        if now_ts >= buffered_exit_at:
            self._short_peak_profit.pop(trade.id, None)
            return "time_exit_4h_close_buffered"
        return None

    def leverage(
        self,
        pair: str,
        current_time,
        current_rate: float,
        proposed_leverage: float,
        max_leverage: float,
        entry_tag: str | None,
        side: str,
        **kwargs,
    ) -> float:
        return min(self.leverage_value, max_leverage)
