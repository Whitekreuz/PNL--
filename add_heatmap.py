import os

def insert_code():
    with open('app.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    insert_idx = -1
    for i, line in enumerate(lines):
        if "st.subheader(\"各大板块强弱与 10 日资金流占比\")" in line:
            insert_idx = i - 1
            break
            
    if insert_idx == -1:
        print("Could not find insertion point!")
        return
        
    code_to_insert = """
        # --- 新增：最强最弱 Top 10 品种近 10 日 RPS 热力图 ---
        st.subheader("最强与最弱 Top 10 品种近 10 个交易日 RPS 热力图")
        try:
            conn = sqlite3.connect(DB_PATH)
            dates_31 = pd.read_sql("SELECT DISTINCT date FROM kline_daily ORDER BY date DESC LIMIT 31", conn)['date'].tolist()
            if len(dates_31) >= 21:
                start_date = dates_31[-1]
                query_all = f"SELECT symbol, date, close FROM kline_daily WHERE is_continuous=1 AND date >= '{start_date}'"
                df_all = pd.read_sql(query_all, conn)
                
                pivot_close = df_all.pivot(index='date', columns='symbol', values='close').ffill()
                returns_20 = pivot_close.pct_change(periods=20).dropna()
                last_10_returns = returns_20.tail(10)
                
                ranks = last_10_returns.rank(axis=1, ascending=True)
                n_symbols = pivot_close.shape[1]
                rps_10d_history = (ranks - 1.0) / (n_symbols - 1.0) * 100.0
                
                top_symbols = list(top10_long.index) + list(top10_short.index)
                available_symbols = [s for s in top_symbols if s in rps_10d_history.columns]
                
                rps_heatmap_df = rps_10d_history[available_symbols].T
                rps_heatmap_df = rps_heatmap_df.sort_values(by=rps_heatmap_df.columns[-1], ascending=False)
                
                if isinstance(rps_heatmap_df.columns, pd.DatetimeIndex):
                    rps_heatmap_df.columns = rps_heatmap_df.columns.strftime('%Y-%m-%d')
                else:
                    rps_heatmap_df.columns = [str(c)[:10] for c in rps_heatmap_df.columns]
                    
                styled_heatmap = rps_heatmap_df.style.background_gradient(cmap='RdYlGn_r', axis=None, vmin=0, vmax=100).format("{:.1f}")
                st.dataframe(styled_heatmap, use_container_width=True)
            else:
                st.info("数据不足 30 个交易日，无法生成单品种 RPS 热力图。")
            conn.close()
        except Exception as e:
            st.error(f"生成单品种热力图失败: {e}")
            
"""
    lines.insert(insert_idx, code_to_insert)
    
    with open('app.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
        
    print("Code inserted successfully.")

if __name__ == "__main__":
    insert_code()
