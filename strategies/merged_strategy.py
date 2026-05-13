"""
Merged Strategy: Volatility Contraction Breakout + MA Bullish Golden Cross
Phase 1-3: Original VCB logic (120-day window)
Phase 4:   Additional golden cross / bullish MA tags (not required, just scored)
"""
import pandas as pd
import numpy as np

MKTCAP_LIMIT = 150
MIN_RISE = 5.0
MAX_PULLBACK = 2.0
MA_SHORT = 10
MA_MID = 20
MA_LONG = 60
WINDOW = 120
MA60_FLAT_TOL = 0.05
MIN_CROSSINGS = 2


def calc_ma(series, period):
    return series.rolling(period).mean()


def count_crossings(s1, s2):
    diff = s1 - s2
    sign_change = np.diff(np.sign(diff.dropna()))
    return np.sum(sign_change != 0)


def analyze_stock(df: pd.DataFrame, code: str, name: str, mktcap_yi: float = 0) -> dict or None:
    if len(df) < WINDOW:
        return None

    cc = '\u6536\u76d8' if '\u6536\u76d8' in df.columns else 'close'
    hc = '\u6700\u9ad8' if '\u6700\u9ad8' in df.columns else 'high'
    lc = '\u6700\u4f4e' if '\u6700\u4f4e' in df.columns else 'low'
    dc = '\u65e5\u671f' if '\u65e5\u671f' in df.columns else 'date'
    pc = '\u6da8\u8dcc\u5e45' if '\u6da8\u8dcc\u5e45' in df.columns else 'pct_chg'

    df = df.tail(WINDOW).copy()
    df.reset_index(drop=True, inplace=True)

    df['MA5'] = calc_ma(df[cc], 5)
    df['MA10'] = calc_ma(df[cc], MA_SHORT)
    df['MA20'] = calc_ma(df[cc], MA_MID)
    df['MA60'] = calc_ma(df[cc], MA_LONG)
    df['BOLL_MID'] = df['MA20']

    if df['MA60'].isna().sum() > 65:
        return None

    if pc in df.columns:
        df['pct_chg'] = pd.to_numeric(df[pc], errors='coerce')
    else:
        df['pct_chg'] = df[cc].pct_change() * 100

    # === Phase 1: Consolidation (rows 60-90) ===
    phase1 = df.iloc[60:90]
    if len(phase1) < 20:
        return None

    ma60_max = phase1['MA60'].max()
    ma60_min = phase1['MA60'].min()
    if pd.isna(ma60_max) or pd.isna(ma60_min) or ma60_min == 0:
        return None
    if (ma60_max - ma60_min) / ma60_min > MA60_FLAT_TOL:
        return None

    crossings = count_crossings(phase1['MA5'], phase1['MA20'])
    if crossings < MIN_CROSSINGS:
        return None

    # === Phase 2: Breakout detection (rows 90-120) ===
    best_signal = None

    for i in range(90, WINDOW):
        if pd.isna(df.loc[i, 'pct_chg']) or df.loc[i, 'pct_chg'] <= MIN_RISE:
            continue

        prev = i - 1
        low_prev = df.loc[prev, lc]
        close_prev = df.loc[prev, cc]
        mid_prev = df.loc[prev, 'BOLL_MID']

        if pd.isna(mid_prev) or mid_prev == 0:
            continue

        # Shake-out: previous day low touches MA20, close stays above
        pullback_to_mid = (low_prev <= mid_prev * 1.015) and (close_prev >= mid_prev * 0.985)

        # MA5 > MA20 on breakout day
        if pd.isna(df.loc[i, 'MA5']) or pd.isna(df.loc[i, 'MA20']):
            continue
        ma5_above_ma20 = df.loc[i, 'MA5'] > df.loc[i, 'MA20']

        close_i = df.loc[i, cc]
        high_i = df.loc[i, hc]
        prev_close = df.loc[prev, cc]
        if pd.isna(prev_close) or prev_close == 0 or pd.isna(high_i) or high_i == 0:
            continue

        rise_pct = df.loc[i, 'pct_chg']
        max_rise_pct = (high_i - prev_close) / prev_close * 100
        pullback_pct = (high_i - close_i) / high_i * 100

        # Post-breakout confirmation
        status = 'FRESH_BREAKOUT'
        if i < WINDOW - 1:
            after = df.loc[i + 1:]
            min_after = after[lc].min()
            if pd.isna(min_after) or min_after < close_i * 0.98:
                continue
            status = 'CONFIRMED'

        # === Phase 3: Extra scoring (golden cross, bullish MA) ===
        bullish_ma = False
        if not pd.isna(df.loc[i, 'MA10']) and not pd.isna(df.loc[i, 'MA20']) and not pd.isna(df.loc[i, 'MA60']):
            bullish_ma = (df.loc[i, 'MA10'] > df.loc[i, 'MA20']) and (df.loc[i, 'MA20'] > df.loc[i, 'MA60'])

        cross_type = 'none'
        if i >= 2:
            a5t = df.loc[i, 'MA5']
            a10t = df.loc[i, 'MA10']
            a5y = df.loc[i - 1, 'MA5']
            a10y = df.loc[i - 1, 'MA10']
            if not any(pd.isna(x) for x in [a5t, a10t, a5y, a10y]):
                if (a5y <= a10y) and (a5t > a10t):
                    cross_type = 'cross10'
                    a20t = df.loc[i, 'MA20']
                    a20y = df.loc[i - 1, 'MA20']
                    if not pd.isna(a20t) and not pd.isna(a20y):
                        if (a5y <= a20y) and (a5t > a20t):
                            cross_type = 'dual'

        # Score
        score = 0
        if pullback_to_mid:
            score += 2
        if ma5_above_ma20:
            score += 1
        if bullish_ma:
            score += 2
        if cross_type == 'dual':
            score += 3
        elif cross_type == 'cross10':
            score += 2
        if pullback_pct < MAX_PULLBACK:
            score += 1
        if 0 < mktcap_yi <= MKTCAP_LIMIT:
            score += 1

        signal = {
            'code': code,
            'name': name,
            'breakout_date': str(df.loc[i, dc]),
            'breakout_close': float(close_i),
            'rise_pct': round(float(rise_pct), 2),
            'max_rise_pct': round(float(max_rise_pct), 2),
            'pullback_pct': round(float(pullback_pct), 2),
            'status': status,
            'consolidation': True,
            'pullback_to_mid': pullback_to_mid,
            'bullish_ma': bullish_ma,
            'cross_type': cross_type,
            'score': score,
            'mktcap_yi': mktcap_yi,
        }

        if best_signal is None or score > best_signal['score']:
            best_signal = signal

    return best_signal


