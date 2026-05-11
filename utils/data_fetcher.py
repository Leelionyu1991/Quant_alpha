"""
Data Fetcher Utility
Downloads and caches historical stock data from akshare.
"""
import akshare as ak
import pandas as pd
import os
import time

DATA_DIR = "data/stocks"

def ensure_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def fetch_stock_history(code: str, days: int = 250) -> pd.DataFrame or None:
    """
    Fetches stock history for a given code.
    Returns DataFrame or None if failed.
    """
    ensure_dir()
    file_path = os.path.join(DATA_DIR, f"{code}.csv")

    # Simple cache check (only if file exists and is less than 1 day old for production)
    # For now, we always fetch fresh to ensure we have the latest data
    try:
        df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
        if df is not None and len(df) > 0:
            df.to_csv(file_path, index=False)
            return df
    except Exception as e:
        print(f"Failed to fetch {code}: {e}")
    return None

def get_stock_list_market_cap(market_cap_limit=300*1e8):
    """
    Gets the list of all A-shares with market cap under the limit.
    """
    print("Fetching stock list...")
    df = ak.stock_zh_a_spot_em()
    # Filter by market cap and remove ST
    df = df[df['总市值'] <= market_cap_limit]
    df = df[~df['名称'].str.contains('ST', na=False)]
    return df[['代码', '名称', '总市值']]

if __name__ == "__main__":
    # Test fetch
    df = fetch_stock_history("000001")
    if df is not None:
        print(df.tail())
