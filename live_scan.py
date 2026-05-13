"""
quant_alpha v3.0 实时选股
找当前正在回踩、布林中轨附近的股票
"""
import os, sys, time, warnings, pandas as pd, numpy as np
sys.path.insert(0, os.path.dirname(__file__))
from utils.market_trend import get_market_trend, trend_adjust, format_trend_summary, INDEX_CODE_SH, INDEX_CODE_CYB
warnings.filterwarnings('ignore')

DATA_DIR = r'C:\Users\Razer\Desktop\quant_alpha\data\stocks'
LIST_FILE = r'C:\Users\Razer\Desktop\quant_alpha\stock_list_clean.csv'
OUTPUT = r'C:\Users\Razer\Desktop\quant_alpha\live_signals.csv'

LOOKBACK = 90
BB_TOLERANCE = 2.0
PULLBACK_MIN = 8.0
PULLBACK_MAX = 30.0
MA60_FLAT_MAX = 5.0
CONSOL_MIN = 15.0
CONSOL_MAX = 70.0
MIN_VOL_RATIO = 1.5

def load_kline(code):
    fp = os.path.join(DATA_DIR, f'{code}.csv')
    if not os.path.exists(fp):
        return None
    try:
        with open(fp, encoding='utf-8', errors='ignore') as f:
            first = f.readline().strip()
        import re
        if re.match(r'^\d{4}-\d{2}-\d{2},', first):
            cols = ['date', 'code', 'open', 'close', 'high', 'low', 'vol']
            df = pd.read_csv(fp, header=None, names=cols, encoding='utf-8', on_bad_lines='skip')
        else:
            df = pd.read_csv(fp, encoding='utf-8', on_bad_lines='skip')
            col_map = {'日期':'date','代码':'code','开盘':'open','收盘':'close',
                       '最高':'high','最低':'low','成交量':'vol','成交额':'amount','涨跌幅':'pct'}
            df.rename(columns={k:v for k,v in col_map.items() if k in df.columns}, inplace=True)
            keep = ['date','code','open','close','high','low','vol']
            df = df[[c for c in keep if c in df.columns]].copy()
        for c in ['close','high','low','vol']:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')
        df.dropna(subset=['close'], inplace=True)
        df.reset_index(drop=True, inplace=True)
        return df if len(df) > LOOKBACK else None
    except:
        return None

