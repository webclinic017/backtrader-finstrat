# backtrader-finstrat


## Momentum based, with tactical asset allocation, pyramide positioning

Source code - `strategy_momentum_gtaa_pyramiding.py`

### Risk Management

1) Monthly checks (beginning of each month)
    * if global market is in downtrend (< 200SMA), exist equities and buy safe assets.
    * If global market switched to uptrend (> 200SMA), rebalance back into risky assets.

Reasoning - don't catch failing knife, however monthly intervals allow some room for market to recover if briefly touching SMA200.

2) Daily checks
    * If individual asset's trailing decline > 25%, close position.

3) Quarterly - if global market is in downtrend, don't rebalance, continue holding safe assets.

### Positioning

 * Pyramide positioning - if price of the asset moved X% above starting price, buy portion of the asset and set new target price. While absolute returns are a bit lower, the strategy has improved risk adjusted returns and significantly lower maximum drawdown. Backtested on multiple universes.

### Profit taking

Profit taking is happening in 2 cases:

1) Sell at the rebalance, because current asset wasn't picked by the momentum algorithm.
2) Profit taking if asset aprreciated 30% compared to it's buy price (for any continuous period, not just 3 month)



