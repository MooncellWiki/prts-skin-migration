// 移动端表格横滑外壳：量哪些表伸出正文栏（detect）、包完前后比对（verify）、落地前后量真实页面（live）。
// 配合 scripts/mobile_table_scroll_apply.py，见 migration/mobile-table/README.md「第四步」。
//   node scripts/mobile_table_scroll_measure.mjs detect
//   node scripts/mobile_table_scroll_measure.mjs verify
//   node scripts/mobile_table_scroll_measure.mjs live before|after
// detect / verify 把 parse API 渲染出的正文换进现网页面再量（不写入站点）；页面里的 <script> 不会执行，前后一致。
import { createRequire } from 'node:module';
import { readFileSync, writeFileSync, readdirSync, existsSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
const require = createRequire('/Users/starheart/Documents/Mooncell/prts-design/package.json');
const { chromium, webkit } = require('@playwright/test');

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const WORK = join(ROOT, 'build', 'mts');
const MODE = process.argv[2];
const CONC = Number(process.env.CONC ?? 4);
const SKIN = process.env.SKIN ?? 'arknights';
const BASE = process.env.BASE ?? 'https://prts.wiki';
const ENGINE = process.env.ENGINE ?? 'chromium';
const ONLY = process.env.ONLY ? new Set(process.env.ONLY.split('|')) : null;
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36';

const pageUrl = (title, base = BASE, skin = SKIN) =>
  `${base}/w/${encodeURIComponent(title.replace(/ /g, '_')).replace(/%2F/g, '/')}?${skin ? `useskin=${skin}&` : ''}mts=${Date.now()}`;

// ---- 页面里跑的函数 ----

function swap(html) {
  const old = document.querySelector('#mw-content-text .mw-parser-output');
  if (!old) return false;
  const tmp = document.createElement('div');
  tmp.innerHTML = html;
  const neu = tmp.querySelector('.mw-parser-output');
  old.replaceWith(neu);
  if (window.mw && window.jQuery) mw.hook('wikipage.content').fire(jQuery('#mw-content-text'));
  return true;
}

function expand() {
  document.querySelectorAll('.mw-collapsible.mw-collapsed').forEach((c) => {
    const t = c.querySelector('.mw-collapsible-toggle');
    if (t) try { t.click(); } catch (e) {}
  });
}

function measure() {
  const root = document.querySelector('#mw-content-text .mw-parser-output') || document.querySelector('#mw-content-text');
  if (!root) return { error: 'no content' };
  const rr = root.getBoundingClientRect();
  const limit = rr.right + 1;
  const fs = parseFloat(getComputedStyle(root).fontSize) || 14;
  const out = [];
  // 最外层的「伸出正文栏」的元素；被裁剪 / 滚动容器包住的不算
  (function walk(el) {
    for (const c of el.children) {
      const cs = getComputedStyle(c);
      if (cs.display === 'none' || cs.position === 'fixed') continue;
      const r = c.getBoundingClientRect();
      if (r.width && r.height && r.right > limit) { out.push(c); continue; }
      if (cs.overflowX !== 'visible') continue;
      walk(c);
    }
  })(root);
  const heading = (el) => {
    for (let p = el; p && p !== root; p = p.parentElement) {
      let s = p.previousElementSibling;
      while (s && !/^H[1-6]$/.test(s.tagName) && !s.classList.contains('mw-heading')) s = s.previousElementSibling;
      if (s) return s.innerText.trim().slice(0, 24);
    }
    return '';
  };
  const offenders = [], unmarked = [];
  for (const el of out) {
    const r = el.getBoundingClientRect();
    if (el.tagName === 'TABLE' && el.dataset.mt != null) { offenders.push(Number(el.dataset.mt)); continue; }
    const inner = [...el.querySelectorAll('table[data-mt]')].map((t) => Number(t.dataset.mt));
    const outer = el.closest('table[data-mt]');
    unmarked.push({
      desc: `${el.tagName.toLowerCase()}.${String(el.className).slice(0, 40)}[${(el.getAttribute('style') || '').slice(0, 60)}] ${Math.round(r.width)}px @${heading(el)}`
        + (outer ? ` 在表 #${outer.dataset.mt} 里` : '') + (inner.length ? ` 里面有表 #${inner.slice(0, 4).join(',')}` : ''),
      inner, outer: outer ? Number(outer.dataset.mt) : null,
    });
  }
  // 竖条：格宽 <5em、≥5 个字、单个文本节点折成 ≥3 行（同 build/mt2/measure.mjs）
  const strips = (t) => {
    let n = 0;
    for (const tr of t.rows) for (const c of tr.cells) {
      if (c.closest('table') !== t) continue;
      const r = c.getBoundingClientRect();
      if (!r.width || r.width >= 5 * fs) continue;
      if ((c.innerText || '').replace(/\s+/g, '').length < 5) continue;
      let max = 0;
      const tw = document.createTreeWalker(c, NodeFilter.SHOW_TEXT);
      let node;
      while ((node = tw.nextNode())) {
        if (!node.nodeValue.trim()) continue;
        const rg = document.createRange();
        rg.selectNodeContents(node);
        const tops = new Set();
        for (const rc of rg.getClientRects()) if (rc.width > 0) tops.add(Math.round(rc.top));
        max = Math.max(max, tops.size);
      }
      if (max >= 3) n++;
    }
    return n;
  };
  const tables = {}, margins = {};
  for (const t of root.querySelectorAll('table[data-mt]')) {
    const r = t.getBoundingClientRect();
    tables[t.dataset.mt] = [Math.round(r.left - rr.left), Math.round(r.top - rr.top), Math.round(r.width), Math.round(r.height)];
    const cs = getComputedStyle(t);
    margins[t.dataset.mt] = [cs.marginTop, cs.marginBottom, t.classList.contains('wikitable') ? 1 : 0];
  }
  const wraps = [...root.querySelectorAll('.ak-table-scroll')].map((w) => {
    const t = w.querySelector('table[data-mt]');
    return {
      mt: t ? Number(t.dataset.mt) : null,
      w: w.clientWidth, sw: w.scrollWidth, h: w.clientHeight, sh: w.scrollHeight,
      strips: t ? strips(t) : 0,
    };
  });
  return {
    vw: document.documentElement.clientWidth, docW: document.documentElement.scrollWidth,
    rootW: Math.round(rr.width), rootH: Math.round(rr.height),
    offenders, unmarked, tables, margins, wraps,
  };
}

// ---- 驱动 ----

const engine = ENGINE === 'webkit' ? webkit : chromium;
const browser = await engine.launch(ENGINE === 'webkit' ? {} : { channel: 'chromium' });
async function withPage(width, fn) {
  const ctx = await browser.newContext({ viewport: { width, height: 844 }, ...(ENGINE === 'webkit' ? {} : { userAgent: UA }) });
  await ctx.route(/(hm\.baidu|google-analytics|googletagmanager)/, (r) => r.abort());
  const page = await ctx.newPage();
  try { return await fn(page); } finally { await ctx.close().catch(() => {}); }
}
async function open(page, title, base, skin) {
  await page.goto(pageUrl(title, base, skin), { waitUntil: 'load', timeout: 90000 });
  await page.waitForTimeout(500);
}
async function swapAndMeasure(page, html) {
  const ok = await page.evaluate(swap, html);
  if (!ok) return { error: 'swap failed' };
  await page.waitForTimeout(500);
  await page.evaluate(expand);
  await page.waitForTimeout(400);
  return page.evaluate(measure);
}
async function pool(items, fn) {
  let i = 0, n = 0;
  await Promise.all(Array.from({ length: CONC }, async () => {
    while (i < items.length) {
      const it = items[i++];
      await fn(it);
      if (++n % 20 === 0) console.log(n, '/', items.length);
    }
  }));
}
const load = (dir) => readdirSync(join(WORK, dir)).filter((f) => f.endsWith('.json'))
  .map((f) => JSON.parse(readFileSync(join(WORK, dir, f), 'utf8')))
  .filter((r) => !ONLY || ONLY.has(r.title));
const near = (a, b, tol = 1) => Math.abs(a - b) <= tol;

if (MODE === 'detect') {
  const OUT = join(WORK, 'detect.jsonl');
  const lines = [];
  await pool(load('prep'), async (rec) => {
    const out = { title: rec.title, offenders: [], unmarked: [], margins: {} };
    for (const w of [390, 360]) {
      let r;
      try {
        r = await withPage(w, async (page) => {
          await open(page, rec.title);
          return swapAndMeasure(page, rec.html);
        });
      } catch (e) { r = { error: String(e).slice(0, 300) }; }
      if (r.error) { out.error = r.error; break; }
      if (w === 390) { out.docW = r.docW; out.unmarked = r.unmarked; }
      for (const mt of r.offenders) if (!out.offenders.includes(mt)) { out.offenders.push(mt); out.margins[mt] = r.margins[mt]; }
    }
    lines.push(JSON.stringify(out));
  });
  // MERGE=1：在上一次结果上取并集（先 Chromium，再 ENGINE=webkit MERGE=1——定长宽度的表只有 WebKit 压不住）
  if (process.env.MERGE && existsSync(OUT)) {
    const prev = Object.fromEntries(readFileSync(OUT, 'utf8').split('\n').filter(Boolean).map((l) => { const r = JSON.parse(l); return [r.title, r]; }));
    for (let k = 0; k < lines.length; k++) {
      const r = JSON.parse(lines[k]), p = prev[r.title];
      if (!p || p.error) continue;
      if (r.error) { lines[k] = JSON.stringify(p); continue; }
      const added = r.offenders.filter((mt) => !p.offenders.includes(mt));
      p.offenders.push(...added);
      for (const mt of added) p.margins[mt] = r.margins[mt];
      p[`only_${ENGINE}`] = added;
      p[`unmarked_${ENGINE}`] = r.unmarked;
      lines[k] = JSON.stringify(p);
    }
  }
  // ONLY 只重量一部分页面时，其余页面沿用上次的结果
  const kept = ONLY && existsSync(OUT)
    ? readFileSync(OUT, 'utf8').split('\n').filter((l) => l && !ONLY.has(JSON.parse(l).title)) : [];
  writeFileSync(OUT, [...kept, ...lines].sort().join('\n') + '\n');
  console.log('detect →', OUT);
} else if (MODE === 'verify') {
  const WIDTHS = (process.env.WIDTHS ?? '360,390,1280').split(',').map(Number);
  const OUT = join(WORK, process.env.OUT ?? 'verify.jsonl');
  const prep = Object.fromEntries(load('prep').map((r) => [r.title, r]));
  const lines = [];
  await pool(load('fix'), async (fix) => {
    const rec = { title: fix.title, ids: fix.ids, ok: true, notes: [], by: {} };
    for (const w of WIDTHS) {
      try {
        const [a, b] = await withPage(w, async (page) => {
          await open(page, fix.title);
          const before = await swapAndMeasure(page, prep[fix.title].html);
          const after = await swapAndMeasure(page, fix.html);
          return [before, after];
        });
        if (a.error || b.error) throw new Error(a.error || b.error);
        rec.by[w] = {
          docW: [a.docW, b.docW], rootH: [a.rootH, b.rootH],
          left: b.offenders.length + b.unmarked.length,
          strips: b.wraps.reduce((s, x) => s + x.strips, 0),
        };
        const bad = (msg) => { rec.ok = false; rec.notes.push(`${w}: ${msg}`); };
        const still = b.offenders.filter((mt) => fix.ids.includes(mt));
        if (still.length) bad(`包了仍伸出 #${still.join(',')}`);
        if (b.docW > a.docW) bad(`整页变宽 ${a.docW} → ${b.docW}`);
        for (const x of b.wraps) if (x.sh > x.h + 1) bad(`外壳出现纵向滚动 #${x.mt}（${x.h} / ${x.sh}）`);
        if (w >= 640) {
          // 桌面：每张表的位置尺寸、正文高度都不该变
          for (const [mt, ra] of Object.entries(a.tables)) {
            const rb = b.tables[mt];
            if (!rb || !ra.every((v, k) => near(v, rb[k]))) { bad(`表 #${mt} 位置尺寸变了 ${ra} → ${rb}`); break; }
          }
          if (!near(a.rootH, b.rootH)) bad(`正文高度 ${a.rootH} → ${b.rootH}`);
        } else if (b.offenders.length + b.unmarked.length) {
          rec.notes.push(`${w}: 还有 ${b.offenders.length + b.unmarked.length} 处伸出：` + [...b.offenders.map((m) => `#${m}`), ...b.unmarked.map((u) => u.desc)].slice(0, 3).join('；'));
        }
      } catch (e) { rec.ok = false; rec.notes.push(`${w}: ${String(e).slice(0, 200)}`); }
    }
    lines.push(JSON.stringify(rec));
  });
  writeFileSync(OUT, lines.sort().join('\n') + '\n');
  console.log('verify →', OUT);
} else if (MODE === 'live') {
  // 真实页面：落地前后各量一遍，比对新皮肤 390 / 1280、旧 Vector 1280、Minerva 390
  const tag = process.argv[3];
  // TITLES=文件（一行一个标题）换页面集合，默认是 build/mts/fix 里要改的页面；沙箱（BASE=http://localhost:8080）没有 Minerva
  const ENVS = [
    ['ak390', 390, BASE, 'arknights'], ['ak360', 360, BASE, 'arknights'], ['ak1280', 1280, BASE, 'arknights'],
    ['vector1280', 1280, BASE, 'vector'], ['minerva390', 390, 'https://m.prts.wiki', ''],
  ].filter((e) => BASE === 'https://prts.wiki' || e[0] !== 'minerva390')
    .filter((e) => !process.env.ENVS || process.env.ENVS.split(',').includes(e[0]));
  const titles = process.env.TITLES
    ? readFileSync(process.env.TITLES, 'utf8').split('\n').map((l) => l.trim()).filter((l) => l && !l.startsWith('#'))
    : load('fix').map((r) => r.title);
  mkdirSync(join(WORK, 'live'), { recursive: true });
  const OUT = join(WORK, 'live', `${tag}.jsonl`);
  const lines = [];
  await pool(titles, async (title) => {
    const rec = { title };
    for (const [name, w, base, skin] of ENVS) {
      try {
        rec[name] = await withPage(w, async (page) => {
          await open(page, title, base, skin);
          await page.evaluate(expand);
          await page.waitForTimeout(400);
          return page.evaluate(() => {
            const root = document.querySelector('#mw-content-text .mw-parser-output') || document.querySelector('#mw-content-text');
            const rr = root.getBoundingClientRect();
            const wraps = [...root.querySelectorAll('.ak-table-scroll')];
            return {
              docW: document.documentElement.scrollWidth, rootH: Math.round(rr.height),
              wraps: wraps.length, vscroll: wraps.filter((x) => x.scrollHeight > x.clientHeight + 1).length,
              tables: [...root.querySelectorAll('table')].filter((t) => !t.parentElement.closest('td, th')).map((t) => {
                const r = t.getBoundingClientRect();
                return [Math.round(r.left - rr.left), Math.round(r.top - rr.top), Math.round(r.width), Math.round(r.height)];
              }),
            };
          });
        });
      } catch (e) { rec[name] = { error: String(e).slice(0, 200) }; }
    }
    lines.push(JSON.stringify(rec));
  });
  writeFileSync(OUT, lines.sort().join('\n') + '\n');
  console.log('live →', OUT);
} else {
  console.error('用法：detect | verify | live before|after');
}
await browser.close();
