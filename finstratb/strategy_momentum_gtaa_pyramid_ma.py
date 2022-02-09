""" This strategy uses the momentum logic from GTAA main, however uses pyramiding technique for positions using moving average rather than fixed percentage
Based on ideas from - https://bastion.substack.com/p/improving-the-stop-loss

This strategy shows superior returns to constant pyramid strategy, but with larger drawdowns and slightly reduced Sharpe ratios.
"""

from __future__ import absolute_import, division, print_function, unicode_literals

import finstratb.misc.edhec_risk_kit as erk
import pyfolio as pf

import numpy as np
from typing import List, Dict
import pandas as pd
import backtrader as bt
import datetime

from universe_11 import (
    EXTENDED_UNIVERSE,
    BASIC_SECTOR_UNIVERSE,
    INVESCO_EQUAL_WEIGHT_ETF,
    INVESCO_STYLE_ETF,
    VANGUARD_SECTOR_ETF,
    VANGUARD_STYLE_ETF,
    SECTOR_STYLE_UNIVERSE,
    RANDOM_STOCKS,
    HFEA_UNIVERSE
)

from loguru import logger
from finstratb.misc.helpers import (
    get_data,
    get_yahooquery_data_from_file,
    get_single_ticker_data_from_file,
)
from finstratb.misc.momentum import Momentum
from finstratb.misc.positioning import PyramidPositioning, EmptyPositionQueueException
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
        long_momentum_period=90,
        max_stocks=4,
        movav=bt.ind.SMA,  # parametrize the moving average and its periods
        spy_risk_ma = 200,
        ticker_uptrend_ma = 150,
        ticker_short_ma = 50,
        # See here - https://www.investopedia.com/ask/answers/122214/what-does-end-quarter-mean-portfolio-management.asp
     #   rebalance_months = [1,2,3,4,5,6,7,8,9,10,11,12],
        rebalance_months=[1, 4, 7, 10],
        #rebalance_months=[3, 6, 9, 12],
        profit_take_pct=0.3,
        stop_loss_pct=-0.25,
        pyramid_step_pct_increase = 0.01,
        pyramid_n_steps = 4
     #   rebalance_months = [2,5,8,11]
    )

    def __init__(self):
        self.i = 0
        self.inds = collections.defaultdict(dict)
        self.spy = self.datas[0]
        self.stocks = self.datas[1:]

        self.spy_sma200 = self.p.movav(self.spy.close, period=self.p.spy_risk_ma)

       # self.spy_sma50 = self.p.movav(self.spy.close, period=50)
        self.safe_assets = [d for d in self.stocks if d._name in [
            "TLT", 'GLD']]  # + [self.spy]
        self.safe_asset_weights = {"GLD": 0.1, "TLT": 0.4}  # , 'SPY':0.05}
        self.hedge = False
        self.d_with_len = self.stocks
        self.buy_positions = []
        self.rebalance_sell_date = None
        self.buy_price = {}
        self.trailing_price = {}
        self.skip_hedge = False
        self.is_downtrend = False
        self.positioning_queue = {}
        self.open_orders = {}

        for d in self.stocks:
            self.inds[d]["long_momentum"] = Momentum(
                d.close, period=self.p.long_momentum_period
            )
            self.inds[d]["sma200"] = bt.indicators.EMA(d.close, period=self.p.ticker_uptrend_ma)
            self.inds[d]["sma_short"] = bt.indicators.EMA(d.close, period=self.p.ticker_short_ma)
            self.inds[d]["pct_change1"] = bt.indicators.PercentChange(
                d.close, period=1)

        self.add_timer(
            name="rebalance",
            when=bt.timer.SESSION_START,
            monthdays=[1], #[30]
            monthcarry=True,
            cheat=False,
        )

        self.add_timer(
            name="risk",
            when=bt.timer.SESSION_START,
            monthdays=[
                6
            ],  # Day 6 is arbitrary, we need to be sure to be check for risks after the rebalance
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
                self.rebalance_portfolio(recovery_mode=True)
            self.is_downtrend = False
            self.skip_hedge = False
            return

        # This code is executed if SPY < SMA(SPY)
        self.is_downtrend = True

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
                self.positioning_queue.pop(d, None)

#        if safe_assets:
        self.log(f"RISK MANAGEMENT: SWITCHING/REBALANCING SAFE ASSETS")
        self.downtrend = 1

        for d in self.safe_assets:
            self.order_target_percent(
                d, target=self.safe_asset_weights[d._name])
            
            # self.positioning_queue[d] =  PyramidPositioning(d, asset_initial_price=d.close[0], asset_total_target_pct=self.safe_asset_weights[d._name], 
            #                                                 step_pct_increase=self.p.pyramid_step_pct_increase, n_steps = self.p.pyramid_n_steps)
            self.buy_price[d] = d.close[0]
            self.trailing_price[d] = d.close[0]

    
    def purchase_assets_in_queue(self):
        if self.positioning_queue:
            temp_queue = [(d, position) for d, position in self.positioning_queue.items()] # Since we can't update the original queue during iteration
            for d, position in temp_queue:
                current_price = d[0]
                try:
                    if current_price >= self.inds[d]["sma_short"][-1]:
                        
                        pct_allocation = position.pop_allocation()
                        self.order_target_percent(d, target=pct_allocation)
                    #    position.update_target_price(current_price=current_price)
                        self.log(f"\t\tPosition Ordering: {d._name}: Price: {d[0]:.2f}, Weight: {pct_allocation:.2f}")
                except EmptyPositionQueueException:
                    self.positioning_queue.pop(d, None) # All purchased, remove key
    
    def next(self):
        # pass
        
        self.purchase_assets_in_queue()

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
                self.positioning_queue.pop(d, None)
                continue

            if d in self.trailing_price and (d.close[-1] / self.trailing_price[d] - 1.0 < self.p.stop_loss_pct):
                self.log(
                    f"RISK MANAGEMENT: TRAILING STOP LOSS for {d._name}, price: {d[-1]:.2f}")
                self.close(d)
                self.positioning_queue.pop(d, None)
                continue

    def rebalance_portfolio(self, recovery_mode=False):
        # only look at data that we can have indicators for
        # Get current positions
        posdata = [d for d, pos in self.getpositions().items() if pos]

        if self.spy.close[-1] < self.spy_sma200[-1] and not recovery_mode:
            self.log("NO REBALANCING DUE TO MARKET DOWNTREND")
            self.global_market_risk_hedge()
            self.skip_hedge = True
            return

        self.is_downtrend = False

        if recovery_mode:
            all_valid_etfs = [
                d for d in self.d_with_len if d.close[-1] >= self.inds[d]["sma200"][-1] and d not in self.safe_assets
            ]

        else:
            all_valid_etfs = [
                d for d in self.d_with_len if d.close[-1] >= self.inds[d]["sma200"][-1]] #  and self.inds[d]["long_momentum"][0]>0.8]
            #]  # self.d_with_len #

        top_long_momentums = sorted(
            all_valid_etfs, key=lambda d: self.inds[d]["long_momentum"][0], reverse=True
        )[: self.p.max_stocks+2]
        
        momentum_values = [f"{d._name}:{self.inds[d]['long_momentum'][0]:.3f}" for d in top_long_momentums]
        
        print(f"MOMENTUM VALUES: {', '.join(momentum_values)}")
        # top_long_momentums = [d for d in top_long_momentums if d not in negative_short_momentums][:self.p.max_stocks]

        self.buy_positions = top_long_momentums[:self.p.max_stocks]

        sell_positions = [d for d in posdata if d not in self.buy_positions]
        for d in sell_positions:
            self.log(f"Exiting position: {d._name}: {d[0]:.2f}")
            self.order_target_percent(d, target=0.0)
            # self.buy_price.pop(d, None)
        #    self.positioning_queue.pop(d, None)
        #   self.trailing_prices.pop(d)
        # self.rebalance_sell_date = self.datas[0].datetime[0]

        
        # Reseet positioning queue
        self.positioning_queue = {d: self.positioning_queue[d] for d in self.positioning_queue if d in self.buy_positions}
        
        
        if self.buy_positions:

            self.log(f"Available cash: {self.broker.get_cash():.2f}")

            weights = [1.0 / self.p.max_stocks] * len(self.buy_positions)

            for w, d in zip(weights, self.buy_positions):
                self.log(
                    f"Assigning positioning: {d._name}: Price: {d[0]:.2f}, Total Weight: {w:.2f}"
                )
                # self.order_target_percent( d, target=target_pct)
                # See - https://community.backtrader.com/topic/370/unexpected-additional-orders-created-rejected/8
                
                if (d not in posdata): # if there is no position, enter new position using pyramid
                    position_allocation = PyramidPositioning(d, asset_initial_price=d.close[0], asset_total_target_pct=0.95*w, 
                                                            step_pct_increase=self.p.pyramid_step_pct_increase, n_steps = self.p.pyramid_n_steps)
                    
                    self.positioning_queue[d] = position_allocation
                    self.buy_price[d] = d.close[0]
                    self.trailing_price[d] = d.close[0]


                elif d not in self.positioning_queue: # just rebalance if asset is fully positioned
                
                    o = self.order_target_percent(d, target=0.95 * w)
                #self.buy_price[d] = d.close[0]
                #self.trailing_price[d] = d.close[0]


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
            if order.isbuy():
                self.open_orders[order.data._name] = order
            return

        # Check if an order has been completed
        # Attention: broker could reject order if not enough cash
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    f"\tORDER COMPLETED: BUY {order.data._name}, price: {order.executed.price:.2f}, shares: {order.size}, value: ${order.executed.price*order.size:.2f}"
                )
                self.open_orders.pop(order.data._name, None)

            elif order.issell():
                self.log(
                    f"\tORDER COMPLETED: SELL {order.data._name}, price: {order.executed.price:.2f}, shares: {order.size}, value: ${order.executed.price*order.size:.2f}"
                )
            posdata = [d for d, pos in self.getpositions().items() if pos]
        #    self.open_orders.pop(order.data._name, None)
            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log("\tORDER ERROR: Order Canceled/Margin/Rejected")
            self.open_orders.pop(order.data._name, None)

        # # Clean up orders
        # self.open_orders = {o.data._name: o for o in self.open_orders.values() if o.alive()}
        # print(f"OPEN ORDERS: {self.open_orders}")
        
        # Write down: no pending order
        self.order = None


if __name__ == "__main__":
    #universe = INVESCO_EQUAL_WEIGHT_ETF
    universe = INVESCO_STYLE_ETF
    #universe = VANGUARD_STYLE_ETF
    #universe =BASIC_SECTOR_UNIVERSE
    #universe = SECTOR_STYLE_UNIVERSE
    #universe = EXTENDED_UNIVERSE
   # universe = RANDOM_STOCKS
    #universe = INVESCO_EQUAL_WEIGHT_ETF
    #universe = HFEA_UNIVERSE
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
    #from_date = datetime.datetime(1999, 12, 15)
    from_date = datetime.datetime(2005, 12, 15)
   # to_date = datetime.datetime(2020,2,17)
    to_date = datetime.datetime.now()

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
   # cerebro.addstrategy(BuyAndHold_1)
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

    quantstats.reports.html(returns, benchmark="SPY",
                            output="results/rotation_stats_gtaa_pyramiding_ma.html")
    cerebro.plot(iplot=False)[0][0]
