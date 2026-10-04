// 道具图标在窄表格里被挤小：量真实页面上的图标尺寸、整页宽，落地前可注入修法预演。
// 配合 scripts/item_icon_shrink_apply.py，见 migration/item-icon-shrink/README.md。
//   node scripts/item_icon_shrink_measure.mjs page 采购中心            # 各皮肤 / 引擎 / 宽度量一遍
//   node scripts/item_icon_shrink_measure.mjs sample 200              # 抽 200 个嵌入 道具图标 的页面（新皮肤，WIDTH=390）；数字给大就是全量
//   PATCH=1 …                                                         # 量完再注入修法量一遍（模板没改时预演用）
//   UNDO=1 …                                                          # 模板改完后：同一次加载里先摘掉类量「前」，再放回去量「后」
// 结果写 build/icon-shrink/。
import { createRequire } from 'node:module';
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
const require = createRequire('/Users/starheart/Documents/Mooncell/prts-design/package.json');
const { chromium, webkit } = require('@playwright/test');

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const WORK = join(ROOT, 'build', 'icon-shrink');
const MODE = process.argv[2];
const PATCH = process.env.PATCH === '1';
const UNDO = process.env.UNDO === '1';
const CONC = Number(process.env.CONC ?? 4);
const BASE = process.env.BASE ?? 'https://prts.wiki';
const ENGINE = process.env.ENGINE ?? 'chromium';
const WIDTH = Number(process.env.WIDTH ?? 390);
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36';

const pageUrl = (title, base, skin) =>
  `${base}/w/${encodeURIComponent(title.replace(/ /g, '_')).replace(/%2F/g, '/')}?${skin ? `useskin=${skin}&` : ''}iis=${Date.now()}`;

// ---- 页面里跑的函数 ----

// 道具图标 的外壳：改后带 prts-item-icon 类；改前只能靠行内样式 + 图片文件名（道具 带框 xxx.png）认
function boxes() {
  const root = document.querySelector('#mw-content-text .mw-parser-output');
  if (!root) return [];
  return [...root.querySelectorAll('div.prts-item-icon, div[data-iis], div[style="display:inline-block;position:relative"]')].filter((b) => {
    const img = b.querySelector(':scope > span[typeof="mw:File"] img');
    return img && decodeURIComponent(img.src).includes('道具_带框_');
  });
}

function expand() {
  document.querySelectorAll('.mw-collapsible.mw-collapsed').forEach((c) => {
    const t = c.querySelector('.mw-collapsible-toggle');
    if (t) try { t.click(); } catch (e) {}
  });
  // Minerva 的章节默认收起
  document.querySelectorAll('.collapsible-block').forEach((s) => { s.hidden = false; s.classList.add('open-block'); });
}

function measure(boxesSrc) {
  const root = document.querySelector('#mw-content-text .mw-parser-output');
  if (!root) return { error: 'no content' };
  const icons = (0, eval)(`(${boxesSrc})`)().map((b) => b.querySelector('img')).filter((i) => i.getClientRects().length);
  const width = (i) => i.getBoundingClientRect().width;
  const small = icons.filter((i) => width(i) < (+i.getAttribute('width') || 0) - 1);
  // 图标伸出所在单元格
  const spill = icons.filter((i) => {
    const td = i.closest('td,th');
    if (!td) return false;
    const a = i.getBoundingClientRect(), b = td.getBoundingClientRect();
    return a.right > b.right + 1 || a.left < b.left - 1;
  }).length;
  // 最外层的「伸出正文栏」的元素；被裁剪 / 滚动容器包住的不算
  const limit = root.getBoundingClientRect().right + 1;
  const out = [];
  (function walk(el) {
    for (const c of el.children) {
      const cs = getComputedStyle(c);
      if (cs.display === 'none' || cs.position === 'fixed') continue;
      const r = c.getBoundingClientRect();
      if (r.width && r.height && r.right > limit) {
        out.push(`${c.tagName.toLowerCase()}.${String(c.className).slice(0, 30)}[${(c.getAttribute('style') || '').slice(0, 40)}] ${Math.round(r.width)}`);
        continue;
      }
      if (cs.overflowX !== 'visible') continue;
      walk(c);
    }
  })(root);
  return {
    icons: icons.length, small: small.length,
    minIcon: icons.length ? Math.round(Math.min(...icons.map(width))) : null,
    spill, pageW: document.documentElement.scrollWidth, contentH: Math.round(root.getBoundingClientRect().height), out,
    tables: JSON.stringify([...root.querySelectorAll('table')].map((t) => { const r = t.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height)]; })),
  };
}

// 预演：等于模板加类 + 样式页那条规则
function patch(boxesSrc) {
  (0, eval)(`(${boxesSrc})`)().forEach((b) => b.classList.add('prts-item-icon'));
  const st = document.createElement('style');
  st.textContent = '.mw-parser-output .prts-item-icon .mw-file-element { max-width: none; }';
  document.head.appendChild(st);
}

function undo(boxesSrc) {
  (0, eval)(`(${boxesSrc})`)().forEach((b) => { b.classList.remove('prts-item-icon'); b.dataset.iis = '1'; });
}

function redo() {
  document.querySelectorAll('[data-iis]').forEach((b) => b.classList.add('prts-item-icon'));
}

// ---- 驱动 ----

const launch = (eng) => (eng === 'webkit' ? webkit.launch() : chromium.launch({ channel: 'chromium' }));

const newContext = (browser, eng, width) =>
  browser.newContext({ viewport: { width, height: 844 }, ...(eng === 'webkit' ? {} : { userAgent: UA }) });

