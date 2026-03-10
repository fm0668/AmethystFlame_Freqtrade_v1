import os
import glob
import zipfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = os.getenv("DATA_DIR", str(PROJECT_ROOT / "data" / "binance" / "um"))
SYMBOLS_FILE = BASE_DIR / "symbols_list.txt"
TRAIN_END = pd.Timestamp("2026-02-28 20:00:00", tz="UTC")
TEST_START = pd.Timestamp("2026-03-01 00:00:00", tz="UTC")
TEST_END = pd.Timestamp("2026-03-05 20:00:00", tz="UTC")
TRAIN_LOOKBACK_BARS = 84
TOP_K = 10
TRUTH_K = 30
SHORT_TOP_K = 60
MIN_HOLDINGS = 5
EXCLUDED_INDEX = {"BTCDOMUSDT", "DEFIUSDT", "FOOTBALLUSDT", "BLUEBIRDUSDT"}


def read_symbols():
    try:
        try:
            with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
                symbols = [x.strip() for x in f if x.strip()]
        except UnicodeDecodeError:
            with open(SYMBOLS_FILE, "r", encoding="gbk") as f:
                symbols = [x.strip() for x in f if x.strip()]
    except Exception:
        symbols = []
    return [s for s in symbols if s not in EXCLUDED_INDEX]


def read_csv_from_zip(zip_path):
    with zipfile.ZipFile(zip_path, "r") as zf:
        name = zf.namelist()[0]
        df = pd.read_csv(zf.open(name), header=None)
    header_row = df.iloc[0].astype(str).str.lower().tolist()
    if "open_time" in header_row or "create_time" in header_row or "calc_time" in header_row:
        df.columns = df.iloc[0].tolist()
        df = df.iloc[1:].copy()
    return df


def load_kline_4h(symbol):
    path = os.path.join(DATA_DIR, "klines", symbol, "1m")
    if not os.path.isdir(path):
        return None
    files = []
    for p in glob.glob(os.path.join(path, "*.zip")):
        bn = os.path.basename(p)
        prefix = f"{symbol}-1m-"
        if not (bn.startswith(prefix) and bn.endswith(".zip")):
            continue
        tag = bn[len(prefix):-4]
        if len(tag) == 10:
            files.append(p)
        elif len(tag) == 7:
            files.append(p)
    if not files:
        return None
    chunks = []
    for p in files:
        df = read_csv_from_zip(p)
        cols = [
            "open_time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "close_time",
            "quote_volume",
            "count",
            "taker_buy_volume",
            "taker_buy_quote_volume",
            "ignore",
        ]
        if not set(cols).issubset(set(df.columns)):
            df = df.iloc[:, :12].copy()
            df.columns = cols
        else:
            df = df[cols].copy()
        df["open_time"] = pd.to_numeric(df["open_time"], errors="coerce")
        df = df.dropna(subset=["open_time"])
        for c in ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_quote_volume"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["dt"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
        df["bucket4h"] = df["dt"].dt.floor("4h")
        g = df.groupby("bucket4h").agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            quote_volume=("quote_volume", "sum"),
            taker_buy_quote_volume=("taker_buy_quote_volume", "sum"),
        )
        chunks.append(g)
    if not chunks:
        return None
    k = pd.concat(chunks).groupby(level=0).last().sort_index()
    k["ret_4h"] = k["close"].pct_change()
    k["ret_24h"] = k["close"] / k["close"].shift(6) - 1
    k["ret_fwd_4h"] = k["close"].shift(-1) / k["close"] - 1
    k["next_high"] = k["high"].shift(-1)
    k["next_low"] = k["low"].shift(-1)
    k["vol_4h_surge"] = k["quote_volume"] / k["quote_volume"].rolling(42, min_periods=20).mean()
    day = k["quote_volume"].resample("1D").sum()
    day_surge = day / day.shift(1).rolling(7, min_periods=5).mean()
    k["vol_1d_surge"] = day_surge.reindex(k.index.floor("1D")).values
    k["taker_buy_ratio"] = k["taker_buy_quote_volume"] / k["quote_volume"].replace(0, np.nan)
    k["net_taker_norm"] = (2 * k["taker_buy_quote_volume"] - k["quote_volume"]) / k["quote_volume"].replace(0, np.nan)
    up = (k["ret_4h"] > 0).astype(int)
    k["up_streak_4h"] = up.groupby((up != up.shift()).cumsum()).cumsum().where(up == 1, 0)
    k["symbol"] = symbol
    k = k.reset_index().rename(columns={"bucket4h": "ts"})
    k["date"] = k["ts"].dt.date
    return k


