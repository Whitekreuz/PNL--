# 资金头寸计算引擎 (Position Calculator)

`position_calculator.py` 模块是本系统连接“风险测算”与“实际交易”的桥梁。它承接了第二个模块计算得出的各品种 VaR 估值与相关性矩阵，并基于交易员设定的核心资金参数（回撤额度与风险因子），输出具体的建仓指导（最大可开手数）并进行多层次的风控拦截。

## 1. 核心功能与方法

### A. 全局目标 VaR 设定
```python
def calculate_target_var(self, drawdown_budget: float, risk_factor: float = 0.075, cppi_multiplier: float = 1.0) -> float
```
- **描述**：根据“最大可承受回撤”（Drawdown Budget）而非总本金来决定单日或总敞口的极限风险预算。
- **动态调节 (CPPI)**：通过外部传入的 `cppi_multiplier`，支持在账户盈利（安全垫变厚）时放大预算，在回撤时缩小预算，实现数学上绝对的清盘底线控制。

### B. 单品种基础建仓手数分配
```python
def calculate_single_asset_lots(self, symbol: str, target_var: float, current_price: float, var_pct: float, weight_alloc: float = 1.0) -> dict
```
- **描述**：计算指定品种在当前价格和当期波动率（VaR%）下，分配到既定目标预算时的最大理论建仓手数。
- **机制**：从 SQLite 数据库提取品种乘数（Multiplier）与保证金率（Margin Rate），自动计算建议手数（向下取整）、名义本金金额及预计占用的保证金。

### C. 投资组合级别风控评估 (Component VaR & Sector Cap)
```python
def evaluate_portfolio_risk(self, portfolio: dict, cov_matrix: pd.DataFrame, var_pct_dict: dict = None) -> dict
```
- **描述**：当持有多个品种形成投资组合时，评估系统整体的实际风险，并自动发现过度集中的情况。
- **返回指标**：
  - `portfolio_var`：基于输入协方差矩阵和当前头寸名义敞口推导出的总体在险价值。
  - `component_var`：各单一品种在当前组合构成中对总体 VaR 的实际边际贡献金额。
  - `sector_warnings`：**40% 板块风控上限（Sector Cap）**。若系统侦测到某个板块（如黑色系）累积的 Component VaR 占比超过投资组合总 VaR 的 40%，会在此处返回红色警告并建议降仓。

### D. 高相关性惩罚过滤器
```python
def check_correlation_penalty(self, target_symbol: str, portfolio_symbols: list, corr_matrix: pd.DataFrame, threshold: float = 0.7) -> list
```
- **描述**：在交易员准备纳入新品种进入组合前，前置校验品种共振风险。
- **机制**：通过比对传入的 `corr_matrix`，当相关系数绝对值超过阈值（如 `0.7`）时，系统自动给出 `penalty_factor` 惩罚系数（如 $\rho > 0.8$ 削减一半仓位），强制交易员降低同质化头寸。

## 2. 依赖项与数据流转
- 本模块高度依赖 SQLite 数据库（`futures_data.db`）中的 `contract_metadata` 表。若查询品种无对应的乘数或保证金率，系统将应用极端保守默认值（10 乘数，10% 保证金）并允许运行，但强烈建议确保元数据已通过第一模块同步。
- 传入的协方差矩阵 `cov_matrix` 应为 **收益率协方差矩阵**。引擎已默认将其处理并利用 $Z=2.326$ 进行 99% 置信度下的名义敞口映射计算。
