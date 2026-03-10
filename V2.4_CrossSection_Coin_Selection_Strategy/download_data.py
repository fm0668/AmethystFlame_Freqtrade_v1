import os
import requests
from datetime import datetime, timedelta
import time
from tqdm import tqdm
from pathlib import Path

# --- 配置区 ---
# 示例币种
SYMBOLS = ['BTCUSDT'] 

START_DATE = "2026-01-01"
END_DATE = "2026-03-06"
BASE_URL = "https://data.binance.vision/data/futures/um"
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = os.getenv("DATA_DIR", str(PROJECT_ROOT / "data" / "binance" / "um"))

# --- 工具函数 ---
def download_file(url, save_path):
    if os.path.exists(save_path):
        print(f"[跳过] 已存在: {save_path}")
        return
    
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    
    try:
        resp = requests.get(url, stream=True)
        if resp.status_code == 200:
            total_size = int(resp.headers.get('content-length', 0))
            block_size = 1024 # 1 Kibibyte
            t = tqdm(total=total_size, unit='iB', unit_scale=True, desc=os.path.basename(save_path))
            with open(save_path, 'wb') as f:
                for data in resp.iter_content(block_size):
                    t.update(len(data))
                    f.write(data)
            t.close()
        else:
            print(f"[失败] HTTP {resp.status_code}: {url}")
    except Exception as e:
        print(f"[错误] {e}")

def get_months_in_range(start_date, end_date):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    months = []
    
    current = start.replace(day=1)
    # 只要月份的第一天在范围内，或者范围包含了月份的一部分
    while current <= end:
        # 如果这个月完全过去了（下一个月的第一天 <= 当前日期），则可以用 Monthly 下载
        # 但要注意 End Date 是否覆盖了整个月。如果 End Date 是 3月6日，3月只能用 Daily。
        # 这里简化逻辑：如果是过去的月份（< 当前实际月份），且请求范围覆盖了整月，则用 Monthly。
        # 考虑到当前是 2026-03-07，1月和2月是完整的过去月。
        
        # 获取当前实际日期的月初
        now = datetime.now()
        current_real_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # 只有当 `current` 月份 < `current_real_month_start` 时，Binance 才会有 Monthly 数据
        if current < current_real_month_start:
             # 检查 end_date 是否覆盖了这个月的最后一天
            # 获取 current 月的最后一天
            if current.month == 12:
                next_month = current.replace(year=current.year+1, month=1)
            else:
                next_month = current.replace(month=current.month+1)
            last_day_of_month = next_month - timedelta(days=1)
            
            if end >= last_day_of_month:
                months.append(current.strftime("%Y-%m"))
        
        # Move to next month
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
            
    return months

def get_days_in_range(start_date, end_date, exclude_months=[]):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days = []
    current = start
    while current <= end:
        month_str = current.strftime("%Y-%m")
        if month_str not in exclude_months:
            days.append(current)
        current += timedelta(days=1)
    return days

# --- 主逻辑 ---
def main():
    print(f"准备下载 {len(SYMBOLS)} 个交易对的数据...")
    print(f"时间范围: {START_DATE} 至 {END_DATE}")
    
    # 1. 计算哪些月份可以用 Monthly 下载 (1月, 2月)
    monthly_months = get_months_in_range(START_DATE, END_DATE)
    print(f"将使用 Monthly 下载的月份: {monthly_months}")
    
    # 2. 计算剩余需要用 Daily 下载的日期 (3月1日-6日)
    daily_dates = get_days_in_range(START_DATE, END_DATE, exclude_months=monthly_months)
    print(f"将使用 Daily 下载的日期数: {len(daily_dates)}")
    
    # 3. Metrics 必须全部 Daily
    all_metrics_dates = get_days_in_range(START_DATE, END_DATE, exclude_months=[])

    for symbol in SYMBOLS:
        print(f"\n>>> 处理 {symbol} <<<")
        
        # --- Klines (1m) ---
        print(f"--- 下载 Klines (1m) ---")
        # Monthly
        for month in monthly_months:
            file_name = f"{symbol}-1m-{month}.zip"
            url = f"{BASE_URL}/monthly/klines/{symbol}/1m/{file_name}"
            save_path = f"{DATA_DIR}/klines/{symbol}/1m/{file_name}"
            download_file(url, save_path)
        # Daily
        for date in daily_dates:
            date_str = date.strftime("%Y-%m-%d")
            file_name = f"{symbol}-1m-{date_str}.zip"
            url = f"{BASE_URL}/daily/klines/{symbol}/1m/{file_name}"
            save_path = f"{DATA_DIR}/klines/{symbol}/1m/{file_name}"
            download_file(url, save_path)

        # --- Funding Rate ---
        print(f"--- 下载 Funding Rate ---")
        # Monthly
        for month in monthly_months:
            file_name = f"{symbol}-fundingRate-{month}.zip"
            url = f"{BASE_URL}/monthly/fundingRate/{symbol}/{file_name}"
            save_path = f"{DATA_DIR}/fundingRate/{symbol}/{file_name}"
            download_file(url, save_path)
        # Daily
        for date in daily_dates:
            date_str = date.strftime("%Y-%m-%d")
            file_name = f"{symbol}-fundingRate-{date_str}.zip"
            url = f"{BASE_URL}/daily/fundingRate/{symbol}/{file_name}"
            save_path = f"{DATA_DIR}/fundingRate/{symbol}/{file_name}"
            download_file(url, save_path)

        # --- Metrics (All Daily) ---
        print(f"--- 下载 Metrics (Daily) ---")
        for date in all_metrics_dates:
            date_str = date.strftime("%Y-%m-%d")
            file_name = f"{symbol}-metrics-{date_str}.zip"
            url = f"{BASE_URL}/daily/metrics/{symbol}/{file_name}"
            save_path = f"{DATA_DIR}/metrics/{symbol}/{file_name}"
            download_file(url, save_path)

    print("\n所有任务完成！")

if __name__ == "__main__":
    main()
