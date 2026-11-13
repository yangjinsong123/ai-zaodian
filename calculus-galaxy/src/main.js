// 入口。URL 参数：
//   ?data=data/knowledge.json   数据
//   &repulsion=low|normal|<数字> 力导向排斥参数（low = 翻车复现：挤成一团、标签叠在一起）
//   &declutter=0                关掉标签避让（第一版没有避让）
//   &bloom=0                    关发光（省性能）
//   &mode=record&shots=xxx.json 录制模式：不跑 requestAnimationFrame，外部逐帧调用 renderAt(t)
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { StarMap } from './starmap.js';
import { Timeline, ease, keyAt, P } from './shots.js';
import { Slides } from './slides.js';

(async () => {
const Q = new URLSearchParams(location.search);
const MODE = Q.get('mode') || 'interactive';
const $ = s => document.querySelector(s);
await document.fonts.load('900 40px "Noto Sans CJK SC"'); await document.fonts.load('700 20px "Noto Sans CJK SC"');
const DATA_URL = Q.get('data') || 'data/knowledge.json';
// 数据来源优先级：拖进页面的 JSON（sessionStorage）> fetch knowledge.json（用本地服务器打开时）> data/knowledge.js（直接双击 index.html 时）
let rawText = MODE === 'record' ? null : sessionStorage.getItem('cg-data');
if (!rawText && location.protocol !== 'file:') { try { const r = await fetch(DATA_URL); if (!r.ok) throw 0; rawText = await r.text(); } catch (e) { } }
if (!rawText) rawText = window.KNOWLEDGE_JSON;
if (!rawText) { document.body.innerHTML = '<p style="padding:20px">没读到 knowledge.json：请用本地服务器打开，或确认 data/knowledge.js 存在。</p>'; throw new Error('no data'); }
const data = JSON.parse(rawText);
const repQ = Q.get('repulsion'); const repulsion = repQ == null ? 'normal' : (isNaN(+repQ) ? repQ : +repQ);
const sm = new StarMap($('#stage'), data, { bloom: Q.get('bloom') !== '0', repulsion, declutter: Q.get('declutter') !== '0' });
if (Q.get('edgefade') === '0') sm.edgeFadeOn = false;   // 关掉贴边淡出（只用于对比检查）
window.SM = sm;
addEventListener('resize', () => sm.resize(innerWidth, innerHeight));

// ---------- 卡片 / 点击涟漪 / 引线：都是“事件发生后过了多少秒”的函数 ----------
let cardId = null;
function fillCard(id) {
  const p = sm.pt[id], c = $('#card'); c.style.setProperty('--cc', p.ch.color.getStyle()); c.classList.toggle('hard', !!p.hard);
  c.querySelector('.c-chap').textContent = p.ch.name + (p.hard ? ' · 红光' : ''); c.querySelector('.c-title').textContent = p.title;
  const ul = c.querySelector('.c-bullets'); ul.innerHTML = '';
  (p.card || '').split('；').filter(Boolean).forEach(b => { const li = document.createElement('li'); li.textContent = b.replace(/。$/, ''); ul.appendChild(li); });
  cardId = id;
}
function cardUI(st) { // st: {id, tap, open, close}（秒；负数 = 还没发生）或 null
  const card = $('#card'), tap = $('#tap'), ld = $('#leader');
  if (!st || st.tap < 0) { sm.setFocus(null); sm.focusAmt = 0; card.style.opacity = 0; card.classList.remove('open'); tap.style.opacity = 0; ld.style.opacity = 0; return; }
  if (cardId !== st.id) fillCard(st.id);
  sm.setFocus(st.id);
  const closing = st.close >= 0 ? ease('in', st.close / 0.22) : 0;
  sm.focusAmt = ease('out', st.tap / 0.3) * (1 - closing);
  const s = sm.screenOf(st.id);
  const tk = st.tap / 0.5; tap.style.left = s.x + 'px'; tap.style.top = s.y + 'px';
  tap.style.opacity = tk < 1 ? (1 - tk).toFixed(3) : 0; tap.style.transform = `scale(${0.6 + 1.6 * ease('out', tk)})`;
  if (st.open < 0) { card.style.opacity = 0; ld.style.opacity = 0; return; }
  const x = st.open, sc = x < 0.16 ? 0.6 + 0.46 * ease('out', x / 0.16) : 1.06 - 0.06 * ease('inOut', (x - 0.16) / 0.12);
  const op = Math.min(1, x / 0.1) * (1 - closing);
  card.style.opacity = op.toFixed(3); card.style.transform = `translateX(-50%) scale(${(sc * (1 - 0.15 * closing)).toFixed(4)})`; card.classList.toggle('open', op > 0.5);
  const r = card.getBoundingClientRect(); const l = ld.querySelector('line'), ci = ld.querySelector('circle');
  l.setAttribute('x1', s.x); l.setAttribute('y1', s.y + 12); l.setAttribute('x2', innerWidth / 2); l.setAttribute('y2', r.top);
  ci.setAttribute('cx', s.x); ci.setAttribute('cy', s.y); ci.setAttribute('r', 11 + 2 * Math.sin(x * 6));
  ld.style.opacity = (op * 0.85).toFixed(3);
}

// ---------- 代码视图（真实 knowledge.json 文本） ----------
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;');
const codeLines = rawText.split('\n');
function codeHTML(hl) {
  return codeLines.map((l, i) => {
    let h = esc(l).replace(/("(?:[^"\\]|\\.)*")(\s*:)?/g, (m, s, c) => c ? `<span class="k">${s}</span><span class="p">${c}</span>` : `<span class="s">${s}</span>`).replace(/\b(true|false)\b/g, '<span class="b">$1</span>');
    return `<span class="ln">${i + 1}</span>` + (i === hl ? `<span class="hl">${h}</span>` : h);
  }).join('\n');
}
let codeBuilt = null;
function codeUI(spec, t) {
  const el = $('#code'); if (!spec) { el.style.display = 'none'; return; } el.style.display = 'block';
  const hl = spec.highlight ? codeLines.findIndex(l => l.includes(spec.highlight)) : -1;
  const showHl = spec.hlFrom != null && t >= spec.hlFrom ? hl : -1;
  if (codeBuilt !== showHl) { el.querySelector('.src').innerHTML = codeHTML(showHl); codeBuilt = showHl; }
  const q = keyAt(spec.keys, t, ['line', 'zoom']); const line = q.line === 'hl' ? hl : q.line;
  const C = typeof line === 'number' ? line : hl, z = q.zoom, Yc = (innerHeight - 38) * (spec.yc ?? 0.42);
  el.querySelector('.src').style.transform = `translate(${-(z - 1) * 40}px, ${Yc - (22 + C * 24) * z}px) scale(${z})`;
}
// keys 里 line 可以写 "hl"（= 高亮那一行），换成数字以便插值
function prepCode(spec) { if (!spec) return; const hl = codeLines.findIndex(l => l.includes(spec.highlight)); spec.keys.forEach(k => { if (k.line === 'hl') k.line = hl; }); }

// ---------- 模拟鼠标（录制用；位置可写像素或 "p:<id>"） ----------
function cursorUI(keys, t) {
  const el = $('#cursor'); if (!keys) { el.style.opacity = 0; return; }
  const q = keyAt(keys, t, ['x', 'y', 'wy', 'op']); let x = q.x, y = q.y;
  const tgt = (q._b && t > q._a.t ? q._b : q._a) || q; // 目标可以是一颗星
  if (typeof (q._a || q).at === 'string' || typeof (q._b || {}).at === 'string') {
    const A = q._a || q, B = q._b || q, pa = A.at ? sm.screenOf(A.at.slice(2)) : { x: A.x, y: A.y }, pb = B.at ? sm.screenOf(B.at.slice(2)) : { x: B.x, y: B.y }, k = q._k ?? 1;
    x = pa.x + (pb.x - pa.x) * k; y = pa.y + (pb.y - pa.y) * k; }
  el.style.opacity = q.op ?? 1; el.style.transform = `translate(${x}px, ${y}px)`;
  const mode = (q._a || q).mode || 'idle'; el.classList.toggle('drag', mode === 'drag');
  const w = el.querySelector('.wheel'); w.style.opacity = mode === 'wheel' ? 1 : 0; w.style.setProperty('--wy', (5 + ((t * 3) % 1) * 14) + 'px');
}

const slides = new Slides(sm);

if (MODE === 'record') {
  document.body.classList.add('record');
  const shots = await (await fetch(Q.get('shots') || 'demo/shots_demo.json')).json();
  shots.shots.forEach(s => prepCode(s.code));
  const tl = new Timeline(sm, shots); window.TL = tl;
  if (shots.cardTop) document.documentElement.style.setProperty('--card-top', shots.cardTop);
  window.renderAt = t => {
    const { shot, card } = tl.apply(t);
    if (shot.cardTop) document.documentElement.style.setProperty('--card-top', shot.cardTop); else if (shots.cardTop) document.documentElement.style.setProperty('--card-top', shots.cardTop);
    cardUI(card); codeUI(shot.code, t); cursorUI(shot.cursor, t);
    document.body.classList.toggle('showhint', !!shot.hint);
    slides.set(shot.slides ? (t < shot.slides.break ? -1 : (t - shot.slides.break) / shot.slides.dur) : null, shot.slides ? (t - shot.t0) / 0.35 : 1);
    sm.labelMul = shot.slides ? Math.min(1, Math.max(0, (t - shot.slides.break - 0.7) / 0.6)) : 1;
    sm.update(t);
    return { shot: shot.name, sub: tl.subAt(t)?.text || null, layout: sm.layoutState, edge: sm.edgeStats };
  };
  window.__duration = tl.duration; window.__ready = true;
} else {
  // 交互模式：拖动/缩放 + 点星弹卡片，镜头飞过去（这里用真实时钟，只是给人用的）
  const cam = sm.camera; cam.position.copy(sm.center).add(new THREE.Vector3(0, 0, 260));
  const ctl = new OrbitControls(cam, sm.labels.domElement); ctl.enableDamping = true; ctl.zoomToCursor = true; ctl.target.copy(sm.center); ctl.update();
  let st = null, fly = null; const T0 = performance.now(); const now = () => (performance.now() - T0) / 1000;
  sm.labels.domElement.style.pointerEvents = 'auto';
  let down = null; sm.labels.domElement.addEventListener('pointerdown', e => down = [e.clientX, e.clientY]);
  sm.labels.domElement.addEventListener('pointerup', e => {
    if (!down || Math.hypot(e.clientX - down[0], e.clientY - down[1]) > 6) return;
    const id = sm.pick(e.clientX, e.clientY);
    if (id) { const p = sm.pt[id].pos, dir = cam.position.clone().sub(p).normalize();
      fly = { t: now(), p0: cam.position.clone(), p1: p.clone().add(dir.multiplyScalar(14)), g0: ctl.target.clone(), g1: p.clone().add(new THREE.Vector3(0, -3, 0)) };
      st = { id, t: now() }; }
    else if (st) st.closeAt = now();
  });
  $('.c-close').addEventListener('click', () => { if (st) st.closeAt = now(); });
  addEventListener('keydown', e => { if (e.key === 'Escape' && st) st.closeAt = now(); });
  // 换课：把自己的 knowledge.json 拖进页面
  addEventListener('dragover', e => e.preventDefault());
  addEventListener('drop', async e => { e.preventDefault(); const f = e.dataTransfer.files[0]; if (!f) return; const txt = await f.text();
    try { JSON.parse(txt); sessionStorage.setItem('cg-data', txt); location.reload(); } catch (err) { alert('这个文件不是合法的 JSON：' + err.message); } });
  (function loop() {
    const t = now();
    if (fly) { const k = ease('inOut', (t - fly.t) / 1.0); cam.position.lerpVectors(fly.p0, fly.p1, k); ctl.target.lerpVectors(fly.g0, fly.g1, k); if (k >= 1) fly = null; }
    ctl.update();
    if (st) { const c = st.closeAt != null ? t - st.closeAt : -1; cardUI({ id: st.id, tap: t - st.t, open: t - st.t - 0.8, close: c }); if (c > 0.3) { st = null; cardUI(null); } }
    sm.update(t); requestAnimationFrame(loop);
  })();
}

})();
