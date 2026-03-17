import argparse
import numpy as np
import pandas as pd

from run_v2_walkforward_4h import read_symbols, build_panel, classify_regime


TRAIN_LOOKBACK_BARS = 84
TOP_K = 5
TRUTH_K = 30
SHORT_TOP_K = 80
MIN_HOLDINGS = 3
TEST_START = pd.Timestamp("2026-03-01 00:00:00", tz="UTC")
TEST_END = pd.Timestamp("2026-03-05 20:00:00", tz="UTC")


def zscore_by_ts(df, col):
    g = df.groupby("ts")[col]
    return (df[col] - g.transform("mean")) / g.transform("std").replace(0, np.nan)


def rank_truth(df_ts):
    x = df_ts.dropna(subset=["ret_fwd_4h"]).copy()
    up = x.nlargest(TRUTH_K, "ret_fwd_4h")["symbol"].tolist()
    dn = x.nsmallest(TRUTH_K, "ret_fwd_4h")["symbol"].tolist()
    return up, dn, set(up), set(dn)


def weighted_quantile(values, weights, q):
    m = np.isfinite(values) & np.isfinite(weights)
    v = values[m]
    w = weights[m]
    if len(v) == 0:
        return np.nan
    order = np.argsort(v)
    v = v[order]
    w = w[order]
    cw = np.cumsum(w)
    if cw[-1] <= 0:
        return np.nan
    target = q * cw[-1]
    idx = np.searchsorted(cw, target)
    idx = min(max(idx, 0), len(v) - 1)
    return float(v[idx])


def weighted_corr(a, b, w):
    m = np.isfinite(a) & np.isfinite(b) & np.isfinite(w)
    a = a[m]
    b = b[m]
    w = w[m]
    if len(a) < 5 or np.sum(w) <= 0:
        return np.nan
    wa = np.average(a, weights=w)
    wb = np.average(b, weights=w)
    cov = np.average((a - wa) * (b - wb), weights=w)
    va = np.average((a - wa) ** 2, weights=w)
    vb = np.average((b - wb) ** 2, weights=w)
    if va <= 1e-12 or vb <= 1e-12:
        return np.nan
    return float(cov / np.sqrt(va * vb))


def add_symbol_time_features(panel):
    panel = panel.sort_values(["symbol", "ts"]).copy()
    panel["roll_high_20"] = panel.groupby("symbol")["high"].transform(lambda s: s.shift(1).rolling(20, min_periods=8).max())
    panel["roll_low_20"] = panel.groupby("symbol")["low"].transform(lambda s: s.shift(1).rolling(20, min_periods=8).min())
    panel["breakout_20"] = panel["close"] / panel["roll_high_20"] - 1
    panel["rebound_20"] = panel["close"] / panel["roll_low_20"] - 1
    panel["trend_hit_6"] = panel.groupby("symbol")["ret_4h"].transform(lambda s: s.shift(1).rolling(6, min_periods=3).apply(lambda x: np.mean(x > 0), raw=True))
    panel["d_top_ls_24h"] = panel.groupby("symbol")["top_ls_ratio"].transform(lambda s: s - s.shift(6))
    panel["d_global_ls_24h"] = panel.groupby("symbol")["global_ls_ratio"].transform(lambda s: s - s.shift(6))
    panel["activity_proxy"] = panel["vol_4h_surge"]
    panel["upper_wick"] = (panel["high"] - panel[["open", "close"]].max(axis=1)) / (panel["high"] - panel["low"]).replace(0, np.nan)
    panel["lower_wick"] = (panel[["open", "close"]].min(axis=1) - panel["low"]) / (panel["high"] - panel["low"]).replace(0, np.nan)
    panel["pullback_quality"] = panel["close"] / panel.groupby("symbol")["high"].transform(lambda s: s.shift(1).rolling(6, min_periods=3).max()) - 1
    return panel


