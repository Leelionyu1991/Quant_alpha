# quant_alpha

量化选股工具，基于**波动收缩形态**（Volatility Contraction Breakout，VCB）筛选 A 股。

## 策略核心

VCB 形态三阶段：
1. **横盘吸筹** — MA60 平坦（变异系数 <5%），价格振幅 15-70%
2. **放量突破** — 涨幅 ≥5%，量比 ≥1.5x
3. **回踩确认** — 回踩深度 10-30%，股价贴近布林中轨（±2%）

回踩确认后买入，等待二次拉升。

## 评分公式

```
最终分 = 资金分 × 0.7 + 形态分 × 0.2 + 情绪分 × 0.1
```

## 目录结构

```
quant_alpha/
├── run_screener.py      # 选股扫描（主脚本）
├── live_scan.py         # 实时选股（当前满足条件的股票）
├── validate_v3.py       # 全量回测验证
├── run_backtest.py      # 回测框架
├── strategies/           # 策略模块
│   └── merged_strategy.py
├── utils/               # 工具模块
│   └── data_fetcher.py
└── data/                # 股票数据缓存（gitignore）
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 快速开始

### 1. 扫描全量股票

```bash
python run_screener.py
```

### 2. 实时选股（找当前可买入的）

```bash
python live_scan.py
```

### 3. 全量回测验证

```bash
python validate_v3.py
```

## 回测结果

- 样本：4169 只股票扫描，153 个 VCB 信号
- T+5 上涨概率：**97.9%**
- T+5 平均最大涨幅：**10.7%**
- T+10 上涨概率：**98.6%**
- T+10 平均最大涨幅：**15.4%**

详见 [STRATEGY_v3.md](STRATEGY_v3.md)

## 数据说明

- 股票列表：`stock_list_clean.csv`
- 数据缓存：`data/stocks/*.csv`（每文件一行代码，自动从腾讯/Sina API 获取）
- 数据格式：日期，开盘，收盘，最高，最低，成交量

## 注意事项

- 本工具仅供研究参考，不构成投资建议
- 实盘请自行做好风险控制（建议止损 -8%）
- 回测结果不代表未来收益
