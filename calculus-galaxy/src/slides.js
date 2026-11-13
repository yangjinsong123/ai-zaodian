// “大纲示意页裂开变成星星”：5 张自己画的章节示意页（canvas 绘制，角落标“示意”），粒子飞向本章的星。
import * as THREE from 'three';
import { rng } from './starmap.js';
const ease = x => x < .5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2;

function drawSlide(ch, k) {
  const c = document.createElement('canvas'); c.width = 960; c.height = 540; const g = c.getContext('2d');
  const F = (w, s) => `${w} ${s}px "Noto Sans CJK SC", sans-serif`;
  g.fillStyle = '#f8fafc'; g.fillRect(0, 0, 960, 540);
  g.fillStyle = ch.color.getStyle(); g.fillRect(0, 0, 22, 540); g.fillRect(0, 0, 960, 10);
  g.fillStyle = '#0f172a'; g.font = F(900, 30); g.fillText(`第 ${k + 1} 部分`, 64, 82);
  g.font = F(900, 62); g.fillText(ch.name, 64, 166);
  g.fillStyle = '#334155'; g.font = F(700, 36);
  ch.pts.slice(0, 4).forEach((p, i) => { g.fillStyle = ch.color.getStyle(); g.beginPath(); g.arc(80, 248 + i * 66, 9, 0, 7); g.fill(); g.fillStyle = '#334155'; g.fillText(p.title, 104, 261 + i * 66); });
  if (ch.pts.length > 4) { g.fillStyle = '#94a3b8'; g.font = F(700, 30); g.fillText(`…… 共 ${ch.pts.length} 个知识点`, 104, 261 + 4 * 66 - 6); }
  g.fillStyle = '#dc2626'; g.beginPath(); g.roundRect(820, 26, 112, 56, 14); g.fill(); g.fillStyle = '#fff'; g.font = F(900, 34); g.fillText('示意', 842, 66);
  g.fillStyle = '#94a3b8'; g.font = F(700, 22); g.fillText('自己画的大纲示意页 · 非真实课件', 600, 512);
  return c;
}

export class Slides {
  constructor(sm) {
    this.sm = sm; const R = rng(77); this.group = new THREE.Group(); sm.camera.add(this.group); this.group.visible = false;
    this.planes = []; const parts = [], cols = [], ends = [];
    Object.values(sm.ch).forEach((ch, k) => {
      const cv = drawSlide(ch, k), tex = new THREE.CanvasTexture(cv); tex.colorSpace = THREE.SRGBColorSpace;
      const m = new THREE.Mesh(new THREE.PlaneGeometry(30, 16.875), new THREE.MeshBasicMaterial({ map: tex, color: 0x8c96a8, transparent: true, depthWrite: false, fog: false }));
      m.position.set((k % 2 ? 2.2 : -2.2), (2 - k) * 15.6, -75 - k * 0.3); m.rotation.z = (k % 2 ? -1 : 1) * 0.03; m.renderOrder = 10 + k; this.group.add(m); this.planes.push(m);
      // 采样像素 → 粒子
      const px = cv.getContext('2d').getImageData(0, 0, 960, 540).data;
      for (let y = 0; y < 540; y += 6) for (let x = 0; x < 960; x += 6) {
        const o = (y * 960 + x) * 4, r = px[o], gg = px[o + 1], b = px[o + 2]; const ink = r + gg + b < 690;
        if (!ink && R() > 0.04) continue;
        const local = new THREE.Vector3(m.position.x + (x / 960 - .5) * 30, m.position.y + (.5 - y / 540) * 16.875, m.position.z + 0.05);
        parts.push(local); cols.push(ink ? [r / 255 * .8 + .2, gg / 255 * .8 + .2, b / 255 * .8 + .2] : [0.5, 0.6, 0.85]);
        const star = ch.pts[Math.floor(R() * ch.pts.length)]; ends.push([star, new THREE.Vector3(R() - .5, R() - .5, R() - .5).multiplyScalar(3.2), R()]);
      }
    });
    this.local = parts; this.ends = ends; const n = parts.length;
    const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(new Float32Array(n * 3), 3));
    g.setAttribute('color', new THREE.BufferAttribute(new Float32Array(cols.flat()), 3));
    this.points = new THREE.Points(g, new THREE.PointsMaterial({ size: 0.5, vertexColors: true, map: sm.texCore, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, fog: false }));
    this.points.frustumCulled = false; this.points.visible = false; sm.scene.add(this.points); this.n = n;
  }
  // u < 0：只显示完整示意页；0~1：裂开飞向星；>1：隐藏。appear：示意页出现的进度 0~1
  set(u, appear = 1) {
    const sm = this.sm; if (u == null || u > 1) { this.group.visible = false; this.points.visible = false; return; }
    this.group.visible = true; this.planes.forEach((m, k) => { const a = Math.min(1, Math.max(0, appear * 1.6 - k * 0.15));
      m.material.opacity = a * (u < 0 ? 1 : 1 - Math.min(1, u / 0.12)); m.position.x = (k % 2 ? 2.2 : -2.2) + (1 - a) * (k % 2 ? 36 : -36); });
    if (u < 0) { this.points.visible = false; return; }
    sm.camera.updateMatrixWorld(); const arr = this.points.geometry.attributes.position.array, tmp = new THREE.Vector3();
    for (let i = 0; i < this.n; i++) { const [star, j, ph] = this.ends[i]; const k = Math.min(1, Math.max(0, (u - ph * 0.25) / 0.75)), e = ease(k);
      tmp.copy(this.local[i]); sm.camera.localToWorld(tmp); const end = star.pos.clone().add(j);
      tmp.lerp(end, e); tmp.y += Math.sin(k * Math.PI) * (ph - .5) * 18; tmp.x += Math.sin(k * Math.PI) * (ph * 7 % 1 - .5) * 18; arr.set([tmp.x, tmp.y, tmp.z], i * 3); }
    this.points.geometry.attributes.position.needsUpdate = true; this.points.visible = true;
    this.points.material.opacity = Math.min(1, u / 0.05) * (1 - Math.max(0, (u - 0.85) / 0.15)); this.points.material.size = 0.5 + 0.4 * Math.sin(Math.min(1, u) * Math.PI);
  }
}
