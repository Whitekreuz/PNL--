import sqlite3
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import os
from typing import Tuple

def calculate_returns(df: pd.DataFrame, price_col: str = 'close', log_returns: bool = True) -> pd.Series:
    """
    计算单个 K 线 DataFrame 的收益率序列。
    """
    df = df.copy()
    if price_col not in df.columns:
        raise ValueError(f"列名 {price_col} 不在 DataFrame 中。")
    
    # 填补可能的空值
    df[price_col] = df[price_col].ffill()
    
    if log_returns:
        # 对数收益率：ln(P_t / P_{t-1})
        returns = np.log(df[price_col] / df[price_col].shift(1))
    else:
        # 简单收益率：(P_t - P_{t-1}) / P_{t-1}
        returns = df[price_col].pct_change()
    
    return returns.dropna()

def calculate_historical_var_cvar(returns: pd.Series, confidence_level: float = 0.95) -> Tuple[float, float]:
    """
    计算历史模拟法下的 VaR 和 CVaR。
    返回: (VaR_value, CVaR_value)
    """
    if returns.empty:
        return np.nan, np.nan
        
    alpha = 1 - confidence_level
    # 计算 VaR
    var_value = -np.percentile(returns, alpha * 100)
    
    # 计算 CVaR (损失超过 VaR 的部分的期望)
    tail_losses = returns[returns <= -var_value]
    if len(tail_losses) > 0:
        cvar_value = -tail_losses.mean()
    else:
        cvar_value = var_value
        
    return var_value, cvar_value

def calculate_ewma_var(returns: pd.Series, confidence_level: float = 0.95, lambda_param: float = 0.94) -> Tuple[float, float, pd.Series]:
    """
    计算 EWMA 动态波动率及其对应的 VaR。
    返回: (VaR_value, latest_volatility, volatility_series)
    """
    if returns.empty:
        return np.nan, np.nan, pd.Series()
        
    # 计算初始方差
    variance = returns.var()
    ewma_var_series = []
    
    for r in returns:
        variance = lambda_param * variance + (1 - lambda_param) * (r ** 2)
        ewma_var_series.append(variance)
        
    ewma_var_series = pd.Series(ewma_var_series, index=returns.index)
    volatility_series = np.sqrt(ewma_var_series)
    
    latest_volatility = volatility_series.iloc[-1]
    
    # 基于正态分布假设计算 VaR
    from scipy.stats import norm
    z_score = norm.ppf(confidence_level)
    
    var_value = z_score * latest_volatility - returns.mean()
    
    return var_value, latest_volatility, volatility_series

def get_aligned_returns(db_path: str, symbols: list, period: str = 'daily', start_date: str = '20200101', is_continuous: int = 1) -> pd.DataFrame:
    """
    从数据库中拉取多个品种的 K 线，计算收益率并进行时间对齐。
    返回: 包含各品种收益率序列的 DataFrame，列名为品种大写（如 'RB', 'CU'）
    """
    conn = sqlite3.connect(db_path)
    
    table_name = 'kline_daily' if period == 'daily' else 'kline_2h'
    time_col = 'date' if period == 'daily' else 'datetime'
    
    df_list = []
    for symbol in symbols:
        query = f"""
            SELECT {time_col}, close 
            FROM {table_name} 
            WHERE symbol = ? AND is_continuous = ? AND {time_col} >= ?
            ORDER BY {time_col} ASC
        """
        df = pd.read_sql(query, conn, params=(symbol.upper(), is_continuous, start_date))
        if not df.empty:
            df.set_index(time_col, inplace=True)
            df.rename(columns={'close': symbol.upper()}, inplace=True)
            df_list.append(df)
            
    conn.close()
    
    if not df_list:
        return pd.DataFrame()
        
    # 合并所有品种的价格
    merged_prices = df_list[0]
    for df in df_list[1:]:
        merged_prices = merged_prices.join(df, how='outer')
        
    # 前向填充处理缺失值
    merged_prices = merged_prices.ffill()
    
    # 计算所有品种的收益率
    returns_df = np.log(merged_prices / merged_prices.shift(1)).dropna(how='all')
    
    # 如果某行所有品种都是 NaN，则删除
    returns_df = returns_df.dropna(how='all')
    
    # 对于部分缺失的情况，填充0收益率（表示停牌或无交易）
    returns_df = returns_df.fillna(0)
    
    return returns_df

def calculate_covariance_correlation(returns_df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    计算对齐后收益率的协方差矩阵与相关性矩阵。
    返回: (cov_matrix_df, corr_matrix_df)
    """
    cov_matrix = returns_df.cov()
    corr_matrix = returns_df.corr()
    return cov_matrix, corr_matrix

def save_matrices_to_db(db_path: str, cov_matrix: pd.DataFrame, corr_matrix: pd.DataFrame, period: str):
    """
    将协方差和相关性矩阵存入 SQLite 数据库中。
    采用 pairwise 的形式存储，方便查询。
    """
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS asset_correlations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            period TEXT,
            symbol1 TEXT,
            symbol2 TEXT,
            covariance REAL,
            correlation REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(period, symbol1, symbol2)
        )
    ''')
    
    symbols = cov_matrix.columns
    records = []
    
    for i in range(len(symbols)):
        for j in range(i, len(symbols)):
            s1 = symbols[i]
            s2 = symbols[j]
            cov = cov_matrix.loc[s1, s2]
            corr = corr_matrix.loc[s1, s2]
            records.append((period, s1, s2, float(cov), float(corr)))
            if s1 != s2:
                 records.append((period, s2, s1, float(cov), float(corr)))
            
    cursor.executemany('''
        INSERT INTO asset_correlations (period, symbol1, symbol2, covariance, correlation)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(period, symbol1, symbol2) 
        DO UPDATE SET covariance=excluded.covariance, correlation=excluded.correlation, updated_at=CURRENT_TIMESTAMP
    ''', records)
    
    conn.commit()
    conn.close()

def export_correlation_matrix_image(corr_matrix: pd.DataFrame, output_path: str, title: str = "Correlation Matrix"):
    """
    将相关性矩阵导出为热力图图片。
    """
    plt.figure(figsize=(10, 8))
    sns.heatmap(corr_matrix, annot=True, cmap='coolwarm', vmin=-1, vmax=1, center=0, fmt='.2f', 
                square=True, linewidths=.5, cbar_kws={"shrink": .8})
    plt.title(title, fontsize=16)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300)
    plt.close()
    print(f"相关性矩阵热力图已保存至: {output_path}")

if __name__ == "__main__":
    # 简单测试逻辑
    pass
