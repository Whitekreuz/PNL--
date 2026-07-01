import os
import sqlite3
import pandas as pd
from datetime import datetime
import sys

# Ensure local imports work regardless of cwd
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.append(BASE_DIR)

from data_fetcher import sync_data
from market_reviewer import MarketReviewer

DB_PATH = os.path.join(BASE_DIR, "futures_data.db")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")

def generate_html_report():
    print("Generating HTML report...")
    reviewer = MarketReviewer(DB_PATH)
    
    flow_res = reviewer.calculate_capital_flow()
    # 启用1, 5, 20, 60周期RPS计算
    rps_res = reviewer.calculate_rps(periods=[1, 5, 20, 60])
    sector_indices = reviewer.generate_sector_indices(start_date='20250101')
    
    conn = sqlite3.connect(DB_PATH)
    dates = pd.read_sql("SELECT DISTINCT date FROM kline_daily ORDER BY date DESC LIMIT 15", conn)['date'].tolist()
    t10_date = dates[10] if len(dates) > 10 else dates[-1]
    
    rps_res_t10 = reviewer.calculate_rps(periods=[1, 5, 20, 60], target_date=t10_date)
    
    query_10d = f"SELECT symbol, date, open_interest, settlement, close FROM kline_daily WHERE is_continuous=1 AND date >= '{t10_date}' ORDER BY symbol, date"
    df_10d = pd.read_sql(query_10d, conn)
    conn.close()
    
    df_10d['prev_oi'] = df_10d.groupby('symbol')['open_interest'].shift(1)
    df_10d['delta_oi'] = df_10d['open_interest'] - df_10d['prev_oi']
    df_10d['multiplier'] = df_10d['symbol'].map(lambda x: float(reviewer._metadata_cache.loc[x, 'contract_multiplier']) if x in reviewer._metadata_cache.index else 10.0)
    df_10d['capital_flow'] = df_10d['delta_oi'] * df_10d['settlement'] * df_10d['multiplier']
    df_10d['sector'] = df_10d['symbol'].map(lambda x: reviewer._metadata_cache.loc[x, 'sector'] if x in reviewer._metadata_cache.index else '未知')
    
    flow_10d_sector = df_10d.groupby('sector')['capital_flow'].sum().reset_index()
    total_abs_flow_10d = flow_10d_sector['capital_flow'].abs().sum()
    flow_10d_sector['flow_ratio_10d'] = flow_10d_sector['capital_flow'] / total_abs_flow_10d if total_abs_flow_10d > 0 else 0
    
    symbol_rps_now = rps_res.get('symbol_rps', pd.DataFrame())
    symbol_rps_t10 = rps_res_t10.get('symbol_rps', pd.DataFrame())
    
    # 计算 RPS_5 和 RPS_20 的 10 日变化量 (加速度)
    for period in [5, 20]:
        if not symbol_rps_t10.empty and f'RPS_{period}' in symbol_rps_t10.columns:
            symbol_rps_now[f'RPS_{period}_t10'] = symbol_rps_now.index.map(lambda x: symbol_rps_t10.loc[x, f'RPS_{period}'] if x in symbol_rps_t10.index else symbol_rps_now.loc[x, f'RPS_{period}'])
        else:
            symbol_rps_now[f'RPS_{period}_t10'] = symbol_rps_now[f'RPS_{period}']
        symbol_rps_now[f'RPS_{period}_Change_10d'] = symbol_rps_now[f'RPS_{period}'] - symbol_rps_now[f'RPS_{period}_t10']
        
    sector_rps_now = rps_res.get('sector_rps', pd.DataFrame())
    sector_rps_t10 = rps_res_t10.get('sector_rps', pd.DataFrame())
    
    for period in [5, 20]:
        if not sector_rps_now.empty and not sector_rps_t10.empty:
            sector_rps_now[f'RPS_{period}_t10'] = sector_rps_now.index.map(lambda x: sector_rps_t10.loc[x, f'RPS_{period}'] if x in sector_rps_t10.index else sector_rps_now.loc[x, f'RPS_{period}'])
            sector_rps_now[f'RPS_{period}_Change_10d'] = sector_rps_now[f'RPS_{period}'] - sector_rps_now[f'RPS_{period}_t10']
            
    if not sector_rps_now.empty:
        sector_summary = pd.merge(sector_rps_now.reset_index().rename(columns={'index': 'sector'}), flow_10d_sector, on='sector', how='left')
    else:
        sector_summary = flow_10d_sector
        
    # 获取板块各周期加权收益率
    sec_df_list = []
    for sec, s_data in sector_indices.items():
        s_data = s_data.copy()
        sec_df_list.append(s_data[['nw_index']].rename(columns={'nw_index': sec}))
    sector_pivot = pd.concat(sec_df_list, axis=1).ffill().dropna()
    sec_ret_1 = sector_pivot.pct_change(periods=1).iloc[-1]
    sec_ret_5 = sector_pivot.pct_change(periods=5).iloc[-1]
    sec_ret_20 = sector_pivot.pct_change(periods=20).iloc[-1]
    
    sector_summary['Return_1'] = sector_summary['sector'].map(sec_ret_1)
    sector_summary['Return_5'] = sector_summary['sector'].map(sec_ret_5)
    sector_summary['Return_20'] = sector_summary['sector'].map(sec_ret_20)
    
    # 按照用户要求，多头领涨和空头领跌榜均以短期强弱 RPS_5 进行排序
    top10_long = symbol_rps_now.sort_values(by='RPS_5', ascending=False).head(10)[['RPS_1', 'RPS_5', 'RPS_20', 'RPS_5_Change_10d', 'Return_1', 'Return_5', 'sector']]
    top10_short = symbol_rps_now.sort_values(by='RPS_5', ascending=True).head(10)[['RPS_1', 'RPS_5', 'RPS_20', 'RPS_5_Change_10d', 'Return_1', 'Return_5', 'sector']]
    
    # 补充个股当日净资金流向
    sym_flow = flow_res.get('symbol_flow', pd.DataFrame()).set_index('symbol')
    for df_top in [top10_long, top10_short]:
        if not sym_flow.empty:
            df_top['capital_flow'] = df_top.index.map(lambda x: sym_flow.loc[x, 'capital_flow'] if x in sym_flow.index else 0.0)
        else:
            df_top['capital_flow'] = 0.0
            
    def format_rps(x): return f"{x:.1f}"
    def format_rps_change(x): return f"{x:+.1f}"
    def format_ret(x): return f"{x:+.2%}"
    def format_flow_wan(x): return f"{x/1e4:,.0f} 万"
    def format_flow_yi(x): return f"{x/1e8:,.2f} 亿"
    
    long_html = top10_long.style.format({
        'RPS_1': format_rps, 'RPS_5': format_rps, 'RPS_20': format_rps,
        'RPS_5_Change_10d': format_rps_change,
        'Return_1': format_ret, 'Return_5': format_ret,
        'capital_flow': format_flow_wan
    }).set_table_attributes('class="data-table"').to_html()
    
    short_html = top10_short.style.format({
        'RPS_1': format_rps, 'RPS_5': format_rps, 'RPS_20': format_rps,
        'RPS_5_Change_10d': format_rps_change,
        'Return_1': format_ret, 'Return_5': format_ret,
        'capital_flow': format_flow_wan
    }).set_table_attributes('class="data-table"').to_html()
    
    # 各板块大表按照 RPS_5 降序排列展示
    if 'RPS_5' in sector_summary.columns:
        sec_sum_disp = sector_summary[['sector', 'RPS_1', 'RPS_5', 'RPS_20', 'RPS_5_Change_10d', 'Return_1', 'Return_5', 'Return_20', 'capital_flow', 'flow_ratio_10d']].sort_values(by='RPS_5', ascending=False)
        sec_sum_html = sec_sum_disp.style.format({
            'RPS_1': format_rps, 'RPS_5': format_rps, 'RPS_20': format_rps,
            'RPS_5_Change_10d': format_rps_change, 
            'Return_1': format_ret, 'Return_5': format_ret, 'Return_20': format_ret,
            'capital_flow': format_flow_yi, 'flow_ratio_10d': '{:.2%}'
        }).set_table_attributes('class="data-table"').to_html()
    else:
        sec_sum_html = "<p>N/A</p>"

    # 提取今日最强势的 3 个板块进行明细复盘 (依据板块 RPS_5 降序前三名)
    top_3_sectors_list = sector_summary.sort_values(by='RPS_5', ascending=False).head(3)['sector'].tolist()
    
    sector_details_html = ""
    for sec in top_3_sectors_list:
        sec_symbols = reviewer._metadata_cache[reviewer._metadata_cache['sector'] == sec].index.tolist()
        sec_df = symbol_rps_now[symbol_rps_now.index.isin(sec_symbols)].copy()
        
        if not sym_flow.empty:
            sec_df['capital_flow'] = sec_df.index.map(lambda x: sym_flow.loc[x, 'capital_flow'] if x in sym_flow.index else 0.0)
        else:
            sec_df['capital_flow'] = 0.0
            
        sec_df['Return_1'] = sec_df.index.map(lambda x: rps_res['symbol_rps'].loc[x, 'Return_1'] if x in rps_res['symbol_rps'].index else 0.0)
        sec_df['Return_5'] = sec_df.index.map(lambda x: rps_res['symbol_rps'].loc[x, 'Return_5'] if x in rps_res['symbol_rps'].index else 0.0)
        
        # 板块内个股明细按 RPS_5 降序排列
        sec_df_sorted = sec_df.sort_values(by='RPS_5', ascending=False)[['RPS_1', 'RPS_5', 'RPS_20', 'RPS_5_Change_10d', 'Return_1', 'Return_5', 'capital_flow']]
        sec_table_html = sec_df_sorted.style.format({
            'RPS_1': format_rps, 'RPS_5': format_rps, 'RPS_20': format_rps,
            'RPS_5_Change_10d': format_rps_change,
            'Return_1': format_ret, 'Return_5': format_ret,
            'capital_flow': format_flow_wan
        }).set_table_attributes('class="data-table"').to_html()
        
        sec_flow_val = sector_summary.loc[sector_summary['sector'] == sec, 'capital_flow'].values[0]
        sector_details_html += f"""
        <div class="sector-card">
            <h3>📂 {sec} 板块明细 (今日净资金流: {format_flow_yi(sec_flow_val)}, 板块RPS_5: {sector_summary.loc[sector_summary['sector'] == sec, 'RPS_5'].values[0]:.1f})</h3>
            <div class="table-container">
                {sec_table_html}
            </div>
        </div>
        """

    # 4. 基于 RPS_5 的对冲与配对交易策略
    sorted_sectors = sector_summary.sort_values(by='RPS_5', ascending=False)
    strongest_sec = sorted_sectors.iloc[0]['sector']
    weakest_sec = sorted_sectors.iloc[-1]['sector']
    
    # 最强板块中最强品种 (基于 RPS_5)
    strongest_sec_syms = reviewer._metadata_cache[reviewer._metadata_cache['sector'] == strongest_sec].index.tolist()
    strongest_sym = symbol_rps_now[symbol_rps_now.index.isin(strongest_sec_syms)].sort_values(by='RPS_5', ascending=False).index[0]
    
    # 最弱板块中最弱品种 (基于 RPS_5)
    weakest_sec_syms = reviewer._metadata_cache[reviewer._metadata_cache['sector'] == weakest_sec].index.tolist()
    weakest_sym = symbol_rps_now[symbol_rps_now.index.isin(weakest_sec_syms)].sort_values(by='RPS_5', ascending=True).index[0]
    
    # 中期市场板块结构分析 (RPS_20 研判)
    mid_leaders = sector_summary[sector_summary['RPS_20'] >= 70].sort_values(by='RPS_20', ascending=False)['sector'].tolist()
    mid_accelerating = sector_summary.sort_values(by='RPS_20_Change_10d', ascending=False).head(2)
    
    mid_analysis_text = ""
    if mid_leaders:
        mid_analysis_text += f"目前中期趋势最强（RPS_20 &ge; 70）的领涨板块为：<b>{', '.join(mid_leaders)}</b>；"
    else:
        mid_analysis_text += "目前暂无中期绝对强势的领涨板块；"
        
    acc_sectors_text = []
    for _, row in mid_accelerating.iterrows():
        acc_sectors_text.append(f"<b>{row['sector']}</b> (RPS_20 10天加速 {row['RPS_20_Change_10d']:+.1f})")
    mid_analysis_text += f"在中期动能变化（RPS_20 加速度）上，近期提升最显著的板块为：{', '.join(acc_sectors_text)}。"
    
    # 寻找短中期动能背离（RPS_5 高但 RPS_20 低的超跌爆发板块）
    divergent_sectors = sector_summary[(sector_summary['RPS_5'] >= 70) & (sector_summary['RPS_20'] < 50)]['sector'].tolist()
    if divergent_sectors:
        mid_analysis_text += f" 值得注意的是，<b>{', '.join(divergent_sectors)}</b> 板块出现短中期动能背离（RPS_5已攀升至70以上，但中期的RPS_20仍处于50以下），表明这属于<b>新一轮短线资金超跌抢筹或题材爆发</b>的初期阶段，可积极布局短线阿尔法头寸。"

    hedge_strategy_html = f"""
    <div class="strategy-card">
        <h3>📊 跨板块强弱对冲建议 (Inter-Sector Hedge - 基于今日 RPS_5)</h3>
        <p>基于今日<b>短期相对强度 (RPS_5)</b>数据，推荐以下跨板块阿尔法对冲配置以抵御系统性波动风险：</p>
        <ul>
            <li><b>多头端 (Long Leg)</b>：买入短期最强板块 <b>{strongest_sec}</b> 中的龙头商品 <b>{strongest_sym}</b>。</li>
            <li><b>空头端 (Short Leg)</b>：卖出短期最弱板块 <b>{weakest_sec}</b> 中的领跌商品 <b>{weakest_sym}</b>。</li>
            <li><b>对冲逻辑</b>：做多短期资金共振最强烈、突破爆发性最好的强动能品种；做空行业基本面下行且短期资金正加速流出的弱势品种。</li>
        </ul>
        
        <h3>🔄 重点活跃板块内强弱配对对冲 (Intra-Sector Pairs - 基于今日 RPS_5)</h3>
        <p>针对本交易日短期动能最前列的前三大板块，提供板块内的强弱对冲套利组合：</p>
        <div class="table-container">
            <table class="data-table">
                <thead>
                    <tr>
                        <th>监控板块</th>
                        <th>多头端 (Long Strong)</th>
                        <th>空头端 (Short Weak)</th>
                        <th>配对对冲逻辑</th>
                    </tr>
                </thead>
                <tbody>
    """
    
    for sec in top_3_sectors_list:
        sec_syms = reviewer._metadata_cache[reviewer._metadata_cache['sector'] == sec].index.tolist()
        sec_sorted = symbol_rps_now[symbol_rps_now.index.isin(sec_syms)].sort_values(by='RPS_5', ascending=False)
        if len(sec_sorted) >= 2:
            l_sym = sec_sorted.index[0]
            s_sym = sec_sorted.index[-1]
            l_rps = sec_sorted.loc[l_sym, 'RPS_5']
            s_rps = sec_sorted.loc[s_sym, 'RPS_5']
            hedge_strategy_html += f"""
                    <tr>
                        <td><b>{sec}</b></td>
                        <td><span style="color:red;font-weight:bold;">{l_sym}</span> (RPS_5: {l_rps:.1f})</td>
                        <td><span style="color:green;font-weight:bold;">{s_sym}</span> (RPS_5: {s_rps:.1f})</td>
                        <td>做多该板块内短期最强势的 <b>{l_sym}</b>，做空最弱势的 <b>{s_sym}</b>。套取由于板块内部基本面差异引发的短线估值劈叉利润。</td>
                    </tr>
            """
            
    hedge_strategy_html += """
                </tbody>
            </table>
        </div>
    </div>
    """

    # Heatmap (展示 RPS_5 近 10 日历史变化)
    sec_df_list_hm = []
    for sec, s_data in sector_indices.items():
        s_data = s_data.copy()
        sec_df_list_hm.append(s_data[['nw_index']].rename(columns={'nw_index': sec}))
        
    sector_pivot_hm = pd.concat(sec_df_list_hm, axis=1).ffill().dropna()
    returns_5_hm = sector_pivot_hm.pct_change(periods=5).dropna()
    last_10_returns_hm = returns_5_hm.tail(10)
    ranks_hm = last_10_returns_hm.rank(axis=1, ascending=True)
    n_sectors_hm = sector_pivot_hm.shape[1]
    rps_10d_history_hm = (ranks_hm - 1.0) / (n_sectors_hm - 1.0) * 100.0
    
    rps_heatmap_df = rps_10d_history_hm.T
    rps_heatmap_df = rps_heatmap_df.sort_values(by=rps_heatmap_df.columns[-1], ascending=False)
    
    if isinstance(rps_heatmap_df.columns, pd.DatetimeIndex):
        rps_heatmap_df.columns = rps_heatmap_df.columns.strftime('%Y-%m-%d')
    else:
        rps_heatmap_df.columns = [str(c)[:10] for c in rps_heatmap_df.columns]
        
    styled_heatmap = rps_heatmap_df.style.background_gradient(cmap='RdYlGn_r', axis=None, vmin=0, vmax=100).format("{:.1f}").set_table_attributes('class="data-table"')
    heatmap_html = styled_heatmap.to_html()

    today_str = datetime.now().strftime('%Y-%m-%d')
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <title>量化收盘复盘与对冲决策报告 - {today_str}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; padding: 30px; color: #333; background-color: #f4f6f9; line-height: 1.6; }}
        h1 {{ border-bottom: 3px solid #1f3a93; padding-bottom: 12px; color: #1f3a93; margin-top: 0; }}
        h2 {{ margin-top: 40px; color: #2c3e50; border-left: 5px solid #1f3a93; padding-left: 12px; font-size: 20px; }}
        h3 {{ margin-top: 10px; color: #34495e; font-size: 16px; }}
        .table-container {{ overflow-x: auto; margin-top: 15px; background-color: #fff; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border-radius: 6px; border: 1px solid #eef2f7; }}
        .data-table {{ border-collapse: collapse; width: 100%; border: none; }}
        .data-table th, .data-table td {{ border: 1px solid #eef2f7; padding: 12px 15px; text-align: right; font-size: 14px; }}
        .data-table th {{ background-color: #ebeff5; font-weight: bold; text-align: center; color: #2c3e50; border-bottom: 2px solid #cbd5e1; }}
        .data-table tr:hover {{ background-color: #f8fafc; }}
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
        
        <h2>🌡️ 全市场各大板块近 10 个交易日 RPS_5 变动热力图</h2>
        <div class="table-container">
            {heatmap_html}
        </div>

        <h2>🔍 中期市场结构与板块强弱变化研判 (基于中期 RPS_20)</h2>
        <div class="sector-card" style="background-color: #fffaf0; border-color: #ffe4b5;">
            <p style="margin: 0; font-size: 15px; color: #b8860b;">{mid_analysis_text}</p>
        </div>

        <h2>📈 各大板块强弱与资金流向总览 (按短期 RPS_5 排序)</h2>
        <div class="table-container">
            {sec_sum_html}
        </div>
        
        <h2>🔥 全市场多头领涨榜 Top 10 (按短期 RPS_5 排序)</h2>
        <div class="table-container">
            {long_html}
        </div>
        
        <h2>🧊 全市场空头领跌榜 Top 10 (按短期 RPS_5 排序)</h2>
        <div class="table-container">
            {short_html}
        </div>
        
        <h2>📂 今日最强势前三大板块深度复盘 (按板块 RPS_5 排序)</h2>
        {sector_details_html}
        
        <p style="margin-top: 60px; font-size: 13px; color: #7f8c8d; text-align: center; border-top: 1px dashed #ccc; padding-top: 20px;">
            本报告由商品期货 VaR 头寸资金管理系统定时任务引擎自动生成。仅供量化交易决策参考。
        </p>
    </body>
    </html>
    """
    
    os.makedirs(REPORTS_DIR, exist_ok=True)
    report_path = os.path.join(REPORTS_DIR, f"daily_report_{today_str}.html")
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    print(f"Report successfully saved to: {report_path}")

def run_daily_job():
    print(f"[{datetime.now()}] Starting daily sync job...")
    # Sync data first
    sync_data(start_date="20250101", recreate_db=False, sync_all_2h=False)
    # Then generate report
    generate_html_report()
    print(f"[{datetime.now()}] Daily job completed.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--report-only":
        generate_html_report()
    else:
        run_daily_job()
