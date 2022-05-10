# 2022-05-10
* Multiple improvements in the algorithm:
    * Don't propose candidates with negative momentum
    * Reduce rolling regression window to 24 months from 36 months, to position better for the recent data
    * Scale down exposure in risk weighting algorithm, when number of stocks is smaller than required.
* Tested improvements on all universes across a range of settings
    * Different monthly day for risk management
* Potential reasons why some universes perform worse:
    * Equal weighting universe - it actually is better if compared to proper benchmark (equal weighted SP500 ETF - e.g. RSP)
    * Vanguard style ETF - due to small number of stocks in the universe, not many stocks are selected.

# 2022-05-07
* Studied sensitivity of SMA200 risk measurement timing:
    
    * On the surface, it was quite sensitive across different universes
* Discovered that main reason for sensitivity is unbalanced allocation to the safe assets:
    * TLT was 0.35, GLD = 0.1
* Given the long time correlation between TLT and GLD is low (~0.1), it makes sense to do more equal allocation.
* CHANGES:
    * Change balance of safe assets to equal weight between bonds and gold: TLT: 0.35, GLD: 0.35, cash: 0.3
    * Changed to 3*0.001 step pyramiding due to more turbulent period in general.
* After the changes, tested different universes
    * THere is still some sensitivity remaining, however most universes result in CAGR >=11% with Sharp Ratio close to or above 1.

# 2022-03-11 
* Increased profit taking to 35%. There is a small chance when profit taking is happenning at the same time as risk management selling