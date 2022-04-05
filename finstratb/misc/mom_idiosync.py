""" Based on the  Blitz, David, Matthias X. Hanauer, and Milan Vidojevic. 
“The Idiosyncratic Momentum Anomaly.” SSRN Scholarly Paper. Rochester, NY: Social Science Research Network, April 7, 2020. https://doi.org/10.2139/ssrn.2947044.
https://papers.ssrn.com/abstract=2947044
"""

import datetime as dt
from typing import Union

import getFamaFrenchFactors as gff
import numpy as np
import pandas as pd
import statsmodels.api as sm
from loguru import logger
from numpy_ext import rolling_apply


def rolling_residuals(dates: pd.Series, y: pd.Series, mkt_rf: pd.Series, smb: pd.Series, hml: pd.Series) -> float:
    """Calculates residals from fitting a linear regression model.
        The residuals are calculated for a given stock for the rolling window.

        y ~ a0 + b0*mkt_rf + b1*smb + b1*hml + eps


    Args:
        y (pd.Series): returns of the stock in rolling period (corrected by risk-free rate)
        mkt_rf (pd.Series): market factors (corrected by risk-free rate) for the rolling period
        smb (pd.Series): small minus big factor
        hml (pd.Series): value factor

    Returns:
        float: the residual (eps) for the last month
    """
    # logger.debug(f"Rolling dates: {dates}")
    x = np.stack([mkt_rf, smb, hml]).T
    x = sm.add_constant(x)
    model = sm.OLS(y, x).fit()

    residuals = y - model.predict(x)
    return residuals[-1]


def idiosync_momentum(res: pd.Series, **kwargs) -> float:
    """Calculates idiosyncratic momentum"""

    n_month = kwargs.get("n_month", 5)
    r = res.iloc[-n_month:-1]
    return r.sum()  # / r.std() / np.sqrt(len(r))


class IdiosyncMomentum:
    """Implemements idiosyncratic momentum estimation for multiple stocks"""

    def __init__(self, ticker_data: dict, rolling_window_coeff=36, rolling_window_mom=5):
        logger.info("Initialazing Idiosyncratic Momentum...")

        self.ticker_data = ticker_data
        self.all_tickers = ticker_data.keys()

        self.ff_factors = self.get_ff_factors()
        self.rolling_window_coeff = rolling_window_coeff
        self.rolling_window_mom = rolling_window_mom
        self._cache = {}

    def get_ff_factors(self) -> pd.DataFrame:
        """Retrieves the latest Fama-French factors"""

        logger.info("Fetching Fama-French 3-factor data...")
        factors = gff.famaFrench3Factor(frequency="m")
        return factors.set_index("date_ff_factors").resample("D").pad()

    def _estimate_momentum(self, ticker: str) -> pd.DataFrame:
        logger.info(f"Calculating idiosyncratic momentum for {ticker}...")
        t_data_monthly = (
            self.ticker_data[ticker][["close"]]
            .resample("M")
            .last()
            .assign(monthly_return=lambda df: df.pct_change())
            .fillna(0)
            .iloc[:-1]  # Get rid of last observation as month isn't finished yet
        )

        monthly_combined = (
            t_data_monthly.merge(self.ff_factors, how="left", left_index=True, right_index=True)
            .ffill()
            .sort_index(ascending=True)
            .assign(monthly_returns_less_rf=lambda df: df["monthly_return"] - df["RF"])
        )

        monthly_combined = monthly_combined.assign(
            residuals=rolling_apply( # Calculates rolling regression based on 36 month window
                rolling_residuals,
                self.rolling_window_coeff,
                monthly_combined.index.values,
                monthly_combined["monthly_returns_less_rf"].values,
                monthly_combined["Mkt-RF"].values,
                monthly_combined["SMB"].values,
                monthly_combined["HML"].values,
                n_jobs = 1 # Can increase parallelism
            )
        ).assign( 
            idiosync_momentum=lambda df: df["residuals"]
            .rolling( # Calculates rolling residual momentum
                15
            )  # Real calculation will be done on the window of less than 15 days, so this is just an upper limit.
            .apply(idiosync_momentum, kwargs={"n_month": self.rolling_window_mom})
        )
        return monthly_combined

    def get_momentum(self, ticker: str, date: Union[str, dt.datetime]) -> float:
        """Calculates residual (idiosyncratic) momentum for a giver ticker and date.

        Args:
            ticker (str): ticker name, should be in the data
            date (Union[str, dt.datetime]): Latest date for the momentum value, will return closest value not beyond the date

        Raises:
            KeyError: if requestes ticker doesn't exist in the input data.

        Returns:
            float: value of the residual momentum
        """
        
        if ticker not in self.all_tickers:
            raise KeyError(f"Data for {ticker} doesn't exist")
        
        if ticker not in self._cache:
            logger.info(f"Caching data for {ticker}...")
            self._cache[ticker] = self._estimate_momentum(ticker)

        data = self._cache[ticker][:date]
        #  print(data.tail(10))
        return data.iloc[-1]["idiosync_momentum"]


if __name__ == "__main__":
    from finstratb.misc.helpers import get_data

    data = get_data(symbols=["XLE", "XLU", "PICK", "DBB", "VDE", "QQQ", "GDX"])

    imom = IdiosyncMomentum(data)
    print(imom.get_momentum("DBB", "2021-04-01"))
