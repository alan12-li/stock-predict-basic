"""股票初级预测验证系统 v0 — 数据抓取 + 确定性快照生成
规则见 ../rules.yaml。快照 = LLM 唯一数字真源（防编数字，参考 TradingAgents market_data_validator 模式）
"""
import akshare as ak
import pandas as pd
import json, time, datetime, pathlib, sys

BASE = pathlib.Path(__file__).resolve().parent.parent
TODAY = datetime.date.today().isoformat()
FETCH_TS = datetime.datetime.now().isoformat(timespec="seconds")

def retry(fn, name, n=3, sleep=3):
    for i in range(n):
        try:
            return fn()
        except Exception as e:
            print(f"[{name}] try{i+1} fail: {type(e).__name__}: {str(e)[:80]}", flush=True)
            time.sleep(sleep)
    return None

# ── 1. 股票池：沪深300 成分，按代码升序取前 100（规则化，无人工挑选）──
cons = retry(lambda: ak.index_stock_cons_csindex(symbol="000300"), "CSI300成分")
if cons is None:
    sys.exit("FATAL: 无法获取沪深300成分")
cons = cons.rename(columns=lambda c: c.strip())
code_col = "成分券代码"; name_col = "成分券名称"
pool = cons[[code_col, name_col]].copy()
pool[code_col] = pool[code_col].astype(str).str.zfill(6)
pool = pool.sort_values(code_col).head(100).reset_index(drop=True)
(BASE / "pool").mkdir(exist_ok=True)
pool_file = BASE / "pool" / f"pool_{TODAY}.csv"
pool.to_csv(pool_file, index=False)
print(f"池子已保存 {pool_file} 共{len(pool)}只 | 指数日期: {cons['日期'].iloc[0] if '日期' in cons.columns else '?'}", flush=True)

# ── 2. 基准：沪深300 指数近 60 日 ──
start = (datetime.date.today() - datetime.timedelta(days=100)).strftime("%Y%m%d")
end = datetime.date.today().strftime("%Y%m%d")
def fetch_index():
    """多源 failover: 东财 → 新浪 (DSA DataFetcherManager 模式)"""
    df = retry(lambda: ak.index_zh_a_hist(symbol="000300", period="daily", start_date=start, end_date=end), "沪深300指数(东财)", n=2, sleep=2)
    if df is not None and not df.empty:
        df["日期"] = df["日期"].astype(str)
        return df.set_index("日期")["收盘"], "东财"
    df = retry(lambda: ak.stock_zh_index_daily(symbol="sh000300"), "沪深300指数(新浪)", n=3, sleep=3)
    if df is not None and not df.empty:
        df["date"] = df["date"].astype(str)
        df = df[(df["date"] >= f"{start[:4]}-{start[4:6]}-{start[6:]}")]
        return df.set_index("date")["close"], "新浪"
    return None, None

idx_close, idx_src = fetch_index()
if idx_close is None:
    sys.exit("FATAL: 东财+新浪均无法获取沪深300指数行情")
print(f"指数源: {idx_src}", flush=True)
idx_ret20 = float(idx_close.iloc[-1] / idx_close.iloc[-21] - 1) if len(idx_close) >= 21 else None
print(f"沪深300最新收盘 {idx_close.iloc[-1]} @ {idx_close.index[-1]} | 近20日收益 {idx_ret20:+.2%}", flush=True)

# ── P1 新增：市场状态（regime）判断 ──
# 用 CSI300 的 MA20 偏离 + 波动率判断 trend vs range
idx_series = idx_close.astype(float)
idx_ma20 = float(idx_series.tail(20).mean())
idx_ma20_dev = float(idx_series.iloc[-1] / idx_ma20 - 1) if idx_ma20 > 0 else 0
idx_vol20 = float(idx_series.tail(21).pct_change().dropna().std())
# regime 规则：MA20 偏离 >2% 或 <-2% → trend（趋势市），否则 → range（震荡市）
if abs(idx_ma20_dev) > 0.02:
    market_regime = "trend"
    regime_strength = "strong" if abs(idx_ma20_dev) > 0.04 else "weak"
else:
    market_regime = "range"
    regime_strength = "high_vol" if idx_vol20 > 0.02 else "low_vol"
print(f"市场状态: {market_regime} ({regime_strength}) | MA20偏离 {idx_ma20_dev:+.2%} | 波动率 {idx_vol20:.4f}", flush=True)

# ── 3. 逐只拉日线（hfq）→ 确定性快照 ──
(BASE / "data").mkdir(exist_ok=True)
snap_file = BASE / "data" / f"snapshots_{TODAY}.jsonl"
ok, fail = 0, 0

