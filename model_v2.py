"""
quant_alpha 综合选股模型 v2.1
基于 K 线数据推导资金流向 + Sina 公告新闻 + 市场情绪

权重:
  资金流向 : 0.6 (从成交量数据推导)
  消息面   : 0.3 (从公告推导)
  市场情绪 : 0.1 (从指数推导)
"""

import os, sys, time, json, requests, re, pandas as pd, numpy as np
from datetime import datetime, timedelta

BASE_DIR = r'C:\Users\Razer\Desktop\quant_alpha'
sys.path.insert(0, BASE_DIR)
PROXY = {'http': 'http://127.0.0.1:7890', 'https': 'http://127.0.0.1:7890'}

# ============================================================
# 数据获取
# ============================================================
from utils.data_fetcher import fetch_stock_history

def get_index_data():
    """获取市场指数数据（上证/深证/创业板）"""
    indices = [
        ('sh000001', '上证指数'),
        ('sz399001', '深证成指'),
        ('sz399006', '创业板指'),
    ]
    result = {}
    for code, name in indices:
        df = fetch_stock_history(code)
        if df is not None and len(df) >= 5:
            df['收盘'] = pd.to_numeric(df['收盘'], errors='coerce')
            df = df.dropna(subset=['收盘'])
            closes = df['收盘'].tail(5).values
            if len(closes) >= 2:
                trend = (closes[-1] - closes[0]) / closes[0] * 100
                vol_trend = 0
                if '成交量' in df.columns:
                    df['成交量'] = pd.to_numeric(df['成交量'], errors='coerce')
                    vols = df['成交量'].tail(5).values
                    if len(vols) >= 2:
                        vol_trend = (vols[-1] - vols[0]) / vols[0] * 100 if vols[0] > 0 else 0
                result[code] = {'name': name, 'trend_5d': round(trend, 2), 'vol_trend': round(vol_trend, 2)}
    return result

# ============================================================
# 资金流向评分 (从成交量推导) - 权重 0.6
# ============================================================
def score_fund_flow(df):
    """
    从 K 线成交量推导资金流向评分 0-100
    原理：放量上涨=资金流入，放量下跌=资金流出
    """
    if df is None or len(df) < 20:
        return 50, {'reason': 'no_data'}

    df = df.copy().reset_index(drop=True)
    df['收盘'] = pd.to_numeric(df['收盘'], errors='coerce')
    df['成交量'] = pd.to_numeric(df['成交量'], errors='coerce')
    df = df.dropna(subset=['收盘', '成交量']).reset_index(drop=True)

    if len(df) < 20:
        return 50, {'reason': 'insufficient_data'}

    score = 50

    # 1. 量比 (今日成交量 / 20日均量)
    vol_20avg = df['成交量'].tail(20).mean()
    vol_today = df['成交量'].iloc[-1]
    vol_ratio = vol_today / vol_20avg if vol_20avg > 0 else 1

    if vol_ratio >= 3.0:
        score += 15
    elif vol_ratio >= 2.0:
        score += 10
    elif vol_ratio >= 1.5:
        score += 5
    elif vol_ratio >= 1.0:
        score += 2
    else:
        score -= 5

    # 2. OBV 趋势 (累积能量潮)
    df['ret'] = df['收盘'].pct_change()
    df['obv_dir'] = df['ret'].apply(lambda x: 1 if x > 0 else -1)
    df['obv'] = (df['obv_dir'] * df['成交量']).cumsum()
    obv_trend = (df['obv'].iloc[-1] - df['obv'].iloc[-20]) / abs(df['obv'].iloc[-20]) * 100 if df['obv'].iloc[-20] != 0 else 0

    if obv_trend > 20:
        score += 15
    elif obv_trend > 10:
        score += 10
    elif obv_trend > 0:
        score += 5
    elif obv_trend > -10:
        score -= 5
    else:
        score -= 15

    # 3. 5日累计净流入估算 (成交量 * 价格变化方向)
    df['net_flow_est'] = df['obv_dir'] * df['成交量']
    flow_5d = df['net_flow_est'].tail(5).sum()
    flow_20d = df['net_flow_est'].tail(20).sum()

    if flow_5d > 0 and flow_5d > flow_20d * 0.3:
        score += 10  # 近期资金加速流入
    elif flow_5d < 0 and abs(flow_5d) > abs(flow_20d) * 0.5:
        score -= 10  # 近期资金加速流出

    # 4. 突破日放量
    if len(df) >= 5:
        recent = df.tail(5)
        rises = [(row['收盘'] - df.iloc[df.index.get_loc(row.name)-1]['收盘']) / df.iloc[df.index.get_loc(row.name)-1]['收盘'] * 100
                  for i, (idx, row) in enumerate(recent.iterrows()) if i > 0]
        if rises:
            max_rise = max(rises)
            vol_at_rise = recent.iloc[rises.index(max_rise)]['成交量']
            vol_ratio_rise = vol_at_rise / vol_20avg if vol_20avg > 0 else 1
            if max_rise >= 5 and vol_ratio_rise >= 2.0:
                score += 10  # 放量突破

    score = max(0, min(100, score))

    return score, {
        'vol_ratio': round(vol_ratio, 2),
        'obv_trend_20d': round(obv_trend, 1),
        'flow_5d': round(flow_5d, 0),
        'flow_20d': round(flow_20d, 0),
    }

