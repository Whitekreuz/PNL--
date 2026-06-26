import sqlite3
import pandas as pd
from market_reviewer import MarketReviewer

reviewer = MarketReviewer('futures_data.db')
rps_res = reviewer.calculate_rps(periods=[20, 60])
symbol_rps_now = rps_res['symbol_rps']
print("symbol_rps_now with RPS_20 not null:")
print(symbol_rps_now[symbol_rps_now['RPS_20'].notna()])
print("\nsymbol_rps_now with RPS_20 IS null:")
print(symbol_rps_now[symbol_rps_now['RPS_20'].isna()].head())