def load_metrics_daily(symbol):
    path = os.path.join(DATA_DIR, "metrics", symbol)
    if not os.path.isdir(path):
        return None
    files = sorted(glob.glob(os.path.join(path, f"{symbol}-metrics-*.zip")))
    recs = []
    for p in files:
        dstr = os.path.basename(p).split("-metrics-")[-1].replace(".zip", "")
        try:
            d = datetime.strptime(dstr, "%Y-%m-%d").date()
        except Exception:
            continue
        df = read_csv_from_zip(p)
        cols = [
            "create_time",
            "symbol",
            "sum_open_interest",
            "sum_open_interest_value",
            "count_toptrader_long_short_ratio",
            "sum_toptrader_long_short_ratio",
            "count_long_short_ratio",
            "sum_taker_long_short_vol_ratio",
        ]
        if not set(cols).issubset(set(df.columns)):
            df = df.iloc[:, :8].copy()
            df.columns = cols
        else:
            df = df[cols].copy()
        for c in cols[2:]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        recs.append(
            {
                "date": d,
                "oi_value": df["sum_open_interest_value"].iloc[-1],
                "global_ls_ratio": df["count_long_short_ratio"].iloc[-1],
                "top_ls_ratio": df["count_toptrader_long_short_ratio"].iloc[-1],
            }
        )
    if not recs:
        return None
    m = pd.DataFrame(recs).sort_values("date")
    m["d_oi"] = m["oi_value"].pct_change()
    return m


def load_funding_daily(symbol):
    recs = []
    funding_dir = os.path.join(DATA_DIR, "fundingRate", symbol)
    zip_files = sorted(glob.glob(os.path.join(funding_dir, f"{symbol}-fundingRate-*.zip")))
    for zip_path in zip_files:
        if os.path.exists(zip_path):
            df = read_csv_from_zip(zip_path)
            cols = ["calc_time", "funding_interval_hours", "last_funding_rate"]
            if not set(cols).issubset(set(df.columns)):
                df = df.iloc[:, :3].copy()
                df.columns = cols
            else:
                df = df[cols].copy()
            df["calc_time"] = pd.to_numeric(df["calc_time"], errors="coerce")
            df["last_funding_rate"] = pd.to_numeric(df["last_funding_rate"], errors="coerce")
            df["date"] = pd.to_datetime(df["calc_time"], unit="ms", utc=True).dt.date
            recs.append(df.groupby("date").agg(funding_rate=("last_funding_rate", "mean")).reset_index())
    api_path = os.path.join(DATA_DIR, "fundingRate", symbol, f"{symbol}-fundingRate-API_supplement.csv")
    if os.path.exists(api_path):
        x = pd.read_csv(api_path)
        if {"calc_time", "last_funding_rate"}.issubset(set(x.columns)):
            x["calc_time"] = pd.to_numeric(x["calc_time"], errors="coerce")
            x["last_funding_rate"] = pd.to_numeric(x["last_funding_rate"], errors="coerce")
            x["date"] = pd.to_datetime(x["calc_time"], unit="ms", utc=True).dt.date
            recs.append(x.groupby("date").agg(funding_rate=("last_funding_rate", "mean")).reset_index())
    if not recs:
        return None
    f = pd.concat(recs, ignore_index=True).groupby("date").agg(funding_rate=("funding_rate", "mean")).reset_index()
    return f


def build_panel(symbols):
    frames = []
    for i, s in enumerate(symbols, 1):
        k = load_kline_4h(s)
        if k is None or k.empty:
            continue
        m = load_metrics_daily(s)
        f = load_funding_daily(s)
        if m is not None:
            k = k.merge(m, on="date", how="left")
        else:
            k["oi_value"] = np.nan
            k["global_ls_ratio"] = np.nan
            k["top_ls_ratio"] = np.nan
            k["d_oi"] = np.nan
        if f is not None:
            k = k.merge(f, on="date", how="left")
        else:
            k["funding_rate"] = np.nan
        frames.append(k)
        if i % 50 == 0:
            print(f"已处理 {i}/{len(symbols)} 个交易对")
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.sort_values(["ts", "symbol"])
    return panel