def add_features(panel):
    panel = add_symbol_time_features(panel)
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
    panel["whale_exit_raw"] = panel["ret_4h"].clip(lower=0) * (-panel["d_top_ls_24h"]).clip(lower=0)
    panel["oi_bear_div_raw"] = panel["ret_4h"].clip(lower=0) * (-panel["d_oi"]).clip(lower=0)
    panel["activity_oi_div_raw"] = panel["activity_proxy"].clip(lower=0) * (-panel["d_oi"]).clip(lower=0)

    for c in [
        "mom_rel",
        "vol_4h_surge",
        "taker_rel",
        "breakout_20",
        "trend_hit_6",
        "d_oi",
        "funding_rate",
        "global_ls_ratio",
        "top_ls_ratio",
        "upper_wick",
        "lower_wick",
        "rebound_20",
        "pullback_quality",
        "whale_exit_raw",
        "oi_bear_div_raw",
        "activity_oi_div_raw",
    ]:
        panel[f"z_{c}"] = zscore_by_ts(panel, c).clip(-3, 3)

    panel["L1_momo"] = panel["z_mom_rel"].fillna(0)
    panel["L2_flow"] = (0.5 * panel["z_vol_4h_surge"].fillna(0) + 0.5 * panel["z_taker_rel"].fillna(0))
    panel["L3_confirm"] = (0.5 * panel["z_breakout_20"].fillna(0) + 0.5 * panel["z_trend_hit_6"].fillna(0))
    panel["L4_oi"] = panel["z_d_oi"].fillna(0)
    panel["L5_cost"] = (-panel["z_funding_rate"].fillna(0) - panel["z_global_ls_ratio"].fillna(0)) / 2
    panel["L6_rebound"] = (0.6 * panel["z_rebound_20"].fillna(0) + 0.4 * panel["z_pullback_quality"].fillna(0))
    panel["L7_candle"] = panel["z_lower_wick"].fillna(0)

    panel["S1_crowd"] = (panel["z_funding_rate"].fillna(0) + panel["z_global_ls_ratio"].fillna(0) + panel["z_top_ls_ratio"].fillna(0)) / 3
    panel["S2_whale_exit"] = panel["z_whale_exit_raw"].fillna(0)
    panel["S3_price_oi_div"] = panel["z_oi_bear_div_raw"].fillna(0)
    panel["S4_activity_oi_div"] = panel["z_activity_oi_div_raw"].fillna(0)
    panel["S5_upper_wick"] = panel["z_upper_wick"].fillna(0)
    return panel


def assign_training_weights(df):
    out = []
    for _, g in df.groupby("ts"):
        up, dn, _, _ = rank_truth(g)
        up_rank = {s: i + 1 for i, s in enumerate(up)}
        dn_rank = {s: i + 1 for i, s in enumerate(dn)}
        x = g.copy()
        x["w_long"] = x["symbol"].map(lambda s: np.exp(-0.35 * (up_rank[s] - 1)) if s in up_rank else 0.005)
        x["w_short"] = x["symbol"].map(lambda s: np.exp(-0.25 * (dn_rank[s] - 1)) if s in dn_rank else 0.01)
        out.append(x)
    return pd.concat(out, ignore_index=True) if out else df.copy()


def calc_factor_weights(train_df, components, target_col, weight_col):
    scores = []
    for fac in components:
        ic_list = []
        pos = 0
        total = 0
        for _, g in train_df.groupby("ts"):
            x = g[[fac, target_col, weight_col]].dropna()
            if len(x) < 8:
                continue
            a = x[fac].rank(method="average").to_numpy()
            b = x[target_col].rank(method="average").to_numpy()
            w = x[weight_col].to_numpy()
            ic = weighted_corr(a, b, w)
            if np.isfinite(ic):
                ic_list.append(ic)
                total += 1
                if ic > 0:
                    pos += 1
        if len(ic_list) == 0:
            scores.append((fac, 0.0))
            continue
        mean_ic = float(np.mean(ic_list))
        std_ic = float(np.std(ic_list))
        pos_rate = pos / max(total, 1)
        stability = mean_ic * pos_rate / (std_ic + 0.05)
        scores.append((fac, max(stability, 0.0)))
    total_score = sum(s for _, s in scores)
    if total_score <= 1e-12:
        return {k: 1 / len(components) for k in components}
    return {k: s / total_score for k, s in scores}


