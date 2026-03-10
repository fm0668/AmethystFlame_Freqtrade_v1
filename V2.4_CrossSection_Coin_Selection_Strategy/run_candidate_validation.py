import os
import glob
import zipfile
from datetime import datetime
from pathlib import Path
import argparse

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = os.getenv("DATA_DIR", str(PROJECT_ROOT / "data" / "binance" / "um"))
SYMBOLS_FILE = BASE_DIR / "symbols_list.txt"
TRAIN_START = "2026-02-15"
TRAIN_END = "2026-02-20"
TEST_START = "2026-02-21"
TEST_END = "2026-02-26"
OUTPUT_PREFIX = "candidate_validation"
EXCLUDED_INDEX = {"BTCDOMUSDT", "DEFIUSDT", "FOOTBALLUSDT", "BLUEBIRDUSDT"}
SHORT_TOP_K = 60
LONG_TOP_K = 30
SHORT_FINAL_K = 30


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
    symbols = [s for s in symbols if s not in EXCLUDED_INDEX]
    return symbols


def read_csv_from_zip(zip_path):
    with zipfile.ZipFile(zip_path, "r") as zf:
        name = zf.namelist()[0]
        df = pd.read_csv(zf.open(name), header=None)
    header_row = df.iloc[0].astype(str).str.lower().tolist()
    if "open_time" in header_row or "create_time" in header_row or "calc_time" in header_row:
        df.columns = df.iloc[0].tolist()
        df = df.iloc[1:].copy()
    return df


def load_kline_daily(symbol):
    path = os.path.join(DATA_DIR, "klines", symbol, "1m")
    if not os.path.isdir(path):
        return None
    target_files = []
    window_start = datetime.strptime(TRAIN_START, "%Y-%m-%d").date()
    window_end = datetime.strptime(TEST_END, "%Y-%m-%d").date()
    for p in glob.glob(os.path.join(path, "*.zip")):
        bn = os.path.basename(p)
        prefix = f"{symbol}-1m-"
        if not (bn.startswith(prefix) and bn.endswith(".zip")):
            continue
        tag = bn[len(prefix):-4]
        if len(tag) == 10:
            try:
                d = datetime.strptime(tag, "%Y-%m-%d").date()
            except ValueError:
                continue
            if window_start <= d <= window_end:
                target_files.append(p)
        elif len(tag) == 7:
            try:
                m = datetime.strptime(f"{tag}-01", "%Y-%m-%d").date()
            except ValueError:
                continue
            if window_start.replace(day=1) <= m <= window_end.replace(day=1):
                target_files.append(p)
    if not target_files:
        return None
    chunks = []
    for p in target_files:
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
        if set(cols).issubset(set(df.columns)):
            k = df[cols].copy()
        else:
            k = df.iloc[:, :12].copy()
            k.columns = cols
        k["open_time"] = pd.to_numeric(k["open_time"], errors="coerce")
        k = k.dropna(subset=["open_time"])
        for c in ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_quote_volume"]:
            k[c] = pd.to_numeric(k[c], errors="coerce")
        k["dt"] = pd.to_datetime(k["open_time"], unit="ms", utc=True)
        k = k.sort_values("dt")
        k["date"] = k["dt"].dt.date
        k["bucket4h"] = k["dt"].dt.floor("4h")
        day = k.groupby("date").agg(
            close=("close", "last"),
            quote_volume=("quote_volume", "sum"),
            taker_buy_quote_volume=("taker_buy_quote_volume", "sum"),
        )
        h4 = k.groupby("bucket4h").agg(h4_quote_volume=("quote_volume", "sum"))
        h4["h4_surge"] = h4["h4_quote_volume"] / h4["h4_quote_volume"].rolling(42, min_periods=20).mean()
        h4["date"] = h4.index.date
        h4_last = h4.groupby("date").agg(vol_4h_surge=("h4_surge", "last"))
        day = day.join(h4_last, how="left")
        chunks.append(day)
    if not chunks:
        return None
    d = pd.concat(chunks).groupby(level=0).last().sort_index()
    d["ret_1d"] = d["close"].pct_change()
    d["ret_fwd_24h"] = d["close"].shift(-1) / d["close"] - 1
    d["vol_1d_surge"] = d["quote_volume"] / d["quote_volume"].shift(1).rolling(7, min_periods=5).mean()
    d["taker_buy_ratio"] = d["taker_buy_quote_volume"] / d["quote_volume"].replace(0, np.nan)
    d["net_taker_norm"] = (2 * d["taker_buy_quote_volume"] - d["quote_volume"]) / d["quote_volume"].replace(0, np.nan)
    up = (d["ret_1d"] > 0).astype(int)
    d["up_streak"] = up.groupby((up != up.shift()).cumsum()).cumsum().where(up == 1, 0)
    d["symbol"] = symbol
    return d.reset_index().rename(columns={"index": "date"})


