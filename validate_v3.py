"""
quant_alpha 策略v3.0 扩展验证脚本
1. 扫描全量股票 (4841只)
2. 形态匹配 + 二次拉升验证
3. 输出统计报告
"""
import os, sys, time, warnings, pandas as pd, numpy as np
warnings.filterwarnings('ignore')
from datetime import datetime

sys.path.insert(0, r'C:\Users\Razer\Desktop\quant_alpha')
from utils.data_fetcher import fetch_stock_history

BASE = r'C:\Users\Razer\Desktop\quant_alpha'
DATA_DIR = os.path.join(BASE, 'data', 'stocks')

# ========================
# 策略参数（与model_v3.py一致）
# ========================
BB_TOLERANCE = 2.0
MA60_FLAT_MAX = 5.0
CONSOL_MIN = 15.0
CONSOL_MAX = 70.0   # 放宽到70（原50）
MIN_VOL_RATIO = 1.5
PULLBACK_MIN = 10.0
PULLBACK_MAX = 35.0
LOOKBACK = 90
W_FUND, W_PATTERN, W_SENTIMENT = 0.7, 0.2, 0.1

# ========================
# K线加载
# ========================
def load_kline(code):
    fp = os.path.join(DATA_DIR, f'{code}.csv')
    if os.path.exists(fp):
        try:
            # 先读第一行判断格式
            with open(fp, encoding='utf-8', errors='ignore') as f:
                first = f.readline().strip()

            import re
            if re.match(r'^\d{4}-\d{2}-\d{2},', first):
                # 无表头格式
                cols = ['日期', '代码', '开盘', '收盘', '最高', '最低', '成交量', '成交额', '涨跌幅']
                df = pd.read_csv(fp, header=None, names=cols, encoding='utf-8', on_bad_lines='skip')
            else:
                # 有表头（中文列名）
                df = pd.read_csv(fp, encoding='utf-8', on_bad_lines='skip')

            # 统一列名
            col_map = {
                '日期': 'date', '开盘': 'open', '收盘': 'close', '最高': 'high',
                '最低': 'low', '成交量': 'vol', '成交额': 'amount', '涨跌幅': 'pct'
            }
            df.rename(columns=col_map, inplace=True)
            keep = ['date', 'open', 'close', 'high', 'low', 'vol']
            df = df[[c for c in keep if c in df.columns]].copy()
            for c in ['close', 'high', 'low', 'vol']:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors='coerce')
            df.dropna(subset=['close'], inplace=True)
            df.reset_index(drop=True, inplace=True)
            return df if len(df) > LOOKBACK + 30 else None
        except Exception as e:
            return None
    return None

