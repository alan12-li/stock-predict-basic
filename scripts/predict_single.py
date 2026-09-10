"""股票初级预测 — 单只股票按需预测（系统B形态，ad-hoc）
用法: python predict_single.py 600519
结果写 logs/adhoc_predictions.md（与验证主日志分开，防样本污染）
"""
import json, os, re, sys, time, datetime, pathlib
import urllib.request
import akshare as ak
import pandas as pd

BASE = pathlib.Path(__file__).resolve().parent.parent
TODAY = datetime.date.today().isoformat()
FETCH_TS = datetime.datetime.now().isoformat(timespec="seconds")
MODEL = os.environ.get("STOCK_PREDICT_MODEL", "moonshotai/kimi-k3")
DAILY_BUDGET_USD = float(os.environ.get("NIUNIU_DAILY_BUDGET", "1.5"))  # 硬预算，超了立即停止
KEY = open(os.path.expanduser("~/.openrouter_api_key")).read().strip()

start = (datetime.date.today() - datetime.timedelta(days=100)).strftime("%Y%m%d")
end = datetime.date.today().strftime("%Y%m%d")

def retry(fn, name, n=3, sleep=2):
    for i in range(n):
        try:
            return fn()
        except Exception as e:
            print(f"[{name}] try{i+1}: {type(e).__name__}: {str(e)[:70]}", flush=True)
            time.sleep(sleep)
    return None

def fetch_index():
    df = retry(lambda: ak.index_zh_a_hist(symbol="000300", period="daily", start_date=start, end_date=end), "指数东财", n=1)
    if df is not None and not df.empty:
        df["日期"] = df["日期"].astype(str)
        return df.set_index("日期")["收盘"], "东财"
    df = retry(lambda: ak.stock_zh_index_daily(symbol="sh000300"), "指数新浪", n=3)
    if df is not None and not df.empty:
        df["date"] = df["date"].astype(str)
        df = df[df["date"] >= f"{start[:4]}-{start[4:6]}-{start[6:]}"]
        return df.set_index("date")["close"], "新浪"
    return None, None

def fetch_stock(code):
    df = retry(lambda: ak.stock_zh_a_hist(symbol=code, period="daily",
               start_date=start, end_date=end, adjust="hfq"), f"{code}东财", n=1, sleep=1)
    if df is not None and not df.empty:
        df["日期"] = df["日期"].astype(str)
        return df, "东财"
    sym = ("sh" if code.startswith(("60", "68")) else "sz") + code
    df = retry(lambda: ak.stock_zh_a_hist_tx(symbol=sym, start_date=start, end_date=end, adjust="hfq"), f"{code}腾讯", n=2)
    if df is not None and not df.empty:
        df = df.rename(columns={"date": "日期", "close": "收盘", "amount": "成交额"})
        df["日期"] = df["日期"].astype(str)
        df["换手率"] = df["turnover"] * 100 if "turnover" in df.columns else None
        return df, "腾讯"
    df = retry(lambda: ak.stock_zh_a_daily(symbol=sym, start_date=start, end_date=end, adjust="hfq"), f"{code}新浪", n=2)
    if df is not None and not df.empty:
        df = df.rename(columns={"date": "日期", "close": "收盘", "amount": "成交额"})
        df["日期"] = df["日期"].astype(str)
        if "换手率" not in df.columns:
            df["换手率"] = None
        return df, "新浪"
    return None, None

def get_name(code):
    try:
        lst = ak.stock_info_a_code_name()
        row = lst[lst["code"].astype(str).str.zfill(6) == code]
        return row["name"].iloc[0] if len(row) else code
    except Exception:
        return code

SYSTEM = """你是A股相对表现研究助手。基于给定的确定性行情快照（唯一数字真源，不得自行编造任何价格/指标数字），
评估该股票未来N个交易日相对沪深300指数的超额收益为正的概率。

规则:
1. 只输出概率和依据，禁止出现: 买入/卖出/加仓/减仓/目标价/建议 等任何指令性词汇。
2. 概率必须校准: 无明显信号时应接近0.50; 偏离0.50越远，快照中必须有越强的依据。
3. 仅依据快照数据推理（动量/均线偏离/波动率/流动性），不得假设任何快照外的消息或基本面。
4. 严格按JSON输出: {"p5": 0.XX, "p10": 0.XX, "p20": 0.XX, "evidence": ["依据1", "依据2"]}"""

