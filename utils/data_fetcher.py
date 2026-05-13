"""
Data Fetcher - 混合数据源
1. 优先从本地缓存读取
2. 未缓存股票用腾讯行情 API (快速)
3. 缓存文件保留旧格式 (baostock 中文列名)
"""
import os, time, requests, json, threading, pandas as pd

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "stocks")
PROXY = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}

def ensure_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)

def _save_cache(code: str, df: pd.DataFrame):
    """保存缓存，兼容旧格式"""
    file_path = os.path.join(DATA_DIR, f"{code}.csv")
    # 如果已有文件，直接追加/更新
    if os.path.exists(file_path):
        try:
            old = pd.read_csv(file_path)
            if len(old) > len(df):
                return  # 旧缓存更长，保留
        except:
            pass
    df.to_csv(file_path, index=False, encoding='utf-8')

def fetch_tencent_raw(code: str, days: int = 250) -> list:
    """腾讯行情 API 拉复权日K"""
    prefix = 'sh' if code.startswith(('6', '688')) else 'sz'
    url = (f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
           f"?_var=kline_dayhfq&param={prefix}{code},day,,,{days},qfq")
    try:
        r = requests.get(url, proxies=PROXY, timeout=8)
        if r.status_code != 200:
            return []
        text = r.text
        json_str = text[text.index('=') + 1:]
        data = json.loads(json_str)
        code_key = '{}{}'.format(prefix, code)
        code_data = data.get('data', {}).get(code_key, {})
        rows = code_data.get('qfqday') or code_data.get('day') or []
        result = []
        for row in rows:
            if len(row) < 6:
                continue
            try:
                result.append({
                    '日期': row[0],
                    '开盘': float(row[1]),
                    '收盘': float(row[2]),
                    '最高': float(row[3]),
                    '最低': float(row[4]),
                    '成交量': float(row[5]),
                    '成交额': 0.0,
                    '涨跌幅': 0.0,
                    '复权类型': '前复权',
                })
            except:
                pass
        return result
    except:
        return []

def fetch_stock_history(code: str, days: int = 250) -> pd.DataFrame or None:
    ensure_dir()
    file_path = os.path.join(DATA_DIR, f"{code}.csv")

    # 1. 读缓存
    if os.path.exists(file_path):
        try:
            # 先尝试读前两行判断格式
            with open(file_path, encoding='utf-8', errors='ignore') as f:
                first = f.readline().strip()
            
            import re
            if re.match(r'^\d{4}-\d{2}-\d{2},', first):
                # 无表头格式（baostock），手动指定列名
                col_names = ['日期', '代码', '开盘', '最高', '最低', '收盘', 
                             '成交量', '成交额', '复权类型', '换手率', '涨跌幅']
                cached = pd.read_csv(file_path, header=None, names=col_names,
                                     encoding='utf-8', on_bad_lines='skip')
            else:
                cached = pd.read_csv(file_path, encoding='utf-8', on_bad_lines='skip')
            
            if len(cached) > 100:
                # 统一保留需要的列
                required = ['日期', '开盘', '最高', '最低', '收盘', '成交量', '成交额']
                cols_keep = [c for c in required if c in cached.columns]
                return cached[cols_keep].copy()
        except Exception as e:
            pass

    # 2. 腾讯行情 API 拉新数据
    rows = fetch_tencent_raw(code, 300)
    if not rows or len(rows) < 100:
        return None

    df = pd.DataFrame(rows)
    for col in ['开盘', '最高', '最低', '收盘', '成交量', '成交额']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    if '涨跌幅' in df.columns:
        df['涨跌幅'] = pd.to_numeric(df['涨跌幅'], errors='coerce')
    df.dropna(subset=['收盘'], inplace=True)
    df.reset_index(drop=True, inplace=True)

    _save_cache(code, df)
    return df

# 旧接口兼容
def get_stock_list_market_cap():
    csv_path = os.path.join(BASE_DIR, 'stock_list_clean.csv')
    if os.path.exists(csv_path):
        return pd.read_csv(csv_path, dtype={'代码': str})
    return pd.DataFrame(columns=['代码', '名称', '总市值'])
