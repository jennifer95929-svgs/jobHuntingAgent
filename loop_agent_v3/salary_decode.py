"""BOSS 薪资字体解码 —— 通过 canvas 渲染对比识别 PUA 数字字形。

原因:BOSS 用 kanzhun 私有字体把薪资数字渲染成 PUA 字符(\\ue000 段),
且每次页面会换字体映射(反爬)。但用户浏览器里渲染的都是正确数字,
所以用「Paint 后像素对比」识别 PUA 对应的真实数字,反爬换字体也躲不掉。

用法:解码器在页面内执行,需要 CDP evaluate 一块 JS(见 build_decoder_js)。
"""
import json


def build_decoder_js() -> str:
    """返回一段可在目标页面内执行的 JS,解码 .job-card-box 内所有薪资的 PUA 数字。"""
    return r"""
(() => {
  // 收集页面上所有薪资文本里的 PUA 字符
  const allSalary = [...document.querySelectorAll('.job-card-box .job-salary, .job-salary')];
  const puaChars = new Set();
  allSalary.forEach(el => [...el.textContent].forEach(c => {
    const cp = c.codePointAt(0);
    if (cp >= 0xe000 && cp <= 0xf8ff) puaChars.add(c);
  }));

  if (puaChars.size === 0) return JSON.stringify({decoded: []});

  // 渲染函数:把字符画到 canvas,返回其像素位图(集合)
  const canvas = document.createElement('canvas');
  canvas.width = 60; canvas.height = 60;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#000';
  ctx.textBaseline = 'top';
  function bitmap(ch, font) {
    ctx.clearRect(0, 0, 60, 60);
    ctx.font = '44px ' + font;
    ctx.fillText(ch, 4, 6);
    const d = ctx.getImageData(0, 0, 60, 60).data;
    const s = new Set();
    for (let i = 0; i < d.length; i += 4) if (d[i + 3] > 0) s.add(i);
    return s;
  }
  // ASCII 数字标尺必须用「非 obfuscated」字体渲染,否则 kanzhun 会把 ASCII 也画成谜底数字。
  // 因此显式排除所有 BOSS 私有字体,标尺用系统字体。
  const asciiFonts = ['sans-serif', 'system-ui', 'Arial', 'Helvetica'];
  let scaleFont = 'sans-serif';
  for (const f of asciiFonts) {
    const b = bitmap('8', f);
    if (b.size > 10) { scaleFont = f; break; }
  }

  // 建 ASCII 0-9 标尺
  const asciiBitmap = {};
  for (let n = 0; n <= 9; n++) asciiBitmap[n] = bitmap(String(n), scaleFont);

  function similarity(a, b) {
    // Jaccard 相似度(宽松版:较小者重合比例),shape 差异大则低分
    let inter = 0;
    for (const v of a) if (b.has(v)) inter++;
    return inter / Math.max(1, Math.min(a.size, b.size));
  }

  // PUA 谜底字符必须用 DOM 里实际使用的字体渲染(kanzhun 系),标尺用系统字体。
  // 先探测页面实际用于薪资的字体。
  const probe = document.querySelector('.job-salary');
  const domFont = probe ? getComputedStyle(probe).fontFamily.split(',')[0].trim() : 'kanzhun-Regular';
  const puaFont = (domFont && domFont.indexOf('sans') === -1) ? domFont : 'kanzhun-Regular';

  const map = {};
  for (const ch of puaChars) {
    const chbmp = bitmap(ch, puaFont);       // PUA 用 kanzhun 渲染 → 得到谜底数字形状
    let best = null, bestSim = 0;
    for (let n = 0; n <= 9; n++) {
      const sim = similarity(chbmp, asciiBitmap[n]);
      if (sim > bestSim) { bestSim = sim; best = n; }
    }
    if (bestSim > 0.5) map[ch] = String(best);
  }

  // 用映射解码每条薪资
  const decoded = allSalary.map(el => {
    let t = el.textContent.trim();
    for (const [ch, digit] of Object.entries(map)) {
      t = t.split(ch).join(digit);
    }
    return t;
  });
  return JSON.stringify({font: scaleFont, map: Object.keys(map).map(k => ('\\u' + k.codePointAt(0).toString(16)) + ':' + map[k]), decoded});
})()
"""
