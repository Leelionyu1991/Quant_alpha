"""
quant_alpha 最终选股模型 v3.0
整合布林中轨约束 + 资金优先 + 形态辅助

核心思路：
  布林中轨(MA20)±2% 是第一道门槛（必要条件）
  资金流向（0.7）是核心驱动
  形态质量（0.2）是辅助
  市场情绪（0.1）是参考
"""
import os, sys, pandas as pd, numpy as np
sys.path.insert(0, r'C:\Users\Razer\Desktop\quant_alpha')
from utils.data_fetcher import fetch_stock_history

BASE = r'C:\Users\Razer\Desktop\quant_alpha'
STOCK_DIR = os.path.join(BASE, 'data', 'stocks')

# ============================================================
# 参数配置
# ============================================================
# 布林中轨约束
BB_TOLERANCE = 2.0       # 回踩必须在MA20±2%以内（必要条件）
MA60_FLAT_MAX = 5.0      # MA60最大平坦度（%）
CONSOL_MIN = 15.0        # 横盘振幅下限（%）
CONSOL_MAX = 50.0        # 横盘振幅上限（%）
MIN_VOL_RATIO = 1.5      # 突破最低量比
PULLBACK_MAX = 35.0      # 最大回踩回落（%）

# 权重
W_FUND = 0.7
W_PATTERN = 0.2
W_SENTIMENT = 0.1

# 评分阈值
FUND_THRESHOLD = 75       # 资金分门槛
FINAL_THRESHOLD = 70      # 综合分门槛

# ============================================================
# 数据获取
# ============================================================
def load_kline_cache(code):
    """从本地缓存加载K线"""
    fp = os.path.join(STOCK_DIR, '{}.csv'.format(code))
    if not os.path.exists(fp):
        df = fetch_stock_history(code)
        if df is None:
            return None
        df = df.copy().reset_index(drop=True)
        if '日期' in df.columns:
            df.columns = ['date','open','close','high','low','vol'] + list(df.columns[6:])
        return df

    df = pd.read_csv(fp, header=None, encoding='utf-8')
    if df.shape[1] < 6:
        return None
    df.columns = ['date','code','open','close','high','low'] + ['c{}'.format(i) for i in range(df.shape[1]-6)]
    for col in ['close','high','low']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df['vol'] = pd.to_numeric(df.iloc[:,6], errors='coerce')
    df = df.dropna(subset=['close']).reset_index(drop=True)
    return df if len(df) > 100 else None

def get_sentiment():
    """市场情绪：基于指数趋势"""
    score = 50
    for idx in ['sh000001', 'sz399006']:
        df = fetch_stock_history(idx)
        if df is None:
            continue
        df = df.copy().reset_index(drop=True)
        if '收盘' in df.columns:
            df.columns = ['date','open','close','high','low','vol'] + list(df.columns[6:])
        if 'close' not in df.columns:
            continue
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df = df.dropna(subset=['close'])
        if len(df) < 5:
            continue
        closes = df['close'].tail(5).values
        trend = (closes[-1] - closes[0]) / closes[0] * 100
        if trend >= 2: score += 6
        elif trend >= 1: score += 4
        elif trend >= 0: score += 2
        elif trend >= -1: score -= 3
        else: score -= 8
    return max(0, min(100, score))