def zscore_by_ts(df, col):
    g = df.groupby("ts")[col]
    return (df[col] - g.transform("mean")) / g.transform("std").replace(0, np.nan)


def classify_regime(panel):
    btc = panel[panel["symbol"] == "BTCUSDT"][["ts", "ret_4h", "ret_24h"]].copy()
    btc["regime"] = np.where((btc["ret_4h"] > 0) & (btc["ret_24h"] > 0), "strong", "weak")
    return btc[["ts", "regime"]]


def add_features(panel):
    btc = panel[panel["symbol"] == "BTCUSDT"][["ts", "ret_4h", "ret_24h", "taker_buy_ratio", "funding_rate"]].rename(
        columns={
            "ret_4h": "btc_ret_4h",
            "ret_24h": "btc_ret_24h",
            "taker_buy_ratio": "btc_taker_buy_ratio",
            "funding_rate": "btc_funding_rate",
        }
    )
    panel = panel.merge(btc, on="ts", how="left")
    panel["mom_rel"] = panel["ret_4h"] - panel["btc_ret_4h"]
    panel["taker_rel"] = panel["taker_buy_ratio"] - panel["btc_taker_buy_ratio"]
    panel["funding_rel"] = panel["funding_rate"] - panel["btc_funding_rate"]
    for c in [
        "mom_rel",
        "vol_1d_surge",
        "vol_4h_surge",
        "taker_rel",
        "net_taker_norm",
        "d_oi",
        "funding_rate",
        "global_ls_ratio",
        "top_ls_ratio",
        "ret_4h",
    ]:
        panel[f"z_{c}"] = zscore_by_ts(panel, c).clip(-3, 3)
    panel["funding_missing"] = panel["funding_rate"].isna().astype(int)
    panel["F1"] = panel["z_mom_rel"].fillna(0)
    panel["F2"] = 0.5 * panel["z_vol_1d_surge"].fillna(0) + 0.5 * panel["z_vol_4h_surge"].fillna(0)
    panel["F3"] = 0.6 * panel["z_taker_rel"].fillna(0) + 0.4 * panel["z_net_taker_norm"].fillna(0)
    panel["F4"] = panel["z_d_oi"].fillna(0)
    panel["F5_base"] = (-panel["z_funding_rate"].fillna(0) - panel["z_global_ls_ratio"].fillna(0) - panel["z_top_ls_ratio"].fillna(0)) / 3
    panel["F5"] = np.where(panel["funding_missing"] == 1, panel["F5_base"] * 0.5, panel["F5_base"])
    panel["score_long"] = 0.35 * panel["F1"] + 0.25 * panel["F2"] + 0.20 * panel["F3"] + 0.10 * panel["F4"] + 0.10 * panel["F5"]

    panel["G1"] = (panel["z_funding_rate"].fillna(0) + panel["z_global_ls_ratio"].fillna(0) + panel["z_top_ls_ratio"].fillna(0)) / 3
    panel["G2"] = -0.6 * panel["z_taker_rel"].fillna(0) - 0.4 * panel["z_net_taker_norm"].fillna(0)
    panel["G3"] = -panel["z_d_oi"].fillna(0)
    panel["G4"] = panel["z_mom_rel"].fillna(0)
    panel["G5"] = -panel["ret_4h"].abs().groupby(panel["ts"]).transform(
        lambda s: (s - s.mean()) / (s.std() if s.std() else 1)
    ).fillna(0).clip(-3, 3)
    panel["score_short"] = 0.35 * panel["G1"] + 0.25 * panel["G2"] + 0.20 * panel["G3"] + 0.15 * panel["G4"] + 0.05 * panel["G5"]
    return panel


def rank_truth(df_ts):
    x = df_ts.dropna(subset=["ret_fwd_4h"]).copy()
    up = x.nlargest(TRUTH_K, "ret_fwd_4h")["symbol"].tolist()
    dn = x.nsmallest(TRUTH_K, "ret_fwd_4h")["symbol"].tolist()
    return up, dn, set(up), set(dn)


