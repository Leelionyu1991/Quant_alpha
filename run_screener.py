import sys
import os
import time
import pandas as pd
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.data_fetcher import fetch_stock_history, get_stock_list_market_cap
from strategies.merged_strategy import analyze_stock, backtest_stock, MKTCAP_LIMIT

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STOCK_LIST_FILE = os.path.join(BASE_DIR, "stock_list_clean.csv")
PROGRESS_FILE = os.path.join(BASE_DIR, "scan_progress.txt")
RESULTS_FILE = os.path.join(BASE_DIR, "results.csv")
BACKTEST_RESULTS_FILE = os.path.join(BASE_DIR, "backtest_results.csv")

PYTHON = sys.executable


def save_progress(code):
    with open(PROGRESS_FILE, 'w') as f:
        f.write(code)


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            return f.read().strip()
    return None


def clear_progress():
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)


def run_screener(skip_cache=False):
    print("=" * 60)
    print("  Merged Strategy Screener: VCB + MA Bullish Golden Cross")
    print("=" * 60)

    if os.path.exists(STOCK_LIST_FILE) and not skip_cache:
        print("Loading cached stock list...")
        stock_df = pd.read_csv(STOCK_LIST_FILE, dtype={'\u4ee3\u7801': str})
    else:
        stock_df = get_stock_list_market_cap()
        stock_df['\u4ee3\u7801'] = stock_df['\u4ee3\u7801'].astype(str).str.zfill(6)
        stock_df.to_csv(STOCK_LIST_FILE, index=False)

    print(f"Total stocks: {len(stock_df)}")

    last_code = load_progress()
    start_idx = 0
    if last_code and last_code in stock_df['\u4ee3\u7801'].values:
        idx_list = stock_df[stock_df['\u4ee3\u7801'] == str(last_code)].index.tolist()
        if idx_list:
            start_idx = idx_list[0] + 1
            print(f"Resuming from {last_code} (index {start_idx})")

    results = []
    scanned = 0

    for i in range(start_idx, len(stock_df)):
        row = stock_df.iloc[i]
        code = str(row['\u4ee3\u7801']).zfill(6)
        name = row['\u540d\u79f0'] if '\u540d\u79f0' in row else code

        save_progress(code)

        df = fetch_stock_history(code)
        if df is not None:
            scanned += 1
            mktcap_yi = float(row['总市值']) if '总市值' in row and pd.notna(row['总市值']) else 0.0

            res = analyze_stock(df, code, name, mktcap_yi)
            if res:
                results.append(res)
                tags = []
                if res.get('consolidation'):
                    tags.append('VCB')
                if res.get('pullback_to_mid'):
                    tags.append('PB')
                if res.get('bullish_ma'):
                    tags.append('BULL')
                if res.get('cross_type') not in ('none', None):
                    tags.append(res.get('cross_type', 'CROSS'))
                tag_str = '+'.join(tags) if tags else 'BREAK'
                print(f"  [HIT] {code} {name} | {res['breakout_date']} | {tag_str} | rise={res['rise_pct']}% | score={res['score']}")

        if scanned % 50 == 0:
            pct = 100 * (i + 1) / len(stock_df)
            print(f"  Progress: {i+1}/{len(stock_df)} ({pct:.1f}%), Hits: {len(results)}")

        time.sleep(0.05)

    print(f"\n{'=' * 60}")
    print(f"  Scan Complete: {scanned} scanned, {len(results)} hits")
    print(f"{'=' * 60}")

    if results:
        pd.DataFrame(results).to_csv(RESULTS_FILE, index=False)
        print(f"Results saved to {RESULTS_FILE}")
        print_summary(results)
    else:
        print("No stocks matched the criteria.")

    clear_progress()
    return results


