import pandas as pd
import argparse

from run_candidate_validation import (
    read_symbols,
    build_panel,
    add_features,
    derive_parameters,
    rank_truth,
)


TRAIN_START = "2026-02-15"
TRAIN_END = "2026-02-20"
TEST_START = "2026-02-21"
TEST_END = "2026-02-26"
SHORT_TOP_K = 60
TOP_K = 10
OUTPUT_PREFIX = "candidate_top10"


def find_best_n(panel):
    best_n = 2
    best_score = -1.0
    params = derive_parameters(panel, TRAIN_START, TRAIN_END)
    for n in [2, 3, 4, 5, 6]:
        ds = pd.date_range(TRAIN_START, TRAIN_END, freq="D").date
        ps = []
        for d in ds:
            day_df = panel[panel["date"] == d].copy()
            if day_df.empty:
                continue
            _, _, _, truth_dn = rank_truth(day_df)
            short_prefilter = day_df.nlargest(SHORT_TOP_K, "ret_1d").copy()
            short_prefilter = short_prefilter[short_prefilter["up_streak"] >= n]
            short_pool = short_prefilter[
                (short_prefilter["funding_rate"].fillna(-999) >= params["short_funding_rate_min"])
                & (short_prefilter["global_ls_ratio"].fillna(-999) >= params["short_global_ls_min"])
                & (short_prefilter["top_ls_ratio"].fillna(-999) >= params["short_top_ls_min"])
                & (short_prefilter["taker_rel"].fillna(999) <= params["short_taker_rel_max"])
                & (short_prefilter["d_oi"].fillna(999) <= params["short_d_oi_max"])
            ].copy()
            picks = short_pool.nlargest(TOP_K, "score_short_raw")["symbol"].tolist()
            if len(picks) < TOP_K:
                need = TOP_K - len(picks)
                backup = short_prefilter[~short_prefilter["symbol"].isin(picks)].nlargest(need, "score_short_raw")["symbol"].tolist()
                picks = picks + backup
            hit = len(set(picks) & truth_dn) / TOP_K if picks else 0
            ps.append(hit)
        score = sum(ps) / len(ps) if ps else 0
        if score > best_score:
            best_score = score
            best_n = n
    return best_n, params


