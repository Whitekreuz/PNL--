import sqlite3
import pandas as pd
import os

db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'futures_data.db')
conn = sqlite3.connect(db_path)
df = pd.read_sql("SELECT symbol, sector FROM commodity_metadata WHERE sector IN ('其它', '未知')", conn)
print(df)
conn.close()
