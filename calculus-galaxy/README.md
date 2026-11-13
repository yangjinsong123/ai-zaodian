# calculus-galaxy · 一元微积分 3D 知识星图

把一门课的知识点写成一张 JSON 表，网页自己把它们排成一片能飞进去的星空：

- 每个知识点是一颗星，同一章的星聚成一个会发光的星团（5 个星团、32 颗星）；
- 光线 = 前置关系（先学 A，再学 B），光点沿着光线从“先学”流向“后学”；
- 红光星是我们自己标的几个重点，只是视觉设计，**不代表考点或必考**；
- 32 颗星之间一共 42 条光线（前置关系），由 `pre` 字段自动生成；
- 拖动旋转、滚轮飞进去、点一颗星弹出要点卡片。

> **关于内容**：`data/knowledge.json` 里的 32 个知识点和卡片文字，是我们按大学高等数学（一元微积分）的**通用常识自己整理**的，
> 不是任何一门课、任何老师或任何教材的真实课件，也没有照搬教材原文。需要的话请按自己的课本和老师的讲法改。

## 直接用（不用装任何东西）

下载整个文件夹，**双击 `index.html`**，用 Chrome / Edge / Firefox 打开就能飞。

- 拖动：旋转星空；滚轮 / 双指：朝鼠标方向飞进去；点星星：飞过去并弹出卡片；Esc 或点空白处：关卡片。
- 换课：把你自己的 `knowledge.json` **直接拖进网页**就会换成你的星图（只在当前标签页生效）。

## 换成你自己的课：knowledge.json 格式

```json
{
 "meta": { "title": "高等数学 · 一元微积分" },
 "chapters": [
  {"id": "limit", "name": "函数、极限与连续", "short": "极限", "color": "#22d3ee"}
 ],
 "points": [
  {
   "id": "d_def", "title": "导数的定义", "chapter": "deriv", "hard": false,
   "pre": ["极限的直观定义"],
   "card": "函数在一点的瞬时变化率，是 Δy/Δx 在 Δx→0 时的极限。"
  }
 ]
}
```

| 字段 | 说明 |
|---|---|
| `chapters[].id / name / short / color` | 星团 id、全名、星团上的大字（可省略，省略就用全名）、颜色 |
| `points[].title` | 星的名字（也可以被别的点在 `pre` 里引用） |
| `points[].id` | 可选，英文 id；不写就用 `title` |
| `points[].chapter` | 属于哪个星团（填 `chapters[].id`） |
| `points[].pre` | 前置知识点的 `title` 或 `id` 列表，连线由它自动生成 |
| `points[].hard` | `true` = 红光星 |
| `points[].card` | 卡片文案，用中文分号 `；` 分成几行要点 |
| `points[].pos` | 可选 `[x,y,z]`，手动固定位置（不写就交给力导向） |

改完 JSON 后：拖进网页即可预览；想让双击 `index.html` 默认就是你的课，运行一次 `npm install && node tools/build.mjs`（会重新生成 `data/knowledge.js` 和 `dist/`）。

## 布局：两层力导向（`src/layout.js`）

纯 JS、固定种子、固定步长、固定 600 步 → 每次打开位置都一样。

1. 星团之间：章节质心互相排斥（强度 = `repulsion × chapterRepulsion`），把 5 团拉开；
2. 星团内部：节点互相排斥 + 向本章质心聚拢 + 依赖连线当弹簧；
3. 向心力 y 方向最弱，所以星图是竖长的，适合手机竖屏。

**翻车开关**：URL 加 `?repulsion=low`（排斥力 0.06，正常是 60）+ `&declutter=0`（关掉标签避让），就能复现“32 颗星挤成一团、字叠在一起”的第一版。
也可以写数字：`?repulsion=5`。命令行检查：`node tools/layout_check.mjs`（打印两种参数的包围盒、最小间距，并验证两次运行结果逐位相同）。

## 开发 / 录视频

```bash
npm install                      # three 0.187.0（+ esbuild 只用于打包）
python3 -m http.server 8000      # 然后打开 http://localhost:8000/dev.html（源码版，ES module）
node tools/build.mjs             # 打包成双击可用的 index.html

# 逐帧录制（固定时间步，不依赖实时时钟；1080×1920 / 30fps）
pip install -r requirements.txt && python -m playwright install chromium   # 或用 --chrome 指向系统 Chrome
python tools/record.py --out ../demo.mp4                                   # 10 秒镜头穿梭 demo
python tools/record.py --shots demo/shots_fail_fix.json --out ../fail.mp4  # 翻车 → 调参散开
python tools/record.py --stills 1.0,2.0 --still-dir ../stills              # 只截几帧
python tools/record.py --shots demo/shots_d5_film.json --raw --no-subs --frames-dir ../frames --frames 800-860  # 只重渲一段帧
```

`demo/*.json` 是镜头时间线（相机关键帧、点哪颗星、什么时候切布局参数），格式见文件里的 `_说明`。
录制时每一帧调用一次 `renderAt(t)`（t = 帧号 / 30），力导向过渡按“帧号 × 每帧步数”推进，所以同一份时间线重录结果一致。

## 文件

```
index.html            双击打开的打包版
dev.html              源码版（需本地服务器 + npm install）
src/layout.js         两层力导向（无依赖）
src/starmap.js        Three.js 渲染：星、星团星云、连线、光点、标签避让、发光
src/shots.js          录制用镜头时间线
src/slides.js         “大纲示意页裂开成星”效果（示意页是 canvas 现画的，角落标“示意”）
src/main.js           入口：交互 / 录制两种模式、卡片、代码视图
data/knowledge.json   32 个知识点（自己整理）
tools/                build.mjs / record.py / layout_check.mjs / make_knowledge.py
```

## 许可

代码 MIT（见 LICENSE）。three.js 为 MIT。网页字体用系统字体（建议安装 Noto Sans CJK，SIL OFL）。
