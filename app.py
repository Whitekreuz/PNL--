import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
import os

from risk_engine import calculate_ewma_var, get_aligned_returns, calculate_covariance_correlation
from position_calculator import PositionCalculator
from market_reviewer import MarketReviewer

# --- 全局配置 ---
st.set_page_config(page_title="量化交易风控工作台", layout="wide", page_icon="📈")
DB_PATH = r"d:\datasci\PNL日志\futures_data.db"

# --- 缓存底层数据加载 ---
@st.cache_resource
def load_engines():
    if not os.path.exists(DB_PATH):
        st.error(f"数据库 {DB_PATH} 不存在！")
        st.stop()
    pos_calc = PositionCalculator(DB_PATH)
    reviewer = MarketReviewer(DB_PATH)
    return pos_calc, reviewer

pos_calc, reviewer = load_engines()

# --- 侧边栏：全局风控中枢 ---
st.sidebar.header("⚙️ 全局风控中枢")
st.sidebar.markdown("---")

drawdown_limit = st.sidebar.number_input("最大回撤容忍度 (RMB)", value=200000.0, step=10000.0)
risk_factor = st.sidebar.slider("风险乘数因子 (k)", min_value=0.01, max_value=0.20, value=0.075, step=0.005)
cppi_m = st.sidebar.number_input("CPPI 乘数 (M)", value=1.0, min_value=0.1, max_value=5.0, step=0.1)

# 计算全局目标 VaR
target_var = pos_calc.calculate_target_var(drawdown_limit, risk_factor, cppi_m)

st.sidebar.markdown("---")
st.sidebar.metric(label="🎯 组合目标 VaR 限额", value=f"¥ {target_var:,.0f}")
st.sidebar.caption("当日全市场最大允许的 99% VaR 波动敞口。")

# --- 主页面 Tabs ---
tab_market, tab_position, tab_risk = st.tabs(["📊 市场复盘与强弱分析", "💰 头寸计算器", "🚨 风控体检单"])

