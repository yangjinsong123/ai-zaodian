"""逐帧步进录制：固定时间步 t = i / fps 调 renderAt(t) → 截图 → 叠底部字幕 → ffmpeg 合成 mp4。
不依赖实时时钟，所以 SwiftShader 再慢也不会掉帧/变速。

用法（在 app/ 目录下）：
  python tools/record.py --out ../work/demo.mp4                     # 录整段
  python tools/record.py --stills 1.0,3.0,7.8 --still-dir ../work   # 只出几张截帧
可选：--shots demo/shots_demo.json --data data/knowledge.json --repulsion low --no-declutter --fps 30 --no-bloom --no-subs --frames-dir DIR --raw
需要：playwright（Python）、Chrome/Chromium、ffmpeg、Pillow；先在 app/ 里 npm install。"""
import argparse, functools, http.server, json, os, shutil, socketserver, subprocess, sys, threading, time
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFont

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ap = argparse.ArgumentParser()
ap.add_argument("--shots", default="demo/shots_demo.json"); ap.add_argument("--data", default="data/knowledge.json")
ap.add_argument("--repulsion", default=""); ap.add_argument("--no-declutter", action="store_true"); ap.add_argument("--raw", action="store_true", help="只存原始帧，不叠字幕、不合成 mp4")
ap.add_argument("--out", default="../work/demo.mp4"); ap.add_argument("--fps", type=int, default=0)
ap.add_argument("--stills", default=""); ap.add_argument("--still-dir", default="../work")
ap.add_argument("--frames-dir", default=""); ap.add_argument("--no-bloom", action="store_true"); ap.add_argument("--no-subs", action="store_true")
ap.add_argument("--frames", default="", help="只重渲这一段帧号，如 800-860（其余帧沿用 frames-dir 里已有的）")
ap.add_argument("--probe", default="", help="不截图，只逐帧调用 renderAt 把返回信息写进这个 json（用来查标签越界）")
ap.add_argument("--no-edgefade", action="store_true")
ap.add_argument("--chrome", default=os.environ.get("CHROME", shutil.which("google-chrome") or shutil.which("chromium") or ""))
A = ap.parse_args()
W, H, CSS_W, CSS_H = 1080, 1920, 540, 960   # 540x960 CSS 像素 @2x → 1080x1920
SHOTS = json.load(open(os.path.join(APP, A.shots), encoding="utf-8"))
FPS = A.fps or SHOTS.get("fps", 30); DUR = SHOTS["duration"]; N = round(DUR * FPS)

# ---- 底部一行字幕（沿用 D2 v2 模板：Noto Sans CJK SC Bold，白字黑描边，中心 y=1700）----
FONT = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
def F(s): return ImageFont.truetype(FONT, s, index=2)
_sc = {}
def sub_img(t):
    if t not in _sc:
        size = 78
        while F(size).getlength(t) > 1000: size -= 2
        f = F(size); st = 9; w = int(f.getlength(t)) + st * 2 + 20; h = int(size * 1.35) + st * 2
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0)); ImageDraw.Draw(im).text((st + 10, st), t, font=f, fill="white", stroke_width=st, stroke_fill="black")
        _sc[t] = im
    return _sc[t]
def overlay(png_path, t):
    im = Image.open(png_path).convert("RGBA")
    if im.size != (W, H): im = im.resize((W, H), Image.LANCZOS)
    if not A.no_subs:
        s = next((x for x in SHOTS.get("subs", []) if x["a"] <= t < x["b"]), None)
        if s: si = sub_img(s["text"]); im.alpha_composite(si, (int(540 - si.width / 2), int(1700 - si.height / 2)))
    return im.convert("RGB")

class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
srv = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Q, directory=APP)); PORT = srv.server_address[1]
threading.Thread(target=srv.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{PORT}/dev.html?mode=record&shots={A.shots}&data={A.data}" + ("&bloom=0" if A.no_bloom else "") + (f"&repulsion={A.repulsion}" if A.repulsion else "") + ("&declutter=0" if A.no_declutter else "") + ("&edgefade=0" if A.no_edgefade else "")

with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=A.chrome or None, args=["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    pg = b.new_page(viewport={"width": CSS_W, "height": CSS_H}, device_scale_factor=2)
    logs = []; pg.on("console", lambda m: logs.append(m.text)); pg.on("pageerror", lambda e: logs.append("PAGEERROR " + str(e)))
    pg.goto(URL); pg.evaluate("document.fonts.ready")
    try: pg.wait_for_function("window.__ready === true", timeout=60000)
    except Exception: print("\n".join(logs)); raise
    def shot_at(t, path):
        info = pg.evaluate(f"renderAt({t:.6f})"); pg.screenshot(path=path); return info
    if A.probe:
        res = []
        for i in range(N): res.append({"i": i, **pg.evaluate(f"renderAt({i / FPS:.6f})")})
        json.dump(res, open(A.probe, "w"), ensure_ascii=False); print("probe ->", A.probe, N); b.close(); sys.exit()
    if A.stills:
        os.makedirs(os.path.join(APP, A.still_dir), exist_ok=True)
        for v in A.stills.split(","):
            t = float(v); tmp = f"/tmp/_d5_{t}.png"; info = shot_at(t, tmp)
            out = os.path.join(APP, A.still_dir, f"still_{t:05.2f}s.png"); overlay(tmp, t).save(out); print(out, info)
        b.close(); sys.exit()
    fd = A.frames_dir or os.path.join(os.path.dirname(os.path.join(APP, A.out)), "frames"); os.makedirs(fd, exist_ok=True)
    t0 = time.time(); log = []
    rng = range(N)
    if A.frames:
        a_, b_ = map(int, A.frames.split("-")); rng = range(a_, min(b_, N - 1) + 1)
        try: log = [x for x in json.load(open(f"{fd}/frames.json")) if x["i"] not in rng]
        except Exception: log = []
    for i in rng:
        t = i / FPS; info = shot_at(t, f"{fd}/f_{i:04d}.png"); log.append({"i": i, "t": round(t, 4), **info})
        if i % 30 == 0: print(f"frame {i}/{N}  {time.time() - t0:.0f}s", flush=True)
    b.close()
log.sort(key=lambda x: x["i"]); json.dump(log, open(f"{fd}/frames.json", "w"), ensure_ascii=False)
if A.raw: print("raw frames ->", fd, N); sys.exit()
out = os.path.join(APP, A.out)
p = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                      "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-pix_fmt", "yuv420p", "-r", str(FPS), "-movflags", "+faststart", out], stdin=subprocess.PIPE)
for i in range(N): p.stdin.write(overlay(f"{fd}/f_{i:04d}.png", i / FPS).tobytes())
p.stdin.close(); p.wait(); print("wrote", out, N, "frames", f"{time.time() - t0:.0f}s")
if logs: print("console:", *logs[:20], sep="\n  ")
