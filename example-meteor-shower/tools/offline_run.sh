#!/usr/bin/env bash
# 在「只属于这一个进程树」的网络命名空间里跑本地模型：unshare -rn 新建 user + network namespace，
# 里面只有一块回环网卡 lo，没有任何对外网卡和路由 → 这个进程树访问不了外网；本机其他进程的网络完全不受影响。
# 进程树退出，命名空间自动销毁，不需要任何“恢复”操作，也不改全局网卡 / iptables / 路由。
# 用法：bash tools/offline_run.sh <日志目录> <python 脚本> [参数...]
#   例：bash tools/offline_run.sh logs/run1 tools/gen_examples.py
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd); LOG=$1; shift; mkdir -p "$LOG"; LOG=$(cd "$LOG" && pwd)
OLLAMA=${OLLAMA_BIN:-ollama}; PY=${PY:-python3}   # OLLAMA_BIN=ollama 可执行文件路径（默认用 PATH 里的 ollama）
export OLLAMA LOG PY HERE
exec unshare --user --map-root-user --net bash -c '
  set -euo pipefail
  ip link set lo up
  {
    echo "### 网络状态（命名空间内，$(date "+%F %T %Z")）"
    echo "\$ lscpu | grep -E \"Model name|^CPU\\(s\\)\""; lscpu | grep -E "Model name|^CPU\(s\)"
    echo "\$ ls /dev/nvidia*"; ls /dev/nvidia* 2>&1 || true
    echo "\$ ip -br link"; ip -br link
    echo "\$ ip route"; ip route; echo "(没有默认路由)"
    echo "\$ curl -m 5 -sS https://www.baidu.com -o /dev/null"
    curl -m 5 -sS https://www.baidu.com -o /dev/null 2>&1 && echo "!! 外网居然能通" || echo "→ 访问失败：外网不通"
    echo "\$ curl -m 5 -sS https://huggingface.co -o /dev/null"
    curl -m 5 -sS https://huggingface.co -o /dev/null 2>&1 && echo "!! 外网居然能通" || echo "→ 访问失败：外网不通"
  } > "$LOG/netns_status.txt" 2>&1
  grep -q "外网居然能通" "$LOG/netns_status.txt" && { echo "网络没断开，停止"; exit 3; }
  OLLAMA_HOST=127.0.0.1:11434 OLLAMA_MODELS=$HOME/.ollama/models OLLAMA_NOPRUNE=1 "$OLLAMA" serve > "$LOG/ollama_serve.log" 2>&1 &
  SRV=$!; trap "kill $SRV 2>/dev/null || true" EXIT
  for i in $(seq 1 100); do curl -s -m 1 http://127.0.0.1:11434/api/version > /dev/null && break; sleep 0.1; done
  echo "ollama $(curl -s http://127.0.0.1:11434/api/version)" >> "$LOG/netns_status.txt"
  "$PY" "$@"
' bash "$@"
