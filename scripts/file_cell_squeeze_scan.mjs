// 全站扫「只放一张文件图的表格格子」被挤小：皮肤 .mw-file-element { max-width:100% } 让图的最小内容宽度计 0，
// 自动表格布局里这种格子会被兄弟列挤到图比 width 属性小、甚至 0 宽（模板:剧情简介 的播放按钮就是一例）。
// 见 migration/story-play-button/README.md。
//   node scripts/file_cell_squeeze_scan.mjs scan [N]     # 主名字空间非重定向页，固定间隔抽 N 个（不给 = 全量）；可断点续跑
//     跳过剧情文本页（/BEG /END /NBT /ENTRY，前 400 个一格没中）和非 wikitext 子页（/spine /data /blockdata）
//   node scripts/file_cell_squeeze_scan.mjs page 标题     # 只量一页，打印明细
// 每页加载一次：先按 1000 宽量（桌面版式、不出侧栏时正文栏最窄的一段），再缩到 390 量（手机版式）。
// 图片请求一律回 1×1 透明 PNG：[[文件:]] 的图都带 width / height 属性，宽度不靠加载（只有非正方形图的高度会变，不影响列宽），
// 省得每页等图、也不给图床添负担。
// 结果逐页追加到 build/file-cell-squeeze/scan.jsonl；再跑 scan 只补没量过和上次出错的页。
//   node scripts/file_cell_squeeze_scan.mjs summarize     # 按「图片名前缀 + 设定宽 + 表格类 + 格子」归组，写 summary.md
import { createRequire } from 'node:module';
import { appendFileSync, existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
const require = createRequire('/Users/starheart/Documents/Mooncell/prts-design/package.json');
const { chromium } = require('@playwright/test');

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const WORK = join(ROOT, 'build', 'file-cell-squeeze');
const OUT = join(WORK, 'scan.jsonl');
const MODE = process.argv[2];
const CONC = Number(process.env.CONC ?? 8);
const BASE = 'https://prts.wiki';
const WIDTHS = [1000, 390];
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36';

const PIXEL = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=', 'base64');

const SKIP = /\/(BEG|END|NBT|ENTRY|spine|data|blockdata)$/;

const pageUrl = (title) => `${BASE}/w/${encodeURIComponent(title.replace(/ /g, '_')).replace(/%2F/g, '/')}?useskin=arknights`;

// ---- 页面里跑的函数 ----

function expand() {
  document.querySelectorAll('.mw-collapsible.mw-collapsed').forEach((c) => {
    const t = c.querySelector('.mw-collapsible-toggle');
    if (t) try { t.click(); } catch (e) {}
    c.classList.remove('mw-collapsed');
  });
}

function scan() {
  const root = document.querySelector('#mw-content-text .mw-parser-output');
  if (!root) return { error: 'no content' };
  const contentW = root.getBoundingClientRect().width;
  const hits = [];
  for (const img of root.querySelectorAll('img.mw-file-element')) {
    if (!img.getClientRects().length) continue;
    const W = +img.getAttribute('width');
    if (!W) continue;
    const w = img.getBoundingClientRect().width;
    if (w >= W - 1) continue;
    const cell = img.closest('td, th');
    if (!cell || !root.contains(cell)) continue;
    // 格子里只有这一张图：没有可见文字、没有别的可见图
    if ([...cell.querySelectorAll('img')].filter((i) => i.getClientRects().length).length !== 1) continue;
    if (cell.innerText.trim() !== '') continue;
    const table = cell.closest('table');
    const src = decodeURIComponent(img.currentSrc || img.src);
    // 原文件名：缩略图 …/thumb/x/xy/文件名/50px-文件名，原图 …/x/xy/文件名
    const m = src.match(/\/thumb\/[0-9a-f]\/[0-9a-f]{2}\/([^/?]+)\//) || src.match(/\/[0-9a-f]\/[0-9a-f]{2}\/([^/?]+?)(?:\?|$)/);
    hits.push({
      file: m ? m[1] : src.slice(-60),
      W, w: Math.round(w),
      cellW: Math.round(cell.getBoundingClientRect().width),
      tableW: Math.round(table.getBoundingClientRect().width),
      cell: `${cell.tagName.toLowerCase()}.${cell.className}`.slice(0, 80),
      cellStyle: (cell.getAttribute('style') || '').slice(0, 80),
      table: String(table.className).slice(0, 80),
      tableStyle: (table.getAttribute('style') || '').slice(0, 80),
      href: (img.closest('a')?.getAttribute('href') || '').slice(0, 60),
    });
  }
  return { contentW: Math.round(contentW), pageW: document.documentElement.scrollWidth, hits };
}

// ---- 驱动 ----

async function measure(ctx, title) {
  const page = await ctx.newPage();
  try {
    await page.setViewportSize({ width: WIDTHS[0], height: 900 });
    await page.goto(pageUrl(title), { waitUntil: 'domcontentloaded', timeout: 90000 });
    await Promise.race([page.waitForLoadState('load'), page.waitForTimeout(4000)]);
    await page.evaluate(expand);
    const rec = { title };
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 900 });
      await page.waitForTimeout(300);
      rec[width] = await page.evaluate(scan);
    }
    return rec;
  } catch (e) {
    return { title, error: String(e).slice(0, 200) };
  } finally {
    await page.close();
  }
}

