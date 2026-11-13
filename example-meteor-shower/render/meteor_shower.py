#!/usr/bin/env python3
"""例句流星雨：读 examples json，把每条例句做成一颗流星（目标词高亮），渲染一段短视频或 PNG 帧。

用法（在仓库根目录）：
  python render/meteor_shower.py                                   # data/examples_20261113.json → meteor_shower.mp4（8 秒）
  python render/meteor_shower.py --seconds 4 --frames out_frames   # 只导出 PNG 帧，不需要 ffmpeg
  python render/meteor_shower.py --size 720x1280 --fps 24 --out small.mp4

依赖：Python ≥ 3.9、numpy、Pillow；导出 mp4 时还需要系统里有 ffmpeg（没有就加 --frames 导出 PNG）。
字体：默认按名字找系统里的 Noto Sans / DejaVu Sans，也可以用 --font / --font-bold 指定 .ttf/.otf/.ttc。

显示规则：json 里的 sentence 是模型原始输出，本脚本不改 json；只在画面上把「整句外面多包的一层英文双引号」去掉（disp()）。"""
import argparse, json, math, os, re, shutil, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

WARM, INK = (255, 200, 87), (232, 238, 255)
clamp = lambda x, a=0.0, b=1.0: max(a, min(b, x))

def load_font(path, size, names):
    for p in ([path] if path else []) + names:
        try: return ImageFont.truetype(p, size)
        except OSError: pass
    try: return ImageFont.load_default(size)          # Pillow ≥ 10.1
    except TypeError: return ImageFont.load_default()

def disp(sent):
    """显示层去掉整句外层的英文双引号（如 "Water is essential …"）；句子中间的引号不动"""
    return sent[1:-1] if len(sent) > 2 and sent[0] == sent[-1] == '"' and sent.count('"') == 2 else sent

def stem(w): return w[:-1] if w.endswith("e") else w
def word_span(sent, w):
    """找目标词（或它的屈折形式，如 persisted / generating）在句子里的位置，用来高亮"""
    for m in re.finditer(r"[A-Za-z']+", sent):
        tok = m.group(0).lower()
        if tok.startswith(stem(w.lower())) and not tok.endswith("ly") and not (w == "persist" and tok.startswith("persisten")): return m.span()   # persistent 是派生词，不算
    return None

