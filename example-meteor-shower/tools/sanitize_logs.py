"""把 logs/*_20261113/ 复制成脱敏副本 logs_clean/（原始日志不动）：本机路径、主机名、内网 IP、MAC、用户名换成占位符。
视频里的日志特写只用 logs_clean/ 里的内容。"""
import os, re, shutil, socket, getpass
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); SRC, DST = f"{HERE}/logs", f"{HERE}/logs_clean"
host = socket.gethostname(); user = getpass.getuser()
RULES = [(re.compile(r"/workspace/[^\s\"']*"), "<项目目录>"), (re.compile(r"/home/[^/\s\"']+"), "~"), (re.compile(r"/root\b"), "~"),
         (re.compile(r"/tmp/[^\s\"']*"), "<临时目录>"),
         (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d+)?\b"), lambda m: m.group(0) if m.group(0).startswith("127.") else "<IP>"),
         (re.compile(r"\b[0-9a-f]{2}(?::[0-9a-f]{2}){5}\b", re.I), lambda m: m.group(0) if m.group(0) == "00:00:00:00:00:00" else "<MAC>"),
         (re.compile(r"\bfe80::[0-9a-f:]+(?:/\d+)?", re.I), "<IPv6>")]
if host: RULES.append((re.compile(re.escape(host)), "<主机名>"))
if user and user not in ("root",): RULES.append((re.compile(rf"\b{re.escape(user)}\b"), "<用户>"))
n = 0
for d in sorted(os.listdir(SRC)):
    if not d.endswith("_20261113"): continue
    for root, _, files in os.walk(f"{SRC}/{d}"):
        for f in files:
            s = open(os.path.join(root, f), encoding="utf-8", errors="replace").read()
            for rx, rep in RULES: s = rx.sub(rep, s)
            out = os.path.join(DST, os.path.relpath(root, SRC), f); os.makedirs(os.path.dirname(out), exist_ok=True); open(out, "w", encoding="utf-8").write(s); n += 1
print(n, "个文件 →", os.path.relpath(DST, HERE))
