"""
quant_alpha 双窗口回测
- 前窗口（回踩日及之前）：验证形态选择策略
- 后窗口（回踩日之后）：验证上涨概率
"""
import sys, os, pandas as pd, numpy as np
sys.path.insert(0, r'C:\Users\Razer\Desktop\quant_alpha')
from utils.data_fetcher import fetch_stock_history

BASE = r'C:\Users\Razer\Desktop\quant_alpha'
STOCK_DIR = os.path.join(BASE, 'data', 'stocks')

# 读取通过BB约束的20只股票
df_signals = pd.read_csv(os.path.join(BASE, 'final_signals_v3.csv'))
df_signals['code'] = df_signals['code'].astype(str).str.zfill(6)
print("Loaded {} stocks from final_signals_v3.csv".format(len(df_signals)))
print(df_signals[['code','name','pullback_date','final_score']].to_string(index=False))

BB_TOL = 2.0
MA60_FLAT_MAX = 5.0

def load_kline(code):
    """加载K线数据（兼容不同格式）"""
    fp = os.path.join(STOCK_DIR, '{}.csv'.format(code))
    if not os.path.exists(fp):
        return None

    try:
        # 尝试无表头方式
        df = pd.read_csv(fp, header=None, encoding='utf-8')
    except:
        return None

    if df.shape[1] < 6:
        return None

    # 检测是否有表头（第一行是'日期'字符串）
    first_val = str(df.iloc[0, 0])
    if '日期' in first_val or 'date' in first_val.lower() or not any(c.isdigit() for c in first_val[:5]):
        df = df.iloc[1:].reset_index(drop=True)

    # 设置列名
    cols = ['date', 'code', 'open', 'close', 'high', 'low'] + ['c{}'.format(i) for i in range(df.shape[1]-6)]
    df.columns = cols[:df.shape[1]]

    for col in ['close', 'high', 'low']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    vol_col = df.columns[6] if len(df.columns) > 6 else 'close'
    df['vol'] = pd.to_numeric(df[vol_col], errors='coerce')
    df = df.dropna(subset=['close']).reset_index(drop=True)

    # 确保date列是字符串
    df['date'] = df['date'].astype(str)

    return df if len(df) > 100 else None

def find_signal_before_pb(df, pb_date_str):
    """
    回踩日及之前：用数据找回踩点之前最近的VCB信号
    只用回踩日及之前的数据
    """
    if df is None: return None
    df = df.copy().reset_index(drop=True)
    for col in ['close','high','low','vol']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['close']).reset_index(drop=True)

    df['MA20'] = df['close'].rolling(20).mean()
    df['MA60'] = df['close'].rolling(60).mean()

    # 找回踩日在K线中的位置
    pb_rows = df[df['date'].astype(str).str.contains(pb_date_str[:10], na=False)]
    if pb_rows.empty:
        return None
    pb_idx = pb_rows.index[0]

    # 用回踩日及之前的数据扫描VCB信号
    scan_end = pb_idx + 1  # 包含回踩日

    for i in range(90, scan_end):
        w = df.iloc[max(0, i-90):i]
        if len(w) < 60: continue

        mf = w['MA60'].std() / w['MA60'].mean() * 100 if w['MA60'].mean() > 0 else 999
        if mf > MA60_FLAT_MAX: continue

        cr = (w['high'].max() - w['low'].min()) / w['low'].min() * 100
        if not (15 <= cr <= 50): continue

        for j in range(max(0, i-30), i):
            if j < 1: continue
            prev = float(df.iloc[j-1]['close'])
            if prev <= 0: continue
            rise = (float(df.iloc[j]['high']) - prev) / prev * 100
            if rise < 5: continue

            avg_vol = w['vol'].tail(20).mean()
            vr = float(df.iloc[j]['vol']) / avg_vol if avg_vol > 0 else 1
            if vr < 1.5: continue

            bk_idx = j
            bk_high = float(df.iloc[j]['high'])

            # 回踩窗口
            pb_win = df.iloc[bk_idx:min(bk_idx+20, scan_end)]
            if len(pb_win) < 2: continue
            pb_local = pb_win['low'].idxmin()
            pb_price = float(pb_win.loc[pb_local, 'low'])
            pb_pct = (bk_high - pb_price) / bk_high * 100
            if not (10 <= pb_pct <= 30): continue

            bb_mid = float(pb_win.loc[pb_local, 'MA20'])
            if bb_mid <= 0 or pd.isna(bb_mid): continue
            bb_dist = abs(pb_price - bb_mid) / bb_mid * 100
            if bb_dist > BB_TOL: continue

            above_ma20 = pb_price >= bb_mid * 0.95

            # 在回踩日之前的资金分
            hist = df.iloc[:pb_local+1]
            fund, fd = calc_fund(hist)
            pat = calc_pat({'ma60_flatness': mf, 'consol_range': cr,
                            'above_ma20': above_ma20, 'vol_ratio': vr, 'bb_dist': bb_dist})

            return {
                'bk_date': str(df.iloc[bk_idx]['date'])[:10],
                'pb_date_actual': str(pb_win.loc[pb_local, 'date'])[:10],
                'pb_price': pb_price,
                'bk_high': bk_high,
                'bb_mid': bb_mid,
                'bb_dist': bb_dist,
                'ma60_flat': mf,
                'consol_range': cr,
                'pullback_pct': pb_pct,
                'above_ma20': above_ma20,
                'vol_ratio': vr,
                'fund_score': fund,
                'pat_score': pat,
                'final_score': round(fund*0.7 + pat*0.2 + 50*0.1, 1),
                'pb_idx': pb_local,
                'total_idx': pb_local,
            }
    return None

