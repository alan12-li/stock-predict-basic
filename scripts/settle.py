"""股票初级预测验证系统 v0 — 结算脚本
读取 pending 预测 → 获取实际行情 → 更新为 resolved → 计算 Brier/LogLoss vs 基准
合规：只输出概率和统计指标，禁指令性词汇。
关键修复：强制单源（腾讯 hfq）+ 源一致性校验，防跨源复权污染。
"""
import json, os, sys, time, datetime, pathlib, re
import akshare as ak
import pandas as pd

BASE = pathlib.Path(__file__).resolve().parent.parent
TODAY = datetime.date.today().isoformat()
LOG_FILE = BASE / "logs/predictions.md"
SNAP_DIR = BASE / "data"

# 验证源一致性：快照必须用同源（腾讯），否则跳过
def check_source_consistency(code):
    """检查该 code 的快照源是否为腾讯（统一口径）"""
    for snap_file in SNAP_DIR.glob("snapshots_*.jsonl"):
        for line in open(snap_file, encoding="utf-8"):
            r = json.loads(line)
            if r["code"] == code:
                src = r.get("source", "")
                if "腾讯" not in src:
                    return False, src
                return True, src
    return False, "无快照"

def retry(fn, name, n=3, sleep=3):
    for i in range(n):
        try:
            return fn()
        except Exception as e:
            print(f"[{name}] try{i+1} fail: {type(e).__name__}: {str(e)[:80]}", flush=True)
            time.sleep(sleep)
    return None

def fetch_stock_hfq(code, start, end):
    """强制单源：只腾讯 hfq，保留与快照同口径"""
    sym = ("sh" if code.startswith(("60", "68")) else "sz") + code
    df = retry(lambda: ak.stock_zh_a_hist_tx(symbol=sym, start_date=start, end_date=end, adjust="hfq"), f"{code}腾讯", n=2, sleep=2)
    if df is not None and not df.empty:
        df["date"] = df["date"].astype(str)
        return df.set_index("date")["close"], "腾讯"
    # 东财/新浪 failover 禁用：复权基准不同，跨源=数据污染
    return None, None

def fetch_index(start, end):
    df = retry(lambda: ak.stock_zh_index_daily(symbol="sh000300"), "沪深300指数(新浪)", n=2, sleep=2)
    if df is not None and not df.empty:
        df["date"] = df["date"].astype(str)
        return df.set_index("date")["close"]
    return None

