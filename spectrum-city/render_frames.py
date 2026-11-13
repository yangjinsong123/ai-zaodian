"""离线逐帧渲染（不按时间截图）：无头 Chrome（SwiftShader 软件渲染也行）打开 city.html，一帧一帧调 renderFrame(i)，存 PNG 或直接用 ffmpeg 合成 mp4。
用法：
  python render_frames.py --data spectrum.json --out city.mp4 [--audio song.wav] [--mode proc|raw] [--start 0 --count 300] [--chrome /path/to/chrome]
  python render_frames.py --data spectrum.json --png frames/ --count 30
依赖：playwright（pip install playwright），ffmpeg（出 mp4 时）。Chrome 用 playwright 自带的 chromium 或 --chrome 指定。"""
import argparse, http.server, json, os, shutil, socketserver, subprocess, threading
from playwright.sync_api import sync_playwright
HERE = os.path.dirname(os.path.abspath(__file__))
ap = argparse.ArgumentParser(); ap.add_argument("--data", required=True); ap.add_argument("--mode", default="proc"); ap.add_argument("--out"); ap.add_argument("--png")
ap.add_argument("--audio"); ap.add_argument("--start", type=int, default=0); ap.add_argument("--count", type=int); ap.add_argument("--w", type=int, default=1080); ap.add_argument("--h", type=int, default=1920)
ap.add_argument("--chrome"); a = ap.parse_args()
data = os.path.abspath(a.data); meta = json.load(open(data)); fps, nfr = meta["fps"], meta["frames"]; n = a.count or (nfr - a.start)
shutil.copy(data, os.path.join(HERE, "_spectrum_tmp.json"))
class Q(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *x, **k): super().__init__(*x, directory=HERE, **k)
    def log_message(self, *x): pass
H = Q
httpd = socketserver.TCPServer(("127.0.0.1", 0), H); port = httpd.server_address[1]; threading.Thread(target=httpd.serve_forever, daemon=True).start()
args = ["--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]
with sync_playwright() as pw:
    br = pw.chromium.launch(executable_path=a.chrome, args=args) if a.chrome else pw.chromium.launch(args=args)
    pg = br.new_page(viewport={"width": a.w, "height": a.h})
    pg.goto(f"http://127.0.0.1:{port}/city.html?data=_spectrum_tmp.json&mode={a.mode}&w={a.w}&h={a.h}"); pg.wait_for_function("window.__ready === true", timeout=600000)
    print("楼高比例 HS =", pg.evaluate("window.HSCALE"))
    ff = None
    if a.out:
        ff = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-framerate", str(fps), "-i", "-", *(["-ss", f"{a.start / fps:.3f}", "-i", a.audio, "-shortest"] if a.audio else []),
                              "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", a.out], stdin=subprocess.PIPE)
    if a.png: os.makedirs(a.png, exist_ok=True)
    for i in range(a.start, a.start + n):
        info = pg.evaluate(f"window.renderFrame({i})"); png = pg.screenshot(type="png")
        if ff: ff.stdin.write(png)
        if a.png: open(os.path.join(a.png, f"frame_{i:05d}.png"), "wb").write(png)
        if (i - a.start) % 30 == 0: print(i, info, flush=True)
    br.close()
    if ff: ff.stdin.close(); ff.wait()
httpd.shutdown(); os.remove(os.path.join(HERE, "_spectrum_tmp.json")); print("done")