def sentence_img(sent, w, f, fb, maxw):
    words = sent.split(" "); lines, cur = [], ""
    for x in words:
        if f.getlength((cur + " " + x).strip()) > maxw and cur: lines.append(cur); cur = x
        else: cur = (cur + " " + x).strip()
    lines.append(cur); span = word_span(sent, w); size = f.size
    hot = lambda a, b: span and a < span[1] and b > span[0]
    pos, starts, widths = 0, [], []
    for l in lines:
        s0 = sent.index(l, pos); pos = s0 + len(l); starts.append(s0)
        widths.append(sum((fb if hot(s0 + m.start(), s0 + m.end()) else f).getlength(m.group(0)) for m in re.finditer(r"\S+|\s+", l)))
    lh = int(size * 1.32); im = Image.new("RGBA", (int(max(widths)) + 48, lh * len(lines) + 24), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for k, l in enumerate(lines):
        x, y, s0 = 20, 10 + k * lh, starts[k]
        for m in re.finditer(r"\S+|\s+", l):
            h = hot(s0 + m.start(), s0 + m.end()); ff = fb if h else f
            d.text((x, y), m.group(0), font=ff, fill=WARM if h else INK, stroke_width=2, stroke_fill=(90, 50, 0) if h else (5, 8, 25)); x += ff.getlength(m.group(0))
    g = im.filter(ImageFilter.GaussianBlur(6)); out = Image.new("RGBA", im.size, (0, 0, 0, 0)); out.alpha_composite(g); out.alpha_composite(im); return out

class Shower:
    def __init__(self, examples, W=1080, H=1920, font=None, font_bold=None, seed=1115, spawn=1.0):
        self.W, self.H, self.k = W, H, W / 1080                      # 所有尺寸按 1080 宽等比缩放
        size = max(10, int(34 * self.k))
        f = load_font(font, size, ["NotoSans-Regular.ttf", "NotoSansCJK-Regular.ttc", "DejaVuSans.ttf", "Arial.ttf"])
        fb = load_font(font_bold, size, ["NotoSans-Bold.ttf", "NotoSansCJK-Bold.ttc", "DejaVuSans-Bold.ttf", "Arial Bold.ttf"])
        self.sent = [sentence_img(disp(e["sentence"]), e["word"], f, fb, 640 * self.k) for e in examples]
        self.vx, self.vy = -250.0 * self.k, 110.0 * self.k; ang = math.atan2(self.vy, self.vx); self.ux, self.uy = math.cos(ang), math.sin(ang)
        self.lanes = [v * self.k for v in (-300, -100, 100, 300, 500, 700, 900)]; self.spawn = spawn
        yy = np.linspace(0, 1, H)[:, None]
        self.sky = Image.fromarray(np.dstack([np.repeat(c, W, 1) for c in (6 + 10 * yy, 10 + 18 * yy, 30 + 34 * yy)]).astype(np.uint8), "RGB").convert("RGBA")
        rng = np.random.default_rng(seed)
        self.stars = [(rng.uniform(0, W), rng.uniform(0, H * 0.86), rng.uniform(0.8, 2.4) * self.k, rng.uniform(0, 6.28), rng.uniform(0.6, 2.2)) for _ in range(230)]
        ex = np.minimum(np.clip(np.arange(W) / (150 * self.k), 0, 1), np.clip((W - 1 - np.arange(W)) / (150 * self.k), 0, 1))
        ey = np.minimum(np.clip(np.arange(H) / (60 * self.k), 0, 1), np.clip((H - 1 - np.arange(H)) / (60 * self.k), 0, 1))
        self.edge = (np.minimum(ex[None, :], ey[:, None]) ** 1.5).astype(np.float32)   # 屏幕边上渐隐，流星句不会被一条竖线切断

    def meteors(self, t):
        """t 时刻画面里的流星：(句子序号, 头部 x, y, 已飞时间)。同速、平行轨道，互不重叠；飞出屏幕才移除"""
        n = len(self.sent); ts = t + 8.0; k1 = int(ts / self.spawn); out = []
        for k in range(max(0, k1 - 12), k1 + 1):
            age = ts - k * self.spawn; x = self.W + 60 * self.k + self.vx * age; y = self.lanes[(k * 3) % 7] + self.vy * age
            if x + 18 * self.k + self.sent[k % n].width < 0 or y - 10 * self.k > self.H: continue
            out.append((k % n, x, y, age))
        return out

    def frame(self, t):
        W, H, k = self.W, self.H, self.k
        im = self.sky.copy(); d = ImageDraw.Draw(im)
        for x, y, r, ph, sp in self.stars:
            a = 0.45 + 0.55 * (0.5 + 0.5 * math.sin(t * sp + ph)); c = int(150 + 100 * a); d.ellipse((x - r, y - r, x + r, y + r), fill=(c, c, min(255, c + 20)))
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        for idx, x, y, age in self.meteors(t):
            a = clamp((y - 110 * k) / (120 * k)) * clamp((H * 0.79 - y) / (160 * k)) * clamp(age / 0.4)
            if a <= 0.01: continue
            tail = 260 * k
            for j in range(14):
                f0, f1 = j / 14, (j + 1) / 14
                d.line((x - self.ux * tail * f0, y - self.uy * tail * f0, x - self.ux * tail * f1, y - self.uy * tail * f1), fill=(200, 220, 255, int(170 * a * (1 - f0) ** 1.6)), width=max(1, int(7 * k * (1 - f0))))
            for r, al in ((16, 50), (9, 120), (5, 255)): r *= k; d.ellipse((x - r, y - r, x + r, y + r), fill=(255, 246, 220, int(al * a)))
            s = self.sent[idx]
            if a < 0.999: s = s.copy(); s.putalpha(s.getchannel("A").point(lambda v: int(v * a)))
            px, py = int(x + 18 * k), int(y - 10 * k)
            if px < W and py < H and px + s.width > 0 and py + s.height > 0:
                ov.alpha_composite(s, (max(0, px), max(0, py)), (max(0, -px), max(0, -py)))
        ov.putalpha(Image.fromarray((np.asarray(ov.getchannel("A"), np.float32) * self.edge).astype(np.uint8), "L"))
        im.alpha_composite(ov); return im.convert("RGB")

def main(argv=None):
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="examples json → 例句流星雨短视频 / PNG 帧")
    ap.add_argument("--examples", default=os.path.join(root, "data", "examples_20261113.json"))
    ap.add_argument("--out", default="meteor_shower.mp4", help="mp4 输出路径（需要 ffmpeg）")
    ap.add_argument("--frames", help="改为把 PNG 帧写进这个目录")
    ap.add_argument("--seconds", type=float, default=8.0); ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--size", default="1080x1920", help="宽x高，默认竖屏 1080x1920")
    ap.add_argument("--font"); ap.add_argument("--font-bold")
    a = ap.parse_args(argv)
    ex = json.load(open(a.examples, encoding="utf-8")); ex = ex["examples"] if isinstance(ex, dict) else ex
    W, H = map(int, a.size.lower().split("x")); sh = Shower(ex, W, H, a.font, a.font_bold); n = int(round(a.seconds * a.fps))
    if a.frames:
        os.makedirs(a.frames, exist_ok=True)
        for i in range(n): sh.frame(i / a.fps).save(os.path.join(a.frames, f"frame_{i:05d}.png"))
        print(f"wrote {n} frames → {a.frames}"); return
    if not shutil.which("ffmpeg"): sys.exit("没找到 ffmpeg：装好 ffmpeg，或者加 --frames DIR 导出 PNG 帧")
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(a.fps), "-i", "-",
                          "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", a.out], stdin=subprocess.PIPE)
    for i in range(n): p.stdin.write(sh.frame(i / a.fps).tobytes())
    p.stdin.close(); sys.exit(p.wait()) if p.wait() else print(f"wrote {a.out}  {n} frames, {W}x{H}@{a.fps}")

if __name__ == "__main__": main()
