import sqlite3
import pandas as pd

conn = sqlite3.connect('d:/datasci/PNL日志/futures_data.db')
df = pd.read_sql("SELECT symbol, sector FROM commodity_metadata WHERE sector IN ('其它', '未知')", conn)
print(df)
conn.close()
