"""
VCB信号追踪报告 - 格式化输出用于QQ发送
"""
import os, sys, json, pandas as pd
sys.path.insert(0, os.path.dirname(__file__))

TRACK_FILE = r'C:\Users\Razer\Desktop\quant_alpha\tracking_signals.json'
REPORT_FILE = r'C:\Users\Razer\Desktop\quant_alpha\tracking_report.csv'

def load_latest_report():
    if not os.path.exists(REPORT_FILE):
        return None
    df = pd.read_csv(REPORT_FILE, encoding='utf-8')
    if len(df) == 0:
        return None
    # 取最新日期
    latest_date = df['date'].max()
    df_today = df[df['date'] == latest_date].sort_values('change_pct', ascending=False)
    return latest_date, df_today

def format_qq_report():
    result = load_latest_report()
    if result is None:
        return None
    date, df = result

    if len(df) == 0:
        return None

    lines = []
    lines.append(f"VCB信号追踪日报 | {date}")
    lines.append("")

    # 汇总
    avg_chg = df['change_pct'].mean()
    win = (df['change_pct'] > 0).sum()
    total = len(df)
    best = df.iloc[0]
    worst = df.iloc[-1]
    days = int(df.iloc[0]['days'])

    lines.append(f"追踪天数: {days}天 | 上涨: {win}/{total} | 均值涨跌: {avg_chg:+.2f}%")
    lines.append(f"最佳: {best['name']} {best['change_pct']:+.2f}% | 最差: {worst['name']} {worst['change_pct']:+.2f}%")
    lines.append("")

    # 详细
    for _, r in df.iterrows():
        code = str(r['code']).zfill(6)
        chg = r['change_pct']
        sign = '+' if chg >= 0 else ''
        today_chg = r.get('today_change', 0)
        tsign = '+' if today_chg >= 0 else ''
        lines.append(f"{code} {r['name']:<6} {sign}{chg:.2f}% (今日{tsign}{today_chg:.2f}%)  {int(r['days'])}天")

    return '\n'.join(lines)

if __name__ == '__main__':
    msg = format_qq_report()
    if msg:
        print(msg)
        # 输出给父进程
        with open(r'C:\Users\Razer\Desktop\quant_alpha\tracking_msg.txt', 'w', encoding='utf-8') as f:
            f.write(msg)
        print("__QQ_MSG_SAVED__")
    else:
        print("无追踪数据")