def calc_fund(df):
    """计算资金分（只用传入的历史数据）"""
    if df is None or len(df) < 30:
        return 50, {}
    df = df.copy().reset_index(drop=True)
    for col in ['close','vol']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['close']).reset_index(drop=True)
    if len(df) < 30:
        return 50, {}

    fund = 50
    vol_20avg = df['vol'].tail(20).mean()
    vol_today = df['vol'].iloc[-1]
    vr = vol_today / vol_20avg if vol_20avg > 0 else 1
    if vr >= 5: fund += 25
    elif vr >= 3: fund += 18
    elif vr >= 2: fund += 12
    elif vr >= 1.5: fund += 6
    elif vr >= 1: fund += 2
    else: fund -= 8

    ret = df['close'].pct_change().fillna(0)
    obv = (ret.apply(lambda x: 1 if x > 0 else -1) * df['vol']).cumsum()
    if len(obv) >= 20:
        obv_t = (obv.iloc[-1] - obv.iloc[-20]) / abs(obv.iloc[-20]) * 100
        if abs(obv_t) > 1e7: obv_t = 0
        if obv_t > 30: fund += 20
        elif obv_t > 20: fund += 15
        elif obv_t > 10: fund += 10
        elif obv_t > 0: fund += 5
        elif obv_t > -10: fund -= 5
        else: fund -= 15

    f5 = ret.tail(5).apply(lambda x: 1 if x > 0 else -1).sum()
    f20 = ret.tail(20).apply(lambda x: 1 if x > 0 else -1).sum()
    if f5 > 0 and f5 > f20 * 0.3: fund += 15
    elif f5 > 0: fund += 8
    elif f5 < 0 and abs(f5) > abs(f20) * 0.5: fund -= 15

    fund = max(0, min(100, fund))
    return fund, {'vr': round(vr, 2)}

def calc_pat(s):
    """计算形态分"""
    pat = 70
    if s['ma60_flatness'] < 2: pat += 15
    elif s['ma60_flatness'] < 3.5: pat += 10
    elif s['ma60_flatness'] < 5: pat += 5
    if s['consol_range'] and 20 <= s['consol_range'] <= 40: pat += 15
    elif s['consol_range'] and 15 <= s['consol_range'] <= 50: pat += 10
    if s['vol_ratio'] >= 2: pat += 10
    elif s['vol_ratio'] >= 1.5: pat += 5
    if s['above_ma20']: pat += 5
    if s['bb_dist'] <= 1.0: pat += 10
    return min(100, pat)

