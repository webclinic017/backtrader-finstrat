from __future__ import absolute_import, division, print_function, unicode_literals

import finstratb.misc.edhec_risk_kit as erk
import pyfolio as pf

import numpy as np
from typing import List, Dict
import pandas as pd
import backtrader as bt
import datetime

from finstratb.universe_11 import (
    EXTENDED_UNIVERSE,
    BASIC_SECTOR_UNIVERSE, 
    INVESCO_EQUAL_WEIGHT_ETF, 
    INVESCO_STYLE_ETF,
    VANGUARD_SECTOR_ETF,
    VANGUARD_STYLE_ETF,
   # SECTOR_STYLE_FX_UNIVERSE
)
from loguru import logger
from finstratb.misc.helpers import (
    get_data,
    get_yahooquery_data_from_file,
    get_single_ticker_data_from_file,
)
from finstratb.misc.momentum import Momentum
import collections
import quantstats


class BuyAndHold_1(bt.Strategy):
    def __init__(self):
        # self.val_start = self.broker.get_cash()  # keep the starting cash
        self.spy = self.datas[0]
        self.stocks = self.datas[1:]

    def nextstart(self):
        # This is called exactly ONCE, when next is 1st called and defaults to
        # call `next`
        self.d_with_len = self.stocks  # all data sets fulfill the guarantees now
        self.next()  # delegate the work to next

    def prenext(self):
        # https://www.backtrader.com/blog/2019-05-20-momentum-strategy/momentum-strategy/

        # Populate d_with_len
        self.d_with_len = [d for d in self.stocks if len(d)]

        # call next() even when data is not available for all tickers
        self.next()

    def next(self):
        all_valid_etfs = self.d_with_len

        for d in all_valid_etfs:
            self.order_target_percent(d, target=1.0 / len(all_valid_etfs))


class Strategy(bt.Strategy):
    params = dict(
        momentum=Momentum,  # parametrize the momentum and its period
        long_momentum_period =90,
        max_stocks=3,
        movav=bt.ind.SMA,  # parametrize the moving average and its periods
        # See here - https://www.investopedia.com/ask/answers/122214/what-does-end-quarter-mean-portfolio-management.asp
      #  rebalance_months = [1.2,3,4,5,6,7,8,9,10,11,12],
        rebalance_months=[1, 4, 7, 10],
        profit_take_pct=0.3,
        stop_loss_pct=-0.2
        # rebalance_months = [2,5,8,11]
    )

    def __init__(self):
        self.i = 0
        self.inds = collections.defaultdict(dict)
        self.spy = self.datas[0]
        self.stocks = self.datas[1:]

        self.spy_sma200 = self.p.movav(self.spy.close, period=200)
        self.safe_assets = [d for d in self.stocks if d._name in ["TLT", 'GLD']] #+ [self.spy]
        self.safe_asset_weights = {"GLD": 0.10, "TLT": 0.40}
        self.hedge = False
        self.d_with_len = self.stocks
        self.buy_positions = []
        self.rebalance_sell_date = None
        self.buy_price = {}
        self.trailing_price = {}
        self.skip_hedge = False
        self.is_downtrend = False

        for d in self.stocks:
            print("Calculating indicators for: ", d._name)
            # self.inds[d] = {}
            self.inds[d]["long_momentum"] = Momentum(
                d.close, period=self.p.long_momentum_period
            )
   

            self.inds[d]["sma200"] = bt.indicators.SMA(d.close, period=200)
            self.inds[d]["sma50"] = bt.indicators.SMA(d.close, period=50)
            
            self.inds[d]["pct_change1"] = bt.indicators.PercentChange(d.close, period=1)

        logger.info("Adding timer...")
        self.add_timer(
            name="rebalance",
            when=bt.timer.SESSION_START,
            monthdays=[1],
            monthcarry=True,
            cheat=False,
        )


    def nextstart(self):
        # This is called exactly ONCE, when next is 1st called and defaults to
        # call `next`
        self.d_with_len = self.stocks  # all data sets fulfill the guarantees now
        self.next()  # delegate the work to next

    def prenext(self):
        # https://www.backtrader.com/blog/2019-05-20-momentum-strategy/momentum-strategy/

        # Populate d_with_len
        self.d_with_len = [d for d in self.stocks if len(d)]

        # call next() even when data is not available for all tickers
        self.next()

    def global_market_risk_hedge(self):

        if self.spy.close[-1] >= self.spy_sma200[-1] or self.skip_hedge:
            if self.is_downtrend:
                self.log("REBALANCING DUE TO DETECTED MARKET RECOVERY")
           #     self.rebalance_portfolio(recovery_mode=True)
            self.is_downtrend = False
            self.skip_hedge = False
            return

        # This code is executed if SPY < SMA(SPY)
      #  self.is_downtrend = True

        posdata = [d for d, pos in self.getpositions().items() if pos]
      #  safe_assets = [d for d in self.safe_assets if d not in posdata]

        # parent_order = None
        for d in posdata:
            # if ( d.close[-1] < self.inds[d]["sma200"][-1]):  # -1 since we are using COC for buy orders. For sell orders we want to execute based on yesterday's data
            if d not in self.safe_assets:
                self.log(
                    f"RISK MANAGEMENT: US MARKET IS IN DOWNTREND, EXITING POSITING for {d._name}, price used for check: {d[-1]:.2f}"
                )
                self.close(d)

