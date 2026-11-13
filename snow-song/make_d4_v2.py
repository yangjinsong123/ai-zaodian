#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
D4「代码写的歌，下了一场初雪」配乐 v2 生成脚本（自有作品，代码作曲 + FluidSynth 渲染）
- 旋律、和弦编排、人性化全部由本脚本生成；未使用任何他人录音或旋律。
- 钢琴：Salamander Grand Piano V3 SF2（Alexander Holm，CC BY 3.0，FreePats 版）
- 弦乐 / Pad：GeneralUser GS v2.0.3（S. Christian Collins，音乐制作可商用）
- 混响：本脚本自写的卷积混响（合成脉冲响应），未用 FluidSynth 内置混响。

用法：
  python make_d4_v2.py --version A            # 整首渲染 + 母带 + 写 notes.json / MIDI
  python make_d4_v2.py --version B
  python make_d4_v2.py --version A --preview 0 15   # 只渲染窗口内的音，低成本检查
环境：Python 3 + numpy、scipy、soundfile、mido、pyloudnorm（见 requirements.txt），另需系统里装 FluidSynth（测试用 2.6.2）。
音色库不随仓库提供，请自己下载（见 README），再用环境变量 SF_PIANO / SF_GU 指向 .sf2 文件。
"""
import argparse, json, os, subprocess, sys, hashlib, math
import numpy as np, soundfile as sf, mido
from scipy.signal import fftconvolve, butter, sosfilt, resample_poly
from scipy.ndimage import minimum_filter1d
import pyloudnorm as pyln

HERE = os.path.dirname(os.path.abspath(__file__))
SF_PIANO = os.environ.get("SF_PIANO", os.path.join(HERE, "soundfonts", "SalamanderGrandPiano-V3+20200602.sf2"))   # 自己下载，见 README
SF_GU = os.environ.get("SF_GU", os.path.join(HERE, "soundfonts", "GeneralUser-GS.sf2"))   # 自己下载，见 README
FLUID = os.environ.get("FLUIDSYNTH", "fluidsynth")   # 系统 PATH 里的 fluidsynth
SR = 48000
TOTAL = 52.5
BPM = 60.0                      # 1 拍 = 1 秒，和旧版一致
TPB = 960
TARGET_LUFS = -14.0
TP_CEIL = -1.5                  # 限幅目标（真峰交付线 -1 dBTP，留 0.5 dB 余量）
# 卡点（沿用旧版 notes.json / timeline.json）
CUE = dict(first_snowflake=0.0, sparkle_high_note=9.6, blizzard_chord=23.0,
           music_cut_start=24.8, music_cut_end=25.3, music_return=27.0,
           last_note=36.0, soft_high_E=41.5, ending_A=46.0)
# 渲染分段：段间用硬门限保证断音 / 留白是真静音（踏板和混响尾巴不会漏进来）
SEGS = [(0.0, 24.8), (25.3, 40.3), (41.0, TOTAL)]

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
def m(name):  # "A2" -> 45
    n, o = name[:-1], int(name[-1]); return 12 * (o + 1) + NOTE_NAMES.index(n)
def nn(p): return NOTE_NAMES[p % 12] + str(p // 12 - 1)

# ---------------------------------------------------------------- 和弦表
CH = {  # 左手分解和弦音（低→高），River Flows 式的「根-五-九-三」开放排列
 "Am":   ["A2", "E3", "B3", "C4"],   "Am/G": ["G2", "E3", "A3", "C4"],
 "F":    ["F2", "C3", "G3", "A3"],   "Fmaj7":["F2", "C3", "E3", "A3"],
 "Dm7":  ["D2", "A2", "F3", "C4"],   "C":    ["C3", "G3", "D4", "E4"],
 "G":    ["G2", "D3", "A3", "B3"],   "G/B":  ["B2", "D3", "G3", "A3"],
 "Esus4":["E2", "B2", "E3", "A3"],   "E":    ["E2", "B2", "E3", "G#3"],
}
STR_V = {  # 弦乐铺底的保持音（中低音区，避开旋律）
 "Am": ["A2", "E3", "C4"], "Am/G": ["G2", "E3", "C4"], "F": ["F2", "C3", "A3"],
 "Fmaj7": ["F2", "C3", "E4"], "Dm7": ["D2", "A2", "F3", "C4"], "C": ["C3", "G3", "E4"],
 "G": ["G2", "D3", "B3"], "G/B": ["B2", "D3", "G3"], "Esus4": ["E2", "B2", "A3"],
 "E": ["E2", "B2", "G#3"],
}

def chords_for(ver):
    if ver == "A":   # 钢琴为主：严格按脚本分镜 Am–F–C–G–Am–F（= C 大调的 vi–IV–I–V）
        return [(0.0, "Am"), (3.0, "F"), (8.0, "C"), (12.0, "G"), (15.0, "Am"), (19.0, "F"),
                (27.0, "Am"), (29.5, "Fmaj7"), (31.8, "G"), (34.0, "Am")]
    # B：每镜开头仍落在脚本的 Am / F / C / G，中间加卡农式下行低音和小调属和弦 E 做推力
    return [(0.0, "Am"), (1.5, "Am/G"), (3.0, "Fmaj7"), (5.5, "Dm7"), (8.0, "C"), (11.0, "G/B"),
            (12.0, "G"), (13.5, "Esus4"), (14.25, "E"), (15.0, "Am"), (17.0, "Am/G"), (19.0, "F"),
            (21.0, "Dm7"), (22.0, "Esus4"), (22.5, "E"),
            (27.0, "Am"), (29.5, "F"), (31.5, "Dm7"), (33.5, "Esus4"), (34.6, "E")]

# ---------------------------------------------------------------- 旋律（自写）
# (时间, 时值, 音, 力度系数, 卡点名)
MEL_COMMON = [
 (2.0, 1.0, "E5", .55, None),
 (3.5, 1.0, "A4", .60, None), (4.5, .5, "C5", .62, None), (5.0, .5, "B4", .58, None),
 (5.5, 1.5, "A4", .60, None), (7.0, .5, "G4", .52, None), (7.5, .5, "E4", .50, None),
 (8.0, .5, "E4", .55, None), (8.5, .5, "G4", .60, None), (9.0, .6, "D5", .66, None),
 (9.6, 1.4, "C5", .74, "sparkle_high_note"), (9.6, 1.4, "C6", .62, "sparkle_high_note"),
 (11.0, .5, "B4", .58, None), (11.5, .5, "G4", .55, None),
 (12.0, 1.0, "D5", .62, None), (13.0, .5, "C5", .58, None), (13.5, .5, "B4", .55, None),
 (15.0, 1.5, "E5", .60, None), (16.5, .5, "D5", .56, None), (17.0, 1.0, "C5", .58, None),
 (18.0, .5, "B4", .55, None), (18.5, .5, "C5", .58, None),
 (19.0, 1.0, "A5", .70, None), (20.0, .5, "E5", .64, None), (20.5, .5, "F5", .68, None),
 (21.0, .75, "G5", .74, None), (21.75, .25, "F5", .70, None), (22.0, .5, "E5", .74, None),
 (22.5, .5, "C5", .76, None),
 (27.0, 1.0, "E5", .50, "music_return"), (28.0, .6, "D5", .46, None), (28.7, 1.0, "C5", .45, None),
 (29.8, 1.0, "A4", .43, None), (30.9, .8, "C5", .42, None), (31.8, .8, "D5", .42, None),
]
MEL = {
 "A": MEL_COMMON + [(14.0, .5, "A4", .52, None), (14.5, .5, "B4", .56, None),
                    (32.7, 1.2, "B4", .38, None), (34.0, 1.0, "C5", .36, None), (35.0, .9, "B4", .33, None)],
 "B": MEL_COMMON + [(14.0, .25, "A4", .52, None), (14.25, .5, "G#4", .55, None), (14.75, .25, "B4", .56, None),
                    (32.7, 1.0, "C5", .40, None), (33.8, .8, "B4", .37, None), (34.7, 1.1, "G#4", .35, None)],
}

class Song:
    def __init__(s, ver, seed):
        s.ver, s.rng = ver, np.random.default_rng(seed)
        s.notes, s.cc = [], []   # notes: dict ; cc: (t, ch, ctrl, val)
    def add(s, t, d, p, v, ch, part, cue=None, human=True, tj=0.010):
        if isinstance(p, str): p = m(p)
        if human and cue is None:
            t = t + float(np.clip(s.rng.normal(0, tj), -2.5 * tj, 2.5 * tj))
            d = d * float(s.rng.uniform(0.9, 1.06))
            v = v + s.rng.normal(0, 4)
        v = int(np.clip(round(v), 8, 125))
        s.notes.append(dict(t=round(max(0.0, t), 4), d=round(d, 4), p=p, v=v, ch=ch, part=part, cue=cue))

def phrase_vel(t):
    """乐句力度起伏：前奏轻→主歌渐强→过程段推到暴雪→尾声渐弱（MIDI 力度基准）"""
    pts = [(0, 58), (3, 50), (6, 56), (8, 52), (10, 62), (12, 56), (15, 50), (17, 56),
           (19, 60), (22.9, 72), (27, 54), (31, 48), (36, 42), (52.5, 34)]
    xs, ys = zip(*pts); return float(np.interp(t, xs, ys))

def arpeggio(s, t0, t1, chord, step_fn, pat, vscale=1.0, ch=0):
    tones = CH[chord]; t, i = t0, 0
    while t < t1 - 1e-6:
        st = step_fn(t); idx = pat[i % len(pat)]
        accent = 1.08 if i % len(pat) == 0 else (0.92 if idx > 1 else 1.0)
        s.add(t, st * 1.8, tones[idx], phrase_vel(t) * vscale * accent * 0.9, ch, "piano_lh")
        t += st; i += 1

def build(ver, seed=20261113):
    s = Song(ver, seed); chords = chords_for(ver)
    # ---- 第 0 帧：干净的 A2（第一片雪），之后 0.5 秒才进分解和弦
    s.add(0.0, 2.6, "A2", 74, 0, "piano_lh", cue="first_snowflake")
    def seg_chords(lo, hi):
        out = []
        for i, (t, c) in enumerate(chords):
            e = chords[i + 1][0] if i + 1 < len(chords) else 36.0
            if t >= lo and t < hi: out.append((t, min(e, hi), c))
        return out
    # 前奏 + 主歌（0–15）：八分音符分解，上下行
    for t, e, c in seg_chords(0, 15):
        st = t + 0.5 if t == 0 else t
        arpeggio(s, st, e, c, lambda x: 0.5, [0, 1, 2, 3, 2, 1], 0.95 if ver == "A" else 0.9)
    # 过程段（15–23，“稍微有点做东西的节奏”）：十六分音符分解，逐渐推高
    for t, e, c in seg_chords(15, 23):
        arpeggio(s, t, e, c, lambda x: 0.25, [0, 1, 2, 3, 2, 3, 2, 1], 0.78)
    # 尾声 1（27–36）：回到 Am，渐慢（ritardando），步长 0.5→0.85 秒
    for t, e, c in seg_chords(27, 36):
        arpeggio(s, t, e, c, lambda x: 0.5 + 0.35 * (x - 27) / 9.0, [0, 1, 2, 3, 2, 1], 0.95)
    # 旋律（右手），旋律音比伴奏晚一点点，像真人“旋律稍后”
    for (t, d, p, k, cue) in MEL[ver]:
        s.add(t + (0 if cue else 0.012), d, p, phrase_vel(t) * k * 1.55, 0, "piano_rh", cue=cue)
    # 低音加厚：每个和弦第一拍低八度（过程段与 B 版更明显）
    for t, e, c in seg_chords(0, 36):
        if t == 0: continue
        root = m(CH[c][0]) - 12
        if root >= m("A1") - 1 and (t >= 15 or ver == "B"):
            s.add(t, min(2.5, e - t + 0.5), root, phrase_vel(t) * 0.55, 0, "piano_lh")
    # ---- 23.00 暴雪和弦：两手砸下一个过满的 Am（加 B / F / G 外音），然后 16 分 / 32 分下行琶音“下成暴雪”
    for p, v in [("A1", 80), ("A2", 84), ("E3", 74), ("A3", 78), ("B3", 64), ("C4", 76), ("E4", 74),
                 ("F4", 60), ("G4", 62), ("A4", 72), ("C5", 70), ("E5", 70), ("A5", 68)]:
        s.add(23.0, 1.75, p, v, 0, "piano_blizzard", cue="blizzard_chord")
    run = ["A6", "E6", "C6", "B5", "A5", "G5", "E5", "C5", "B4", "A4", "E4", "C4", "A3"]
    t = 23.30; k = 0
    while t < 24.62:
        p = m(run[k % len(run)]) + (0 if (k // len(run)) % 2 == 0 else -12)
        s.add(t, 0.6, p, 66 - 5 * (k % 4) + s.rng.normal(0, 4), 0, "piano_blizzard", tj=0.006)
        t += 0.085 + 0.02 * s.rng.random(); k += 1
    # ---- 36.00 最后一个音：A2 + A3 + A4 同时（听感是“一个音”），之后自然衰减
    for p, v in [("A2", 46), ("A3", 34), ("A4", 40)]:
        s.add(36.0, 2.8, p, v, 0, "piano_last", cue="last_note")
    # ---- 41.50 极轻高音 E5（机器人抬头）
    s.add(41.5, 1.4, "E5", 30, 0, "piano_E", cue="soft_high_E")
    s.add(41.5, 1.4, "E6", 18, 0, "piano_E", cue="soft_high_E")
    # ---- 46.00 收尾：再弹一次开头的 A2（加很轻的 E3 / B3 让它像“一个和声里的回声”）
    s.add(46.0, 3.2, "A2", 46, 0, "piano_end", cue="ending_A")
    s.add(46.35, 3.0, "E3", 28, 0, "piano_end"); s.add(46.8, 2.8, "B3", 24, 0, "piano_end")

    # ---------------- 踏板 CC64：换和弦时先抬后踩（legato pedaling），人性化 ±20 ms
    def ped(t, v): s.cc.append((round(t + float(s.rng.normal(0, 0.01)), 4), 0, 64, v))
    s.cc.append((0.03, 0, 64, 100))
    for t, e, c in seg_chords(0, 36):
        if t in (0.0, 27.0): continue
        ped(t - 0.03, 0); ped(t + 0.07, 100 if t < 23 else 90)
    ped(23.0 - 0.03, 0); s.cc.append((23.06, 0, 64, 127))       # 暴雪：踏板踩死
    s.cc.append((24.70, 0, 64, 0))                                  # 断音前抬踏板
    s.cc.append((27.02, 0, 64, 96))
    s.cc.append((35.97, 0, 64, 0)); s.cc.append((36.06, 0, 64, 110)); s.cc.append((38.75, 0, 64, 0))
    s.cc.append((41.52, 0, 64, 90)); s.cc.append((43.2, 0, 64, 0))
    s.cc.append((46.03, 0, 64, 100)); s.cc.append((50.2, 0, 64, 0))

    # ---------------- 弦乐 / pad（GeneralUser GS）
    # ch1 = 49 String Ensemble 2（慢起音铺底）, ch2 = 48 String Ensemble 1（暴雪齐奏）,
    # ch3 = 42 Cello（B 版低音线）, ch4 = 89 Warm Pad（B 版极轻氛围）
    if ver == "A":
        str_start, str_vel, swell = 8.0, 40, 0.75
    else:
        str_start, str_vel, swell = 3.0, 52, 1.0
    for t, e, c in seg_chords(0, 23):
        if t < str_start and not (t <= str_start < e): continue
        tt = max(t, str_start)
        for p in STR_V[c]:
            s.add(tt + 0.05, e - tt + 0.15, p, str_vel + (8 if t >= 15 else 0), 1, "strings", tj=0.02)
    # 暴雪：弦乐齐奏 + 高音
    for p in ["A2", "E3", "A3", "C4", "E4", "A4", "C5", "E5"]:
        s.add(23.0, 1.75, p, 84 if ver == "B" else 64, 2, "strings_blizzard", cue="blizzard_chord")
    if ver == "B":
        # 19–23 小提琴高八度叠旋律（高潮更满）
        for (t, d, p, k, cue) in MEL["B"]:
            if 19.0 <= t < 23.0: s.add(t + 0.02, d + 0.1, m(p), 70 + 30 * (t - 19) / 4, 2, "violin_line")
        # 大提琴低音线（15 秒起）
        for t, e, c in seg_chords(15, 23):
            s.add(t, e - t + 0.1, m(CH[c][0]), 64, 3, "cello")
        for t, e, c in seg_chords(27, 36):
            s.add(t, e - t + 0.1, m(CH[c][0]), 50, 3, "cello")
    # 尾声弦乐：27 秒回来，越来越轻
    for t, e, c in seg_chords(27, 36):
        for p in STR_V[c]:
            s.add(t + 0.1, e - t + 0.2, p, (34 if ver == "A" else 46), 1, "strings", tj=0.02)
    if ver == "B":
        for p in ["A3", "E4"]:                       # 46 秒收尾时极轻的 pad
            s.add(46.0, 4.0, p, 30, 4, "pad")
    # CC11 表情曲线（弦乐渐强渐弱）
    def expr(points, ch):
        xs, ys = zip(*points)
        for t in np.arange(xs[0], xs[-1] + 1e-6, 0.05):
            s.cc.append((round(float(t), 3), ch, 11, int(np.interp(t, xs, ys))))
    if ver == "A":
        e1 = [(0, 0), (8, 40), (12, 70), (15, 60), (19, 70), (22.9, 100), (24.7, 112), (24.79, 0), (27.0, 60), (31, 55), (35.5, 30), (36.5, 0)]
    else:
        e1 = [(0, 0), (3, 50), (8, 72), (12, 82), (15, 78), (19, 92), (22.9, 120), (24.7, 127), (24.79, 0), (27.0, 80), (31, 70), (35.5, 40), (36.5, 0)]
    expr(e1, 1); expr([(0, 110), (24.7, 120), (24.79, 0)], 2)
    if ver == "B":
        expr([(0, 0), (15, 60), (19, 80), (22.9, 110), (24.79, 0), (27, 70), (35.5, 30), (36.5, 0)], 3)
        expr([(45.9, 0), (46.0, 40), (48, 70), (50.5, 0)], 4)
    s.notes.sort(key=lambda n: (n["t"], n["p"])); s.cc.sort()
    return s, chords

# ---------------------------------------------------------------- MIDI
PROG = {0: 0, 1: 49, 2: 48, 3: 42, 4: 89}
def write_midi(path, notes, ccs, chans, t_lo=0.0, t_hi=1e9, cut_at=None):
    mid = mido.MidiFile(ticks_per_beat=TPB); evs = []
    for ch in chans:
        evs.append((0.0, 0, mido.Message("program_change", channel=ch, program=PROG[ch])))
        evs.append((0.0, 0, mido.Message("control_change", channel=ch, control=91, value=0)))  # 关内置混响
        evs.append((0.0, 0, mido.Message("control_change", channel=ch, control=93, value=0)))
        evs.append((0.0, 0, mido.Message("control_change", channel=ch, control=7, value=100)))
        evs.append((0.0, 0, mido.Message("control_change", channel=ch, control=11, value=127 if ch == 0 else 0)))
    for n in notes:
        if n["ch"] not in chans or not (t_lo <= n["t"] < t_hi): continue
        off = n["t"] + n["d"]
        if cut_at is not None: off = min(off, cut_at)
        evs.append((n["t"], 1, mido.Message("note_on", channel=n["ch"], note=n["p"], velocity=n["v"])))
        evs.append((max(off, n["t"] + 0.02), 0, mido.Message("note_off", channel=n["ch"], note=n["p"], velocity=0)))
    for (t, ch, c, v) in ccs:
        if ch in chans and (t_lo - 3 <= t < t_hi):
            evs.append((max(0.0, t), 0 if c == 64 and v == 0 else 1, mido.Message("control_change", channel=ch, control=c, value=v)))
    evs.sort(key=lambda e: (e[0], e[1]))
    tr = mido.MidiTrack(); mid.tracks.append(tr)
    tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(BPM)))
    tr.append(mido.MetaMessage("time_signature", numerator=4, denominator=4))
    last = 0
    for t, _, msg in evs:
        tick = int(round(t * TPB * BPM / 60)); msg.time = tick - last; last = tick; tr.append(msg)
    tr.append(mido.MetaMessage("end_of_track", time=int(TPB * 2)))
    mid.save(path)

def write_midi_delivery(path, s):
    """交付用多轨 MIDI：钢琴（含 CC64 踏板）+ 各弦乐轨，一条时间线（无分段）"""
    mid = mido.MidiFile(ticks_per_beat=TPB)
    names = {0: "Piano (Salamander)", 1: "Strings pad (GU 49)", 2: "Strings tutti (GU 48)", 3: "Cello (GU 42)", 4: "Warm pad (GU 89)"}
    chans = sorted({n["ch"] for n in s.notes})
    for ch in chans:
        tr = mido.MidiTrack(); mid.tracks.append(tr)
        tr.append(mido.MetaMessage("track_name", name=names[ch]))
        if ch == chans[0]:
            tr.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(BPM)))
            tr.append(mido.MetaMessage("time_signature", numerator=4, denominator=4))
        evs = [(0.0, 0, mido.Message("program_change", channel=ch, program=PROG[ch]))]
        for n in s.notes:
            if n["ch"] != ch: continue
            off = n["t"] + n["d"]
            if n["t"] < 24.8: off = min(off, 24.78)
            evs.append((n["t"], 1, mido.Message("note_on", channel=ch, note=n["p"], velocity=n["v"])))
            evs.append((off, 0, mido.Message("note_off", channel=ch, note=n["p"], velocity=0)))
        for (t, c_, c, v) in s.cc:
            if c_ == ch: evs.append((t, 1, mido.Message("control_change", channel=ch, control=c, value=v)))
        evs.sort(key=lambda e: (e[0], e[1])); last = 0
        for t, _, msg in evs:
            tick = int(round(t * TPB)); msg.time = tick - last; last = tick; tr.append(msg)
    mid.save(path)

def render(mid_path, sf2, wav_path, gain):
    cmd = [FLUID, "-ni", "-q", "-R", "0", "-C", "0", "-g", str(gain), "-r", str(SR), "-O", "float", "-T", "wav",
           "-o", "synth.polyphony=1024", "-o", "synth.reverb.active=0", "-o", "synth.chorus.active=0",
           "-F", wav_path, sf2, mid_path]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    x, sr = sf.read(wav_path, dtype="float64", always_2d=True); assert sr == SR
    return x

# ---------------------------------------------------------------- 混响（合成脉冲响应）
def make_ir(rt60, pre=0.02, seed=7, length=None, damp_hz=6000.0):
    rng = np.random.default_rng(seed); L = int((length or rt60 * 1.3) * SR); t = np.arange(L) / SR
    ir = np.zeros((L, 2))
    for c in range(2):
        nz = rng.standard_normal(L)
        hi = sosfilt(butter(2, damp_hz, "high", fs=SR, output="sos"), nz)
        lo = nz - hi
        env = np.exp(-6.91 * t / rt60); env_hi = np.exp(-6.91 * t / (rt60 * 0.45))
        ir[:, c] = lo * env + 0.5 * hi * env_hi
        ir[:, c] *= np.clip(t / 0.03, 0, 1)                # 柔和起始
    for d, g in [(0.011, .5), (0.017, .4), (0.023, .35), (0.031, .3)]:   # 早期反射
        k = int(d * SR); ir[k, 0] += g; ir[int(k * 1.13), 1] += g
    pad = int(pre * SR); ir = np.vstack([np.zeros((pad, 2)), ir])
    return ir / np.sqrt((ir ** 2).sum(0).mean())

def reverb(x, ir, wet):
    y = np.stack([fftconvolve(x[:, c], ir[:, c])[:len(x)] for c in range(2)], 1)
    return x + wet * y

def fade_env(n, pts):
    t = np.arange(n) / SR; xs, ys = zip(*pts); return np.interp(t, xs, ys)

def true_peak_db(x):
    os_ = resample_poly(x, 4, 1, axis=0); return 20 * np.log10(np.max(np.abs(os_)) + 1e-12)

def limiter(x, ceil_db):
    thr = 10 ** (ceil_db / 20)
    os_ = np.abs(resample_poly(x, 4, 1, axis=0)).max(1)
    env = os_[: len(x) * 4].reshape(-1, 4).max(1)
    g = np.minimum(1.0, thr / np.maximum(env, 1e-9))
    look = int(0.004 * SR); g = minimum_filter1d(g, size=2 * look + 1)
    rel = np.exp(-1 / (0.08 * SR)); out = np.empty_like(g); cur = 1.0
    for i, gi in enumerate(g):            # 只有恢复是慢的，压缩立刻生效
        cur = gi if gi < cur else gi + (cur - gi) * rel; out[i] = cur
    k = np.hanning(look * 2 + 1); k /= k.sum(); out = np.convolve(out, k, mode="same")
    out = np.minimum(out, g * 0 + 1.0)
    return x * out[:, None]

def compressor(x, thr_db, ratio, att=0.03, rel=0.35):
    """温和的总线压缩（RMS 检波，2:1），只压过响的暴雪 / 过程段，减小峰值响度比"""
    blk = 240; nb = len(x) // blk
    p = (x[: nb * blk] ** 2).mean(1).reshape(nb, blk).mean(1)
    lvl = 10 * np.log10(p + 1e-12); out = np.empty(nb); cur = -120.0
    a_att, a_rel = np.exp(-blk / (att * SR)), np.exp(-blk / (rel * SR))
    for i, l in enumerate(lvl):
        cur = l + (cur - l) * (a_att if l > cur else a_rel); out[i] = cur
    gr = np.minimum(0.0, (thr_db - out) * (1 - 1 / ratio))
    g = np.repeat(10 ** (gr / 20), blk); g = np.concatenate([g, np.full(len(x) - len(g), g[-1])])
    return x * g[:, None], float(gr.min())

def master(mix):
    meter = pyln.Meter(SR); y = mix.copy()
    sos = butter(2, 28, "high", fs=SR, output="sos"); y = sosfilt(sos, y, axis=0)
    y = y * 10 ** ((TARGET_LUFS - meter.integrated_loudness(y)) / 20)
    y, gr_c = compressor(y, TARGET_LUFS - 4.0, 2.0)
    pre = None
    for _ in range(6):                         # 增益→限幅→复测，收敛到 -14 LUFS 且真峰 ≤ -1.3
        y = y * 10 ** ((TARGET_LUFS - meter.integrated_loudness(y)) / 20)
        if pre is None: pre = true_peak_db(y)
        if true_peak_db(y) > TP_CEIL + 0.2: y = limiter(y, TP_CEIL)
        if abs(meter.integrated_loudness(y) - TARGET_LUFS) < 0.03 and true_peak_db(y) <= -1.3: break
    if true_peak_db(y) > -1.3: y = y * 10 ** ((-1.3 - true_peak_db(y)) / 20)
    master.stats = dict(compressor_max_gr_db=round(gr_c, 2), true_peak_before_limiter_db=round(pre, 2),
                        limiter_max_gr_db=round(pre - true_peak_db(y), 2) if pre > true_peak_db(y) else 0.0,
                        lufs_pyloudnorm=round(meter.integrated_loudness(y), 2), true_peak_4x_db=round(true_peak_db(y), 2))
    return y

# ---------------------------------------------------------------- 主流程
def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--version", choices=["A", "B"], required=True)
    ap.add_argument("--preview", nargs=2, type=float)
    ap.add_argument("--segs", default="0,1,2", help="只重渲这些分段，其余复用 work/ 里已渲染的分轨（省额度）")
    ap.add_argument("--meta-only", action="store_true", help="不渲染，只按同一随机种子重写 notes_X.json 和 MIDI")
    a = ap.parse_args(); only = {int(z) for z in a.segs.split(",")}
    ver = a.version; s, chords = build(ver)
    work = os.path.join(HERE, "work"); os.makedirs(work, exist_ok=True)
    if a.meta_only:
        old = json.load(open(os.path.join(HERE, f"notes_{ver}.json"), encoding="utf-8"))
        master.stats = old.get("mastering"); write_meta(ver, s, chords); print("meta written"); return
    win = a.preview or (0.0, TOTAL)
    n = int(TOTAL * SR); mix = np.zeros((n, 2))
    ir_p, ir_s = make_ir(2.3, seed=11), make_ir(2.8, seed=23, damp_hz=5000)
    piano_wet, str_wet = (0.22, 0.30)
    str_gain = 0.75 if ver == "A" else 0.80
    for k, (lo, hi) in enumerate(SEGS):
        if hi <= win[0] or lo >= win[1]: continue
        for part, chans, sf2, g, ir, wet in [("pf", [0], SF_PIANO, 0.5, ir_p, piano_wet),
                                             ("st", [1, 2, 3, 4], SF_GU, 0.5 * str_gain, ir_s, str_wet)]:
            if not any(n_["ch"] in chans and lo <= n_["t"] < hi and win[0] - 3 <= n_["t"] < win[1] for n_ in s.notes): continue
            sub = [n_ for n_ in s.notes if win[0] - 3 <= n_["t"] < win[1]]
            mp = os.path.join(work, f"{ver}_seg{k}_{part}.mid"); wp = os.path.join(work, f"{ver}_seg{k}_{part}.wav")
            write_midi(mp, sub, s.cc, chans, lo, hi, cut_at=(24.78 if k == 0 else None))
            x = render(mp, sf2, wp, g) if (k in only or not os.path.exists(wp)) else sf.read(wp, dtype="float64", always_2d=True)[0]
            x = x[:n] if len(x) >= n else np.vstack([x, np.zeros((n - len(x), 2))])
            x = reverb(x, ir, wet)
            # 段门限：段外严格为 0（断音 / 留白不被踏板、采样释放和混响尾巴污染）
            if k == 0:   env = fade_env(n, [(0, 1), (24.77, 1), (24.80, 0), (TOTAL, 0)])
            elif k == 1: env = fade_env(n, [(0, 0), (25.3, 0), (25.3001, 1), (38.8, 1), (40.3, 0), (TOTAL, 0)])
            else:        env = fade_env(n, [(0, 0), (41.0, 0), (41.0001, 1), (49.0, 1), (51.3, 0), (TOTAL, 0)])
            mix += x * env[:, None]
    if a.preview:
        i0, i1 = int(win[0] * SR), int(win[1] * SR)
        y = mix[i0:i1]; y = y / (np.max(np.abs(y)) + 1e-9) * 0.7
        out = os.path.join(work, f"preview_{ver}_{win[0]:.0f}-{win[1]:.0f}.wav")
        sf.write(out, y, SR, subtype="PCM_16"); print("preview", out); return
    y = master(mix)
    for g, (a0, a1) in [(0, (24.8, 25.3)), (0, (40.3, 41.0)), (0, (51.3, TOTAL))]:   # 再保险：静音窗写成数字 0
        y[int(a0 * SR):int(a1 * SR)] = 0.0
    base = f"D4_配乐v2_{ver}"
    wav = os.path.join(HERE, base + "_-14LUFS.wav"); sf.write(wav, y, SR, subtype="PCM_24")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-c:a", "libmp3lame", "-b:a", "192k",
                    os.path.join(HERE, base + "_试听.mp3")], check=True)
    write_meta(ver, s, chords); print("done", wav)

def write_meta(ver, s, chords):
    base = f"D4_配乐v2_{ver}"
    write_midi_delivery(os.path.join(HERE, base + ".mid"), s)
    vr = os.path.join(HERE, "work", "verify_result.json")
    verify = json.load(open(vr, encoding="utf-8")).get(ver) if os.path.exists(vr) else None
    meta = dict(title=f"D4 配乐 v2 · {ver} 版", account="AI造点真东西", version=ver,
                license="自有作品（代码作曲、代码编曲）。渲染音色：Salamander Grand Piano V3（CC BY 3.0，需署名）+ GeneralUser GS v2.0.3（可商用，无强制署名）。详见 授权说明.txt",
                key="A minor（A 自然小调；B 版尾段与过门用和声小调属和弦 E）", bpm=BPM, time_signature="4/4",
                duration_sec=TOTAL, sample_rate=SR, bit_depth=24, target_lufs=TARGET_LUFS, true_peak_limit_dbtp=-1.0,
                markers=[dict(time=v, name=k) for k, v in sorted(CUE.items(), key=lambda kv: kv[1])],
                silence_windows=[[24.8, 25.3], [40.3, 41.0], [51.3, TOTAL]], mastering=master.stats,
                chords=[dict(start=t, name=c) for t, c in chords],
                sections=[dict(start=0, end=8, name="前奏 intro"), dict(start=8, end=15, name="主歌 verse"),
                          dict(start=15, end=24.8, name="推进 → 高潮（23.00 暴雪和弦）"), dict(start=24.8, end=25.3, name="断音（数字静音）"),
                          dict(start=25.3, end=27, name="留白"), dict(start=27, end=40.3, name="尾声 1：回到 Am、渐慢渐弱、36.00 最后一个音"),
                          dict(start=41.5, end=44, name="极轻 E5"), dict(start=46, end=51.3, name="尾声 2：A2 收尾")],
                notes_format="与旧版相同：start(秒) / freq(Hz) / velocity(0–1)，可直接给 app/snow-song/snow.py 的 load_notes 用；midi_velocity 为原始 MIDI 力度",
                notes=[dict(start=n_["t"], duration=n_["d"], pitch=nn(n_["p"]), midi=n_["p"],
                            freq=round(440.0 * 2 ** ((n_["p"] - 69) / 12), 4), velocity=round(n_["v"] / 127, 3),
                            midi_velocity=n_["v"], channel=n_["ch"], part=n_["part"], cue=n_["cue"]) for n_ in s.notes],
                midi_cc=[dict(time=t, channel=ch, cc=c, value=v) for (t, ch, c, v) in s.cc if c == 64])
    meta["verify"] = verify
    json.dump(meta, open(os.path.join(HERE, f"notes_{ver}.json"), "w"), ensure_ascii=False, indent=1)

if __name__ == "__main__":
    main()
