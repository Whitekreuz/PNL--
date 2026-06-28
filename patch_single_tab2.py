import os

def patch_app():
    with open('app.py', 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Replace the layout configuration to add category xaxes
    old_layout = """                            # 布局设置
                            fig.update_layout(
                                title=f"{selected_symbol} 过去 60 日详细复盘 (价格/量仓/资金/RPS)",
                                xaxis_rangeslider_visible=False,
                                height=900,
                                margin=dict(l=40, r=40, t=60, b=40),
                                hovermode="x unified"
                            )"""
                            
    new_layout = """                            # 布局设置
                            fig.update_layout(
                                title=f"{selected_symbol} 过去 60 日详细复盘 (价格/量仓/资金/RPS)",
                                xaxis_rangeslider_visible=False,
                                height=900,
                                margin=dict(l=40, r=40, t=60, b=40),
                                hovermode="x unified"
                            )
                            # 设置 X 轴为类目型，去除双休日/非交易日的空白断层
                            fig.update_xaxes(type='category', categoryorder='category ascending')"""
                            
    content = content.replace(old_layout, new_layout)
    
    # Inject the heatmaps after plotting the chart (at the end of `if selected_symbol:` block)
    old_end = """                            st.plotly_chart(fig, use_container_width=True)
                        else:"""
                        
    new_end = """                            st.plotly_chart(fig, use_container_width=True)
                            
                            st.markdown("---")
                            # ======= 新增：板块及内部品种 20 日 RPS 热力图 =======
                            
                            # 1. 板块 RPS 热力图
                            sector_indices_all = reviewer.generate_sector_indices(start_date='20250101')
                            if sector_indices_all:
                                sec_df_list = []
                                for sec, s_data in sector_indices_all.items():
                                    sec_df_list.append(s_data[['nw_index']].rename(columns={'nw_index': sec}))
                                sector_pivot = pd.concat(sec_df_list, axis=1).ffill().dropna()
                                returns_20_sec = sector_pivot.pct_change(periods=20).dropna()
                                last_20_returns_sec = returns_20_sec.tail(20)
                                ranks_sec = last_20_returns_sec.rank(axis=1, ascending=True)
                                rps_20d_history_sec = (ranks_sec - 1.0) / (sector_pivot.shape[1] - 1.0) * 100.0
                                
                                if selected_sector in rps_20d_history_sec.columns:
                                    sec_rps_heatmap = rps_20d_history_sec[[selected_sector]].T
                                    sec_rps_heatmap.columns = [str(c)[:10] for c in sec_rps_heatmap.columns]
                                    
                                    st.subheader(f"🔥 {selected_sector}板块整体 - 近 20 个交易日 RPS 热力图")
                                    st.dataframe(sec_rps_heatmap.style.background_gradient(cmap='RdYlGn_r', axis=None, vmin=0, vmax=100).format("{:.1f}"), use_container_width=True)
                                    
                            # 2. 板块内各品种 RPS 热力图
                            rps_history_20d = rps_history.tail(20)
                            symbols_to_plot = [s for s in symbols_in_sector if s in rps_history_20d.columns]
                            if symbols_to_plot:
                                sym_rps_heatmap = rps_history_20d[symbols_to_plot].T
                                # 按最新一天的分数降序排列
                                sym_rps_heatmap = sym_rps_heatmap.sort_values(by=sym_rps_heatmap.columns[-1], ascending=False)
                                sym_rps_heatmap.columns = [str(c)[:10] for c in sym_rps_heatmap.columns]
                                
                                st.subheader(f"📊 {selected_sector}板块内所有品种 - 近 20 个交易日 RPS 热力图")
                                st.dataframe(sym_rps_heatmap.style.background_gradient(cmap='RdYlGn_r', axis=None, vmin=0, vmax=100).format("{:.1f}"), height=(len(symbols_to_plot) * 35 + 40), use_container_width=True)
                            
                        else:"""
                        
    content = content.replace(old_end, new_end)
    
    with open('app.py', 'w', encoding='utf-8') as f:
        f.write(content)
        
    print("Patch applied successfully.")

if __name__ == "__main__":
    patch_app()