# ==========================================
# Tab 1: 市场复盘与强弱分析
# ==========================================
with tab_market:
    st.header("1. 板块与品种资金面与技术面扫描")
    
    # 提取复盘数据
    with st.spinner("正在计算全市场资金流向与 RPS..."):
        flow_res = reviewer.calculate_capital_flow()
        rps_res = reviewer.calculate_rps(periods=[20, 60])
        sector_indices = reviewer.generate_sector_indices(start_date='20250101')
        
        # 10日变化逻辑
        conn = sqlite3.connect(DB_PATH)
        dates = pd.read_sql("SELECT DISTINCT date FROM kline_daily ORDER BY date DESC LIMIT 15", conn)['date'].tolist()
        t10_date = dates[10] if len(dates) > 10 else dates[-1]
        
        rps_res_t10 = reviewer.calculate_rps(periods=[20, 60], target_date=t10_date)
        
        query_10d = f"SELECT symbol, date, open_interest, settlement FROM kline_daily WHERE is_continuous=1 AND date >= '{t10_date}' ORDER BY symbol, date"
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
        if not symbol_rps_t10.empty and 'RPS_20' in symbol_rps_t10.columns:
            symbol_rps_now['RPS_20_t10'] = symbol_rps_now.index.map(lambda x: symbol_rps_t10.loc[x, 'RPS_20'] if x in symbol_rps_t10.index else symbol_rps_now.loc[x, 'RPS_20'])
        else:
            symbol_rps_now['RPS_20_t10'] = symbol_rps_now['RPS_20']
        symbol_rps_now['RPS_Change_10d'] = symbol_rps_now['RPS_20'] - symbol_rps_now['RPS_20_t10']
        
        sector_rps_now = rps_res.get('sector_rps', pd.DataFrame())
        sector_rps_t10 = rps_res_t10.get('sector_rps', pd.DataFrame())
        if not sector_rps_now.empty and not sector_rps_t10.empty:
            sector_rps_now['RPS_20_t10'] = sector_rps_now.index.map(lambda x: sector_rps_t10.loc[x, 'RPS_20'] if x in sector_rps_t10.index else sector_rps_now.loc[x, 'RPS_20'])
            sector_rps_now['RPS_Change_10d'] = sector_rps_now['RPS_20'] - sector_rps_now['RPS_20_t10']
            sector_summary = pd.merge(sector_rps_now.reset_index().rename(columns={'index': 'sector'}), flow_10d_sector, on='sector', how='left')
        else:
            sector_summary = flow_10d_sector
        
    if flow_res and rps_res and sector_indices:
        data_date = flow_res['target_date']
        st.caption(f"📅 数据日期: {data_date}")
        
        # --- 视图 1：九大板块走势对比 ---
        st.subheader("一、全市场宏观板块趋势对比")
        index_type = st.radio("选择指数计算模式：", ["持仓金额加权 (默认)", "等权重 (探寻小品种)"], horizontal=True)
        col_name = 'nw_index' if '持仓' in index_type else 'ew_index'
        
        # 组装 9 大板块走势为宽表
        sec_df_list = []
        for sec, s_data in sector_indices.items():
            s_data = s_data.copy()
            s_data.rename(columns={col_name: sec}, inplace=True)
            sec_df_list.append(s_data[sec])
        
        all_sector_df = pd.concat(sec_df_list, axis=1).ffill().dropna()
        
        fig_sectors = px.line(all_sector_df, title=f"9 大板块历史走势 ({index_type})")
        fig_sectors.update_layout(xaxis_title="日期", yaxis_title="指数净值 (基准 1000)", height=500)
        st.plotly_chart(fig_sectors, use_container_width=True)
        
        st.markdown("---")
        
        # --- 视图 1.5：全市场最强与最弱 TOP 10 ---
        st.subheader("全市场最强 (多头) 与最弱 (空头) Top 10 品种")
        top10_long = symbol_rps_now.sort_values(by='RPS_20', ascending=False).head(10)[['RPS_20', 'RPS_Change_10d', 'Return_20', 'sector']]
        top10_short = symbol_rps_now.sort_values(by='RPS_20', ascending=True).head(10)[['RPS_20', 'RPS_Change_10d', 'Return_20', 'sector']]
        
        col_l, col_s = st.columns(2)
        with col_l:
            st.write("🔥 **最强多头榜 Top 10**")
            st.dataframe(top10_long.style.format({'RPS_20': '{:.1f}', 'RPS_Change_10d': '{:+.1f}', 'Return_20': '{:.2%}'}))
        with col_s:
            st.write("🧊 **最弱空头榜 Top 10**")
            st.dataframe(top10_short.style.format({'RPS_20': '{:.1f}', 'RPS_Change_10d': '{:+.1f}', 'Return_20': '{:.2%}'}))
            
        # 板块强弱与 10日资金流
        st.subheader("各大板块强弱与 10 日资金流占比")
        if 'RPS_20' in sector_summary.columns:
            st.dataframe(sector_summary[['sector', 'RPS_20', 'RPS_Change_10d', 'capital_flow', 'flow_ratio_10d']].sort_values(by='RPS_20', ascending=False).style.format({
                'RPS_20': '{:.1f}', 'RPS_Change_10d': '{:+.1f}', 'capital_flow': '{:,.0f}', 'flow_ratio_10d': '{:.2%}'
            }))
            
        # 板块 10日 RPS 历史热力图
        st.subheader("各大板块近 10 个交易日 RPS 变动热力图")
        try:
            sec_df_list_hm = []
            for sec, s_data in sector_indices.items():
                s_data = s_data.copy()
                sec_df_list_hm.append(s_data[[col_name]].rename(columns={col_name: sec}))
                
            sector_pivot_hm = pd.concat(sec_df_list_hm, axis=1).ffill().dropna()
            
            returns_20_hm = sector_pivot_hm.pct_change(periods=20).dropna()
            last_10_returns_hm = returns_20_hm.tail(10)
            
            ranks_hm = last_10_returns_hm.rank(axis=1, ascending=True)
            n_sectors_hm = sector_pivot_hm.shape[1]
            rps_10d_history_hm = (ranks_hm - 1.0) / (n_sectors_hm - 1.0) * 100.0
            
            # 转置为 行：板块，列：日期
            rps_heatmap_df = rps_10d_history_hm.T
            # 按最新一天的 RPS 降序排列
            rps_heatmap_df = rps_heatmap_df.sort_values(by=rps_heatmap_df.columns[-1], ascending=False)
            
            # 将列名(日期)转换为字符串格式
            if isinstance(rps_heatmap_df.columns, pd.DatetimeIndex):
                rps_heatmap_df.columns = rps_heatmap_df.columns.strftime('%Y-%m-%d')
            else:
                rps_heatmap_df.columns = [str(c)[:10] for c in rps_heatmap_df.columns]
                
            # 渲染带背景色的热力图表格
            styled_heatmap = rps_heatmap_df.style.background_gradient(cmap='RdYlGn_r', axis=None, vmin=0, vmax=100).format("{:.1f}")
            st.dataframe(styled_heatmap, use_container_width=True)
        except Exception as e:
            st.error(f"热力图渲染失败: {e}")
        
        st.markdown("---")
        
        # --- 视图 2：全市场个股对比 (RPS 散点图) ---
        st.subheader("二、全市场单品种 20 日动能与资金流对比")
        symbol_flow = flow_res['symbol_flow'].set_index('symbol')
        symbol_rps = rps_res['symbol_rps']
        
        # 合并 RPS 和资金流
        market_scatter_df = pd.merge(symbol_rps, symbol_flow[['capital_flow', 'delta_oi']], left_index=True, right_index=True)
        
        fig_scatter = px.scatter(
            market_scatter_df.reset_index(), 
            x='capital_flow', 
            y='RPS_20', 
            color='sector', 
            hover_data=['symbol', 'Return_20'],
            labels={'capital_flow': '当日资金净流入 (RMB)', 'RPS_20': '20日相对强度 (RPS)'},
            title="全市场品种：资金流向与动能强弱散点图"
        )
        # 添加辅助线
        fig_scatter.add_hline(y=50, line_dash="dash", line_color="gray")
        fig_scatter.add_vline(x=0, line_dash="dash", line_color="gray")
        st.plotly_chart(fig_scatter, use_container_width=True)
        
        st.markdown("---")
        
        # --- 视图 3：板块内横向对比 ---
        st.subheader("三、板块内部结构深扒")
        selected_sector = st.selectbox("选择要分析的板块：", market_scatter_df['sector'].unique())
        
        # 获取该板块内的所有品种数据
        intra_sector_df = market_scatter_df[market_scatter_df['sector'] == selected_sector]
        intra_symbols = intra_sector_df.index.tolist()
        
        col1, col2 = st.columns(2)
        with col1:
            st.write(f"**[{selected_sector}] 板块内部 RPS 与资金流水**")
            st.dataframe(intra_sector_df[['RPS_20', 'Return_20', 'capital_flow']].sort_values(by='RPS_20', ascending=False).style.format({'RPS_20': '{:.1f}', 'Return_20': '{:.2%}', 'capital_flow': '{:,.0f}'}))
            
        with col2:
            # 绘制板块内部各个品种的净值走势
            st.write(f"**[{selected_sector}] 内部各品种近半年净值对比**")
            try:
                conn = sqlite3.connect(DB_PATH)
                query = f"SELECT symbol, date, close FROM kline_daily WHERE is_continuous=1 AND date >= '20250601' AND symbol IN ({','.join(['?']*len(intra_symbols))})"
                intra_prices = pd.read_sql(query, conn, params=intra_symbols)
                conn.close()
                intra_pivot = intra_prices.pivot(index='date', columns='symbol', values='close').ffill().dropna()
                # 归一化到 1000
                intra_norm = (intra_pivot / intra_pivot.iloc[0]) * 1000
                fig_intra = px.line(intra_norm)
                fig_intra.update_layout(xaxis_title="日期", yaxis_title="归一化净值 (基准 1000)", showlegend=True)
                st.plotly_chart(fig_intra, use_container_width=True)
            except Exception as e:
                st.warning(f"加载板块内部对比图表失败: {e}")

