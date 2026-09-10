# 股票初级预测验证系统 | Stock Basic Prediction Validation

> A股相对表现预测研究项目 — 90 天验证期，非商业化  
> A-share relative performance prediction research — 90-day validation, non-commercial

---

## 项目定位 | Project Overview

这是一个**研究验证项目**，目标是评估 LLM 对 A 股个股相对沪深300指数超额收益的预测能力。项目处于**封闭验证期**，不向公众提供投资建议，不收费，不承诺收益。

This is a **research validation project** evaluating LLM's ability to predict A-share stock excess returns vs CSI300 index. Currently in **closed validation phase** — no investment advice, no fees, no return guarantees.

---

## 核心设计 | Core Design

### 预测目标 | Prediction Target

| 项目 | 内容 |
|------|------|
| **目标** | 未来 N 个交易日相对沪深300指数的超额收益为正的概率 |
| **Target** | Probability of positive excess return vs CSI300 over N trading days |
| **周期** | N ∈ {5, 10, 20} 个交易日 |
| **Horizons** | N ∈ {5, 10, 20} trading days |
| **输出** | 概率 p ∈ [0,1] + 证据清单（禁指令性词汇） |
| **Output** | Probability p ∈ [0,1] + evidence list (no directive words) |

### 数据管道 | Data Pipeline

```
fetch_snapshots.py  →  确定性指标快照（唯一数字真源）
       ↓
predict_batch.py   →  LLM 概率输出（OpenRouter）
       ↓
settle.py          →  T+N 结算，计算 Brier/LogLoss
```

### 防作弊机制 | Anti-Cheat Mechanisms

| 机制 | 说明 |
|------|------|
| **Point-in-Time** | 无未来函数，快照时间戳锁定 |
| **PIT** | No look-ahead bias, snapshot timestamp locked |
| **单源锁定** | 腾讯 hfq 复权，防跨源污染 |
| **Source Lock** | Tencent hfq only, prevents cross-source contamination |
| **Append-only 日志** | git commit 作防篡改时间戳 |
| **Append-only Log** | git commit as tamper-evident timestamp |
| **双基准对比** | p=0.5 恒定基准 + 动量规则基准 |
| **Dual Baselines** | p=0.5 constant + momentum rule baselines |

---

## 授权机制 | License Mechanism

本项目采用**授权码机制**，保护核心预测功能：

This project uses **license code mechanism** to protect core prediction features:

| 功能 | 授权要求 | Feature | License Required |
|------|---------|---------|-----------------|
| `fetch_snapshots.py` 数据抓取 | ✅ 无需授权 | Data fetching | ✅ No |
| `predict_batch.py` 批量预测 | 🔒 需要授权 | Batch prediction | 🔒 Yes |
| `predict_single.py` 单只预测 | 🔒 需要授权 | Single prediction | 🔒 Yes |
| `settle.py` 到期结算 | 🔒 需要授权 | Settlement | 🔒 Yes |
| `daily_run.sh` 完整流程 | 🔒 需要授权 | Full pipeline | 🔒 Yes |

### 获取授权 | Get License

1. **获取机器指纹** | Get machine fingerprint:
   ```bash
   python3 scripts/license_manager.py
   ```

2. **发送指纹给作者** | Send fingerprint to author

3. **保存授权码** | Save license to `~/.stock_predict_license`:
   ```json
   {
     "license_code": "你的授权码",
     "machine_fingerprint": "你的机器指纹"
   }
   ```

4. **授权绑定机器** | License binds to machine, non-transferable

### 管理员生成授权码 | Admin: Generate License

```bash
python3 scripts/license_manager.py --admin
# 输入用户机器指纹 + 管理员密钥
# Enter user fingerprint + admin secret
```

> **注意**：管理员密钥不公开，只有项目作者持有。  
> **Note**: Admin secret is private, held by project author only.

---

## 快速开始 | Quick Start

### 1. 环境准备 | Environment Setup

```bash
# 创建虚拟环境 | Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 安装依赖 | Install dependencies
pip install akshare pandas

# 设置 OpenRouter API key | Set OpenRouter API key
export OPENROUTER_API_KEY="your-key-here"
# 或创建 ~/.openrouter_api_key 文件
# Or create ~/.openrouter_api_key file
```

### 2. 配置模型 | Configure Model

```bash
export STOCK_PREDICT_MODEL="deepseek/deepseek-chat"  # 或其他 OpenRouter 模型
```

### 3. 运行 | Run

```bash
# 手动单次运行 | Manual run
cd validation
bash scripts/daily_run.sh

# 或分步运行 | Or step by step
python3 scripts/fetch_snapshots.py   # 抓取快照 | Fetch snapshots
python3 scripts/predict_batch.py     # 批量预测（需授权）| Batch predict (license required)
python3 scripts/settle.py            # 到期结算（需授权）| Settle (license required)
```

