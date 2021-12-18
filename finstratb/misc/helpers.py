
from yahooquery import Ticker
from typing import List, Dict
import pandas as pd
from loguru import logger

def get_data(symbols: List[str], period = '35y',from_file = None, **kwargs) -> Dict[str, pd.DataFrame]:

    logger.info(f"Fetching {','.join(symbols)}")
    data = (Ticker(symbols = symbols)
                .history(period=period, **kwargs)
                .reset_index()
                )
    data['date'] = pd.to_datetime(data['date'])
   # data.to_csv("etf_data.csv", index=False)
    res_data = {s: (data.loc[data['symbol'] == s,['date','volume', 'open', 'high','low', 'adjclose']]
                 .rename(columns = {'adjclose':'close'})
                 .set_index('date')) for s in data['symbol'].unique()}
    return res_data

def get_yahooquery_data_from_file(file_name: str) -> Dict[str, pd.DataFrame]:
    
    logger.info(f"Fetching from {file_name}")
    data = pd.read_csv(file_name, parse_dates=['date'])
    
    res_data = {s: (data.loc[data['symbol'] == s,['date','volume', 'open', 'high','low', 'adjclose']]
                 .rename(columns = {'adjclose':'close'})
                 .set_index('date')) for s in data['symbol'].unique()}
    return res_data

def get_single_ticker_data_from_file(file_name: str) -> pd.DataFrame:
    data = (pd
            .read_csv(file_name, parse_dates=['date'])
            .loc[:, ['date','volume', 'open', 'high','low', 'close']]
            .set_index('date')
    )
            
    return data

    

        

if __name__ == '__main__':
        from universe_11 import UNIVERSE
       # d = get_data(symbols=['SPY'])
        d = get_yahooquery_data_from_file(file_name="./mretf/backtrader/data/etf_data.zip")
        d2 = get_single_ticker_data_from_file(file_name="./mretf/backtrader/data/SPY.csv")
        print(d)
        print(d2)