def main():
    # 授权检查
    from license_manager import require_license
    require_license("单只预测")
    code = sys.argv[1].strip() if len(sys.argv) > 1 else sys.exit("用法: predict_single.py <6位代码>")
    code = code.zfill(6)
    name = get_name(code)
    print(f"== {code} {name} | {FETCH_TS} ==", flush=True)

    idx_close, idx_src = fetch_index()
    if idx_close is None:
        sys.exit("FATAL: 指数不可得")
    idx_ret20 = float(idx_close.iloc[-1] / idx_close.iloc[-21] - 1)

    df, src = fetch_stock(code)
    if df is None or len(df) < 25:
        sys.exit(f"FATAL: {code} 行情不可得或不足25日")
    c = df["收盘"].astype(float)
    ma20 = float(c.tail(20).mean())
    turn = df["换手率"].iloc[-1] if "换手率" in df.columns else None
    turn = float(turn) if turn is not None and pd.notna(turn) else None
    snap = {
        "code": code, "name": name, "date": df["日期"].iloc[-1],
        "close_hfq": round(float(c.iloc[-1]), 2),
        "ret5": round(float(c.iloc[-1]/c.iloc[-6]-1), 4),
        "ret20": round(float(c.iloc[-1]/c.iloc[-21]-1), 4),
        "excess20_vs_csi300": round(float(c.iloc[-1]/c.iloc[-21]-1) - idx_ret20, 4),
        "ma20_hfq": round(ma20, 2),
        "close_over_ma20": round(float(c.iloc[-1])/ma20 - 1, 4),
        "vol20_daily": round(float(c.tail(21).pct_change().dropna().std()), 4),
        "amount_last_yi": round(float(df["成交额"].iloc[-1])/1e8, 2),
        "turnover_last": turn,
        "recent5_close": [round(float(x), 2) for x in c.tail(5)],
    }
    print("确定性快照(源:%s hfq, 指数源:%s):" % (src, idx_src), flush=True)
    print(json.dumps(snap, ensure_ascii=False, indent=1), flush=True)

    body = json.dumps({
        "model": MODEL, "temperature": 0.2, "max_tokens": 1500,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": f"快照(源:akshare {src} hfq, 抓取:{FETCH_TS}):\n" + json.dumps(snap, ensure_ascii=False)}],
        "usage": {"include": True}
    }).encode()
    req = urllib.request.Request("https://openrouter.ai/api/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        resp = json.load(r)
    choices = resp.get("choices")
    if not choices:
        sys.exit(f"OpenRouter 无 choices: {resp}")
    txt = choices[0].get("message", {}).get("content")
    if not txt:
        sys.exit(f"content 为空 (upstream 瞬时失败), 响应: {choices[0]}")
    match = re.search(r"\{.*\}", txt, re.DOTALL)
    if not match:
        sys.exit(f"模型未返回 JSON: {txt!r}")
    out = json.loads(match.group(0))
    usage = resp.get("usage", {})
    for k in ("p5", "p10", "p20"):
        p = float(out[k])
        assert 0 <= p <= 1, f"{k} 越界"
        out[k] = round(p, 2)
    ev = " ".join(out.get("evidence", []))
    for w in ("买入", "卖出", "加仓", "减仓", "目标价"):
        assert w not in ev, f"禁词: {w}"

    print("\n== 模型输出 ==", flush=True)
    print(json.dumps(out, ensure_ascii=False, indent=1), flush=True)
    print(f"tokens: in={usage.get('prompt_tokens')} out={usage.get('completion_tokens')}", flush=True)

    (BASE / "logs").mkdir(exist_ok=True)
    with open(BASE / "logs" / "adhoc_predictions.md", "a", encoding="utf-8") as f:
        for N, pk in ((5, "p5"), (10, "p10"), (20, "p20")):
            f.write(f"[{TODAY} | {code} | {name} | N={N} | {MODEL} | p={out[pk]:.2f} | adhoc | pending]\n")
        f.write(f"  snapshot_date: {snap['date']} | evidence: {'; '.join(out.get('evidence', []))[:300]}\n\n")
    print(f"\n已留痕 → logs/adhoc_predictions.md (adhoc 标记，不入验证主样本)", flush=True)

if __name__ == "__main__":
    main()
