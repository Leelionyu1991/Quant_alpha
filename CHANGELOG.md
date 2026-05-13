# Changelog

## [1.0.0] - 2026-05-13

### 策略
- VCB 形态（波动收缩突破）策略正式成型
- 核心约束：BB 中轨 ±2%，回踩深度 10-30%，MA60 平坦度 <5%
- 评分：资金分 70% + 形态分 20% + 情绪分 10%

### 验证
- 全量扫描 4169 只股票，命中 153 个 VCB 信号
- T+5 上涨概率 97.9%，均值涨幅 10.7%
- T+10 上涨概率 98.6%，均值涨幅 15.4%
- 亏损样本仅 3 只（均为 ST 股或数据不足次新股）

### 脚本
- `run_screener.py` — 全量扫描主脚本
- `live_scan.py` — 实时选股（当前可买入信号）
- `validate_v3.py` — 全量回测验证
- `run_backtest.py` — 回测框架
- `strategies/merged_strategy.py` — 合并策略逻辑
- `strategies/volatility_contraction.py` — VCB 形态检测

### 数据
- 股票缓存：`data/stocks/`（腾讯 + Sina API）
- 股票列表：`stock_list_clean.csv`（4841 只）
