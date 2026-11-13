// node tools/layout_check.mjs：两种参数各跑一遍，打印包围盒/最小间距/章节质心，并验证确定性
import { readFileSync } from 'fs';
import { ForceLayout, PRESETS } from '../src/layout.js';
const data = JSON.parse(readFileSync(new URL('../data/knowledge.json', import.meta.url)));
for (const [k, pr] of Object.entries(PRESETS)) {
  const a = new ForceLayout(data, pr).run(), b = new ForceLayout(data, pr).run();
  const same = a.x.every((v, i) => v === b.x[i]); const c = a.centroids();
  console.log(k, JSON.stringify(a.stats()), 'deterministic:', same);
  console.log('  centroids', data.chapters.map((ch, j) => ch.short + '(' + [0, 1, 2].map(q => c[j * 3 + q].toFixed(0)).join(',') + ')').join(' '));
}
const f = new ForceLayout(data, PRESETS.low).run(); f.set(PRESETS.normal);
for (const s of [30, 90, 180, 300, 450]) { f.step(s - (f.stepCount - 600)); console.log('low→normal +' + (f.stepCount - 600), JSON.stringify(f.stats())); }
