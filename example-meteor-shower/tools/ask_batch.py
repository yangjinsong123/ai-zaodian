"""只造句（不测冷启动 / 现场）：python ask_batch.py <日志目录> <词表 json> <起始种子> [只跑这些词，逗号分隔]
请求格式和 ask.py 完全一样，每个词的种子 = 起始种子 + 词序号；所有原始返回写进 <日志目录>/raw_batch.jsonl。"""
import json, sys, os
sys.argv = [sys.argv[0]] + sys.argv[1:]
LOG, WF, SEED0 = sys.argv[1], sys.argv[2], int(sys.argv[3]); ONLY = set(sys.argv[4].split(",")) if len(sys.argv) > 4 else None
sys.argv = [sys.argv[0], LOG, WF]
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ask.py"), encoding="utf-8").read()
src = src[:src.index('ask(COLD, 1115, "cold")')]            # 复用 ask.py 里的 ask()，不跑冷启动 / 现场
exec(compile(src, "ask.py", "exec"))
for i, w in enumerate(WORDS):
    if ONLY is None or w["word"] in ONLY: ask(w["word"], SEED0 + i, "batch")
print("done", now())