# ============================================================
# 形态检测
# ============================================================
def detect_vcb(df, lookback=90):
    """
    检测VCB形态（横盘-突破-回踩）
    返回：形态分、各项指标、是否满足布林中轨约束
    """
    if df is None or len(df) < lookback + 20:
        return None

    df = df.copy().reset_index(drop=True)
    for col in ['close','high','low','vol']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['close']).reset_index(drop=True)
    if len(df) < lookback + 20:
        return None

    df['MA20'] = df['close'].rolling(20).mean()
    df['MA60'] = df['close'].rolling(60).mean()

    # 找最近的横盘区间
    best_signal = None
    best_score = 0

    # 从最近的窗口开始扫描
    start = max(lookback, len(df) - 60)
    for i in range(start, len(df) - 10):
        window = df.iloc[i-lookback:i]
        if len(window) < 60:
            continue

        # 1. MA60平坦度
        mf = window['MA60'].std() / window['MA60'].mean() * 100
        if mf > MA60_FLAT_MAX:
            continue

        # 2. 横盘振幅
        cr = (window['high'].max() - window['low'].min()) / window['low'].min() * 100
        if not (CONSOL_MIN <= cr <= CONSOL_MAX):
            continue

        # 3. 找突破点
        found_breakout = False
        for j in range(max(0, i-30), i):
            if j < 1:
                continue
            prev_close = float(df.iloc[j-1]['close'])
            if prev_close <= 0:
                continue
            rise = (float(df.iloc[j]['high']) - prev_close) / prev_close * 100
            if rise < 5:
                continue

            found_breakout = True
            bk_idx = j
            bk_high = float(df.iloc[j]['high'])
            bk_date = str(df.iloc[j]['date'])[:10]
            bk_price = float(df.iloc[j]['close'])
            avg_vol = window['vol'].tail(20).mean()
            vr = float(df.iloc[j]['vol']) / avg_vol if avg_vol > 0 else 1

            # 4. 回踩
            pb_win = df.iloc[bk_idx:min(bk_idx+20, len(df))]
            if len(pb_win) < 3:
                continue
            pb_local_idx = pb_win['low'].idxmin()
            pb_idx = pb_local_idx
            pb_date = str(pb_win.loc[pb_idx, 'date'])[:10]
            pb_price = float(pb_win.loc[pb_idx, 'low'])
            pb_pct = (bk_high - pb_price) / bk_high * 100

            if pb_pct > PULLBACK_MAX:
                continue

            # 5. 【关键】布林中轨约束
            bb_mid = float(pb_win.loc[pb_idx, 'MA20'])
            if bb_mid <= 0 or pd.isna(bb_mid):
                continue
            bb_dist = abs(pb_price - bb_mid) / bb_mid * 100
            bb_ok = bb_dist <= BB_TOLERANCE

            # 6. MA20支撑
            ma20_at_pb = bb_mid
            above_ma20 = pb_price >= ma20_at_pb * 0.95

            # 计算形态分
            score = 0
            if mf < 2: score += 20
            elif mf < 3.5: score += 15
            elif mf < 5: score += 10

            if 20 <= cr <= 40: score += 15
            elif CONSOL_MIN <= cr <= CONSOL_MAX: score += 10

            if above_ma20: score += 15
            if vr >= 3: score += 15
            elif vr >= 2: score += 10
            elif vr >= 1.5: score += 5

            if bb_ok: score += 20  # BB中轨通过额外加分
            if bb_dist <= 1.0: score += 10  # 极度贴近再加

            if score > best_score:
                best_score = score
                best_signal = {
                    'detected': True,
                    'pattern_score': min(100, score),
                    'breakout_date': bk_date,
                    'breakout_price': round(bk_price, 3),
                    'breakout_high': round(bk_high, 3),
                    'pullback_date': pb_date,
                    'pullback_price': round(pb_price, 3),
                    'bb_mid': round(bb_mid, 3),
                    'bb_dist': round(bb_dist, 2),
                    'bb_ok': bb_ok,
                    'ma60_flatness': round(mf, 2),
                    'consolidation_range': round(cr, 2),
                    'pullback_pct': round(pb_pct, 2),
                    'above_ma20': above_ma20,
                    'vol_ratio': round(vr, 2),
                    'breakout_rise': round(rise, 2),
                }
            break  # 只找最近的一次突破

    return best_signal

