"""
quant_alpha v3.0 信号追踪
追踪最佳买点信号每日表现，验证策略有效性
"""
import os, sys, json, time, pandas as pd, numpy as np
sys.path.insert(0, os.path.dirname(__file__))

DATA_DIR = r'C:\Users\Razer\Desktop\quant_alpha\data\stocks'
TRACK_FILE = r'C:\Users\Razer\Desktop\quant_alpha\tracking_signals.json'
REPORT_FILE = r'C:\Users\Razer\Desktop\quant_alpha\tracking_report.csv'

# 追踪的8只最佳买点信号
TRACK_STOCKS = [
    {'code': '002991', 'name': '甘源食品',  'entry_date': '2026-05-13', 'entry_price': None},  # pullback_date in data
    {'code': '002988', 'name': '豪美新材',  'entry_date': '2026-05-13', 'entry_price': None},
    {'code': '300741', 'name': '华宝股份',  'entry_date': '2026-05-13', 'entry_price': None},
    {'code': '300107', 'name': '建新股份',  'entry_date': '2026-05-13', 'entry_price': None},
    {'code': '300511', 'name': '雪榕生物',  'entry_date': '2026-05-13', 'entry_price': None},
    {'code': '300925', 'name': '法本信息',  'entry_date': '2026-05-13', 'entry_price': None},
    {'code': '301015', 'name': '百洋医药',  'entry_date': '2026-05-13', 'entry_price': None},
    {'code': '300443', 'name': '金雷股份',  'entry_date': '2026-05-13', 'entry_price': None},
]

# 从 live_signals.csv 读取回踩价格作为入场参考价
def load_entry_prices():
    fp = r'C:\Users\Razer\Desktop\quant_alpha\live_signals.csv'
    if not os.path.exists(fp):
        return {}
    df = pd.read_csv(fp, encoding='utf-8')
    prices = {}
    for _, r in df.iterrows():
        code = str(r['code']).zfill(6)
        prices[code] = {
            'pullback_price': float(r['pullback_price']),
            'pullback_date': str(r['pullback_date']),
            'final_score': float(r['final_score']),
            'pullback_pct': float(r['pullback_pct']),
            'cur_bb_dist': float(r['cur_bb_dist']),
        }
    return prices


def load_today_price(code: str):
    """获取股票最新收盘价"""
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
            cm = {'日期':'date','收盘':'close','最高':'high','最低':'low',
                  '成交量':'vol','开盘':'open'}
            df.rename(columns={k:v for k,v in cm.items() if k in df.columns}, inplace=True)
            keep = ['date','close','high','low','vol']
            df = df[[c for c in keep if c in df.columns]].copy()
        for c in ['close','high','low']:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors='coerce')
        df.dropna(subset=['close'], inplace=True)
        df.reset_index(drop=True, inplace=True)
        if len(df) < 2:
            return None
        latest = df.iloc[-1]
        prev = df.iloc[-2] if len(df) >= 2 else latest
        return {
            'date': str(latest['date'])[:10],
            'close': float(latest['close']),
            'high': float(latest['high']),
            'low': float(latest['low']),
            'prev_close': float(prev['close']),
            'change': (float(latest['close']) - float(prev['close'])) / float(prev['close']) * 100,
        }
    except:
        return None


def load_or_init_tracking():
    """加载或初始化追踪记录"""
    if os.path.exists(TRACK_FILE):
        try:
            with open(TRACK_FILE, encoding='utf-8') as f:
                return json.load(f)
        except:
            pass

    # 初始化：今天为第0天
    today = time.strftime('%Y-%m-%d')
    init_prices = load_entry_prices()
    tracking = {
        'started': today,
        'stocks': {},
        'history': [],
    }
    for stock in TRACK_STOCKS:
        code = stock['code']
        info = init_prices.get(code, {})
        tracking['stocks'][code] = {
            'name': stock['name'],
            'entry_date': stock['entry_date'],
            'entry_price': info.get('pullback_price'),
            'pullback_date': info.get('pullback_date'),
            'final_score': info.get('final_score', 0),
            'pullback_pct': info.get('pullback_pct', 0),
            'cur_bb_dist': info.get('cur_bb_dist', 0),
            'days': 0,
        }
    save_tracking(tracking)
    return tracking