# ========================
# VCB形态检测 + 二次拉升验证
# ========================
def detect_and_validate(df, code, name):
    """
    检测VCB形态，然后验证回踩后的二次拉升
    返回：(信号dict, 回测结果dict)
    """
    df = df.copy().reset_index(drop=True)
    for col in ['close', 'high', 'low', 'vol']:
        c = col if col in df.columns else col.title()
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.dropna(subset=['close']).reset_index(drop=True)
    if len(df) < LOOKBACK + 30:
        return None, None

    df['MA20'] = df['close'].rolling(20).mean()
    df['MA60'] = df['close'].rolling(60).mean()

    # 扫描横盘区间
    start = max(LOOKBACK, len(df) - 60)
    best = None
    best_score = 0

    for i in range(start, len(df) - 10):
        window = df.iloc[i-LOOKBACK:i]
        if len(window) < 60:
            continue

        mf = window['MA60'].std() / window['MA60'].mean() * 100
        if mf > MA60_FLAT_MAX:
            continue

        low_min = window['low'].min()
        if low_min <= 0:
            continue
        cr = (window['high'].max() - low_min) / low_min * 100
        if not (CONSOL_MIN <= cr <= CONSOL_MAX):
            continue

        # 找突破点
        for j in range(max(0, i-30), i):
            if j < 1:
                continue
            prev_close = float(df.iloc[j-1]['close'])
            if prev_close <= 0:
                continue
            rise = (float(df.iloc[j]['high']) - prev_close) / prev_close * 100
            if rise < 5:
                continue

            avg_vol = window['vol'].tail(20).mean()
            vr = float(df.iloc[j]['vol']) / avg_vol if avg_vol > 0 else 1
            if vr < MIN_VOL_RATIO:
                continue

            # 回踩窗口
            pb_win = df.iloc[j:min(j+20, len(df))]
            if len(pb_win) < 3:
                continue
            pb_idx = pb_win['low'].idxmin()
            pb_price = float(pb_win.loc[pb_idx, 'low'])
            pb_date = str(pb_win.loc[pb_idx, 'date'])[:10]
            bk_high = float(df.iloc[j]['high'])
            pb_pct = (bk_high - pb_price) / bk_high * 100

            if not (PULLBACK_MIN <= pb_pct <= PULLBACK_MAX):
                continue

            # 布林中轨约束
            bb_mid = float(pb_win.loc[pb_idx, 'MA20'])
            if bb_mid <= 0 or pd.isna(bb_mid):
                continue
            bb_dist = abs(pb_price - bb_mid) / bb_mid * 100
            if bb_dist > BB_TOLERANCE:
                continue

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
            final = fund * W_FUND + score * W_PATTERN + 50 * W_SENTIMENT

            # ===== 二次拉升验证（关键）=====
            # 回踩确认点之后，N日内涨幅
            post_pb = df.iloc[pb_idx:].reset_index(drop=True)
            if len(post_pb) < 10:
                post_results = {}
            else:
                post_results = {}
                for n in [3, 5, 10, 15, 20]:
                    if len(post_pb) > n:
                        entry = float(post_pb.iloc[0]['close'])
                        future_max = float(post_pb.iloc[1:n+1]['high'].max())
                        future_close = float(post_pb.iloc[n]['close'])
                        max_ret = (future_max - entry) / entry * 100
                        close_ret = (future_close - entry) / entry * 100
                        post_results[f'max_{n}d'] = round(max_ret, 2)
                        post_results[f'close_{n}d'] = round(close_ret, 2)

            signal = {
                'code': code,
                'name': name,
                'pattern_score': score,
                'fund_score': fund,
                'final_score': round(final, 1),
                'bb_dist': round(bb_dist, 2),
                'bb_ok': bb_dist <= BB_TOLERANCE,
                'breakout_date': str(df.iloc[j]['date'])[:10],
                'pullback_date': pb_date,
                'pullback_price': round(pb_price, 2),
                'pullback_pct': round(pb_pct, 2),
                'ma60_flatness': round(mf, 2),
                'consolidation_range': round(cr, 2),
                'vol_ratio': round(vr, 2),
                'breakout_rise': round(rise, 2),
                'data_days': len(df),
            }

            if post_results:
                signal.update(post_results)

            if final > best_score:
                best_score = final
                best = signal
            break

    return best, None