def run():
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
    panel = build_panel(symbols)
    panel = add_features(panel).sort_values(["date", "symbol"])
    best_n, params = find_best_n(panel)

    summary_rows = []
    detail_rows = []
    md_lines = [f"# {TEST_START}~{TEST_END} Top10 多空筛选评估", ""]
    md_lines.append(f"- 训练倒推参数区间：{TRAIN_START}~{TRAIN_END}")
    md_lines.append(f"- 测试区间：{TEST_START}~{TEST_END}")
    md_lines.append(f"- 做空连涨最优N（日K）：{best_n}")
    md_lines.append("")

    for d in pd.date_range(TEST_START, TEST_END, freq="D").date:
        day_df = panel[panel["date"] == d].copy()
        if day_df.empty:
            continue

        truth_up_ranked, truth_dn_ranked, truth_up, truth_dn = rank_truth(day_df)
        up_rank_map = {s: i + 1 for i, s in enumerate(truth_up_ranked)}
        dn_rank_map = {s: i + 1 for i, s in enumerate(truth_dn_ranked)}

        long_pool = day_df[
            (day_df["vol_1d_surge"] >= params["long_vol_1d_surge_min"])
            & (day_df["vol_4h_surge"] >= params["long_vol_4h_surge_min"])
            & (day_df["taker_buy_ratio"] >= params["long_taker_buy_ratio_min"])
            & (day_df["mom_rel"] >= params["long_mom_rel_min"])
            & (day_df["d_oi"].fillna(-999) >= params["long_d_oi_min"])
        ].copy()
        long_pick_df = long_pool.nlargest(TOP_K, "score_long")[["symbol", "score_long", "ret_fwd_24h"]].copy()

        short_prefilter = day_df.nlargest(SHORT_TOP_K, "ret_1d").copy()
        short_prefilter = short_prefilter[short_prefilter["up_streak"] >= best_n]
        short_pool = short_prefilter[
            (short_prefilter["funding_rate"].fillna(-999) >= params["short_funding_rate_min"])
            & (short_prefilter["global_ls_ratio"].fillna(-999) >= params["short_global_ls_min"])
            & (short_prefilter["top_ls_ratio"].fillna(-999) >= params["short_top_ls_min"])
            & (short_prefilter["taker_rel"].fillna(999) <= params["short_taker_rel_max"])
            & (short_prefilter["d_oi"].fillna(999) <= params["short_d_oi_max"])
        ].copy()
        short_pick_df = short_pool.nlargest(TOP_K, "score_short_raw")[["symbol", "score_short_raw", "ret_fwd_24h"]].copy()
        if len(short_pick_df) < TOP_K:
            need = TOP_K - len(short_pick_df)
            backup = short_prefilter[~short_prefilter["symbol"].isin(short_pick_df["symbol"])].nlargest(
                need, "score_short_raw"
            )[["symbol", "score_short_raw", "ret_fwd_24h"]]
            short_pick_df = pd.concat([short_pick_df, backup], ignore_index=True)

        long_picks = long_pick_df["symbol"].tolist()
        short_picks = short_pick_df["symbol"].tolist()

        long_hits = [s for s in long_picks if s in truth_up]
        short_hits = [s for s in short_picks if s in truth_dn]
        long_hit_rate = len(long_hits) / TOP_K
        short_hit_rate = len(short_hits) / TOP_K

        summary_rows.append(
            {
                "date": str(d),
                "long_hit_count@10_vs_real30": len(long_hits),
                "long_hit_rate": long_hit_rate,
                "short_hit_count@10_vs_real30": len(short_hits),
                "short_hit_rate": short_hit_rate,
            }
        )

        md_lines.append(f"## {d}")
        md_lines.append(f"- 做多命中：{len(long_hits)}/10；做空命中：{len(short_hits)}/10")
        md_lines.append("")
        md_lines.append("### 做多Top10（含真实涨幅Top30排名与未来24h涨跌幅）")
        for _, r in long_pick_df.iterrows():
            sym = r["symbol"]
            rank = up_rank_map.get(sym, "-")
            ret = float(r["ret_fwd_24h"]) if pd.notna(r["ret_fwd_24h"]) else float("nan")
            md_lines.append(f"- {sym} | 真实涨幅Top30排名: {rank} | 未来24h收益: {ret:.4%}")
            detail_rows.append(
                {
                    "date": str(d),
                    "side": "long",
                    "symbol": sym,
                    "score": float(r["score_long"]),
                    "real_top30_rank": rank,
                    "ret_fwd_24h": ret,
                }
            )
        md_lines.append("")
        md_lines.append("### 做空Top10（含真实跌幅Top30排名与未来24h涨跌幅）")
        for _, r in short_pick_df.iterrows():
            sym = r["symbol"]
            rank = dn_rank_map.get(sym, "-")
            ret = float(r["ret_fwd_24h"]) if pd.notna(r["ret_fwd_24h"]) else float("nan")
            md_lines.append(f"- {sym} | 真实跌幅Top30排名: {rank} | 未来24h收益: {ret:.4%}")
            detail_rows.append(
                {
                    "date": str(d),
                    "side": "short",
                    "symbol": sym,
                    "score": float(r["score_short_raw"]),
                    "real_top30_rank": rank,
                    "ret_fwd_24h": ret,
                }
            )
        md_lines.append("")

    summary_df = pd.DataFrame(summary_rows)
    detail_df = pd.DataFrame(detail_rows)
    summary_df.to_csv(f"{OUTPUT_PREFIX}_hit_summary.csv", index=False)
    detail_df.to_csv(f"{OUTPUT_PREFIX}_detail.csv", index=False)
    with open(f"{OUTPUT_PREFIX}_eval.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))


if __name__ == "__main__":
    run()
