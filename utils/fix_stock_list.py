"""
构建全量股票列表 - 快速保存版（每10批保存一次）
"""
import os, time, requests, pandas as pd, sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROXY = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}
MKT_CAP_LIMIT = 300
BATCH_SIZE = 60
DELAY = 0.2

def fetch_tencent_batch(tx_codes):
    url = 'https://qt.gtimg.cn/q=' + ','.join(tx_codes)
    try:
        r = requests.get(url, proxies=PROXY, timeout=8)
        if r.status_code != 200:
            return {}
        result = {}
        for line in r.text.strip().split('\n'):
            if '~' not in line:
                continue
            parts = line.split('~')
            if len(parts) < 46:
                continue
            raw = parts[0].replace('v_', '').replace('"', '').strip()
            if '=' in raw:
                code = raw.split('=')[0][2:]
            else:
                code = raw[2:] if len(raw) > 2 else raw
            try:
                mktcap_yi = float(parts[44]) if parts[44].strip() not in ('', '-', 'N/A') else 0
                name = parts[1].strip() if len(parts) > 1 else ''
                result[code] = {'mktcap_yi': mktcap_yi, 'name': name}
            except:
                pass
        return result
    except:
        return {}

def save_partial(found, segment):
    out = os.path.join(BASE_DIR, 'stock_list_partial.csv')
    records = [{'code': code, 'name': d['name'], 'mktcap_yi': d['mktcap_yi']}
               for code, d in found.items()]
    df = pd.DataFrame(records)
    small = df[(df['mktcap_yi'] > 0) & (df['mktcap_yi'] <= MKT_CAP_LIMIT)].copy()
    small = small.sort_values('code').reset_index(drop=True)
    small[['code', 'name', 'mktcap_yi']].to_csv(out, index=False)
    print('  [{}] Total: {}/{} stocks, partial saved'.format(
        segment, len(found), len(small)))

def scan_range(prefix, start, end, segment):
    found = {}
    batch_count = 0
    i = start
    while i <= end:
        batch = ['{}{:06d}'.format(prefix, j) for j in range(i, min(i + BATCH_SIZE, end + 1))]
        result = fetch_tencent_batch(batch)
        for code, data in result.items():
            if data['mktcap_yi'] > 0:
                found[code] = data
        i += BATCH_SIZE
        batch_count += 1
        time.sleep(DELAY)
        if batch_count % 10 == 0:
            save_partial(found, segment)
    return found

if __name__ == '__main__':
    all_found = {}

    print('=== Shanghai Main (600000-605999) ===')
    sys.stdout.flush()
    r1 = scan_range('sh', 600000, 605999, 'SH')
    all_found.update(r1)
    print('  SH done: {}'.format(len(r1)))
    sys.stdout.flush()

    print('=== STAR (688000-688999) ===')
    sys.stdout.flush()
    r2 = scan_range('sh', 688000, 688999, 'STAR')
    all_found.update(r2)
    print('  STAR done: {}'.format(len(r2)))
    sys.stdout.flush()

    print('=== Shenzhen Main (000000-003999) ===')
    sys.stdout.flush()
    r3 = scan_range('sz', 0, 3999, 'SZ')
    all_found.update(r3)
    print('  SZ done: {}'.format(len(r3)))
    sys.stdout.flush()

    print('=== ChiNext (300000-303999) ===')
    sys.stdout.flush()
    r4 = scan_range('sz', 300000, 303999, 'GEM')
    all_found.update(r4)
    print('  GEM done: {}'.format(len(r4)))
    sys.stdout.flush()

    # Final save
    print('\nTotal found: {}'.format(len(all_found)))
    records = [{'code': code, 'name': d['name'], 'mktcap_yi': d['mktcap_yi']}
               for code, d in all_found.items()]
    df = pd.DataFrame(records)
    small = df[(df['mktcap_yi'] > 0) & (df['mktcap_yi'] <= MKT_CAP_LIMIT)].copy()
    small = small.sort_values('code').reset_index(drop=True)

    print('Filtered (<= 300Y): {} stocks'.format(len(small)))
    out = os.path.join(BASE_DIR, 'stock_list_clean.csv')
    small[['code', 'name', 'mktcap_yi']].to_csv(out, index=False)
    print('Saved to: {}'.format(out))
    sys.stdout.flush()