def save_tracking(data):
    with open(TRACK_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run_tracking():
    """执行当日追踪"""
    print('============================================================')
    print('  VCB信号追踪报告')
    print(f'  {time.strftime("%Y-%m-%d %H:%M:%S")}')
    print('============================================================')

    tracking = load_or_init_tracking()
    today = time.strftime('%Y-%m-%d')

    # 检查是否已更新过今天
    hist_today = [h for h in tracking.get('history', []) if h.get('date') == today]
    if hist_today:
        print(f'今日({today})已更新，直接展示')
    else:
        # 新的一天
        tracking['stocks'] = {code: {**s, 'days': s.get('days', 0) + 1}
                               for code, s in tracking['stocks'].items()}

    rows = []
    all_up = 0
    all_total = 0

    for code, info in tracking['stocks'].items():
        price_data = load_today_price(code)
        if price_data is None:
            print(f'  {code} {info["name"]}: 无数据')
            continue

        cur = price_data['close']
        entry = info.get('entry_price')
        if entry is None or entry <= 0:
            print(f'  {code} {info["name"]}: 无入场价')
            continue

        chg = (cur - entry) / entry * 100
        bb_dist = info.get('cur_bb_dist', 0)
        score = info.get('final_score', 0)
        days = info.get('days', 0)

        row = {
            'date': price_data['date'],
            'code': code,
            'name': info['name'],
            'score': score,
            'entry_price': entry,
            'cur_close': cur,
            'change_pct': round(chg, 2),
            'today_change': round(price_data['change'], 2),
            'pullback_pct': info.get('pullback_pct', 0),
            'cur_bb_dist': bb_dist,
            'days': days,
        }
        rows.append(row)

        if chg > 0:
            all_up += 1
        all_total += 1

    if not rows:
        print('无有效数据')
        return

    # 更新历史
    today_row = {k: [r[k] for r in rows] for k in rows[0].keys()}
    tracking.setdefault('history', [])
    tracking['history'] = [h for h in tracking['history'] if h.get('date') != today]
    tracking['history'].append(today_row)
    tracking['history'] = tracking['history'][-30:]  # 保留最近30条
    save_tracking(tracking)

    # 追加到CSV
    new_rows = pd.DataFrame(rows)
    if os.path.exists(REPORT_FILE):
        old = pd.read_csv(REPORT_FILE, encoding='utf-8')
        # 只追加今天没有的日期
        if today not in old['date'].values:
            new_rows = pd.concat([old, new_rows], ignore_index=True)
    new_rows.to_csv(REPORT_FILE, index=False, encoding='utf-8-sig')

    # 打印报告
    rows_sorted = sorted(rows, key=lambda x: x['change_pct'], reverse=True)
    print()
    print(f'追踪天数: {rows[0]["days"]}天 | 上涨: {all_up}/{all_total}')
    print()
    print(f'{"代码":<8} {"名称":<8} {"评分":<5} {"入场价":<8} {"现价":<8} {"涨跌":<8} {"今日涨跌":<8} {"追踪天":<6}')
    print('-' * 75)
    for r in rows_sorted:
        sign = '+' if r['change_pct'] >= 0 else ''
        sign2 = '+' if r['today_change'] >= 0 else ''
        print(f'{r["code"]:<8} {r["name"]:<8} {r["score"]:<5.1f} '
              f'{r["entry_price"]:<8.2f} {r["cur_close"]:<8.2f} '
              f'{sign}{r["change_pct"]:<7.2f}% {sign2}{r["today_change"]:<7.2f}% '
              f'{r["days"]:>4}天')

    print()
    avg_chg = sum(r['change_pct'] for r in rows) / len(rows)
    avg_today = sum(r['today_change'] for r in rows) / len(rows)
    best = rows_sorted[0]
    worst = rows_sorted[-1]
    print(f'均值涨跌: {avg_chg:+.2f}%  |  均值今日: {avg_today:+.2f}%')
    print(f'最佳: {best["name"]} {best["change_pct"]:+.2f}%  |  最差: {worst["name"]} {worst["change_pct"]:+.2f}%')
    print()
    print(f'报告已保存: {REPORT_FILE}')
    return rows


if __name__ == '__main__':
    run_tracking()