# ============================================================
# 资金评分
# ============================================================
def score_fund(df):
    """从K线数据推导资金流向"""
    if df is None or len(df) < 30:
        return 50, {}

    df = df.copy().reset_index(drop=True)
    for col in ['close','high','low','vol']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['close']).reset_index(drop=True)
    if len(df) < 30:
        return 50, {}

    score = 50

    # 1. 量比
    vol_20avg = df['vol'].tail(20).mean()
    vol_today = df['vol'].iloc[-1]
    vr = vol_today / vol_20avg if vol_20avg > 0 else 1
    if vr >= 5: score += 25
    elif vr >= 3: score += 18
    elif vr >= 2: score += 12
    elif vr >= 1.5: score += 6
    elif vr >= 1: score += 2
    else: score -= 8

    # 2. OBV趋势（20日）
    ret = df['close'].pct_change().fillna(0)
    obv = (ret.apply(lambda x: 1 if x > 0 else -1) * df['vol']).cumsum()
    if len(obv) >= 20:
        obv_t = (obv.iloc[-1] - obv.iloc[-20]) / abs(obv.iloc[-20]) * 100
        if abs(obv_t) > 1e8: obv_t = 0
        if obv_t > 30: score += 20
        elif obv_t > 20: score += 15
        elif obv_t > 10: score += 10
        elif obv_t > 0: score += 5
        elif obv_t > -10: score -= 5
        else: score -= 15

    # 3. 5日净流量加速
    flow5 = ret.tail(5).apply(lambda x: 1 if x > 0 else -1).sum()
    flow20 = ret.tail(20).apply(lambda x: 1 if x > 0 else -1).sum()
    if flow5 > 0 and flow5 > flow20 * 0.3: score += 15
    elif flow5 > 0: score += 8
    elif flow5 < 0 and abs(flow5) > abs(flow20) * 0.5: score -= 15

    # 4. 当日资金方向
    today_dir = 1 if ret.iloc[-1] > 0 else -1
    today_net_ratio = today_dir * df['vol'].iloc[-1] / vol_20avg if vol_20avg > 0 else 0
    if today_dir > 0 and today_net_ratio > 0.5: score += 8
    elif today_dir < 0 and today_net_ratio < -0.5: score -= 8

    score = max(0, min(100, score))
    return score, {'vr': round(vr, 2), 'obv_t': round(obv_t, 1) if 'obv_t' in dir() else 0}

# ============================================================
# 形态评分（来自检测结果）
# ============================================================
def score_pattern(vcb_result):
    """基于VCB检测结果评分"""
    if vcb_result is None:
        return 50

    score = vcb_result['pattern_score'] if vcb_result.get('pattern_score', 0) > 0 else 50
    # BB通过额外加权
    if vcb_result.get('bb_ok', False):
        score = min(100, score + 10)
    return max(0, min(100, score))

# ============================================================
# 主扫描函数
# ============================================================
def scan_stocks():
    """扫描所有股票"""
    # 读取股票列表
    stock_list = pd.read_csv(os.path.join(BASE, 'stock_list_clean.csv'))
    stock_list['code'] = stock_list['code'].astype(str).str.zfill(6)
    print("Loaded {} stocks".format(len(stock_list)))

    # 市场情绪
    sent = get_sentiment()
    print("Market sentiment: {}".format(sent))

    results = []
    total = len(stock_list)

    print("\nScanning...")
    for i, row in stock_list.iterrows():
        code = row['code']
        name = str(row.get('name', code))
        mkt_cap = row.get('mkt_cap', 0)

        df = load_kline_cache(code)

        # 检测VCB形态
        vcb = detect_vcb(df)
        if vcb is None:
            continue

        # 【关键过滤】布林中轨约束
        if not vcb['bb_ok']:
            continue

        # 资金评分
        fund, fd = score_fund(df)

        # 形态评分
        pat = score_pattern(vcb)

        # 综合分
        final = fund * W_FUND + pat * W_PATTERN + sent * W_SENTIMENT
        final = round(min(100, max(0, final)), 1)

        # 过滤
        if fund < FUND_THRESHOLD:
            continue

        results.append({
            'code': code,
            'name': name,
            'mkt_cap': mkt_cap,
            # 形态
            'pattern_score': pat,
            'bb_ok': vcb['bb_ok'],
            'bb_dist': vcb['bb_dist'],
            'bb_mid': vcb['bb_mid'],
            'breakout_date': vcb['breakout_date'],
            'pullback_date': vcb['pullback_date'],
            'pullback_price': vcb['pullback_price'],
            'pullback_pct': vcb['pullback_pct'],
            'ma60_flatness': vcb['ma60_flatness'],
            'consolidation_range': vcb['consolidation_range'],
            'above_ma20': vcb['above_ma20'],
            'vol_ratio': vcb['vol_ratio'],
            'breakout_rise': vcb['breakout_rise'],
            # 资金
            'fund_score': fund,
            'vr': fd.get('vr', 0),
            # 综合
            'sentiment': sent,
            'final_score': final,
        })

        sys.stdout.write("\r  {}/{} {} {} bb={:.1f}% fund={} final={}".format(
            i+1, total, code, name[:4], vcb['bb_dist'], fund, final))
        sys.stdout.flush()

    print("\n\nScan complete: {} signals (BB passed)".format(len(results)))

    if results:
        df_out = pd.DataFrame(results).sort_values('final_score', ascending=False).reset_index(drop=True)
        df_out.to_csv(os.path.join(BASE, 'final_signals_v3.csv'), index=False, encoding='utf-8-sig')
        return df_out
    return pd.DataFrame()

