"""cet-countdown-words：900 个英文单词拼成一个倒计时数字（默认“30”），输出静态壁纸 PNG。

用法：
    python countdown.py                       # 默认：数字 30，输出 wallpapers/ 下两种尺寸
    python countdown.py --num 30 --date "12月12日" --size 1170x2532 --out my.png

依赖：Python 3.9+、numpy、Pillow；字体用 Noto Sans CJK（SIL OFL 1.1），找不到时请用 --font 指定。
"""
import argparse, glob, os, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
COLORS = [(255, 255, 255), (255, 214, 90), (140, 200, 255)]   # 白、金、浅蓝
FONT_CANDIDATES = ["/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", "/System/Library/Fonts/PingFang.ttc",
                   "C:/Windows/Fonts/msyhbd.ttc"]


def find_font(path=None):
    if path: return path
    for p in FONT_CANDIDATES + glob.glob("/usr/share/fonts/**/NotoSansCJK*Bold*", recursive=True):
        if os.path.exists(p): return p
    raise SystemExit("找不到中文字体，请用 --font 指定一个 .ttf/.ttc（推荐 Noto Sans CJK，SIL OFL 1.1）")


def load_words(path=os.path.join(HERE, "words.txt")):
    return [w.strip() for w in open(path, encoding="utf-8") if w.strip()]


def font(path, size):
    return ImageFont.truetype(path, size, index=2 if path.endswith(".ttc") and "Noto" in path else 0)


def ease_out_cubic(t):
    """缓动：前快后慢"""
    t = min(max(t, 0.0), 1.0)
    return 1 - (1 - t) ** 3


