# 风险分析引擎 (Risk Engine)

`risk_engine.py` 模块是商品期货 VaR 头寸资金管理系统的核心计算组件，负责为单个品种或多个品种的投资组合计算各种风险指标，包括对数收益率、风险价值（VaR）、条件风险价值（CVaR）、动态波动率（EWMA）以及资产间的协方差与相关性矩阵。

## 1. 核心功能与方法

### A. 收益率计算
```python
def calculate_returns(df: pd.DataFrame, price_col: str = 'close', log_returns: bool = True) -> pd.Series
```
- **描述**：根据传入的价格数据计算收益率。为了满足在多期计算中收益率可直接线性相加的特性，系统默认采用**对数收益率**（Log Returns），即：

$$ r_t = \ln\left(\frac{P_t}{P_{t-1}}\right) $$
- **机制**：内置空值前向填充机制（`ffill`），并在计算后剔除不可用的起始空值。

### B. 历史模拟法 VaR & CVaR
```python
def calculate_historical_var_cvar(returns: pd.Series, confidence_level: float = 0.95) -> tuple
```
- **描述**：通过历史经验分布直接计算风险指标，无需假设收益率服从正态分布。
- **VaR (Value at Risk)**：通过计算给定置信水平下的分位数得出，如 95% 置信度对应 5% 的下行分位数绝对值。
- **CVaR (Conditional VaR)**：计算在损失超过 VaR 的尾部情境下的平均损失预期（Expected Shortfall）。

### C. EWMA 动态波动率 VaR
```python
def calculate_ewma_var(returns: pd.Series, confidence_level: float = 0.95, lambda_param: float = 0.94) -> tuple
```
- **描述**：指数加权移动平均（Exponentially Weighted Moving Average）能更好地捕捉金融市场的“波动率聚集”现象（Volatility Clustering）。
- **参数**：
  - `lambda_param`：衰减因子。对于日线数据默认推荐使用 RiskMetrics 的标准 `0.94`；对于高频（如 2H）数据可根据平滑要求调整至 `0.97`。
- **迭代公式**：

$$ \sigma_t^2 = \lambda \sigma_{t-1}^2 + (1 - \lambda) r_{t-1}^2 $$
- **返回值**：返回当期最新的动态 VaR、最新标准差以及历史的动态波动率时间序列。

### D. 收益率对齐
```python
def get_aligned_returns(db_path: str, symbols: list, period: str = 'daily', start_date: str = '20200101', is_continuous: int = 1) -> pd.DataFrame
```
- **描述**：由于不同品种在某些交易日或小节可能停牌，导致时间戳不完全一致，此方法负责从 SQLite 数据库提取多品种数据并**时间对齐**。
- **机制**：采用 `Outer Join` 并通过前向填充（`ffill`）处理短暂的非同步问题，未发生交易的时段收益率记为 0，确保矩阵能够被平滑计算。

### E. 协方差与相关性矩阵
```python
def calculate_covariance_correlation(returns_df: pd.DataFrame) -> tuple
def save_matrices_to_db(db_path: str, cov_matrix: pd.DataFrame, corr_matrix: pd.DataFrame, period: str)
def export_correlation_matrix_image(corr_matrix: pd.DataFrame, output_path: str, title: str = "Correlation Matrix")
```
- **描述**：计算品种间的风险联动性。
- **持久化**：将矩阵以关系型表格（Pairwise）的方式写入到 `asset_correlations` 表中（字段包含：`symbol1`, `symbol2`, `covariance`, `correlation`），便于利用 SQL 查询最高/最低相关的资产。
- **可视化**：支持将相关系数矩阵输出为 Seaborn 绘制的高分辨率热力图（Heatmap），直观呈现多品种的相关性冷暖分布。

## 2. 数据库设计联动

为支持矩阵持久化，引擎自动在 `futures_data.db` 中维护 `asset_correlations` 表：

| 字段名 | 类型 | 说明 |
| :--- | :--- | :--- |
| `id` | INTEGER | 主键自增 |
| `period` | TEXT | 周期类型（如 'daily', '2h'） |
| `symbol1` | TEXT | 资产代码 1 |
| `symbol2` | TEXT | 资产代码 2 |
| `covariance` | REAL | 协方差值 |
| `correlation`| REAL | 相关系数（-1 到 1） |
| `updated_at` | TIMESTAMP| 最后更新时间 |

## 3. 测试与验证
本模块通过完整的单元测试和与数据库对接的集成测试保障准确性。相关测试代码存放在 `test_risk_engine.py` 中，主要校验了历史 VaR 数学分位数的准确性、EWMA 波动率的递推严谨性以及矩阵主对角线全 1 的性质。