# ==========================================
# Tab 2: 头寸计算器
# ==========================================
with tab_position:
    st.header("2. 交互式资金头寸计算器")
    st.markdown("在这里构建你的计划交易清单。引擎将拉取真实的波动率并匹配组合 VaR。")
    
    # 状态缓存用于记录当前填写的品种清单
    if 'portfolio_items' not in st.session_state:
        st.session_state.portfolio_items = []
        
    with st.form("add_symbol_form"):
        col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
        with col1:
            input_sym = st.text_input("品种代码 (如 RB, CU)").upper()
        with col2:
            input_price = st.number_input("计划开仓价", min_value=0.0, step=1.0)
        with col3:
            input_direction = st.selectbox("交易方向", ["做多 (1)", "做空 (-1)"])
        with col4:
            add_btn = st.form_submit_button("添加/更新")
            
    if add_btn and input_sym:
        meta = pos_calc.get_symbol_metadata(input_sym)
        if not meta:
            st.error(f"数据库中未找到品种 {input_sym}")
        else:
            # 获取真实 VaR%
            returns_df = get_aligned_returns(DB_PATH, [input_sym], period='daily', start_date='20200101', is_continuous=1)
            if not returns_df.empty and input_sym in returns_df.columns:
                returns = returns_df[input_sym]
                var_value, _, _ = calculate_ewma_var(returns, confidence_level=0.99, lambda_param=0.94)
                
                # 检查是否已存在，存在则更新，否则追加
                exists = False
                for item in st.session_state.portfolio_items:
                    if item['symbol'] == input_sym:
                        item['price'] = input_price
                        item['direction'] = 1 if '做多' in input_direction else -1
                        item['var_pct'] = var_value
                        exists = True
                if not exists:
                    st.session_state.portfolio_items.append({
                        'symbol': input_sym,
                        'price': input_price,
                        'direction': 1 if '做多' in input_direction else -1,
                        'var_pct': var_value,
                        'planned_lots': 0 # 待用户填入
                    })
                st.success(f"{input_sym} 已添加！当前市场单日真实 VaR: {var_value*100:.2f}%")
            else:
                st.error("无法计算该品种历史 VaR。")

    if st.session_state.portfolio_items:
        st.markdown("### 当前投资组合配置表")
        st.info("💡 **提示**：你可以在上方继续添加更多品种，构建多品种投资组合！修改下方手数后，请直接前往【🚨 风控体检单】查看综合报告。")
        
        for i, item in enumerate(st.session_state.portfolio_items):
            sym = item['symbol']
            c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
            c1.write(f"**{sym}** (VaR: {item['var_pct']*100:.2f}%)")
            c2.write(f"{'做多' if item['direction']==1 else '做空'} @ {item['price']}")
            
            meta = pos_calc.get_symbol_metadata(sym)
            multiplier = meta['multiplier'] if meta else 10.0
            occupied_var = item['planned_lots'] * item['price'] * multiplier * item['var_pct']
            
            # 计算如果单吊该品种的建议最大手数
            max_res = pos_calc.calculate_single_asset_lots(sym, target_var, item['price'], item['var_pct'])
            c3.write(f"建议上限: {max_res['suggested_lots']} 手\n\n已占 VaR: ¥{occupied_var:,.0f}")
            
            # 输入实际计划手数 (直接通过 key 绑定，修改后即刻生效触发全页重绘)
            item['planned_lots'] = c4.number_input(f"实际开仓手数 ({sym})", value=int(item['planned_lots']), min_value=0, step=1, key=f"lots_{sym}")
            
        st.markdown("---")
        if st.button("🗑️ 清空所有品种"):
            st.session_state.portfolio_items = []
            st.rerun()

