import os
import re

def refactor_app():
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()
        
    # 1. Update reviewer.calculate_rps calls
    content = content.replace("rps_res = reviewer.calculate_rps(periods=[20, 60])", 
                              "rps_res = reviewer.calculate_rps(periods=[1, 5, 20, 60])")
    content = content.replace("rps_res_t10 = reviewer.calculate_rps(periods=[20, 60], target_date=t10_date)", 
                              "rps_res_t10 = reviewer.calculate_rps(periods=[1, 5, 20, 60], target_date=t10_date)")
                              
    # 2. Update Top 10 DataFrames to include Return_1 and Return_5
    content = content.replace(
        "top10_long = symbol_rps_now.sort_values(by='RPS_20', ascending=False).head(10)[['RPS_20', 'RPS_Change_10d', 'Return_20', 'sector']]",
        "top10_long = symbol_rps_now.sort_values(by='RPS_20', ascending=False).head(10)[['RPS_20', 'RPS_Change_10d', 'Return_1', 'Return_5', 'Return_20', 'sector']]"
    )
    content = content.replace(
        "top10_short = symbol_rps_now.sort_values(by='RPS_20', ascending=True).head(10)[['RPS_20', 'RPS_Change_10d', 'Return_20', 'sector']]",
        "top10_short = symbol_rps_now.sort_values(by='RPS_20', ascending=True).head(10)[['RPS_20', 'RPS_Change_10d', 'Return_1', 'Return_5', 'Return_20', 'sector']]"
    )
    content = content.replace(
        "st.dataframe(top10_long.style.format({'RPS_20': '{:.1f}', 'RPS_Change_10d': '{:+.1f}', 'Return_20': '{:.2%}'}))",
        "st.dataframe(top10_long.style.format({'RPS_20': '{:.1f}', 'RPS_Change_10d': '{:+.1f}', 'Return_1': '{:+.2%}', 'Return_5': '{:+.2%}', 'Return_20': '{:+.2%}'}))"
    )
    content = content.replace(
        "st.dataframe(top10_short.style.format({'RPS_20': '{:.1f}', 'RPS_Change_10d': '{:+.1f}', 'Return_20': '{:.2%}'}))",
        "st.dataframe(top10_short.style.format({'RPS_20': '{:.1f}', 'RPS_Change_10d': '{:+.1f}', 'Return_1': '{:+.2%}', 'Return_5': '{:+.2%}', 'Return_20': '{:+.2%}'}))"
    )

    # 3. Update Sector Summary to include Return_1 and Return_5
    content = content.replace(
        "st.dataframe(sector_summary[['sector', 'RPS_20', 'RPS_Change_10d', 'capital_flow', 'flow_ratio_10d']]",
        "st.dataframe(sector_summary[['sector', 'RPS_20', 'RPS_Change_10d', 'Return_1', 'Return_5', 'capital_flow', 'flow_ratio_10d']]"
    )
    content = content.replace(
        "'RPS_20': '{:.1f}', 'RPS_Change_10d': '{:+.1f}', 'capital_flow': '{:,.0f}', 'flow_ratio_10d': '{:.2%}'",
        "'RPS_20': '{:.1f}', 'RPS_Change_10d': '{:+.1f}', 'Return_1': '{:+.2%}', 'Return_5': '{:+.2%}', 'capital_flow': '{:,.0f}', 'flow_ratio_10d': '{:.2%}'"
    )
    
    # 4. Extract and Swap sections
    # Find the separator line for Top 10
    top10_marker = "# --- 视图 1.5：全市场最强与最弱 TOP 10 ---"
    if top10_marker not in content:
        print("Marker 1 not found")
        return
        
    parts = content.split(top10_marker)
    part1 = parts[0]
    rest = parts[1]
    
    sector_marker = "# 板块强弱与 10日资金流"
    if sector_marker not in rest:
        print("Marker 2 not found")
        return
        
    sub_parts = rest.split(sector_marker)
    top10_section = top10_marker + sub_parts[0]
    rest2 = sub_parts[1]
    
    # The end of the sector section is before Tab 1.5
    tab1_5_marker = "# ==========================================\n# Tab 1.5: 单品种详细分析"
    if tab1_5_marker not in rest2:
        print("Marker 3 not found")
        return
        
    sub_parts2 = rest2.split(tab1_5_marker)
    sector_section = sector_marker + sub_parts2[0]
    tail_section = tab1_5_marker + sub_parts2[1]
    
    # Now reconstruct with sector section before top10
    content = part1 + "\\n" + sector_section + "\\n" + top10_section + "\\n" + tail_section
    
    # 5. Fix the Plotly x-axis for rangebreaks
    old_xaxes = """                            # 设置 X 轴为类目型，去除双休日/非交易日的空白断层，并添加贯穿所有子图的十字准星
                            fig.update_xaxes(
                                type='category', 
                                categoryorder='category ascending',
                                showspikes=True,
                                spikemode="across",
                                spikesnap="cursor",
                                showline=True,
                                spikedash="solid",
                                spikethickness=1,
                                spikecolor="grey"
                            )"""
                            
    new_xaxes = """                            # 收集非交易日以去除空白
                            all_dates = pd.date_range(start=df_single.index.min(), end=df_single.index.max())
                            df_dates = pd.to_datetime(df_single.index)
                            missing_dates = all_dates.difference(df_dates).strftime('%Y-%m-%d').tolist()
                            
                            # 设置十字准星，并通过 rangebreaks 隐藏非交易日
                            fig.update_xaxes(
                                rangebreaks=[dict(values=missing_dates)],
                                showspikes=True,
                                spikemode="across",
                                spikesnap="cursor",
                                showline=True,
                                spikedash="solid",
                                spikethickness=1,
                                spikecolor="grey"
                            )"""
                            
    content = content.replace(old_xaxes, new_xaxes)
    
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Refactoring complete.")

if __name__ == "__main__":
    refactor_app()
