# spectrum-city：把一首歌变成一座会跳的 3D 频谱城市

抖音「AI造点真东西」11/16 那期视频的代码。64 栋楼 = 64 段频率，楼高 = 这一帧这一段有多响。
频谱用 numpy **离线**从音频算好写成 JSON，Three.js 再**一帧一帧**读出来驱动楼高（不是实时麦克风，也不按时间截图）。

## 文件

| 文件 | 作用 |
|---|---|
| `spectrum.py` | 从 wav 算 64 段频谱 → JSON（`proc` 正常版、`raw` 翻车版，另有 `step1` / `step2` 两个中间步骤） |
| `city.html` | Three.js 场景：8×8 楼群、霓虹窗带、楼顶灯、地面倒影；自动求楼高比例，保证楼顶不出画 |
| `render_frames.py` | 无头 Chrome 逐帧渲染成 PNG 或 mp4（可以把音频一起合进去） |
| `three.module.js` / `three.core.js` | Three.js r187（MIT，文件头的版权声明保留） |
| `LICENSE` | 本仓库代码：MIT |
| `THIRD_PARTY_LICENSES.md` | 第三方许可 |

包里**不带**音频、音色库采样、模型权重或日志。换歌请用你自己有权使用的音频。

## 用法

```bash
pip install -r requirements.txt && python -m playwright install chromium   # 需要 ffmpeg 才能出 mp4
python spectrum.py my_song.wav spectrum.json            # 30 fps，每帧 64 段
python -m http.server 8000                              # 浏览器打开 http://127.0.0.1:8000/city.html?audio=my_song.wav ，点一下开始播放
python render_frames.py --data spectrum.json --out city.mp4 --audio my_song.wav          # 离线逐帧渲染整首
python render_frames.py --data spectrum.json --mode raw --out crash.mp4 --audio my_song.wav  # 复现「翻车版」
```

`city.html` 参数：`data=`（JSON）、`mode=proc|raw|step1|step2`、`audio=`、`w=` / `h=`（默认 1080×1920 竖屏）、`hs=`（手动指定楼高比例，不给就自动求）。

## 频谱怎么算的（和视频里一致）

- 每帧一个 4096 点 Hann 窗，窗从「这一帧时刻 − 1024 个采样」开始，第 0 帧前补零，所以第 0 帧就包含第一个鼓点。
- **正常版 `proc`**：30 Hz–16 kHz 按对数等分 64 段 → 每段功率转 dB，以全曲 99.5 分位为顶、往下 54 dB 线性映射到 0–1（幅度压缩）→ 上升不平滑、下落每帧乘 0.80（平滑）。
- **翻车版 `raw`**：0–24 kHz 等宽 64 段（每段 375 Hz），直接用线性幅度，不压缩、不平滑；只乘一个常数，让全曲平均高度和 `proc` 一样。
  结果就是视频里那样：鼓、贝斯的能量几乎都落在第一段，管低音的那一栋冲上天，其余的贴着地乱抖。
- `step1` = 只做对数分段（线性幅度）；`step2` = 对数分段 + 幅度压缩（不平滑）。

## 视频里的配乐和音色（署名）

视频里用的歌（配乐 v3）是我们用代码原创作曲、再用免费音色库渲染的（本包不带这首歌和音色库）：

- 配乐：AI造点真东西 原创（和弦进行 I–V–vi–IV）
- 钢琴音色：Salamander Grand Piano by Alexander Holm（CC BY 3.0）https://creativecommons.org/licenses/by/3.0/（SF2 版由 FreePats 整理，https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html）
- 其他乐器和鼓组：GeneralUser GS v2.0.3 by S. Christian Collins（GeneralUser GS License v2.0：可商用，不要求署名）。用到的预设：GM 48 弦乐、GM 49 Slow Strings（配乐 v3 新加，副歌 / 最高潮铺底）、GM 89 Warm Pad、GM 38 Synth Bass 1、GM 81 Saw Lead、GM 95 Sweep Pad、鼓组 bank 128 / preset 16（Power kit）、bank 128 / preset 25（808/909 kit 底鼓）

## 许可

本仓库代码 MIT（见 `LICENSE`）。第三方见 `THIRD_PARTY_LICENSES.md`。
