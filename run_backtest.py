"""
历史回测：验证模型预测能力
"""
import os, sys, pandas as pd, numpy as np
sys.path.insert(0, r'C:\Users\Razer\Desktop\quant_alpha')
from utils.data_fetcher import fetch_stock_history

BASE_DIR = r'C:\Users\Razer\Desktop\quant_alpha'

def find_signals(df, code):
    """找所有历史VCB信号"""
    if df is None or len(df) < 150:
        return []
    df = df.copy().reset_index(drop=True)
    for col in ['收盘','最高','最低','成交量']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['收盘']).reset_index(drop=True)
    if len(df) < 150:
        return []

    df['MA20'] = df['收盘'].rolling(20).mean()
    df['MA60'] = df['收盘'].rolling(60).mean()

    signals = []
    for i in range(90, len(df) - 15):
        window = df.iloc[i-90:i]
        if len(window) < 70:
            continue

        # 横盘：MA60平坦度<5%
        ma60_flat = window['MA60'].std() / window['MA60'].mean() * 100 if window['MA60'].mean() > 0 else 999
        if ma60_flat > 5.0:
            continue

        # 突破：涨幅>=5%
        if i < 1:
            continue
        rise = (df.iloc[i]['最高'] - df.iloc[i-1]['收盘']) / df.iloc[i-1]['收盘'] * 100
        if rise < 5:
            continue

        breakout_date = df.iloc[i]['日期']
        breakout_high = df.iloc[i]['最高']
        consol_range = (window['最高'].max() - window['最低'].min()) / window['最低'].min() * 100

        # 回踩窗口
        pb_win = df.iloc[i:min(i+20, len(df))]
        if len(pb_win) < 3:
            continue
        pb_idx = pb_win['最低'].idxmin()
        pb_date = pb_win.loc[pb_idx, '日期']
        pb_price = pb_win.loc[pb_idx, '最低']
        pb_pct = (breakout_high - pb_price) / breakout_high * 100 if breakout_high > 0 else 999

        ma20_at_pb = pb_win.loc[pb_idx, 'MA20'] if not pd.isna(pb_win.loc[pb_idx, 'MA20']) else 0
        above_ma20 = pb_price >= ma20_at_pb * 0.95 if ma20_at_pb > 0 else False

        avg_vol = window['成交量'].tail(20).mean()
        vol_ratio = df.iloc[i]['成交量'] / avg_vol if avg_vol > 0 else 1

        # 后续涨幅（用于验证）
        post = df.iloc[pb_idx:min(pb_idx+30, len(df))]
        if len(post) >= 5:
            ret5 = (post['收盘'].iloc[4] - pb_price) / pb_price * 100
            ret10 = (post['收盘'].iloc[min(9, len(post)-1)] - pb_price) / pb_price * 100
            ret20 = (post['收盘'].iloc[min(19, len(post)-1)] - pb_price) / pb_price * 100
            max_high = post['最高'].max()
            ret_max = (max_high - pb_price) / pb_price * 100
        else:
            ret5 = ret10 = ret20 = ret_max = None

        signals.append({
            'code': code,
            'breakout_date': breakout_date,
            'pb_date': pb_date,
            'pb_price': pb_price,
            'breakout_high': breakout_high,
            'rise': rise,
            'pb_pct': pb_pct,
            'above_ma20': above_ma20,
            'vol_ratio': vol_ratio,
            'ma60_flat': ma60_flat,
            'consol_range': consol_range,
            'ret5': ret5,
            'ret10': ret10,
            'ret20': ret20,
            'ret_max': ret_max,
        })

    return signals


