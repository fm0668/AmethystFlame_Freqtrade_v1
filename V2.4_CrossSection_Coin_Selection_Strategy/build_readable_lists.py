import pandas as pd


def main():
    df = pd.read_csv("candidate_test_symbol_lists.csv")
    lines = ["# 2026-02-21~2026-02-26 每日筛选与真实名单对照", ""]
    for _, r in df.iterrows():
        lines.append(f"## {r['date']}")
        lines.append("### 做多 Top30")
        lines.append(f"- 筛选名单：{r['pred_long_top30']}")
        lines.append(f"- 真实名单：{r['real_long_top30']}")
        lines.append(f"- 命中名单：{r['hit_long']}")
        lines.append(f"- 命中数：{int(r['long_hit_count'])}/30")
        lines.append("")
        lines.append("### 做空 Top30")
        lines.append(f"- 筛选名单：{r['pred_short_top30']}")
        lines.append(f"- 真实名单：{r['real_short_top30']}")
        lines.append(f"- 命中名单：{r['hit_short']}")
        lines.append(f"- 命中数：{int(r['short_hit_count'])}/30")
        lines.append("")
    with open("candidate_test_lists_readable.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