def load_metrics(symbol):
    path = os.path.join(DATA_DIR, "metrics", symbol)
    if not os.path.isdir(path):
        return None
    files = sorted(glob.glob(os.path.join(path, f"{symbol}-metrics-*.zip")))
    if not files:
        return None
    recs = []
    for p in files:
        dstr = os.path.basename(p).split("-metrics-")[-1].replace(".zip", "")
        try:
            d = datetime.strptime(dstr, "%Y-%m-%d").date()
        except Exception:
            continue
        window_start = datetime.strptime(TRAIN_START, "%Y-%m-%d").date()
        window_end = datetime.strptime(TEST_END, "%Y-%m-%d").date()
        if not (window_start <= d <= window_end):
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
        if set(cols).issubset(set(df.columns)):
            x = df[cols].copy()
        else:
            x = df.iloc[:, :8].copy()
            x.columns = cols
        for c in cols[2:]:
            x[c] = pd.to_numeric(x[c], errors="coerce")
        row = {
            "date": d,
            "oi_value": x["sum_open_interest_value"].iloc[-1],
            "global_ls_ratio": x["count_long_short_ratio"].iloc[-1],
            "top_ls_ratio": x["count_toptrader_long_short_ratio"].iloc[-1],
        }
        recs.append(row)
    if not recs:
        return None
    m = pd.DataFrame(recs).sort_values("date")
    m["d_oi"] = m["oi_value"].pct_change()
    return m


def load_funding(symbol):
    funding_dir = os.path.join(DATA_DIR, "fundingRate", symbol)
    files = sorted(glob.glob(os.path.join(funding_dir, f"{symbol}-fundingRate-*.zip")))
    if not files:
        return None
    recs = []
    for path in files:
        df = read_csv_from_zip(path)
        cols = ["calc_time", "funding_interval_hours", "last_funding_rate"]
        if set(cols).issubset(set(df.columns)):
            x = df[cols].copy()
        else:
            x = df.iloc[:, :3].copy()
            x.columns = cols
        x["calc_time"] = pd.to_numeric(x["calc_time"], errors="coerce")
        x["last_funding_rate"] = pd.to_numeric(x["last_funding_rate"], errors="coerce")
        x["date"] = pd.to_datetime(x["calc_time"], unit="ms", utc=True).dt.date
        recs.append(x.groupby("date").agg(funding_rate=("last_funding_rate", "mean")).reset_index())
    f = pd.concat(recs, ignore_index=True).groupby("date").agg(funding_rate=("funding_rate", "mean")).reset_index()
    window_start = datetime.strptime(TRAIN_START, "%Y-%m-%d").date()
    window_end = datetime.strptime(TEST_END, "%Y-%m-%d").date()
    f = f[(f["date"] >= window_start) & (f["date"] <= window_end)]
    return f


def zscore_by_date(df, col):
    g = df.groupby("date")[col]
    return (df[col] - g.transform("mean")) / g.transform("std").replace(0, np.nan)


def build_panel(symbols):
    frames = []
    for i, s in enumerate(symbols, 1):
        kd = load_kline_daily(s)
        if kd is None or kd.empty:
            continue
        md = load_metrics(s)
        fd = load_funding(s)
        if md is not None:
            kd = kd.merge(md, on="date", how="left")
        if fd is not None:
            kd = kd.merge(fd, on="date", how="left")
        else:
            kd["funding_rate"] = np.nan
        frames.append(kd)
        if i % 50 == 0:
            print(f"已处理 {i}/{len(symbols)} 个交易对")
    panel = pd.concat(frames, ignore_index=True)
    panel["date"] = pd.to_datetime(panel["date"]).dt.date
    return panel


