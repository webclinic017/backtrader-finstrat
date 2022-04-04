import backtrader as bt
from scipy.stats import linregress
import numpy as np
import getFamaFrenchFactors as gff
import datetime as dt

class Momentum(bt.Indicator):
    lines = ('trend',)
    params = {'period': 90}
    
    def __init__(self):
        self.addminperiod(self.params.period)
    
    def next(self):
        log_ts = np.log(self.data.get(size=self.p.period))
  #      returns = self.data.get(size=self.p.period)
        x = np.arange(len(log_ts))
        slope, _, rvalue, pvalue, stderr = linregress(x, log_ts)
       # score = (1 + slope) ** 252
        #annualized_slope = np.power(np.exp(slope), 252)-1
        annualized_slope =  (1 + slope) ** 252 # np.power(np.exp(slope), 252)-1
                
        # This implementation penalizes less volatile momentum stocks
        self.lines.trend[0] = annualized_slope * np.abs(rvalue) 
        
        # This implementation results in higher sharpe ratio with lower returns
        #self.lines.trend[0] = annualized_slope  * np.abs(rvalue) / stderr
        
