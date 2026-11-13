# snow-song：用代码写一首歌，再让这首歌下一场雪

一首用代码一个音一个音写出来的钢琴弦乐小曲（A 小调，60 BPM，52.5 秒），和一个把这首歌“翻译”成落雪的粒子程序。
旋律、和弦、编曲都是 `make_d4_v2.py` 里逐音写出来的 MIDI；声音是用 FluidSynth 加上两套**开源采样音色库**渲染出来的（钢琴：Salamander Grand Piano；弦乐、大提琴、Pad：GeneralUser GS）。
画面里的雪不是手动摆的：每个音落下一片雪，低音越响雪越密，最高的几个音响起时雪花闪一下，雪落地后堆成这首歌的形状。

## 文件

| 文件 | 是什么 |
|---|---|
| `make_d4_v2.py` | 作曲 + 编曲 + 写 MIDI + 用 FluidSynth 渲染 + 自写卷积混响 + 母带（B 版谱面） |
| `make_d4_v2_B2.py` | 视频里用的 B2 版：复用 `make_d4_v2.py` 的 B 版编曲，再按人性化规则重新「演奏」（力度拱形、起音随机、和弦错开、句尾弹性速度、踏板），卡点和 22.45–25.30 不动 |
| `D4_配乐v2_B2_-14LUFS.wav` | B2 脚本渲出来的成品（48 kHz / 24-bit 立体声，52.467 秒，-14 LUFS） |
| `D4_配乐v2_B2.mid` | 这首歌的 MIDI（钢琴、弦乐铺底、弦乐齐奏、大提琴、Pad 共 5 轨） |
| `notes_B2.json` | 每个音的时间、音高、频率、力度，以及卡点表（23.00 暴雪和弦、24.80 断音等），雪按它落；`humanization` 里是人性化参数和统计 |
| `snow.py` | 雪：读一条音频（可选再读音符表），逐帧算出落雪，输出 1080×1920 / 30fps 视频 |
| `LICENSES/` | 两套音色库的许可原文 |
| `requirements.txt` | Python 依赖（另需 ffmpeg、fluidsynth） |

**音色库文件（.sf2）不在这个文件夹里**，需要自己下载（见下）。只想看雪的话不用下载：直接用现成的 wav + notes_B2.json 跑 `snow.py`。

## 怎么跑

```bash
pip install -r requirements.txt          # 另需系统里有 ffmpeg；重新渲染音乐还需要 fluidsynth

# 只看雪（不需要音色库）
python snow.py D4_配乐v2_B2_-14LUFS.wav --notes notes_B2.json                    # 按音符表落雪 → snow.mp4
python snow.py D4_配乐v2_B2_-14LUFS.wav --notes notes_B2.json --seconds 5 --w 540 --h 960   # 先试 5 秒小图
python snow.py D4_配乐v2_B2_-14LUFS.wav --notes notes_B2.json --first-version   # 第一版参数：一个和弦就下成暴雪（视频里那次翻车）
python snow.py 你自己的歌.wav                                                  # 任何 wav 都行：没有音符表时，从音频里找起音

# 重新生成音乐（需要先下载两个 .sf2，放进 soundfonts/，或者用环境变量指过去）
SF_PIANO=/你的路径/SalamanderGrandPiano-V3+20200602.sf2 SF_GU=/你的路径/GeneralUser-GS.sf2 python make_d4_v2.py --version B
python make_d4_v2.py --version B --preview 0 15      # 只渲染 0–15 秒，先听一下
SF_PIANO=... SF_GU=... python make_d4_v2_B2.py             # 视频里的 B2 版（人性化演奏）→ D4_配乐v2_B2_-14LUFS.wav、notes_B2.json、D4_配乐v2_B2.mid
```

## 采样音色从哪下载

