// 在页面里跑的行悬停审计：找出 .wikitable 行悬停时底色被皮肤盖掉、文字看不清的单元格。
// 由 scripts/hover_audit.py 注入；也可以直接贴进 DevTools 控制台执行 hoverAudit()。
//
// 皮肤有 .wikitable > tbody > tr:hover > td { background: var(--ak-bg-hover) }（特异性 0,2,3），
// 模板 / 页内样式给单元格（或所在行、表格）上底色的选择器特异性更低时，悬停那一行底色就被换掉，
// 文字色却照旧——深底白字悬停成浅灰底白字。
//
// 悬停态的模拟：把能读到的样式表里所有带 :hover 的规则原位克隆一份，:hover 换成 .__hov
// （特异性相同、紧挨原规则，层叠结果与真悬停一致），再给单元格、所在行及其全部祖先挂上 __hov。
// 计算样式对 display:none 的元素也有效，折叠 / 标签页里没展开的表格照样量得到。
function hoverAudit(options) {
  const threshold = (options && options.threshold) || 3;
  const root = document.querySelector('.mw-parser-output') || document.body;
  const HOV = '__hov';

  if (!window.__hoverAuditCloned) {
    const clone = (list) => {
      for (let i = 0; i < list.cssRules.length; i++) {
        const rule = list.cssRules[i];
        if (rule instanceof CSSStyleRule) {
          if (!rule.selectorText.includes(':hover')) continue;
          const sel = rule.selectorText.replace(/:hover(?![\w-])/g, '.' + HOV);
          try {
            list.insertRule(sel + '{' + rule.style.cssText + '}', i + 1);
            i++;
          } catch (e) {
            /* 选择器浏览器不认（克隆前就不生效），跳过 */
          }
        } else if (rule.cssRules && rule.insertRule) {
          clone(rule);
        }
      }
    };
    for (const sheet of document.styleSheets) {
      try {
        if (sheet.cssRules) clone(sheet);
      } catch (e) {
        /* 跨域样式表读不到 */
      }
    }
    window.__hoverAuditCloned = true;
  }

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
    c ? '#' + [c.r, c.g, c.b].map((v) => Math.round(v).toString(16).padStart(2, '0')).join('') : null;

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

  // 实际背景：往上逐层合成 background-color；遇到渐变 / 图片记 image（算不准对比度）
  const background = (el) => {
    const layers = [];
    let image = false;
    for (let n = el; n; n = n.parentElement) {
      const s = getComputedStyle(n);
      if (s.backgroundImage && s.backgroundImage !== 'none') {
        image = true;
        break;
      }
      const c = parse(s.backgroundColor);
      if (c && c.a > 0) {
        layers.push(c);
        if (c.a === 1) break;
      }
    }
    if (image) return null;
    let base = canvas;
    for (const layer of layers.reverse()) base = over(layer, base);
    return base;
  };

  const ownBg = (el) => {
    const s = getComputedStyle(el);
    return s.backgroundColor + ' ' + s.backgroundImage;
  };
  const hasOwnBg = (el) => {
    const s = getComputedStyle(el);
    const c = parse(s.backgroundColor);
    return (c && c.a > 0) || (s.backgroundImage && s.backgroundImage !== 'none');
  };

  // 单元格里文字的最低对比度（只看底色归单元格及以上的文字；自带底色的徽章等不受行悬停影响）
  const textRatio = (td) => {
    let min = null;
    let sample = '';
    const walker = document.createTreeWalker(td, NodeFilter.SHOW_TEXT);
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const text = node.nodeValue.trim();
      if (!text) continue;
      const el = node.parentElement;
      if (!el || /^(SCRIPT|STYLE|NOSCRIPT)$/.test(el.tagName)) continue;
      let shielded = false;
      for (let n = el; n && n !== td; n = n.parentElement) {
        if (hasOwnBg(n)) {
          shielded = true;
          break;
        }
      }
      if (shielded) continue;
      const bg = background(el);
      const fgRaw = parse(getComputedStyle(el).color);
      if (!bg || !fgRaw) continue;
      const value = ratio(over(fgRaw, bg), bg);
      if (min === null || value < min) {
        min = value;
        sample = text.slice(0, 30);
      }
    }
    return { min, sample };
  };

  const describe = (el) => {
    if (!el) return '';
    const cls = typeof el.className === 'string' ? el.className.trim() : '';
    return el.tagName.toLowerCase() + (cls ? '.' + cls.split(/\s+/).slice(0, 4).join('.') : '');
  };
  // 底色来自哪条规则：列出匹配该元素、写了 background 的非皮肤规则（选择器 + 所在样式块）
  const sheetLabel = (sheet) => {
    const node = sheet.ownerNode;
    if (sheet.href) {
      const m = /modules=([^&]+)/.exec(sheet.href);
      return m ? 'load:' + decodeURIComponent(m[1]) : sheet.href;
    }
    if (!node) return '?';
    const dedup = node.getAttribute && node.getAttribute('data-mw-deduplicate');
    if (dedup) return dedup;
    if (node.classList && node.classList.contains('WidgetStyle')) return 'WidgetStyle';
    return '<style>';
  };
  const rulesFor = (el) => {
    const out = [];
    const walk = (list, label) => {
      for (const rule of list.cssRules) {
        if (rule instanceof CSSStyleRule) {
          if (rule.selectorText.includes('.' + HOV)) continue;
          const st = rule.style;
          if (!/background/.test(st.cssText)) continue;
          let hit = false;
          for (const sel of rule.selectorText.split(/,(?![^(]*\))/)) {
            try {
              if (el.matches(sel)) {
                hit = true;
                break;
              }
            } catch (e) {
              /* ignore */
            }
          }
          if (!hit) continue;
          const important =
            st.getPropertyPriority('background') ||
            st.getPropertyPriority('background-color') ||
            st.getPropertyPriority('background-image');
          out.push({ src: label, sel: rule.selectorText.slice(0, 200), important: !!important });
        } else if (rule.cssRules) {
          if (rule instanceof CSSMediaRule && !matchMedia(rule.conditionText || rule.media.mediaText).matches) continue;
          walk(rule, label);
        }
      }
    };
    for (const sheet of document.styleSheets) {
      let rules;
      try {
        rules = sheet.cssRules;
      } catch (e) {
        continue;
      }
      if (!rules) continue;
      const label = sheetLabel(sheet);
      if (/skins\.arknights/.test(label)) continue;
      walk(sheet, label.slice(0, 80));
    }
    return out;
  };

  const cells = [...root.querySelectorAll('table.wikitable > tbody > tr > td')];
  const measure = () =>
    cells.map((td) => {
      const eff = background(td);
      const t = textRatio(td);
      return { own: ownBg(td), eff: eff ? hex(eff) : 'image', ratio: t.min, sample: t.sample };
    });

  const before = measure();
  const marked = new Set();
  for (const td of cells) {
    for (let n = td; n; n = n.parentElement) {
      if (marked.has(n)) break;
      marked.add(n);
    }
  }
  for (const n of marked) n.classList.add(HOV);
  const after = measure();
  for (const n of marked) n.classList.remove(HOV);

  // 皮肤的悬停底色是半透明叠加：写在 |- 行或表格上的底色只是被压暗一点，不算问题；
  // 要找的是单元格自己的底色被整个换成了悬停色（作者规则特异性不够，输给皮肤）
  const probe = document.createElement('div');
  probe.style.background = 'var(--ak-bg-hover)';
  root.appendChild(probe);
  const hoverOwn = ownBg(probe);
  probe.remove();

  const groups = new Map();
  cells.forEach((td, i) => {
    const b = before[i];
    const a = after[i];
    if (b.own === a.own || a.own !== hoverOwn) return;
    if (/^rgba\(0, 0, 0, 0\) none$/.test(b.own)) return;
    const rules = rulesFor(td);
    if (!rules.length) return; // 底色不是作者样式表给的（皮肤自己的条纹等）
    let kind;
    if (a.ratio !== null && a.ratio < threshold && (b.ratio === null || b.ratio >= threshold)) kind = 'unreadable';
    else if (/gradient|url\(/.test(b.own)) kind = 'image';
    else kind = 'recolor';
    const table = td.closest('table');
    const key = [kind, describe(table), describe(td), b.own].join(' | ');
    const g = groups.get(key) || {
      kind,
      table: describe(table),
      cell: describe(td),
      bgBefore: b.own,
      bgAfter: a.own,
      effBefore: b.eff,
      effAfter: a.eff,
      ratioBefore: b.ratio === null ? null : Math.round(b.ratio * 100) / 100,
      ratioAfter: a.ratio === null ? null : Math.round(a.ratio * 100) / 100,
      sample: a.sample || b.sample || '',
      rules,
      count: 0,
    };
    g.count++;
    groups.set(key, g);
  });
  return {
    theme: [...document.documentElement.classList].filter((c) => c.startsWith('skin-theme')),
    dark: matchMedia('(prefers-color-scheme: dark)').matches,
    cells: cells.length,
    issues: [...groups.values()],
  };
}
