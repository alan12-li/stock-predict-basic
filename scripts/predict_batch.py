"""股票初级预测验证系统 v0 — 批量预测（模型槽：OpenRouter）
读取确定性快照 → 每只股票一次调用 → 输出 3 周期概率 → append-only 留痕
合规：只输出概率+证据，禁指令性词汇。快照为唯一数字真源。
"""
import json, os, sys, time, datetime, pathlib, re
import urllib.request

BASE = pathlib.Path(__file__).resolve().parent.parent
TODAY = datetime.date.today().isoformat()
MODEL = os.environ.get("STOCK_PREDICT_MODEL", "moonshotai/kimi-k3")
KEY = open(os.path.expanduser("~/.openrouter_api_key")).read().strip()

SYSTEM = """你是A股相对表现研究助手。基于给定的确定性行情快照（唯一数字真源，不得自行编造任何价格/指标数字），
评估该股票未来N个交易日相对沪深300指数的超额收益为正的概率。

规则:
1. 只输出概率和依据，禁止出现: 买入/卖出/加仓/减仓/目标价/建议 等任何指令性词汇。
2. 概率必须校准: 无明显信号时应接近0.50; 偏离0.50越远，快照中必须有越强的依据。
3. 仅依据快照数据推理（动量/均线偏离/波动率/流动性/RSI/布林带），不得假设任何快照外的消息或基本面。
4. 严格按JSON输出: {"p5": 0.XX, "p10": 0.XX, "p20": 0.XX, "evidence": ["依据1", "依据2"]}
5. 市场状态感知: 快照含 market_regime 字段。当 regime=range（震荡市）时，动量/趋势信号可靠性降低，需更关注 RSI 超买超卖和均值回复风险；当 regime=trend（趋势市）时，动量信号更可靠。"""

def call_model(snap: dict) -> dict | None:
    # 注入市场状态到 user prompt（显式提醒模型当前 regime）
    regime_note = ""
    if snap.get("market_regime"):
        regime_note = f"\n【市场状态】当前为 {snap['market_regime']} ({snap.get('regime_strength','')})。"
        if snap['market_regime'] == 'range':
            regime_note += "震荡市中动量信号可靠性降低，注意均值回复风险，RSI 超买超卖更关键。"
        else:
            regime_note += "趋势市中动量信号更可靠，但需警惕趋势末端的反转。"
    user = f"快照(来源:{snap['source']}, 抓取:{snap['fetch_ts']}):{regime_note}\n" + json.dumps(
        {k: v for k, v in snap.items() if k not in ("source", "fetch_ts", "market_regime", "regime_strength")}, ensure_ascii=False)
    body = json.dumps({
        "model": MODEL, "temperature": 0.2, "max_tokens": 1500,
        "messages": [{"role": "system", "content": SYSTEM},
                     {"role": "user", "content": user}],
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                resp = json.load(r)
            if not resp.get("choices"):
                raise ValueError(f"OpenRouter 无 choices: {resp}")
            txt = resp["choices"][0].get("message", {}).get("content")
            if not txt:
                raise ValueError(f"content 为空 (upstream 瞬时失败)")
            m = re.search(r"\{.*\}", txt, re.DOTALL)
            if not m:
                raise ValueError("模型未返回 JSON")
            out = json.loads(m.group(0))
            usage = resp.get("usage", {})
            # 概率合法性检查
            for k in ("p5", "p10", "p20"):
                p = float(out[k])
                if not (0.0 <= p <= 1.0):
                    raise ValueError(f"{k}={p} 越界")
                out[k] = round(p, 2)
            # 合规词检查
            ev = " ".join(out.get("evidence", []))
            for w in ("买入", "卖出", "加仓", "减仓", "目标价"):
                if w in ev:
                    raise ValueError(f"证据含禁词: {w}")
            return {"ok": True, "pred": out,
                    "tokens_in": usage.get("prompt_tokens"), "tokens_out": usage.get("completion_tokens")}
        except Exception as e:
            print(f"  [{snap['code']}] try{attempt+1}: {type(e).__name__}: {str(e)[:80]}", flush=True)
            time.sleep(4)
    return None

def main():
    # 授权检查：未授权用户无法运行预测
    from license_manager import require_license
    require_license("批量预测")
    snap_file = BASE / "data" / f"snapshots_{TODAY}.jsonl"
    if not snap_file.exists():
        sys.exit(f"FATAL: 找不到 {snap_file}，先跑 fetch_snapshots.py")
    snaps = [json.loads(l) for l in open(snap_file, encoding="utf-8")]
    print(f"载入快照 {len(snaps)} 只 | 模型 {MODEL}", flush=True)

    (BASE / "logs").mkdir(exist_ok=True)
    log_file = BASE / "logs" / "predictions.md"
    # 幂等：跳过今天已预测的代码
    done = set()
    if log_file.exists():
        for line in open(log_file, encoding="utf-8"):
            m = re.match(rf"\[{TODAY} \| (\d{{6}}) \|", line)
            if m:
                done.add(m.group(1))
    total_in = total_out = n_ok = n_fail = 0
    t0 = time.time()
    with open(log_file, "a", encoding="utf-8") as f:
        for i, snap in enumerate(snaps):
            if snap["code"] in done:
                continue
            r = call_model(snap)
            if r is None:
                n_fail += 1
                continue
            p = r["pred"]
            ev = "; ".join(p.get("evidence", []))[:200]
            # 每个周期一行，两阶段生命周期: pending → resolved
            for N, pk in ((5, "p5"), (10, "p10"), (20, "p20")):
                f.write(f"[{TODAY} | {snap['code']} | {snap['name']} | N={N} | {MODEL} | p={p[pk]:.2f} | pending]\n")
            f.write(f"  evidence: {ev}\n\n")
            f.flush()
            n_ok += 1
            total_in += r["tokens_in"] or 0
            total_out += r["tokens_out"] or 0
            if (i + 1) % 10 == 0:
                print(f"[{i+1}/{len(snaps)}] ok={n_ok} fail={n_fail} tokens={total_in}+{total_out} {time.time()-t0:.0f}s", flush=True)
            time.sleep(0.3)
    print(f"DONE ok={n_ok} fail={n_fail} | tokens: in={total_in} out={total_out} | {time.time()-t0:.0f}s", flush=True)
    # 用量存档
    with open(BASE / "logs" / f"usage_{TODAY}.json", "w") as f:
        json.dump({"date": TODAY, "model": MODEL, "n_ok": n_ok, "n_fail": n_fail,
                   "tokens_in": total_in, "tokens_out": total_out}, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
