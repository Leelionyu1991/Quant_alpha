"""
市场趋势模块
用上证指数(000001.SH) 和 创业板指(399006.SZ) 判断大盘状态
"""
import pandas as pd
import numpy as np

# 上证指数代码
INDEX_CODE_SH = '000001'
INDEX_CODE_CYB = '399006'


def get_index_trend(index_code: str, df: pd.DataFrame = None, data_dir: str = None) -> dict:
    """
    计算指数趋势

    返回:
        trend: 'strong_up' | 'up' | 'neutral' | 'down'
        score: 0-100 趋势得分
        ma60_above: bool - 当前是否在MA60上方
        ma60_slope: float - MA60斜率（%）
        ret_5d: float - 5日收益率
        ret_10d: float - 10日收益率
        ret_20d: float - 20日收益率
    """
    if df is None:
        import os
        fp = os.path.join(data_dir, f'{index_code}.csv')
        if not os.path.exists(fp):
            return None
        df = pd.read_csv(fp, encoding='utf-8', on_bad_lines='skip')
        col_map = {'日期': 'date', '收盘': 'close', '最高': 'high',
                   '最低': 'low', '成交量': 'vol', '开盘': 'open'}
        df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}, inplace=True)
        if 'close' not in df.columns:
            return None
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        df.dropna(subset=['close'], inplace=True)
        df.reset_index(drop=True, inplace=True)

    if len(df) < 60:
        return None

    df = df.tail(80).copy()
    df['MA20'] = df['close'].rolling(20).mean()
    df['MA60'] = df['close'].rolling(60).mean()

    last = df.iloc[-1]
    cur = float(last['close'])
    ma60 = float(last['MA60'])
    ma20 = float(last['MA20'])

    if np.isnan(ma60) or ma60 <= 0:
        return None

    # MA60斜率（最近20天MA60变化率）
    ma60_series = df['MA60'].dropna()
    if len(ma60_series) >= 20:
        ma60_slope = (ma60_series.iloc[-1] - ma60_series.iloc[-20]) / ma60_series.iloc[-20] * 100
    else:
        ma60_slope = 0.0

    # 相对MA60位置
    above_ma60 = cur > ma60
    ma60_dist = (cur - ma60) / ma60 * 100

    # MA多头排列
    ma20_above_ma60 = ma20 > ma60 if (not np.isnan(ma20) and not np.isnan(ma60)) else False

    # 近期收益率
    ret_5d = float(df['close'].pct_change(5).iloc[-1] * 100) if len(df) > 5 else 0
    ret_10d = float(df['close'].pct_change(10).iloc[-1] * 100) if len(df) > 10 else 0
    ret_20d = float(df['close'].pct_change(20).iloc[-1] * 100) if len(df) > 20 else 0

    # 趋势评分 (0-100)
    score = 50
    if above_ma60:
        score += 15
    if ma20_above_ma60:
        score += 10
    if ma60_slope > 0.5:
        score += 10
    elif ma60_slope > 0:
        score += 5
    elif ma60_slope < -0.5:
        score -= 10
    if ma60_dist > 2:
        score += 5
    elif ma60_dist < -2:
        score -= 10
    if ret_5d > 2:
        score += 10
    elif ret_5d > 0:
        score += 5
    elif ret_5d < -2:
        score -= 10
    if ret_20d > 5:
        score += 10
    elif ret_20d > 0:
        score += 5
    elif ret_20d < -5:
        score -= 10
    score = max(0, min(100, score))

    # 趋势分类
    if score >= 75 and above_ma60 and ma60_slope > 0.3:
        trend = 'strong_up'
    elif score >= 60 and above_ma60:
        trend = 'up'
    elif score <= 35 or (not above_ma60 and ma60_slope < -0.3):
        trend = 'down'
    else:
        trend = 'neutral'

    return {
        'trend': trend,
        'score': score,
        'index_code': index_code,
        'current_price': round(cur, 2),
        'ma60': round(ma60, 2),
        'ma60_slope': round(ma60_slope, 2),
        'above_ma60': above_ma60,
        'ma60_dist': round(ma60_dist, 2),
        'ma20_above_ma60': ma20_above_ma60,
        'ret_5d': round(ret_5d, 2),
        'ret_10d': round(ret_10d, 2),
        'ret_20d': round(ret_20d, 2),
    }


