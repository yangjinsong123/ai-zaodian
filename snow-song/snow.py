"""snow-song / snow.py：用一条音频驱动一场雪。

    python snow.py song.wav                 # 输出 snow.mp4（1080×1920，30fps，带原音频）
    python snow.py song.wav --w 720 --h 1280 --out small.mp4
    python snow.py D4_配乐v2_B2_-14LUFS.wav --notes notes_B2.json   # 按音符表（每个音的时间、力度）落雪
    python snow.py D4_配乐v2_B2_-14LUFS.wav --notes notes_B2.json --first-version   # 第一版参数：一个和弦就下成暴雪

对应关系（全部从音频里算，不读乐谱，所以换成任何 WAV 都能下雪）：
  - 每个音的起音（频谱突然变强）→ 从夜空中段的“频谱带”上，按音高的位置落下一片雪；
  - 低频（60–300 Hz）的音量 → 天上飘下来的雪量（低音落下，雪就密一点）；
  - 高频（1–4 kHz）的起音 → 正在飘的几片雪闪一下；
  - 雪落到地上会堆起来，音高对应横向位置，所以雪地会慢慢堆成这首歌的形状。
"""
import argparse, math, subprocess, json
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

FPS = 30
QUIET = 10 ** (-60 / 20)   # 帧 RMS 低于 -60 dBFS 算“没声音”
HIGH_HZ = 480          # 起音里出现高于这个频率的音，就算“高音响起”
NOTE_DEPOSIT = 8.0     # 每个音落地时，在它音高对应的横向位置把雪地垫高多少像素（× 力度）；雪地就慢慢堆成这首歌的音高分布
NORMAL = dict(gain=1.1, cap=2, speed=1.0, note_flakes=1, size=1.0, deposit=1.0, note_deposit=NOTE_DEPOSIT)       # 修好后的参数
FIRST_VERSION = dict(gain=2400.0, cap=None, speed=4.4, note_flakes=40, size=3.0, deposit=1.5)   # 第一版：系数太大、没有上限、下得太快


def load_notes(path):
    """读 notes.json（配乐部门格式：notes[].start / freq / velocity），返回 [(秒, Hz, 力度)]"""
    d = json.load(open(path, encoding="utf-8"))
    return [(n["start"], n["freq"], n["velocity"]) for n in d["notes"]]


def load_audio(path, sr=44100):
    raw = subprocess.check_output(["ffmpeg", "-v", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(sr), "-"])
    return np.frombuffer(raw, np.float32).copy(), sr


class Analysis:
    """逐帧分析：每帧取从该帧时刻开始的 4096 点窗口"""
    def __init__(self, x, sr, fps=FPS, nfft=2048, notes=None):
        self.sr = sr; hop = sr / fps; n = int(len(x) / hop) + 1
        win = np.hanning(nfft); freqs = np.fft.rfftfreq(nfft, 1 / sr); self.freqs = freqs
        S = np.zeros((n, len(freqs)), np.float32)
        for i in range(n):
            s = int(i * hop); seg = x[s:s + nfft]
            if len(seg) < nfft: seg = np.pad(seg, (0, nfft - len(seg)))
            S[i] = np.abs(np.fft.rfft(seg * win))
        self.S = S; self.n = n
        self.rms = np.array([np.sqrt(np.mean(x[int(i * hop):int(i * hop + hop)] ** 2)) if int(i * hop) < len(x) else 0.0 for i in range(n)])
        band = lambda lo, hi: S[:, (freqs >= lo) & (freqs < hi)].sum(1)
        low, high = band(60, 300), band(1000, 4000)
        ref = lambda v: np.percentile(v[v > 1e-6], 95) if (v > 1e-6).any() else 1.0
        self.low = low / ref(low); self.high = high / ref(high)
        # 起音：正的频谱差之和（spectral flux）
        D = np.maximum(0, np.diff(np.vstack([np.zeros((1, S.shape[1])), S]), axis=0)); self.D = D
        flux = D[:, (freqs > 60) & (freqs < 5000)].sum(1)
        thr = np.percentile(flux, 85) * 3 + 1e-6
        med = np.array([np.median(flux[max(0, i - 8):i]) if i else 0.0 for i in range(n)])   # 只看之前的帧
        self.onset = self._pick((flux > thr) & (flux > 2 * med), 3)
        # 每一帧的“音符事件”(频率 Hz, 力度 0-1)：有音符表（notes.json）就按表里每个音的时间和力度；没有就从音频起音里找
        self.events = [[] for _ in range(n)]
        if notes is not None:
            for t, hz, vel in notes:
                i = int(round(t * fps))
                if 0 <= i < n: self.events[i].append((hz, vel))
        else:
            for i in np.where(self.onset)[0]: self.events[i] = [(hz, 0.5) for hz in self.onset_pitches(i)]
        self.high_onset = np.array([any(hz >= HIGH_HZ for hz, _ in e) for e in self.events])
        self.flash_level = self.high_onset.astype(np.float32)   # 每次闪光的亮度（0–1）；调用方可以改成只让最高的几个音闪、各自不同亮度
        # 64 段对数频带（画频谱带用）
        centers = np.geomspace(80, 2200, 64)
        self.bands = np.stack([np.interp(centers, freqs, np.convolve(row, np.ones(3) / 3, "same")) for row in S])
        self.bands /= np.percentile(self.bands, 99) + 1e-9
        self.avg_shape = self.bands.mean(0)

    @staticmethod
    def _pick(mask, gap):
        out = np.zeros_like(mask); last = -99
        for i in np.where(mask)[0]:
            if i - last >= gap: out[i] = True; last = i
        return out

    def onset_pitches(self, i, k=3):
        """起音帧里新增能量最大的几个频率（Hz）"""
        d = self.D[i].copy(); d[(self.freqs < 60) | (self.freqs > 3000)] = 0; out = []
        for _ in range(k):
            j = int(d.argmax())
            if d[j] <= 0 or (out and d[j] < 0.25 * self.D[i].max()): break
            out.append(self.freqs[j]); d[max(0, j - 6):j + 7] = 0
        return out


