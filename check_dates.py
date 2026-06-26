import sqlite3
import pandas as pd

conn = sqlite3.connect('futures_data.db')
query = "SELECT symbol, MAX(date) as max_date, COUNT(*) as cnt FROM kline_daily GROUP BY symbol ORDER BY max_date DESC"
df = pd.read_sql_query(query, conn)
print(df.head(20))
print(df.tail(20))
conn.close()
