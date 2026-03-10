import requests
import time
from datetime import datetime
import pandas as pd
import os
from pathlib import Path

# 配置
BASE_URL = "https://fapi.binance.com"
BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
DATA_DIR = os.getenv("DATA_DIR", str(PROJECT_ROOT / "data" / "binance" / "um"))

def get_funding_history(symbol, start_time, end_time):
    """
    通过API获取资金费率历史
    start_time, end_time: datetime objects
    """
    endpoint = "/fapi/v1/fundingRate"
    url = BASE_URL + endpoint
    
    # 转换为毫秒时间戳
    start_ts = int(start_time.timestamp() * 1000)
    end_ts = int(end_time.timestamp() * 1000)
    
    all_data = []
    current_start = start_ts
    
    print(f"开始获取 {symbol} 资金费率: {start_time} -> {end_time}")
    
    while current_start < end_ts:
        params = {
            "symbol": symbol,
            "startTime": current_start,
            "endTime": end_ts,
            "limit": 1000 
        }
        
        try:
            resp = requests.get(url, params=params)
            data = resp.json()
            
            if not data:
                break
                
            all_data.extend(data)
            print(f"获取到 {len(data)} 条数据, 最新时间: {datetime.fromtimestamp(data[-1]['fundingTime']/1000)}")
            
            # 更新下一次请求的开始时间
            last_time = data[-1]['fundingTime']
            current_start = last_time + 1
            
            time.sleep(0.1) # 避免限频
            
        except Exception as e:
            print(f"请求失败: {e}")
            time.sleep(1)
            
    return all_data

def save_to_csv(data, symbol):
    if not data:
        print("无数据可保存")
        return
        
    df = pd.DataFrame(data)
    # 原始字段: symbol, fundingTime, fundingRate, markPrice
    # 目标字段: calc_time, funding_interval_hours, last_funding_rate
    
    df['calc_time'] = df['fundingTime']
    df['last_funding_rate'] = df['fundingRate']
    
    # 资金费率间隔通常是8小时，但在API中不直接返回。
    # 我们可以通过相邻两条数据的时间差来推算，或者默认设为8（大部分情况）。
    # 这里为了保持格式一致，我们简单设为8，或者通过计算。
    df['funding_interval_hours'] = 8 
    
    # 只需要保留目标列
    df_final = df[['calc_time', 'funding_interval_hours', 'last_funding_rate']]
    
    # 保存路径
    save_dir = os.path.join(DATA_DIR, "fundingRate", symbol)
    os.makedirs(save_dir, exist_ok=True)
    # 命名为 API_supplement.csv，后续ETL时优先读取
    save_path = os.path.join(save_dir, f"{symbol}-fundingRate-API_supplement.csv")
    
    df_final.to_csv(save_path, index=False)
    print(f"已保存补充数据至: {save_path}")

def main():
    symbol = "BTCUSDT"
    # 补充 3月1日 到 3月7日的数据
    start_date = datetime(2026, 3, 1)
    end_date = datetime(2026, 3, 7)
    
    data = get_funding_history(symbol, start_date, end_date)
    save_to_csv(data, symbol)

if __name__ == "__main__":
    main()
