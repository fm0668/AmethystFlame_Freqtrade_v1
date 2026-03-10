import os
from datetime import datetime, timedelta
from pathlib import Path

SYMBOLS = ['BTCUSDT']
START_DATE = "2026-01-01"
END_DATE = "2026-03-06"
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = os.getenv("DATA_DIR", str(PROJECT_ROOT / "data" / "binance" / "um"))

def get_expected_files(symbol, start_date, end_date):
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    
    # Logic same as download_data.py
    monthly_months = []
    daily_dates = []
    
    current = start.replace(day=1)
    while current <= end:
        now = datetime.now()
        current_real_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        if current < current_real_month_start:
            if current.month == 12:
                next_month = current.replace(year=current.year+1, month=1)
            else:
                next_month = current.replace(month=current.month+1)
            last_day_of_month = next_month - timedelta(days=1)
            
            if end >= last_day_of_month:
                monthly_months.append(current.strftime("%Y-%m"))
        
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)

    # Calculate daily dates
    current = start
    while current <= end:
        month_str = current.strftime("%Y-%m")
        if month_str not in monthly_months:
            daily_dates.append(current)
        current += timedelta(days=1)
        
    metrics_dates = []
    current = start
    while current <= end:
        metrics_dates.append(current)
        current += timedelta(days=1)
        
    files = []
    
    # Klines & Funding Rate
    for m in monthly_months:
        files.append(f"klines/{symbol}/1m/{symbol}-1m-{m}.zip")
        files.append(f"fundingRate/{symbol}/{symbol}-fundingRate-{m}.zip")
        
    for d in daily_dates:
        d_str = d.strftime("%Y-%m-%d")
        files.append(f"klines/{symbol}/1m/{symbol}-1m-{d_str}.zip")
        files.append(f"fundingRate/{symbol}/{symbol}-fundingRate-{d_str}.zip")
        
    # Metrics
    for d in metrics_dates:
        d_str = d.strftime("%Y-%m-%d")
        files.append(f"metrics/{symbol}/{symbol}-metrics-{d_str}.zip")
        
    return files

def main():
    missing = []
    total = 0
    for symbol in SYMBOLS:
        expected = get_expected_files(symbol, START_DATE, END_DATE)
        total += len(expected)
        for f in expected:
            path = os.path.join(DATA_DIR, f)
            if not os.path.exists(path):
                missing.append(path)
            else:
                # Check size > 0
                if os.path.getsize(path) == 0:
                    missing.append(f"{path} (Size 0)")
                    
    if missing:
        print(f"验证失败! 缺失 {len(missing)}/{total} 个文件:")
        for m in missing:
            print(m)
    else:
        print(f"验证成功! 所有 {total} 个文件均存在且非空。")

if __name__ == "__main__":
    main()
