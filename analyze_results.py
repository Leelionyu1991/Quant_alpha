import pandas as pd, numpy as np

df = pd.read_csv(r'C:\Users\Razer\Desktop\quant_alpha\final_signals_v3.csv')

has5 = df.dropna(subset=['max_5d'])
has10 = df.dropna(subset=['max_10d'])
total = len(df)
n5 = len(has5)
n10 = len(has10)

print(f'总信号: {total}  |  有T+5: {n5}  |  有T+10: {n10}')
print()

v3 = df['max_3d'].dropna()
v5 = has5['max_5d']
v10 = has10['max_10d']

pos3 = (v3 > 0).sum() / len(v3) * 100
pos5 = (v5 > 0).sum() / len(v5) * 100
pos10 = (v10 > 0).sum() / len(v10) * 100

print('上涨概率:')
print(f'  T+3  {pos3:.1f}%')
print(f'  T+5  {pos5:.1f}%')
print(f'  T+10 {pos10:.1f}%')
print()

print('平均最大涨幅:')
print(f'  T+3  {v3.mean():.2f}%')
print(f'  T+5  {v5.mean():.2f}%')
print(f'  T+10 {v10.mean():.2f}%')
print()

print('中位数最大涨幅:')
print(f'  T+3  {v3.median():.2f}%')
print(f'  T+5  {v5.median():.2f}%')
print(f'  T+10 {v10.median():.2f}%')
print()

loss5 = has5[has5['max_5d'] < 0]
print(f'T+5 亏损样本 ({len(loss5)}只):')
for _, r in loss5.iterrows():
    print(f'  {r["code"]} {r["name"]} max={r["max_5d"]:.1f}%')

print()
loss10 = has10[has10['max_10d'] < 0]
print(f'T+10 亏损样本 ({len(loss10)}只):')
for _, r in loss10.iterrows():
    print(f'  {r["code"]} {r["name"]} max={r["max_10d"]:.1f}%')

print()
print('=== 按最终分分段 ===')
for lo, hi in [(80,100),(70,80),(60,70),(0,60)]:
    sub = df[df['final_score'].between(lo, hi)]
    if len(sub) == 0:
        continue
    sub5 = sub.dropna(subset=['max_5d'])
    avg5 = sub5['max_5d'].mean()
    win5p = (sub5['max_5d'] > 0).sum() / len(sub5) * 100 if len(sub5) > 0 else 0
    print(f'  {lo}-{hi}分: {len(sub)}只 | T+5上涨率{win5p:.0f}% | T+5均值{avg5:.1f}%')

print()
print('=== 按BB距离分段 ===')
for lo, hi in [(0,1),(1,2),(2,5)]:
    sub = has5[has5['bb_dist'].between(lo, hi)]
    if len(sub) == 0:
        continue
    avg5 = sub['max_5d'].mean()
    win5p = (sub['max_5d'] > 0).sum() / len(sub) * 100
    print(f'  bb={lo}-{hi}%: {len(sub)}只 | 上涨率{win5p:.0f}% | 均值{avg5:.1f}%')

print()
print('=== 按回踩深度分段 ===')
for lo, hi in [(10,15),(15,20),(20,25),(25,35)]:
    sub = has5[has5['pullback_pct'].between(lo, hi)]
    if len(sub) == 0:
        continue
    avg5 = sub['max_5d'].mean()
    win5p = (sub['max_5d'] > 0).sum() / len(sub) * 100
    print(f'  pb={lo}-{hi}%: {len(sub)}只 | 上涨率{win5p:.0f}% | 均值{avg5:.1f}%')

print()
print('=== 按量比分段 ===')
for lo, hi in [(1.5,2),(2,3),(3,10)]:
    sub = has5[has5['vol_ratio'].between(lo, hi)]
    if len(sub) == 0:
        continue
    avg5 = sub['max_5d'].mean()
    win5p = (sub['max_5d'] > 0).sum() / len(sub) * 100
    print(f'  vr={lo}-{hi}x: {len(sub)}只 | 上涨率{win5p:.0f}% | 均值{avg5:.1f}%')

print()
print('=== Top10信号 ===')
top10 = df.nlargest(10, 'final_score')[['code','name','final_score','max_5d','max_10d','max_20d']]
for _, r in top10.iterrows():
    print(f'  {r["code"]} {r["name"]} {r["final_score"]:.1f}分 | T+5={r["max_5d"]:.1f}% T+10={r["max_10d"]:.1f}% T+20={r["max_20d"]:.1f}%')

print()
print('=== T+5最大涨幅Top10 ===')
top5 = has5.nlargest(10, 'max_5d')[['code','name','final_score','max_5d','vol_ratio','bb_dist']]
for _, r in top5.iterrows():
    print(f'  {r["code"]} {r["name"]} {r["final_score"]:.1f}分 | T+5={r["max_5d"]:.1f}% vr={r["vol_ratio"]:.1f}x bb={r["bb_dist"]:.2f}%')

# 排除ST
no_st = has5[~has5['name'].str.contains('ST|\*', na=False)]
st_count = len(has5) - len(no_st)
print()
print(f'排除ST后: {len(no_st)}只 (剔除{len(has5)}中的{st_count}只ST)')
print(f'  T+5上涨率: {(no_st["max_5d"]>0).sum()/len(no_st)*100:.1f}%')
print(f'  T+5均值: {no_st["max_5d"].mean():.2f}%')
print(f'  T+10上涨率: {(no_st.dropna(subset=["max_10d"])["max_10d"]>0).sum()/len(no_st.dropna(subset=["max_10d"]))*100:.1f}%')
print(f'  T+10均值: {no_st.dropna(subset=["max_10d"])["max_10d"].mean():.2f}%')