def derive_regime_params(train_df):
    params = {}
    for regime in ["strong", "weak"]:
        r = train_df[train_df["regime"] == regime].copy()
        if r.empty:
            params[regime] = None
            continue
        long_s, short_s = [], []
        for ts, g in r.groupby("ts"):
            up, dn, up_set, dn_set = rank_truth(g)
            long_s.append(g[g["symbol"].isin(up_set)])
            short_s.append(g[g["symbol"].isin(dn_set)])
        long_df = pd.concat(long_s, ignore_index=True) if long_s else pd.DataFrame()
        short_df = pd.concat(short_s, ignore_index=True) if short_s else pd.DataFrame()
        p = {
            "long_vol_1d_surge_min": float(long_df["vol_1d_surge"].quantile(0.30)) if not long_df.empty else 1.0,
            "long_vol_4h_surge_min": float(long_df["vol_4h_surge"].quantile(0.30)) if not long_df.empty else 1.0,
            "long_taker_buy_ratio_min": float(long_df["taker_buy_ratio"].quantile(0.35)) if not long_df.empty else 0.5,
            "long_mom_rel_min": float(long_df["mom_rel"].quantile(0.30)) if not long_df.empty else 0.0,
            "long_d_oi_min": float(long_df["d_oi"].quantile(0.30)) if not long_df.empty else -0.05,
            "long_score_conf": float(long_df["score_long"].quantile(0.40)) if not long_df.empty else 0.0,
            "short_funding_rate_min": float(short_df["funding_rate"].quantile(0.65)) if not short_df.empty else 0.0,
            "short_global_ls_min": float(short_df["global_ls_ratio"].quantile(0.65)) if not short_df.empty else 1.0,
            "short_top_ls_min": float(short_df["top_ls_ratio"].quantile(0.65)) if not short_df.empty else 1.0,
            "short_taker_rel_max": float(short_df["taker_rel"].quantile(0.40)) if not short_df.empty else 0.0,
            "short_d_oi_max": float(short_df["d_oi"].quantile(0.45)) if not short_df.empty else 0.0,
            "short_score_conf": float(short_df["score_short"].quantile(0.60)) if not short_df.empty else 0.0,
        }
        best_n, best_score = 6, -1.0
        for n in [6, 12, 18]:
            ps = []
            for ts, g in r.groupby("ts"):
                _, _, _, dn_set = rank_truth(g)
                pre = g.nlargest(SHORT_TOP_K, "ret_4h")
                pre = pre[pre["up_streak_4h"] >= n]
                pool = pre[
                    (pre["funding_rate"].fillna(-999) >= p["short_funding_rate_min"])
                    & (pre["global_ls_ratio"].fillna(-999) >= p["short_global_ls_min"])
                    & (pre["top_ls_ratio"].fillna(-999) >= p["short_top_ls_min"])
                    & (pre["taker_rel"].fillna(999) <= p["short_taker_rel_max"])
                    & (pre["d_oi"].fillna(999) <= p["short_d_oi_max"])
                ]
                picks = pool.nlargest(TOP_K, "score_short")["symbol"].tolist()
                if len(picks) < MIN_HOLDINGS:
                    need = MIN_HOLDINGS - len(picks)
                    picks += pre[~pre["symbol"].isin(picks)].nlargest(need, "score_short")["symbol"].tolist()
                if picks:
                    ps.append(len(set(picks) & dn_set) / len(picks))
            score = float(np.mean(ps)) if ps else 0.0
            if score > best_score:
                best_score = score
                best_n = n
        p["short_up_streak_min"] = best_n
        params[regime] = p
    return params


def pick_with_confidence(pool, score_col):
    picks = pool.nlargest(TOP_K, score_col)
    if len(picks) < MIN_HOLDINGS:
        return picks
    return picks