def analyze_stock(code, name):
    df = load_kline(code)
    if df is None or len(df) < LOOKBACK:
        return None

    df['MA20'] = df['close'].rolling(20).mean()
    df['MA60'] = df['close'].rolling(60).mean()
    df['BB_MID'] = df['MA20']

    # 最新N天横盘窗口检测
    results = []

    for start in range(max(60, len(df)-80), len(df)-5):
        window = df.iloc[start:start+LOOKBACK]
        if len(window) < 80:
            continue

        # MA60平坦度
        mf = window['MA60'].std() / window['MA60'].mean() * 100
        if mf > MA60_FLAT_MAX:
            continue

        # 横盘振幅
        low_min = window['low'].min()
        if low_min <= 0:
            continue
        cr = (window['high'].max() - low_min) / low_min * 100
        if not (CONSOL_MIN <= cr <= CONSOL_MAX):
            continue

        # 找突破点（窗口后半段）
        for j in range(start + LOOKBACK//2, start + LOOKBACK - 5):
            if j < 1 or j >= len(df)-3:
                continue
            prev = float(df.iloc[j-1]['close'])
            if prev <= 0:
                continue
            rise = (float(df.iloc[j]['high']) - prev) / prev * 100
            if rise < 5:
                continue

            avg_vol = window['vol'].tail(20).mean()
            vr = float(df.iloc[j]['vol']) / avg_vol if avg_vol > 0 else 1
            if vr < MIN_VOL_RATIO:
                continue

            # 回踩窗口（突破后）
            pb_win = df.iloc[j:min(j+25, len(df))]
            if len(pb_win) < 5:
                continue

            # 找最低点（用iloc，避免索引问题）
            pb_local = pb_win['low'].idxmin()
            pb_pos_in_win = pb_win.index.get_loc(pb_local)
            pb_price = float(pb_win.iloc[pb_pos_in_win]['low'])
            bk_high = float(df.iloc[j]['high'])
            pb_pct = (bk_high - pb_price) / bk_high * 100

            if not (PULLBACK_MIN <= pb_pct <= PULLBACK_MAX):
                continue

            bb_mid = float(pb_win.iloc[pb_pos_in_win]['BB_MID'])
            if bb_mid <= 0 or np.isnan(bb_mid):
                continue
            bb_dist = abs(pb_price - bb_mid) / bb_mid * 100
            if bb_dist > BB_TOLERANCE:
                continue

            # 当前状态评估
            last = df.iloc[-1]
            cur_price = float(last['close'])
            cur_bb_dist = abs(cur_price - bb_mid) / bb_mid * 100

            # 回踩确认后走了多少天（用iloc位置计算）
            pb_global_pos = df.index.get_loc(pb_local)
            days_since_pb = len(df) - pb_global_pos - 1

            # 当前价相对回踩低点的涨幅
            cur_from_pb = (cur_price - pb_price) / pb_price * 100

            # 突破后涨幅（当前相对突破点）
            bk_from_break = (cur_price - prev) / prev * 100

            # 形态评分
            score = 0
            if mf < 2: score += 20
            elif mf < 3.5: score += 15
            else: score += 10
            if 20 <= cr <= 40: score += 15
            elif CONSOL_MIN <= cr <= CONSOL_MAX: score += 10
            if pb_price >= bb_mid * 0.95: score += 15
            if vr >= 3: score += 15
            elif vr >= 2: score += 10
            elif vr >= 1.5: score += 5
            if bb_dist <= 1.0: score += 10
            score = min(100, score)

            # 资金分
            fund = 50
            if vr >= 5: fund += 25
            elif vr >= 3: fund += 18
            elif vr >= 2: fund += 12
            elif vr >= 1.5: fund += 6
            else: fund -= 8
            ret = df['close'].pct_change().fillna(0)
            obv = (ret.apply(lambda x: 1 if x > 0 else -1) * df['vol']).cumsum()
            if len(obv) >= 20:
                obv_t = (obv.iloc[-1] - obv.iloc[-20]) / max(1, abs(obv.iloc[-20])) * 100
                if obv_t > 30: fund += 20
                elif obv_t > 20: fund += 15
                elif obv_t > 10: fund += 10
                elif obv_t > 0: fund += 5
                else: fund -= 10
            flow5 = ret.tail(5).apply(lambda x: 1 if x > 0 else -1).sum()
            flow20 = ret.tail(20).apply(lambda x: 1 if x > 0 else -1).sum()
            if flow5 > 0 and flow5 > flow20 * 0.3: fund += 15
            elif flow5 > 0: fund += 8
            fund = max(0, min(100, fund))

            W_FUND = 0.7; W_PATTERN = 0.2; W_SENTIMENT = 0.1
            final = fund * W_FUND + score * W_PATTERN + 50 * W_SENTIMENT

            results.append({
                'code': code,
                'name': name,
                'final_score': round(final, 1),
                'pattern_score': score,
                'fund_score': fund,
                'bb_dist_at_pb': round(bb_dist, 2),
                'pullback_pct': round(pb_pct, 2),
                'ma60_flatness': round(mf, 2),
                'consolidation_range': round(cr, 2),
                'vol_ratio': round(vr, 2),
                'breakout_date': str(df.iloc[j]['date'])[:10],
                'pullback_date': str(pb_win.iloc[pb_pos_in_win]['date'])[:10],
                'pullback_price': round(pb_price, 2),
                'current_price': round(cur_price, 2),
                'cur_bb_dist': round(cur_bb_dist, 2),
                'cur_from_pb': round(cur_from_pb, 2),
                'days_since_pb': days_since_pb,
                'breakout_rise': round(bk_from_break, 2),
                'data_days': len(df),
            })
            break  # 只保留最匹配的横盘区间

    if not results:
        return None

    # 返回最佳信号
    return max(results, key=lambda x: x['final_score'])

def load_index_data():
    """加载指数数据"""
    indices = {}
    for code in [INDEX_CODE_SH, INDEX_CODE_CYB]:
        fp = os.path.join(DATA_DIR, f'{code}.csv')
        if os.path.exists(fp):
            try:
                df = pd.read_csv(fp, encoding='utf-8', on_bad_lines='skip')
                cm = {'日期':'date','收盘':'close','最高':'high','最低':'low','成交量':'vol','开盘':'open'}
                df.rename(columns={k:v for k,v in cm.items() if k in df.columns}, inplace=True)
                if 'close' in df.columns:
                    df['close'] = pd.to_numeric(df['close'], errors='coerce')
                    df.dropna(subset=['close'], inplace=True)
                    df.reset_index(drop=True, inplace=True)
                    indices[code] = df
            except:
                pass
    return indices


def main():
    t0 = time.time()
    print('============================================================')
    print('  quant_alpha v3.0 实时选股')
    print(f'  {time.strftime("%Y-%m-%d %H:%M:%S")}')
    print('============================================================')

    # 加载指数数据
    print('正在获取大盘趋势...')
    index_df = load_index_data()
    market = get_market_trend(DATA_DIR, index_df)
    trend_summary = format_trend_summary(market)
    print(f'  {trend_summary}')
    print()

    df_list = pd.read_csv(LIST_FILE, encoding='utf-8')
    # 检测列名
    if '代码' in df_list.columns:
        df_list.rename(columns={'代码':'code','名称':'name'}, inplace=True)
    if 'code' not in df_list.columns:
        df_list.columns = ['code','name'][:len(df_list.columns)]

    stocks = df_list[['code','name']].drop_duplicates()
    stocks = stocks[stocks['name'].str.contains('ST|\*', na=False) == False]
    print(f'股票列表: {len(stocks)} 只（已排除ST）')
    print()

    signals = []
    done = 0
    cache_hits = 0

    for idx, row in stocks.iterrows():
        code = str(row['code']).zfill(6)
        name = str(row['name'])
        result = analyze_stock(code, name)
        done += 1

        if result:
            signals.append(result)

        if done % 200 == 0:
            print(f'  进度: {done}/{len(stocks)} ({done/len(stocks)*100:.1f}%) | 当前命中: {len(signals)} | 缓存: {cache_hits}')

    print()
    print(f'扫描完成: {done}只 | 命中: {len(signals)}')
    print()

    if not signals:
        print('无信号')
        return

    sig_df = pd.DataFrame(signals)

    # 应用市场趋势调整
    trend_str = market['trend']
    sig_df['trend_adjusted'] = sig_df.apply(
        lambda r: trend_adjust(market, r['final_score'], r['pullback_pct']), axis=1
    )

    # 趋势差时提示过滤
    if trend_str == 'down':
        sig_df = sig_df[sig_df['trend_adjusted'] > 0]
        print(f'  [警告] 大盘趋势下跌，仅展示调整后评分>0的信号')
        print()

    # 优先推荐：回踩完成或接近完成（当前价贴近布林中轨）
    # 且回踩后涨幅不大（还没大涨）
    sig_df['rec_score'] = (
        sig_df['trend_adjusted'] * 0.4 +
        (100 - sig_df['cur_bb_dist'] * 10) * 0.3 +
        (30 - sig_df['cur_from_pb'].clip(0, 30)) * 0.3
    )

    sig_df = sig_df.sort_values('rec_score', ascending=False)

    print('推荐买入（按综合评分排序）：')
    print(f'{"代码":<8} {"名称":<10} {"评分":<6} {"调整分":<7} {"回踩深度":<8} {"当前偏离BB":<10} {"回踩后涨幅":<10} {"距回踩天数":<10}')
    print('-' * 95)
    for _, r in sig_df.iterrows():
        print(f'{r["code"]:<8} {r["name"]:<10} {r["final_score"]:<6.1f} '
              f'{r["trend_adjusted"]:<6.1f}  {r["pullback_pct"]:<7.1f}% {r["cur_bb_dist"]:<9.1f}% '
              f'{r["cur_from_pb"]:>+8.1f}% {r["days_since_pb"]:>6}天')

    sig_df.to_csv(OUTPUT, index=False, encoding='utf-8-sig')
    print()
    print(f'详细结果已保存: {OUTPUT}')
    print(f'耗时: {time.time()-t0:.1f}秒')

if __name__ == '__main__':
    main()