# ============================================================
# 消息面评分 - 权重 0.3
# ============================================================
_news_cache = {}

def get_news_sina(code):
    """从 Sina 公告页抓取个股公告标题"""
    if code in _news_cache:
        return _news_cache[code]

    prefix = 'sz' if not code.startswith(('6', '688')) else 'sh'
    url = 'https://vip.stock.finance.sina.com.cn/corp/go.php/vCB_AllBulletin/stockid/{}/page/1.phtml'.format(code)
    try:
        r = requests.get(url, proxies=PROXY, timeout=5)
        if r.status_code != 200:
            _news_cache[code] = []
            return []

        text = r.text
        # 解析标题列表
        titles = re.findall(r'title="([^"]*(?:公告|报告|通知|决议|说明|业绩|回购|增持|减持|风险|问询|立案|处罚)[^"]*)"', text)
        dates = re.findall(r'(\d{4}-\d{2}-\d{2})', text[:20000])
        dates = [d for d in dates if d.startswith('202')][:len(titles)]

        results = []
        for i in range(min(len(titles), 10)):
            results.append({
                'title': titles[i] if i < len(titles) else '',
                'date': dates[i] if i < len(dates) else '',
            })
        _news_cache[code] = results
        return results
    except:
        _news_cache[code] = []
        return []

def score_news(code):
    """
    消息面评分 0-100
    """
    news = get_news_sina(code)
    if not news:
        return 50, {'reason': 'no_news', 'news_count': 0}

    positive_keywords = ['业绩', '净利润', '营收', '超预期', '订单', '中标', '回购', '增持',
                        '战略', '合作', '研发', '突破', '投产', '扩产', '利润增长']
    negative_keywords = ['风险提示', 'ST', '退市', '减持', '诉讼', '处罚', '立案', '违规',
                        '亏损', '下滑', '商誉', '减值', '亏损', '业绩预亏', '无法表示']

    score = 50
    news_count = len(news)
    positive = 0
    negative = 0
    recent_important = 0

    today = datetime.now()

    for n in news:
        title = n.get('title', '')
        date_str = n.get('date', '')

        if any(k in title for k in positive_keywords):
            positive += 1
        if any(k in title for k in negative_keywords):
            negative += 1

        # 近期重要公告（7天内）
        if date_str:
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d')
                days_ago = (today - date).days
                if days_ago <= 7:
                    if any(k in title for k in positive_keywords):
                        recent_important += 1
                    if any(k in title for k in negative_keywords):
                        recent_important -= 2
            except:
                pass

    # 加分：利好公告
    score += positive * 6
    if recent_important >= 2:
        score += 15
    elif recent_important == 1:
        score += 8

    # 减分：利空公告
    score -= negative * 10

    score = max(0, min(100, score))

    return score, {
        'news_count': news_count,
        'positive': positive,
        'negative': negative,
        'recent_important': recent_important,
        'latest': news[0]['title'][:50] if news else '',
    }

# ============================================================
# 市场情绪评分 - 权重 0.1
# ============================================================
_sentiment_cache = {}
_sentiment_cache_time = 0

def get_market_sentiment():
    """
    市场情绪评分 0-100
    基于：指数趋势 + 涨停数量估算
    """
    global _sentiment_cache, _sentiment_cache_time

    if _sentiment_cache and time.time() - _sentiment_cache_time < 300:
        return _sentiment_cache

    score = 50
    details = {}

    # 1. 指数趋势
    indices = get_index_data()
    if indices:
        trends = [v['trend_5d'] for v in indices.values()]
        avg_trend = sum(trends) / len(trends) if trends else 0
        details['indices'] = indices

        if avg_trend >= 2:
            score += 20
        elif avg_trend >= 1:
            score += 12
        elif avg_trend >= 0.5:
            score += 6
        elif avg_trend >= 0:
            score += 3
        elif avg_trend >= -1:
            score -= 5
        else:
            score -= 15

    _sentiment_cache = {'score': score, 'details': details}
    _sentiment_cache_time = time.time()
    return _sentiment_cache

