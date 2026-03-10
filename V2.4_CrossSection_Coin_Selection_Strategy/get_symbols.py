import requests
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
SYMBOLS_FILE = BASE_DIR / "symbols_list.txt"

def get_all_usdt_perp_symbols():
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    try:
        resp = requests.get(url).json()
        symbols = resp['symbols']
        
        # 过滤逻辑
        # 1. 必须是 USDT 永续合约
        # 2. 状态必须是 TRADING
        # 3. 剔除稳定币交易对 (Base Asset 是稳定币)
        # 4. 上线时间 > 30天
        
        filtered_symbols = []
        excluded_stable = []
        excluded_new = []
        excluded_other = []
        
        stable_coins = ['USDC', 'USDP', 'TUSD', 'BUSD', 'FDUSD', 'DAI', 'USDT'] # Base Asset to exclude
        
        today = datetime.utcnow()
        threshold_date = today - timedelta(days=30)
        
        for s in symbols:
            # 基本过滤
            if s['contractType'] != 'PERPETUAL':
                continue
            if s['quoteAsset'] != 'USDT':
                continue
            if s['status'] != 'TRADING':
                continue
                
            symbol_name = s['symbol']
            base_asset = s['baseAsset']
            onboard_date_ts = s['onboardDate'] # ms timestamp
            onboard_date = datetime.fromtimestamp(onboard_date_ts / 1000)
            
            # 3. 剔除稳定币
            if base_asset in stable_coins:
                excluded_stable.append(symbol_name)
                continue
                
            # 4. 上线时间 < 30天
            if onboard_date > threshold_date:
                excluded_new.append(f"{symbol_name} ({onboard_date.strftime('%Y-%m-%d')})")
                continue
            
            # 5. 其他剔除建议 (如: 1000SHIB, BTCDOM, DEFI 等特殊合约)
            # 这里先不剔除，只是列出供讨论
            # 但通常量化策略会剔除流动性极差的小币种，或者风险极高的 Meme (视策略而定)
            # 我们暂时保留所有，只做上述硬性剔除
            
            filtered_symbols.append(symbol_name)
            
        return filtered_symbols, excluded_stable, excluded_new

    except Exception as e:
        print(f"获取交易对列表失败: {e}")
        return [], [], []

def main():
    print("正在获取币安合约交易对信息...")
    symbols, stable, new_listings = get_all_usdt_perp_symbols()
    
    print(f"\n=== 筛选结果统计 ===")
    print(f"总符合条件的交易对数量: {len(symbols)}")
    print(f"剔除稳定币交易对 ({len(stable)}个): {stable}")
    print(f"剔除上线不足30天的新币 ({len(new_listings)}个): {new_listings}")
    
    # 保存列表到文件，供后续查看
    with open(SYMBOLS_FILE, "w") as f:
        for s in symbols:
            f.write(f"{s}\n")
            
    print("\n已将符合条件的交易对列表保存至 symbols_list.txt")
    
    # 打印前20个示例
    print(f"\n示例交易对 (前20个): {symbols[:20]}")

if __name__ == "__main__":
    main()