# ★ P0 修复：强制单源（腾讯 hfq），禁用跨源 failover（防复权污染）
SOURCE_LOCK = "腾讯"

def fetch_stock(code):
    """个股日线强制单源：只腾讯 hfq，返回 (df[日期,收盘,成交额,换手率], 源名)"""
    sym = ("sh" if code.startswith(("60", "68")) else "sz") + code
    df = retry(lambda: ak.stock_zh_a_hist_tx(symbol=sym, start_date=start, end_date=end, adjust="hfq"), f"{code}腾讯", n=2, sleep=2)
    if df is not None and not df.empty:
        df = df.rename(columns={"date": "日期", "close": "收盘", "amount": "成交额"})
        df["日期"] = df["日期"].astype(str)
        df["换手率"] = df["turnover"] * 100 if "turnover" in df.columns else None
        return df, "腾讯"
    # 东财/新浪 failover 禁用：跨源复权基准不同，跨源=数据污染
    return None, None

with open(snap_file, "w", encoding="utf-8") as f:
    for i, row in pool.iterrows():
        code, name = row[code_col], row[name_col]
        df, src = fetch_stock(code)
        if df is None or df.empty or len(df) < 25:
            fail += 1
            print(f"[{i+1}/100] {code} {name} 数据不足，跳过", flush=True)
            continue
        df["日期"] = df["日期"].astype(str)
        c = df["收盘"].astype(float)
        # 确定性指标（纯计算，无 LLM）
        ret5  = float(c.iloc[-1]/c.iloc[-6]-1)  if len(c)>=6  else None
        ret20 = float(c.iloc[-1]/c.iloc[-21]-1) if len(c)>=21 else None
        ma20  = float(c.tail(20).mean())
        vol20 = float(c.tail(21).pct_change().dropna().std())
        # 与基准对齐的近20日超额
        excess20 = (ret20 - idx_ret20) if (ret20 is not None and idx_ret20 is not None) else None
        turn = df["换手率"].iloc[-1] if "换手率" in df.columns else None
        turn = float(turn) if turn is not None and pd.notna(turn) else None

        # ── P0 新增：均值回复指标 ──
        # RSI(14)
        delta = c.diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi14 = float(100 - 100/(1+rs.iloc[-1])) if len(rs) >= 14 and not pd.isna(rs.iloc[-1]) else None
        # 布林带 %B (20,2)
        ma20_bb = c.rolling(20).mean()
        std20 = c.rolling(20).std()
        upper = ma20_bb + 2*std20
        lower = ma20_bb - 2*std20
        pct_b = float((c.iloc[-1] - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1])) if len(upper) >= 20 and not pd.isna(upper.iloc[-1]) and (upper.iloc[-1]-lower.iloc[-1])>0 else None

        snap = {
            "code": code, "name": name, "date": df["日期"].iloc[-1],
            "close_hfq": round(float(c.iloc[-1]), 2),
            "ret5": round(ret5, 4), "ret20": round(ret20, 4),
            "excess20_vs_csi300": round(excess20, 4),
            "ma20_hfq": round(ma20, 2),
            "close_over_ma20": round(float(c.iloc[-1])/ma20 - 1, 4),
            "vol20_daily": round(vol20, 4),
            "amount_last": round(float(df["成交额"].iloc[-1])/1e8, 2),  # 亿元
            "turnover_last": turn,
            "recent5_close": [round(float(x),2) for x in c.tail(5)],
            "rsi14": round(rsi14, 2) if rsi14 else None,
            "bollinger_pct_b": round(pct_b, 4) if pct_b else None,
            "market_regime": market_regime,
            "regime_strength": regime_strength,
            "fetch_ts": FETCH_TS, "source": f"akshare {src} hfq",
        }
        f.write(json.dumps(snap, ensure_ascii=False) + "\n")
        ok += 1
        if (i+1) % 10 == 0:
            print(f"[{i+1}/100] 完成 {ok} 失败 {fail}", flush=True)
        time.sleep(0.5)  # 限速防封

# 基准信息单独存
meta = {"benchmark": "沪深300", "idx_close": float(idx_close.iloc[-1]),
        "idx_date": idx_close.index[-1], "idx_ret20": idx_ret20,
        "idx_ma20_dev": idx_ma20_dev, "idx_vol20": idx_vol20,
        "market_regime": market_regime, "regime_strength": regime_strength,
        "pool_size": len(pool), "snapshots_ok": ok, "snapshots_fail": fail,
        "fetch_ts": FETCH_TS}
with open(BASE / "data" / f"meta_{TODAY}.json", "w", encoding="utf-8") as f:
    json.dump(meta, f, ensure_ascii=False, indent=2)
print(f"DONE 快照 {ok} 只, 失败 {fail} 只 → {snap_file}", flush=True)
