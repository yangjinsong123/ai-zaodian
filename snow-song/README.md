# snow-song：用代码写一首歌，再让这首歌下一场雪

一首用 numpy 一个音一个音合成的钢琴小曲（A 小调，60 BPM，52 秒），和一个把这首歌“翻译”成落雪的粒子程序。
画面里的雪不是手动摆的：每个音落下一片雪，低音越响雪越密，高音响起时雪花闪一下，雪落地后堆成这首歌的形状。

## 文件

| 文件 | 是什么 |
|---|---|
| `make_d4_song.py` | 合成这首歌（numpy / scipy 加法合成 + 自写混响，没有采样、没有现成曲子、没有音色库）。**这份代码是我们配乐部门写的**，原样放进来，只把文件开头说明里两处内部路径改成了通用写法 |
| `代码歌_-13LUFS.wav` | 上面脚本渲出来的成品（48 kHz 立体声，52 秒，-13 LUFS） |
| `notes.json` | 这首歌每个音的时间、音高、频率、力度（脚本同时生成），雪可以按它落 |
| `snow.py` | 雪：读一条音频（可选再读 notes.json），逐帧算出落雪，输出 1080×1920 / 30fps 视频 |
| `requirements.txt` | Python 依赖 |

## 怎么跑

```bash
pip install -r requirements.txt          # 另需系统里有 ffmpeg

python make_d4_song.py                    # 重新合成这首歌：生成 D4_代码歌_demo.wav（-16）、D4_代码歌_-14LUFS.wav、D4_代码歌_-13LUFS.wav、一个 mp3，并覆盖 notes.json
python snow.py 代码歌_-13LUFS.wav --notes notes.json            # 按音符表落雪 → snow.mp4
python snow.py 代码歌_-13LUFS.wav --notes notes.json --seconds 5 --w 540 --h 960   # 先试 5 秒小图
python snow.py 你自己的歌.wav                                     # 任何 wav 都行：没有 notes.json 时，从音频里找每个音的起音
python snow.py 代码歌_-13LUFS.wav --notes notes.json --first-version   # 第一版参数：一个和弦就下成暴雪（视频里那次翻车）
```

## 改旋律，下一场你的雪

打开 `make_d4_song.py`，找到 `build_score()` 里一行行的

```python
N(9.60, 1.0, "C5", 0.62, "melody", "C", "雪花闪光高音")
#  起始秒 时值  音名  力度
```

改音名、时间、力度，重跑 `make_d4_song.py`，再跑 `snow.py`，雪就跟着新的旋律落。

## 声音怎么变成雪（snow.py）

- **每个音**（notes.json 里的一行，或从音频里找到的一次起音）→ 在夜空中段那条频谱带上、按音高对应的横向位置落下一片近处的雪，力度越大雪片越大。音符所在的那一帧就落，第 0 秒的第一个音就是第 0 帧的第一片雪。
- **低频音量**（60–300 Hz）→ 每帧从天上飘下来的雪量：`雪量 = gain × 音量`，并且每帧最多 `cap` 片。
- **高音**（起音里有高于 480 Hz 的音，这首歌里是 C5、E5）→ 正在飘的几片雪闪一下。
- **落地**：雪落到地上会把那一小段地面垫高，所以雪地慢慢堆成这首歌的形状。
- **歌停了**（连续 0.5 秒几乎没声音）→ 不再有新雪，空中剩下的雪 1.5 秒内淡掉。
- 雪分远、中、近三层，大小、速度、亮度都不一样。

两组参数都在 `snow.py` 开头：

```python
NORMAL        = dict(gain=1.1,   cap=2,    speed=1.0, ...)   # 修好后的
FIRST_VERSION = dict(gain=2400,  cap=None, speed=4.4, ...)   # 第一版：系数写大了、没有上限、下得太快
```

用第一版参数跑这首歌，23 秒那个“过满”的和弦一响，不到 2 秒整个画面就被雪埋白了。这不是后期加的白屏，是程序真的算出来的。

## 授权

- 代码（`make_d4_song.py`、`snow.py`）：MIT，见 `LICENSE`。
- 歌（`代码歌_-13LUFS.wav`、`notes.json`）：本账号用上面的代码合成的自有作品，可以随便用、改、商用，不强制署名。
