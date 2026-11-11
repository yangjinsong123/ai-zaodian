/* 边打字边背单词 · cet-typing-words
 * 纯前端，无依赖。数据全部存在浏览器 localStorage。 */
(function () {
  "use strict";

  // ===== 配置 =====
  var EXAM = { y: 2026, m: 12, d: 12, label: "笔试 2026年12月12日" }; // 四六级笔试日（每年改这里）
  var WRONG_LIMIT = 2;            // 同一个词拼错几次进错词本
  var KEY = "cet-typing-words:v1"; // localStorage 键名

  var WORDS = (window.WORDS || []).filter(function (x) { return x && x.w && x.m; });
  var byWord = {};
  WORDS.forEach(function (x) { byWord[x.w] = x; });

  // ===== 存储 =====
  function todayStr(dt) {
    dt = dt || new Date();
    return dt.getFullYear() + "-" + pad(dt.getMonth() + 1) + "-" + pad(dt.getDate());
  }
  function pad(n) { return (n < 10 ? "0" : "") + n; }
  function load() {
    var s = null;
    try { s = JSON.parse(localStorage.getItem(KEY)); } catch (e) { s = null; }
    s = s || {};
    s.pos = typeof s.pos === "number" ? s.pos : 0;
    s.wrong = s.wrong || {};      // 每个词累计拼错次数
    s.book = s.book || [];        // 错词本：[{w, n, t}]
    s.today = s.today || { date: todayStr(), n: 0 };
    if (s.today.date !== todayStr()) s.today = { date: todayStr(), n: 0 };
    s.muted = !!s.muted;
    return s;
  }
  var S = load();
  var storageOK = true;
  function save() {
    try { localStorage.setItem(KEY, JSON.stringify(S)); }
    catch (e) { if (storageOK) { storageOK = false; toast("浏览器不允许本地存储，刷新后进度会丢失"); } }
  }

  // ===== DOM =====
  var $ = function (id) { return document.getElementById(id); };
  var el = {
    days: $("days"), examDate: $("examDate"), badge: $("badge"), today: $("today"), prog: $("prog"), total: $("total"),
    progWrap: $("progWrap"), tabLearn: $("tabLearn"), tabBook: $("tabBook"), tabN: $("tabN"), viewLearn: $("viewLearn"),
    viewBook: $("viewBook"), modeTag: $("modeTag"), card: $("card"), pos: $("pos"), meaning: $("meaning"), hint: $("hint"),
    form: $("form"), ans: $("ans"), fb: $("fb"), skipBtn: $("skipBtn"), okBtn: $("okBtn"), tip: $("tip"),
    bookList: $("bookList"), bookEmpty: $("bookEmpty"), reviewBtn: $("reviewBtn"), toast: $("toast"),
    bookBtn: $("bookBtn"), muteBtn: $("muteBtn")
  };

  // ===== 倒计时 =====
  function daysLeft() {
    var now = new Date();
    var a = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    var b = new Date(EXAM.y, EXAM.m - 1, EXAM.d);
    return Math.round((b - a) / 86400000);
  }
  function renderCountdown() {
    var n = daysLeft();
    el.examDate.textContent = EXAM.label;
    if (n < 0) { el.days.parentNode.parentNode.innerHTML = '<span class="cd-label">本次四六级笔试已结束，下次见</span>'; return; }
    if (n === 0) { el.days.textContent = "0"; el.examDate.textContent = "今天考试，加油！"; return; }
    // 每天第一次打开：数字从 n+1 翻到 n
    if (S.cdSeen !== todayStr()) {
      el.days.textContent = String(n + 1);
      setTimeout(function () {
        el.days.classList.add("flip");
        setTimeout(function () { el.days.textContent = String(n); }, 300);
        setTimeout(function () { el.days.classList.remove("flip"); }, 650);
        beep("tick");
      }, 700);
      S.cdSeen = todayStr(); save();
    } else {
      el.days.textContent = String(n);
    }
  }

  // ===== 声音（WebAudio 现场合成，无音频文件）=====
  var ac = null;
  function beep(kind) {
    if (S.muted) return;
    try {
      ac = ac || new (window.AudioContext || window.webkitAudioContext)();
      var t = ac.currentTime;
      var seq = {
        ok: [[880, 0, .09], [1320, .08, .18]],
        bad: [[220, 0, .16], [180, .12, .2]],
        fly: [[600, 0, .05], [900, .05, .05], [1200, .1, .08]],
        tick: [[1500, 0, .03]]
      }[kind] || [];
      seq.forEach(function (s) {
        var o = ac.createOscillator(), g = ac.createGain();
        o.type = kind === "bad" ? "square" : "sine"; o.frequency.value = s[0];
        g.gain.setValueAtTime(0.0001, t + s[1]);
        g.gain.exponentialRampToValueAtTime(kind === "bad" ? 0.06 : 0.18, t + s[1] + 0.01);
        g.gain.exponentialRampToValueAtTime(0.0001, t + s[1] + s[2]);
        o.connect(g); g.connect(ac.destination); o.start(t + s[1]); o.stop(t + s[1] + s[2] + 0.02);
      });
    } catch (e) { /* 没有声音也不影响使用 */ }
  }

  // ===== 状态 =====
  var mode = "learn";     // learn | review
  var queue = [];         // 复习队列
  var cur = null;         // 当前词对象
  var locked = false;     // 答对后的短暂锁定
  var triesThisWord = 0;

  function currentWord() {
    if (mode === "review") return queue.length ? byWord[queue[0]] : null;
    if (S.pos >= WORDS.length) S.pos = 0;
    return WORDS[S.pos];
  }
  function show() {
    cur = currentWord(); locked = false; triesThisWord = 0;
    el.card.classList.remove("ok", "bad");
    el.fb.innerHTML = ""; el.ans.value = "";
    if (!cur) { // 复习完了
      el.pos.textContent = "完成"; el.meaning.textContent = "错词全部复习完 🎉"; el.hint.textContent = "继续背新词吧";
      el.ans.disabled = true; el.okBtn.textContent = "回去背新词"; el.skipBtn.hidden = true;
      return;
    }
    el.ans.disabled = false; el.okBtn.textContent = "确认 ⏎"; el.skipBtn.hidden = false;
    el.pos.textContent = cur.p || "";
    el.meaning.textContent = cur.m;
    el.hint.textContent = "共 " + cur.w.length + " 个字母";
    renderStats();
  }
  function renderStats() {
    el.today.textContent = S.today.n;
    el.total.textContent = WORDS.length;
    if (mode === "review") {
      el.progWrap.innerHTML = "复习剩 <b>" + queue.length + "</b> 个";
      el.modeTag.textContent = "错词复习 · 打对就移出错词本"; el.modeTag.classList.add("review");
    } else {
      el.progWrap.innerHTML = '进度 <b id="prog">' + (S.pos + 1) + "</b>/" + WORDS.length;
      el.modeTag.textContent = "看中文，打英文 · 回车确认"; el.modeTag.classList.remove("review");
    }
    var n = S.book.length;
    el.badge.textContent = n; el.badge.classList.toggle("zero", n === 0);
    el.tabN.textContent = n; el.tabN.classList.toggle("zero", n === 0);
    el.muteBtn.textContent = S.muted ? "🔇" : "🔊";
  }

  function norm(s) { return String(s || "").trim().toLowerCase().replace(/\s+/g, " "); }
  function isRight(v) {
    if (!cur) return false;
    v = norm(v);
    return v === cur.w.toLowerCase() || (cur.alt || []).some(function (a) { return v === a.toLowerCase(); });
  }

  function onCorrect() {
    locked = true;
    el.card.classList.remove("bad"); el.card.classList.add("ok");
    beep("ok");
    if (mode === "review") {
      S.book = S.book.filter(function (b) { return b.w !== cur.w; });
      delete S.wrong[cur.w];
      queue.shift();
      el.fb.innerHTML = '<span class="good">✓ 拼对了，已移出错词本</span>';
      toast("✓ " + cur.w + " 已移出错词本");
    } else {
      S.today.n += 1; S.pos += 1;
      el.fb.innerHTML = '<span class="good">✓ 正确</span>';
      el.today.classList.remove("tick"); void el.today.offsetWidth; el.today.classList.add("tick");
    }
    save(); renderStats(); renderBook();
    setTimeout(show, 750);
  }

  function onWrong(v) {
    triesThisWord++;
    el.card.classList.remove("ok", "shake"); void el.card.offsetWidth;
    el.card.classList.add("bad", "shake");
    beep("bad");
    var w = cur.w;
    S.wrong[w] = (S.wrong[w] || 0) + 1;
    var n = S.wrong[w];
    var html = '<div><span class="warn">✗ 拼错了</span>（这个词第 ' + n + ' 次拼错）</div>' +
      '<div>正确拼写：<span class="right">' + w + "</span></div>";
    var entered = false;
    var inBook = S.book.some(function (b) { return b.w === w; });
    if (inBook) {
      S.book.forEach(function (b) { if (b.w === w) b.n = n; });
    } else if (n >= WRONG_LIMIT) {
      S.book.unshift({ w: w, n: n, t: Date.now() }); entered = true;
      html += '<div class="into">已自动加入错词本</div>';
    }
    if (mode === "review") {
      // 复习时打错：放到队尾，稍后再来
      queue.push(queue.shift());
    }
    el.fb.innerHTML = html;
    save();
    el.ans.value = "";
    el.ans.focus();
    if (entered) fly(w, function () { renderStats(); renderBook(true); bump(); }); else { renderStats(); renderBook(); }
    if (mode === "review") setTimeout(function () { if (!locked) show(); }, 1600);
  }

  function submit() {
    if (!cur) { setMode("learn"); return; }
    if (locked) return;
    var v = el.ans.value;
    if (!norm(v)) { el.ans.focus(); return; }
    if (isRight(v)) onCorrect(); else onWrong(v);
  }

  // 词卡“飞”进右上角错词本
  function fly(word, done) {
    // 兼容页面被缩放（CSS zoom / 浏览器缩放）的情况：把矩形换算回 CSS 像素
    var z = (el.card.getBoundingClientRect().width / el.card.offsetWidth) || 1;
    var R = function (r) { return { left: r.left / z, top: r.top / z, width: r.width / z, height: r.height / z }; };
    var from = R(el.ans.getBoundingClientRect()), to = R(el.bookBtn.getBoundingClientRect());
    var f = document.createElement("div"); f.className = "flyer"; f.textContent = word;
    document.body.appendChild(f);
    var fw = f.offsetWidth, fh = f.offsetHeight;
    var x0 = from.left + from.width / 2 - fw / 2, y0 = from.top + from.height / 2 - fh / 2;
    f.style.left = x0 + "px"; f.style.top = y0 + "px";
    var dx = to.left + to.width / 2 - (x0 + fw / 2), dy = to.top + to.height / 2 - (y0 + fh / 2);
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        f.style.transform = "translate(" + dx + "px," + dy + "px) scale(.25)"; f.style.opacity = ".2";
      });
    });
    beep("fly");
    setTimeout(function () { f.remove(); done && done(); }, 720);
  }
  function bump() { el.badge.classList.remove("bump"); void el.badge.offsetWidth; el.badge.classList.add("bump"); }

  // ===== 错词本 =====
  function renderBook(animateFirst) {
    el.bookList.innerHTML = "";
    S.book.forEach(function (b, i) {
      var x = byWord[b.w] || { m: "", p: "" };
      var li = document.createElement("li");
      if (animateFirst && i === 0) li.className = "new";
      li.innerHTML = '<span class="bw"></span><span class="bm"></span><span class="bc"></span>';
      li.children[0].textContent = b.w;
      li.children[1].textContent = (x.p ? x.p + " " : "") + x.m;
      li.children[2].textContent = "错 " + (S.wrong[b.w] || b.n) + " 次";
      el.bookList.appendChild(li);
    });
    el.bookEmpty.hidden = S.book.length > 0;
    el.reviewBtn.disabled = S.book.length === 0;
    el.reviewBtn.style.opacity = S.book.length ? 1 : .5;
  }

  // ===== 页面切换 =====
  function setView(v) {
    el.viewLearn.hidden = v !== "learn"; el.viewBook.hidden = v !== "book";
    el.tabLearn.classList.toggle("active", v === "learn"); el.tabBook.classList.toggle("active", v === "book");
    if (v === "book") renderBook();
    window.scrollTo(0, 0);
  }
  function setMode(m) {
    mode = m;
    if (m === "review") queue = S.book.map(function (b) { return b.w; }).reverse(); // 先错的先复习
    setView("learn"); show();
    setTimeout(function () { if (!el.ans.disabled) el.ans.focus(); }, 50);
  }

  var toastT = null;
  function toast(msg) {
    el.toast.textContent = msg; el.toast.classList.add("show");
    clearTimeout(toastT); toastT = setTimeout(function () { el.toast.classList.remove("show"); }, 1600);
  }

  // ===== 事件 =====
  el.form.addEventListener("submit", function (e) { e.preventDefault(); submit(); });
  el.okBtn.addEventListener("click", function () { submit(); });
  el.ans.addEventListener("input", function () {
    if (el.card.classList.contains("bad")) el.card.classList.remove("bad", "shake");
    if (!locked && isRight(el.ans.value) && norm(el.ans.value).length === cur.w.length) onCorrect(); // 打完即判对，不用回车
  });
  el.skipBtn.addEventListener("click", function () {
    if (!cur || locked) return;
    if (mode === "review") queue.push(queue.shift()); else { S.pos += 1; save(); }
    show(); el.ans.focus();
  });
  el.tabLearn.addEventListener("click", function () { if (mode === "review") setMode("learn"); else setView("learn"); });
  el.tabBook.addEventListener("click", function () { setView("book"); });
  el.bookBtn.addEventListener("click", function () { setView("book"); });
  el.reviewBtn.addEventListener("click", function () { if (S.book.length) setMode("review"); });
  el.muteBtn.addEventListener("click", function () { S.muted = !S.muted; save(); renderStats(); });
  // 软键盘弹出时，把输入框滚到可视区域
  el.ans.addEventListener("focus", function () {
    setTimeout(function () { el.card.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, 250);
  });
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", function () {
      if (document.activeElement === el.ans) el.card.scrollIntoView({ block: "nearest" });
    });
  }
  // 跨过零点自动重置“今日已背”
  setInterval(function () {
    if (S.today.date !== todayStr()) { S.today = { date: todayStr(), n: 0 }; save(); renderStats(); renderCountdown(); }
  }, 60000);

  // ===== 启动 =====
  if (!WORDS.length) { el.meaning.textContent = "词表没加载到，请检查 words.js"; return; }
  renderCountdown(); renderBook(); show();
  setTimeout(function () { try { el.ans.focus({ preventScroll: true }); } catch (e) {} }, 100);
  // 调试/录屏用：暴露只读状态
  window.CTW = { state: function () { return JSON.parse(JSON.stringify(S)); }, daysLeft: daysLeft };
})();
