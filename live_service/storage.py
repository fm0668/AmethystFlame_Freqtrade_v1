from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd


class LiveStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = duckdb.connect(str(path))
        self._init_schema()

    def _init_schema(self) -> None:
        self.conn.execute(
            """
            create table if not exists bars_4h_full (
                symbol varchar,
                open_time bigint,
                open double,
                high double,
                low double,
                close double,
                volume double,
                close_time bigint,
                quote_volume double,
                trade_count bigint,
                taker_buy_volume double,
                taker_buy_quote_volume double,
                primary key (symbol, open_time)
            )
            """
        )
        self.conn.execute(
            """
            create table if not exists funding_8h (
                symbol varchar,
                funding_time bigint,
                funding_rate double,
                mark_price double,
                primary key (symbol, funding_time)
            )
            """
        )
        self.conn.execute(
            """
            create table if not exists oi_4h (
                symbol varchar,
                ts bigint,
                sum_open_interest double,
                sum_open_interest_value double,
                primary key (symbol, ts)
            )
            """
        )
        self.conn.execute(
            """
            create table if not exists global_lsr_4h (
                symbol varchar,
                ts bigint,
                long_short_ratio double,
                long_account double,
                short_account double,
                primary key (symbol, ts)
            )
            """
        )
        self.conn.execute(
            """
            create table if not exists top_lsr_4h (
                symbol varchar,
                ts bigint,
                long_short_ratio double,
                long_account double,
                short_account double,
                primary key (symbol, ts)
            )
            """
        )
        self.conn.execute(
            """
            create table if not exists run_state (
                id integer primary key,
                last_synced_at bigint,
                last_emitted_open_time bigint
            )
            """
        )
        self.conn.execute("insert or ignore into run_state(id, last_synced_at, last_emitted_open_time) values (1, 0, 0)")

    def upsert_bars(self, rows: list[dict]) -> None:
        if not rows:
            return
        df = pd.DataFrame(rows)
        self.conn.register("tmp_bars_df", df)
        self.conn.execute(
            """
            insert or replace into bars_4h_full
            select * from tmp_bars_df
            """
        )
        self.conn.unregister("tmp_bars_df")

    def upsert_funding(self, rows: list[dict]) -> None:
        if not rows:
            return
        df = pd.DataFrame(rows)
        self.conn.register("tmp_funding_df", df)
        self.conn.execute(
            """
            insert or replace into funding_8h
            select * from tmp_funding_df
            """
        )
        self.conn.unregister("tmp_funding_df")

    def upsert_oi(self, rows: list[dict]) -> None:
        if not rows:
            return
        df = pd.DataFrame(rows)
        self.conn.register("tmp_oi_df", df)
        self.conn.execute(
            """
            insert or replace into oi_4h
            select * from tmp_oi_df
            """
        )
        self.conn.unregister("tmp_oi_df")

    def upsert_global_lsr(self, rows: list[dict]) -> None:
        if not rows:
            return
        df = pd.DataFrame(rows)
        self.conn.register("tmp_global_lsr_df", df)
        self.conn.execute(
            """
            insert or replace into global_lsr_4h
            select * from tmp_global_lsr_df
            """
        )
        self.conn.unregister("tmp_global_lsr_df")

    def upsert_top_lsr(self, rows: list[dict]) -> None:
        if not rows:
            return
        df = pd.DataFrame(rows)
        self.conn.register("tmp_top_lsr_df", df)
        self.conn.execute(
            """
            insert or replace into top_lsr_4h
            select * from tmp_top_lsr_df
            """
        )
        self.conn.unregister("tmp_top_lsr_df")

    def mark_sync_time(self, ts_ms: int) -> None:
        self.conn.execute("update run_state set last_synced_at = ? where id = 1", [ts_ms])

    def set_last_emitted_open_time(self, open_time_ms: int) -> None:
        self.conn.execute("update run_state set last_emitted_open_time = ? where id = 1", [open_time_ms])

    def get_last_emitted_open_time(self) -> int:
        row = self.conn.execute("select last_emitted_open_time from run_state where id = 1").fetchone()
        return int(row[0]) if row else 0

    def latest_closed_open_time(self) -> int:
        row = self.conn.execute(
            """
            select max(open_time) from bars_4h_full
            """
        ).fetchone()
        return int(row[0]) if row and row[0] else 0