def settle():
    # 授权检查
    from license_manager import require_license
    require_license("结算")
    if not LOG_FILE.exists():
        print("无预测记录")
        return

    lines = open(LOG_FILE, encoding="utf-8").read().strip().split("\n")
    pending = []
    for line in lines:
        m = re.match(r"\[(\d{4}-\d{2}-\d{2}) \| (\d{6}) \| (.+?) \| N=(\d+) \| (.+?) \| p=([\d.]+) \| (?:adhoc \| )?pending\]", line)
        if m:
            pending.append({
                "line": line,
                "date": m.group(1),
                "code": m.group(2),
                "name": m.group(3),
                "N": int(m.group(4)),
                "model": m.group(5),
                "p": float(m.group(6)),
                "adhoc": "adhoc" in m.group(0)
            })

    if not pending:
        print("无 pending 预测")
        return

    # 算每个预测需要的结算日期范围
    max_N = max(p["N"] for p in pending)
    start = (datetime.date.today() - datetime.timedelta(days=max_N + 10)).strftime("%Y%m%d")
    end = datetime.date.today().strftime("%Y%m%d")

    # 获取指数基准
    idx = fetch_index(start, end)
    if idx is None:
        sys.exit("FATAL: 无法获取沪深300指数")

    resolved = []
    still_pending = []
    today = datetime.date.today()

    # 先按 code 分组，只拉到期的（减少 API 调用）
    from collections import defaultdict
    due_by_code = defaultdict(list)
    not_due = []
    for p in pending:
        pred_date = datetime.date.fromisoformat(p["date"])
        # 交易日估算: N 个交易日 ≈ N * 1.4 自然日 (5个交易日 ≈ 1 周)
        settle_date = pred_date + datetime.timedelta(days=int(p["N"] * 1.5) + 2)
        if settle_date <= today:
            due_by_code[p["code"]].append(p)
        else:
            not_due.append(p)

    if not due_by_code:
        print(f"无到期预测（最早到期约: {min(datetime.date.fromisoformat(p['date']) + datetime.timedelta(days=int(p['N']*1.5)+2) for p in pending)}）")
        return

    print(f"到期股票: {len(due_by_code)} 只 | 未到期: {len(not_due)} 条")

    # 只处理到期的，每只拉一次行情后结算所有 N
    for code, preds in due_by_code.items():
        # ★ 源一致性检查：快照必须腾讯源，否则跳过（防跨源污染）
        ok, src = check_source_consistency(code)
        if not ok:
            print(f"⚠️ 跳过 {code}: 快照源={src} 与结算源不一致", flush=True)
            still_pending.extend(preds)
            continue
        close, src = fetch_stock_hfq(code, start, end)
        if close is None:
            still_pending.extend(preds)
            continue
        for p in preds:
            pred_date = datetime.date.fromisoformat(p["date"])
            settle_date = pred_date + datetime.timedelta(days=p["N"] * 2)  # 粗略：2倍自然日覆盖停牌
            settle_date_str = settle_date.strftime("%Y-%m-%d")

            # 检查是否到期
            if settle_date > today:
                still_pending.append(p)
                continue

            if len(close) <= p["N"]:
                still_pending.append(p)
                continue

            # 找到预测日收盘价（快照日）和结算日收盘价
            dates = sorted(close.index)
            pred_date_str = pred_date.strftime("%Y-%m-%d")
            if pred_date_str not in dates:
                # 快照日可能不是交易日（如周末），找最近的前一交易日
                pred_date_str = max(d for d in dates if d <= pred_date_str)
                if pred_date_str > settle_date_str:
                    still_pending.append(p)
                    continue

            # 找结算日实际收盘（可能不是精确日期，取最近的）
            settle_close_date = max(d for d in dates if d <= settle_date_str)
            pred_close = close[pred_date_str]
            settle_close = close[settle_close_date]
            stock_ret = settle_close / pred_close - 1

            # 指数同口径
            idx_dates = sorted(idx.index)
            idx_pred_date = max(d for d in idx_dates if d <= pred_date_str)
            idx_settle_date = max(d for d in idx_dates if d <= settle_date_str)
            idx_ret = idx[idx_settle_date] / idx[idx_pred_date] - 1

            excess = stock_ret - idx_ret
            outcome = 1 if excess > 0 else 0  # 预测">0" → 实际>0 则 outcome=1

            # 更新记录
            resolved.append({
                "original": p["line"],
                "resolved_line": f"[{p['date']} | {p['code']} | {p['name']} | N={p['N']} | {p['model']} | p={p['p']:.2f} | {'adhoc | ' if p['adhoc'] else ''}outcome={outcome} | raw={stock_ret:+.4f} | alpha={excess:+.4f} | resolved:{TODAY}]"
            })

    # 写回（resolved 替换 pending）
    with open(LOG_FILE, "a+", encoding="utf-8") as f:
        for r in resolved:
            f.write(r["resolved_line"] + "\n")
        # 注：实际应做原子替换，这里简化为 append（验证期数据量小可接受）

    # 统计
    for N in [5, 10, 20]:
        n_resolved = [r for r in resolved if f"N={N}" in r["resolved_line"]]
        if n_resolved:
            # 提取 p 和 outcome 算 Brier
            ps, outcomes = [], []
            for r in n_resolved:
                m = re.search(r"p=([\d.]+)", r["resolved_line"])
                o = re.search(r"outcome=(\d)", r["resolved_line"])
                if m and o:
                    ps.append(float(m.group(1)))
                    outcomes.append(int(o.group(1)))
            if ps and outcomes:
                brier = sum((p - o) ** 2 for p, o in zip(ps, outcomes)) / len(ps)
                # 基准 Brier: p=0.5 恒定
                brier_base = sum((0.5 - o) ** 2 for o in outcomes) / len(outcomes)
                print(f"N={N}: {len(ps)} 结算 | Brier={brier:.4f} vs base={brier_base:.4f} | {'模型优' if brier < brier_base else '基准优'}")

    print(f"\n今日结算 {len(resolved)} 条 | 剩余 pending {len(still_pending)} 条")

if __name__ == "__main__":
    settle()