def evaluate(panel):
    regime_map = classify_regime(panel)
    panel = panel.merge(regime_map, on="ts", how="left")
    test_ts = sorted([t for t in panel["ts"].unique() if TEST_START <= t <= TEST_END])
    rows = []
    detail = []
    pnl_rows = []
    for ts in test_ts:
        train_start_ts = ts - pd.Timedelta(hours=4 * TRAIN_LOOKBACK_BARS)
        train = panel[(panel["ts"] < ts) & (panel["ts"] >= train_start_ts)]
        if train.empty:
            continue
        params = derive_regime_params(train)
        cur = panel[panel["ts"] == ts].copy()
        if cur.empty:
            continue
        regime = cur["regime"].iloc[0] if pd.notna(cur["regime"].iloc[0]) else "weak"
        p = params.get(regime) or params.get("weak") or params.get("strong")
        if p is None:
            continue
        up_ranked, dn_ranked, up_set, dn_set = rank_truth(cur)
        up_rank_map = {s: i + 1 for i, s in enumerate(up_ranked)}
        dn_rank_map = {s: i + 1 for i, s in enumerate(dn_ranked)}

        long_pool = cur[
            (cur["vol_1d_surge"] >= p["long_vol_1d_surge_min"])
            & (cur["vol_4h_surge"] >= p["long_vol_4h_surge_min"])
            & (cur["taker_buy_ratio"] >= p["long_taker_buy_ratio_min"])
            & (cur["mom_rel"] >= p["long_mom_rel_min"])
            & (cur["d_oi"].fillna(-999) >= p["long_d_oi_min"])
            & (cur["score_long"] >= p["long_score_conf"])
        ]
        long_pick = long_pool.nlargest(TOP_K, "score_long")
        if len(long_pick) < MIN_HOLDINGS:
            need = MIN_HOLDINGS - len(long_pick)
            long_pick = pd.concat(
                [long_pick, cur[~cur["symbol"].isin(long_pick["symbol"])].nlargest(need, "score_long")]
            ).drop_duplicates("symbol")

        short_pre = cur.nlargest(SHORT_TOP_K, "ret_4h")
        short_pre = short_pre[short_pre["up_streak_4h"] >= p["short_up_streak_min"]]
        short_pool = short_pre[
            (short_pre["funding_rate"].fillna(-999) >= p["short_funding_rate_min"])
            & (short_pre["global_ls_ratio"].fillna(-999) >= p["short_global_ls_min"])
            & (short_pre["top_ls_ratio"].fillna(-999) >= p["short_top_ls_min"])
            & (short_pre["taker_rel"].fillna(999) <= p["short_taker_rel_max"])
            & (short_pre["d_oi"].fillna(999) <= p["short_d_oi_max"])
            & (short_pre["score_short"] >= p["short_score_conf"])
        ]
        short_pick = short_pool.nlargest(TOP_K, "score_short")
        if len(short_pick) < MIN_HOLDINGS:
            need = MIN_HOLDINGS - len(short_pick)
            short_pick = pd.concat(
                [short_pick, short_pre[~short_pre["symbol"].isin(short_pick["symbol"])].nlargest(need, "score_short")]
            ).drop_duplicates("symbol")

        long_syms = long_pick["symbol"].tolist()
        short_syms = short_pick["symbol"].tolist()
        long_hit = [s for s in long_syms if s in up_set]
        short_hit = [s for s in short_syms if s in dn_set]
        long_ret = float(long_pick["ret_fwd_4h"].mean()) if not long_pick.empty else 0.0
        short_ret = float((-short_pick["ret_fwd_4h"]).mean()) if not short_pick.empty else 0.0
        combo = 0.5 * long_ret + 0.5 * short_ret
        pnl_rows.append({"ts": ts, "long_ret_4h": long_ret, "short_ret_4h": short_ret, "combo_ret_4h": combo})

        rows.append(
            {
                "ts": ts,
                "regime": regime,
                "long_count": len(long_syms),
                "short_count": len(short_syms),
                "long_hit_count@10_vs_real30": len(long_hit),
                "short_hit_count@10_vs_real30": len(short_hit),
                "long_hit_rate": len(long_hit) / max(len(long_syms), 1),
                "short_hit_rate": len(short_hit) / max(len(short_syms), 1),
                "long_ret_4h": long_ret,
                "short_ret_4h": short_ret,
                "combo_ret_4h": combo,
            }
        )
        for _, r in long_pick.iterrows():
            sym = r["symbol"]
            detail.append(
                {
                    "ts": ts,
                    "side": "long",
                    "symbol": sym,
                    "score": float(r["score_long"]),
                    "real_top30_rank": up_rank_map.get(sym, "-"),
                    "ret_fwd_4h": float(r["ret_fwd_4h"]) if pd.notna(r["ret_fwd_4h"]) else np.nan,
                    "is_hit_top30": int(sym in up_set),
                }
            )
        for _, r in short_pick.iterrows():
            sym = r["symbol"]
            detail.append(
                {
                    "ts": ts,
                    "side": "short",
                    "symbol": sym,
                    "score": float(r["score_short"]),
                    "real_top30_rank": dn_rank_map.get(sym, "-"),
                    "ret_fwd_4h": float(r["ret_fwd_4h"]) if pd.notna(r["ret_fwd_4h"]) else np.nan,
                    "is_hit_top30": int(sym in dn_set),
                }
            )
    return pd.DataFrame(rows), pd.DataFrame(detail), pd.DataFrame(pnl_rows), panel


