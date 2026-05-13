import requests, time
PROXY = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}

def batch(codes):
    url = 'https://qt.gtimg.cn/q=' + ','.join(codes)
    r = requests.get(url, proxies=PROXY, timeout=10)
    result = {}
    for line in r.text.strip().split('\n'):
        if '~' not in line:
            continue
        p = line.split('~')
        if len(p) < 45:
            continue
        raw = p[0].replace('v_', '').replace('"', '').strip()
        if len(raw) < 8:
            continue
        code = raw[2:]
        try:
            mkt = float(p[44]) if p[44].strip() not in ('', '-', 'N/A') else 0
            result[code] = mkt
        except:
            pass
    return result

# Test batch
codes = ['sh600000', 'sh600519', 'sz000001', 'sz000002', 'sh601318']
r = batch(codes)
print('Test batch:', r)

# Test speed: 60 codes
batch60 = ['sh{:06d}'.format(600000 + i) for i in range(60)]
t0 = time.time()
r60 = batch(batch60)
elapsed = time.time() - t0
found = sum(1 for v in r60.values() if v > 0)
print('Scan 60 codes in {:.1f}s, found {} with mktcap>0'.format(elapsed, found))
for c, v in list(r60.items())[:5]:
    print('  {}: {:.1f}Y'.format(c, v))
