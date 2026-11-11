#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
D4《代码歌》合成脚本
账号「AI造点真东西」自有作品：numpy / scipy 纯合成，不使用采样或有版权的音色库。

依据：本账号 D4 分镜脚本（约 52 秒，A 小调，Am–F–C–G）
  - 约 52 秒；A 小调；Am–F–C–G；60 BPM；单音钢琴感（无 Pad 铺底）+ 2–3 秒长混响
  - t=0 低音 A2 对上第一片雪；8–12 秒放一个高音给雪花闪光
  - 23 秒暴雪和弦，随后音乐切断 0.5 秒；27 秒回到 Am 并渐慢渐弱
  - 约 36 秒最后一个音；46 秒再轻轻弹一次开头的 A2 收尾

用法（在本目录或任意目录）：
  python make_d4_song.py
  # 一次渲出 -16（demo，保留）、-14、与 -13 三版 WAV，并更新 notes.json
"""

from __future__ import annotations

import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy import signal
from scipy.signal import fftconvolve, butter, sosfilt, resample_poly

# ---------------------------------------------------------------------------
# 基本参数（与 D4_代码歌_方案.md 一致）
# ---------------------------------------------------------------------------
SR = 48000
BPM = 60.0
BEAT = 60.0 / BPM  # 1.0 秒
DURATION = 52.0  # 成片时长（脚本：约 52 秒）
KEY = "A minor"
TIME_SIGNATURE = "4/4"

OUT_DIR = Path(__file__).resolve().parent
WAV_PATH = OUT_DIR / "D4_代码歌_demo.wav"
MP3_PATH = OUT_DIR / "D4_代码歌_demo.mp3"
NOTES_PATH = OUT_DIR / "notes.json"

TARGET_LUFS = -16.0
TRUE_PEAK_DBTP = -1.0

# 音色包络与混响（写进方案文档，改这里即可重渲）
PIANO_ATTACK = 0.012          # 秒，软槌，不要太“叮”
PIANO_RELEASE = 1.15          # 秒，踏板感
PIANO_DECAY_BASE = 2.15       # 越大衰减越快
# 按脚本第九节：单音钢琴感，不要煽情铺底。已去掉 Pad 层。
REVERB_RT60 = 2.6             # 秒，冬夜空间（脚本要求 2–3 秒尾音）
REVERB_PREDELAY = 0.028       # 秒
REVERB_MIX = 0.32             # 湿声比例
REVERB_DAMP_HZ = 5200         # 高频阻尼

# 关键时间码（与分镜锁定）
T_FIRST_NOTE = 0.00
T_SPARKLE = 9.60
T_BLIZZARD = 23.00
T_CUT_START = 24.80
T_CUT_END = 25.30
T_RETURN = 27.00
T_LAST_NOTE = 36.00
T_SOFT_E = 41.50
T_ENDING_A = 46.00

NOTE_FREQ = {
    "A1": 55.0000, "B1": 61.7354, "C2": 65.4064, "D2": 73.4162,
    "E2": 82.4069, "F2": 87.3071, "G2": 97.9989, "G#2": 103.8262,
    "A2": 110.0000, "B2": 123.4708, "C3": 130.8128, "D3": 146.8324,
    "E3": 164.8138, "F3": 174.6141, "G3": 195.9977, "G#3": 207.6523,
    "A3": 220.0000, "B3": 246.9417, "C4": 261.6256, "D4": 293.6648,
    "E4": 329.6276, "F4": 349.2282, "G4": 391.9954, "G#4": 415.3047,
    "A4": 440.0000, "B4": 493.8833, "C5": 523.2511, "D5": 587.3295,
    "E5": 659.2551, "F5": 698.4565, "G5": 783.9909, "A5": 880.0000,
    "C6": 1046.502, "E6": 1318.510,
}

CHORD_TONES = {
    "Am": ["A2", "E3", "A3", "C4"],
    "F":  ["F2", "C3", "F3", "A3"],
    "C":  ["C3", "G3", "C4", "E4"],
    "G":  ["G2", "D3", "G3", "B3"],
}

CHORD_ROMAN = {"Am": "i", "F": "VI", "C": "III", "G": "VII"}


def midi_of(name: str) -> int:
    """科学音名 -> MIDI。"""
    pc_map = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
              "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}
    if name[1] == "#":
        pc, octv = name[:2], int(name[2:])
    else:
        pc, octv = name[0], int(name[1:])
    return (octv + 1) * 12 + pc_map[pc]


def adsr(n: int, sr: int, attack: float, release: float,
         hold: float | None = None, peak: float = 1.0) -> np.ndarray:
    """简单的 attack–hold–release 包络，hold 默认吃掉剩余时长。"""
    env = np.zeros(n, dtype=np.float64)
    a = max(1, int(attack * sr))
    r = max(1, int(release * sr))
    if a + r >= n:
        a = max(1, n // 8)
        r = n - a
    h = n - a - r
    env[:a] = np.linspace(0.0, peak, a, endpoint=False)
    if h > 0:
        # 钢琴式指数衰减，不完全保持
        t = np.arange(h) / sr
        env[a:a + h] = peak * np.exp(-t * 0.85)
    t_r = np.arange(r) / sr
    start = env[a + h - 1] if a + h > 0 else peak
    env[a + h:] = start * np.exp(-t_r * (3.2 if release > 0 else 8.0))
    # 末尾收到 0，避免咔嗒
    env[-min(64, n):] *= np.linspace(1.0, 0.0, min(64, n))
    return env


def piano_tone(freq: float, duration: float, velocity: float, sr: int,
               is_bass: bool = False) -> np.ndarray:
    """加法合成的软钢琴：非谐分音 + 高频更快衰减 + 短槌击噪声。不用采样。"""
    tail = PIANO_RELEASE
    n = int(round((duration + tail) * sr))
    t = np.arange(n, dtype=np.float64) / sr
    # 高频琴弦非谐更明显
    B = 1.4e-4 if is_bass else 2.6e-4 * (freq / 440.0) ** 0.35
    n_partials = 16 if is_bass else 26
    sig = np.zeros(n, dtype=np.float64)
    p = 1.20 - 0.30 * velocity  # 力度越大越亮
    for k in range(1, n_partials + 1):
        fk = k * freq * math.sqrt(1.0 + B * k * k)
        if fk > sr * 0.47:
            break
        amp = (1.0 / (k ** p)) * math.exp(-0.035 * (k - 1))
        decay = (PIANO_DECAY_BASE + 0.32 * k)
        if is_bass:
            decay *= 0.55
        else:
            decay *= 0.70 + 0.30 * (440.0 / max(freq, 80.0)) ** 0.25
        env_k = np.exp(-t * decay)
        sig += amp * env_k * np.sin(2.0 * math.pi * fk * t)
        # 中高音的二、三弦微失谐，增加合唱感
        if k <= 8 and freq > 140:
            det = 1.0 + (0.00045 if k % 2 == 0 else -0.00035)
            sig += 0.16 * amp * env_k * np.sin(2.0 * math.pi * fk * det * t)
    # 软槌击：极短的带通噪声，不要做成金属“叮”
    rng = np.random.default_rng(int(freq * 10) + 7)
    noise = rng.standard_normal(n)
    sos = butter(2, [900, 4200], btype="band", fs=sr, output="sos")
    hammer = sosfilt(sos, noise) * np.exp(-t * 70.0) * (0.055 * velocity)
    sig = sig + hammer
    # 总体包络
    env = adsr(n, sr, PIANO_ATTACK + 0.006 * (1.0 - velocity), tail, peak=1.0)
    # 力度曲线略压缩，避免暴雪和弦炸响、弱音又听不见
    vel_gain = (0.22 + 0.78 * velocity) ** 1.15
    sig = sig * env * vel_gain
    # 轻柔饱和，让正弦分音更像琴槌而不是电子蜂鸣
    sig = np.tanh(sig * 1.25) / math.tanh(1.25)
    return sig.astype(np.float64)


def add_to(buf: np.ndarray, tone: np.ndarray, start: float, sr: int,
           pan: float = 0.0) -> None:
    """把单声道音色以 pan（-1 左，+1 右）叠加到立体声缓冲。"""
    i0 = int(round(start * sr))
    if i0 >= buf.shape[0]:
        return
    i1 = min(buf.shape[0], i0 + len(tone))
    sl = tone[: i1 - i0]
    left = sl * math.sqrt((1.0 - pan) * 0.5 + 0.5) * (1.0 if pan <= 0 else math.sqrt(1.0 - 0.5 * pan))
    # 等功率平移
    gL = math.sin((0.5 - 0.5 * pan) * math.pi / 2.0) * math.sqrt(2.0)
    gR = math.sin((0.5 + 0.5 * pan) * math.pi / 2.0) * math.sqrt(2.0)
    # 上面 sqrt2*sin 在 pan=0 时约为 1,1
    buf[i0:i1, 0] += sl * gL
    buf[i0:i1, 1] += sl * gR


def make_reverb_ir(sr: int, rt60: float, predelay: float, seed: int = 20261113):
    """指数衰减的滤波噪声 IR，左右略不同，模拟小板厅。"""
    length = rt60 * 1.6
    n = int(round(length * sr))
    pd = int(round(predelay * sr))
    rng = np.random.default_rng(seed)
    t = np.arange(max(1, n - pd), dtype=np.float64) / sr
    # -60 dB at rt60
    decay = np.exp(-t * (math.log(1000.0) / rt60))
    ir = np.zeros((n, 2), dtype=np.float64)
    for ch, damp, sd in ((0, REVERB_DAMP_HZ, seed + 1), (1, REVERB_DAMP_HZ * 0.92, seed + 2)):
        noise = np.random.default_rng(sd).standard_normal(n - pd)
        sos = butter(2, damp, btype="low", fs=sr, output="sos")
        wet = sosfilt(sos, noise) * decay
        ir[pd:, ch] = wet
        # 几条早期反射
        for delay, amp in ((0.019, 0.22), (0.027, 0.16), (0.041, 0.11), (0.053, 0.08)):
            d = int(round(delay * sr)) + pd
            if d < n:
                ir[d, ch] += amp * (0.7 if ch == 0 else 0.85)
    # 归一
    peak = np.max(np.abs(ir)) + 1e-12
    ir /= peak
    return ir


def apply_reverb(x: np.ndarray, ir: np.ndarray, mix: float) -> np.ndarray:
    left = fftconvolve(x[:, 0], ir[:, 0], mode="full")
    right = fftconvolve(x[:, 1], ir[:, 1], mode="full")
    n = x.shape[0]
    wet = np.stack([left[:n], right[:n]], axis=1)
    # 湿声能量不要压过干声
    dry_rms = np.sqrt(np.mean(x ** 2) + 1e-12)
    wet_rms = np.sqrt(np.mean(wet ** 2) + 1e-12)
    wet = wet * (dry_rms / wet_rms) * 0.85
    return (1.0 - mix) * x + mix * wet


# ---------------------------------------------------------------------------
# 曲谱：时间单位为秒（60 BPM 时 1 拍 = 1 秒）
# voice: melody / bass / harmony / FX（无 pad 铺底）
# ---------------------------------------------------------------------------
def build_score() -> tuple[list[dict], list[dict], list[dict]]:
    """返回 (notes, chords, markers)。"""
    notes: list[dict] = []
    chords: list[dict] = []
    markers: list[dict] = []

    def N(start, dur, pitch, vel, voice, chord, comment=""):
        notes.append({
            "start": round(float(start), 4),
            "duration": round(float(dur), 4),
            "pitch": pitch,
            "midi": midi_of(pitch),
            "freq": NOTE_FREQ[pitch],
            "velocity": round(float(vel), 4),
            "voice": voice,
            "chord": chord,
            "comment": comment,
        })

    def C(start, dur, name, section):
        chords.append({
            "start": round(float(start), 4),
            "duration": round(float(dur), 4),
            "name": name,
            "roman": CHORD_ROMAN[name],
            "section": section,
        })

    # ---- 第 1 镜 0–3s｜Am｜第一个低音 A，第一片雪 ----
    C(0.0, 3.0, "Am", "shot1_hook")
    N(0.00, 2.4, "A2", 0.58, "melody", "Am", "第一片雪；低音 A，长混响")
    N(2.00, 1.0, "E3", 0.36, "melody", "Am", "")

    # ---- 第 2 镜 3–8s｜F ----
    C(3.0, 5.0, "F", "shot2")
    N(3.00, 1.5, "A3", 0.48, "melody", "F", "")
    N(4.50, 0.5, "G3", 0.42, "melody", "F", "")
    N(5.00, 1.5, "F3", 0.46, "melody", "F", "")
    N(6.50, 0.5, "E3", 0.40, "melody", "F", "")
    N(7.00, 1.0, "C4", 0.44, "melody", "F", "导入 C 和弦")
    N(3.00, 4.0, "F2", 0.34, "bass", "F", "")
    for p in CHORD_TONES["F"][1:]:
        N(3.05, 4.8, p, 0.28, "harmony", "F", "")

    # ---- 第 3 镜 8–12s｜C｜高音 C5 给雪花闪光 ----
    C(8.0, 4.0, "C", "shot3_sparkle")
    N(8.00, 1.0, "E4", 0.50, "melody", "C", "")
    N(9.00, 0.6, "G4", 0.48, "melody", "C", "")
    N(9.60, 1.0, "C5", 0.62, "melody", "C", "雪花闪光高音")
    N(10.60, 0.5, "G4", 0.42, "melody", "C", "")
    N(11.10, 0.9, "E4", 0.40, "melody", "C", "")
    N(8.00, 4.0, "C3", 0.34, "bass", "C", "")
    for p in CHORD_TONES["C"][1:]:
        N(8.05, 3.8, p, 0.28, "harmony", "C", "")

    # ---- 第 4 镜 12–15s｜G｜下行，雪地显形 ----
    C(12.0, 3.0, "G", "shot4")
    N(12.00, 1.5, "D4", 0.46, "melody", "G", "")
    N(13.50, 0.5, "B3", 0.40, "melody", "G", "")
    N(14.00, 1.0, "G3", 0.38, "melody", "G", "")
    N(12.00, 3.0, "G2", 0.32, "bass", "G", "")
    for p in CHORD_TONES["G"][1:]:
        N(12.05, 2.8, p, 0.26, "harmony", "G", "")

    # ---- 第 5–6 镜 15–23s｜过程段，音乐自己收 quietly，不预做 -6 dB 闪避
    #     （闪避留给成片配音；本轨还要驱动落雪，不能整段压没） ----
    C(15.0, 4.0, "Am", "shot5_process")
    N(15.00, 2.0, "A3", 0.34, "melody", "Am", "过程段，弱")
    N(17.00, 1.0, "C4", 0.32, "melody", "Am", "")
    N(18.00, 1.0, "B3", 0.30, "melody", "Am", "")
    N(15.00, 4.0, "A2", 0.26, "bass", "Am", "")

    C(19.0, 4.0, "F", "shot6_process")
    N(19.00, 2.0, "A3", 0.32, "melody", "F", "")
    N(21.00, 2.0, "E3", 0.28, "melody", "F", "导入暴雪前的回落")
    N(19.00, 4.0, "F2", 0.24, "bass", "F", "")

    # ---- 第 7 镜 23–27s｜暴雪和弦 + 切断 0.5 秒 ----
    C(23.0, 1.8, "Am", "shot7_blizzard")
    blizzard = [
        ("A1", 0.70), ("A2", 0.78), ("E3", 0.66), ("F3", 0.40),
        ("A3", 0.72), ("C4", 0.70), ("E4", 0.68), ("G4", 0.45),
        ("A4", 0.64), ("C5", 0.60), ("E5", 0.55),
    ]
    for p, v in blizzard:
        N(23.00, 1.7, p, v, "FX", "Am", "暴雪和弦：音过多、过满")
    # 24.80–25.30 为硬切静音，由渲染时把缓冲清零实现
    # 25.30–27.00 保持静音（脚本不要铺底），给“×”留白
    C(25.30, 1.7, "Am", "shot7_after_cut")

    # ---- 第 8 镜 27–36s｜回到 Am，渐慢渐弱（ritardando 用拉长时值实现） ----
    C(27.0, 9.0, "Am", "shot8_ritard")
    N(27.00, 2.2, "A3", 0.38, "melody", "Am", "恢复，开始渐慢")
    N(29.30, 2.0, "F3", 0.34, "melody", "Am", "时值拉长")
    N(31.50, 2.1, "E3", 0.30, "melody", "Am", "")
    N(33.70, 2.1, "C3", 0.26, "melody", "Am", "")
    N(27.00, 4.0, "A2", 0.26, "bass", "Am", "")
    N(31.50, 4.4, "A2", 0.20, "bass", "Am", "")

    # ---- 第 9 镜 36s 起｜最后一个音 ----
    C(36.0, 10.0, "Am", "shot9_last")
    N(36.00, 3.2, "A2", 0.40, "melody", "Am", "最后一个音，与开头同音")
    # 1.5 秒完全留白之后（对应“地上留着的，就是这首歌”后的停顿），极轻高音 E
    N(41.50, 1.2, "E5", 0.12, "melody", "Am", "机器人抬头时的极轻高音 E，可按配音点微调")

    # ---- 第 10 镜 46–52s｜再弹一次开头的低音 A，然后静音 ----
    C(46.0, 6.0, "Am", "shot10_ending")
    N(46.00, 3.0, "A2", 0.28, "melody", "Am", "收尾：再轻轻弹一次开头的音")

    markers = [
        {"time": T_FIRST_NOTE, "name": "first_snowflake",
         "detail": "第 0 帧：低音 A2 落下，第一片雪落下，频谱带亮起"},
        {"time": T_SPARKLE, "name": "sparkle_high_note",
         "detail": "高音 C5，给第 3 镜“雪花闪一下”"},
        {"time": T_BLIZZARD, "name": "blizzard_chord",
         "detail": "过满的 Am 堆叠和弦，驱动满屏暴雪"},
        {"time": T_CUT_START, "name": "music_cut_start",
         "detail": "音乐硬切开始，持续 0.5 秒"},
        {"time": T_CUT_END, "name": "music_cut_end",
         "detail": "0.5 秒静音结束"},
        {"time": T_RETURN, "name": "music_return",
         "detail": "回到 Am，开始渐慢渐弱"},
        {"time": T_LAST_NOTE, "name": "last_note",
         "detail": "最后一个音 A2，之后混响自然衰减，雪停、定格"},
        {"time": T_SOFT_E, "name": "soft_high_E",
         "detail": "极轻高音 E5，给机器人抬头；若配音点改了，改 start 后重跑"},
        {"time": T_ENDING_A, "name": "ending_A",
         "detail": "收尾再弹一次开头的 A2，约 51 秒前应已静音"},
    ]
    return notes, chords, markers


def render(notes: list[dict], sr: int, duration: float) -> np.ndarray:
    # 多留 3 秒给混响，最后再裁到 duration
    n = int(round((duration + 3.0) * sr))
    buf = np.zeros((n, 2), dtype=np.float64)
    for ev in notes:
        freq = ev["freq"]
        vel = ev["velocity"]
        dur = ev["duration"]
        start = ev["start"]
        voice = ev["voice"]
        pitch = ev["pitch"]
        is_bass = ev["voice"] in ("bass",) or ev["midi"] <= 52
        tone = piano_tone(freq, dur, vel, sr, is_bass=is_bass)
        # 低音靠中，旋律略偏右，和声略偏左，像一架小钢琴
        if voice == "bass" or ev["midi"] <= 50:
            pan = 0.0
        elif voice == "melody":
            pan = 0.12 + 0.15 * ((ev["midi"] - 57) / 24.0)
            pan = max(-0.35, min(0.45, pan))
        elif voice == "FX":
            pan = float(np.clip((ev["midi"] - 57) / 30.0, -0.5, 0.5))
        else:
            pan = -0.18
        add_to(buf, tone, start, sr, pan=pan)
    # 硬切 0.5 秒：24.80–25.30 清零，边缘做 8ms 淡出/淡入，避免咔嗒
    fade = int(0.008 * sr)
    a = int(round(T_CUT_START * sr))
    b = int(round(T_CUT_END * sr))
    a = min(max(a, fade), n - fade)
    b = min(max(b, a + 1), n - fade)
    buf[a - fade:a] *= np.linspace(1.0, 0.0, fade)[:, None]
    buf[a:b] = 0.0
    buf[b:b + fade] *= np.linspace(0.0, 1.0, fade)[:, None]

    # 高通去 rumble，再轻混响
    sos_hp = butter(2, 35.0, btype="high", fs=sr, output="sos")
    buf[:, 0] = sosfilt(sos_hp, buf[:, 0])
    buf[:, 1] = sosfilt(sos_hp, buf[:, 1])
    ir = make_reverb_ir(sr, REVERB_RT60, REVERB_PREDELAY)
    buf = apply_reverb(buf, ir, REVERB_MIX)
    # 切断区间在混响后还可能有尾音，再清一次，保证“突然安静”
    buf[a:b] = 0.0
    buf[a - fade:a] *= np.linspace(1.0, 0.0, fade)[:, None]

    # 裁到目标时长，结尾 0.4 秒淡出，保证 51–52 秒全黑时已经静音
    n_out = int(round(duration * sr))
    buf = buf[:n_out]
    fade_end = int(0.40 * sr)
    buf[-fade_end:] *= np.linspace(1.0, 0.0, fade_end)[:, None]
    return buf


def measure_lufs_ffmpeg(path: Path) -> dict:
    """用 ffmpeg ebur128 测集成响度和真峰。只读 Summary 块，避免被逐帧行干扰。"""
    proc = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path),
         "-af", "ebur128=peak=true", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    err = proc.stderr
    i_lufs = tp = lra = None
    idx = err.rfind("Summary:")
    block = err[idx:] if idx >= 0 else err
    for line in block.splitlines():
        s = line.strip()
        try:
            if s.startswith("I:"):
                i_lufs = float(s.split("I:")[1].split("LUFS")[0].strip())
            elif s.startswith("LRA:"):
                lra = float(s.split("LRA:")[1].split("LU")[0].strip())
            elif s.startswith("Peak:"):
                # ffmpeg 在 Summary 里把真峰写成 "Peak:  -1.0 dBFS"
                num = s.split("Peak:")[1].replace("dBTP", "").replace("dBFS", "").strip()
                tp = float(num)
        except ValueError:
            pass
    return {"lufs": i_lufs, "true_peak": tp, "lra": lra, "raw": err[-2500:]}


def true_peak(y: np.ndarray, sr: int) -> float:
    up = resample_poly(y, 4, 1, axis=0)
    peak = float(np.max(np.abs(up)))
    if peak <= 0:
        return -99.0
    return 20.0 * math.log10(peak)


def soft_limit(y: np.ndarray, ceiling_db: float = TRUE_PEAK_DBTP) -> np.ndarray:
    """软限制：只压过热的峰值（暴雪和弦），不把整轨按峰值成比例缩小。"""
    ceil = 10 ** (ceiling_db / 20.0)
    return ceil * np.tanh(y / ceil)


def normalize(y: np.ndarray, sr: int, tmp: Path, target_lufs: float = TARGET_LUFS) -> tuple[np.ndarray, dict]:
    """先软限制峰值，再按 ffmpeg 实测 LUFS 精调到目标，必要时再限一次真峰（≤ -1 dBTP）。"""
    # 切勿在峰值 6+ 时直接 write+clip 再去测 LUFS，那会把暴雪削成方波、读数虚高。
    y = soft_limit(y, TRUE_PEAK_DBTP)
    write_wav(tmp, y, sr)
    m = measure_lufs_ffmpeg(tmp)
    if m["lufs"] is None:
        rms = float(np.sqrt(np.mean(y ** 2)) + 1e-12)
        gain = (10 ** (target_lufs / 20.0)) / rms * 0.15
    else:
        gain = 10 ** ((target_lufs - m["lufs"]) / 20.0)
    y = y * gain
    tp = true_peak(y, sr)
    if tp > TRUE_PEAK_DBTP:
        # 先软限，再若仍超则做很小的整体回退
        y = soft_limit(y, TRUE_PEAK_DBTP)
        tp2 = true_peak(y, sr)
        if tp2 > TRUE_PEAK_DBTP:
            y = y * (10 ** ((TRUE_PEAK_DBTP - tp2) / 20.0))
    write_wav(tmp, y, sr)
    m2 = measure_lufs_ffmpeg(tmp)
    m2["pre_lufs"] = m.get("lufs")
    m2["gain_db"] = 20.0 * math.log10(abs(gain) + 1e-12)
    m2["true_peak_lib"] = true_peak(y, sr)
    return y, m2


def write_wav(path: Path, y: np.ndarray, sr: int) -> None:
    """48 kHz 立体声 24-bit PCM。不依赖 soundfile 写，直接用标准库 + 手动打包也可，这里用 scipy。"""
    from scipy.io import wavfile
    y = np.clip(y, -1.0, 1.0)
    pcm = (y * (2 ** 23 - 1)).astype(np.int32)
    # scipy wavfile 对 int32 按 32-bit 写；改用 16-bit 不够，用 ffmpeg 转 24-bit
    # 先写 float64 wav 再让 ffmpeg 转。
    # 为简单与兼容：写 int16 会损失，改用 soundfile（venv 已装）。
    try:
        import soundfile as sf
        sf.write(str(path), y, sr, subtype="PCM_24")
    except Exception:
        wavfile.write(str(path), sr, np.clip(y, -1, 1).astype(np.float32))


def write_mp3(wav: Path, mp3: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
         "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "192k",
         "-ar", "48000", "-ac", "2", str(mp3)],
        check=True,
    )


def write_notes(path: Path, notes, chords, markers, extra: dict) -> None:
    payload = {
        "title": "D4 代码歌",
        "account": "AI造点真东西",
        "license": "自有作品，由本脚本纯合成，可商用，不强制署名。未使用采样或第三方音色库。",
        "key": KEY,
        "mode": "natural minor (Aeolian); 暴雪和弦带少量 F/G 外音",
        "bpm": BPM,
        "time_signature": TIME_SIGNATURE,
        "beat_duration_sec": BEAT,
        "duration_sec": DURATION,
        "sample_rate": SR,
        "target_lufs": TARGET_LUFS,
        "loudness_versions": [-16.0, -14.0, -13.0],
        "true_peak_limit_dbtp": TRUE_PEAK_DBTP,
        "envelope": {
            "piano_attack_sec": PIANO_ATTACK,
            "piano_release_sec": PIANO_RELEASE,
            "piano_decay_base": PIANO_DECAY_BASE,
            "pad": "disabled; 脚本第九节要求单音钢琴感、不要煽情铺底",
        },
        "reverb": {
            "rt60_sec": REVERB_RT60,
            "predelay_sec": REVERB_PREDELAY,
            "mix": REVERB_MIX,
            "damp_hz": REVERB_DAMP_HZ,
        },
        "visualization": {
            "first_snowflake_time_sec": T_FIRST_NOTE,
            "first_snowflake_pitch": "A2",
            "snow_amount": "由低频能量 / 低音与和弦力度驱动",
            "sparkle": "由高频能量驱动；刻意高音在 9.60s 的 C5",
            "blizzard_time_sec": T_BLIZZARD,
            "music_cut": [T_CUT_START, T_CUT_END],
            "last_note_time_sec": T_LAST_NOTE,
            "ending_note_time_sec": T_ENDING_A,
        },
        "markers": markers,
        "chords": chords,
        "notes": notes,
        "verify": extra,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def export_version(y_raw: np.ndarray, sr: int, tmp: Path, target_lufs: float, wav_path: Path, mp3_path: Path | None = None) -> dict:
    """把同一条干混校准到指定 LUFS，写出 WAV（可选 MP3），返回核对数据。"""
    y, loud = normalize(y_raw, sr, tmp, target_lufs=target_lufs)
    write_wav(wav_path, y, sr)
    if mp3_path is not None:
        write_mp3(wav_path, mp3_path)
    probe = subprocess.check_output(
        ["ffprobe", "-hide_banner", "-show_entries",
         "format=duration,sample_rate:stream=sample_rate,channels,codec_name,bits_per_raw_sample",
         "-of", "json", str(wav_path)],
        text=True,
    )
    final = measure_lufs_ffmpeg(wav_path)
    peak = float(np.max(np.abs(y)))
    n_clip = int(np.sum(np.abs(y) >= 0.999))
    info = {
        "wav": str(wav_path),
        "mp3": str(mp3_path) if mp3_path else None,
        "ffprobe": json.loads(probe),
        "loudness": {
            "integrated_lufs": final.get("lufs"),
            "lra": final.get("lra"),
            "true_peak_dbtp": final.get("true_peak"),
            "true_peak_oversampled": loud.get("true_peak_lib"),
            "target_lufs": target_lufs,
        },
        "sample_peak": peak,
        "clip_samples": n_clip,
    }
    print(f"Wrote {wav_path}")
    if mp3_path:
        print(f"Wrote {mp3_path}")
    print(f"  duration={info['ffprobe'].get('format', {}).get('duration')}  "
          f"I={final.get('lufs')} LUFS  LRA={final.get('lra')}  "
          f"TP={final.get('true_peak')} dBTP  peak={peak:.4f}  clip={n_clip}")
    if final.get("true_peak") is not None and final["true_peak"] > TRUE_PEAK_DBTP + 0.05:
        print(f"  WARNING: true peak {final['true_peak']} exceeds {TRUE_PEAK_DBTP} dBTP")
    return info


def main() -> int:
    notes, chords, markers = build_score()
    # 保险：曲谱里不应再出现 pad
    n_pad = sum(1 for ev in notes if ev["voice"] == "pad")
    if n_pad:
        raise SystemExit(f"score still contains {n_pad} pad events")
    print(f"Rendering {len(notes)} events, {DURATION}s @ {SR} Hz, {BPM} BPM, {KEY} ...")
    y_raw = render(notes, SR, DURATION)
    peak = float(np.max(np.abs(y_raw)))
    print(f"  raw peak = {peak:.4f} ({20*math.log10(peak+1e-12):.2f} dBFS)")
    tmp = OUT_DIR / "_d4_tmp_loudness.wav"

    # -16 版保留原文件名；另出 -14、-13 供脚本第九节试听定稿
    versions = [
        (-16.0, WAV_PATH, MP3_PATH),
        (-14.0, OUT_DIR / "D4_代码歌_-14LUFS.wav", None),
        (-13.0, OUT_DIR / "D4_代码歌_-13LUFS.wav", None),
    ]
    results = {}
    for target, wav_path, mp3_path in versions:
        # normalize 内部会 soft_limit，必须从同一条未限幅的干混复制
        results[target] = export_version(y_raw.copy(), SR, tmp, target, wav_path, mp3_path)

    extra = {
        "versions": {str(k): v for k, v in results.items()},
        "wav": str(WAV_PATH),
        "mp3": str(MP3_PATH),
        "ffprobe": results[-16.0]["ffprobe"],
        "loudness": results[-16.0]["loudness"],
    }
    write_notes(NOTES_PATH, notes, chords, markers, extra)
    if tmp.exists():
        tmp.unlink()
    print(f"Wrote {NOTES_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
