# backtrader-finstrat


## Momentum based, with tactical asset allocation, pyramid positioning

Source code - `strategy_momentum_gtaa_pyramiding.py`

### Risk Management

1) Monthly checks (beginning of each month)
    * if the global market is in a downtrend (< 200SMA), exist equities and buy safe assets.
    * If the global market switched to an uptrend (> 200SMA), rebalance back into risky assets.

Reasoning - don't catch a falling knife, however, monthly intervals allow some room for the market to recover if briefly touching SMA200.

2) Daily checks
    * If individual asset's trailing decline > 25%, close position.

3) Quarterly - if the global market is in a downtrend, don't rebalance, continue holding safe assets.

### Positioning

 * Pyramid positioning - if the price of the asset moved X% above starting price, buy a portion of the asset and set a new target price. While absolute returns are a bit lower, the strategy has improved risk-adjusted returns and significantly lower maximum drawdown. Backtested on multiple universes.

### Profit taking

Profit-taking is happening in 2 cases:

1) Sell at the rebalance, because the current asset wasn't picked by the momentum algorithm.
2) Profit-taking if asset appreciated 30% compared to its buy price (for any continuous period, not just 3 months)