| 音色库 | 下载 | 许可 |
|---|---|---|
| Salamander Grand Piano V3（SF2 版 V3+20200602，FreePats 打包），作者 Alexander Holm | FreePats 页面：https://freepats.zenvoid.org/Piano/acoustic-grand-piano.html （SFZ 原版：https://github.com/sfzinstruments/SalamanderGrandPiano ） | CC BY 3.0：https://creativecommons.org/licenses/by/3.0/ ，**需要署名** |
| GeneralUser GS v2.0.3，作者 S. Christian Collins | 作者网站：https://www.schristiancollins.com/generaluser （GitHub：https://github.com/mrbumpy409/GeneralUser-GS ） | GeneralUser GS License v2.0，见 `LICENSES/` |

（GeneralUser GS 的作者要求别人不要直接链接他的下载文件，所以这里只放网站和仓库地址。）

## 改旋律，下一场你的雪

打开 `make_d4_v2.py`，找到 `MEL_COMMON` 里一行行的

```python
(9.6, 1.4, "C5", .74, "sparkle_high_note"),
# 起始秒 时值 音名 力度  卡点名
```

改音名、时间、力度，重跑 `make_d4_v2.py`（会同时重写 notes_B.json 和 MIDI；想要人性化版就再跑 `make_d4_v2_B2.py`），再跑 `snow.py`，雪就跟着新的旋律落。和弦在 `chords_for()` 里。

## 声音怎么变成雪（snow.py）

- **每个音**（音符表里的一行，或从音频里找到的一次起音）→ 在夜空中段那条频谱带上、按音高对应的横向位置落下一片近处的雪，力度越大雪片越大。
- **低频音量**（60–300 Hz）→ 每帧从天上飘下来的雪量：`雪量 = gain × 音量`，并且每帧最多 `cap` 片。
- **高音** → 正在飘的几片雪闪一下。默认是起音里有高于 480 Hz 的音就闪；视频里只让 ≥1000 Hz 的几个最高音闪（9.60 秒的 C6 最亮），做法是改 `Analysis.flash_level`（每一帧的闪光亮度 0–1）。
- **落地**：雪落到地上会把那一小段地面垫高，所以雪地慢慢堆成这首歌的形状。
- **歌停了**（连续 0.5 秒几乎没声音）→ 不再有新雪，空中剩下的雪 1.5 秒内淡掉。

两组参数都在 `snow.py` 开头：

```python
NORMAL        = dict(gain=1.1,   cap=2,    speed=1.0, ...)   # 修好后的
FIRST_VERSION = dict(gain=2400,  cap=None, speed=4.4, ...)   # 第一版：系数写大了、没有上限、下得太快
```

用第一版参数跑这首歌，23 秒那个“过满”的和弦一响，不到 2 秒整个画面就被雪埋白了。这不是后期加的白屏，是程序真的算出来的。

## 授权和署名

- 代码（`make_d4_v2.py`、`make_d4_v2_B2.py`、`snow.py`）：MIT，见 `LICENSE`。
- 旋律、编曲、MIDI、音符表：本账号用代码写的自有作品，可以用、改、商用。
- 音频（`D4_配乐v2_B2_-14LUFS.wav`）是用下面两套音色库渲染的：
  - **钢琴音色：Salamander Grand Piano by Alexander Holm（CC BY 3.0，https://creativecommons.org/licenses/by/3.0/ ）**。转发或再用这段音频时请保留这行署名。
  - 弦乐 / 大提琴 / Pad 音色：GeneralUser GS v2.0.3 by S. Christian Collins。许可原文：“You may use GeneralUser GS without restriction for your own music creation, private or commercial.”（不要求署名，这里致谢）
- 请不要把这段音频登记到 Content ID 一类的版权识别系统：音色库是公开的，别人用同一套音色也可能被误判。

## 雪地为什么会堆成歌的形状

`snow.py` 里每个音符生成的雪花落到地面那一帧（按近层雪的平均下落速度算），会在这个音的音高对应的横向位置（80–2200 Hz 按对数铺满画面宽度，左低右高）堆一个小雪包，高度 = `NOTE_DEPOSIT`（默认 8 像素）× 力度。整首歌下完，雪地的起伏就是这首歌每个音高用了多少、弹得多重。设成 0 就关掉。
