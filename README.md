# backtrader-finstrat



## Active Stratefy - Residual (idiosyncratic) momentum based, with tactical asset allocation, pyramid positioning (Bollinger Bands)

Source code - `strategy_idiosync_m_gtaa_py_bb_atr_stoploss.py`

### Risk Management
0) Quarterly (rebalance) checks
    * If the global market is in a downtrend, don't rebalance and continue holding safe assets.
    * Individual stocks - exclude from consideration stocks in downtrend (SMA < 200 or 150)

1) Monthly checks (beginning of each month)
    * if the global market is in a downtrend (< 200SMA), exist equities and buy safe assets.
    * If the global market switched to an uptrend (> 200SMA), rebalance back into risky assets, even before the official rebalance.

Reasoning - don't catch a falling knife, however, monthly intervals allow room for the market to recover if briefly touching SMA200.

2) Daily checks
    * Checks trailing high against deviation of scaled average true range ATR(90) of the stock.
        * ATR is more robust than using constant trailing % loss, since it takes into account historical volatility of specific stock.
        * The larger is number of days from trailing high, the more likely price to break the ATR
            * To count that, ATR is scaled by number of days (up-to 6) from the high
        * ATR approach is more sound theoretically and is robust under different universes, as opposed to constant 20%, which was more tuned to the extended universe
        * It is mechanism that backs up the global (monthly) risk management in a robust manner.


### Positioning

 * If stock is in a downtrend at the purchase decision, wait till it reaches the lower limit of its Bollinger Band before allowing the purchase.
 * If the purchase is enabled, perform pyramid positioning - if the asset's price moved X% above the current target price, buy an asset's proportion and set a new target price. 

### Profit taking

Profit-taking is happening in 2 cases:

1) Sell at the rebalance, due to the current asset wasn't picked by the momentum algorithm.
2) Profit-taking if an asset appreciated 30% compared to its buy price (for any continuous period, not just a quarter)


## Past strategy - Absolute momentum based, with tactical asset allocation, pyramid positioning (Bollinger Bands)
Source code - `strategy_momentum_gtaa_py_bb_atr_stoploss.py`

* Shares the same features as the main strategy, just the momentum calculation is different.


## Past strategy 2 - momentum based, with tactical asset allocation, pyramid positioning

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
2) Profit-taking if an asset appreciated 30% compared to its buy price (for any continuous period, not just 3 months)



