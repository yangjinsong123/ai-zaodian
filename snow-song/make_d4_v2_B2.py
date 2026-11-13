#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
D4 配乐 v2 · B2：在 B 版基础上做演奏人性化（和弦、编曲、时长、卡点不变）
- 复用 make_d4_v2.py 的 B 版编曲（同一随机种子），先取回每个音的「谱面」时间 / 力度，再按新规则重新演奏。
- 冻结区：22.45–25.30（含 23.00 暴雪和弦、暴雪琶音、24.80 断音前后）完全沿用 B 版的音和踏板；所有卡点音沿用 B 版。
- 总长 52.467 s = 2,518,416 样本 @ 48 kHz。
用法：python make_d4_v2_B2.py [--preview 0 16]
"""
import argparse, json, os, sys, subprocess
import numpy as np, soundfile as sf
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import make_d4_v2 as M

M.TOTAL = 52.467
N_SAMPLES = 2518416
SEED = 20261114
FREEZE = (22.45, 25.30)
ANCHORS = [0.0, 9.6, 23.0, 27.0, 36.0, 41.5, 46.0]
# 乐句（力度拱形 + 句尾渐慢的单位）
PHRASES = [(0, 3), (3, 8), (8, 12), (12, 15), (15, 19), (19, 22.45), (27, 29.5), (29.5, 31.5), (31.5, 33.5), (33.5, 36)]
# 弹性速度：在这些换句点前渐慢、换句后追回（窗口不跨卡点、不进冻结区）
RUBATO = [(3.0, 1.5, .060), (8.0, 1.5, .060), (12.0, 1.5, .055), (15.0, 1.5, .060), (19.0, 1.5, .065),
          (29.5, 1.0, .045), (31.5, 1.0, .045), (33.5, 1.0, .040)]
P = dict(vel_rand=8, lh_scale=0.88, mel_over=8, arch_lo=0.86, arch_amp=0.24,
         jitter_sigma_ms=14.0, jitter_clip_ms=20.0, spread_ms=(5.0, 15.0), dur_scale=(0.92, 1.08),
         legato_overlap_ms=(20, 40), pedal_up_after_ms=(0, 30), pedal_down_after_ms=(80, 150), pedal_depth=(92, 115))

def delta(t):
    """弹性速度位移（秒）：换句点 b 前 W 秒二次曲线渐慢到 +D，b 后 W 秒余弦追回到 0。卡点处恒为 0。"""
    d = 0.0
    for b, W, D in RUBATO:
        if b - W <= t < b: d += D * ((t - (b - W)) / W) ** 2
        elif b <= t < b + W: d += D * 0.5 * (1 + np.cos(np.pi * (t - b) / W))
    return d

def arch(t):
    for a, b in PHRASES:
        if a <= t < b:
            x = (t - a) / (b - a); return P["arch_lo"] + P["arch_amp"] * np.sin(np.pi * x ** 0.8)
    return 1.0

def build_b_with_nominal():
    orig_add = M.Song.add
    def add(self, t, d, p, v, ch, part, cue=None, human=True, tj=0.010):
        orig_add(self, t, d, p, v, ch, part, cue, human, tj)
        n = self.notes[-1]; n["t0"], n["d0"], n["v0"] = t, d, v
    M.Song.add = add
    try: s, chords = M.build("B")
    finally: M.Song.add = orig_add
    return s, chords

def humanize(s, chords):
    rng = np.random.default_rng(SEED)
    frozen = lambda t: FREEZE[0] <= t < FREEZE[1]
    piano = [n for n in s.notes if n["ch"] == 0]
    # ---- 力度
    for n in piano:
        n["vB"] = n["v"]
        if n["cue"] or frozen(n["t0"]) or n["t0"] >= 36.0: continue
        v = n["v0"] * arch(n["t0"])
        if n["part"] == "piano_lh": v *= P["lh_scale"]
        n["v"] = v
    for n in piano:
        if n["cue"] or frozen(n["t0"]) or n["t0"] >= 36.0: continue
        n["v"] = int(np.clip(round(n["v"] + rng.uniform(-P["vel_rand"], P["vel_rand"])), 16, 118))
    for n in piano:   # 随机之后再保证：旋律音比同一时刻（±30 ms）的其他音至少高 mel_over
        if n["part"] != "piano_rh" or n["cue"] or frozen(n["t0"]): continue
        others = [o["v"] for o in piano if o is not n and abs(o["t0"] - n["t0"]) < 0.03 and not o["cue"]]
        if others: n["v"] = int(min(118, max(n["v"], max(others) + P["mel_over"])))
    # ---- 时值：弹性速度 + 起音随机 + 和弦错开
    cand = sorted([n for n in piano if not n["cue"] and not frozen(n["t0"])], key=lambda n: n["t0"])
    groups, cur = [], []
    for n in cand:                                   # 谱面起音相差 ≤20 ms 的音算同一个和弦（旋律原本晚 12 ms，也并进来）
        if cur and n["t0"] - cur[0]["t0"] > 0.020: groups.append(cur); cur = []
        cur.append(n)
    if cur: groups.append(cur)
    for g in groups:
        t0 = min(n["t0"] for n in g); j = float(np.clip(rng.normal(0, P["jitter_sigma_ms"]), -P["jitter_clip_ms"], P["jitter_clip_ms"])) / 1000
        g.sort(key=lambda n: n["p"]); off = 0.0
        for i, n in enumerate(g):
            if i > 0: off += rng.uniform(*P["spread_ms"]) / 1000
            n["jit"], n["spr"], n["rub"], n["grp"] = j, off, delta(t0), id(g)
            t = t0 + delta(t0) + j + off
            if t0 < FREEZE[0]: t = min(t, FREEZE[0] - 0.005)          # 不越进冻结区
            if 25.3 <= t0 < 27.0: t = max(t, 25.3)
            end0 = t0 + n["d0"] * rng.uniform(*P["dur_scale"])
            n["t"] = round(max(0.0, t), 4); n["d"] = round(max(0.05, end0 + delta(end0) - (t0 + delta(t0))), 4)
    # 旋律连奏：相邻旋律音之间留 20–40 ms 手指重叠（句尾不连）
    mel = sorted([n for n in piano if n["part"] == "piano_rh" and not frozen(n["t0"])], key=lambda n: n["t"])
    phrase_end = {b for _, b in PHRASES}
    for a, b in zip(mel, mel[1:]):
        if a["cue"] or any(a["t0"] < pe <= b["t0"] for pe in phrase_end): continue
        gap = b["t"] - (a["t"] + a["d"])
        if gap < 0.15: a["d"] = round(b["t"] - a["t"] + rng.uniform(*P["legato_overlap_ms"]) / 1000, 4)
    # 弦乐只跟着弹性速度挪（不另加随机），冻结区和卡点不动
    for n in s.notes:
        if n["ch"] != 0 and not n["cue"] and not frozen(n["t0"]):
            n["t"] = round(n["t"] + delta(n["t0"]), 4)
    # ---- 踏板：换和弦时先抬后踩，重新踩在新和弦实际起音之后
    keep = [c for c in s.cc if not (c[2] == 64 and (0.05 < c[0] < FREEZE[0] or 27.05 < c[0] < 35.9))]
    newp = []
    for t, name in chords:
        if not (0.05 < t < FREEZE[0] or 27.05 < t < 35.9): continue
        on = min([n["t"] for n in piano if abs(n["t0"] - t) < 0.002] or [t + delta(t)])
        up = on + rng.uniform(*P["pedal_up_after_ms"]) / 1000
        dn = on + rng.uniform(*P["pedal_down_after_ms"]) / 1000
        newp += [(round(up, 4), 0, 64, 0), (round(dn, 4), 0, 64, int(rng.integers(P["pedal_depth"][0], P["pedal_depth"][1] + 1)))]
    s.cc = sorted(keep + newp)
    s.notes.sort(key=lambda n: (n["t"], n["p"]))
    return s

def stats(s):
    piano = [n for n in s.notes if n["ch"] == 0]
    free = [n for n in piano if not n["cue"] and not (FREEZE[0] <= n["t0"] < FREEZE[1])]
    vB = np.array([n["vB"] for n in free]); v2 = np.array([n["v"] for n in free])
    resid = lambda arr: arr  # 占位
    off = np.array([(n["t"] - n["t0"]) * 1000 for n in free if "jit" in n])
    jit = np.array([n["jit"] * 1000 for n in free if "jit" in n])
    spr = [n["spr"] * 1000 for n in free if n.get("spr", 0) > 0]
    gaps = []
    gs = {}
    for n in free:
        if "jit" in n: gs.setdefault(n["grp"], []).append(n)
    for g in gs.values():
        if len(g) > 1:
            ts = sorted(x["t"] for x in g); gaps += list(np.diff(ts) * 1000)
    # 局部速度曲线：谱面间隔 / 实际（只算弹性速度部分），每 0.25 s 采样
    curve = []
    for a, b in [(0, 22.45), (27, 36)]:
        for t in np.arange(a, b, 0.25):
            r = 0.25 / (0.25 + delta(t + 0.25) - delta(t)); curve.append((round(float(t), 2), round(float(r * 60), 2)))
    tempos = np.array([c[1] for c in curve])
    lh = [n for n in free if n["part"] == "piano_lh"]; rh = [n for n in free if n["part"] == "piano_rh"]
    mel_lead = []
    for n in rh:
        oth = [o["v"] for o in piano if o is not n and abs(o["t0"] - n["t0"]) < 0.03 and not o["cue"]]
        if oth: mel_lead.append(n["v"] - max(oth))
    def local_std(key):
        res = []
        for part in ("piano_lh", "piano_rh"):
            ns = [n for n in free if n["part"] == part]
            for n in ns:
                nb = [o[key] for o in ns if abs(o["t0"] - n["t0"]) <= 1.0]
                if len(nb) >= 3: res.append(n[key] - np.mean(nb))
        return round(float(np.std(res)), 2)
    return dict(
        velocity_local_std_vs_1s_neighbourhood=dict(B=local_std("vB"), B2=local_std("v")),
        n_piano_humanized=len(free), n_piano_total=len(piano),
        velocity=dict(B_std=round(float(vB.std()), 2), B2_std=round(float(v2.std()), 2),
                      B_range=[int(vB.min()), int(vB.max())], B2_range=[int(v2.min()), int(v2.max())],
                      B2_LH_mean=round(float(np.mean([n["v"] for n in lh])), 1), B2_RH_mean=round(float(np.mean([n["v"] for n in rh])), 1),
                      melody_over_chord_min=int(min(mel_lead)) if mel_lead else None, melody_over_chord_mean=round(float(np.mean(mel_lead)), 1) if mel_lead else None,
                      B_LH_mean=round(float(np.mean([n["vB"] for n in lh])), 1), B_RH_mean=round(float(np.mean([n["vB"] for n in rh])), 1)),
        onset_jitter_ms=dict(std=round(float(jit.std()), 1), mean_abs=round(float(np.abs(jit).mean()), 1),
                             p10_p90=[round(float(np.percentile(jit, 10)), 1), round(float(np.percentile(jit, 90)), 1)], max_abs=round(float(np.abs(jit).max()), 1)),
        chord_spread_gap_ms=dict(n=len(gaps), min=round(float(min(gaps)), 1), max=round(float(max(gaps)), 1), mean=round(float(np.mean(gaps)), 1)) if gaps else None,
        total_offset_vs_score_ms=dict(std=round(float(off.std()), 1), min=round(float(off.min()), 1), max=round(float(off.max()), 1)),
        rubato=dict(local_tempo_bpm_min=float(tempos.min()), local_tempo_bpm_max=float(tempos.max()),
                    max_slowdown_pct=round(float((1 - tempos.min() / 60) * 100), 1), max_speedup_pct=round(float((tempos.max() / 60 - 1) * 100), 1),
                    drift_at_anchors_ms={str(a): round(delta(a) * 1000, 3) for a in ANCHORS},
                    curve_every_0_25s=curve))

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--preview", nargs=2, type=float); a = ap.parse_args()
    s, chords = build_b_with_nominal(); s = humanize(s, chords); st = stats(s)
    work = os.path.join(HERE, "work"); os.makedirs(work, exist_ok=True)
    win = a.preview or (0.0, M.TOTAL); n = int(round(M.TOTAL * M.SR)); assert n == N_SAMPLES
    mix = np.zeros((n, 2)); ir_p, ir_s = M.make_ir(2.3, seed=11), M.make_ir(2.8, seed=23, damp_hz=5000)
    for k, (lo, hi) in enumerate(M.SEGS):
        hi = min(hi, M.TOTAL)
        if hi <= win[0] or lo >= win[1]: continue
        for part, chans, sf2, g, ir, wet in [("pf", [0], M.SF_PIANO, 0.5, ir_p, 0.22), ("st", [1, 2, 3, 4], M.SF_GU, 0.5 * 0.80, ir_s, 0.30)]:
            sub = [x for x in s.notes if win[0] - 3 <= x["t"] < win[1]]
            if not any(x["ch"] in chans and lo <= x["t"] < hi for x in sub): continue
            mp, wp = os.path.join(work, f"B2_seg{k}_{part}.mid"), os.path.join(work, f"B2_seg{k}_{part}.wav")
            M.write_midi(mp, sub, s.cc, chans, lo, hi, cut_at=(24.78 if k == 0 else None))
            x = M.render(mp, sf2, wp, g); x = x[:n] if len(x) >= n else np.vstack([x, np.zeros((n - len(x), 2))])
            x = M.reverb(x, ir, wet)
            if k == 0:   env = M.fade_env(n, [(0, 1), (24.77, 1), (24.80, 0), (M.TOTAL, 0)])
            elif k == 1: env = M.fade_env(n, [(0, 0), (25.3, 0), (25.3001, 1), (38.8, 1), (40.3, 0), (M.TOTAL, 0)])
            else:        env = M.fade_env(n, [(0, 0), (41.0, 0), (41.0001, 1), (49.0, 1), (51.3, 0), (M.TOTAL, 0)])
            mix += x * env[:, None]
    if a.preview:
        i0, i1 = int(win[0] * M.SR), int(win[1] * M.SR); y = mix[i0:i1]; y = y / (np.abs(y).max() + 1e-9) * 0.7
        out = os.path.join(work, f"preview_B2_{win[0]:.0f}-{win[1]:.0f}.wav"); sf.write(out, y, M.SR, subtype="PCM_16")
        print("preview", out); print(json.dumps({k: v for k, v in st.items() if k != "rubato"}, ensure_ascii=False)); return
    y = M.master(mix)
    for a0, a1 in [(24.8, 25.3), (40.3, 41.0), (51.3, M.TOTAL)]: y[int(a0 * M.SR):int(a1 * M.SR)] = 0.0
    assert len(y) == N_SAMPLES
    wav = os.path.join(HERE, "D4_配乐v2_B2_-14LUFS.wav"); sf.write(wav, y, M.SR, subtype="PCM_24")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-c:a", "libmp3lame", "-b:a", "192k",
                    os.path.join(HERE, "D4_配乐v2_B2_试听.mp3")], check=True)
    vp = os.path.join(work, "verify.py")   # 配乐部门内部的核对脚本，仓库里没有就跳过
    if os.path.exists(vp): subprocess.run([sys.executable, vp, "B2"], check=True, stdout=subprocess.DEVNULL)
    M.write_meta("B2", s, chords)
    p = os.path.join(HERE, "notes_B2.json"); d = json.load(open(p, encoding="utf-8"))
    d["title"] = "D4 配乐 v2 · B2 版（B 版 + 演奏人性化）"; d["version"] = "B2"; d["duration_samples"] = N_SAMPLES
    d["humanization"] = dict(params=P, rubato_points=[dict(boundary=b, window_s=W, peak_delay_ms=D * 1000) for b, W, D in RUBATO],
                             phrases=PHRASES, freeze_window=list(FREEZE), seed=SEED, stats=st)
    json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("done", wav); print(json.dumps({k: v for k, v in st.items() if k != "rubato"}, ensure_ascii=False))
    print(json.dumps({k: v for k, v in st["rubato"].items() if k != "curve_every_0_25s"}))

if __name__ == "__main__":
    main()
