"""向本机 127.0.0.1:11434 的 Ollama 发造句请求，流式读回，每个片段记下到达时间。只用标准库。
所有原始返回（Ollama 每一行 JSON）原样写进日志，作为「模型实际输出」的凭证。
用法（在 offline_run.sh 里跑）：python ask.py <日志目录> <词表 json> [cold_word] [live_word]
顺序：①冷启动：服务刚起、模型还没加载，造第一句（测首字等待）②逐词造 30 句 ③热状态下现场再造一句（测 token/s）"""
import json, sys, time, urllib.request, datetime, os
LOG, WORDS = sys.argv[1], json.load(open(sys.argv[2], encoding="utf-8"))["words"]
COLD = sys.argv[3] if len(sys.argv) > 3 else "persist"; LIVE = sys.argv[4] if len(sys.argv) > 4 else "persist"
MODEL = os.environ.get("MODEL", "qwen25-1.5b-local")
PROMPT = 'Write one short, natural English example sentence (8 to 15 words) using the word "{w}". Reply with the sentence only.'
def now(): return datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")
def ask(word, seed, tag):
    body = {"model": MODEL, "prompt": PROMPT.format(w=word), "stream": True,
            "options": {"temperature": 0.7, "seed": seed, "num_predict": 64}}
    req = urllib.request.Request("http://127.0.0.1:11434/api/generate", json.dumps(body).encode(), {"Content-Type": "application/json"})
    rec = {"tag": tag, "word": word, "request": body, "sent_at": now(), "chunks": []}
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=600) as r:
        for line in r:
            t = time.perf_counter() - t0; j = json.loads(line)
            rec["chunks"].append({"t": round(t, 4), "raw": line.decode().rstrip("\n")})
            if j.get("done"): rec["final"] = j
    rec["text"] = "".join(json.loads(c["raw"]).get("response", "") for c in rec["chunks"])
    toks = [c["t"] for c in rec["chunks"] if json.loads(c["raw"]).get("response")]
    f = rec["final"]
    rec["measure"] = {
        "首字等待_s（请求发出→第一个字到达，墙钟）": round(toks[0], 3) if toks else None,
        "总耗时_s（墙钟）": round(rec["chunks"][-1]["t"], 3),
        "load_duration_s（Ollama 自报：加载模型）": round(f.get("load_duration", 0) / 1e9, 3),
        "prompt_eval": [f.get("prompt_eval_count"), round(f.get("prompt_eval_duration", 0) / 1e9, 3)],
        "eval_count": f.get("eval_count"), "eval_duration_s": round(f.get("eval_duration", 0) / 1e9, 3),
        "token_per_s（Ollama 自报 eval_count/eval_duration）": round(f["eval_count"] / (f["eval_duration"] / 1e9), 2) if f.get("eval_duration") else None,
    }
    with open(f"{LOG}/raw_{tag}.jsonl", "a", encoding="utf-8") as fo: fo.write(json.dumps(rec, ensure_ascii=False) + "\n")
    print(f"[{tag}] {word}: {rec['text'].strip()}  | {rec['measure']}", flush=True)
    return rec
ask(COLD, 1115, "cold")
for i, w in enumerate(WORDS): ask(w["word"], 2000 + i, "batch")
ask(LIVE, 9115, "live")
print("done", now())
