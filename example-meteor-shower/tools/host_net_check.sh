#!/usr/bin/env bash
# 在宿主（命名空间外）检查本机全局网络：网卡、默认路由、能否访问外网。测之前、测的过程中、测完各跑一次。
echo "### 宿主网络检查 $(date '+%F %T %Z') — $1"
ip -br addr | grep -v "^lo"; ip route | grep default
for u in https://www.baidu.com https://huggingface.co; do echo "$u → HTTP $(curl -sS -m 8 -o /dev/null -w '%{http_code}' $u 2>&1)"; done
