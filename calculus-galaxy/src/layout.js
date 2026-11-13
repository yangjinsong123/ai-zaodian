// 两层力导向布局（纯 JS，不依赖 three，可在 node 里单测）。
// 固定步长 + 固定步数 + 固定种子 → 每次结果完全一样，录制时可按“帧号 × 每帧步数”确定性推进。
//   第 1 层：章节质心之间互相排斥（把 5 个星团拉开），有依赖的章节之间有弱弹簧
//   第 2 层：团内节点互相排斥 + 向本章质心聚拢 + 依赖连线弹簧
// 关键参数 repulsion：太小 → 全部挤成一团、标签叠在一起（翻车状态，见 PRESETS.low）。
export const PRESETS = {
  normal: { repulsion: 60 },
  low: { repulsion: 0.06 },  // 翻车复现：排斥力只有正常的 1/1000
};
export const DEFAULTS = { repulsion: 60, chapterRepulsion: 45, cohesion: 0.06, linkK: 0.08, linkLen: 7, crossK: 0.012, crossLen: 30,
  gravity: [0.0034, 0.0010, 0.0052],   // x / y / z 方向的向心力；y 最弱 → 竖屏方向拉长
  damping: 0.82, dt: 1, maxForce: 4, steps: 600, seed: 20261114, initRadius: 2.5 };

// 数据规范化：points[].pre 写前置知识点的名称（或 id）；也兼容顶层 links:[{from,to}]
export function normalize(data) {
  const pts = data.points.map(p => ({ ...p, id: p.id || p.title }));
  const byKey = {}; pts.forEach(p => { byKey[p.id] = p.id; byKey[p.title] = p.id; });
  const links = [];
  pts.forEach(p => (p.pre || []).forEach(q => { if (!(q in byKey)) (typeof console !== 'undefined') && console.warn('未知前置', q, '←', p.title); else links.push({ from: byKey[q], to: p.id }); }));
  (data.links || []).forEach(l => { if (l.from in byKey && l.to in byKey) links.push({ from: byKey[l.from], to: byKey[l.to] }); });
  return { ...data, points: pts, links };
}


function rng(seed) { return () => { seed |= 0; seed = seed + 0x6D2B79F5 | 0; let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
  t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t; return ((t ^ t >>> 14) >>> 0) / 4294967296; }; }

