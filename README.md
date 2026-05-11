# quant_alpha

A quantitative trading strategy research & backtesting framework.

## Philosophy

We avoid "saturated" signals like Golden Cross/Death Cross. Our core focus is on:
1. **Volatility Contraction (横盘)**: Identifying periods of low volatility before a potential move.
2. **Bollinger Band Pullback (回踩布林)**: The "shake-out" before the real breakout.
3. **Structural Breakout (结构突破)**: A strong, decisive price action (>5%) breaking out of the contraction.
4. **No Repainting**: Our signals are based on closed candles only.

## Setup

```bash
pip install akshare pandas numpy
```

## Data

We use `akshare` to fetch historical daily K-line data.