# ============================================================
# 生成分析报告
# ============================================================
def generate_report(df):
    """生成最终分析报告"""
    if df.empty:
        print("No signals found!")
        return

    print("\n" + "=" * 70)
    print("quant_alpha 最终选股模型 v3.0 - 分析报告")
    print("=" * 70)

    print("""
【核心理念】
布林中轨(MA20)是股价的"引力线"，所有有效突破后的回踩
如果不落回中轨附近，说明突破虚假，后市大概率继续跌。
只有在布林中轨±2%内企稳的股票，才有高概率的二次拉升。

【模型公式】
最终分 = 资金分 × 0.7 + 形态分 × 0.2 + 情绪分 × 0.1

其中：
  资金分（70%）：量比 + OBV趋势 + 5日净流量加速
  形态分（20%）：VCB形态质量 + BB中轨校验
  情绪分（10%）：上证/创业板指数趋势

【布林中轨约束】
  回踩价格必须在 MA20 ± 2% 以内
  这是必要条件，不满足直接过滤
""")

    print("【扫描结果】")
    print("通过BB约束的股票: {}只".format(len(df)))
    print("资金分门槛: >={}".format(FUND_THRESHOLD))
    print("综合分门槛: >={}".format(FINAL_THRESHOLD))

    # 过滤最终名单
    final = df[df['final_score'] >= FINAL_THRESHOLD].copy()
    print("综合分>={}: {}只".format(FINAL_THRESHOLD, len(final)))

    # 分布
    print("\n【综合分分布】")
    for t in [80, 75, 70]:
        cnt = (df['final_score'] >= t).sum()
        print("  >= {}: {}只".format(t, cnt))

    # Top信号
    print("\n【Top20 信号】")
    top = df.head(20)
    cols = ['code','name','final_score','fund_score','pattern_score','bb_dist',
            'vr','pullback_pct','vol_ratio','consolidation_range']
    print(top[cols].to_string(index=False))

    # BB距离分析
    print("\n【BB距离分析】")
    print("BB通过股票的偏离分布:")
    for t in [0.5, 1.0, 1.5, 2.0]:
        cnt = (df['bb_dist'] <= t).sum()
        print("  <= {}%: {}只 ({:.0f}%)".format(t, cnt, 100*cnt/len(df)))

    # 按BB距离排序看质量
    print("\n【BB越近质量越高？】")
    df_near = df[df['bb_dist'] <= 1.0]
    df_far = df[(df['bb_dist'] > 1.0) & (df['bb_dist'] <= 2.0)]
    print("BB<=1%: {}只 均值资金={:.0f}".format(len(df_near), df_near['fund_score'].mean()))
    print("BB 1-2%: {}只 均值资金={:.0f}".format(len(df_far), df_far['fund_score'].mean()))

    # 形态参数统计
    print("\n【形态参数统计（BB通过的股票）】")
    print("  MA60平坦度: 均值={:.2f}% 中位数={:.2f}%".format(
        df['ma60_flatness'].mean(), df['ma60_flatness'].median()))
    print("  横盘振幅: 均值={:.1f}% 中位数={:.1f}%".format(
        df['consolidation_range'].mean(), df['consolidation_range'].median()))
    print("  回踩回落: 均值={:.1f}% 中位数={:.1f}%".format(
        df['pullback_pct'].mean(), df['pullback_pct'].median()))
    print("  量比: 均值={:.2f}x 中位数={:.2f}x".format(
        df['vol_ratio'].mean(), df['vol_ratio'].median()))
    print("  BB偏离: 均值={:.2f}% 中位数={:.2f}%".format(
        df['bb_dist'].mean(), df['bb_dist'].median()))

    # 保存最终名单
    if not final.empty:
        final.to_csv(os.path.join(BASE, 'final_watchlist_v3.csv'), index=False, encoding='utf-8-sig')
        print("\n最终观察名单: final_watchlist_v3.csv ({}只)".format(len(final)))
    else:
        print("\n无股票达到门槛（综合分<{})".format(FINAL_THRESHOLD))

    # 保存全部BB通过信号
    df.to_csv(os.path.join(BASE, 'final_signals_v3.csv'), index=False, encoding='utf-8-sig')
    print("全部BB通过信号: final_signals_v3.csv")
    print("\nDone!")


if __name__ == '__main__':
    results = scan_stocks()
    generate_report(results)
