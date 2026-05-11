# quant_alpha - 量化趋势追踪系统

## 项目理念
我们专注于 **“横盘突破”** 策略，拒绝使用过度饱和的技术指标（如简单金叉死叉）。
核心逻辑：市场在窄幅横盘整理后，主力资金会进行“洗盘”（回踩布林带中轨），随后展开结构性突破。

## 目录结构
```text
quant_alpha/
├── data/               # 历史数据缓存目录 (会自动生成)
├── strategies/         # 策略逻辑实现
│   └── volatility_contraction.py
├── utils/              # 工具函数 (数据获取等)
│   └── data_fetcher.py
├── run_screener.py     # 选股器入口
├── requirements.txt    # Python 依赖
└── README.md
```

## 快速开始

### 1. 环境配置
建议使用 **VS Code** 打开本项目，并配合 **Anaconda** 使用。

打开 VS Code 终端，执行以下命令创建并激活环境：

```bash
# 创建环境
conda create -n quant_alpha python=3.9 -y

# 激活环境
conda activate quant_alpha

# 安装依赖
pip install akshare pandas numpy
```

### 2. 运行选股器
```bash
python run_screener.py
```

## 策略核心逻辑 (参考 STRATEGY.md)

## 待开发功能：评价函数
计划将 **消息情绪** 和 **资金流向** 作为买入信号的辅助判断依据，详见 `STRATEGY.md`。