export class ForceLayout {
  constructor(data, params = {}) {
    if (!data.links || data.points.some(p => !p.id)) data = normalize(data);
    this.p = { ...DEFAULTS, ...params };
    this.chIds = data.chapters.map(c => c.id); const chIdx = Object.fromEntries(this.chIds.map((c, i) => [c, i]));
    this.nodes = data.points.map(p => ({ id: p.id, ch: chIdx[p.chapter], fixed: p.pos || null }));
    this.idx = Object.fromEntries(this.nodes.map((n, i) => [n.id, i]));
    this.links = data.links.filter(l => l.from in this.idx && l.to in this.idx).map(l => [this.idx[l.from], this.idx[l.to]]);
    this.nCh = this.chIds.length; this.reset();
  }
  reset() { // 所有节点从原点附近出发（每章一个很小的初始偏移，避免完全对称）
    const R = rng(this.p.seed), n = this.nodes.length;
    this.x = new Float64Array(n * 3); this.v = new Float64Array(n * 3); this.stepCount = 0;
    this.nodes.forEach((nd, i) => { const a = nd.ch / this.nCh * Math.PI * 2;
      const r = this.p.initRadius;
      this.x[i * 3] = Math.cos(a) * r * 0.5 + (R() - .5) * r; this.x[i * 3 + 1] = Math.sin(a) * r + (R() - .5) * r; this.x[i * 3 + 2] = (R() - .5) * r; });
  }
  set(params) { Object.assign(this.p, params); }
  centroids() { const c = new Float64Array(this.nCh * 3), m = new Float64Array(this.nCh);
    this.nodes.forEach((nd, i) => { for (let k = 0; k < 3; k++) c[nd.ch * 3 + k] += this.x[i * 3 + k]; m[nd.ch]++; });
    for (let j = 0; j < this.nCh; j++) for (let k = 0; k < 3; k++) c[j * 3 + k] /= m[j] || 1; return c; }
  step(count = 1) {
    const P = this.p, X = this.x, V = this.v, n = this.nodes.length, F = new Float64Array(n * 3);
    for (let s = 0; s < count; s++) {
      F.fill(0); const C = this.centroids();
      // 节点两两排斥
      for (let i = 0; i < n; i++) for (let j = i + 1; j < n; j++) {
        const dx = X[i * 3] - X[j * 3], dy = X[i * 3 + 1] - X[j * 3 + 1], dz = X[i * 3 + 2] - X[j * 3 + 2], d2 = dx * dx + dy * dy + dz * dz + 0.25, d = Math.sqrt(d2);
        const w = this.nodes[i].ch === this.nodes[j].ch ? 1 : 0.5, f = P.repulsion * w / d2 / d;
        F[i * 3] += dx * f; F[i * 3 + 1] += dy * f; F[i * 3 + 2] += dz * f; F[j * 3] -= dx * f; F[j * 3 + 1] -= dy * f; F[j * 3 + 2] -= dz * f; }
      // 章节质心互相排斥（作用到该章每个节点上），强度同样乘 repulsion
      const CF = new Float64Array(this.nCh * 3);
      for (let a = 0; a < this.nCh; a++) for (let b = a + 1; b < this.nCh; b++) {
        const dx = C[a * 3] - C[b * 3], dy = C[a * 3 + 1] - C[b * 3 + 1], dz = C[a * 3 + 2] - C[b * 3 + 2], d2 = dx * dx + dy * dy + dz * dz + 1, d = Math.sqrt(d2);
        const f = P.repulsion * P.chapterRepulsion / d2 / d;
        CF[a * 3] += dx * f; CF[a * 3 + 1] += dy * f; CF[a * 3 + 2] += dz * f; CF[b * 3] -= dx * f; CF[b * 3 + 1] -= dy * f; CF[b * 3 + 2] -= dz * f; }
      // 依赖弹簧
      for (const [i, j] of this.links) {
        const same = this.nodes[i].ch === this.nodes[j].ch, k = same ? P.linkK : P.crossK, L = same ? P.linkLen : P.crossLen;
        const dx = X[j * 3] - X[i * 3], dy = X[j * 3 + 1] - X[i * 3 + 1], dz = X[j * 3 + 2] - X[i * 3 + 2], d = Math.sqrt(dx * dx + dy * dy + dz * dz) + 1e-9, f = k * (d - L) / d;
        F[i * 3] += dx * f; F[i * 3 + 1] += dy * f; F[i * 3 + 2] += dz * f; F[j * 3] -= dx * f; F[j * 3 + 1] -= dy * f; F[j * 3 + 2] -= dz * f; }
      for (let i = 0; i < n; i++) {
        const ch = this.nodes[i].ch;
        for (let k = 0; k < 3; k++) {
          let f = F[i * 3 + k] + CF[ch * 3 + k] + P.cohesion * (C[ch * 3 + k] - X[i * 3 + k]) - P.gravity[k] * X[i * 3 + k];
          f = Math.max(-P.maxForce, Math.min(P.maxForce, f));
          V[i * 3 + k] = (V[i * 3 + k] + f * P.dt) * P.damping; X[i * 3 + k] += V[i * 3 + k] * P.dt; }
        if (this.nodes[i].fixed) for (let k = 0; k < 3; k++) { X[i * 3 + k] = this.nodes[i].fixed[k]; V[i * 3 + k] = 0; }
      }
      this.stepCount++;
    }
    return this;
  }
  run(steps = this.p.steps) { return this.step(steps); }
  pos(i) { return [this.x[i * 3], this.x[i * 3 + 1], this.x[i * 3 + 2]]; }
  stats() { // 用于自检：包围盒、最小节点间距
    const n = this.nodes.length; let mn = [1e9, 1e9, 1e9], mx = [-1e9, -1e9, -1e9], md = 1e9;
    for (let i = 0; i < n; i++) { for (let k = 0; k < 3; k++) { mn[k] = Math.min(mn[k], this.x[i * 3 + k]); mx[k] = Math.max(mx[k], this.x[i * 3 + k]); }
      for (let j = i + 1; j < n; j++) { const d = Math.hypot(this.x[i * 3] - this.x[j * 3], this.x[i * 3 + 1] - this.x[j * 3 + 1], this.x[i * 3 + 2] - this.x[j * 3 + 2]); md = Math.min(md, d); } }
    return { size: mx.map((v, k) => +(v - mn[k]).toFixed(1)), minDist: +md.toFixed(2), steps: this.stepCount };
  }
}
