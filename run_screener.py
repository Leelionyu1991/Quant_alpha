import sys
import os
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.data_fetcher import get_stock_list_market_cap, fetch_stock_history
from strategies.volatility_contraction import analyze_stock

def run():
    print("--- Starting Quant Alpha Screener ---")
    
    # 1. Get stock list (Market Cap < 30B, No ST)
    stock_list = get_stock_list_market_cap(market_cap_limit=300 * 1e8)
    
    # We will test on the first 100 stocks to verify logic quickly
    test_list = stock_list.head(100)
    print(f"Testing on {len(test_list)} stocks out of {len(stock_list)}...")

    results = []

    for idx, row in test_list.iterrows():
        code = str(row['代码']).zfill(6)
        name = row['名称']
        
        # 2. Fetch data
        df = fetch_stock_history(code)
        if df is None:
            time.sleep(0.1)
            continue
            
        # 3. Analyze
        res = analyze_stock(df, code, name)
        if res:
            results.append(res)
            print(f"[HIT] {code} {name} at {res['breakout_date']}")
            
        time.sleep(0.1) # Be nice to the API

    print("\n--- Scan Complete ---")
    if len(results) == 0:
        print("No stocks matched the criteria in the tested subset.")
    else:
        for r in results:
            print(r)

if __name__ == "__main__":
    run()