# ========================
# 主扫描
# ========================
def run_full_scan():
    print("=" * 60)
    print("  quant_alpha v3.0 全量扫描 + 二次拉升验证")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    stocks = pd.read_csv(os.path.join(BASE, 'stock_list_clean.csv'))
    code_col = next((c for c in stocks.columns if c in ('code', '代码')), stocks.columns[0])
    name_col = next((c for c in stocks.columns if c in ('name', '名称')), stocks.columns[1])
    stocks['code'] = stocks[code_col].astype(str).str.zfill(6)
    stocks['name'] = stocks[name_col].astype(str)
    print(f"股票列表: {len(stocks)} 只")

    all_signals = []
    cache_hits = 0
    cache_miss = 0
    scan_start = time.time()

    for idx, row in stocks.iterrows():
        code = row['code']
        name = str(row.get(name_col, code))

        df = load_kline(code)
        if df is not None:
            cache_hits += 1
        else:
            cache_miss += 1
            raw = fetch_stock_history(code)
            if raw is None:
                continue
            # 统一成英文列名
            cm = {'日期':'date','开盘':'open','收盘':'close','最高':'high','最低':'low','成交量':'vol','成交额':'amount','涨跌幅':'pct'}
            raw.rename(columns={k:v for k,v in cm.items() if k in raw.columns}, inplace=True)
            df = raw[['date','open','close','high','low','vol']].copy()
            for c in ['close','high','low','vol']:
                df[c] = pd.to_numeric(df[c], errors='coerce')
            df.dropna(subset=['close'], inplace=True)
            df.reset_index(drop=True, inplace=True)
            if len(df) <= LOOKBACK + 30:
                continue

        signal, _ = detect_and_validate(df, code, name)
        if signal:
            all_signals.append(signal)
            print(f"  [HIT] {code} {name[:4]} | {signal['pullback_date']} "
                  f"| bb={signal['bb_dist']:.1f}% pb={signal['pullback_pct']:.1f}% "
                  f"| score={signal['final_score']:.0f} "
                  f"| T+3={signal.get('max_3d','?')} "
                  f"T+5={signal.get('max_5d','?')}")

        elapsed = time.time() - scan_start
        if (idx + 1) % 100 == 0:
            rate = (idx + 1) / elapsed
            eta = (len(stocks) - idx - 1) / rate / 60
            print(f"  进度: {idx+1}/{len(stocks)} ({100*(idx+1)/len(stocks):.1f}%) "
                  f"| 命中: {len(all_signals)} | 缓存: {cache_hits} 缺: {cache_miss} "
                  f"| ETA: {eta:.0f}min")

        time.sleep(0.03)

    print(f"\n扫描完成: {len(stocks)} 只 | 命中: {len(all_signals)} 只")
    elapsed = time.time() - scan_start
    print(f"耗时: {elapsed/60:.1f}min | 缓存命中率: {cache_hits}/{len(stocks)}")

    if not all_signals:
        print("无信号！")
        return

    # 保存原始信号
    sig_df = pd.DataFrame(all_signals)
    sig_df.sort_values('final_score', ascending=False, inplace=True)
    sig_df.reset_index(drop=True, inplace=True)
    sig_df.to_csv(os.path.join(BASE, 'final_signals_v3.csv'),
                  index=False, encoding='utf-8-sig')
    print(f"信号保存: final_signals_v3.csv ({len(sig_df)} 只)")

    # ========================
    # 生成报告
    # ========================
    generate_report(sig_df)


