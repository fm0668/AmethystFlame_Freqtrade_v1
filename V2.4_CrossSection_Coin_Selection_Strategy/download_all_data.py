import os
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from pathlib import Path

LOOKBACK_DAYS = int(os.getenv("LOOKBACK_DAYS", "35"))
END_DATE = os.getenv("END_DATE", datetime.now().strftime("%Y-%m-%d"))
START_DATE = os.getenv(
    "START_DATE",
    (datetime.now() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d"),
)
BASE_URL = "https://data.binance.vision/data/futures/um"
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = os.getenv("DATA_DIR", str(PROJECT_ROOT / "data" / "binance" / "um"))
SYMBOLS_FILE = BASE_DIR / "symbols_list.txt"
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "12"))
API_WORKERS = int(os.getenv("API_WORKERS", "4"))
MAX_SYMBOLS = int(os.getenv("MAX_SYMBOLS", "0"))
REQUEST_TIMEOUT = (8, 45)
MAX_RETRY = 4
EXCLUDED_INDEX = {'BTCDOMUSDT', 'DEFIUSDT', 'FOOTBALLUSDT', 'BLUEBIRDUSDT'}

COUNTER_LOCK = Lock()
PRINT_EVERY = 500


def load_symbols():
    try:
        try:
            with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
                all_symbols = [line.strip() for line in f if line.strip()]
        except UnicodeDecodeError:
            with open(SYMBOLS_FILE, "r", encoding="gbk") as f:
                all_symbols = [line.strip() for line in f if line.strip()]
        symbols = [s for s in all_symbols if s not in EXCLUDED_INDEX]
        if MAX_SYMBOLS > 0:
            symbols = symbols[:MAX_SYMBOLS]
        print(f"读取到 {len(all_symbols)} 个交易对")
        print(f"剔除 {len(EXCLUDED_INDEX)} 个指数合约: {sorted(EXCLUDED_INDEX)}")
        print(f"最终待下载: {len(symbols)} 个交易对")
        return symbols
    except Exception as e:
        print(f"读取 {SYMBOLS_FILE} 失败: {e}")
        return ["BTCUSDT"]


def get_months_in_range(start_date, end_date):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    months = []
    current = start.replace(day=1)
    current_real_month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while current <= end:
        if current < current_real_month_start:
            next_month = current.replace(year=current.year + 1, month=1) if current.month == 12 else current.replace(month=current.month + 1)
            if end >= (next_month - timedelta(days=1)):
                months.append(current.strftime("%Y-%m"))
        current = current.replace(year=current.year + 1, month=1) if current.month == 12 else current.replace(month=current.month + 1)
    return months


def get_days_in_range(start_date, end_date, exclude_months=None):
    if exclude_months is None:
        exclude_months = []
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days = []
    current = start
    while current <= end:
        if current.strftime("%Y-%m") not in exclude_months:
            days.append(current)
        current += timedelta(days=1)
    return days


def build_download_tasks(symbols, monthly_months, daily_dates, all_metrics_dates):
    tasks = []
    for symbol in symbols:
        for month in monthly_months:
            tasks.append((
                f"{BASE_URL}/monthly/klines/{symbol}/1m/{symbol}-1m-{month}.zip",
                f"{DATA_DIR}/klines/{symbol}/1m/{symbol}-1m-{month}.zip",
            ))
        for date in daily_dates:
            d = date.strftime("%Y-%m-%d")
            tasks.append((
                f"{BASE_URL}/daily/klines/{symbol}/1m/{symbol}-1m-{d}.zip",
                f"{DATA_DIR}/klines/{symbol}/1m/{symbol}-1m-{d}.zip",
            ))
        for month in monthly_months:
            tasks.append((
                f"{BASE_URL}/monthly/fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip",
                f"{DATA_DIR}/fundingRate/{symbol}/{symbol}-fundingRate-{month}.zip",
            ))
        for date in all_metrics_dates:
            d = date.strftime("%Y-%m-%d")
            tasks.append((
                f"{BASE_URL}/daily/metrics/{symbol}/{symbol}-metrics-{d}.zip",
                f"{DATA_DIR}/metrics/{symbol}/{symbol}-metrics-{d}.zip",
            ))
    return tasks