async function measurePage(ctx, title, base, skin) {
  const page = await ctx.newPage();
  try {
    await page.goto(pageUrl(title, base, skin), { waitUntil: 'load', timeout: 90000 });
    await page.waitForTimeout(800);
    await page.evaluate(expand);
    await page.waitForTimeout(500);
    const src = boxes.toString();
    if (UNDO) await page.evaluate(undo, src);
    const rec = { before: await page.evaluate(measure, src) };
    if ((PATCH || UNDO) && !rec.before.error) {
      await page.evaluate(UNDO ? redo : patch, src);
      await page.waitForTimeout(300);
      rec.after = await page.evaluate(measure, src);
    }
    return rec;
  } catch (e) {
    return { before: { error: String(e).slice(0, 200) } };
  } finally {
    await page.close();
  }
}

const brief = (m) => (m.error ? m.error : `图标 ${m.icons}，缩小 ${m.small}（最小 ${m.minIcon}px），伸出格子 ${m.spill}，整页 ${m.pageW}，正文高 ${m.contentH}${m.out.length ? `，伸出正文栏：${m.out.join('；')}` : ''}`);

mkdirSync(WORK, { recursive: true });

if (MODE === 'page') {
  const title = process.argv[3] ?? '采购中心';
  const envs = [
    ['chromium', BASE, 'arknights', 390], ['chromium', BASE, 'arknights', 360], ['webkit', BASE, 'arknights', 390],
    ['chromium', BASE, 'arknights', 1280], ['chromium', BASE, 'vector', 1280],
    ['chromium', 'https://m.prts.wiki', '', 390], ['webkit', 'https://m.prts.wiki', '', 390],
  ].filter((e) => BASE === 'https://prts.wiki' || e[1] === BASE);
  const browsers = {};
  for (const [eng, base, skin, width] of envs) {
    browsers[eng] ??= await launch(eng);
    const ctx = await newContext(browsers[eng], eng, width);
    const rec = await measurePage(ctx, title, base, skin);
    await ctx.close();
    console.log(`${eng} · ${skin || 'minerva'} · ${width}`);
    console.log(`  ${rec.after ? '前 ' : ''}${brief(rec.before)}`);
    if (rec.after) console.log(`  后 ${brief(rec.after)}${rec.before.tables === rec.after.tables ? '（各表尺寸不变）' : ''}`);
  }
  for (const b of Object.values(browsers)) await b.close();
} else if (MODE === 'sample') {
  const n = Number(process.argv[3] ?? 200);
  const browser = await launch(ENGINE);
  // 嵌入页清单在页面里用 API 取（站点对非浏览器 UA 返回 403）
  const ctx = await browser.newContext({ userAgent: UA });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/api.php`, { waitUntil: 'domcontentloaded' });
  const all = await page.evaluate(async () => {
    const titles = [];
    let cont = {};
    for (;;) {
      const q = new URLSearchParams({ action: 'query', format: 'json', list: 'embeddedin', eititle: '模板:道具图标', einamespace: '0', eilimit: 'max', ...cont });
      const j = await (await fetch(`/api.php?${q}`)).json();
      titles.push(...j.query.embeddedin.map((p) => p.title));
      if (!j.continue) return titles;
      cont = j.continue;
    }
  });
  await ctx.close();
  // 固定间隔抽样，结果可复现
  const step = Math.max(1, Math.floor(all.length / n));
  const titles = all.filter((_, i) => i % step === 0).slice(0, n);
  console.log(`主名字空间嵌入页 ${all.length}，抽 ${titles.length}（每 ${step} 个取 1）`);
  const recs = [];
  let next = 0;
  // 每个并发一个上下文，页面之间共用缓存
  await Promise.all(Array.from({ length: CONC }, async () => {
    const worker = await newContext(browser, ENGINE, WIDTH);
    while (next < titles.length) {
      const title = titles[next++];
      recs.push({ title, ...(await measurePage(worker, title, BASE, 'arknights')) });
      if (recs.length % 100 === 0) console.log(`  ${recs.length} / ${titles.length}`);
    }
  }));
  await browser.close();
  const file = join(WORK, `sample-${ENGINE}-${WIDTH}-${titles.length}${PATCH ? '-patch' : UNDO ? '-undo' : ''}.jsonl`);
  writeFileSync(file, recs.map((r) => JSON.stringify(r)).join('\n') + '\n');
  const ok = recs.filter((r) => !r.before.error);
  const shrunk = ok.filter((r) => r.before.small);
  console.log(`量到 ${ok.length} 页（失败 ${recs.length - ok.length}）；有图标被挤小的 ${shrunk.length} 页，共 ${shrunk.reduce((s, r) => s + r.before.small, 0)} 个图标`);
  if (PATCH || UNDO) {
    const still = ok.filter((r) => r.after.small || r.after.spill);
    const wider = ok.filter((r) => r.after.pageW > r.before.pageW);
    const newOut = ok.filter((r) => r.after.out.length > r.before.out.length);
    console.log(`改后：仍有缩小 / 伸出格子的 ${still.length} 页；整页变宽的 ${wider.length} 页；新伸出正文栏的 ${newOut.length} 页`);
    for (const r of new Set([...still, ...wider, ...newOut])) console.log(`  ${r.title}\n    前 ${brief(r.before)}\n    后 ${brief(r.after)}`);
  } else {
    for (const r of shrunk) console.log(`  ${r.title}：${brief(r.before)}`);
  }
  console.log(`→ ${file}`);
} else {
  console.error('用法：node scripts/item_icon_shrink_measure.mjs page <标题> | sample <N>');
  process.exit(1);
}
