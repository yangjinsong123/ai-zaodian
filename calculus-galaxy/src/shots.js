// 镜头时间线：shots JSON → 给定全局时间 t 的相机 / 布局 / 卡片 / 叠层状态（纯函数，逐帧步进可复现）。
import * as THREE from 'three';
const E = { linear: x => x, in: x => x * x * x, out: x => 1 - Math.pow(1 - x, 3), inOut: x => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2,
  expoOut: x => x >= 1 ? 1 : 1 - Math.pow(2, -9 * x), sine: x => -(Math.cos(Math.PI * x) - 1) / 2 };
export const ease = (n, x) => (E[n] || E.inOut)(Math.min(1, Math.max(0, x)));
const lerp = (a, b, k) => a + (b - a) * k;
export const P = (sm, spec) => { if (typeof spec === 'string' || (Array.isArray(spec) && typeof spec[0] === 'number')) return sm.anchor(spec);
  return sm.anchor(spec[0]).add(new THREE.Vector3(...(spec[1] || [0, 0, 0]))); }; // [anchor, [dx,dy,dz]]
const range = (v, k) => Array.isArray(v) ? lerp(v[0], v[1], k) : v;
// keys: [{t, ...数值}]，按时间平滑插值
function keyAt(keys, t, f) { if (t <= keys[0].t) return keys[0]; for (let i = 0; i < keys.length - 1; i++) { const a = keys[i], b = keys[i + 1];
  if (t <= b.t) { const k = ease(b.ease || 'inOut', (t - a.t) / (b.t - a.t)); const o = { t }; for (const q of f) o[q] = Array.isArray(a[q]) ? a[q] : (typeof a[q] === 'number' ? lerp(a[q], b[q] ?? a[q], k) : a[q]); o._k = k; o._a = a; o._b = b; return o; } }
  return keys[keys.length - 1]; }

export class Timeline {
  constructor(sm, shots) { this.sm = sm; this.root = shots; this.s = shots.shots; this.fps = shots.fps || 30; this.duration = shots.duration || this.s[this.s.length - 1].t1; this.subs = shots.subs || []; }
  shotAt(t) { let s = this.s[0]; for (const x of this.s) if (t >= x.t0) s = x; return s; }
  apply(t) {
    const sm = this.sm, cam = sm.camera, s = this.shotAt(t), u = (t - s.t0) / (s.t1 - s.t0), k = ease(s.ease, u);
    // 1) 布局（翻车 / 散开）：过渡按“帧号 × 每帧步数”推进
    const L = s.layout ?? this.root.layout ?? 'normal';
    if (typeof L === 'object') sm.setLayout({ from: L.from, to: L.to, steps: (t < L.t0 - 1e-6 ? 0 : Math.floor((t - L.t0) * this.fps + 1e-6) + 1) * (L.spf || 2)  /* t0 那一帧就已经推进 spf 步：散开正好落在 t0 */ });
    else sm.setLayout(L);
    sm.update0 = true; if (sm._dirty) sm._syncGeometry();
    // 2) 相机
    let up = new THREE.Vector3(0, 1, 0);
    if (s.orbit) { const o = s.orbit, c = P(sm, o.center), a = range(o.a, k), rad = range(o.r, k), h = range(o.h ?? 0, k);
      cam.up.copy(up); cam.position.set(c.x + Math.sin(a) * rad, c.y + h, c.z + Math.cos(a) * rad); cam.lookAt(o.look ? P(sm, o.look) : c); }
    else if (s.path) { const pts = s.path.map(q => P(sm, q)), curve = new THREE.CatmullRomCurve3(pts, false, 'centripetal');
      const kk = Math.min(0.999, k); cam.up.copy(up); cam.position.copy(curve.getPointAt(kk));
      const la = s.lookAhead || 0.08, ahead = s.look ? P(sm, s.look) : curve.getPointAt(Math.min(1, kk + la));
      if (s.lookEnd && !s.look) { const w = Math.min(1, Math.max(0, (kk - (1 - 2.5 * la)) / (2.5 * la))); ahead.lerp(P(sm, s.lookEnd), w * w * (3 - 2 * w)); }  // 路径末段视线渐渐转向终点星，避免看向空处
      cam.lookAt(ahead); }
    else if (s.ctl) { const q = keyAt(s.ctl, t, ['theta', 'phi', 'r', 'tx', 'ty', 'tz']); const tg = new THREE.Vector3(q.tx, q.ty, q.tz);
      if (s.ctlTarget) { const A = P(sm, s.ctlTarget[0]), B = P(sm, s.ctlTarget[1]); const kk = keyAt(s.ctl, t, ['w']).w ?? 0; tg.copy(A.lerp(B, kk)); }
      cam.up.copy(up); cam.position.set(tg.x + q.r * Math.sin(q.phi) * Math.sin(q.theta), tg.y + q.r * Math.cos(q.phi), tg.z + q.r * Math.sin(q.phi) * Math.cos(q.theta)); cam.lookAt(tg); }
    else { cam.up.copy(up); cam.position.lerpVectors(P(sm, s.from), P(sm, s.to || s.from), k); cam.lookAt(new THREE.Vector3().lerpVectors(P(sm, s.lookFrom), P(sm, s.lookTo || s.lookFrom), ease(s.lookEase || s.ease, u))); }
    if (s.roll) cam.rotateZ(range(s.roll, k) * Math.PI / 180);
    if (s.shake) { const a = s.shake * Math.max(0, 1 - (t - s.t0) / 1.2); cam.rotateZ(Math.sin(t * 61) * a * 0.004); cam.rotateX(Math.sin(t * 47) * a * 0.003); }
    const fov = s.fov || 60, punch = s.punch ?? 8;
    cam.fov = range(fov, k) + punch * (1 - ease('out', (t - s.t0) / 0.32)); cam.updateProjectionMatrix(); cam.updateMatrixWorld();
    // 3) 其他视觉参数
    sm.warpAmt = s.warp != null ? range(s.warp, k) : 0;
    sm.dustAmt = s.dust != null ? range(s.dust, k) : 0;
    // 星团亮起：glowIn = [开始秒, 时长]，从 0.35 亮到 1.3 再回落到 1
    if (s.glowIn) { const u = Math.max(0, Math.min(1, (t - s.glowIn[0]) / s.glowIn[1])), v = Math.max(0, Math.min(1, (t - s.glowIn[0] - s.glowIn[1]) / 0.4));
      sm.chGlow = 0.35 + 0.95 * ease('out', u) - 0.3 * ease('inOut', v); } else sm.chGlow = 1;
    sm.labelFar = s.labelFar ?? null; sm.declutter = s.declutter ?? true; sm.lineOpacity = s.lineOpacity ?? null;
    sm.hardAmt = s.hard ? ease('out', (t - (s.hard.t ?? s.t0)) / 0.4) * (s.hard.until != null ? 1 - ease('in', (t - s.hard.until) / 0.3) : 1) : 0;
    // 4) 卡片（取最近一次已点击的）
    let card = null; for (const c of (s.cards || [])) if (t >= c.tap) card = { id: c.id, tap: t - c.tap, open: t - c.open, close: c.close != null ? t - c.close : -1 };
    return { shot: s, card, u };
  }
  subAt(t) { return this.subs.find(x => t >= x.a && t < x.b) || null; }
}
export { keyAt };