async function newContext(browser) {
  const ctx = await browser.newContext({ userAgent: UA });
  await ctx.route('**/*', (route) => {
    const type = route.request().resourceType();
    if (type === 'image') return route.fulfill({ status: 200, contentType: 'image/png', body: PIXEL });
    if (type === 'media') return route.abort();
    return route.continue();
  });
  return ctx;
}

async function allTitles(browser) {
  // 页面清单在页面里用 API 取（站点对非浏览器 UA 返回 403）
  const ctx = await browser.newContext({ userAgent: UA });
  const page = await ctx.newPage();
  await page.goto(`${BASE}/api.php`, { waitUntil: 'domcontentloaded' });
  const titles = await page.evaluate(async () => {
    const out = [];
    let cont = {};
    for (;;) {
      const q = new URLSearchParams({ action: 'query', format: 'json', list: 'allpages', apnamespace: '0', apfilterredir: 'nonredirects', aplimit: 'max', ...cont });
      const j = await (await fetch(`/api.php?${q}`)).json();
      out.push(...j.query.allpages.map((p) => p.title));
      if (!j.continue) return out;
      cont = j.continue;
    }
  });
  await ctx.close();
  return titles;
}

// 每页取最后一次的记录（scan 重跑会给出错的页追加新记录）
const latest = () => [...new Map((existsSync(OUT) ? readFileSync(OUT, 'utf8') : '').split('\n').filter(Boolean)
  .map((l) => JSON.parse(l)).map((r) => [r.title, r])).values()];
const ok = (r) => !r.error && WIDTHS.every((w) => r[w] && !r[w].error);
// 没有 .mw-parser-output 的页（…/spine 之类非 wikitext 内容模型），不算失败，也不重量
const noContent = (r) => WIDTHS.every((w) => r[w]?.error === 'no content');

// 归组用的特征：文件名第一段去掉末尾编号（头像_敌人_xxx → 头像，干员轮换卡池194 → 干员轮换卡池）、表格类（去掉脚本加的）、格子；
// 设定宽不进特征（同一模板常按参数给不同尺寸），组里另记范围
const IGNORED = new Set(['jquery-tablesorter', 'mw-made-collapsible', 'mw-collapsed', 'mw-collapsible', 'sortable', 'logo', 'logo-top', 'nodesktop', 'nomobile']);
const signature = (h) => [
  h.file.replace(/\.\w+$/, '').split(/[_ ]/)[0].replace(/\d+$/, '') || h.file,
  h.table.split(/\s+/).filter((c) => c && !IGNORED.has(c) && !/^(mw-made|jquery)/.test(c)).join('.') || '-',
  h.cell,
].join(' · ');

mkdirSync(WORK, { recursive: true });