#        if safe_assets:
        self.log(f"RISK MANAGEMENT: SWITCHING/REBALANCING SAFE ASSETS")
        self.downtrend = 1

        for d in self.safe_assets:
            self.order_target_percent(d, target=self.safe_asset_weights[d._name])
            self.buy_price[d] = d.close[0]
            self.trailing_price[d] = d.close[0]

    def next(self):
        # pass

        posdata = [d for d, pos in self.getpositions().items() if pos]

        for d in posdata:

            if (
                d.close[-1] >= self.trailing_price[d]
            ):  # this is required for max drawdown calculation for trailing stop loss
                self.trailing_price[d] = d.close[-1]

            if d in self.buy_price and (
                d.close[-1] / self.buy_price[d] - 1.0 > self.p.profit_take_pct
            ):
                self.log(
                    f"RISK MANAGEMENT: TRAILING PROFIT TAKE for {d._name}, price: {d[-1]:.2f}"
                )
                self.close(d)
                continue

            if d in self.trailing_price and (d.close[-1] / self.trailing_price[d] - 1.0 < self.p.stop_loss_pct):
                self.log(f"RISK MANAGEMENT: TRAILING STOP LOSS for {d._name}, price: {d[-1]:.2f}")
                self.close(d)
                continue

            # if ( d.close[-1] < self.inds[d]["sma200"][-1]):  # -1 since we are using COC for buy orders. For sell orders we want to execute based on yesterday's data
            #     self.log(
            #         f"RISK MANAGEMENT: PRICE<SMA200, EXITING POSITING for {d._name}, price used for check: {d[-1]:.2f}"
            #     )
            #     self.close(d)

    def rebalance_portfolio(self):
        # only look at data that we can have indicators for
        # Get current positions
        posdata = [d for d, pos in self.getpositions().items() if pos]

        if self.spy.close[-1] < self.spy_sma200[-1]:
            self.log("NO REBALANCING DUE TO MARKET DOWNTREND")
            self.global_market_risk_hedge()
            self.skip_hedge = True
            return
        
        self.is_downtrend = False

        # if recovery_mode:
        #     all_valid_etfs = [
        #         d for d in self.d_with_len if d.close[-1] >= self.inds[d]["sma200"][-1] and d not in self.safe_assets
        #     ]
        
        # else:
        all_valid_etfs = [
                d for d in self.d_with_len if d.close[-1] >= self.inds[d]["sma200"][-1]
            ]  # self.d_with_len #
        # volatile_positions = self.get_volatile_positions(all_valid_etfs)
        # all_valid_etfs = [d for d in all_valid_etfs if d not in volatile_positions]

        #   negative_short_momentums = [d for d in all_valid_etfs if self.inds[d]["short_momentum"][0] < 0]
        top_long_momentums = sorted(
            all_valid_etfs, key=lambda d: self.inds[d]["long_momentum"][0], reverse=True
        )[: self.p.max_stocks]
        # top_long_momentums = [d for d in top_long_momentums if d not in negative_short_momentums][:self.p.max_stocks]

        self.buy_positions = top_long_momentums

        sell_positions = [d for d in posdata if d not in self.buy_positions]
        for d in sell_positions:
            self.log(f"Exiting position: {d._name}: {d[0]:.2f}")
            self.order_target_percent(d, target=0.0)
        #   self.trailing_prices.pop(d)
        # self.rebalance_sell_date = self.datas[0].datetime[0]

        if self.buy_positions:
            # weights = self.get_gmv_weights(
            #      self.buy_positions
            #  )  # Global minimum variance portfolio
            weights = self.get_erc_weights(self.buy_positions) # Equal risk contributions (risk parity)
            self.log(f"Available cash: {self.broker.get_cash():.2f}")

           # weights = [1.0 / self.p.max_stocks] * len(self.buy_positions)
           # weights = self.get_weights_linear_increasing()
            for w, d in zip(weights, self.buy_positions):
                self.log(
                    f"Entering position: {d._name}: Price: {d[0]:.2f}, Weight: {w:.2f}"
                )
                # self.order_target_percent( d, target=target_pct)
                # See - https://community.backtrader.com/topic/370/unexpected-additional-orders-created-rejected/8
                o = self.order_target_percent(d, target=0.98 * w)
                self.buy_price[d] = d.close[0]
                self.trailing_price[d] = d.close[0]

    def get_weights_linear_increasing(self) -> List[float]:
        weights = np.arange(self.p.max_stocks, 0, -1)
        #weights = np.arange(1, self.max_tickers+1)
        weights = weights/weights.sum()
        return weights
        #return {t:w for t,w in zip(tickers_df.index, weights[:len(tickers_df)])}
    
    
    
    def get_gmv_weights(self, buy_positions) -> list:
        try:
            rets = np.stack(
                (
                    [
                        self.inds[d]["pct_change1"].get(0, 60).tolist()
                        for d in buy_positions
                    ]
                )
            ).T
            gmv_weights = erk.weight_gmv(pd.DataFrame(rets))
        except ValueError:
            self.log("Error with weights, falling back to EW")
            gmv_weights = [1.0 / self.p.max_stocks] * len(buy_positions)
        return gmv_weights

    def get_erc_weights(self, buy_positions) -> list:
        try:
            rets = np.stack(
                (
                    [
                        self.inds[d]["pct_change1"].get(0, 90).tolist()
                        for d in buy_positions
                    ]
                )
            ).T
            erc_weights = erk.weight_erc(pd.DataFrame(rets))
        except ValueError:
            self.log("Error with weights, falling back to EW")
            erc_weights = [1.0 / self.p.max_stocks] * len(buy_positions)
        return erc_weights

    def notify_timer(self, timer, when, *args, **kwargs):
        if kwargs["name"] == "rebalance":
            if when.month in self.p.rebalance_months:
                self.log(f"====== REBALANCING ======")
                self.rebalance_portfolio()
        elif kwargs["name"] == "risk":
            self.global_market_risk_hedge()

    def log(self, txt, dt=None):
        """Logging function fot this strategy"""
        dt = dt or self.data.datetime[0]
        if isinstance(dt, float):
            dt = bt.num2date(dt)
        print("%s, %s" % (dt.isoformat(), txt))

    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            # Buy/Sell order submitted/accepted to/by broker - Nothing to do
            return

        # Check if an order has been completed
        # Attention: broker could reject order if not enough cash
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f"\tORDER COMPLETED: BUY {order.data._name}, price: {order.executed.price:.2f}, shares: {order.size}, value: ${order.executed.price*order.size:.2f}"
                )

            elif order.issell():
                self.log(
                    f"\tORDER COMPLETED: SELL {order.data._name}, price: {order.executed.price:.2f}, shares: {order.size}, value: ${order.executed.price*order.size:.2f}"
                )
            posdata = [d for d, pos in self.getpositions().items() if pos]
            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log("\tORDER ERROR: Order Canceled/Margin/Rejected")

        # Write down: no pending order
        self.order = None


