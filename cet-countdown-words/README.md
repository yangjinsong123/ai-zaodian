# cet-countdown-words · 900 个单词拼成的四六级倒计时壁纸

900 个英文单词（白、金、浅蓝三色，带辉光）拼成一个巨大的“30”，上方写“距离四六级还有”，下方写“天 · 12月12日”。
可以直接拿 `wallpapers/` 里的 PNG 当手机锁屏壁纸，也可以自己改数字、改尺寸重新生成。

> 属于合集仓库 `ai-zaodian` 的 `cet-countdown-words` 文件夹。上一期的打字背单词网页在同一合集的 `cet-typing-words`。

![预览](wallpapers/wallpaper_30_1080x1920.png)

## 直接下载

| 文件 | 尺寸 | 适合 |
|---|---|---|
| `wallpapers/wallpaper_30_1080x1920.png` | 1080×1920 | 16:9 屏幕的手机 |
| `wallpapers/wallpaper_30_1080x2340.png` | 1080×2340 | 全面屏手机（19.5:9） |

静态图片不会自己变天数；想换数字请按下面的方法重新生成。

## 自己生成

需要 Python 3.9+：

```bash
pip install -r requirements.txt
python countdown.py                                   # 生成 wallpapers/ 下两张默认壁纸（数字 30）
python countdown.py --num 30 --size 1170x2532         # 指定尺寸
python countdown.py --num 30 --date "12月12日" --out my_wallpaper.png
python countdown.py --font /path/to/NotoSansCJKsc-Bold.otf   # 找不到中文字体时手动指定
```

参数：

- `--num`：要拼的数字，也就是离考试的天数。
- `--date`：底部的日期文字。
- `--size`：宽x高。不填就输出 1080×1920 和 1080×2340 两张。
- `--font`：中文字体文件。
- `--out`：输出路径。

## 原理（三步）

1. **撒点**：用大号字体把数字画成蒙版，在笔画内部撒 900 个点。撒点时保持最小间距，所以点分布比较均匀、不扎堆。
2. **换成单词**：每个点换成一个单词。离画面左右边越近的点分到越短的单词，所以单词不会超出画面；程序最后会检查单词的外接框。
3. **辉光**：把单词层缩小、模糊、再放大，叠两层，就有了发光效果。缓动函数 `ease_out_cubic` 是视频里单词“飞回去”用的（前快后慢）。

主要代码都在 `countdown.py`：`Layout` 负责撒点和分配单词，`draw_words` 负责画单词和辉光，`wallpaper` 负责出图。

## 素材来源与许可

| 内容 | 来源 | 许可 |
|---|---|---|
| 代码 `countdown.py` | 我们自己写的 | MIT（见 `LICENSE`） |
| 词表 `words.txt`（900 个英文单词） | 我们**自己整理**的四六级常见英文单词，没有照搬任何词书的选词、顺序、释义或版式；拼写用拼写检查工具核对过 | 跟代码一起按 MIT 发布 |
| 壁纸 PNG `wallpapers/` | 用本仓库代码生成 | MIT，可以自由使用、修改、分享 |
| 字体 | Noto Sans CJK（Google / Adobe），**本仓库不附带字体文件**，使用你系统里已装的字体 | SIL Open Font License 1.1，可商用 |
| 依赖 | numpy（BSD-3-Clause）、Pillow（MIT-CMU 许可） | 见各自项目 |

本项目和考试主办方没有任何关系。“四六级”只作文字出现，不使用任何官方标志。

## 许可

MIT License，见 [LICENSE](LICENSE)。
