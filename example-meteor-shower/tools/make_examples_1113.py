"""从 11/13 的原始日志汇总 data/examples_20261113.json（成片用这一份；11/12 的 examples.json 原样保留）。
句子逐字照抄日志里 response 的拼接（只去掉首尾空白，引号等原样保留），标出采用哪一句、没采用的写明原因。
核对标准同 make_examples.py：①出现目标词本身或其屈折形式（派生词、换词不算）②没有明显语法错误、搭配不当或语义别扭；
另外 ③不含真实人名。核对由制作（AI 代理）按这几条做，没有经过真人核对。"""
import json, os
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); L = f"{HERE}/logs" if os.path.isdir(f"{HERE}/logs") else f"{HERE}/logs_clean"   # 开源包里只有脱敏副本 logs_clean/，内容（response、时间）与原始日志相同
W = json.load(open(f"{HERE}/data/words.json", encoding="utf-8"))["words"]
LOGS = ["film_20261113/raw_cold.jsonl", "film_20261113/raw_live.jsonl", "batch_20261113/raw_batch.jsonl", "retry_20261113/raw_batch.jsonl",
        "retry_20261113/r2/raw_batch.jsonl", "retry_20261113/r8000/raw_batch.jsonl", "retry_20261113/r9000/raw_batch.jsonl", "retry_20261113/r10000/raw_batch.jsonl"]
outs = {}
for p in LOGS:
    for line in open(f"{L}/{p}", encoding="utf-8"):
        r = json.loads(line)
        outs.setdefault(r["word"], []).append(dict(text=r["text"].strip(), log=f"logs/{p}", tag=r["tag"], seed=r["request"]["options"]["seed"], sent_at=r["sent_at"]))
PICK = {"obvious": 6024, "available": 7008, "sufficient": 7028, "anxiety": 8004, "priority": 9026, "reluctant": 9027}   # 其余用 batch 种子 5000+i
WHY = {
 1115: {"persist": "冷启动测速那一句：用的是派生词 persistent，不是 persist 本身"},
 9115: {"persist": "第 9 镜现场演示这一句（可用）；流星雨里用 batch 那一句"},
 5004: {"anxiety": "没用到 anxiety：写成了形容词 anxious"}, 6004: {"anxiety": "没用到 anxiety（anxious）"}, 7004: {"anxiety": "没用到 anxiety（anxious）"},
 5008: {"available": "语义不通：天气不能 available"}, 6008: {"available": "搭配别扭：recommend a book on the available topics"},
 5024: {"obvious": "语义不完整：没有说明能看出什么"}, 7024: {"obvious": "语义别扭：spelled with the letter 'o'"},
 5026: {"priority": "没用到 priority：写成了动词 prioritize"}, 6026: {"priority": "没用到 priority（prioritized）"}, 7026: {"priority": "出现人名 John，不用"},
 8026: {"priority": "没用到 priority，语义也不通"}, 10026: {"priority": "可用，备选（句子偏长）"},
 5027: {"reluctant": "语法别扭：I'm being quite reluctant"}, 6027: {"reluctant": "没用到 reluctant：写成了副词 reluctantly"}, 7027: {"reluctant": "没用到 reluctant（reluctantly）"},
 10027: {"reluctant": "可用，备选（lend you my car 语境稍别扭）"},
 5028: {"sufficient": "没用到 sufficient：写成了 enough"}, 6028: {"sufficient": "可用，备选（不如 7028 自然）"},
}
res = []
for i, w in enumerate(W):
    pick = PICK.get(w["word"], 5000 + i); cands = outs[w["word"]]
    for c in cands:
        c["adopted"] = c["seed"] == pick and c["tag"] == "batch"
        c["note"] = "采用" if c["adopted"] else WHY.get(c["seed"], {}).get(w["word"], "")
        if not c["note"]: raise SystemExit(f"没写原因: {w['word']} {c}")
    ad = [c for c in cands if c["adopted"]]; assert len(ad) == 1, w
    res.append(dict(word=w["word"], cn=w["cn"], sentence=ad[0]["text"], adopted_from=f'{ad[0]["log"]} · seed {ad[0]["seed"]}', all_outputs=cands))
meta = {"model": "Qwen2.5-1.5B-Instruct Q4_K_M（GGUF，Apache-2.0），Ollama 0.40.16（MIT）",
        "prompt": 'Write one short, natural English example sentence (8 to 15 words) using the word "{w}". Reply with the sentence only.',
        "options": "temperature 0.7，num_predict 64，每句固定随机种子（见 all_outputs）",
        "环境": "云电脑 8 核 Intel Xeon、无显卡；模型进程在单独的网络命名空间里运行（unshare -rn），里面只有回环网卡，访问外网失败，见 logs/*/netns_status.txt",
        "核对": "sentence 是模型原始输出，一个字没改（包括模型自己加的引号）。是否采用由制作（AI 代理）按本脚本顶部的标准判断，未经真人核对。",
        "生成时间": "2026-11-13 02:22–03:06（北京时间）"}
json.dump({"meta": meta, "examples": res}, open(f"{HERE}/data/examples_20261113.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(len(res), "条采用；候选总数", sum(len(r["all_outputs"]) for r in res))
for r in res: print(f'{r["word"]:12s} {r["sentence"]}')
