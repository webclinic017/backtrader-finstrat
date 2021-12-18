# Inspired by https://www.optimizedportfolio.com/all-weather-portfolio/

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import collections
import datetime
from typing import Dict, List

import numpy as np
import pandas as pd
import pyfolio as pf
import quantstats
from loguru import logger
from finstratb.misc.helpers import get_data
#from mretf.helpers import edhec_risk_kit as erk

import backtrader as bt


UNIVERSE = ['UPRO', 'TMF']
#UNIVERSE = ['SSO', 'UBT', 'UST', 'DIG', 'UGL']

class AllWeatherStatic(bt.Strategy):
    params = dict(        
        
        allocations = {'UPRO': 0.55, # Stocks
                       'TMF': 0.45, # Long-term treasuries
                    #    'VGIT': 0.15, # intermediate treasuries
                    #    'IAU': 0.08, # Gold
                    #    'PDBC': 0.07 # Commodities
                       },
        


        rebalance_months=[1, 2,3,4,5,6,7,8,9,10,11,12],
      #  rebalance_months=[1, 4, 7, 10],

        
        # rebalance_months = [2,5,8,11]
    )

    def __init__(self):
        self.i = 0
        self.inds = collections.defaultdict(dict)
        self.spy = self.datas[0]
        self.stocks = self.datas[1:]
        self.d_with_len = self.stocks

        self.spy_sma200 = bt.indicators.SMA(self.spy.close, period=200)
       
        for d in self.stocks:
            self.inds[d]["sma200"] = bt.indicators.SMA(d.close, period=200)
            self.inds[d]["pct_change1"] = bt.indicators.PercentChange(d.close, period=1)

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

    
                
    def next(self):
        
        pass


            

    def rebalance_portfolio(self):
        # if self.spy < self.spy_sma200:
        #     self.log("NO REBALANCE DUE TO MARKET DOWNTURN")
        #     return 
        
        all_valid_tickers = self.d_with_len

        for d in all_valid_tickers:
            target_weight = self.p.allocations[d._name]
            self.order_target_percent(d, target=0.98*target_weight)

    def notify_timer(self, timer, when, *args, **kwargs):
        if kwargs["name"] == "rebalance":
            if when.month in self.p.rebalance_months:
                self.log(f"====== REBALANCING ======")
                self.rebalance_portfolio()
        elif kwargs["name"] == 'risk':
            self.hedge_risk()

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
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(100000.0)

    # https://www.backtrader.com/docu/broker/ - see cheat-on-close, prevents buy/sell at the same bar
    # matching a `Market` order to the closing price of the bar in which
    # the order was issued. This is actually *cheating*, because the bar
    # is *closed* and any order should first be matched against the prices
    # in the next bar
    cerebro.broker.set_coc(True)  # Cheat on close

    cerebro.broker.set_checksubmit(checksubmit=False)

    data_dict = get_data(symbols=["SPY"] + UNIVERSE)

    for symbol, data in data_dict.items():
        # print(data)
        logger.info(f"Adding '{symbol}' to Cerebro.")
        cerebro.adddata(
            bt.feeds.PandasData(
                dataname=data,
                fromdate=datetime.datetime(2009, 12, 15),
                todate=datetime.datetime(2021,11,30),
                name=symbol,
                plot = False
            )
        )

    cerebro.addobserver(bt.observers.Value)
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, riskfreerate=0.0)
    cerebro.addanalyzer(bt.analyzers.Returns)
    cerebro.addanalyzer(bt.analyzers.DrawDown)
    # cerebro.addanalyzer(bt.analyzers.TradeAnalyzer)
    cerebro.addanalyzer(bt.analyzers.PyFolio)

    print("Starting Portfolio Value: %.2f" % cerebro.broker.getvalue())

    cerebro.addstrategy(AllWeatherStatic)
    #  cerebro.addstrategy(BuyAndHold_1)
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

    quantstats.reports.html(returns, benchmark="SPY", output="results/hfea_unhedged.html")
    cerebro.plot(iplot=False)[0][0]