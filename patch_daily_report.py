import os

def patch_daily_job():
    with open('daily_job.py', 'r', encoding='utf-8') as f:
        content = f.read()

    # Find the start of generate_html_report
    target_start = "def generate_html_report():"
    target_end = 'print(f"Report successfully saved to: {report_path}")'

    start_idx = content.find(target_start)
    end_idx = content.find(target_end)

    if start_idx == -1 or end_idx == -1:
        print("Could not find start or end index for generate_html_report.")
        return

    end_idx += len(target_end)

    new_report_code = """def generate_html_report():
    print("Generating HTML report...")
    reviewer = MarketReviewer(DB_PATH)
    
    flow_res = reviewer.calculate_capital_flow()
    rps_res = reviewer.calculate_rps(periods=[1, 5, 20, 60])
    sector_indices = reviewer.generate_sector_indices(start_date=\'20250101\')
    
    conn = sqlite3.connect(DB_PATH)
    dates = pd.read_sql("SELECT DISTINCT date FROM kline_daily ORDER BY date DESC LIMIT 15", conn)[\'date\'].tolist()
    t10_date = dates[10] if len(dates) > 10 else dates[-1]
    
    rps_res_t10 = reviewer.calculate_rps(periods=[1, 5, 20, 60], target_date=t10_date)
    
    query_10d = f"SELECT symbol, date, open_interest, settlement, close FROM kline_daily WHERE is_continuous=1 AND date >= \'{t10_date}\' ORDER BY symbol, date"
    df_10d = pd.read_sql(query_10d, conn)
    conn.close()
    
    df_10d[\'prev_oi\'] = df_10d.groupby(\'symbol\')[\'open_interest\'].shift(1)
    df_10d[\'delta_oi\'] = df_10d[\'open_interest\'] - df_10d[\'prev_oi\']
    df_10d[\'multiplier\'] = df_10d[\'symbol\'].map(lambda x: float(reviewer._metadata_cache.loc[x, \'contract_multiplier\']) if x in reviewer._metadata_cache.index else 10.0)
    df_10d[\'capital_flow\'] = df_10d[\'delta_oi\'] * df_10d[\'settlement\'] * df_10d[\'multiplier\']
    df_10d[\'sector\'] = df_10d[\'symbol\'].map(lambda x: reviewer._metadata_cache.loc[x, \'sector\'] if x in reviewer._metadata_cache.index else \'未知\')
    
    flow_10d_sector = df_10d.groupby(\'sector\')[\'capital_flow\'].sum().reset_index()
    total_abs_flow_10d = flow_10d_sector[\'capital_flow\'].abs().sum()
    flow_10d_sector[\'flow_ratio_10d\'] = flow_10d_sector[\'capital_flow\'] / total_abs_flow_10d if total_abs_flow_10d > 0 else 0
    
    symbol_rps_now = rps_res.get(\'symbol_rps\', pd.DataFrame())
    symbol_rps_t10 = rps_res_t10.get(\'symbol_rps\', pd.DataFrame())
    if not symbol_rps_t10.empty and \'RPS_20\' in symbol_rps_t10.columns:
        symbol_rps_now[\'RPS_20_t10\'] = symbol_rps_now.index.map(lambda x: symbol_rps_t10.loc[x, \'RPS_20\'] if x in symbol_rps_t10.index else symbol_rps_now.loc[x, \'RPS_20\'])
    else:
        symbol_rps_now[\'RPS_20_t10\'] = symbol_rps_now[\'RPS_20\']
    symbol_rps_now[\'RPS_Change_10d\'] = symbol_rps_now[\'RPS_20\'] - symbol_rps_now[\'RPS_20_t10\']
    
    sector_rps_now = rps_res.get(\'sector_rps\', pd.DataFrame())
    sector_rps_t10 = rps_res_t10.get(\'sector_rps\', pd.DataFrame())
    if not sector_rps_now.empty and not sector_rps_t10.empty:
        sector_rps_now[\'RPS_20_t10\'] = sector_rps_now.index.map(lambda x: sector_rps_t10.loc[x, \'RPS_20\'] if x in sector_rps_t10.index else sector_rps_now.loc[x, \'RPS_20\'])
        sector_rps_now[\'RPS_Change_10d\'] = sector_rps_now[\'RPS_20\'] - sector_rps_now[\'RPS_20_t10\']
        sector_summary = pd.merge(sector_rps_now.reset_index().rename(columns={\'index\': \'sector\'}), flow_10d_sector, on=\'sector\', how=\'left\')
    else:
        sector_summary = flow_10d_sector
        
    # 获取板块各周期收益率
    sec_df_list = []
    for sec, s_data in sector_indices.items():
        s_data = s_data.copy()
        sec_df_list.append(s_data[[\'nw_index\']].rename(columns={\'nw_index\': sec}))
    sector_pivot = pd.concat(sec_df_list, axis=1).ffill().dropna()
    sec_ret_1 = sector_pivot.pct_change(periods=1).iloc[-1]
    sec_ret_5 = sector_pivot.pct_change(periods=5).iloc[-1]
    sec_ret_20 = sector_pivot.pct_change(periods=20).iloc[-1]
    
    sector_summary[\'Return_1\'] = sector_summary[\'sector\'].map(sec_ret_1)
    sector_summary[\'Return_5\'] = sector_summary[\'sector\'].map(sec_ret_5)
    sector_summary[\'Return_20\'] = sector_summary[\'sector\'].map(sec_ret_20)
    
    # 提取今日最强多头与最弱空头
    top10_long = symbol_rps_now.sort_values(by=\'RPS_20\', ascending=False).head(10)[[\'RPS_20\', \'RPS_Change_10d\', \'Return_1\', \'Return_5\', \'Return_20\', \'sector\']]
    top10_short = symbol_rps_now.sort_values(by=\'RPS_20\', ascending=True).head(10)[[\'RPS_20\', \'RPS_Change_10d\', \'Return_1\', \'Return_5\', \'Return_20\', \'sector\']]
    
    # 补充资金流数据到多空榜
    sym_flow = flow_res.get(\'symbol_flow\', pd.DataFrame()).set_index(\'symbol\')
    if not sym_flow.empty:
        top10_long[\'capital_flow\'] = top10_long.index.map(lambda x: sym_flow.loc[x, \'capital_flow\'] if x in sym_flow.index else 0.0)
        top10_short[\'capital_flow\'] = top10_short.index.map(lambda x: sym_flow.loc[x, \'capital_flow\'] if x in sym_flow.index else 0.0)
    else:
        top10_long[\'capital_flow\'] = 0.0
        top10_short[\'capital_flow\'] = 0.0
        
    def format_rps(x): return f"{x:.1f}"
    def format_rps_change(x): return f"{x:+.1f}"
    def format_ret(x): return f"{x:+.2%}"
    def format_flow_wan(x): return f"{x/1e4:,.0f} 万"
    def format_flow_yi(x): return f"{x/1e8:,.2f} 亿"
    
    long_html = top10_long.style.format({
        \'RPS_20\': format_rps, \'RPS_Change_10d\': format_rps_change, 
        \'Return_1\': format_ret, \'Return_5\': format_ret, \'Return_20\': format_ret,
        \'capital_flow\': format_flow_wan
    }).set_table_attributes(\'class="data-table"\').to_html()
    
    short_html = top10_short.style.format({
        \'RPS_20\': format_rps, \'RPS_Change_10d\': format_rps_change, 
        \'Return_1\': format_ret, \'Return_5\': format_ret, \'Return_20\': format_ret,
        \'capital_flow\': format_flow_wan
    }).set_table_attributes(\'class="data-table"\').to_html()
    
    if \'RPS_20\' in sector_summary.columns:
        sec_sum_disp = sector_summary[[\'sector\', \'RPS_20\', \'RPS_Change_10d\', \'Return_1\', \'Return_5\', \'Return_20\', \'capital_flow\', \'flow_ratio_10d\']].sort_values(by=\'RPS_20\', ascending=False)
        sec_sum_html = sec_sum_disp.style.format({
            \'RPS_20\': format_rps, \'RPS_Change_10d\': format_rps_change, 
            \'Return_1\': format_ret, \'Return_5\': format_ret, \'Return_20\': format_ret,
            \'capital_flow\': format_flow_yi, \'flow_ratio_10d\': \'{:.2%}\'
        }).set_table_attributes(\'class="data-table"\').to_html()
    else:
        sec_sum_html = "<p>N/A</p>"

    # 提取 3 个活跃板块的重点数据 (根据绝对资金流前三名)
    top_3_sectors_list = sector_summary.assign(abs_flow=sector_summary[\'capital_flow\'].abs()).sort_values(by=\'abs_flow\', ascending=False).head(3)[\'sector\'].tolist()
    
    sector_details_html = ""
    for sec in top_3_sectors_list:
        sec_symbols = reviewer._metadata_cache[reviewer._metadata_cache[\'sector\'] == sec].index.tolist()
        sec_df = symbol_rps_now[symbol_rps_now.index.isin(sec_symbols)].copy()
        
        # 获取板块中品种的日涨跌幅与5日、20日涨跌幅
        # 我们这里通过 returns_all 取最新一天
        # 或者从 df_all 宽表计算
        if not sym_flow.empty:
            sec_df[\'capital_flow\'] = sec_df.index.map(lambda x: sym_flow.loc[x, \'capital_flow\'] if x in sym_flow.index else 0.0)
        else:
            sec_df[\'capital_flow\'] = 0.0
            
        # 补充品种的 Return_1, Return_5, Return_20 (从 calculate_rps 返回的结果中合并)
        sec_df[\'Return_1\'] = sec_df.index.map(lambda x: rps_res[\'symbol_rps\'].loc[x, \'Return_1\'] if x in rps_res[\'symbol_rps\'].index else 0.0)
        sec_df[\'Return_5\'] = sec_df.index.map(lambda x: rps_res[\'symbol_rps\'].loc[x, \'Return_5\'] if x in rps_res[\'symbol_rps\'].index else 0.0)
        sec_df[\'Return_20\'] = sec_df.index.map(lambda x: rps_res[\'symbol_rps\'].loc[x, \'Return_20\'] if x in rps_res[\'symbol_rps\'].index else 0.0)
        
        sec_df_sorted = sec_df.sort_values(by=\'RPS_20\', ascending=False)[[\'RPS_20\', \'RPS_Change_10d\', \'Return_1\', \'Return_5\', \'Return_20\', \'capital_flow\']]
        sec_table_html = sec_df_sorted.style.format({
            \'RPS_20\': format_rps, \'RPS_Change_10d\': format_rps_change,
            \'Return_1\': format_ret, \'Return_5\': format_ret, \'Return_20\': format_ret,
            \'capital_flow\': format_flow_wan
        }).set_table_attributes(\'class="data-table"\').to_html()
        
        sec_flow_val = sector_summary.loc[sector_summary[\'sector\'] == sec, \'capital_flow\'].values[0]
        sector_details_html += f\"\"\"
        <div class="sector-card">
            <h3>📂 {sec} 板块明细 (今日净资金流: {format_flow_yi(sec_flow_val)})</h3>
            {sec_table_html}
        </div>
        \"\"\"

    # 4. 生成对冲与配对交易策略
    sorted_sectors = sector_summary.sort_values(by=\'RPS_20\', ascending=False)
    strongest_sec = sorted_sectors.iloc[0][\'sector\']
    weakest_sec = sorted_sectors.iloc[-1][\'sector\']
    
    strongest_sec_syms = reviewer._metadata_cache[reviewer._metadata_cache[\'sector\'] == strongest_sec].index.tolist()
    strongest_sym = symbol_rps_now[symbol_rps_now.index.isin(strongest_sec_syms)].sort_values(by=\'RPS_20\', ascending=False).index[0]
    
    weakest_sec_syms = reviewer._metadata_cache[reviewer._metadata_cache[\'sector\'] == weakest_sec].index.tolist()
    weakest_sym = symbol_rps_now[symbol_rps_now.index.isin(weakest_sec_syms)].sort_values(by=\'RPS_20\', ascending=True).index[0]
    
    hedge_strategy_html = f\"\"\"
    <div class="strategy-card">
        <h3>📊 跨板块强弱对冲建议 (Inter-Sector Hedge)</h3>
        <p>基于今日市场截面强弱数据，推荐以下跨板块阿尔法对冲配置：</p>
        <ul>
            <li><b>多头端 (Long Leg)</b>：买入最强板块 <b>{strongest_sec}</b> (板块RPS: {sorted_sectors.iloc[0][\'RPS_20\']:.1f}) 内的龙头商品 <b>{strongest_sym}</b>。</li>
            <li><b>空头端 (Short Leg)</b>：卖出最弱板块 <b>{weakest_sec}</b> (板块RPS: {sorted_sectors.iloc[-1][\'RPS_20\']:.1f}) 内的领跌商品 <b>{weakest_sym}</b>。</li>
            <li><b>对冲逻辑</b>：该配置旨在套取最强板块与最弱板块之间的宏观剪刀差红利，并通过多空配对消除全商品市场的系统性Beta波动风险。</li>
        </ul>
        
        <h3>🔄 重点活跃板块内强弱配对策略 (Intra-Sector Pairs)</h3>
        <p>针对今日资金聚焦的前三大重点板块，提供板块内的统计套利/强弱配对参考：</p>
        <table class="data-table">
            <thead>
                <tr>
                    <th>监控板块</th>
                    <th>板块内强开多 (Long)</th>
                    <th>板块内弱开空 (Short)</th>
                    <th>配对对冲逻辑</th>
                </tr>
            </thead>
            <tbody>
    \"\"\"
    
    for sec in top_3_sectors_list:
        sec_syms = reviewer._metadata_cache[reviewer._metadata_cache[\'sector\'] == sec].index.tolist()
        sec_sorted = symbol_rps_now[symbol_rps_now.index.isin(sec_syms)].sort_values(by=\'RPS_20\', ascending=False)
        if len(sec_sorted) >= 2:
            l_sym = sec_sorted.index[0]
            s_sym = sec_sorted.index[-1]
            l_rps = sec_sorted.loc[l_sym, \'RPS_20\']
            s_rps = sec_sorted.loc[s_sym, \'RPS_20\']
            hedge_strategy_html += f\"\"\"
                <tr>
                    <td><b>{sec}</b></td>
                    <td><span style="color:red;font-weight:bold;">{l_sym}</span> (RPS: {l_rps:.1f})</td>
                    <td><span style="color:green;font-weight:bold;">{s_sym}</span> (RPS: {s_rps:.1f})</td>
                    <td>做多该板块最强商品 <b>{l_sym}</b>，同时做空最弱商品 <b>{s_sym}</b>。锁定该行业内部不同品种基本面的劈叉收益。</td>
                </tr>
            \"\"\"
            
    hedge_strategy_html += \"\"\"
            </tbody>
        </table>
    </div>
    \"\"\"

    # Heatmap
    sec_df_list_hm = []
    for sec, s_data in sector_indices.items():
        s_data = s_data.copy()
        sec_df_list_hm.append(s_data[[\'nw_index\']].rename(columns={\'nw_index\': sec}))
        
    sector_pivot_hm = pd.concat(sec_df_list_hm, axis=1).ffill().dropna()
    returns_20_hm = sector_pivot_hm.pct_change(periods=20).dropna()
    last_10_returns_hm = returns_20_hm.tail(10)
    ranks_hm = last_10_returns_hm.rank(axis=1, ascending=True)
    n_sectors_hm = sector_pivot_hm.shape[1]
    rps_10d_history_hm = (ranks_hm - 1.0) / (n_sectors_hm - 1.0) * 100.0
    
    rps_heatmap_df = rps_10d_history_hm.T
    rps_heatmap_df = rps_heatmap_df.sort_values(by=rps_heatmap_df.columns[-1], ascending=False)
    
    if isinstance(rps_heatmap_df.columns, pd.DatetimeIndex):
        rps_heatmap_df.columns = rps_heatmap_df.columns.strftime(\'%Y-%m-%d\')
    else:
        rps_heatmap_df.columns = [str(c)[:10] for c in rps_heatmap_df.columns]
        
    styled_heatmap = rps_heatmap_df.style.background_gradient(cmap=\'RdYlGn_r\', axis=None, vmin=0, vmax=100).format("{:.1f}").set_table_attributes(\'class="data-table"\')
    heatmap_html = styled_heatmap.to_html()

    today_str = datetime.now().strftime(\'%Y-%m-%d\')
    html_content = f\"\"\"
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <title>收盘量化复盘与对冲决策报告 - {today_str}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding: 30px; color: #333; background-color: #f4f6f9; line-height: 1.6; }}
        h1 {{ border-bottom: 3px solid #1f3a93; padding-bottom: 12px; color: #1f3a93; margin-top: 0; }}
        h2 {{ margin-top: 40px; color: #2c3e50; border-left: 5px solid #1f3a93; padding-left: 12px; font-size: 20px; }}
        h3 {{ margin-top: 10px; color: #34495e; font-size: 16px; }}
        .data-table {{ border-collapse: collapse; width: 100%; margin-top: 15px; background-color: #fff; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border-radius: 6px; overflow: hidden; }}
        .data-table th, .data-table td {{ border: 1px solid #eef2f7; padding: 12px 15px; text-align: right; font-size: 14px; }}
        .data-table th {{ background-color: #ebeff5; font-weight: bold; text-align: center; color: #2c3e50; }}
        .data-table tr:hover {{ background-color: #f8fafc; }}
        .flex-container {{ display: flex; gap: 25px; margin-top: 20px; }}
        .flex-child {{ flex: 1; min-width: 0; }}
        .strategy-card {{ background-color: #eef5ff; border: 1px solid #bce0fd; border-radius: 8px; padding: 20px; margin-top: 20px; }}
        .strategy-card ul {{ padding-left: 20px; }}
        .strategy-card li {{ margin-bottom: 8px; }}
        .sector-card {{ background-color: #ffffff; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px; margin-top: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.02); }}
    </style>
    </head>
    <body>
        <h1>📊 收盘量化复盘与对冲决策报告 ({today_str})</h1>
        
        <h2>🛡️ 截面强弱多空对冲交易策略 (Quant Hedge & Pairs Strategy)</h2>
        {hedge_strategy_html}
        
        <h2>📈 各大板块强弱与资金流向总览 (持仓加权)</h2>
        {sec_sum_html}
        
        <div class="flex-container">
            <div class="flex-child">
                <h2>🔥 全市场多头领涨榜 Top 10 (RPS 20)</h2>
                {long_html}
            </div>
            <div class="flex-child">
                <h2>🧊 全市场空头领跌榜 Top 10 (RPS 20)</h2>
                {short_html}
            </div>
        </div>
        
        <h2>📂 今日最活跃前三大板块深度复盘 (板块个股明细)</h2>
        {sector_details_html}
        
        <h2>🌡️ 全市场各大板块近 10 个交易日 RPS 变动热力图</h2>
        {heatmap_html}
        
        <p style="margin-top: 60px; font-size: 13px; color: #7f8c8d; text-align: center; border-top: 1px dashed #ccc; padding-top: 20px;">
            本报告由商品期货 VaR 头寸资金管理系统定时任务引擎自动生成。仅供量化交易决策参考。
        </p>
    </body>
    </html>
    \"\"\"
    
    os.makedirs(REPORTS_DIR, exist_ok=True)
    report_path = os.path.join(REPORTS_DIR, f"daily_report_{today_str}.html")
    with open(report_path, \'w\', encoding=\'utf-8\') as f:
        f.write(html_content)
    print(f"Report successfully saved to: {report_path}")"""

    # Do the replace
    patched_content = content[:start_idx] + new_report_code + content[end_idx:]

    with open('daily_job.py', 'w', encoding='utf-8') as f:
        f.write(patched_content)
        
    print("daily_job.py report patched successfully.")

if __name__ == "__main__":
    patch_daily_job()