def add_features(panel):
    btc = panel[panel["symbol"] == "BTCUSDT"][["date", "ret_1d", "taker_buy_ratio", "funding_rate"]].rename(
        columns={"ret_1d": "btc_ret_1d", "taker_buy_ratio": "btc_taker_buy_ratio", "funding_rate": "btc_funding_rate"}
    )
    panel = panel.merge(btc, on="date", how="left")
    panel["mom_rel"] = panel["ret_1d"] - panel["btc_ret_1d"]
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
        "ret_1d",
    ]:
        panel[f"z_{c}"] = zscore_by_date(panel, c).clip(-3, 3)

    panel["funding_missing"] = panel["funding_rate"].isna().astype(int)
    panel["F1"] = panel["z_mom_rel"].fillna(0)
    panel["F2"] = (0.5 * panel["z_vol_1d_surge"].fillna(0) + 0.5 * panel["z_vol_4h_surge"].fillna(0))
    panel["F3"] = (0.6 * panel["z_taker_rel"].fillna(0) + 0.4 * panel["z_net_taker_norm"].fillna(0))
    panel["F4"] = panel["z_d_oi"].fillna(0)
    panel["F5_base"] = (-panel["z_funding_rate"].fillna(0) - panel["z_global_ls_ratio"].fillna(0) - panel["z_top_ls_ratio"].fillna(0)) / 3
    panel["F5"] = np.where(panel["funding_missing"] == 1, panel["F5_base"] * 0.5, panel["F5_base"])
    panel["score_long"] = 0.35 * panel["F1"] + 0.25 * panel["F2"] + 0.20 * panel["F3"] + 0.10 * panel["F4"] + 0.10 * panel["F5"]

    panel["G1"] = (panel["z_funding_rate"].fillna(0) + panel["z_global_ls_ratio"].fillna(0) + panel["z_top_ls_ratio"].fillna(0)) / 3
    panel["G2"] = -0.6 * panel["z_taker_rel"].fillna(0) - 0.4 * panel["z_net_taker_norm"].fillna(0)
    panel["G3"] = -panel["z_d_oi"].fillna(0)
    panel["G4"] = panel["z_mom_rel"].fillna(0)
    panel["G5"] = -panel["ret_1d"].abs().groupby(panel["date"]).transform(lambda s: (s - s.mean()) / (s.std() if s.std() else 1)).fillna(0).clip(-3, 3)
    panel["score_short_raw"] = 0.35 * panel["G1"] + 0.25 * panel["G2"] + 0.20 * panel["G3"] + 0.15 * panel["G4"] + 0.05 * panel["G5"]
    return panel


def precision_at_k(picks, truth_set):
    if not picks:
        return 0.0
    return len(set(picks) & truth_set) / len(picks)


def rank_truth(day_df):
    x = day_df.dropna(subset=["ret_fwd_24h"]).copy()
    top_up = x.nlargest(30, "ret_fwd_24h")["symbol"].tolist()
    top_dn = x.nsmallest(30, "ret_fwd_24h")["symbol"].tolist()
    return top_up, top_dn, set(top_up), set(top_dn)


def derive_parameters(panel, start_date, end_date):
    ds = pd.date_range(start_date, end_date, freq="D").date
    long_samples = []
    short_samples = []
    for d in ds:
        day_df = panel[panel["date"] == d].copy()
        if day_df.empty:
            continue
        truth_up_ranked, truth_dn_ranked, truth_up, truth_dn = rank_truth(day_df)
        long_df = day_df[day_df["symbol"].isin(truth_up)]
        short_df = day_df[day_df["symbol"].isin(truth_dn)]
        if not long_df.empty:
            long_samples.append(long_df)
        if not short_df.empty:
            short_samples.append(short_df)
    long_all = pd.concat(long_samples, ignore_index=True) if long_samples else pd.DataFrame()
    short_all = pd.concat(short_samples, ignore_index=True) if short_samples else pd.DataFrame()

    params = {
        "long_vol_1d_surge_min": float(long_all["vol_1d_surge"].quantile(0.30)) if not long_all.empty else 1.8,
        "long_vol_4h_surge_min": float(long_all["vol_4h_surge"].quantile(0.30)) if not long_all.empty else 1.6,
        "long_taker_buy_ratio_min": float(long_all["taker_buy_ratio"].quantile(0.35)) if not long_all.empty else 0.50,
        "long_mom_rel_min": float(long_all["mom_rel"].quantile(0.30)) if not long_all.empty else 0.0,
        "long_d_oi_min": float(long_all["d_oi"].quantile(0.30)) if not long_all.empty else 0.0,
        "short_funding_rate_min": float(short_all["funding_rate"].quantile(0.65)) if not short_all.empty else 0.0,
        "short_global_ls_min": float(short_all["global_ls_ratio"].quantile(0.65)) if not short_all.empty else 1.0,
        "short_top_ls_min": float(short_all["top_ls_ratio"].quantile(0.65)) if not short_all.empty else 1.0,
        "short_taker_rel_max": float(short_all["taker_rel"].quantile(0.40)) if not short_all.empty else 0.0,
        "short_d_oi_max": float(short_all["d_oi"].quantile(0.45)) if not short_all.empty else 0.0,
    }
    return params


