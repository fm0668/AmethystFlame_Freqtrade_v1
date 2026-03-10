from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
import sys

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TRAINING_ROOT = PROJECT_ROOT / "v2.4_crosssection_coin_selection_strategy"
if str(TRAINING_ROOT) not in sys.path:
    sys.path.insert(0, str(TRAINING_ROOT))

from run_v2_4_long_focus import MIN_HOLDINGS
from run_v2_4_long_focus import SHORT_TOP_K
from run_v2_4_long_focus import TOP_K
from run_v2_4_long_focus import add_features as long_focus_add_features
from run_v2_4_long_focus import apply_scores
from run_v2_walkforward_4h import classify_regime

from .storage import LiveStore


def symbol_to_pair(symbol: str) -> str:
    if not symbol.endswith("USDT"):
        raise ValueError(f"unsupported symbol {symbol}")
    return f"{symbol[:-4]}/USDT:USDT"


def _latest_frame(store: LiveStore, symbols: list[str], bars: int) -> pd.DataFrame:
    marks = ",".join(["?"] * len(symbols))
    q = f"""
    with latest as (
        select symbol, max(open_time) as mx_open_time
        from bars_4h_full
        where symbol in ({marks})
        group by symbol
    ),
    hist as (
        select b.*
        from bars_4h_full b
        join latest l on b.symbol = l.symbol
        where b.open_time <= l.mx_open_time
    )
    select *
    from hist
    qualify row_number() over(partition by symbol order by open_time desc) <= ?
    """
    df = store.conn.execute(q, [*symbols, bars]).fetch_df()
    if df.empty:
        return df
    df = df.sort_values(["symbol", "open_time"])
    df["ts"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    return df


def _latest_aux(store: LiveStore, table: str, symbols: list[str]) -> pd.DataFrame:
    marks = ",".join(["?"] * len(symbols))
    q = f"""
    select *
    from {table}
    where symbol in ({marks})
    """
    return store.conn.execute(q, symbols).fetch_df()


def add_features(panel: pd.DataFrame) -> pd.DataFrame:
    return long_focus_add_features(panel)


def _merge_latest_aux_on_ts(base: pd.DataFrame, aux: pd.DataFrame, ts_col: str, rename: dict) -> pd.DataFrame:
    if aux.empty:
        out = base.copy()
        for k in rename.values():
            out[k] = np.nan
        return out
    out_parts = []
    for symbol, g in base.groupby("symbol"):
        a = aux[aux["symbol"] == symbol].copy()
        if a.empty:
            t = g.copy()
            for k in rename.values():
                t[k] = np.nan
            out_parts.append(t)
            continue
        a["ts_aux"] = pd.to_datetime(a[ts_col], unit="ms", utc=True)
        a = a.drop(columns=["symbol", ts_col], errors="ignore")
        a = a.sort_values("ts_aux")
        h = g.drop(columns=["ts_aux"], errors="ignore").sort_values("ts").copy()
        m = pd.merge_asof(h, a, left_on="ts", right_on="ts_aux", direction="backward")
        for src, dst in rename.items():
            m[dst] = m[src] if src in m.columns else np.nan
        out_parts.append(m)
    return pd.concat(out_parts, ignore_index=True)


def build_panel(store: LiveStore, symbols: list[str], bars: int) -> pd.DataFrame:
    panel = _latest_frame(store, symbols, bars)
    if panel.empty:
        return panel
    panel["ret_4h"] = panel.groupby("symbol")["close"].pct_change()
    panel["ret_24h"] = panel["close"] / panel.groupby("symbol")["close"].shift(6) - 1
    panel["ret_fwd_4h"] = panel.groupby("symbol")["close"].shift(-1) / panel["close"] - 1
    panel["next_high"] = panel.groupby("symbol")["high"].shift(-1)
    panel["next_low"] = panel.groupby("symbol")["low"].shift(-1)
    panel["vol_4h_surge"] = panel["quote_volume"] / (
        panel.groupby("symbol")["quote_volume"].rolling(42, min_periods=20).mean().reset_index(level=0, drop=True)
    )
    panel["date"] = panel["ts"].dt.floor("1d")
    day = panel.groupby(["symbol", "date"], as_index=False)["quote_volume"].sum().rename(columns={"quote_volume": "day_quote_volume"})
    day["vol_1d_surge"] = day.groupby("symbol")["day_quote_volume"].transform(
        lambda s: s / s.shift(1).rolling(7, min_periods=5).mean()
    )
    panel = panel.merge(day[["symbol", "date", "vol_1d_surge"]], on=["symbol", "date"], how="left")
    panel["taker_buy_ratio"] = panel["taker_buy_quote_volume"] / panel["quote_volume"].replace(0, np.nan)
    panel["net_taker_norm"] = (2 * panel["taker_buy_quote_volume"] - panel["quote_volume"]) / panel["quote_volume"].replace(0, np.nan)
    up = (panel["ret_4h"] > 0).astype(int)
    panel["up_streak_4h"] = up.groupby(panel["symbol"]).transform(
        lambda s: s.groupby((s != s.shift()).cumsum()).cumsum().where(s == 1, 0)
    )
    oi = _latest_aux(store, "oi_4h", symbols)
    panel = _merge_latest_aux_on_ts(
        panel,
        oi,
        "ts",
        {"sum_open_interest": "sum_open_interest", "sum_open_interest_value": "sum_open_interest_value"},
    )
    panel["d_oi"] = panel.groupby("symbol")["sum_open_interest_value"].pct_change()
    g_lsr = _latest_aux(store, "global_lsr_4h", symbols)
    panel = _merge_latest_aux_on_ts(panel, g_lsr, "ts", {"long_short_ratio": "global_ls_ratio"})
    t_lsr = _latest_aux(store, "top_lsr_4h", symbols)
    panel = _merge_latest_aux_on_ts(panel, t_lsr, "ts", {"long_short_ratio": "top_ls_ratio"})
    funding = _latest_aux(store, "funding_8h", symbols)
    panel = _merge_latest_aux_on_ts(panel, funding, "funding_time", {"funding_rate": "funding_rate"})
    return panel.sort_values(["ts", "symbol"]).reset_index(drop=True)


def _pass_threshold(series: pd.Series, threshold) -> pd.Series:
    if threshold is None or (isinstance(threshold, float) and np.isnan(threshold)):
        return pd.Series(True, index=series.index)
    return series >= threshold


def select_current_signals(panel: pd.DataFrame, latest_ts: pd.Timestamp, models: dict) -> pd.DataFrame:
    regime_map = classify_regime(panel)
    panel = panel.merge(regime_map, on="ts", how="left")
    cur = panel[panel["ts"] == latest_ts].copy()
    if cur.empty:
        return pd.DataFrame()
    regime = cur["regime"].iloc[0] if pd.notna(cur["regime"].iloc[0]) else "weak"
    model = models.get(regime) or models.get("weak") or models.get("strong")
    if model is None:
        return pd.DataFrame()
    cur = apply_scores(cur, model["long_weights"], model["short_weights"])
    p = model["params"]

    long_pool = cur[
        _pass_threshold(cur["vol_4h_surge"], p.get("long_vol_4h_min"))
        & _pass_threshold(cur["breakout_20"].fillna(-999), p.get("long_breakout_min"))
        & _pass_threshold(cur["trend_hit_6"].fillna(-999), p.get("long_trend_min"))
        & _pass_threshold(cur["rebound_20"].fillna(-999), p.get("long_rebound_min"))
        & _pass_threshold(cur["score_long"], p.get("long_score_conf"))
    ]
    long_pick = long_pool.nlargest(TOP_K, "score_long")
    if len(long_pick) < MIN_HOLDINGS:
        need = MIN_HOLDINGS - len(long_pick)
        long_pick = pd.concat(
            [long_pick, cur[~cur["symbol"].isin(long_pick["symbol"])].nlargest(need, "score_long")]
        ).drop_duplicates("symbol")

    short_pre = cur.nlargest(SHORT_TOP_K, "ret_4h")
    short_pre = short_pre[_pass_threshold(short_pre["up_streak_4h"], p.get("short_up_streak_min"))]
    short_pool = short_pre[
        _pass_threshold(short_pre["funding_rate"].fillna(-999), p.get("short_funding_min"))
        & _pass_threshold(short_pre["global_ls_ratio"].fillna(-999), p.get("short_global_min"))
        & _pass_threshold(short_pre["top_ls_ratio"].fillna(-999), p.get("short_top_min"))
        & _pass_threshold(short_pre["score_short"], p.get("short_score_conf"))
    ]
    short_pick = short_pool.nlargest(TOP_K, "score_short")
    if len(short_pick) < MIN_HOLDINGS:
        need = MIN_HOLDINGS - len(short_pick)
        short_pick = pd.concat(
            [short_pick, short_pre[~short_pre["symbol"].isin(short_pick["symbol"])].nlargest(need, "score_short")]
        ).drop_duplicates("symbol")
    if short_pick.empty:
        short_pick = cur.nlargest(1, "score_short")

    out = []
    for _, r in long_pick.iterrows():
        out.append({"symbol": r["symbol"], "side": "long", "score": float(r["score_long"]), "open_time": int(r["open_time"])})
    for _, r in short_pick.iterrows():
        out.append({"symbol": r["symbol"], "side": "short", "score": float(r["score_short"]), "open_time": int(r["open_time"])})
    return pd.DataFrame(out).sort_values("score", ascending=False).reset_index(drop=True)


def build_signal_payload(
    selected: pd.DataFrame,
    top_n: int,
    long_threshold: float,
    short_threshold: float,
) -> tuple[dict, list[str], list[dict]]:
    if selected.empty:
        return {"signals": {}}, [], []
    rows = selected.copy()
    if long_threshold > 0 or short_threshold > 0:
        rows = rows[
            ((rows["side"] == "long") & (rows["score"] >= long_threshold))
            | ((rows["side"] == "short") & (rows["score"] >= short_threshold))
        ].copy()
        if rows.empty:
            return {"signals": {}}, [], []
    if top_n > 0:
        rows = rows.sort_values("score", ascending=False).head(top_n * 2)
    side_n = rows.groupby("symbol")["side"].nunique()
    conflict_symbols = set(side_n[side_n > 1].index.tolist())
    if conflict_symbols:
        rows = rows[~rows["symbol"].isin(conflict_symbols)].copy()
        if rows.empty:
            return {"signals": {}}, [], []
    signals: dict[str, dict[str, list[str]]] = {}
    details: list[dict] = []
    for _, row in rows.iterrows():
        pair = symbol_to_pair(str(row["symbol"]))
        signal_open_time = int(row["open_time"])
        ts = datetime.fromtimestamp(signal_open_time / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        if pair not in signals:
            signals[pair] = {"long": [], "short": []}
        signals[pair][str(row["side"])].append(ts)
        details.append(
            {
                "symbol": str(row["symbol"]),
                "pair": pair,
                "side": str(row["side"]),
                "score": float(row["score"]),
                "open_time": int(row["open_time"]),
            }
        )
    return {"signals": signals}, sorted(signals.keys()), details