### 4. 自动化 | Automation

项目包含 `daily_check.sh` 用于每日自动检查+补跑，可通过 cron/launchd/Hermes 调度。

Includes `daily_check.sh` for daily auto-check + catch-up, schedulable via cron/launchd/Hermes.

---

## 文件说明 | File Structure

| 文件 | 说明 | File | Description |
|------|------|------|-------------|
| `rules.yaml` | 冻结规则（v1.0），验证期内不得修改 | Frozen rules (v1.0), no modification during validation |
| `scripts/fetch_snapshots.py` | 数据抓取 + 确定性快照生成（腾讯 hfq 单源锁定） | Data fetch + deterministic snapshot (Tencent hfq locked) |
| `scripts/predict_batch.py` | 批量预测（OpenRouter，幂等设计，需授权） | Batch prediction (OpenRouter, idempotent, license required) |
| `scripts/predict_single.py` | 单只测试（需授权） | Single test (license required) |
| `scripts/settle.py` | 到期结算（Brier/LogLoss vs 基准，需授权） | Settlement (Brier/LogLoss vs baselines, license required) |
| `scripts/daily_run.sh` | 每日完整流程 | Daily full pipeline |
| `scripts/daily_check.sh` | 每日检查+补跑（防休眠漏跑） | Daily check + catch-up (prevents sleep miss) |
| `scripts/license_manager.py` | 授权管理（机器指纹绑定） | License management (machine fingerprint binding) |

---

## 技术架构 | Technical Architecture

### 快照指标 | Snapshot Indicators

| 指标 | 说明 | Indicator | Description |
|------|------|-----------|-------------|
| `ret5` / `ret20` | 5日/20日收益率 | 5-day/20-day return |
| `excess20_vs_csi300` | 20日超额收益 vs 沪深300 | 20-day excess return vs CSI300 |
| `close_over_ma20` | 收盘价/MA20 偏离 | Close/MA20 deviation |
| `vol20_daily` | 20日波动率 | 20-day volatility |
| `rsi14` | RSI(14) 超买超卖 | RSI(14) overbought/oversold |
| `bollinger_pct_b` | 布林带 %B 位置 | Bollinger %B position |
| `market_regime` | 市场状态（trend/range） | Market regime (trend/range) |
| `turnover_last` | 换手率 | Turnover rate |

### 市场状态判断 | Market Regime Detection

| 状态 | 条件 | 策略 |
|------|------|------|
| **trend** | MA20 偏离 >2% 或 <-2% | 动量信号更可靠 |
| **range** | MA20 偏离 <2% | 动量信号可靠性降低，关注均值回复 |

| Regime | Condition | Strategy |
|--------|-----------|----------|
| **trend** | MA20 deviation >2% or <-2% | Momentum signals more reliable |
| **range** | MA20 deviation <2% | Momentum less reliable, watch mean reversion |

---

## 合规声明 | Compliance

- 本项目仅供**学习研究**，不构成任何投资建议  
  This project is for **research only**, not investment advice
- 不输出买卖指令，只输出概率和统计指标  
  No buy/sell directives, only probabilities and statistics
- 数据来源：AkShare（腾讯/新浪/东财公开接口）  
  Data source: AkShare (Tencent/Sina/EastMoney public APIs)
- 模型服务：OpenRouter（用户自备 API key）  
  Model service: OpenRouter (user-provided API key)
- 授权机制保护核心预测功能，防止未授权商业使用  
  License mechanism protects core features, prevents unauthorized commercial use

---

## 许可证 | License

MIT License — 仅供学习研究使用， commercial use prohibited without authorization.  
MIT License — For research only, commercial use prohibited without authorization.

---

## 致谢 | Acknowledgments

- 数据接口：[AkShare](https://github.com/akfamily/akshare)  
  Data API: [AkShare](https://github.com/akfamily/akshare)
- 模型服务：[OpenRouter](https://openrouter.ai/)  
  Model service: [OpenRouter](https://openrouter.ai/)
- 设计参考：TradingAgents (arXiv 2412.20138), daily_stock_analysis (MIT)  
  Design reference: TradingAgents (arXiv 2412.20138), daily_stock_analysis (MIT)

---

## 联系方式 | Contact

- **作者** | Author: alan12-li
- **授权申请** | License request: 请通过 GitHub Issues 联系 | Please contact via GitHub Issues
- **问题反馈** | Bug report: GitHub Issues

---

> ⚠️ **免责声明** | Disclaimer  
> 股市有风险，投资需谨慎。本项目输出仅为概率研究，不构成投资建议。  
> Stock market involves risks. This project output is probability research only, not investment advice.