def get_post_returns(df, pb_idx):
    """计算回踩日之后的涨幅"""
    post = df.iloc[pb_idx:]
    if len(post) < 5:
        return {}
    entry = float(post['close'].iloc[0])
    returns = {}
    for n in [3, 5, 10, 20, 30]:
        if len(post) > n:
            future_close = float(post['close'].iloc[n])
            ret = (future_close - entry) / entry * 100
            returns['ret{}'.format(n)] = round(ret, 2)
    # 最大涨幅（之后30天内最高价）
    if len(post) >= 2:
        future_max = float(post['high'].iloc[1:].max())
        returns['ret_max'] = round((future_max - entry) / entry * 100, 2)
    return returns

# ============================================================
# 主回测
# ============================================================
print("\n" + "=" * 70)
print("双窗口回测")
print("=" * 70)

all_results = []

for _, row in df_signals.iterrows():
    code = row['code']
    name = str(row.get('name', code))
    pb_date = str(row.get('pullback_date', ''))[:10]

    df = load_kline(code)
    if df is None:
        print("  {} {} no data".format(code, name))
        continue

    # 用回踩日之前的数据找到信号
    sig = find_signal_before_pb(df, pb_date)
    if sig is None:
        print("  {} {} no signal found before {}".format(code, name, pb_date))
        continue

    # 计算回踩日之后的涨幅
    post_ret = get_post_returns(df, sig['pb_idx'])

    result = {
        'code': code, 'name': name,
        'pb_date': pb_date,
        'bk_date': sig['bk_date'],
        'fund_score': sig['fund_score'],
        'pat_score': sig['pat_score'],
        'final_score': sig['final_score'],
        'bb_dist': sig['bb_dist'],
        'pullback_pct': sig['pullback_pct'],
        'ma60_flat': sig['ma60_flat'],
        'consol_range': sig['consol_range'],
        'vol_ratio': sig['vol_ratio'],
        'above_ma20': sig['above_ma20'],
    }
    result.update(post_ret)
    all_results.append(result)

    ret_str = ' '.join(['{}={:.1f}%'.format(k, v) for k, v in post_ret.items()])
    print("  {} {} fund={} pat={} final={} pb={} bb={:.2f}% ret:{}".format(
        code, name[:4], sig['fund_score'], sig['pat_score'],
        sig['final_score'], pb_date, sig['bb_dist'], ret_str))

df_bt = pd.DataFrame(all_results)
print("\nTotal: {} signals".format(len(df_bt)))

# ============================================================
# 前窗口验证：形态识别的准确性
# ============================================================
print("\n" + "=" * 70)
print("【前窗口验证】形态识别：回踩日及之前的形态质量")
print("=" * 70)

print("\n--- 形态参数分布 ---")
for col in ['bb_dist', 'pullback_pct', 'ma60_flat', 'consol_range', 'vol_ratio']:
    print("  {}: 均值={:.2f} 中位数={:.2f} min={:.2f} max={:.2f}".format(
        col, df_bt[col].mean(), df_bt[col].median(), df_bt[col].min(), df_bt[col].max()))

# BB距离分布
print("\n--- BB距离分布 ---")
for t in [0.5, 1.0, 1.5, 2.0]:
    cnt = (df_bt['bb_dist'] <= t).sum()
    print("  <= {}%: {}只 ({:.0f}%)".format(t, cnt, 100*cnt/len(df_bt)))

# 回踩幅度分布
print("\n--- 回踩幅度分布 ---")
for t in [8, 10, 12, 15, 18, 20, 25]:
    cnt = (df_bt['pullback_pct'] >= t).sum()
    print("  >= {}%: {}只 ({:.0f}%)".format(t, cnt, 100*cnt/len(df_bt)))

# MA60平坦度分布
print("\n--- MA60平坦度分布 ---")
for t in [1, 2, 3, 4, 5]:
    cnt = (df_bt['ma60_flat'] <= t).sum()
    print("  <= {}%: {}只 ({:.0f}%)".format(t, cnt, 100*cnt/len(df_bt)))

# ============================================================
# 后窗口验证：上涨概率
# ============================================================
print("\n" + "=" * 70)
print("【后窗口验证】上涨概率：回踩日之后的收益")
print("=" * 70)

