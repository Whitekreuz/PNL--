import os

def patch_app():
    with open('app.py', 'r', encoding='utf-8') as f:
        lines = f.readlines()
        
    # 1. Add make_subplots import
    for i, line in enumerate(lines):
        if line.startswith('import plotly.graph_objects as go'):
            lines.insert(i+1, "from plotly.subplots import make_subplots\n")
            break
            
    # 2. Modify tabs definition
    for i, line in enumerate(lines):
        if "tab_market, tab_position, tab_risk = st.tabs" in line:
            lines[i] = line.replace('tab_market, tab_position, tab_risk = st.tabs(["📊 市场复盘与强弱分析", "💰 头寸计算器", "🚨 风控体检单"])', 
                                    'tab_market, tab_single, tab_position, tab_risk = st.tabs(["📊 市场复盘与强弱分析", "🔍 单品种详细分析", "💰 头寸计算器", "🚨 风控体检单"])')
            break

    # 3. Insert tab_single logic right before `with tab_position:`
    insert_idx = -1
    for i, line in enumerate(lines):
        if line.startswith("with tab_position:"):
            insert_idx = i - 1
            break
            
    if insert_idx == -1:
        print("Error: Could not find 'with tab_position:'")
        return
        
    # Build tab_single logic
    code = """
# ==========================================
# Tab 1.5: 单品种详细分析
# ==========================================
with tab_single:
    st.header("🔍 单品种 60 日量价与动能分析")
    
    # 确保所需的基础数据已就绪
    try:
        sectors = list(reviewer._metadata_cache['sector'].unique())
        sectors = [s for s in sectors if str(s) != 'nan' and s.strip() != '']
    except:
        sectors = []
        
    if not sectors:
        st.warning("暂无可用的板块数据。")
    else:
        col1, col2 = st.columns(2)
        with col1:
            selected_sector = st.selectbox("1. 选择板块", options=sorted(sectors))
        
        # 筛选该板块下的品种
        symbols_in_sector = reviewer._metadata_cache[reviewer._metadata_cache['sector'] == selected_sector].index.tolist()
        
        with col2:
            selected_symbol = st.selectbox("2. 选择品种", options=sorted(symbols_in_sector))
            
        if selected_symbol:
            with st.spinner(f"正在生成 {selected_symbol} 的分析图表..."):
                try:
                    conn = sqlite3.connect(DB_PATH)
                    # 我们需要获取全市场近 80 天的收盘价，以便计算 60 天内的每日 RPS_20
                    dates_80 = pd.read_sql("SELECT DISTINCT date FROM kline_daily ORDER BY date DESC LIMIT 81", conn)['date'].tolist()
                    if len(dates_80) >= 21:
                        start_date_80 = dates_80[-1]
                        
                        # 取全市场计算 RPS
                        query_all = f"SELECT symbol, date, close FROM kline_daily WHERE is_continuous=1 AND date >= '{start_date_80}'"
                        df_all = pd.read_sql(query_all, conn)
                        
                        pivot_close = df_all.pivot(index='date', columns='symbol', values='close').ffill()
                        returns_20 = pivot_close.pct_change(periods=20).dropna()
                        
                        ranks = returns_20.rank(axis=1, ascending=True)
                        n_symbols = pivot_close.shape[1]
                        rps_history = (ranks - 1.0) / (n_symbols - 1.0) * 100.0
                        
                        # 取选定品种的 RPS
                        if selected_symbol in rps_history.columns:
                            symbol_rps = rps_history[selected_symbol]
                        else:
                            symbol_rps = pd.Series(dtype=float)
                            
                        # 取选定品种近 60 天的详细 K 线数据
                        start_date_60 = dates_80[60] if len(dates_80) > 60 else dates_80[-1]
                        query_single = f"SELECT date, open, high, low, close, volume, open_interest, settlement FROM kline_daily WHERE symbol='{selected_symbol}' AND is_continuous=1 AND date >= '{start_date_60}' ORDER BY date"
                        df_single = pd.read_sql(query_single, conn)
                        
                        if not df_single.empty:
                            # 资金流向计算
                            multiplier = float(reviewer._metadata_cache.loc[selected_symbol, 'contract_multiplier']) if selected_symbol in reviewer._metadata_cache.index else 10.0
                            df_single['prev_oi'] = df_single['open_interest'].shift(1)
                            df_single['delta_oi'] = df_single['open_interest'] - df_single['prev_oi']
                            df_single['capital_flow'] = df_single['delta_oi'] * df_single['settlement'] * multiplier
                            
                            df_single.set_index('date', inplace=True)
                            
                            # 合并 RPS
                            df_single['rps_20'] = symbol_rps
                            
                            # 剔除第一行可能缺失 delta_oi 的数据
                            df_single = df_single.dropna(subset=['close']).tail(60)
                            
                            # ====== 绘制复合图表 ======
                            fig = make_subplots(
                                rows=4, cols=1, shared_xaxes=True, 
                                vertical_spacing=0.03,
                                row_heights=[0.4, 0.2, 0.2, 0.2],
                                specs=[[{"secondary_y": False}],
                                       [{"secondary_y": True}],
                                       [{"secondary_y": False}],
                                       [{"secondary_y": False}]]
                            )
                            
                            # 1. K 线图 (Row 1)
                            fig.add_trace(go.Candlestick(
                                x=df_single.index,
                                open=df_single['open'],
                                high=df_single['high'],
                                low=df_single['low'],
                                close=df_single['close'],
                                name="K线",
                                increasing_line_color='red', decreasing_line_color='green'
                            ), row=1, col=1)
                            
                            # 2. 成交量与持仓量 (Row 2)
                            fig.add_trace(go.Bar(
                                x=df_single.index, y=df_single['volume'],
                                name="成交量", marker_color='rgba(158,202,225,0.7)'
                            ), row=2, col=1, secondary_y=False)
                            
                            fig.add_trace(go.Scatter(
                                x=df_single.index, y=df_single['open_interest'],
                                name="持仓量", line=dict(color='orange', width=2)
                            ), row=2, col=1, secondary_y=True)
                            
                            # 3. 资金流向变化 (Row 3)
                            colors = ['red' if val > 0 else 'green' for val in df_single['capital_flow']]
                            fig.add_trace(go.Bar(
                                x=df_single.index, y=df_single['capital_flow'],
                                name="资金净流入", marker_color=colors
                            ), row=3, col=1)
                            
                            # 4. RPS 20 日动能变化 (Row 4)
                            fig.add_trace(go.Scatter(
                                x=df_single.index, y=df_single['rps_20'],
                                name="RPS 20", line=dict(color='purple', width=2),
                                mode='lines+markers'
                            ), row=4, col=1)
                            
                            # 布局设置
                            fig.update_layout(
                                title=f"{selected_symbol} 过去 60 日详细复盘 (价格/量仓/资金/RPS)",
                                xaxis_rangeslider_visible=False,
                                height=900,
                                margin=dict(l=40, r=40, t=60, b=40),
                                hovermode="x unified"
                            )
                            
                            # 设置 Y 轴标题
                            fig.update_yaxes(title_text="价格", row=1, col=1)
                            fig.update_yaxes(title_text="成交量", row=2, col=1, secondary_y=False)
                            fig.update_yaxes(title_text="持仓量", row=2, col=1, secondary_y=True)
                            fig.update_yaxes(title_text="资金流向", row=3, col=1)
                            fig.update_yaxes(title_text="RPS (0-100)", range=[0, 100], row=4, col=1)
                            
                            st.plotly_chart(fig, use_container_width=True)
                        else:
                            st.warning(f"未能获取到 {selected_symbol} 的历史行情数据。")
                    else:
                        st.warning("全市场数据不足以计算 60 日 RPS (需要至少 80 个交易日的数据)。")
                        
                    conn.close()
                except Exception as e:
                    st.error(f"图表生成失败: {e}")

"""
    lines.insert(insert_idx, code + "\n")
    
    with open('app.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
        
    print("Patch applied successfully.")

if __name__ == "__main__":
    patch_app()