def factor_attribution(panel, test_start, test_end):
    test = panel[(panel["ts"] >= test_start) & (panel["ts"] <= test_end)].copy()
    factors = ["F1", "F2", "F3", "F4", "F5", "G1", "G2", "G3", "G4", "G5", "score_long", "score_short"]
    rows = []
    for fac in factors:
        x = test[["ts", fac, "ret_fwd_4h"]].dropna()
        if x.empty:
            continue
        def _spearman_like(g):
            a = g[fac].rank(method="average")
            b = g["ret_fwd_4h"].rank(method="average")
            return a.corr(b)

        ic = x.groupby("ts").apply(_spearman_like).dropna()
        rows.append(
            {
                "factor": fac,
                "spearman_ic_mean": float(ic.mean()) if len(ic) else np.nan,
                "spearman_ic_std": float(ic.std()) if len(ic) else np.nan,
                "sample_bars": int(len(ic)),
            }
        )
    return pd.DataFrame(rows)


def write_md(summary_df, detail_df, ic_df):
    lines = ["# v2 4H滚动训练/测试报告", ""]
    lines.append("- 标签：未来4H收益")
    lines.append("- 训练截止：2026-02-28（滚动回看84个4H）")
    lines.append("- 测试区间：2026-03-01 ~ 2026-03-05")
    lines.append("- 指标：收益导向（long/short/combo）+ 命中真实Top30（辅助）")
    lines.append("")
    if not summary_df.empty:
        lines.append("## 汇总")
        lines.append(f"- 平均做多4H收益：`{summary_df['long_ret_4h'].mean():.4%}`")
        lines.append(f"- 平均做空4H收益：`{summary_df['short_ret_4h'].mean():.4%}`")
        lines.append(f"- 平均组合4H收益：`{summary_df['combo_ret_4h'].mean():.4%}`")
        lines.append(f"- 做多命中率均值：`{summary_df['long_hit_rate'].mean():.4%}`")
        lines.append(f"- 做空命中率均值：`{summary_df['short_hit_rate'].mean():.4%}`")
        lines.append("")
    lines.append("## 因子归因（测试期Spearman IC均值）")
    for _, r in ic_df.sort_values("spearman_ic_mean", ascending=False).iterrows():
        lines.append(f"- {r['factor']}: `{r['spearman_ic_mean']:.5f}`")
    lines.append("")
    lines.append("## 明细文件")
    lines.append("- `v2_4h_summary.csv`：每个4H时点命中率与收益")
    lines.append("- `v2_4h_detail.csv`：每个4H时点多空Top10及真实Top30排名")
    lines.append("- `v2_4h_factor_ic.csv`：因子归因IC")
    with open("v2_4h_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    symbols = read_symbols()
    print(f"载入交易对数量: {len(symbols)}")
    panel = build_panel(symbols)
    panel = add_features(panel)
    summary_df, detail_df, pnl_df, panel_all = evaluate(panel)
    ic_df = factor_attribution(panel_all, TEST_START, TEST_END)
    summary_df.to_csv("v2_4h_summary.csv", index=False)
    detail_df.to_csv("v2_4h_detail.csv", index=False)
    ic_df.to_csv("v2_4h_factor_ic.csv", index=False)
    pnl_df.to_csv("v2_4h_pnl.csv", index=False)
    write_md(summary_df, detail_df, ic_df)
    print("已输出: v2_4h_report.md / v2_4h_summary.csv / v2_4h_detail.csv / v2_4h_factor_ic.csv / v2_4h_pnl.csv")


if __name__ == "__main__":
    main()
