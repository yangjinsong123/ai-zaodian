# example-meteor-shower

30 个四六级单词，让一个**本地小模型**在**没有显卡、模型进程断网**的云电脑上逐个造句，再把句子做成流星雨（抖音「AI造点真东西」D6）。流星雨动画的代码在 `render/`。

- 模型：Qwen2.5-1.5B-Instruct（Q4_K_M GGUF，Apache-2.0），用 Ollama（MIT）在 CPU 上跑。**包里没有模型权重**，需要自己用 Ollama 拉取。
- `data/words.json`：30 个词和我们自己写的中文意思。
- `data/examples_20261113.json`：视频里用的 30 条例句。`sentence` 是模型**原始输出**，一个字没改（包括模型自己在 essential、generate 两句外面加的英文引号）；`all_outputs` 里是这个词的全部候选、种子、来自哪个日志、没采用的原因。挑选标准见 `tools/make_examples_1113.py` 顶部（由 AI 代理按规则挑，没有经过真人逐句核对）。
  - json 里写的日志路径是 `logs/…`（原始日志的目录名）。原始日志不在包里，同样结构的脱敏副本在 `logs_clean/…`。
- `logs_clean/*_20261113/`：11/13 原始日志的脱敏副本（本机路径、内网 IP、主机名、用户名换成了占位符），其余内容不变：`netns_status.txt`（断网证据）、`raw_*.jsonl`（每个字到达的时间）、`host_net.txt`（同一时间本机其他程序的网络正常）、`ollama_serve.log`。
  - 注意：`netns_status.txt` 里 `$ ip route` 下面那行「(没有默认路由)」是 `offline_run.sh` 自己 echo 的说明文字，不是命令输出；真正的证据是 `ip -br link` 只有回环网卡 `lo`，以及 `curl` 访问外网失败。

## 目录
| 路径 | 内容 |
|---|---|
| `render/meteor_shower.py` | 流星雨渲染：examples json → 短视频（mp4）或 PNG 帧 |
| `tools/offline_run.sh` | 只给模型进程断网，在里面起 Ollama 并跑脚本 |
| `tools/ask.py` / `tools/ask_batch.py` | 冷启动测速 + 逐词造句 + 现场再造一句 / 只逐词造句 |
| `tools/host_net_check.sh` | 测前、测中、测后检查本机其他程序的网络 |
| `tools/make_examples_1113.py` | 从日志汇总 `data/examples_20261113.json`（有 `logs/` 用 `logs/`，否则用 `logs_clean/`） |
| `tools/sanitize_logs.py` | 生成脱敏副本 `logs_clean/` 的脚本（需要原始 `logs/`，包里没有，留作说明） |

## 流星雨动画（render/）
依赖：Python ≥ 3.9，`pip install -r render/requirements.txt`（numpy、Pillow）；导出 mp4 还需要系统里装好 `ffmpeg`。
```
python render/meteor_shower.py                                   # → meteor_shower.mp4，8 秒，1080x1920，30 fps
python render/meteor_shower.py --seconds 4 --frames out_frames   # 只导出 PNG 帧（不需要 ffmpeg）
python render/meteor_shower.py --size 720x1280 --fps 24 --out small.mp4
python render/meteor_shower.py --examples 你的.json --font 某字体.ttf --font-bold 某粗体.ttf
```
- examples json 只需要 `{"examples": [{"word": "...", "sentence": "..."}, ...]}`（或直接一个列表）。
- 每条例句一颗流星，目标词（含屈折形式，如 persisted）高亮；所有流星同速、平行轨道，不会互相重叠；飞到屏幕边上渐隐，飞出屏幕才移除。
- **显示时去掉了外层引号**：句子整句外面多包的一层英文双引号只在画面上去掉，json 不改。
- 字体：默认按名字找 Noto Sans / DejaVu Sans，找不到就用 Pillow 自带字体（很小）。建议用 `--font` 指定。
- 视频里的镜头、配音、字幕、角标是成片专用的，不在这里。

## 只给模型进程断网
```
bash tools/offline_run.sh logs/run1 tools/ask.py logs/run1 data/words.json
```
`offline_run.sh` 用 `unshare --user --map-root-user --net` 给这一个进程树开一个新的网络命名空间：里面只有回环网卡 `lo`、没有路由，`curl` 外网会失败（结果写进 `netns_status.txt`）。Ollama 在命名空间里监听 127.0.0.1（`OLLAMA_BIN` 指定 ollama 可执行文件，默认用 PATH 里的）。进程退出，命名空间自动消失；**不改电脑本身的网卡、路由和防火墙**，其他程序照常联网（`tools/host_net_check.sh` 在测前、测中、测后各查一次）。

## 11/13 实测（无显卡，8 核 Intel Xeon）
- 冷启动：请求发出到第一个字 3.705 s（Ollama 自报 load_duration 3.578 s）。
- 模型已在内存里：eval_count 15 / eval_duration 0.323 s = 46.45 token/s（Ollama 自报），整句 0.356 s。

## 许可
本仓库代码和数据：MIT（见 `LICENSE`）。第三方依赖的许可见 `THIRD_PARTY_LICENSES.md`。
