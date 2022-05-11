""" This strategy uses a different momentum definition - idiosyncratic momentum
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
    HFEA_UNIVERSE,
    PBEAR
)

from loguru import logger
from finstratb.misc.helpers import (
    get_data,
    get_yahooquery_data_from_file,
    get_single_ticker_data_from_file,
)
from finstratb.misc.mom_idiosync import IdiosyncMomentum
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
        momentum_instance = None, 
      #   momentum=IdiosyncMomentum,  # parametrize the momentum and its period
        long_momentum_period=90,
        max_stocks=3,
        movav=bt.ind.SMA,  # parametrize the moving average and its periods
        spy_risk_ma=200,
        ticker_uptrend_ma=150,
        ticker_short_ma=50,
        # See here - https://www.investopedia.com/ask/answers/122214/what-does-end-quarter-mean-portfolio-management.asp
        #rebalance_months = [2,3,4,5,6,7,8,9,10,11,12],
        
        #rebalance_months=[2,5,8,11],
        rebalance_months=[1, 4, 7, 10],

        weight_strategy = ['equal_weight', 'equal_risk'][0],

        profit_take_pct=0.35,
       # stop_loss_pct=-0.25,

        # minimum price increase percentage for pyramid buy
        pyramid_step_pct_increase=0.001, # 0.0025,
        pyramid_n_steps=1,  # number of pyramid steps
        bbands_period=20,  # bollinger bands look back period, used for purchase decision in the
        bbands_devfactor=3,  # historical std deviation factor for BB calculation
        atr_factor_trailing_stop = 1,
        atr_max_days_from_high = 6

    )

    def __init__(self):
        self.i = 0
        self.inds = collections.defaultdict(dict)
        self.spy = self.datas[0]
        self.stocks = self.datas[1:]

        self.spy_sma200 = self.p.movav(
            self.spy.close, period=self.p.spy_risk_ma)

       # self.spy_sma50 = self.p.movav(self.spy.close, period=50)
        self.safe_assets = [d for d in self.stocks if d._name in [
            "TLT", 'GLD']]  # + [self.spy]
        self.safe_asset_weights = {"GLD": 0.35, "TLT": 0.35}  # , 'SPY':0.05}
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
        self.atr_days_since_high = {}

        for d in self.stocks:
            # self.inds[d]["long_momentum"] = self.p.momentum(
            #     d, period=self.p.long_momentum_period
            # )
            self.inds[d]["sma200"] = bt.indicators.EMA(
                d.close, period=self.p.ticker_uptrend_ma)
            self.inds[d]['bband'] = bt.indicators.BBands(
                d.close, period=self.p.bbands_period, devfactor=self.p.bbands_devfactor)
            
            self.inds[d]['atr'] = bt.indicators.ATR(d, period = 90)
            self.inds[d]["pct_change1"] = bt.indicators.PercentChange(
                d.close, period=1)

        self.add_timer(
            name="rebalance",
            when=bt.timer.SESSION_START,
            monthdays=[1], #[30], # [1],  # [30]
            monthcarry=True,
            cheat=False,
        )

        self.add_timer(
            name="risk",
            when=bt.timer.SESSION_START,
            monthdays=[
          2
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
        
        """Global risk hedge works on a monthly cadence:
            If SPY's price < SMA200, market is in confirmed downtrend, switch to ALL to safe assets. Set downtrend to True
            If SPY's price >= SMA200 and market was previously in downtrend, rebalance straight away, even before the official rebalance cadence.
        """


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
        """Function responsible for entering positions
        """
        
        if self.positioning_queue:
            # Since we can't update the original queue during iteration
            temp_queue = [(d, position)
                          for d, position in self.positioning_queue.items()]
            for d, position in temp_queue:
                current_price = d[0]
                try:

                    # if position.delay_buy and (current_price <= self.inds[d]["bband"].lines.bot[-1] or current_price >= self.inds[d]["bband"].lines.mid[-1]):
                    # If price was in downtrend according to BB and price touched the bottom limit, allow to buy
                    # If price was in downtend but crossed back to uptrend without reaching bottom, proceed with pyramid...
                    if position.delay_buy and ((current_price <= self.inds[d]["bband"].lines.bot[-1]) or (current_price >= self.inds[d]["bband"].lines.mid[-1])):
                        position.delay_buy = False
                        self.log(
                            f"\t\tBollinger Band reached bottom. Updating target price: {d._name}: Price: {d[0]:.2f}")
                        # Set current price as buy target (less the required pct increase for pyramid buying)
                        position.update_target_price(current_price)

                    # If buy is allowed, perforom pyramid purchasing based on pyramid parameters
                    if not position.delay_buy:
                        pct_allocation = position.get_allocation(
                            asset_current_price=current_price)
                        if pct_allocation > 0 and d._name not in self.open_orders:
                            self.order_target_percent(d, target=pct_allocation)
                        #    position.update_target_price(current_price=current_price)
                            position.update_target_price(
                                current_price=position.asset_target_price)
                            self.log(
                                f"\t\tPosition Ordering: {d._name}: Price: {d[0]:.2f}, Weight: {pct_allocation:.2f}")
                        
                        # 2022/02/18 - if no allocation and price is touching lower band again, update the target price
                        elif (current_price <= self.inds[d]["bband"].lines.bot[-1]):
                            position.update_target_price(
                                current_price=position.asset_target_price)
                            
                except EmptyPositionQueueException:
                    # All purchased, remove key
                    self.positioning_queue.pop(d, None)

    def next(self):
        """Function responsible for everyday operations:
            1) Purchase outstanding assets, if any.
            2) Trailing profit taking and loss cuts, if any.
        """

        self.purchase_assets_in_queue()

        posdata = [d for d, pos in self.getpositions().items() if pos]

        # if self.downtrend:
        #     return
        for d in posdata:
            self.atr_days_since_high.setdefault(d, 1)

            if (
                d.close[-1] >= self.trailing_price[d]
            ):  # this is required for max drawdown calculation for trailing stop loss
                self.trailing_price[d] = d.close[-1]
                self.atr_days_since_high[d] = 1
            else:
                self.atr_days_since_high[d]+=1
                self.atr_days_since_high[d] = min(self.p.atr_max_days_from_high, self.atr_days_since_high[d]) # limit by n days

            if d in self.buy_price and (d not in self.open_orders) and (
                d.close[-1] / self.buy_price[d] - 1.0 > self.p.profit_take_pct
            ):
                self.log(
                    f"RISK MANAGEMENT: TRAILING PROFIT TAKE for {d._name}, price: {d[-1]:.2f}"
                )
                self.close(d)
                self.positioning_queue.pop(d, None)
                continue
            #print(f"ATR: {self.inds[d]['atr'][-1]}")
            if d in self.trailing_price and (d not in self.open_orders) and (d.close[-1] <  self.trailing_price[d] - self.p.atr_factor_trailing_stop*self.inds[d]['atr'][-1]*self.atr_days_since_high[d]) and (d not in self.positioning_queue):
            #if (d.close[-1] <  d.close[-2] - self.p.atr_factor_trailing_stop * self.inds[d]['atr'][-2]):
                self.log(
                    f"RISK MANAGEMENT: ATR TRAILING STOP LOSS for {d._name}, price: {d[-1]:.2f}, ATR days high: {self.atr_days_since_high[d]}, trailing high: {self.trailing_price[d]:.2f}, ATR: {self.p.atr_factor_trailing_stop * self.inds[d]['atr'][-1]:.2f}")
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
        
        current_date = bt.num2date(self.data.datetime[0])

        
        # In recovery mode, exclude safe assets
        if recovery_mode:
            all_valid_etfs = [
                d for d in self.d_with_len 
                if d.close[-1] >= self.inds[d]["sma200"][-1] and 
                d not in self.safe_assets and 
                self.p.momentum_instance.get_momentum(d._name, current_date) >=0
            ]

        else:
            # get rid of candidates who are clearly in downtrend, regardless of momentum
            all_valid_etfs = [
                d for d in self.d_with_len 
                if d.close[-1] >= self.inds[d]["sma200"][-1] and 
            #    d not in self.safe_assets and 
                self.p.momentum_instance.get_momentum(d._name, current_date) >= 0
                ]
            

        top_long_momentums = sorted(
            all_valid_etfs, key=lambda d: self.p.momentum_instance.get_momentum(d._name, current_date), reverse=True
        )[: self.p.max_stocks+2] # +2 is only for display purposes
        
        # top_long_momentums = sorted(
        #     all_valid_etfs, key=lambda d: self.inds[d]["long_momentum"][0], reverse=True
        # )[: self.p.max_stocks+2]

        momentum_values = [
            f"{d._name}:{self.p.momentum_instance.get_momentum(d._name, current_date):.3f}" for d in top_long_momentums]

        print(f"MOMENTUM VALUES: {', '.join(momentum_values)}")
        # top_long_momentums = [d for d in top_long_momentums if d not in negative_short_momentums][:self.p.max_stocks]

        self.buy_positions = top_long_momentums[:self.p.max_stocks]

        sell_positions = [d for d in posdata if d not in self.buy_positions]
        for d in sell_positions:
            self.log(f"Exiting position: {d._name}: {d[0]:.2f}")
            self.order_target_percent(d, target=0.0)

        # Reseet positioning queue
        self.positioning_queue = {
            d: self.positioning_queue[d] for d in self.positioning_queue if d in self.buy_positions}

        if self.buy_positions:

            self.log(f"Available cash: {self.broker.get_cash():.2f}")

            if self.p.weight_strategy == 'equal_weight':
                weights = [1.0 / self.p.max_stocks] * len(self.buy_positions)
            elif self.p.weight_strategy == 'equal_risk':

                weights = self.get_erc_weights(self.buy_positions) # Equal risk contributions (risk parity)
                scale = min(len(self.buy_positions)/self.p.max_stocks, 1.0)
                if scale < 1.0:
                    self.log(f"SCALING DOWN EXPOSURE BY FACTOR: {scale:.2f}")
                    weights = [w*scale for w in weights]
            else:
                raise ValueError(f"Invalid weights strategy {self.p.weight_strategy}")

            for w, d in zip(weights, self.buy_positions):
                self.log(
                    f"Assigning positioning: {d._name}: Price: {d[0]:.2f}, Total Weight: {w:.2f}"
                )
                # self.order_target_percent( d, target=target_pct)
                # See - https://community.backtrader.com/topic/370/unexpected-additional-orders-created-rejected/8

                if (d not in posdata):  # if there is no position, enter new position using pyramid
                    position_allocation = PyramidPositioning(d, asset_initial_price=d.close[0], asset_total_target_pct=0.95*w,
                                                             step_pct_increase=self.p.pyramid_step_pct_increase, n_steps=self.p.pyramid_n_steps)

                    # stock is in downtrend, delay purchase till BB reaches the bottom
                    if d.close[0] <= self.inds[d]["bband"].lines.mid[-1]:
                        position_allocation.delay_buy = True

                    self.positioning_queue[d] = position_allocation
                    self.buy_price[d] = d.close[0]
                    self.trailing_price[d] = d.close[0]

                elif d not in self.positioning_queue:  # just rebalance if asset is fully positioned

                    o = self.order_target_percent(d, target=0.95 * w)
                #self.buy_price[d] = d.close[0]
                #self.trailing_price[d] = d.close[0]
                
    def get_erc_weights(self, buy_positions) -> list:
        try:
            rets = np.stack(
                (
                    [
                        self.inds[d]["pct_change1"].get(0, 60).tolist()
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
    #universe = INVESCO_STYLE_ETF
    #universe = VANGUARD_STYLE_ETF
    #universe =BASIC_SECTOR_UNIVERSE
    #universe = SECTOR_STYLE_UNIVERSE
    universe = EXTENDED_UNIVERSE
   # universe = RANDOM_STOCKS
    #universe = INVESCO_EQUAL_WEIGHT_ETF
    #universe = HFEA_UNIVERSE
    #universe = PBEAR
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
    # from_date = datetime.datetime(1999, 12, 15)
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
    
    imom = IdiosyncMomentum(ticker_data = data_dict)

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

    cerebro.addstrategy(Strategy, momentum_instance = imom)
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
                            output="results/idiosync_rotation_stats_gtaa_pyramid_bb_positioning_atr.html")
    cerebro.plot(iplot=False)[0][0]