def run_backtest(sample_size=200):
    print("=" * 60)
    print("  Merged Strategy Backtest (rolling window)")
    print("=" * 60)

    if not os.path.exists(STOCK_LIST_FILE):
        print("No stock list found. Run screener first.")
        return

    stock_df = pd.read_csv(STOCK_LIST_FILE, dtype={'\u4ee3\u7801': str})

    if sample_size > 0 and sample_size < len(stock_df):
        stock_df = stock_df.sample(n=sample_size, random_state=42).reset_index(drop=True)
        print(f"Sampling {sample_size} stocks for backtest")
    else:
        print(f"Using all {len(stock_df)} stocks")

    all_signals = []
    scanned = 0

    for i in range(len(stock_df)):
        row = stock_df.iloc[i]
        code = str(row['\u4ee3\u7801']).zfill(6)
        name = row['\u540d\u79f0'] if '\u540d\u79f0' in row else code
        mktcap_yi = float(row['总市值']) if '总市值' in row and pd.notna(row['总市值']) else 0.0

        df = fetch_stock_history(code)
        if df is not None and len(df) > 160:
            signals = backtest_stock(df, code, name, mktcap_yi)
            all_signals.extend(signals)
            scanned += 1

        if scanned % 50 == 0:
            pct = 100 * (i + 1) / len(stock_df)
            print(f"  Progress: {scanned} scanned, {len(all_signals)} signals found ({pct:.1f}%)")

        time.sleep(0.02)

    print(f"\nTotal signals: {len(all_signals)}")

    if all_signals:
        pd.DataFrame(all_signals).to_csv(BACKTEST_RESULTS_FILE, index=False)
        print(f"Saved to {BACKTEST_RESULTS_FILE}")
        print_backtest_summary(all_signals)
    else:
        print("No signals found.")


def print_summary(results):
    print(f"\n--- Signal Summary ---")
    vcb = sum(1 for r in results if r.get('consolidation'))
    bull = sum(1 for r in results if r.get('bullish_ma'))
    cross = sum(1 for r in results if r.get('cross_type') not in ('none', None))
    dual = sum(1 for r in results if r.get('cross_type') == 'dual')
    pb_mid = sum(1 for r in results if r.get('pullback_to_mid'))
    both = sum(1 for r in results if r.get('consolidation') and r.get('cross_type') not in ('none', None))
    print(f"  VCB consolidation: {vcb}")
    print(f"  Pullback to MA20: {pb_mid}")
    print(f"  Bullish MA10>MA20>MA60: {bull}")
    print(f"  Golden cross: {cross} (dual: {dual})")
    print(f"  VCB + Golden cross: {both}")
    avg_score = np.mean([r.get('score', 0) for r in results])
    print(f"  Avg score: {avg_score:.1f}")
    print(f"  Total: {len(results)}")


def print_backtest_summary(signals):
    print(f"\n--- Backtest Summary ---")
    total = len(signals)
    print(f"Total signals: {total}")

    for d in [1, 2, 3, 5, 10]:
        key = f't{d}'
        rets = [s[key] for s in signals if key in s and s[key] is not None]
        if not rets:
            continue
        rets_f = [float(r) for r in rets]
        avg = np.mean(rets_f)
        win = sum(1 for r in rets_f if r > 0)
        wr = win / len(rets_f) * 100
        avg_w = np.mean([r for r in rets_f if r > 0]) if any(r > 0 for r in rets_f) else 0
        avg_l = np.mean([r for r in rets_f if r <= 0]) if any(r <= 0 for r in rets_f) else 0
        label = f'T+{d}'
        print(f"  {label}: n={len(rets_f)} | WR={wr:.1f}% | Avg={avg:.2f}% | WinAvg={avg_w:.2f}% | LoseAvg={avg_l:.2f}%")

    groups = {
        'VCB_only': [s for s in signals if s.get('consolidation') and not s.get('golden_cross')],
        'Golden_only': [s for s in signals if not s.get('consolidation') and s.get('golden_cross')],
        'Both_VCB_Golden': [s for s in signals if s.get('consolidation') and s.get('golden_cross')],
        'Bullish_MA': [s for s in signals if s.get('bullish_ma')],
        'Dual_cross': [s for s in signals if s.get('cross_type') == 'dual'],
    }

    print(f"\n--- By Signal Type (T+1) ---")
    for name, group in groups.items():
        if not group:
            continue
        rets = [s.get('t1') for s in group if s.get('t1') is not None]
        if not rets:
            continue
        rets_f = [float(r) for r in rets]
        avg = np.mean(rets_f)
        win = sum(1 for r in rets_f if r > 0)
        wr = win / len(rets_f) * 100
        print(f"  {name} (n={len(group)}): T+1 WR={wr:.1f}% | Avg={avg:.2f}%")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else 'screener'

    if mode == 'backtest':
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 200
        run_backtest(n)
    elif mode == 'screener':
        skip = '--skip-cache' in sys.argv
        run_screener(skip)
    else:
        print(f"Usage: python {sys.argv[0]} [screener|backtest] [sample_size]")
        print(f"  screener  - scan all stocks for current signals")
        print(f"  backtest  - historical backtest (default 200 sample)")