def evaluate(panel, start_date, end_date, n_up, params):
    ds = pd.date_range(start_date, end_date, freq="D").date
    long_precisions = []
    short_precisions = []
    rows = []
    list_rows = []
    for d in ds:
        day_df = panel[panel["date"] == d].copy()
        if day_df.empty:
            continue
        truth_up_ranked, truth_dn_ranked, truth_up, truth_dn = rank_truth(day_df)

        long_pool = day_df[
            (day_df["vol_1d_surge"] >= params["long_vol_1d_surge_min"])
            & (day_df["vol_4h_surge"] >= params["long_vol_4h_surge_min"])
            & (day_df["taker_buy_ratio"] >= params["long_taker_buy_ratio_min"])
            & (day_df["mom_rel"] >= params["long_mom_rel_min"])
            & (day_df["d_oi"].fillna(-999) >= params["long_d_oi_min"])
        ].copy()
        long_picks = long_pool.nlargest(LONG_TOP_K, "score_long")["symbol"].tolist()

        short_prefilter = day_df.nlargest(SHORT_TOP_K, "ret_1d").copy()
        short_prefilter = short_prefilter[short_prefilter["up_streak"] >= n_up]
        short_pool = short_prefilter[
            (short_prefilter["funding_rate"].fillna(-999) >= params["short_funding_rate_min"])
            & (short_prefilter["global_ls_ratio"].fillna(-999) >= params["short_global_ls_min"])
            & (short_prefilter["top_ls_ratio"].fillna(-999) >= params["short_top_ls_min"])
            & (short_prefilter["taker_rel"].fillna(999) <= params["short_taker_rel_max"])
            & (short_prefilter["d_oi"].fillna(999) <= params["short_d_oi_max"])
        ].copy()
        short_picks = short_pool.nlargest(SHORT_FINAL_K, "score_short_raw")["symbol"].tolist()
        if len(short_picks) < SHORT_FINAL_K:
            need = SHORT_FINAL_K - len(short_picks)
            backup = short_prefilter[~short_prefilter["symbol"].isin(short_picks)].nlargest(need, "score_short_raw")["symbol"].tolist()
            short_picks = short_picks + backup

        lp = precision_at_k(long_picks, truth_up)
        sp = precision_at_k(short_picks, truth_dn)
        long_precisions.append(lp)
        short_precisions.append(sp)
        long_hit = sorted(list(set(long_picks) & truth_up))
        short_hit = sorted(list(set(short_picks) & truth_dn))
        rows.append(
            {
                "date": str(d),
                "long_pool_size": len(long_pool),
                "short_pool_size": len(short_pool),
                "long_precision@30": lp,
                "short_precision@30": sp,
            }
        )
        list_rows.append(
            {
                "date": str(d),
                "pred_long_top30": "|".join(long_picks),
                "real_long_top30": "|".join(truth_up_ranked),
                "hit_long": "|".join(long_hit),
                "pred_short_top30": "|".join(short_picks),
                "real_short_top30": "|".join(truth_dn_ranked),
                "hit_short": "|".join(short_hit),
                "long_hit_count": len(long_hit),
                "short_hit_count": len(short_hit),
            }
        )
    summary = {
        "long_precision@30_avg": float(np.mean(long_precisions) if long_precisions else 0),
        "short_precision@30_avg": float(np.mean(short_precisions) if short_precisions else 0),
    }
    return summary, pd.DataFrame(rows), pd.DataFrame(list_rows)


