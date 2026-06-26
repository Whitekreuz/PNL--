import sqlite3
import pandas as pd
from market_reviewer import MarketReviewer

reviewer = MarketReviewer('futures_data.db')
df_10d = reviewer.get_10d_flow()
print(f"df_10d shape: {df_10d.shape}")
print(df_10d['symbol'].unique())

if not df_10d.empty:
    symbol_rps_now = df_10d[df_10d['date'] == df_10d['date'].max()].set_index('symbol')
    print(f"symbol_rps_now shape: {symbol_rps_now.shape}")
    print(symbol_rps_now.index.tolist())
    print(symbol_rps_now[['RPS_20', 'sector']].dropna())
