// 在页面里跑的对比度审计：找出正文中「文字色 vs 实际背景色」对比度不足的元素。
// 由 scripts/theme_audit.mjs 注入；也可以直接贴进 DevTools 控制台执行 contrastAudit()。
//
// 背景色取法：从元素往上逐层合成 background-color，直到不透明为止；
// 中途遇到 background-image（渐变 / 图片）就放弃——算不准，不报。
function contrastAudit(options) {
  const threshold = (options && options.threshold) || 3;
  const root = document.querySelector('.mw-parser-output') || document.body;

  const parse = (value) => {
    const m = /rgba?\(([^)]+)\)/.exec(value);
    if (!m) return null;
    const p = m[1].split(/[,\/\s]+/).filter(Boolean).map(Number);
    return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
  };
  const over = (top, bottom) => ({
    r: top.r * top.a + bottom.r * (1 - top.a),
    g: top.g * top.a + bottom.g * (1 - top.a),
    b: top.b * top.a + bottom.b * (1 - top.a),
    a: 1,
  });
  const luminance = (c) => {
    const f = (v) => {
      v /= 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  };
  const ratio = (a, b) => {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
    return (hi + 0.05) / (lo + 0.05);
  };
  const hex = (c) =>
    '#' + [c.r, c.g, c.b].map((v) => Math.round(v).toString(16).padStart(2, '0')).join('');

  // 画布色：正文容器再往上的那一层
  const canvas = (() => {
    const layers = [];
    for (let n = root; n; n = n.parentElement) {
      const c = parse(getComputedStyle(n).backgroundColor);
      if (c && c.a > 0) layers.push(c);
      if (c && c.a === 1) break;
    }
    let base = matchMedia('(prefers-color-scheme: dark)').matches
      ? { r: 18, g: 18, b: 18, a: 1 }
      : { r: 255, g: 255, b: 255, a: 1 };
    for (const layer of layers.reverse()) base = over(layer, base);
    return base;
  })();

  const background = (el) => {
    const layers = [];
    let owner = null;
    for (let n = el; n && n !== root.parentElement; n = n.parentElement) {
      const s = getComputedStyle(n);
      if (s.backgroundImage && s.backgroundImage !== 'none') return null;
      const c = parse(s.backgroundColor);
      if (c && c.a > 0) {
        layers.push(c);
        if (!owner) owner = n;
        if (c.a === 1) break;
      }
    }
    let base = canvas;
    for (const layer of layers.reverse()) base = over(layer, base);
    return { color: base, owner };
  };

  const describe = (el) => {
    if (!el) return '';
    const cls = typeof el.className === 'string' ? el.className.trim() : '';
    return el.tagName.toLowerCase() + (cls ? '.' + cls.split(/\s+/).slice(0, 3).join('.') : '');
  };
  const nearestClass = (el) => {
    for (let n = el; n && n !== root; n = n.parentElement) {
      if (typeof n.className === 'string' && n.className.trim()) return n;
    }
    return null;
  };
  const inlineHas = (el, prop) => !!(el && el.style && el.style.getPropertyValue(prop));

  const groups = new Map();
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let total = 0;
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = node.nodeValue.trim();
    if (!text) continue;
    const el = node.parentElement;
    if (!el || /^(SCRIPT|STYLE|NOSCRIPT)$/.test(el.tagName)) continue;
    if (!el.getClientRects().length) continue;
    const style = getComputedStyle(el);
    if (style.visibility === 'hidden' || Number(style.opacity) === 0) continue;
    const bg = background(el);
    const fgRaw = parse(style.color);
    if (!bg || !fgRaw) continue;
    total++;
    const fg = over(fgRaw, bg.color);
    const value = ratio(fg, bg.color);
    if (value >= threshold) continue;

    // 文字色是谁定的：自己或祖先的行内 style，否则算样式表 / 继承
    let colorOwner = null;
    for (let n = el; n && n !== root; n = n.parentElement) {
      if (inlineHas(n, 'color')) {
        colorOwner = n;
        break;
      }
    }
    const anchor = nearestClass(bg.owner && root.contains(bg.owner) ? bg.owner : el);
    const key = [describe(anchor), hex(fg), hex(bg.color)].join(' | ');
    const group = groups.get(key) || {
      anchor: describe(anchor),
      element: describe(el),
      fg: hex(fg),
      bg: hex(bg.color),
      ratio: Math.round(value * 100) / 100,
      fgFrom: colorOwner ? 'inline' : 'css',
      bgFrom: !bg.owner || !root.contains(bg.owner)
        ? 'skin'
        : inlineHas(bg.owner, 'background-color') || inlineHas(bg.owner, 'background')
          ? 'inline'
          : 'css',
      bgStyle: bg.owner && root.contains(bg.owner) ? (bg.owner.getAttribute('style') || '').slice(0, 160) : '',
      count: 0,
      chars: 0,
      sample: text.slice(0, 30),
    };
    group.count++;
    group.chars += text.length;
    groups.set(key, group);
  }
  return {
    theme: [...document.documentElement.classList].filter((c) => c.startsWith('skin-theme')),
    dark: matchMedia('(prefers-color-scheme: dark)').matches,
    canvas: hex(canvas),
    textNodes: total,
    issues: [...groups.values()].sort((a, b) => b.chars - a.chars),
  };
}