if __name__ == "__main__":
  #  universe = VANGUARD_STYLE_ETF
    universe = EXTENDED_UNIVERSE
  #  universe = INVESCO_EQUAL_WEIGHT_ETF
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(100000.0)

    # https://www.backtrader.com/docu/broker/ - see cheat-on-close, prevents buy/sell at the same bar
    # matching a `Market` order to the closing price of the bar in which
    # the order was issued. This is actually *cheating*, because the bar
    # is *closed* and any order should first be matched against the prices
    # in the next bar
    cerebro.broker.set_coc(True)  # Cheat on close

    cerebro.broker.set_checksubmit(checksubmit=False)

    data_dict = get_data(symbols=["SPY"] + universe)
    from_date = datetime.datetime(2005,12,15)
    to_date = datetime.datetime(2020, 2,17)

    # spy_data = get_single_ticker_data_from_file(
    #     file_name="./mretf/backtrader/data/SPY.csv"
    # )
    # data_dict = get_yahooquery_data_from_file(
    #     file_name="./mretf/backtrader/data/etf_data.zip"
    # )
    # cerebro.adddata(
    #     bt.feeds.PandasData(
    #         dataname=spy_data,
    #         fromdate=from_date,
    #         todate=to_date,
    #         name="SPY",
    #         plot=False,
    #     )
    # )

    for symbol, data in data_dict.items():
        # print(data)
        logger.info(f"Adding '{symbol}' to Cerebro.")

        cerebro.adddata(
            bt.feeds.PandasData(
                dataname=data,
                fromdate=from_date,
                todate=to_date,
                name=symbol,
                plot=False,
            )
        )

    # print(data_dict)

    cerebro.addobserver(bt.observers.Value)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.Returns)
    cerebro.addanalyzer(bt.analyzers.DrawDown)
    # cerebro.addanalyzer(bt.analyzers.TradeAnalyzer)
    cerebro.addanalyzer(bt.analyzers.PyFolio)

    print("Starting Portfolio Value: %.2f" % cerebro.broker.getvalue())

    cerebro.addstrategy(Strategy)
    #cerebro.addstrategy(BuyAndHold_1)
    results = cerebro.run()

    print(
        f"Sharpe: {results[0].analyzers.sharperatio.get_analysis()['sharperatio']:.3f}"
    )
    print(
        f"Norm. Annual Return: {results[0].analyzers.returns.get_analysis()['rnorm100']:.2f}%"
    )
    print(
        f"Max Drawdown: {results[0].analyzers.drawdown.get_analysis()['max']['drawdown']:.2f}%"
    )

    pyfoliozer = results[0].analyzers.getbyname("pyfolio")
    returns, positions, transactions, gross_lev = pyfoliozer.get_pf_items()
    returns.index = returns.index.tz_convert(None)

    quantstats.reports.html(returns, benchmark="SPY", output="results/rotation_stats_gtaa_robust.html")
    cerebro.plot(iplot=False)[0][0]
