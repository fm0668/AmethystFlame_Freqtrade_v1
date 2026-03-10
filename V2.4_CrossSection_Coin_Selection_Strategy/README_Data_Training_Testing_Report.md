# V2.4筛选策略迁移包使用说明（数据下载→训练/测试→报告）

## 1. 包内文件说明
- `get_symbols.py`：获取并筛选可交易USDT永续交易对，生成`symbols_list.txt`
- `download_all_data.py`：批量下载K线全字段、Funding、Metrics，并补充Funding API数据
- `download_data.py`：单币/小规模下载模板
- `download_funding_api.py`：单币Funding API补充模板
- `verify_data.py`：校验下载数据完整性
- `run_v2_walkforward_4h.py`：4H数据构建与基础特征函数
- `run_v2_4_long_focus.py`：V2.4主训练/回测/报告脚本
- `run_candidate_validation.py`：候选池验证脚本（历史方案）
- `run_top10_eval.py`：Top10评估脚本（历史方案）
- `build_readable_lists.py`：将CSV名单转成可读Markdown
- `symbols_list.txt`：交易对清单
- `config.example.env`：环境变量模板（下载并发、测试参数）

## 2. 环境准备
- Python建议版本：`3.10+`
- 在迁移目录创建虚拟环境后安装依赖：

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
```

## 2.1 建议先配置环境变量
```bash
copy config.example.env .env
```
- 可按机器性能调整：
  - `MAX_WORKERS`、`API_WORKERS`
- 调试时可设置：
  - `MAX_SYMBOLS=50`
- 建议将`.env`纳入运行环境，但不要提交敏感配置

## 3. 数据下载流程

## 3.1 生成交易对清单
```bash
.venv\Scripts\python get_symbols.py
```
- 输出：`symbols_list.txt`

## 3.2 批量下载全量数据（推荐）
```bash
.venv\Scripts\python download_all_data.py
```
- 默认下载：
  - Kline 1m（全字段）
  - Funding（zip + API补充）
  - Metrics（OI、多空比等）
- 环境变量可调：
  - `MAX_WORKERS`：文件下载线程数
  - `API_WORKERS`：Funding API补充线程数
  - `MAX_SYMBOLS`：限制下载币种数量（调试用）

## 3.3 数据完整性校验
```bash
.venv\Scripts\python verify_data.py
```

## 4. V2.4训练/测试与报告

## 4.1 默认区间回测（脚本内默认）
```bash
.venv\Scripts\python run_v2_4_long_focus.py
```
- 产出：
  - `v2_4_4h_eval.md`
  - `v2_4_4h_summary.csv`
  - `v2_4_4h_detail.csv`
  - `v2_4_4h_weights.csv`
  - `v2_4_4h_factor_ic.csv`
  - `v2_4_4h_aggregate.csv`

## 4.2 单日测试（不覆盖基线）
```bash
.venv\Scripts\python run_v2_4_long_focus.py --test-date 2026-03-06 --output-prefix v2_4_20260306_4h
```
- 产出示例：
  - `v2_4_20260306_4h_eval.md`
  - `v2_4_20260306_4h_summary.csv`
  - `v2_4_20260306_4h_detail.csv`
  - `v2_4_20260306_4h_weights.csv`
  - `v2_4_20260306_4h_factor_ic.csv`
  - `v2_4_20260306_4h_aggregate.csv`

## 4.3 自定义测试区间
```bash
.venv\Scripts\python run_v2_4_long_focus.py --test-start "2026-03-01 00:00:00" --test-end "2026-03-05 20:00:00" --output-prefix v2_4_custom
```

## 5. 结果解读要点
- `*_eval.md`：逐4H时段明细（选币、评分、命中、收益、最大回撤）
- `*_summary.csv`：每个4H时段聚合指标
- `*_detail.csv`：逐交易对明细（便于二次分析）
- `*_weights.csv`：每个时段、每个因子动态权重
- `*_factor_ic.csv`：测试期因子IC（稳定性评估）
- `*_aggregate.csv`：整体平均收益/命中率

## 6. 迁移到Freqtrade时建议
- 保持“筛选引擎与执行引擎解耦”：
  - 本包脚本负责每4H生成信号
  - Freqtrade只负责读信号和执行交易
- 建议信号字段：
  - `ts, symbol, side, score, rank, max_drawdown_4h, expire_ts, version`

## 7. 常见问题
- 若下载慢：降低`MAX_SYMBOLS`做小样本联调
- 若Funding缺失：先确认`download_all_data.py`中API补充是否成功
- 若回测无信号：先检查数据目录是否完整、时间区间是否覆盖测试日期