def apply_scores(df, long_w, short_w):
    df = df.copy()
    df["score_long"] = 0.0
    for k, w in long_w.items():
        df["score_long"] += w * df[k].fillna(0)
    df["score_short"] = 0.0
    for k, w in short_w.items():
        df["score_short"] += w * df[k].fillna(0)
    return df


def derive_regime_model(train_df):
    models = {}
    long_components = ["L1_momo", "L2_flow", "L3_confirm", "L4_oi", "L5_cost", "L6_rebound", "L7_candle"]
    short_components = ["S1_crowd", "S2_whale_exit", "S3_price_oi_div", "S4_activity_oi_div", "S5_upper_wick"]
    for regime in ["strong", "weak"]:
        r = train_df[train_df["regime"] == regime].copy()
        if r.empty:
            models[regime] = None
            continue
        r = assign_training_weights(r)
        r["target_short"] = -r["ret_fwd_4h"]
        long_w = calc_factor_weights(r, long_components, "ret_fwd_4h", "w_long")
        short_w = calc_factor_weights(r, short_components, "target_short", "w_short")
        r = apply_scores(r, long_w, short_w)

        truth_rows = []
        for _, g in r.groupby("ts"):
            up, dn, up_set, dn_set = rank_truth(g)
            gg = g.copy()
            gg["is_up30"] = gg["symbol"].isin(up_set).astype(int)
            gg["is_dn30"] = gg["symbol"].isin(dn_set).astype(int)
            truth_rows.append(gg)
        rr = pd.concat(truth_rows, ignore_index=True) if truth_rows else r
        long_truth = rr[rr["is_up30"] == 1]
        short_truth = rr[rr["is_dn30"] == 1]

        p = {
            "long_vol_4h_min": weighted_quantile(long_truth["vol_4h_surge"].to_numpy(), long_truth["w_long"].to_numpy(), 0.20) if not long_truth.empty else 0.8,
            "long_breakout_min": weighted_quantile(long_truth["breakout_20"].to_numpy(), long_truth["w_long"].to_numpy(), 0.20) if not long_truth.empty else -0.02,
            "long_trend_min": weighted_quantile(long_truth["trend_hit_6"].to_numpy(), long_truth["w_long"].to_numpy(), 0.25) if not long_truth.empty else 0.40,
            "long_rebound_min": weighted_quantile(long_truth["rebound_20"].to_numpy(), long_truth["w_long"].to_numpy(), 0.20) if not long_truth.empty else 0.0,
            "short_funding_min": weighted_quantile(short_truth["funding_rate"].to_numpy(), short_truth["w_short"].to_numpy(), 0.35) if not short_truth.empty else -0.0003,
            "short_global_min": weighted_quantile(short_truth["global_ls_ratio"].to_numpy(), short_truth["w_short"].to_numpy(), 0.35) if not short_truth.empty else 0.9,
            "short_top_min": weighted_quantile(short_truth["top_ls_ratio"].to_numpy(), short_truth["w_short"].to_numpy(), 0.35) if not short_truth.empty else 0.9,
        }

        best_obj = -1e9
        best_cfg = {"long_conf_q": 0.20, "short_conf_q": 0.30, "short_up_streak_min": 3}
        groups = [g for _, g in r.groupby("ts")]
        if len(groups) > 20:
            step = max(len(groups) // 20, 1)
            groups = groups[::step]
        for lq in [0.15, 0.20, 0.30]:
            lc = float(np.nanquantile(long_truth["score_long"], lq)) if not long_truth.empty else -0.2
            for sq in [0.25, 0.35]:
                sc = float(np.nanquantile(short_truth["score_short"], sq)) if not short_truth.empty else -0.2
                for n in [3, 6]:
                    obj_list = []
                    for g in groups:
                        long_pool = g[
                            (g["vol_4h_surge"] >= p["long_vol_4h_min"])
                            & (g["breakout_20"].fillna(-999) >= p["long_breakout_min"])
                            & (g["trend_hit_6"].fillna(-999) >= p["long_trend_min"])
                            & (g["rebound_20"].fillna(-999) >= p["long_rebound_min"])
                            & (g["score_long"] >= lc)
                        ]
                        long_pick = long_pool.nlargest(TOP_K, "score_long")
                        if len(long_pick) < MIN_HOLDINGS:
                            need = MIN_HOLDINGS - len(long_pick)
                            long_pick = pd.concat([long_pick, g[~g["symbol"].isin(long_pick["symbol"])].nlargest(need, "score_long")]).drop_duplicates("symbol")
                        short_pre = g.nlargest(SHORT_TOP_K, "ret_4h")
                        short_pre = short_pre[short_pre["up_streak_4h"] >= n]
                        short_pool = short_pre[
                            (short_pre["funding_rate"].fillna(-999) >= p["short_funding_min"])
                            & (short_pre["global_ls_ratio"].fillna(-999) >= p["short_global_min"])
                            & (short_pre["top_ls_ratio"].fillna(-999) >= p["short_top_min"])
                            & (short_pre["score_short"] >= sc)
                        ]
                        short_pick = short_pool.nlargest(TOP_K, "score_short")
                        if len(short_pick) < MIN_HOLDINGS:
                            need = MIN_HOLDINGS - len(short_pick)
                            short_pick = pd.concat([short_pick, short_pre[~short_pre["symbol"].isin(short_pick["symbol"])].nlargest(need, "score_short")]).drop_duplicates("symbol")
                        if short_pick.empty:
                            short_pick = g.nlargest(1, "score_short")
                        lr = float(long_pick["ret_fwd_4h"].mean()) if not long_pick.empty else 0.0
                        sr = float((-short_pick["ret_fwd_4h"]).mean()) if not short_pick.empty else 0.0
                        ldd = float(np.abs(np.minimum(long_pick["next_low"] / long_pick["close"] - 1, 0)).mean()) if not long_pick.empty else 0.0
                        sdd = float(np.abs(np.minimum(1 - short_pick["next_high"] / short_pick["close"], 0)).mean()) if not short_pick.empty else 0.0
                        obj = 0.70 * lr + 0.30 * sr - 0.20 * ldd - 0.10 * sdd
                        obj_list.append(obj)
                    o = float(np.mean(obj_list)) if obj_list else -1e9
                    if o > best_obj:
                        best_obj = o
                        best_cfg = {"long_conf_q": lq, "short_conf_q": sq, "short_up_streak_min": n}
        p["long_score_conf"] = float(np.nanquantile(long_truth["score_long"], best_cfg["long_conf_q"])) if not long_truth.empty else -0.2
        p["short_score_conf"] = float(np.nanquantile(short_truth["score_short"], best_cfg["short_conf_q"])) if not short_truth.empty else -0.2
        p["short_up_streak_min"] = best_cfg["short_up_streak_min"]
        models[regime] = {"params": p, "long_weights": long_w, "short_weights": short_w}
    return models


def evaluate(panel, test_start, test_end, output_prefix, fixed_train_start=None, fixed_train_end=None):
    panel = panel.merge(classify_regime(panel), on="ts", how="left")
    test_ts = sorted([t for t in panel["ts"].unique() if test_start <= t <= test_end])
    rows = []
    detail = []
    weight_rows = []
    md = ["# v2.4 4H滚动测试报告（做多侧二次优化）", "", "- 标签：未来4H收益", f"- 测试区间：{test_start} ~ {test_end}", f"- 选币数量：做多/做空各Top{TOP_K}"]
    fixed_models = None
    if fixed_train_start is not None and fixed_train_end is not None:
        fixed_train = panel[(panel["ts"] >= fixed_train_start) & (panel["ts"] <= fixed_train_end)]
        if fixed_train.empty:
            raise ValueError(f"固定训练窗口无数据: {fixed_train_start} ~ {fixed_train_end}")
        fixed_models = derive_regime_model(fixed_train)
        md.append(f"- 训练模式：固定窗口 {fixed_train_start} ~ {fixed_train_end}")
    else:
        md.append(f"- 训练模式：滚动窗口（回看{TRAIN_LOOKBACK_BARS}根4H）")
    md.append("")
    for ts in test_ts:
        if fixed_models is None:
            train_start = ts - pd.Timedelta(hours=4 * TRAIN_LOOKBACK_BARS)
            train = panel[(panel["ts"] < ts) & (panel["ts"] >= train_start)]
            if train.empty:
                continue
            models = derive_regime_model(train)
        else:
            models = fixed_models
        cur = panel[panel["ts"] == ts].copy()
        if cur.empty:
            continue
        regime = cur["regime"].iloc[0] if pd.notna(cur["regime"].iloc[0]) else "weak"
        model = models.get(regime) or models.get("weak") or models.get("strong")
        if model is None:
            continue
        cur = apply_scores(cur, model["long_weights"], model["short_weights"])
        p = model["params"]
        for k, v in model["long_weights"].items():
            weight_rows.append({"ts": ts, "regime": regime, "side": "long", "factor": k, "weight": v})
        for k, v in model["short_weights"].items():
            weight_rows.append({"ts": ts, "regime": regime, "side": "short", "factor": k, "weight": v})

        up_ranked, dn_ranked, up_set, dn_set = rank_truth(cur)
        up_map = {s: i + 1 for i, s in enumerate(up_ranked)}
        dn_map = {s: i + 1 for i, s in enumerate(dn_ranked)}

        long_pool = cur[
            (cur["vol_4h_surge"] >= p["long_vol_4h_min"])
            & (cur["breakout_20"].fillna(-999) >= p["long_breakout_min"])
            & (cur["trend_hit_6"].fillna(-999) >= p["long_trend_min"])
            & (cur["rebound_20"].fillna(-999) >= p["long_rebound_min"])
            & (cur["score_long"] >= p["long_score_conf"])
        ]
        long_pick = long_pool.nlargest(TOP_K, "score_long")
        if len(long_pick) < MIN_HOLDINGS:
            need = MIN_HOLDINGS - len(long_pick)
            long_pick = pd.concat([long_pick, cur[~cur["symbol"].isin(long_pick["symbol"])].nlargest(need, "score_long")]).drop_duplicates("symbol")

        short_pre = cur.nlargest(SHORT_TOP_K, "ret_4h")
        short_pre = short_pre[short_pre["up_streak_4h"] >= p["short_up_streak_min"]]
        short_pool = short_pre[
            (short_pre["funding_rate"].fillna(-999) >= p["short_funding_min"])
            & (short_pre["global_ls_ratio"].fillna(-999) >= p["short_global_min"])
            & (short_pre["top_ls_ratio"].fillna(-999) >= p["short_top_min"])
            & (short_pre["score_short"] >= p["short_score_conf"])
        ]
        short_pick = short_pool.nlargest(TOP_K, "score_short")
        if len(short_pick) < MIN_HOLDINGS:
            need = MIN_HOLDINGS - len(short_pick)
            short_pick = pd.concat([short_pick, short_pre[~short_pre["symbol"].isin(short_pick["symbol"])].nlargest(need, "score_short")]).drop_duplicates("symbol")
        if short_pick.empty:
            short_pick = cur.nlargest(1, "score_short")

        long_syms = long_pick["symbol"].tolist()
        short_syms = short_pick["symbol"].tolist()
        long_hit = [s for s in long_syms if s in up_set]
        short_hit = [s for s in short_syms if s in dn_set]
        long_ret = float(long_pick["ret_fwd_4h"].mean()) if not long_pick.empty else 0.0
        short_ret = float((-short_pick["ret_fwd_4h"]).mean()) if not short_pick.empty else 0.0
        combo = 0.5 * long_ret + 0.5 * short_ret

        rows.append(
            {
                "ts": ts,
                "regime": regime,
                "long_count": len(long_syms),
                "short_count": len(short_syms),
                "long_hit_count_vs_real30": len(long_hit),
                "short_hit_count_vs_real30": len(short_hit),
                "long_hit_rate": len(long_hit) / max(len(long_syms), 1),
                "short_hit_rate": len(short_hit) / max(len(short_syms), 1),
                "long_ret_4h": long_ret,
                "short_ret_4h": short_ret,
                "combo_ret_4h": combo,
            }
        )

        md.append(f"## {ts} | Regime: {regime}")
        md.append(f"- 做多总收益（4H等权）：{long_ret:.4%}")
        md.append(f"- 做空总收益（4H等权）：{short_ret:.4%}")
        md.append(f"- 时段汇总收益（4H，多空各50%）：{combo:.4%}")
        md.append(f"- 命中：做多 {len(long_hit)}/{len(long_syms)}，做空 {len(short_hit)}/{len(short_syms)}")
        md.append("")
        md.append(f"### 做多Top{TOP_K}")
        if long_pick.empty:
            md.append("- 无入选标的")
        for _, r in long_pick.iterrows():
            sym = r["symbol"]
            rank = up_map.get(sym, "-")
            ret = float(r["ret_fwd_4h"]) if pd.notna(r["ret_fwd_4h"]) else np.nan
            score = float(r["score_long"])
            entry = float(r["close"]) if pd.notna(r["close"]) else np.nan
            long_mdd = (float(r["next_low"]) / entry - 1) if pd.notna(r["next_low"]) and pd.notna(entry) and entry != 0 else np.nan
            md.append(f"- {sym} | 合成评分: {score:.4f} | 真实涨幅Top30排名: {rank} | 未来4H收益: {ret:.4%} | 未来4H最大回撤: {long_mdd:.4%}")
            detail.append({"ts": ts, "side": "long", "symbol": sym, "score": score, "real_top30_rank": rank, "ret_fwd_4h": ret, "max_drawdown_4h": long_mdd, "entry_price": entry, "next_high": float(r["next_high"]) if pd.notna(r.get("next_high")) else np.nan, "next_low": float(r["next_low"]) if pd.notna(r.get("next_low")) else np.nan, "is_hit_top30": int(sym in up_set)})
        md.append("")
        md.append(f"### 做空Top{TOP_K}")
        if short_pick.empty:
            md.append("- 无入选标的")
        for _, r in short_pick.iterrows():
            sym = r["symbol"]
            rank = dn_map.get(sym, "-")
            ret = float(r["ret_fwd_4h"]) if pd.notna(r["ret_fwd_4h"]) else np.nan
            score = float(r["score_short"])
            entry = float(r["close"]) if pd.notna(r["close"]) else np.nan
            short_mdd = (1 - float(r["next_high"]) / entry) if pd.notna(r["next_high"]) and pd.notna(entry) and entry != 0 else np.nan
            md.append(f"- {sym} | 合成评分: {score:.4f} | 真实跌幅Top30排名: {rank} | 未来4H收益: {ret:.4%} | 未来4H最大回撤(做空): {short_mdd:.4%}")
            detail.append({"ts": ts, "side": "short", "symbol": sym, "score": score, "real_top30_rank": rank, "ret_fwd_4h": ret, "max_drawdown_4h": short_mdd, "entry_price": entry, "next_high": float(r["next_high"]) if pd.notna(r.get("next_high")) else np.nan, "next_low": float(r["next_low"]) if pd.notna(r.get("next_low")) else np.nan, "is_hit_top30": int(sym in dn_set)})
        md.append("")

    summary = pd.DataFrame(rows)
    detail_df = pd.DataFrame(detail)
    weights_df = pd.DataFrame(weight_rows)
    with open(f"{output_prefix}_eval.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md))
    return summary, detail_df, weights_df, panel


def factor_ic(panel, test_start, test_end):
    test = panel[(panel["ts"] >= test_start) & (panel["ts"] <= test_end)].copy()
    factors = ["L1_momo", "L2_flow", "L3_confirm", "L4_oi", "L5_cost", "L6_rebound", "L7_candle", "S1_crowd", "S2_whale_exit", "S3_price_oi_div", "S4_activity_oi_div", "S5_upper_wick"]
    rows = []
    for fac in factors:
        x = test[["ts", fac, "ret_fwd_4h"]].dropna()
        if x.empty:
            continue
        ic = x.groupby("ts").apply(lambda g: g[fac].rank(method="average").corr(g["ret_fwd_4h"].rank(method="average"))).dropna()
        rows.append({"factor": fac, "spearman_ic_mean": float(ic.mean()) if len(ic) else np.nan, "spearman_ic_std": float(ic.std()) if len(ic) else np.nan, "sample_bars": int(len(ic))})
    return pd.DataFrame(rows)


def parse_utc(s):
    t = pd.Timestamp(s)
    if t.tzinfo is None:
        return t.tz_localize("UTC")
    return t.tz_convert("UTC")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-start", type=str, default=None)
    parser.add_argument("--train-end", type=str, default=None)
    parser.add_argument("--test-start", type=str, default=None)
    parser.add_argument("--test-end", type=str, default=None)
    parser.add_argument("--test-date", type=str, default=None)
    parser.add_argument("--output-prefix", type=str, default="v2_4_4h")
    args = parser.parse_args()
    train_start = parse_utc(args.train_start) if args.train_start else None
    train_end = parse_utc(args.train_end) if args.train_end else None
    if args.test_date:
        test_start = parse_utc(f"{args.test_date} 00:00:00")
        test_end = parse_utc(f"{args.test_date} 20:00:00")
    else:
        test_start = parse_utc(args.test_start) if args.test_start else TEST_START
        test_end = parse_utc(args.test_end) if args.test_end else TEST_END

    symbols = read_symbols()
    print(f"载入交易对数量: {len(symbols)}")
    panel = build_panel(symbols)
    panel = add_features(panel)
    summary, detail, weights, panel_all = evaluate(panel, test_start, test_end, args.output_prefix, train_start, train_end)
    ic = factor_ic(panel_all, test_start, test_end)
    summary.to_csv(f"{args.output_prefix}_summary.csv", index=False)
    detail.to_csv(f"{args.output_prefix}_detail.csv", index=False)
    weights.to_csv(f"{args.output_prefix}_weights.csv", index=False)
    ic.to_csv(f"{args.output_prefix}_factor_ic.csv", index=False)
    if not summary.empty:
        agg = pd.DataFrame([{"avg_long_ret_4h": summary["long_ret_4h"].mean(), "avg_short_ret_4h": summary["short_ret_4h"].mean(), "avg_combo_ret_4h": summary["combo_ret_4h"].mean(), "avg_long_hit_rate": summary["long_hit_rate"].mean(), "avg_short_hit_rate": summary["short_hit_rate"].mean()}])
    else:
        agg = pd.DataFrame([{}])
    agg.to_csv(f"{args.output_prefix}_aggregate.csv", index=False)
    print(f"已输出: {args.output_prefix}_eval.md / {args.output_prefix}_summary.csv / {args.output_prefix}_detail.csv / {args.output_prefix}_weights.csv / {args.output_prefix}_factor_ic.csv / {args.output_prefix}_aggregate.csv")


if __name__ == "__main__":
    main()
