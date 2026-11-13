// calculus-galaxy 引擎：knowledge.json → 3D 星团。所有动画都是时间 t 的纯函数，位置来自 layout.js 的确定性力导向。
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { CSS2DRenderer, CSS2DObject } from 'three/addons/renderers/CSS2DRenderer.js';
import { LineSegments2 } from 'three/addons/lines/LineSegments2.js';
import { LineSegmentsGeometry } from 'three/addons/lines/LineSegmentsGeometry.js';
import { LineMaterial } from 'three/addons/lines/LineMaterial.js';
import { ForceLayout, PRESETS, normalize } from './layout.js';
export { normalize };

export function rng(seed) { return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
  t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }
export const smooth = (a, b, x) => { const k = Math.min(1, Math.max(0, (x - a) / (b - a))); return k * k * (3 - 2 * k); };
const RED = new THREE.Color('#ff3b3b'), WHITE = new THREE.Color(1, 1, 1);

function glowTexture(stops) {
  const c = document.createElement('canvas'); c.width = c.height = 128; const g = c.getContext('2d');
  const gr = g.createRadialGradient(64, 64, 0, 64, 64, 64); stops.forEach(([o, a]) => gr.addColorStop(o, `rgba(255,255,255,${a})`));
  g.fillStyle = gr; g.fillRect(0, 0, 128, 128); const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

export class StarMap {
  constructor(container, rawData, opt = {}) {
    const data = this.data = normalize(rawData);
    this.opt = Object.assign({ bloom: true, seed: 20261114, pixelRatio: window.devicePixelRatio || 1, repulsion: 'normal', declutter: true }, opt);
    const W = container.clientWidth, H = container.clientHeight;
    const r = this.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    r.setPixelRatio(this.opt.pixelRatio); r.setSize(W, H); r.setClearColor(0x020a1f, 1); container.appendChild(r.domElement);
    this.scene = new THREE.Scene(); this.scene.background = new THREE.Color(0x041233); this.scene.fog = new THREE.FogExp2(0x020a1f, 0.0013);
    this.camera = new THREE.PerspectiveCamera(60, W / H, 0.1, 4000); this.camera.position.set(0, 0, 220); this.scene.add(this.camera);
    this.labels = new CSS2DRenderer(); this.labels.setSize(W, H); this.labels.domElement.className = 'lbl-layer'; container.appendChild(this.labels.domElement);
    if (this.opt.bloom) {
      this.composer = new EffectComposer(r); this.composer.setPixelRatio(this.opt.pixelRatio); this.composer.setSize(W, H);
      this.composer.addPass(new RenderPass(this.scene, this.camera));
      this.bloom = new UnrealBloomPass(new THREE.Vector2(W, H), 0.7, 0.35, 0.42); this.composer.addPass(this.bloom); this.composer.addPass(new OutputPass());
    }
    this.texCore = glowTexture([[0, 1], [0.12, 0.95], [0.28, 0.35], [0.6, 0.06], [1, 0]]);
    this.texSoft = glowTexture([[0, 0.7], [0.4, 0.22], [1, 0]]);
    this.focusId = null; this.focusAmt = 0; this.hardAmt = 0; this.labelFar = null; this.declutter = this.opt.declutter;
    // 力导向：两种参数各自确定性跑完 600 步并缓存；过渡状态按“步数”推进
    const rep = v => typeof v === 'number' ? { repulsion: v } : (PRESETS[v] || PRESETS.normal);
    this.layouts = {}; this.layoutFor = k => this.layouts[k] ||= new ForceLayout(data, rep(k)).run();
    this._init(); this.setLayout(this.opt.repulsion); this._build();
  }

  _init() {
    const d = this.data; this.ch = {}; this.pt = {};
    d.chapters.forEach((c, i) => { this.ch[c.id] = { ...c, idx: i, pos: new THREE.Vector3(), color: new THREE.Color(c.color), pts: [] }; });
    const R = rng(this.opt.seed);
    d.points.forEach((p, i) => { const c = this.ch[p.chapter]; const o = { ...p, i, ch: c, pos: new THREE.Vector3(), phase: R() * 6.28, nb: new Set(), deg: 0 }; c.pts.push(o); this.pt[p.id] = o; });
    this.links = d.links; this.links.forEach(l => { const a = this.pt[l.from], b = this.pt[l.to]; a.nb.add(b.id); b.nb.add(a.id); a.deg++; b.deg++; });
    Object.values(this.ch).forEach(c => c.radius = 6 + Math.sqrt(c.pts.length) * 3.2);
    this.center = new THREE.Vector3();
  }

  // spec: 'normal' | 'low' | 数字 | {from, to, steps}（from 状态跑完后，用 to 参数再推进 steps 步）
  setLayout(spec) {
    let L;
    if (typeof spec === 'object' && spec) {
      const key = JSON.stringify([spec.from, spec.to]);
      if (!this._tr || this._tr.key !== key || this._tr.L.stepCount - 600 > spec.steps) {
        const base = this.layoutFor(spec.from), T = new ForceLayout(this.data, typeof spec.to === 'number' ? { repulsion: spec.to } : PRESETS[spec.to]);
        T.x.set(base.x); T.v.set(base.v); T.stepCount = base.stepCount; this._tr = { key, L: T };
      }
      const T = this._tr.L; T.step(spec.steps - (T.stepCount - 600)); L = T;
    } else L = this.layoutFor(spec ?? 'normal');
    const sig = (typeof spec === 'object' ? JSON.stringify(spec) : String(spec));
    if (sig === this._layoutSig) return; this._layoutSig = sig; this.layoutState = L.stats();
    this.data.points.forEach((p, i) => this.pt[p.id].pos.set(...L.pos(L.idx[p.id])));
    Object.values(this.ch).forEach(c => { c.pos.set(0, 0, 0); c.pts.forEach(p => c.pos.add(p.pos)); c.pos.multiplyScalar(1 / c.pts.length); });
    this.center.set(0, 0, 0); Object.values(this.ch).forEach(c => this.center.add(c.pos)); this.center.multiplyScalar(1 / this.data.chapters.length);
    this._dirty = true;
  }

  _build() {
    const S = this.scene, R = rng(this.opt.seed + 7), pr = this.opt.pixelRatio;
    // 背景星空（深蓝底 + 远处几团暗星云）
    { const n = 7000, p = new Float32Array(n * 3), col = new Float32Array(n * 3);
      for (let i = 0; i < n; i++) { const v = new THREE.Vector3(R() - .5, R() - .5, R() - .5).normalize().multiplyScalar(260 + R() * 1100);
        p.set([v.x, v.y, v.z], i * 3); const w = R() < 0.06 ? 1 : 0.35 + R() * 0.4, tint = R(); col.set([w * (tint < .25 ? .75 : 1), w * .95, w * (tint > .8 ? .7 : 1)], i * 3); }
      const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(p, 3)); g.setAttribute('color', new THREE.BufferAttribute(col, 3));
      S.add(new THREE.Points(g, new THREE.PointsMaterial({ size: 1.3 * pr, sizeAttenuation: false, vertexColors: true, map: this.texCore, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }))); }
    ['#1e3a8a', '#312e81', '#0c4a6e', '#1e1b4b'].forEach((c, k) => { const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.texSoft, color: c, transparent: true, opacity: .3, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }));
      const a = k * 1.7 + .4; s.position.set(Math.cos(a) * 700, (k - 1.5) * 260, Math.sin(a) * 700 - 200); s.scale.setScalar(900); S.add(s); });
    // 前景尘埃：星图周围一片带透视的小颗粒，镜头一动就有前后视差（dust 参数控制亮度）
    { const n = 2600, p = new Float32Array(n * 3), c0 = this.center || new THREE.Vector3();
      for (let i = 0; i < n; i++) p.set([(R() - .5) * 520, (R() - .5) * 700, (R() - .5) * 760 + 120], i * 3);
      const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(p, 3));
      this.dust = new THREE.Points(g, new THREE.PointsMaterial({ size: 0.9, sizeAttenuation: true, color: 0xcfe3ff, map: this.texCore, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }));
      this.dust.frustumCulled = false; S.add(this.dust); }
    // 光速穿梭线（挂在相机上，warp 参数控制）
    { const n = 360, p = new Float32Array(n * 6); this.warpSeed = [];
      for (let i = 0; i < n; i++) { const a = R() * 6.28, rr = 6 + R() * 40; this.warpSeed.push([Math.cos(a) * rr, Math.sin(a) * rr * 1.6, R()]); }
      const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(p, 3));
      this.warp = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0xbfdbfe, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }));
      this.warp.frustumCulled = false; this.camera.add(this.warp); }
    // 章节：星云 + 星尘（放在跟随质心移动的 group 里）+ 标签
    Object.values(this.ch).forEach(c => {
      const g = new THREE.Group(); S.add(g); c.group = g; c.neb = [];
      for (let k = 0; k < 3; k++) { const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.texSoft, color: c.color, transparent: true, opacity: 0.13 + 0.04 * k, depthWrite: false, blending: THREE.AdditiveBlending }));
        s.position.set(R() - .5, R() - .5, R() - .5).multiplyScalar(c.radius * 0.6); s.scale.setScalar(c.radius * (3.2 + R() * 1.6)); s.userData.op = s.material.opacity; g.add(s); c.neb.push(s); }
      const n = 700, p = new Float32Array(n * 3);
      for (let i = 0; i < n; i++) { const v = new THREE.Vector3(R() - .5, R() - .5, R() - .5).normalize().multiplyScalar(Math.pow(R(), .7) * c.radius * 1.9); p.set([v.x, v.y, v.z], i * 3); }
      const pg = new THREE.BufferGeometry(); pg.setAttribute('position', new THREE.BufferAttribute(p, 3));
      c.dust = new THREE.Points(pg, new THREE.PointsMaterial({ size: 0.6, color: c.color, map: this.texCore, transparent: true, opacity: .8, depthWrite: false, blending: THREE.AdditiveBlending })); g.add(c.dust);
      const el = document.createElement('div'); el.className = 'chlabel'; el.innerHTML = `<b>${c.short || c.name}</b>${c.short && c.short !== c.name ? `<small>${c.name}</small>` : ''}`; el.style.color = c.color.getStyle();
      c.label = new CSS2DObject(el); c.label.center.set(0.5, 1); S.add(c.label); c.el = el;
    });
    // 知识点星：核心 + 光晕 + 名字；红光节点 hard=true
    Object.values(this.pt).forEach(p => {
      const coreCol = p.hard ? new THREE.Color('#ffd0d0') : WHITE.clone().lerp(p.ch.color, .25);
      p.core = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.texCore, color: coreCol, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
      p.halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.texSoft, color: p.hard ? RED : p.ch.color, transparent: true, opacity: .5, depthWrite: false, blending: THREE.AdditiveBlending }));
      p.base = p.hard ? 3.0 : 1.9 + 0.15 * Math.min(p.deg, 5); S.add(p.halo); S.add(p.core);
      const el = document.createElement('div'); el.className = 'slabel' + (p.hard ? ' hard' : ''); el.textContent = p.title;
      p.label = new CSS2DObject(el); p.label.center.set(0.5, -0.55); S.add(p.label); p.el = el;
    });
    // 依赖连线（粗线，像素线宽）+ 高亮线 + 流动光点（方向 = 先学 → 后学）
    this.lineMat = new LineMaterial({ vertexColors: true, linewidth: 2 * pr, transparent: true, opacity: .32, depthWrite: false, blending: THREE.AdditiveBlending });
    this.lines = new LineSegments2(new LineSegmentsGeometry(), this.lineMat); this.lines.frustumCulled = false; S.add(this.lines);
    this.hlMat = new LineMaterial({ color: 0xffffff, linewidth: 3.2 * pr, transparent: true, opacity: 0, depthWrite: false, blending: THREE.AdditiveBlending });
    this.hlLines = new LineSegments2(new LineSegmentsGeometry(), this.hlMat); this.hlLines.frustumCulled = false; S.add(this.hlLines);
    this.pulses = this.links.map(l => { const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: this.texCore, color: this.pt[l.to].ch.color.clone().lerp(WHITE, .5), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
      s.scale.setScalar(1.0); S.add(s); return { s, a: this.pt[l.from].pos, b: this.pt[l.to].pos, ph: R(), sp: 0.35 + R() * 0.25 }; });
    this.resize(this.renderer.domElement.clientWidth, this.renderer.domElement.clientHeight);
  }

  _syncGeometry() { // 布局变化后，把位置同步到所有物体
    Object.values(this.pt).forEach(p => { p.core.position.copy(p.pos); p.halo.position.copy(p.pos); p.label.position.copy(p.pos); });
    Object.values(this.ch).forEach(c => { c.group.position.copy(c.pos); let top = -1e9; c.pts.forEach(p => top = Math.max(top, p.pos.y)); c.label.position.set(c.pos.x, Math.max(top, c.pos.y) + 3.2, c.pos.z); });
    const pos = [], col = [];
    this.links.forEach(l => { const a = this.pt[l.from], b = this.pt[l.to]; pos.push(...a.pos.toArray(), ...b.pos.toArray());
      const ca = (a.hard ? RED : a.ch.color).clone().lerp(WHITE, .3), cb = (b.hard ? RED : b.ch.color).clone().lerp(WHITE, .3); col.push(ca.r, ca.g, ca.b, cb.r, cb.g, cb.b); });
    this.lines.geometry.dispose(); const g = new LineSegmentsGeometry(); g.setPositions(pos); g.setColors(col); this.lines.geometry = g;
    this._focusGeom(); this._dirty = false;
  }
  _focusGeom() { const id = this.focusId, pos = [];
    if (id) this.links.forEach(l => { if (l.from === id || l.to === id) pos.push(...this.pt[l.from].pos.toArray(), ...this.pt[l.to].pos.toArray()); });
    this.hlLines.geometry.dispose(); const g = new LineSegmentsGeometry(); if (pos.length) g.setPositions(pos); this.hlLines.geometry = g; this.hlLines.visible = pos.length > 0; }

  anchor(a) { // "origin" | "galaxy" | "ch:<id>" | "p:<id 或 名称>" | [x,y,z]
    if (Array.isArray(a)) return new THREE.Vector3(...a);
    if (!a || a === 'origin') return new THREE.Vector3();
    if (a === 'galaxy') return this.center.clone();
    const k = a.slice(0, a.indexOf(':')), id = a.slice(a.indexOf(':') + 1); const o = k === 'ch' ? this.ch[id] : this.pt[id];
    if (!o) throw new Error('unknown anchor ' + a); return o.pos.clone();
  }
  setFocus(id) { if (id === this.focusId) return; this.focusId = id; this._focusGeom(); }

  update(t) {
    if (this._dirty) this._syncGeometry();
    const cam = this.camera, h = this.focusAmt, f = this.focusId, hd = this.hardAmt, lf = this.labelFar;
    const W = this.renderer.domElement.clientWidth, H = this.renderer.domElement.clientHeight;
    const cands = [];
    Object.values(this.pt).forEach(p => {
      const d = cam.position.distanceTo(p.pos), near = smooth(2.5, 9, d);
      const tw = 1 + 0.12 * Math.sin(t * 2.3 + p.phase) + 0.05 * Math.sin(t * 7.1 + p.phase * 3);
      const isF = p.id === f, isN = f && p.nb.has(f), dim = f && !isF && !isN ? 1 - 0.7 * h : 1;
      const big = (isF ? 1 + 0.35 * h : isN ? 1 + 0.25 * h : 1) * (p.hard ? 1 + 0.45 * hd * (0.75 + 0.25 * Math.sin(t * 9)) : 1);
      const ss = Math.max(1, d * (p.hard ? 0.0145 : 0.0105) / p.base); // 远景时保证最小屏幕尺寸
      p.core.scale.setScalar(p.base * tw * big * ss); p.halo.scale.setScalar(p.base * (p.hard ? 4.2 : 3.2) * tw * big * Math.max(1, ss * 0.85));
      p.halo.material.opacity = (p.hard ? .75 : .45) * dim * near * (p.hard && hd ? 1 + .4 * hd : 1); p.core.material.opacity = dim * (0.3 + 0.7 * near);
      const far = lf ?? 52, nearF = lf ? lf * 0.7 : 34;
      let lo = 1 - smooth(nearF, far, d); if (f && h > 0) lo *= isF || isN ? 1 : 1 - .85 * h; if (isF) lo *= 1 - h;
      lo *= this.labelMul ?? 1; p.lo = lo; if (lo > 0.01) cands.push(p); else { p.el.style.opacity = 0; p.label.visible = false; }
    });
    // 标签避让：按优先级（聚焦 > 邻居 > 红光 > 连线多）贪心放置，和已放的框重叠就隐藏
    const placed = [];
    Object.values(this.ch).forEach(c => {
      const d = cam.position.distanceTo(c.pos); let o = smooth(c.radius * 1.1, c.radius * 2.4, d) * (1 - smooth(780, 950, d)); o *= (1 - .7 * h) * (this.labelMul ?? 1) * Math.min(1, this.chGlow ?? 1);
      c.el.style.opacity = o.toFixed(3); c.label.visible = o > 0.01;
      if (o > 0.3 && this.declutter) { const v = c.label.position.clone().project(cam); if (v.z < 1) { const x = (v.x + 1) / 2 * W, y = (1 - v.y) / 2 * H; placed.push([x - 45, y - 40, x + 45, y]); } }
    });
    const pri = p => (p.id === f ? 1e4 : 0) + (f && p.nb.has(f) ? 1e3 : 0) + (p.hard ? 100 : 0) + p.deg * 10 - p.i * 0.01;
    cands.sort((a, b) => pri(b) - pri(a)).forEach(p => {
      let show = true;
      if (this.declutter) { const v = p.pos.clone().project(cam); const x = (v.x + 1) / 2 * W, y = (1 - v.y) / 2 * H, w = p.title.length * 15 + 6;
        const r = [x - w / 2, y + 6, x + w / 2, y + 26]; show = v.z < 1 && !placed.some(q => r[0] < q[2] && r[2] > q[0] && r[1] < q[3] && r[3] > q[1]); if (show) placed.push(r); }
      p.el.style.opacity = show ? p.lo.toFixed(3) : 0; p.label.visible = show;
    });
    Object.values(this.ch).forEach(c => { const d = cam.position.distanceTo(c.pos); const nf = smooth(c.radius * 1.1, c.radius * 3.4, d); c.neb.forEach(s => s.material.opacity = s.userData.op * nf * (1 - .5 * h) * (this.chGlow ?? 1)); });
    this.pulses.forEach(q => { const u = (t * q.sp + q.ph) % 1; q.s.position.lerpVectors(q.a, q.b, u); q.s.material.opacity = Math.sin(Math.PI * u) * (1 - .6 * h); });
    this.lineMat.opacity = (this.lineOpacity ?? .32) * (1 - .65 * h); this.hlMat.opacity = .7 * h;
    // 光速线
    const wv = this.warpAmt || 0; this.warp.visible = wv > 0.01;
    if (this.warp.visible) { const a = this.warp.geometry.attributes.position.array, L = 4 + 26 * wv;
      this.warpSeed.forEach(([x, y, ph], i) => { const z = -(((ph + t * (1.6 + 2.4 * wv)) % 1) * 180) - 5; a.set([x, y, z, x, y, z - L], i * 6); });
      this.warp.geometry.attributes.position.needsUpdate = true; this.warp.material.opacity = .55 * wv; }
    if (this.center) this.dust.position.copy(this.center); this.dust.material.opacity = 0.55 * (this.dustAmt ?? 0.3); this.dust.visible = this.dust.material.opacity > 0.01;
    if (this.composer) this.composer.render(); else this.renderer.render(this.scene, cam);
    this.labels.render(this.scene, cam);
    this._edgeFade(W, H);
  }
  // 安全边距：标签离画面任一边不到 M（20 CSS 像素 = 成片 40 px）就完全隐藏，M 到 M+F 之间按距离淡入（镜头运动时不会贴边或被切）
  // edgeStats.bad 记录这一帧仍可见、却进了安全边距的标签（应当永远为空），录制时逐帧写进 frames.json 供检查
  _edgeFade(W, H) {
    const M = this.edgeMargin ?? 20, F = this.edgeFadeW ?? 12, bad = [], near = [];   // 1080 宽成片里 = 40 px 安全边距 + 24 px 淡入带
    const all = [...Object.values(this.pt), ...Object.values(this.ch)];
    for (const o of all) {
      if (!o.label.visible) continue; const base = +o.el.style.opacity; if (!(base > 0.01)) continue;
      const r = o.el.getBoundingClientRect(); if (r.width === 0) continue;
      const m = Math.min(r.left, W - r.right, r.top, H - r.bottom);
      if (m < M + F) near.push(o.title || o.name);
      const k = this.edgeFadeOn === false ? 1 : Math.max(0, Math.min(1, (m - M) / F)), op = base * k * k * (3 - 2 * k);
      o.el.style.opacity = op.toFixed(3); if (op <= 0.01) o.label.visible = false, o.el.style.opacity = 0;
      if (op > 0.02 && m < M) bad.push([o.title || o.name, Math.round(r.left), Math.round(r.right), Math.round(r.top), Math.round(r.bottom), +op.toFixed(2)]);   // 仍可见却进了安全边距
    }
    this.edgeStats = { near, bad };
  }

  screenOf(id) { const v = this.pt[id].pos.clone().project(this.camera); const el = this.renderer.domElement;
    return { x: (v.x + 1) / 2 * el.clientWidth, y: (1 - v.y) / 2 * el.clientHeight, z: v.z }; }
  screenOfVec(p) { const v = p.clone().project(this.camera); const el = this.renderer.domElement; return { x: (v.x + 1) / 2 * el.clientWidth, y: (1 - v.y) / 2 * el.clientHeight, z: v.z }; }
  pick(x, y) { let best = null, bd = 1e9; Object.values(this.pt).forEach(p => { const s = this.screenOf(p.id); if (s.z > 1) return; const dd = Math.hypot(s.x - x, s.y - y); if (dd < bd) { bd = dd; best = p.id; } });
    return bd < 30 ? best : null; }
  resize(W, H) { this.camera.aspect = W / H; this.camera.updateProjectionMatrix(); this.renderer.setSize(W, H); this.labels.setSize(W, H);
    if (this.composer) this.composer.setSize(W, H); const pr = this.opt.pixelRatio; [this.lineMat, this.hlMat].forEach(m => m.resolution.set(W * pr, H * pr)); }
}