def backtest_stock(df: pd.DataFrame, code: str, name: str, mktcap_yi: float = 0):
    cc = '\u6536\u76d8' if '\u6536\u76d8' in df.columns else 'close'
    hc = '\u6700\u9ad8' if '\u6700\u9ad8' in df.columns else 'high'
    lc = '\u6700\u4f4e' if '\u6700\u4f4e' in df.columns else 'low'
    dc = '\u65e5\u671f' if '\u65e5\u671f' in df.columns else 'date'

    need = MA_LONG + 20
    if len(df) < need + WINDOW + 10:
        return []

    all_signals = []
    step = 5

    for anchor in range(need, len(df) - 10, step):
        sub = df.iloc[anchor:anchor + WINDOW].copy()
        if len(sub) < WINDOW:
            continue
        sub.reset_index(drop=True, inplace=True)

        res = analyze_stock(sub, code, name, mktcap_yi)
        if res is None:
            continue

        trig_date = res['breakout_date']
        trig_close = res['breakout_close']

        for idx in range(anchor, min(anchor + WINDOW + 10, len(df))):
            if str(df.iloc[idx][dc]) == trig_date:
                for d in range(1, 11):
                    fi = idx + d
                    if fi >= len(df):
                        break
                    fc = float(df.iloc[fi][cc])
                    if pd.isna(fc):
                        break
                    ret = (fc - trig_close) / trig_close * 100
                    res[f't{d}'] = round(ret, 2)
                all_signals.append(dict(res))
                break

    return all_signals