def generate_report(df):
    print("\n" + "=" * 70)
    print("  策略v3.0 扩展验证报告")
    print("=" * 70)

    print(f"\n【样本概况】")
    print(f"  总信号数: {len(df)}")
    print(f"  数据天数: 均值={df['data_days'].mean():.0f} 最小={df['data_days'].min()}")

    # 综合分分布
    print(f"\n【综合分分布】")
    for t in [90, 85, 80, 75, 70, 60]:
        cnt = (df['final_score'] >= t).sum()
        print(f"  >= {t}分: {cnt}只 ({100*cnt/len(df):.0f}%)")

    # 二次拉升统计
    print(f"\n{'='*70}")
    print("  【二次拉升验证】（回踩确认后N日内最大涨幅）")
    print(f"{'='*70}")

    for n, label in [(3,'T+3'), (5,'T+5'), (10,'T+10'), (15,'T+15'), (20,'T+20')]:
        max_col = f'max_{n}d'
        cls_col = f'close_{n}d'
        if max_col not in df.columns:
            continue

        max_vals = df[max_col].dropna()
        cls_vals = df[cls_col].dropna()
        if len(max_vals) < 3:
            continue

        win_rate = (max_vals > 0).mean() * 100
        avg_max = max_vals.mean()
        median_max = max_vals.median()
        avg_close = cls_vals.mean() if len(cls_vals) else 0

        print(f"\n  {label}窗口 (n={len(max_vals)}只):")
        print(f"    上涨概率: {win_rate:.1f}%")
        print(f"    平均最大涨幅: {avg_max:.2f}%")
        print(f"    中位数最大涨幅: {median_max:.2f}%")
        print(f"    平均收盘涨幅: {avg_close:.2f}%")
        print(f"    最大涨幅: {max_vals.max():.1f}%  最小: {max_vals.min():.1f}%")

    # 按综合分分组验证
    print(f"\n{'='*70}")
    print("  【按综合分分组验证（T+5最大涨幅）】")
    print(f"{'='*70}")

    for g_name, g_df in [
        ('Top(>=85分)', df[df['final_score'] >= 85]),
        ('中高(80-85)', df[(df['final_score'] >= 80) & (df['final_score'] < 85)]),
        ('中(75-80)', df[(df['final_score'] >= 75) & (df['final_score'] < 80)]),
        ('一般(70-75)', df[(df['final_score'] >= 70) & (df['final_score'] < 75)]),
        ('全部', df),
    ]:
        if len(g_df) < 3:
            continue
        m3 = g_df.get('max_3d', pd.Series()).dropna()
        m5 = g_df.get('max_5d', pd.Series()).dropna()
        m10 = g_df.get('max_10d', pd.Series()).dropna()
        print(f"\n  {g_name} (n={len(g_df)}):")
        if len(m5) > 0:
            print(f"    T+3: 胜率={100*(m3>0).mean():.1f}% 均={m3.mean():.1f}% 中位={m3.median():.1f}%")
            print(f"    T+5: 胜率={100*(m5>0).mean():.1f}% 均={m5.mean():.1f}% 中位={m5.median():.1f}%")
            print(f"    T+10: 胜率={100*(m10>0).mean():.1f}% 均={m10.mean():.1f}% 中位={m10.median():.1f}%")

    # BB距离 vs 涨幅
    print(f"\n{'='*70}")
    print("  【BB距离 vs 二次拉升（T+5最大涨幅）】")
    print(f"{'='*70}")

    for g_name, g_df in [
        ('BB<=0.5%', df[df['bb_dist'] <= 0.5]),
        ('BB 0.5-1%', df[(df['bb_dist'] > 0.5) & (df['bb_dist'] <= 1.0)]),
        ('BB 1-2%', df[(df['bb_dist'] > 1.0) & (df['bb_dist'] <= 2.0)]),
    ]:
        if len(g_df) < 2:
            continue
        m5 = g_df.get('max_5d', pd.Series()).dropna()
        m10 = g_df.get('max_10d', pd.Series()).dropna()
        print(f"\n  {g_name} (n={len(g_df)}):")
        print(f"    T+5: 胜率={100*(m5>0).mean():.1f}% 均={m5.mean():.1f}% 中位={m5.median():.1f}%")
        print(f"    T+10: 胜率={100*(m10>0).mean():.1f}% 均={m10.mean():.1f}% 中位={m10.median():.1f}%")

    # 回踩深度 vs 涨幅
    print(f"\n{'='*70}")
    print("  【回踩深度 vs 二次拉升（T+5最大涨幅）】")
    print(f"{'='*70}")

    for g_name, g_df in [
        ('10-15%', df[(df['pullback_pct'] >= 10) & (df['pullback_pct'] < 15)]),
        ('15-20%', df[(df['pullback_pct'] >= 15) & (df['pullback_pct'] < 20)]),
        ('20-25%', df[(df['pullback_pct'] >= 20) & (df['pullback_pct'] < 25)]),
        ('25-35%', df[(df['pullback_pct'] >= 25) & (df['pullback_pct'] <= 35)]),
    ]:
        if len(g_df) < 2:
            continue
        m5 = g_df.get('max_5d', pd.Series()).dropna()
        print(f"  {g_name} (n={len(g_df)}): "
              f"胜率={100*(m5>0).mean():.1f}% 均={m5.mean():.1f}% 中位={m5.median():.1f}%")

    # Top20 信号
    print(f"\n{'='*70}")
    print("  【Top20信号】")
    print(f"{'='*70}")

    top20 = df.head(20)
    cols = ['code', 'name', 'final_score', 'fund_score', 'bb_dist',
            'pullback_pct', 'vol_ratio', 'max_5d', 'max_10d']
    avail = [c for c in cols if c in top20.columns]
    print(top20[avail].to_string(index=False))

    print(f"\n{'='*70}")
    print(f"  报告完成 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}")


if __name__ == '__main__':
    run_full_scan()