# ============================================================
# 综合评分
# ============================================================
def score_stock(code, name='', mktcap_yi=0):
    """综合评分 0-100"""
    # 1. K 线数据
    df = fetch_stock_history(code)

    # 2. 资金流 (0.6)
    fund_score, fund_details = score_fund_flow(df)

    # 3. 消息面 (0.3)
    news_score, news_details = score_news(code)

    # 4. 市场情绪 (0.1)
    sentiment_data = get_market_sentiment()
    sentiment_score = sentiment_data['score']

    # 5. 综合加权
    final = (
        fund_score * 0.6 +
        news_score * 0.3 +
        sentiment_score * 0.1
    )

    final = round(min(100, max(0, final)), 1)
    fund_score = round(fund_score, 1)
    news_score = round(news_score, 1)
    sentiment_score = round(sentiment_score, 1)

    return {
        'code': code,
        'name': name,
        'final_score': final,
        'fund_score': fund_score,
        'news_score': news_score,
        'sentiment_score': sentiment_score,
        'components': {
            'fund': fund_details,
            'news': news_details,
            'sentiment': sentiment_data,
        }
    }

# ============================================================
# 全量扫描
# ============================================================
def run_full_scan(min_score=60, top_n=50):
    print('=' * 60)
    print('  quant_alpha 综合选股模型 v2.1')
    print('  资金流向(0.6) + 消息面(0.3) + 市场情绪(0.1)')
    print('=' * 60)

    stock_df = pd.read_csv(os.path.join(BASE_DIR, 'stock_list_clean.csv'))
    print('Total stocks: {}'.format(len(stock_df)))

    # 预热市场情绪
    print('Fetching market sentiment...')
    sent = get_market_sentiment()
    print('Market sentiment score: {}'.format(sent['score']))
    if sent['details'].get('indices'):
        for code, data in sent['details']['indices'].items():
            print('  {}: 5日趋势{:.2f}%'.format(data['name'], data['trend_5d']))

    results = []
    scored = 0

    for idx, row in stock_df.iterrows():
        code = str(row.get('代码', '')).zfill(6)
        name = str(row.get('名称', code))
        mktcap = float(row.get('总市值', 0)) if pd.notna(row.get('总市值')) else 0

        if idx % 200 == 0:
            pct = 100 * (idx + 1) / len(stock_df)
            print('Progress: {}/{} ({:.1f}%) scored: {}'.format(
                idx + 1, len(stock_df), pct, scored))
            sys.stdout.flush()

        try:
            result = score_stock(code, name, mktcap)
            scored += 1
            results.append(result)
        except Exception as e:
            pass

        time.sleep(0.02)

    print('\nScored: {}'.format(scored))

    # 排序
    df_results = pd.DataFrame(results)
    df_results = df_results.sort_values('final_score', ascending=False).reset_index(drop=True)

    # 保存
    out_path = os.path.join(BASE_DIR, 'final_scores.csv')
    df_results.to_csv(out_path, index=False, encoding='utf-8-sig')
    print('\nResults saved: {}'.format(out_path))

    # 打印 Top
    print('\nTop {} 综合评分:'.format(top_n))
    print('-' * 80)
    for i, r in df_results.head(top_n).iterrows():
        flag = ''
        if r['final_score'] >= 80:
            flag = '**'
        elif r['final_score'] >= 70:
            flag = '*'
        print('{:<3} {:<8} {:<8} 综合{:>5} 资金{:>5} 消息{:>5} 情绪{:>5}'.format(
            flag, r['code'], r['name'][:6],
            r['final_score'], r['fund_score'], r['news_score'], r['sentiment_score']))

    return df_results


if __name__ == '__main__':
    # 测试
    print('=== 测试 ===')
    for code, name in [('002515', '金字火腿'), ('603158', '腾龙股份'), ('002108', '沧州明珠')]:
        result = score_stock(code, name)
        print('')
        print('{} {} 综合:{} 资金:{} 消息:{} 情绪:{}'.format(
            code, name, result['final_score'], result['fund_score'],
            result['news_score'], result['sentiment_score']))
        print('  资金: {}'.format(result['components']['fund']))
        print('  消息: {}'.format(result['components']['news']))