def download_file(task):
    url, save_path = task
    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        return "skip"
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    for attempt in range(1, MAX_RETRY + 1):
        try:
            resp = requests.get(url, stream=True, timeout=REQUEST_TIMEOUT)
            code = resp.status_code
            if code == 200:
                tmp_path = save_path + ".part"
                with open(tmp_path, "wb") as f:
                    for chunk in resp.iter_content(64 * 1024):
                        if chunk:
                            f.write(chunk)
                if os.path.getsize(tmp_path) == 0:
                    os.remove(tmp_path)
                    return "empty"
                os.replace(tmp_path, save_path)
                return "ok"
            if code == 404:
                return "404"
            if attempt < MAX_RETRY:
                time.sleep(0.2 * attempt)
                continue
            return f"http_{code}"
        except Exception:
            if attempt < MAX_RETRY:
                time.sleep(0.3 * attempt)
                continue
            return "error"
    return "error"


def supplement_funding_rate_via_api(symbol, start_date, end_date):
    save_dir = f"{DATA_DIR}/fundingRate/{symbol}"
    os.makedirs(save_dir, exist_ok=True)
    save_path = f"{save_dir}/{symbol}-fundingRate-API_supplement.csv"
    if os.path.exists(save_path) and os.path.getsize(save_path) > 0:
        return "skip"
    try:
        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000) + 86400000
        all_data = []
        current_start = start_ts
        while current_start < end_ts:
            params = {"symbol": symbol, "startTime": current_start, "endTime": end_ts, "limit": 1000}
            resp = requests.get("https://fapi.binance.com/fapi/v1/fundingRate", params=params, timeout=REQUEST_TIMEOUT)
            data = resp.json()
            if not data:
                break
            all_data.extend(data)
            current_start = data[-1]["fundingTime"] + 1
            time.sleep(0.05)
        if not all_data:
            return "empty"
        df = pd.DataFrame(all_data)
        df["calc_time"] = df["fundingTime"]
        df["last_funding_rate"] = df["fundingRate"]
        df["funding_interval_hours"] = 8
        df[["calc_time", "funding_interval_hours", "last_funding_rate"]].to_csv(save_path, index=False)
        return "ok"
    except Exception:
        return "error"


def main():
    symbols = load_symbols()
    monthly_months = get_months_in_range(START_DATE, END_DATE)
    daily_dates = get_days_in_range(START_DATE, END_DATE, exclude_months=monthly_months)
    all_metrics_dates = get_days_in_range(START_DATE, END_DATE, exclude_months=[])

    tasks = build_download_tasks(symbols, monthly_months, daily_dates, all_metrics_dates)
    total = len(tasks)
    print(f"并发下载线程数: {MAX_WORKERS}")
    print(f"文件任务总数: {total}")

    stats = {"ok": 0, "skip": 0, "404": 0, "error": 0, "other": 0}
    done = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(download_file, task) for task in tasks]
        for future in as_completed(futures):
            result = future.result()
            with COUNTER_LOCK:
                done += 1
                if result in stats:
                    stats[result] += 1
                elif str(result).startswith("http_"):
                    stats["other"] += 1
                else:
                    stats["error"] += 1
                if done % PRINT_EVERY == 0 or done == total:
                    print(f"进度: {done}/{total} | 成功:{stats['ok']} 跳过:{stats['skip']} 404:{stats['404']} 错误:{stats['error']} 其他:{stats['other']}")

    if daily_dates:
        api_start_date = daily_dates[0].strftime("%Y-%m-%d")
        api_end_date = daily_dates[-1].strftime("%Y-%m-%d")
        print(f"开始API补充资金费率, 线程数: {API_WORKERS}")
        api_stats = {"ok": 0, "skip": 0, "empty": 0, "error": 0}
        with ThreadPoolExecutor(max_workers=API_WORKERS) as executor:
            futures = [executor.submit(supplement_funding_rate_via_api, s, api_start_date, api_end_date) for s in symbols]
            for future in as_completed(futures):
                result = future.result()
                if result in api_stats:
                    api_stats[result] += 1
                else:
                    api_stats["error"] += 1
        print(f"API补充结果: {api_stats}")

    print(f"下载完成: {stats}")


if __name__ == "__main__":
    main()
