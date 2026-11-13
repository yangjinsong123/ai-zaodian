"""从配乐 wav 离线算 64 段频谱，逐帧（30 fps）写 JSON，Three.js 直接读来定楼高。两版，同一段音频、同一组 FFT：
  proc（正常版，第 1–8、10 右、11–17 镜）：对数分段（30 Hz–16 kHz 按对数等分 64 段）→ 幅度压缩（转 dB，按全曲 99.5 分位往下 54 dB 线性映射到 0–1）→ 平滑（上升不平滑，下落每帧乘 0.80）
  raw （翻车版，第 9 镜、第 10 镜左）：线性分段（0–24 kHz 等宽 64 段，每段 375 Hz）→ 直接用线性幅度 → 不平滑。
        为了和正常版放在同一把尺子上：raw 的全曲平均高度 = proc 的全曲平均高度（只乘一个常数，不改形状）。
FFT：每帧一个 4096 点 Hann 窗，窗从「这一帧时刻 − 1024 个采样」开始（第 0 帧前面补零），所以第 0 帧就含第一记重击。
用法：python spectrum.py <wav> <out.json> [--fps 30]"""
import sys, json, argparse
import numpy as np, soundfile as sf
ap = argparse.ArgumentParser(); ap.add_argument("wav"); ap.add_argument("out"); ap.add_argument("--fps", type=int, default=30); ap.add_argument("--bands", type=int, default=64)
a = ap.parse_args()
x, sr = sf.read(a.wav, dtype="float32", always_2d=True); x = x.mean(1)
N, PRE, B = 4096, 1024, a.bands; nfr = int(round(len(x) / sr * a.fps)); win = np.hanning(N).astype(np.float32)
xp = np.concatenate([np.zeros(PRE, np.float32), x, np.zeros(N, np.float32)])
freqs = np.fft.rfftfreq(N, 1 / sr)
S = np.empty((nfr, len(freqs)), np.float32)
for i in range(nfr):
    s = int(round(i / a.fps * sr)); S[i] = np.abs(np.fft.rfft(xp[s:s + N] * win)) / (N / 4)   # s 在补零后的坐标里 = 帧时刻 − PRE
# ---- 正常版 ----
edges = np.geomspace(30, 16000, B + 1); P = np.empty((nfr, B), np.float32)
for b in range(B):
    m = (freqs >= edges[b]) & (freqs < edges[b + 1])
    if m.sum() == 0: m = np.abs(freqs - np.sqrt(edges[b] * edges[b + 1])) == np.abs(freqs - np.sqrt(edges[b] * edges[b + 1])).min()   # 低频段比一个 FFT 格还窄：取最近的那一格
    P[:, b] = (S[:, m] ** 2).mean(1)
db = 10 * np.log10(P + 1e-12); top = np.percentile(db, 99.5); RANGE = 54.0
lin = np.clip((db - (top - RANGE)) / RANGE, 0, 1)
proc = np.empty_like(lin); proc[0] = lin[0]; REL = 0.80
for i in range(1, nfr): proc[i] = np.maximum(lin[i], proc[i - 1] * REL)
# ---- 第 10 镜右侧逐步修：step1 = 只做对数分段（线性幅度、不平滑），step2 = 对数分段 + 幅度压缩（不平滑），step3 = proc ----
amp = np.sqrt(P); step1 = amp / amp.mean() * proc.mean(); step2 = lin
# ---- 翻车版 ----
ledges = np.linspace(0, sr / 2, B + 1); R = np.empty((nfr, B), np.float32)
for b in range(B):
    m = (freqs >= ledges[b]) & (freqs < ledges[b + 1]) if b < B - 1 else (freqs >= ledges[b])
    R[:, b] = S[:, m].mean(1)
raw = R / R.mean() * proc.mean()
out = dict(fps=a.fps, frames=nfr, bands=B, sample_rate=sr, fft=N, window="hann", window_start_offset_samples=-PRE,
           proc=dict(method="log bands 30Hz-16kHz, power→dB, top=99.5 percentile, range 54 dB → 0..1, release ×0.80/frame", edges_hz=[round(e, 2) for e in edges], top_db=round(float(top), 2), range_db=RANGE, release=REL,
                     h=np.round(proc, 4).tolist()),
           raw=dict(method="linear bands 0-24kHz (375 Hz each), linear magnitude, no compression, no smoothing; one global constant so mean(raw)=mean(proc)", edges_hz=[round(e, 1) for e in ledges], scale=float(proc.mean() / R.mean()),
                    h=np.round(raw, 4).tolist()),
           step1=dict(method="log bands, linear magnitude (sqrt power), no compression, no smoothing; mean matched to proc", h=np.round(step1, 4).tolist()),
           step2=dict(method="log bands + dB compression (same as proc before smoothing), no smoothing", h=np.round(step2, 4).tolist()))
json.dump(out, open(a.out, "w"))
print("frames", nfr, "proc mean %.3f max %.3f" % (proc.mean(), proc.max()), "raw max %.2f band-mean" % raw.max(), np.round(raw.mean(0)[:6], 3), "others mean %.4f" % raw[:, 2:].mean())
print("frame0 proc（每 8 段取一个）", np.round(proc[0][::8], 2))
print("raw 每段全曲平均（前 6 段）", np.round(raw.mean(0)[:6], 3))