def score_at_pb(df, s):
    """在回踩日打分，只用历史数据"""
    if df is None:
        return 50, 50, {}

    # 历史数据截至回踩日
    df2 = df.copy().reset_index(drop=True)
    for col in ['收盘','最高','最低','成交量']:
        if col in df2.columns:
            df2[col] = pd.to_numeric(df2[col], errors='coerce')

    pb_date = s['pb_date']
    date_list = df2[df2['日期'] == pb_date].index.tolist()
    cutoff = date_list[0] if date_list else len(df2) - 1
    hist = df2.iloc[:cutoff+1]
    if len(hist) < 30:
        return 50, 50, {}

    fund = 50
    vol_20avg = hist['成交量'].tail(20).mean()
    vol_today = hist['成交量'].iloc[-1]
    vr = vol_today / vol_20avg if vol_20avg > 0 else 1
    if vr >= 5: fund += 25
    elif vr >= 3: fund += 18
    elif vr >= 2: fund += 12
    elif vr >= 1.5: fund += 6
    elif vr >= 1: fund += 2
    else: fund -= 8

    hist['ret'] = hist['收盘'].pct_change().fillna(0)
    hist['obv'] = (hist['ret'].apply(lambda x: 1 if x > 0 else -1) * hist['成交量']).cumsum()
    if len(hist) >= 20:
        obv_t = (hist['obv'].iloc[-1] - hist['obv'].iloc[-20]) / abs(hist['obv'].iloc[-20]) * 100 if hist['obv'].iloc[-20] != 0 else 0
        if obv_t > 30: fund += 20
        elif obv_t > 20: fund += 15
        elif obv_t > 10: fund += 10
        elif obv_t > 0: fund += 5
        elif obv_t > -10: fund -= 5
        else: fund -= 15

        flow5 = hist['ret'].apply(lambda x: 1 if x > 0 else -1).tail(5).sum()
        flow20 = hist['ret'].apply(lambda x: 1 if x > 0 else -1).tail(20).sum()
        if flow5 > 0 and flow5 > flow20 * 0.3: fund += 15
        elif flow5 > 0: fund += 8
        elif flow5 < 0 and abs(flow5) > abs(flow20) * 0.5: fund -= 15

    fund = max(0, min(100, fund))

    # 形态分（用信号本身的历史参数）
    pat = 50
    if s['ma60_flat'] < 2: pat += 15
    elif s['ma60_flat'] < 3.5: pat += 10
    elif s['ma60_flat'] < 5: pat += 5
    if 15 <= s['consol_range'] <= 50: pat += 10
    elif s['consol_range'] < 15: pat += 5
    if s['above_ma20']: pat += 10
    if s['vol_ratio'] >= 2: pat += 10
    elif s['vol_ratio'] >= 1.5: pat += 5
    pat = max(0, min(100, pat))

    return fund, pat, {'vr': round(vr, 2)}


print("=" * 60)
print("历史回测：验证模型预测能力")
print("=" * 60)

# 加载结果
results = pd.read_csv(os.path.join(BASE_DIR, 'results.csv'))
results['code'] = results['code'].astype(str).str.zfill(6)
print("Loaded {} stocks".format(len(results)))

all_signals = []

print("\nFinding historical signals...")
for _, row in results.iterrows():
    code = row['code']
    name = str(row.get('name', code))
    sys.stdout.write("  {} {}... ".format(code, name))
    sys.stdout.flush()

    df = fetch_stock_history(code)
    signals = find_signals(df, code)
    if not signals:
        print("no signal")
        continue

    # 匹配最接近的信号
    target_date = str(row.get('breakout_date', ''))[:10]
    best = None
    for s in signals:
        if s['breakout_date'][:10] == target_date:
            best = s
            break
    if not best:
        best = signals[-1]  # 取最后一次信号

    # 在回踩日打分
    fund, pat, fd = score_at_pb(df, best)
    sent = 50
    final = fund * 0.7 + pat * 0.2 + sent * 0.1
    final = round(min(100, max(0, final)), 1)

    best['fund_score'] = fund
    best['pat_score'] = pat
    best['final_score'] = final
    best['name'] = name
    best['vr'] = fd.get('vr', 0)

    all_signals.append(best)
    sys.stdout.write("OK fund={} pat={} final={}\n".format(fund, pat, final))
    sys.stdout.flush()