class Snow:
    def __init__(self, W=1080, H=1920, params=NORMAL, seed=13, avg_shape=None):
        self.W, self.H, self.p = W, H, dict(params); k = W / 1080; self.k = k
        self.rng = np.random.default_rng(seed)
        self.band_y = int(H * 0.36); self.ground_y = int(H * 0.79)
        # 雪片：x, y, 半径, 下落速度, 层(0远 1中 2近), 相位, 闪光剩余, 亮度(歌停了就慢慢变淡)
        self.f = np.zeros((0, 8), np.float32); self.quiet = 0
        # 画面下方预先铺好一层薄雪（“已经下了一阵”）：形状取这首歌的平均频谱
        x = np.arange(W); base = 46 * k
        shape = np.interp(x, np.linspace(60 * k, W - 60 * k, 64), avg_shape if avg_shape is not None else np.ones(64))
        shape = np.convolve(shape, np.ones(int(90 * k)) / int(90 * k), "same")
        self.ground = base + 30 * k * shape / (shape.max() + 1e-9) + 6 * k * np.sin(x / (97 * k))
        self.bg = self._background()

    def _background(self):
        W, H = self.W, self.H; y = np.linspace(0, 1, H)[:, None]
        r = 8 + 10 * y; g = 13 + 14 * y; b = 32 + 26 * y      # #0A1024 左右，越往下越亮一点
        return Image.fromarray(np.dstack([np.repeat(c, W, 1) for c in (r, g, b)]).astype(np.uint8), "RGB")

    def x_of(self, hz):
        return float(np.interp(math.log(max(hz, 80)), [math.log(80), math.log(2200)], [60 * self.k, self.W - 60 * self.k]))

    def _spawn(self, n, xs=None, y=None, layers=None, flash=0, scale=1.0):
        if n <= 0: return
        r = self.rng; k = self.k * self.p["size"] * scale
        L = r.choice(3, n, p=[0.45, 0.35, 0.20]) if layers is None else np.full(n, layers)
        rad = np.choose(L, [r.uniform(0.9, 1.5, n), r.uniform(1.6, 2.5, n), r.uniform(2.8, 4.0, n)]) * k
        spd = np.choose(L, [r.uniform(1.4, 2.0, n), r.uniform(2.4, 3.2, n), r.uniform(3.6, 4.5, n)]) * self.k * self.p["speed"]
        xs = r.uniform(0, self.W, n) if xs is None else np.asarray(xs, float) + r.normal(0, 6 * self.k, n)
        ys = r.uniform(-30, -5, n) if y is None else np.full(n, float(y)) + r.normal(0, 4, n)
        new = np.stack([xs, ys, rad, spd, L, r.uniform(0, 6.28, n), np.full(n, flash), np.ones(n)], 1).astype(np.float32)
        self.f = np.vstack([self.f, new])

    def step(self, A, i):
        """推进一帧：按第 i 帧的音频特征生成、移动、落地"""
        p = self.p
        if i < A.n:
            for hz, vel in A.events[i]:                      # 每个音：从频谱带上、按音高的位置落雪；力度越大雪片越大
                m = max(1, int(round(p["note_flakes"] * vel / 0.45)))
                self._spawn(m, xs=[self.x_of(hz)] * m, y=self.band_y, layers=2, flash=6, scale=0.7 + vel)
                if p.get("note_deposit"):                    # 这个音的雪落到地面那一帧（按近层雪的平均下落速度算），在同一横向位置堆一个小雪包
                    x = self.x_of(hz); fall = (self.ground_y - self.ground[int(x)] - self.band_y) / (4.05 * self.k * p["speed"])
                    self.pend = getattr(self, "pend", []) + [(i + max(1, int(round(fall))), x, p["note_deposit"] * self.k * vel)]
            want = p["gain"] * A.low[i]                      # 低音越响，天上飘下来的雪越多
            if p["cap"] is not None: want = min(want, p["cap"])
            self.acc = getattr(self, "acc", 0.0) + want
            m = int(self.acc); self.acc -= m; self._spawn(m)
            lv = float(getattr(A, "flash_level", A.high_onset)[i])
            if lv > 0 and len(self.f):                       # 高音：几片雪闪一下（亮度和片数按 flash_level）
                k = max(1, int(round(12 * lv)))
                idx = self.rng.choice(len(self.f), min(k, len(self.f)), replace=False); self.f[idx, 6] = 20 * lv
        pend = getattr(self, "pend", [])
        if pend:
            due = [q for q in pend if q[0] <= i]; self.pend = [q for q in pend if q[0] > i]
            if due:
                xx = np.arange(self.W)
                for _, x, h in due: self.ground += h * np.exp(-0.5 * ((xx - x) / (22 * self.k)) ** 2)
        # 歌停了（连续 0.5 秒几乎无声）：不再有新雪，空中剩下的雪 1.5 秒内淡掉——“最后一个音停下，雪也停了”
        self.quiet = self.quiet + 1 if (i >= A.n or A.rms[i] < QUIET) else 0
        f = self.f
        if not len(f): return
        if self.quiet >= FPS // 2: f[:, 7] -= 1 / (1.5 * FPS)
        f[:, 1] += f[:, 3]; f[:, 0] += np.sin(f[:, 1] / (60 * self.k) + f[:, 5]) * 0.35 * self.k * (1 + f[:, 4] * 0.3)
        f[:, 6] = np.maximum(0, f[:, 6] - 1)
        xi = np.clip(f[:, 0].astype(int), 0, self.W - 1)
        landed = (f[:, 1] >= self.ground_y - self.ground[xi]) & (f[:, 4] >= 1)    # 远层的雪只是背景，不落地
        gone = (f[:, 1] > self.H + 10) | landed | (f[:, 7] <= 0)
        for x, r in zip(xi[landed], f[landed, 2]):
            w = int(r * 5) + 3; lo, hi = max(0, x - w), min(self.W, x + w)
            self.ground[lo:hi] += p["deposit"] * r * 0.55 * np.cos(np.linspace(-1.4, 1.4, hi - lo)) ** 2
        self.f = f[~gone]

    def layers(self, A, i, band=True):
        """返回三层：背景（夜空+频谱带+远、中层雪）、近层雪、雪地（RGBA）"""
        W, H, k = self.W, self.H, self.k
        back = self.bg.copy().convert("RGBA"); d = ImageDraw.Draw(back, "RGBA")
        ba = getattr(self, "band_alpha", 1.0)                # 整条频谱带的淡出系数（1 = 原样；视频里最后一个音之后淡掉）
        if band and i < A.n and ba > 0.004:                  # 频谱带：很淡的灰蓝
            bw = (W - 120 * k) / 64; v = A.bands[i]
            ov = back if ba >= 1 else Image.new("RGBA", (W, H), (0, 0, 0, 0)); do = d if ba >= 1 else ImageDraw.Draw(ov)
            for j in range(64):
                h = 4 * k + min(1.0, v[j]) * 120 * k; a = int(36 + 120 * min(1.0, v[j]))
                if ba < 1: a = int(255 * ba)                 # 注意：在 RGBA 图上直接画不会按 alpha 混合，所以淡出时画在透明层上再叠
                x0 = 60 * k + j * bw; do.rectangle([x0, self.band_y - h / 2, x0 + bw - 3 * k, self.band_y + h / 2], fill=(96, 120, 160, a))
            if ba < 1: back.alpha_composite(ov)
        sky = Image.new("RGBA", (W, H), (0, 0, 0, 0)); near = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ds, dn = ImageDraw.Draw(sky), ImageDraw.Draw(near)
        for x, y, r, _, L, _, fl, life in self.f:
            a = (110, 170, 235)[int(L)]
            c = (min(255, 228 + int(fl * 2)), min(255, 236 + int(fl)), 255, int(min(255, a + int(fl * 8)) * max(0.0, life)))
            if fl > 0: r = r * (1 + fl / 20 * 1.6)
            (dn if L == 2 else ds).ellipse([x - r, y - r, x + r, y + r], fill=c)
        back.alpha_composite(sky.filter(ImageFilter.GaussianBlur(0.6 * k)))
        glow = sky.resize((W // 4, H // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(2)).resize((W, H), Image.BILINEAR)
        back.alpha_composite(glow)
        near = Image.alpha_composite(near.filter(ImageFilter.GaussianBlur(1.1 * k)),
                                     near.resize((W // 4, H // 4), Image.BILINEAR).filter(ImageFilter.GaussianBlur(2.5)).resize((W, H), Image.BILINEAR))
        # 雪地：表面偏冷白，往下渐暗（底部要能压字幕）
        top = (self.ground_y - self.ground).clip(0, H)
        yy = np.arange(H)[:, None]; inside = yy >= top[None, :]
        depth = np.clip((yy - np.maximum(top[None, :], self.ground_y - 50 * k)) / (H - self.ground_y + 110 * k), 0, 1)   # 原地面线以上堆起来的雪是亮的
        depth = depth ** 0.55 * (1 - np.clip((self.ground - 300 * k) / (600 * k), 0, 1))[None, :]   # 整片被埋住时，下面也是白的
        col = np.stack([150 - 126 * depth, 162 - 134 * depth, 190 - 146 * depth], 2)
        edge = np.clip(1 - (yy - top[None, :]) / (6 * k), 0, 1) * inside          # 表面一条亮边
        crest = np.clip(np.maximum((self.ground_y - 50 * k - yy) / (14 * k), 1 - depth * 8), 0, 1)[..., None] * np.ones((1, W, 1))   # 堆高的部分是新雪，冷白
        col = col * (1 - crest) + np.array([222, 229, 243]) * crest
        col = col + edge[..., None] * 40
        alpha = (inside * 255).astype(np.uint8)
        ground = Image.fromarray(np.dstack([col.clip(0, 255).astype(np.uint8), alpha]), "RGBA")
        return back, near, ground

    def frame(self, A, i, band=True):
        back, near, ground = self.layers(A, i, band)
        back.alpha_composite(near); back.alpha_composite(ground); return back


def run(audio, out, W=1080, H=1920, params=NORMAL, t0=0.0, t1=None, notes=None):
    x, sr = load_audio(audio); A = Analysis(x, sr, notes=load_notes(notes) if notes else None)
    s = Snow(W, H, params, avg_shape=A.avg_shape)
    i0, i1 = int(t0 * FPS), int((t1 or len(x) / sr) * FPS)
    p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-ss", str(t0), "-i", audio, "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", out], stdin=subprocess.PIPE)
    for i in range(i0, i1):
        s.step(A, i); p.stdin.write(s.frame(A, i).convert("RGB").tobytes())
    p.stdin.close(); p.wait(); print(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="一条音频驱动一场雪")
    ap.add_argument("audio"); ap.add_argument("--out", default="snow.mp4")
    ap.add_argument("--w", type=int, default=1080); ap.add_argument("--h", type=int, default=1920)
    ap.add_argument("--notes", help="可选：notes.json 音符表（不给就从音频里找起音）")
    ap.add_argument("--seconds", type=float, help="只渲前几秒（试效果用）")
    ap.add_argument("--first-version", action="store_true", help="用第一版（会下成暴雪）的参数")
    a = ap.parse_args()
    run(a.audio, a.out, a.w, a.h, FIRST_VERSION if a.first_version else NORMAL, t1=a.seconds, notes=a.notes)