def write_report(train_best_n, params, train_summary, test_summary, train_daily, test_daily, test_lists):
    lines = []
    lines.append("# 候选池倒推验证报告（v1 执行结果）")
    lines.append("")
    lines.append("## 固定规则")
    lines.append("- 标签：未来24h收益")
    lines.append("- 做空初筛：当日涨幅前60")
    lines.append("- 做空连涨定义：日K连涨N天（N由训练集挖掘）")
    lines.append("- Funding缺失：降权处理")
    lines.append("")
    lines.append("## 由训练集倒推得到的具体参数")
    lines.append(f"- 做多 VOL_1D_SURGE 下限：`{params['long_vol_1d_surge_min']:.4f}`")
    lines.append(f"- 做多 VOL_4H_SURGE 下限：`{params['long_vol_4h_surge_min']:.4f}`")
    lines.append(f"- 做多 TAKER_BUY_RATIO 下限：`{params['long_taker_buy_ratio_min']:.4f}`")
    lines.append(f"- 做多 MOM_REL 下限：`{params['long_mom_rel_min']:.6f}`")
    lines.append(f"- 做多 dOI 下限：`{params['long_d_oi_min']:.6f}`")
    lines.append(f"- 做空 Funding 下限：`{params['short_funding_rate_min']:.6f}`")
    lines.append(f"- 做空 全市场多空人数比下限：`{params['short_global_ls_min']:.4f}`")
    lines.append(f"- 做空 大户多空人数比下限：`{params['short_top_ls_min']:.4f}`")
    lines.append(f"- 做空 TAKER_REL 上限：`{params['short_taker_rel_max']:.6f}`")
    lines.append(f"- 做空 dOI 上限：`{params['short_d_oi_max']:.6f}`")
    lines.append("")
    lines.append(f"## 训练集（{TRAIN_START} ~ {TRAIN_END}）")
    lines.append(f"- 挖掘得到最优N：`{train_best_n}`")
    lines.append(f"- Long Precision@30 均值：`{train_summary['long_precision@30_avg']:.4f}`")
    lines.append(f"- Short Precision@30 均值：`{train_summary['short_precision@30_avg']:.4f}`")
    lines.append("")
    lines.append(f"## 测试集（{TEST_START} ~ {TEST_END}）")
    lines.append(f"- Long Precision@30 均值：`{test_summary['long_precision@30_avg']:.4f}`")
    lines.append(f"- Short Precision@30 均值：`{test_summary['short_precision@30_avg']:.4f}`")
    lines.append("")
    lines.append("## 备注")
    lines.append("- 该结果用于候选池筛选，不等同最终交易收益。")
    lines.append("- 下一步建议叠加手续费、滑点和仓位约束后再做策略级验证。")
    with open(f"{OUTPUT_PREFIX}_report.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    train_daily.to_csv(f"{OUTPUT_PREFIX}_train_daily.csv", index=False)
    test_daily.to_csv(f"{OUTPUT_PREFIX}_test_daily.csv", index=False)
    test_lists.to_csv(f"{OUTPUT_PREFIX}_test_symbol_lists.csv", index=False)


def main():
    global TRAIN_START, TRAIN_END, TEST_START, TEST_END, OUTPUT_PREFIX
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-start", type=str, default=None)
    parser.add_argument("--train-end", type=str, default=None)
    parser.add_argument("--test-start", type=str, default=None)
    parser.add_argument("--test-end", type=str, default=None)
    parser.add_argument("--output-prefix", type=str, default=None)
    args = parser.parse_args()
    if args.train_start:
        TRAIN_START = args.train_start
    if args.train_end:
        TRAIN_END = args.train_end
    if args.test_start:
        TEST_START = args.test_start
    if args.test_end:
        TEST_END = args.test_end
    if args.output_prefix:
        OUTPUT_PREFIX = args.output_prefix
    symbols = read_symbols()
    print(f"载入交易对数量: {len(symbols)}")
    panel = build_panel(symbols)
    panel = add_features(panel)
    panel = panel.sort_values(["date", "symbol"])

    best_n = None
    best_score = -1
    best_summary = None
    best_daily = None
    best_params = None
    for n in [2, 3, 4, 5, 6]:
        p = derive_parameters(panel, TRAIN_START, TRAIN_END)
        s, d, _ = evaluate(panel, TRAIN_START, TRAIN_END, n, p)
        if s["short_precision@30_avg"] > best_score:
            best_score = s["short_precision@30_avg"]
            best_n = n
            best_summary = s
            best_daily = d
            best_params = p
    print(f"训练集最优N: {best_n}, short_precision@30={best_score:.4f}")

    test_summary, test_daily, test_lists = evaluate(panel, TEST_START, TEST_END, best_n, best_params)
    write_report(best_n, best_params, best_summary, test_summary, best_daily, test_daily, test_lists)
    print(f"已输出: {OUTPUT_PREFIX}_report.md / {OUTPUT_PREFIX}_train_daily.csv / {OUTPUT_PREFIX}_test_daily.csv / {OUTPUT_PREFIX}_test_symbol_lists.csv")


if __name__ == "__main__":
    main()