print("\nTotal signals: {}".format(len(all_signals)))

# 过滤有效数据
df_bt = pd.DataFrame([s for s in all_signals if s.get('ret20') is not None])
print("With future data: {}".format(len(df_bt)))

# ============================================================
# 分组统计
# ============================================================
print("\n" + "=" * 60)
print("回测结果")
print("=" * 60)

for period, col in [('5日', 'ret5'), ('10日', 'ret10'), ('20日', 'ret20')]:
    if col not in df_bt.columns:
        continue
    d = df_bt.dropna(subset=[col])
    if len(d) < 10:
        continue

    print("\n--- {}涨幅 vs 模型分 ---".format(period))
    for t in [80, 75, 70]:
        hi = d[d['final_score'] >= t][col]
        lo = d[d['final_score'] < t][col]
        if len(hi) >= 3 and len(lo) >= 3:
            print("  模型>={}: {}只 均值={:.1f}% 中位数={:.1f}%".format(t, len(hi), hi.mean(), hi.median()))
            print("  模型<{}: {}只 均值={:.1f}% 中位数={:.1f}%".format(t, len(lo), lo.mean(), lo.median()))
            n_win = sum(h > l for h, l in zip(hi.values, lo.values) if pd.notna(h) and pd.notna(l))
            n_tot = sum(pd.notna(h) and pd.notna(l) for h, l in zip(hi.values, lo.values))
            print("  胜率: {:.1f}%".format(n_win / n_tot * 100 if n_tot > 0 else 0))

    print("\n--- {}涨幅 vs 资金分 ---".format(period))
    for t in [90, 80, 70]:
        hi = d[d['fund_score'] >= t][col]
        lo = d[d['fund_score'] < t][col]
        if len(hi) >= 3 and len(lo) >= 3:
            print("  资金>={}: {}只 均值={:.1f}% 中位数={:.1f}%".format(t, len(hi), hi.mean(), hi.median()))
            print("  资金<{}: {}只 均值={:.1f}% 中位数={:.1f}%".format(t, len(lo), lo.mean(), lo.median()))
            n_win = sum(h > l for h, l in zip(hi.values, lo.values) if pd.notna(h) and pd.notna(l))
            n_tot = sum(pd.notna(h) and pd.notna(l) for h, l in zip(hi.values, lo.values))
            print("  胜率: {:.1f}%".format(n_win / n_tot * 100 if n_tot > 0 else 0))

    # 按十分位
    print("\n--- {}涨幅 vs 四分位 ---".format(period))
    d['q'] = pd.qcut(d['final_score'], q=4, labels=['Q1(低)', 'Q2', 'Q3', 'Q4(高)'], duplicates='drop')
    g = d.groupby('q', observed=True)[col].agg(['mean', 'median', 'count'])
    for q, row_data in g.iterrows():
        print("  {}: 均值={:.1f}% 中位数={:.1f}% n={}".format(
            q, row_data['mean'], row_data['median'], int(row_data['count'])))

    # 相关性
    corr = d[['final_score', col]].corr().iloc[0, 1]
    fund_corr = d[['fund_score', col]].corr().iloc[0, 1]
    print("  相关性: 模型分={:.3f} 资金分={:.3f}".format(corr, fund_corr))

# Top20 表现
print("\n--- Top20 模型分股票后续表现 ---")
top20 = df_bt.nlargest(20, 'final_score')
print(top20[['code','name','fund_score','pat_score','final_score','ret5','ret10','ret20']].to_string(index=False))

# 保存
df_bt.to_csv(os.path.join(BASE_DIR, 'backtest_results.csv'), index=False, encoding='utf-8-sig')
print("\nSaved to backtest_results.csv")
print("DONE")