class Layout:
    """在数字字形里撒 N 个点，再给每个点分配一个单词，保证每个单词整个落在 [margin, W-margin] 内。"""

    def __init__(self, W, H, num="30", words=None, fontpath=None, word_size=22, margin=48,
                 box=None, seed=1112, min_dist=None, stretch=1.45):
        self.W, self.H, self.fp = W, H, find_font(fontpath)
        self.words = words or load_words()
        N = len(self.words)
        rng = np.random.default_rng(seed)
        # 1) 字形蒙版：把数字放进 box（x0,y0,x1,y1）里并居中，按宽高同时约束字号
        x0, y0, x1, y1 = box or (margin + 70, int(H * 0.2), W - margin - 70, int(H * 0.72))
        size = 1600
        while True:
            f = font(self.fp, size); bb = f.getbbox(num)
            if bb[2] - bb[0] <= x1 - x0 and (bb[3] - bb[1]) * stretch <= y1 - y0: break
            size -= 10
        # 先画在小画布上，再纵向拉伸 stretch 倍（数字更高挑，横向不出画面）
        g = Image.new("L", (bb[2] - bb[0] + 4, bb[3] - bb[1] + 4), 0)
        ImageDraw.Draw(g).text((2 - bb[0], 2 - bb[1]), num, font=f, fill=255)
        g = g.resize((g.width, int(g.height * stretch)), Image.BILINEAR)
        m = Image.new("L", (W, H), 0)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        m.paste(g, (int(cx - g.width / 2), int(cy - g.height / 2)))
        self.mask = m; self.glyph_size = size
        ys, xs = np.nonzero(np.array(m) > 128)
        # 2) 撒点：带最小间距的随机撒点（比纯随机均匀，不会扎堆）
        area = len(xs); r = min_dist or math.sqrt(area / N) * 0.72
        order = rng.permutation(area); pts = []; grid = {}
        cell = r
        def ok(x, y):
            gx, gy = int(x // cell), int(y // cell)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for (px, py) in grid.get((gx + dx, gy + dy), ()):
                        if (px - x) ** 2 + (py - y) ** 2 < r * r: return False
            return True
        for k in order:
            x, y = float(xs[k]), float(ys[k])
            if ok(x, y):
                pts.append((x, y)); grid.setdefault((int(x // cell), int(y // cell)), []).append((x, y))
                if len(pts) == N: break
        if len(pts) < N:   # 间距太大放不下就补随机点
            extra = rng.choice(area, N - len(pts), replace=False); pts += [(float(xs[k]), float(ys[k])) for k in extra]
        P = np.array(pts)
        # 3) 分配单词：离左右边越近的点分到越短的单词，保证不出画面
        fw = font(self.fp, word_size)
        widths = np.array([fw.getlength(w) for w in self.words])
        room = np.minimum(P[:, 0] - margin, W - margin - P[:, 0]) * 2
        pi = np.argsort(room); wi = list(np.argsort(widths))
        assign = np.zeros(N, int)
        for p in pi:                                   # 最紧的点先挑：在放得下的单词里随机挑一个
            fits = [j for j in range(len(wi)) if widths[wi[j]] <= room[p]]
            j = fits[rng.integers(len(fits))] if fits else 0
            assign[p] = wi.pop(j)
        self.pos = P; self.word_idx = assign; self.color = rng.integers(0, 3, N)
        self.word_size = word_size; self.margin = margin
        self._spr = {}

    def place(self, word, xy):
        """把指定单词换到离 xy 最近的点上（用来让 abandon / persist 出现在想要的位置）"""
        i = self.words.index(word); p = int(np.argmin(((self.pos - np.array(xy)) ** 2).sum(1)))
        a = int(np.where(self.word_idx == i)[0][0]); self.word_idx[a], self.word_idx[p] = self.word_idx[p], self.word_idx[a]
        return p

    def sprite(self, i, scale=1.0, color=None):
        size = max(6, int(round(self.word_size * scale)))
        c = self.color[i] if color is None else color
        key = (int(self.word_idx[i]), int(c), size)
        if key not in self._spr:
            f = font(self.fp, size); w = self.words[self.word_idx[i]]; bb = f.getbbox(w)
            im = Image.new("RGBA", (bb[2] - bb[0] + 6, bb[3] - bb[1] + 8), (0, 0, 0, 0))
            ImageDraw.Draw(im).text((3 - bb[0], 3 - bb[1]), w, font=f, fill=COLORS[c] + (240,))
            self._spr[key] = im
        return self._spr[key]

    def bbox_of(self, pos=None, scale=1.0):
        """所有单词贴图的外接框（用来检查是否越界）"""
        pos = self.pos if pos is None else pos; xs0 = []; xs1 = []; ys0 = []; ys1 = []
        for i in range(len(pos)):
            s = self.sprite(i, scale); xs0.append(pos[i, 0] - s.width / 2); xs1.append(pos[i, 0] + s.width / 2)
            ys0.append(pos[i, 1] - s.height / 2); ys1.append(pos[i, 1] + s.height / 2)
        return min(xs0), min(ys0), max(xs1), max(ys1)


def background(W, H):
    y = np.linspace(0, 1, H)[:, None]
    r = 8 + 14 * y; g = 12 + 16 * y; b = 38 + 50 * y
    img = np.dstack([np.repeat(r, W, 1), np.repeat(g, W, 1), np.repeat(b, W, 1)])
    return Image.fromarray(img.clip(0, 255).astype(np.uint8), "RGB")


def draw_words(L, pos, W, H, cam=(None, None, 1.0), alpha=None, glow=True, bg=None, colors=None):
    """把单词画到画面上。cam=(cx,cy,zoom)：以 (cx,cy) 为中心放大 zoom 倍（镜头推近）。"""
    cx, cy, z = cam; cx = W / 2 if cx is None else cx; cy = H / 2 if cy is None else cy
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sp = (pos - np.array([cx, cy])) * z + np.array([W / 2, H / 2])
    for i in range(len(pos)):
        if alpha is not None and alpha[i] <= 0.01: continue
        s = L.sprite(i, z, None if colors is None else colors[i])
        x, y = int(sp[i, 0] - s.width / 2), int(sp[i, 1] - s.height / 2)
        if x > W or y > H or x + s.width < 0 or y + s.height < 0: continue
        if alpha is not None and alpha[i] < 0.99:
            s = s.copy(); s.putalpha(s.getchannel("A").point(lambda v, a=alpha[i]: int(v * a)))
        layer.alpha_composite(s, (x, y)) if x >= 0 and y >= 0 else layer.paste(s, (x, y), s)
    out = (bg or background(W, H)).convert("RGBA")
    if glow:   # 辉光：缩小→模糊→放大，叠两层
        small = layer.resize((W // 4, H // 4), Image.BILINEAR)
        g1 = small.filter(ImageFilter.GaussianBlur(2.2)).resize((W, H), Image.BILINEAR)
        g2 = small.filter(ImageFilter.GaussianBlur(7)).resize((W, H), Image.BILINEAR)
        out.alpha_composite(g2); out.alpha_composite(g1)
    out.alpha_composite(layer)
    return out


def captions(img, fp, num_text_y0, num_text_y1, date="12月12日", n=900, top="距离四六级还有"):
    W, H = img.size; d = ImageDraw.Draw(img); k = W / 1080
    d.text((W / 2, num_text_y0), top, font=font(fp, int(66 * k)), fill=(255, 255, 255), anchor="mm")
    d.text((W / 2, num_text_y1), f"天 · {date}", font=font(fp, int(70 * k)), fill=(255, 214, 90), anchor="mm")
    d.text((W / 2, num_text_y1 + 90 * k), f"{n} 个单词", font=font(fp, int(40 * k)), fill=(200, 210, 255), anchor="mm")
    return img


def wallpaper(W, H, num="30", date="12月12日", fontpath=None, words=None):
    L = Layout(W, H, num, words=words, fontpath=fontpath, word_size=int(22 * W / 1080), margin=int(48 * W / 1080),
               box=(int(118 * W / 1080), int(H * 0.27), W - int(118 * W / 1080), int(H * 0.70)))
    img = draw_words(L, L.pos, W, H)
    b = L.bbox_of()
    captions(img, L.fp, b[1] - 90 * W / 1080, b[3] + 95 * W / 1080, date=date, n=len(L.words))
    assert b[0] >= 0 and b[2] <= W, f"数字越界：{b}"
    return img.convert("RGB"), L, b


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="900 个单词拼成倒计时壁纸")
    ap.add_argument("--num", default="30", help="要拼的数字（距离考试的天数）")
    ap.add_argument("--date", default="12月12日", help="考试日期文字")
    ap.add_argument("--size", default=None, help="宽x高，例如 1170x2532；不填则输出 1080x1920 和 1080x2340 两张")
    ap.add_argument("--font", default=None); ap.add_argument("--out", default=None)
    a = ap.parse_args()
    sizes = [tuple(map(int, a.size.split("x")))] if a.size else [(1080, 1920), (1080, 2340)]
    os.makedirs(os.path.join(HERE, "wallpapers"), exist_ok=True)
    for (W, H) in sizes:
        img, L, b = wallpaper(W, H, a.num, a.date, a.font)
        out = a.out or os.path.join(HERE, "wallpapers", f"wallpaper_{a.num}_{W}x{H}.png")
        img.save(out); print(out, "单词外接框", [round(v) for v in b])
