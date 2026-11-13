// 打包成双击就能打开的版本：index.html + dist/calculus-galaxy.js（three.js 打进去）+ data/knowledge.js
// 用法：npm install && node tools/build.mjs     （改了 knowledge.json 后也跑一下，或者直接把 json 拖进网页）
import { build } from 'esbuild';
import { readFileSync, writeFileSync, mkdirSync } from 'fs';
const here = new URL('..', import.meta.url).pathname;
const json = readFileSync(here + 'data/knowledge.json', 'utf8'); JSON.parse(json);
writeFileSync(here + 'data/knowledge.js', '// 由 tools/build.mjs 从 knowledge.json 生成，双击 index.html 时用\nwindow.KNOWLEDGE_JSON = ' + JSON.stringify(json) + ';\n');
mkdirSync(here + 'dist', { recursive: true });
await build({ entryPoints: [here + 'src/main.js'], bundle: true, format: 'iife', target: 'es2020', minify: true, outfile: here + 'dist/calculus-galaxy.js',
  legalComments: 'eof', banner: { js: '/* calculus-galaxy (MIT) — bundles three.js (MIT, Copyright 2010-2025 Three.js Authors) */' } });
const html = readFileSync(here + 'dev.html', 'utf8')
  .replace(/<script type="importmap">[\s\S]*?<\/script>\n?/, '')
  .replace('<script type="module" src="./src/main.js"></script>', '<script src="./data/knowledge.js"></script>\n<script src="./dist/calculus-galaxy.js"></script>');
writeFileSync(here + 'index.html', html.replace('<title>', '<!-- 打包版：双击即可打开。开发请用 dev.html（需要本地服务器 + npm install） -->\n<title>'));
console.log('built index.html + dist/calculus-galaxy.js + data/knowledge.js');
