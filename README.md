# 股票初级预测验证系统 (Stock Basic Prediction Validation)

> A股相对表现预测研究项目 — 90 天验证期，非商业化

## 项目定位

这是一个**研究验证项目**，目标是评估 LLM 对 A 股个股相对沪深300指数超额收益的预测能力。项目处于**封闭验证期**，不向公众提供投资建议，不收费，不承诺收益。

## 核心设计

### 预测目标
- **相对表述**：预测未来 N 个交易日相对沪深300指数的超额收益为正的概率（合规安全表述）
- **周期**：N ∈ {5, 10, 20} 个交易日
- **输出**：概率 p ∈ [0,1] + 证据清单（禁指令性词汇：买入/卖出/加仓/减仓/目标价）

### 数据管道
```
fetch_snapshots.py  →  确定性指标快照（唯一数字真源）
       ↓
predict_batch.py   →  LLM 概率输出（OpenRouter）
       ↓
settle.py          →  T+N 结算，计算 Brier/LogLoss
```

### 防作弊机制
- **Point-in-Time**：无未来函数，快照时间戳锁定
- **单源锁定**：腾讯 hfq 复权，防跨源污染
- **Append-only 日志**：git commit 作防篡改时间戳
- **双基准对比**：p=0.5 恒定基准 + 动量规则基准

## 授权机制

本项目采用**授权码机制**，保护核心预测功能：

| 功能 | 授权要求 |
|------|---------|
| `fetch_snapshots.py` 数据抓取 | ✅ 无需授权 |
| `predict_batch.py` 批量预测 | 🔒 需要授权 |
| `predict_single.py` 单只预测 | 🔒 需要授权 |
| `settle.py` 到期结算 | 🔒 需要授权 |
| `daily_run.sh` 完整流程 | 🔒 需要授权 |

### 获取授权

1. 运行以下命令获取你的机器指纹：
   ```bash
   python3 scripts/license_manager.py
   ```

2. 将显示的**机器指纹**发送给项目作者

3. 作者生成授权码后，保存到 `~/.stock_predict_license`：
   ```json
   {
     "license_code": "你的授权码",
     "machine_fingerprint": "你的机器指纹"
   }
   ```

4. 授权码**绑定机器**，不可复制到其他电脑

### 管理员生成授权码

```bash
python3 scripts/license_manager.py --admin
# 输入用户机器指纹 + 管理员密钥
```

> **注意**：管理员密钥不公开，只有项目作者持有。

## 快速开始

### 1. 环境准备

```bash
# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install akshare pandas

# 设置 OpenRouter API key（预测用）
export OPENROUTER_API_KEY="your-key-here"
# 或创建 ~/.openrouter_api_key 文件
```

### 2. 配置模型

```bash
export STOCK_PREDICT_MODEL="deepseek/deepseek-chat"  # 或其他 OpenRouter 模型
```

### 3. 运行

```bash
# 手动单次运行
cd validation
bash scripts/daily_run.sh

# 或分步运行
python3 scripts/fetch_snapshots.py   # 抓取快照
python3 scripts/predict_batch.py     # 批量预测（需授权）
python3 scripts/settle.py            # 到期结算（需授权）
```

### 4. 自动化（可选）

项目包含 `daily_check.sh` 用于每日自动检查+补跑，可通过 cron/launchd/Hermes 调度。

## 文件说明

| 文件 | 说明 |
|------|------|
| `rules.yaml` | 冻结规则（v1.0），验证期内不得修改 |
| `scripts/fetch_snapshots.py` | 数据抓取 + 确定性快照生成（腾讯 hfq 单源锁定） |
| `scripts/predict_batch.py` | 批量预测（OpenRouter，幂等设计，需授权） |
| `scripts/predict_single.py` | 单只测试（需授权） |
| `scripts/settle.py` | 到期结算（Brier/LogLoss vs 基准，需授权） |
| `scripts/daily_run.sh` | 每日完整流程 |
| `scripts/daily_check.sh` | 每日检查+补跑（防休眠漏跑） |
| `scripts/license_manager.py` | 授权管理（机器指纹绑定） |

## 合规声明

- 本项目仅供**学习研究**，不构成任何投资建议
- 不输出买卖指令，只输出概率和统计指标
- 数据来源：AkShare（腾讯/新浪/东财公开接口）
- 模型服务：OpenRouter（用户自备 API key）
- 授权机制保护核心预测功能，防止未授权商业使用

## 许可证

MIT License — 仅供学习研究使用， commercial use prohibited without authorization.

## 致谢

- 数据接口：[AkShare](https://github.com/akfamily/akshare)
- 模型服务：[OpenRouter](https://openrouter.ai/)
- 设计参考：TradingAgents (arXiv 2412.20138), daily_stock_analysis (MIT)