def get_market_trend(data_dir: str = None, index_df: dict = None) -> dict:
    """
    综合上证 + 创业板趋势
    """
    result = {
        'trend': 'neutral',
        'score': 50,
        'details': {},
        'position': 'neutral',  # 多头/空头/中性
    }

    sh_trend = None
    cyb_trend = None

    if index_df and '000001' in index_df:
        sh_trend = get_index_trend('000001', index_df['000001'], data_dir)
    elif data_dir:
        sh_trend = get_index_trend('000001', data_dir=data_dir)

    if index_df and '399006' in index_df:
        cyb_trend = get_index_trend('399006', index_df['399006'], data_dir)
    elif data_dir:
        cyb_trend = get_index_trend('399006', data_dir=data_dir)

    if sh_trend:
        result['details']['sh'] = sh_trend
    if cyb_trend:
        result['details']['cyb'] = cyb_trend

    # 综合评分
    scores = []
    if sh_trend:
        scores.append(sh_trend['score'])
    if cyb_trend:
        scores.append(cyb_trend['score'])

    if scores:
        result['score'] = int(sum(scores) / len(scores))
    else:
        result['score'] = 50

    # 趋势分类（两者综合）
    trends = [t['trend'] for t in [sh_trend, cyb_trend] if t]
    if not trends:
        result['trend'] = 'neutral'
    elif all(t in ('strong_up', 'up') for t in trends):
        result['trend'] = 'strong_up'
    elif any(t == 'strong_up' for t in trends):
        result['trend'] = 'up'
    elif all(t == 'down' for t in trends):
        result['trend'] = 'down'
    elif any(t == 'down' for t in trends):
        result['trend'] = 'neutral'
    else:
        result['trend'] = 'neutral'

    # 仓位建议
    if result['trend'] == 'strong_up':
        result['position'] = '多头'
    elif result['trend'] == 'up':
        result['position'] = '多头轻仓'
    elif result['trend'] == 'down':
        result['position'] = '空头/观望'
    else:
        result['position'] = '中性'

    return result


def trend_adjust(trend: dict, final_score: float, pullback_pct: float = None) -> float:
    """
    根据市场趋势调整最终评分

    Args:
        trend: 市场趋势字典
        final_score: 原始评分
        pullback_pct: 回踩深度（%），用于弱市时对浅回踩更严格

    Returns:
        调整后评分
    """
    t = trend['trend']
    s = trend['score']

    adjusted = final_score

    if t == 'strong_up':
        # 牛市：评分不变，浅回踩也接受
        pass
    elif t == 'up':
        # 偏牛：轻微下调
        adjusted = final_score * 0.95
    elif t == 'down':
        # 熊市：大幅下调，浅回踩直接过滤
        adjusted = final_score * 0.6
        if pullback_pct is not None and pullback_pct < 15:
            adjusted = 0  # 熊市浅回踩不可靠
    else:
        # 中性：轻微下调
        adjusted = final_score * 0.85
        if pullback_pct is not None and pullback_pct < 12:
            adjusted *= 0.7  # 中性市场浅回踩也要更严格

    return max(0, adjusted)


def format_trend_summary(trend: dict) -> str:
    """格式化趋势摘要"""
    if not trend:
        return "市场趋势: 未知（无指数数据）"

    parts = []
    t = trend['trend']

    label = {'strong_up': '强势上涨', 'up': '上涨', 'neutral': '中性', 'down': '下跌'}
    parts.append(f"大盘: {label.get(t, t)}")

    if 'sh' in trend['details']:
        sh = trend['details']['sh']
        parts.append(f"上证: {sh['current_price']} ({sh['ret_5d']:+.1f}%近5日)")

    if 'cyb' in trend['details']:
        cyb = trend['details']['cyb']
        parts.append(f"创业板: {cyb['current_price']} ({cyb['ret_5d']:+.1f}%近5日)")

    parts.append(f"仓位建议: {trend['position']}")

    return ' | '.join(parts)