if (MODE === 'scan') {
  const browser = await chromium.launch({ channel: 'chromium' });
  const list = join(WORK, 'titles.json');
  const all = existsSync(list) ? JSON.parse(readFileSync(list, 'utf8')) : await allTitles(browser);
  writeFileSync(list, JSON.stringify(all));
  const n = Number(process.argv[3] ?? all.filter((t) => !SKIP.test(t)).length);
  const step = Math.max(1, Math.floor(all.length / n));
  const done = new Set(latest().filter((r) => ok(r) || noContent(r)).map((r) => r.title));
  // MAX：这个进程最多量几页。Playwright 客户端随页数涨内存（换上下文也压不住），几千页后 Node 堆会爆，
  // 全量用外层循环分批跑：until node … scan | grep -q '这次量 0'; do :; done
  const titles = all.filter((t) => !SKIP.test(t)).filter((_, i) => i % step === 0).slice(0, n).filter((t) => !done.has(t))
    .slice(0, Number(process.env.MAX ?? Infinity));
  console.log(`主名字空间 ${all.length} 页，抽 ${Math.min(n, all.length)}（每 ${step} 个取 1），已量 ${done.size}，这次量 ${titles.length}`);
  let next = 0, finished = 0;
  const t0 = Date.now();
  await Promise.all(Array.from({ length: CONC }, async () => {
    // 上下文定期换新：一直开着的话，拦截图片留下的请求对象越积越多，几千页后 Node 堆会爆
    let ctx = await newContext(browser), used = 0;
    while (next < titles.length) {
      if (++used > 150) { await ctx.close(); ctx = await newContext(browser); used = 1; }
      const rec = await measure(ctx, titles[next++]);
      appendFileSync(OUT, JSON.stringify(rec) + '\n');
      if (++finished % 200 === 0) {
        const rate = finished / ((Date.now() - t0) / 1000);
        console.log(`  ${finished} / ${titles.length}（${rate.toFixed(2)} 页/秒，约剩 ${Math.round((titles.length - finished) / rate / 60)} 分钟）`);
      }
    }
    await ctx.close();
  }));
  await browser.close();
  console.log(`→ ${OUT}`);
} else if (MODE === 'page') {
  const browser = await chromium.launch({ channel: 'chromium' });
  const ctx = process.env.REAL_IMAGES === '1' ? await browser.newContext({ userAgent: UA }) : await newContext(browser);
  console.log(JSON.stringify(await measure(ctx, process.argv[3]), null, 1));
  await browser.close();
} else if (MODE === 'summarize') {
  const recs = latest();
  const good = recs.filter(ok);
  const empty = recs.filter(noContent);
  const failed = recs.filter((r) => !ok(r) && !noContent(r));
  const lines = [`量到 ${good.length} 页，无正文 ${empty.length} 页，失败 ${failed.length} 页${failed.length ? `：${failed.map((r) => r.title).join('、')}` : ''}`, ''];
  for (const width of WIDTHS) {
    const pages = good.filter((r) => r[width].hits.some((x) => x.w <= x.W * 0.9));
    lines.push(`## ${width} 宽`, '', `有缩小 10% 以上的单图格子 ${pages.length} 页，共 ${pages.reduce((s, r) => s + r[width].hits.filter((x) => x.w <= x.W * 0.9).length, 0)} 格。「大图」= 设定宽超过正文栏一半，按栏宽缩放是预期行为。`, '');
    const groups = new Map();
    for (const r of pages) {
      // 缩小不到 10% 的不算（大图按栏宽收一点是预期行为）
      for (const h of r[width].hits.filter((x) => x.w <= x.W * 0.9)) {
        const k = signature(h);
        const g = groups.get(k) ?? groups.set(k, { pages: new Set(), cells: 0, ratios: [], min: Infinity, big: false, Ws: new Set() }).get(k);
        g.pages.add(r.title); g.cells++; g.ratios.push(h.w / h.W); g.min = Math.min(g.min, h.w); g.Ws.add(h.W);
        g.big ||= h.W > r[width].contentW / 2;
      }
    }
    lines.push('| 页 | 格 | 设定宽 | 实际 / 设定（中位） | 最小 px | 图片前缀 · 表格类 · 格子 | | 例 |', '| ---: | ---: | ---: | ---: | ---: | --- | --- | --- |');
    for (const [k, g] of [...groups].sort((a, b) => b[1].pages.size - a[1].pages.size)) {
      const med = g.ratios.sort((a, b) => a - b)[g.ratios.length >> 1];
      const Ws = [...g.Ws].sort((a, b) => a - b);
      lines.push(`| ${g.pages.size} | ${g.cells} | ${Ws.length > 1 ? `${Ws[0]}–${Ws.at(-1)}` : Ws[0]} | ${Math.round(med * 100)}% | ${g.min} | ${k} | ${g.big ? '大图' : ''} | ${[...g.pages].slice(0, 3).join('、')} |`);
    }
    lines.push('');
  }
  writeFileSync(join(WORK, 'summary.md'), lines.join('\n'));
  console.log(lines.slice(0, 2).join('\n'));
  console.log(`→ ${join(WORK, 'summary.md')}`);
} else {
  console.error('用法：node scripts/file_cell_squeeze_scan.mjs scan [N] | page <标题> | summarize');
  process.exit(1);
}
