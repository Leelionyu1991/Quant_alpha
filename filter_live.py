import pandas as pd
df = pd.read_csv(r'C:\Users\Razer\Desktop\quant_alpha\live_signals.csv')

# 最优选择：贴近布林中轨 + 回踩后涨幅不大（还在低位）
df2 = df[(df['cur_bb_dist'] < 3) & (df['cur_from_pb'] < 6)].copy()
df2['entry_quality'] = (100 - df2['cur_bb_dist']*10) + (30 - df2['cur_from_pb'].clip(0,30)) + df2['final_score']
df2 = df2.sort_values('entry_quality', ascending=False)

print('=== 最优买入机会（贴近布林中轨 + 回踩未大涨）===')
cols = ['code','name','final_score','pullback_pct','cur_bb_dist','cur_from_pb','days_since_pb']
for col in cols:
    print(f'{col:<16}', end='')
print()
print('-'*100)
for _, r in df2.head(15).iterrows():
    print(f'{str(r["code"]):<16}{str(r["name"]):<16}{str(r["final_score"]):<16}{str(r["pullback_pct"]):<16}{str(r["cur_bb_dist"]):<16}{str(r["cur_from_pb"]):<16}{str(r["days_since_pb"])}')

print()
print('=== 高评分信号（>=75分）===')
df3 = df[df['final_score']>=75].sort_values('final_score', ascending=False)
print(f'{"code":<8} {"name":<10} {"score":<6} {"pb%":<7} {"bb":<6} {"from_pb":<8} {"days":<6}')
print('-'*60)
for _, r in df3.iterrows():
    print(f'{r["code"]:<8} {r["name"]:<10} {r["final_score"]:<6.1f} {r["pullback_pct"]:<6.1f}% {r["cur_bb_dist"]:<5.1f}% {r["cur_from_pb"]:>+6.1f}% {r["days_since_pb"]:>5}天')

print()
print('=== 综合推荐 Top5（综合考虑评分+贴近度+未启动）===')
for i, (_, r) in enumerate(df2.head(5).iterrows(), 1):
    print(f'{i}. {r["code"]} {r["name"]}')
    print(f'   评分: {r["final_score"]:.1f}分 | 回踩深度: {r["pullback_pct"]:.1f}% | 当前距BB中轨: {r["cur_bb_dist"]:.1f}%')
    print(f'   回踩日期: {r["pullback_date"]} | 回踩后涨幅: {r["cur_from_pb"]:+.1f}% | 距今: {r["days_since_pb"]}天')
    print()
