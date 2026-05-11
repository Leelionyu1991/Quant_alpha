"""
Strategy: Structural Breakout after Volatility Contraction
"""
import pandas as pd
import numpy as np

def analyze_stock(df: pd.DataFrame, code: str, name: str) -> dict:
    """
    Analyzes a single stock's dataframe for the strategy conditions.
    """
    if len(df) < 120:
        return None

    # Use the last 120 days
    df = df.tail(120).copy()
    df.reset_index(drop=True, inplace=True)

    # 1. Moving Averages & Bollinger Mid Band
    df['MA5'] = df['收盘'].rolling(5).mean()
    df['MA20'] = df['收盘'].rolling(20).mean()
    df['MA60'] = df['收盘'].rolling(60).mean()
    df['BOLL_MID'] = df['MA20']

    if df['MA60'].isna().sum() > 65:
        return None

    # ==========================================
    # Phase 1: Volatility Contraction (First 90 days, roughly 3/4)
    # 1. 60-day MA is flat (max/min diff <= 5%)
    # 2. 5-day and 20-day MA cross multiple times (chop/consolidation)
    # ==========================================
    phase1 = df.iloc[60:90]
    if len(phase1) < 20: return None

    ma60_max = phase1['MA60'].max()
    ma60_min = phase1['MA60'].min()
    if ma60_min == 0 or (ma60_max - ma60_min) / ma60_min > 0.05: # Changed back to 5% per your request
        return None

    phase1_ma_diff = phase1['MA5'] - phase1['MA20']
    crossings = np.sum(np.diff(np.sign(phase1_ma_diff.dropna())) != 0)
    if crossings < 2:
        return None

    # ==========================================
    # Phase 2: The Setup & Breakout (Last 30 days, roughly 1/4)
    # ==========================================
    phase2_start_idx = 90
    df['pct_chg'] = df['收盘'].pct_change() * 100

    for i in range(phase2_start_idx, 120):
        # The Breakout: Gain > 5%
        if df.loc[i, 'pct_chg'] > 5.0:
            prev_day = i - 1
            low_prev = df.loc[prev_day, '最低']
            close_prev = df.loc[prev_day, '收盘']
            mid_prev = df.loc[prev_day, 'BOLL_MID']

            # The Shake-out: Pullback to Bollinger Mid (MA20) on the day BEFORE breakout
            # Low price touches/goes under mid, but close stays near or above
            is_pullback = (low_prev <= mid_prev * 1.015) and (close_prev >= mid_prev * 0.985)

            if is_pullback:
                # The Trend: Bulls in control (MA5 > MA20) on breakout day
                if df.loc[i, 'MA5'] < df.loc[i, 'MA20']:
                    continue

                # The Confirmation: Pullback post-breakout is < 2%
                breakout_close = df.loc[i, '收盘']
                breakout_date = df.loc[i, '日期']

                if i < 119: # Breakout was not today
                    after_breakout = df.loc[i+1:]
                    min_after = after_breakout['最低'].min()

                    if min_after >= breakout_close * 0.98:
                        return {
                            "code": code,
                            "name": name,
                            "breakout_date": breakout_date,
                            "breakout_close": breakout_close,
                            "status": "CONFIRMED"
                        }
                else:
                    # Breakout is exactly today
                    return {
                        "code": code,
                        "name": name,
                        "breakout_date": breakout_date,
                        "breakout_close": breakout_close,
                        "status": "FRESH_BREAKOUT"
                    }
    return None
