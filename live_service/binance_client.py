from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from datetime import UTC, datetime

import requests


@dataclass(slots=True)
class BinanceClient:
    base_url: str
    timeout_seconds: float = 10.0
    _session: requests.Session = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._session = requests.Session()

    def _get(self, endpoint: str, params: dict) -> list | dict:
        url = f"{self.base_url}{endpoint}"
        resp = self._session.get(url, params=params, timeout=self.timeout_seconds)
        resp.raise_for_status()
        return resp.json()

    def fetch_klines(self, symbol: str, interval: str, limit: int) -> list[dict]:
        rows = self._get(
            "/fapi/v1/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )
        out: list[dict] = []
        for r in rows:
            out.append(
                {
                    "symbol": symbol,
                    "open_time": int(r[0]),
                    "open": float(r[1]),
                    "high": float(r[2]),
                    "low": float(r[3]),
                    "close": float(r[4]),
                    "volume": float(r[5]),
                    "close_time": int(r[6]),
                    "quote_volume": float(r[7]),
                    "trade_count": int(r[8]),
                    "taker_buy_volume": float(r[9]),
                    "taker_buy_quote_volume": float(r[10]),
                }
            )
        return out

    def fetch_funding_rate(self, symbol: str, limit: int) -> list[dict]:
        rows = self._get(
            "/fapi/v1/fundingRate",
            {"symbol": symbol, "limit": limit},
        )
        out: list[dict] = []
        for r in rows:
            out.append(
                {
                    "symbol": symbol,
                    "funding_time": int(r["fundingTime"]),
                    "funding_rate": float(r["fundingRate"]),
                    "mark_price": float(r["markPrice"]),
                }
            )
        return out

    def fetch_open_interest_hist(self, symbol: str, period: str, limit: int) -> list[dict]:
        rows = self._get(
            "/futures/data/openInterestHist",
            {"symbol": symbol, "period": period, "limit": limit},
        )
        out: list[dict] = []
        for r in rows:
            out.append(
                {
                    "symbol": symbol,
                    "ts": int(r["timestamp"]),
                    "sum_open_interest": float(r["sumOpenInterest"]),
                    "sum_open_interest_value": float(r["sumOpenInterestValue"]),
                }
            )
        return out

    def fetch_global_lsr(self, symbol: str, period: str, limit: int) -> list[dict]:
        rows = self._get(
            "/futures/data/globalLongShortAccountRatio",
            {"symbol": symbol, "period": period, "limit": limit},
        )
        out: list[dict] = []
        for r in rows:
            out.append(
                {
                    "symbol": symbol,
                    "ts": int(r["timestamp"]),
                    "long_short_ratio": float(r["longShortRatio"]),
                    "long_account": float(r["longAccount"]),
                    "short_account": float(r["shortAccount"]),
                }
            )
        return out

    def fetch_top_position_lsr(self, symbol: str, period: str, limit: int) -> list[dict]:
        rows = self._get(
            "/futures/data/topLongShortPositionRatio",
            {"symbol": symbol, "period": period, "limit": limit},
        )
        out: list[dict] = []
        for r in rows:
            out.append(
                {
                    "symbol": symbol,
                    "ts": int(r["timestamp"]),
                    "long_short_ratio": float(r["longShortRatio"]),
                    "long_account": float(r["longAccount"]),
                    "short_account": float(r["shortAccount"]),
                }
            )
        return out

    @staticmethod
    def now_utc_iso() -> str:
        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