# 各周期收益统计
for period, col in [('3日', 'ret3'), ('5日', 'ret5'), ('10日', 'ret10'),
                     ('20日', 'ret20'), ('30日', 'ret30'), ('最大', 'ret_max')]:
    vals = df_bt[col].dropna()
    if len(vals) == 0:
        continue
    win_rate = (vals > 0).mean() * 100
    big_win = (vals > 5).mean() * 100
    print("\n--- {}涨幅 ---".format(period))
    print("  样本: {}只".format(len(vals)))
    print("  均值: {:+.2f}%".format(vals.mean()))
    print("  中位数: {:+.2f}%".format(vals.median()))
    print("  标准差: {:.2f}%".format(vals.std()))
    print("  盈利比例: {:.0f}%".format(win_rate))
    print("  大涨(>5%)比例: {:.0f}%".format(big_win))
    print("  最小: {:+.2f}% | 最大: {:+.2f}%".format(vals.min(), vals.max()))

# ============================================================
# 核心验证：高分股票 vs 低分股票
# ============================================================
print("\n" + "=" * 70)
print("【核心验证】模型分 vs 后续涨幅")
print("=" * 70)

# 按资金分分组
for t in [90, 80, 70]:
    hi = df_bt[df_bt['fund_score'] >= t]
    lo = df_bt[df_bt['fund_score'] < t]
    if len(hi) >= 2 and len(lo) >= 2:
        print("\n--- 资金分>={} vs <{} ---".format(t, t))
        print("  高分组: {}只 均值资金={:.0f}".format(len(hi), hi['fund_score'].mean()))
        for col, name in [('ret5','5日'), ('ret10','10日'), ('ret20','20日'), ('ret_max','最大')]:
            hv = hi[col].dropna()
            lv = lo[col].dropna()
            if len(hv) > 0 and len(lv) > 0:
                wr = (hv > lv).mean() * 100
                print("  {}: 高分={:+.1f}% 低分={:+.1f}% 胜率={:.0f}%".format(
                    name, hv.mean(), lv.mean(), wr))

# 按综合分分组
for t in [85, 80, 75]:
    hi = df_bt[df_bt['final_score'] >= t]
    lo = df_bt[df_bt['final_score'] < t]
    if len(hi) >= 2 and len(lo) >= 2:
        print("\n--- 综合分>={} vs <{} ---".format(t, t))
        print("  高分组: {}只".format(len(hi)))
        for col, name in [('ret5','5日'), ('ret10','10日'), ('ret20','20日'), ('ret_max','最大')]:
            hv = hi[col].dropna()
            lv = lo[col].dropna()
            if len(hv) > 0 and len(lv) > 0:
                wr = (hv > lv).mean() * 100
                print("  {}: 高分={:+.1f}% 低分={:+.1f}% 胜率={:.0f}%".format(
                    name, hv.mean(), lv.mean(), wr))

# 四分位分组
print("\n--- 综合分四分位 ---")
for col, name in [('ret5','5日'), ('ret10','10日'), ('ret20','20日'), ('ret_max','最大')]:
    d = df_bt.dropna(subset=[col]).copy()
    if len(d) < 4: continue
    try:
        d['q'] = pd.qcut(d['final_score'], q=4, labels=['Q1(低)', 'Q2', 'Q3', 'Q4(高)'], duplicates='drop')
        g = d.groupby('q', observed=True)[col].agg(['mean', 'median', 'count'])
        print("\n  {}涨幅:".format(name))
        for q, r in g.iterrows():
            print("    {}: 均值={:+.1f}% 中位数={:+.1f}% n={}".format(
                q, r['mean'], r['median'], int(r['count'])))
    except:
        pass

# ============================================================
# 详细列表
# ============================================================
print("\n" + "=" * 70)
print("【详细数据】所有信号及后续涨幅")
print("=" * 70)
cols = ['code','name','final_score','fund_score','pat_score','bb_dist',
        'pullback_pct','vol_ratio','ret3','ret5','ret10','ret20','ret_max']
available = [c for c in cols if c in df_bt.columns]
print(df_bt[available].sort_values('final_score', ascending=False).to_string(index=False))

# 保存
df_bt.to_csv(os.path.join(BASE, 'backtest_v3.csv'), index=False, encoding='utf-8-sig')
print("\n\nSaved: backtest_v3.csv")
print("Done!")
