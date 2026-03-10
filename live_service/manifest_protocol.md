# manifest.json 协议定义（v2.0）

`manifest.json` 字段定义如下：

- `version`: string，信号版本号，建议等于 `run_id`
- `run_id`: string，单次信号计算批次唯一ID
- `updated_at`: string，UTC时间，ISO8601格式
- `bar_open_time`: string，本次信号对应4H K线开盘时间，UTC ISO8601
- `bar_open_time_ms`: number，本次信号对应4H K线开盘时间，毫秒时间戳
- `active_signal_file`: string，当前激活信号文件名
- `active_pairs_file`: string，本次入场候选交易对文件名
- `active_universe_file`: string，当前全市场Universe文件名
- `active_runtime_pairs_file`: string，Freqtrade运行时实际读取的交易对文件名
- `active_score_file`: string，本次打分明细文件名
- `selected_pairs_count`: number，本次候选交易对数量
- `signal_checksum`: string，`active_signal_file` 的 SHA256
- `manifest_schema_version`: string，固定为 `2.0`

`params_manifest.json` 字段定义如下：

- `version`: string，参数版本号
- `updated_at`: string，UTC时间，ISO8601格式
- `active_params_file`: string，当前激活参数文件名
- `manifest_schema_version`: string，固定为 `2.0`

`active_signal_file` 内容结构如下：

```json
{
  "signals": {
    "BTC/USDT:USDT": {
      "long": ["2026-03-09T00:00:00Z"],
      "short": []
    }
  }
}
```

`active_runtime_pairs_file` 内容结构如下：

```json
{
  "exchange": {
    "pair_whitelist": ["BTC/USDT:USDT"],
    "pair_blacklist": []
  }
}
```