# ==========================================
# Tab 3: 风控体检单
# ==========================================
with tab_risk:
    st.header("3. 投资组合全局风控诊断报告")
    
    if not st.session_state.portfolio_items:
        st.info("请先在「头寸计算器」中添加交易品种。")
    else:
        # 构建评估参数
        portfolio_dict = {}
        symbols_list = []
        for item in st.session_state.portfolio_items:
            if item['planned_lots'] > 0:
                portfolio_dict[item['symbol']] = {
                    'lots': item['planned_lots'],
                    'direction': item['direction'],
                    'price': item['price']
                }
                symbols_list.append(item['symbol'])
                
        if not portfolio_dict:
            st.warning("所有品种的手数均为 0，无法进行体检。")
        else:
            with st.spinner("正在拉取协方差矩阵对冲风险..."):
                aligned_returns = get_aligned_returns(DB_PATH, symbols_list, period='daily', start_date='20200101', is_continuous=1)
                cov_matrix, corr_matrix = calculate_covariance_correlation(aligned_returns)
                res_port = pos_calc.evaluate_portfolio_risk(portfolio_dict, cov_matrix)
                
            st.subheader("总览指标")
            m1, m2, m3 = st.columns(3)
            m1.metric("占用总保证金", f"¥ {res_port['total_margin']:,.0f}")
            m2.metric("当前组合总 VaR", f"¥ {res_port['portfolio_var']:,.0f}", 
                     delta=f"离限额还剩 {target_var - res_port['portfolio_var']:,.0f}", delta_color="normal")
            
            var_usage = res_port['portfolio_var'] / target_var
            m3.metric("预算使用率", f"{var_usage*100:.1f}%")
            if var_usage > 1.0:
                st.error("🚨 警告：当前组合的总 VaR 已严重超标，请全面削减仓位！")
            
            st.markdown("---")
            col_a, col_b = st.columns(2)
            
            with col_a:
                st.subheader("一、板块 40% 集中度预警")
                # 绘制饼图
                pie_df = pd.DataFrame(list(res_port['sector_var_ratios'].items()), columns=['Sector', 'Ratio'])
                fig_pie = px.pie(pie_df, values='Ratio', names='Sector', title="各大板块风险 (VaR) 贡献度分布")
                st.plotly_chart(fig_pie, use_container_width=True)
                
                if len(symbols_list) < 3:
                    st.info("💡 当前组合品种较少，单一板块集中度触及上限属于数学必然。40% 限额警报主要为监控【多品种分散投资】而设计。")
                    
                if res_port['sector_warnings']:
                    for w in res_port['sector_warnings']:
                        st.error(f"❌ {w['message']}")
                        st.warning(f"**建议执行**：将该板块内所有头寸削减 {w['reduction_factor']*100:.1f}%。")
                else:
                    st.success("✅ 所有板块均处于安全集中度阈值内。")
                    
            with col_b:
                st.subheader("二、高相关性同质化拦截")
                if len(symbols_list) > 1:
                    fig_corr = px.imshow(corr_matrix, text_auto=".2f", color_continuous_scale='RdBu_r', range_color=[-1, 1], title="持仓品种相关系数热力图")
                    st.plotly_chart(fig_corr, use_container_width=True)
                    
                    has_penalty = False
                    checked = set()
                    for s1 in symbols_list:
                        penalties = pos_calc.check_correlation_penalty(s1, [s for s in symbols_list if s != s1], corr_matrix)
                        for p in penalties:
                            s2 = p['symbol']
                            pair = tuple(sorted([s1, s2]))
                            if pair not in checked:
                                has_penalty = True
                                st.warning(f"⚠️ **{s1}** 与 **{s2}** 高度正相关 ({p['correlation']:.2f})！建议叠加惩罚因子，仅分配原权重的 **{p['penalty_factor']*100:.0f}%**。")
                                checked.add(pair)
                    if not has_penalty:
                        st.success("✅ 持仓结构相关度健康，无同质化预警。")
                else:
                    st.info("单品种持仓不存在相关性校验。")
