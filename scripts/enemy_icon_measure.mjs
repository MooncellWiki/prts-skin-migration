// 敌人头像（模板:敌人头像 的 .enemyicon）被挤小：按页面类型抽样，页内预演「外壳写定宽」的修法。
// 外壳 <div class="enemyicon"> 是按内容收缩的 inline-block，图的 max-width:100% 以它为参照，最小宽度计 0（同 item-icon-shrink）。
// 拟改 模板:敌人头像：<div class="enemyicon" style="width:{{{px|130}}}px">；预演时按图的 width 属性写同样的行内宽度。
// 见 migration/story-play-button/README.md「全站扫描」。
//   node scripts/enemy_icon_measure.mjs sample [每类页数]     # 默认 25；结果写 build/enemy-icon/
//   node scripts/enemy_icon_measure.mjs page 标题             # 单页明细
// 每页在新皮肤 1280 / 1000 / 390 宽各量一次（同一次加载里缩放视口），另在 m.prts.wiki（Minerva）390 宽量一次；
// 每个宽度都是先量「前」、写上宽度量「后」、再摘掉。
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
const require = createRequire('/Users/starheart/Documents/Mooncell/prts-design/package.json');
const { chromium } = require('@playwright/test');

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const WORK = join(ROOT, 'build', 'enemy-icon');
const MODE = process.argv[2];
const CONC = Number(process.env.CONC ?? 8);
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36';
const PIXEL = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=', 'base64');
const WIDTHS = [1280, 1000, 390];
// 调用 敌人头像 的模板，按这个顺序给页面归类（一页用了多个时取第一个）
const CALLERS = ['敌方情报', '敌方情报pro', '特殊敌方情报', '登场敌人', 'EnemyDataMini', '敌人信息/common', '敌人信息/common2'];

const pageUrl = (base, title, skin) =>
  `${base}/w/${encodeURIComponent(title.replace(/ /g, '_')).replace(/%2F/g, '/')}${skin ? `?useskin=${skin}` : ''}`;

// ---- 页面里跑的函数 ----

function measure() {
  const root = document.querySelector('#mw-content-text .mw-parser-output');
  if (!root) return { error: 'no content' };
  const w = (el) => el.getBoundingClientRect().width;
  const icons = [...root.querySelectorAll('.enemyicon img.mw-file-element')].filter((i) => i.getClientRects().length);
  const small = icons.filter((i) => w(i) < (+i.getAttribute('width') || 0) - 1);
  const spill = icons.filter((i) => {
    const cell = i.closest('td, th');
    if (!cell) return false;
    const a = i.getBoundingClientRect(), b = cell.getBoundingClientRect();
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
        out.push(`${c.tagName.toLowerCase()}.${String(c.className).split(' ').filter((x) => !x.startsWith('mw-') && !x.startsWith('jquery')).join('.')} ${Math.round(r.width)}`);
        continue;
      }
      if (cs.overflowX !== 'visible') continue;
      walk(c);
    }
  })(root);
  return {
    icons: icons.length, small: small.length,
    min: icons.length ? Math.round(Math.min(...icons.map(w))) : null,
    spill, pageW: document.documentElement.scrollWidth, contentW: Math.round(w(root)), out,
  };
}

// 预演：等于模板给外壳写 width:{{{px}}}px
function patch() {
  document.querySelectorAll('.enemyicon').forEach((box) => {
    const img = box.querySelector(':scope > span[typeof^="mw:File"] img, :scope > a img, :scope img.mw-file-element');
    if (img && img.getAttribute('width')) box.style.width = `${img.getAttribute('width')}px`;
  });
}

function unpatch() {
  document.querySelectorAll('.enemyicon').forEach((box) => box.style.removeProperty('width'));
}

function expand() {
  document.querySelectorAll('.mw-collapsible.mw-collapsed').forEach((c) => {
    const t = c.querySelector('.mw-collapsible-toggle');
    if (t) try { t.click(); } catch (e) {}
    c.classList.remove('mw-collapsed');
  });
  // Minerva 的章节默认收起
  document.querySelectorAll('.collapsible-block').forEach((s) => { s.hidden = false; s.classList.add('open-block'); });
}

// ---- 驱动 ----

async function newContext(browser, mobile) {
  const ctx = await browser.newContext({ userAgent: UA, ...(mobile ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } : {}) });
  await ctx.route('**/*', (route) => {
    const type = route.request().resourceType();
    if (type === 'image') return route.fulfill({ status: 200, contentType: 'image/png', body: PIXEL });
    if (type === 'media') return route.abort();
    return route.continue();
  });
  return ctx;
}

async function load(ctx, url, width) {
  const page = await ctx.newPage();
  if (width) await page.setViewportSize({ width, height: 900 });
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 90000 });
  await Promise.race([page.waitForLoadState('load'), page.waitForTimeout(4000)]);
  await page.evaluate(expand);
  await page.waitForTimeout(200);
  return page;
}

async function beforeAfter(page) {
  const before = await page.evaluate(measure);
  await page.evaluate(patch);
  await page.waitForTimeout(100);
  const after = await page.evaluate(measure);
  await page.evaluate(unpatch);
  return { before, after };
}

async function measurePage(desk, mob, title) {
  const rec = { title };
  try {
    const page = await load(desk, pageUrl('https://prts.wiki', title, 'arknights'), WIDTHS[0]);
    for (const width of WIDTHS) {
      await page.setViewportSize({ width, height: 900 });
      await page.waitForTimeout(250);
      rec[width] = await beforeAfter(page);
    }
    await page.close();
    const m = await load(mob, pageUrl('https://m.prts.wiki', title));
    rec.minerva = await beforeAfter(m);
    await m.close();
  } catch (e) {
    rec.error = String(e).slice(0, 200);
  }
  return rec;
}

const ENVS = [...WIDTHS.map(String), 'minerva'];
const brief = (m) => (m.error ? m.error : `头像 ${m.icons}，缩小 ${m.small}（最小 ${m.min}），伸出格子 ${m.spill}，整页 ${m.pageW}${m.out.length ? `，伸出正文栏 ${m.out.join('；')}` : ''}`);
// 改后变差：整页变宽、伸出正文栏的变多、头像伸出格子
const worse = (r, env) => r[env] && !r[env].before.error && (r[env].after.pageW > r[env].before.pageW || r[env].after.out.length > r[env].before.out.length || r[env].after.spill > r[env].before.spill);

async function apiList(browser, params) {
  const ctx = await browser.newContext({ userAgent: UA });
  const page = await ctx.newPage();
  await page.goto('https://prts.wiki/api.php', { waitUntil: 'domcontentloaded' });
  const res = await page.evaluate(async (params) => {
    const out = [];
    let cont = {};
    for (;;) {
      const q = new URLSearchParams({ action: 'query', format: 'json', formatversion: '2', ...params, ...cont });
      const j = await (await fetch(`/api.php?${q}`)).json();
      out.push(j.query);
      if (!j.continue) return out;
      cont = j.continue;
    }
  }, params);
  await ctx.close();
  return res;
}

mkdirSync(WORK, { recursive: true });

if (MODE === 'sample') {
  const per = Number(process.argv[3] ?? 25);
  const browser = await chromium.launch({ channel: 'chromium' });
  const pages = (await apiList(browser, { list: 'embeddedin', eititle: '模板:敌人头像', einamespace: '0', eilimit: 'max' }))
    .flatMap((q) => q.embeddedin.map((p) => p.title));
  // 归类：每 50 页一批查用了哪些调用方模板
  const kind = new Map(pages.map((t) => [t, '正文直接调用']));
  for (let i = 0; i < pages.length; i += 50) {
    const qs = await apiList(browser, { prop: 'templates', titles: pages.slice(i, i + 50).join('|'), tltemplates: CALLERS.map((c) => `模板:${c}`).join('|'), tllimit: 'max' });
    for (const q of qs) for (const p of q.pages) {
      const used = new Set((p.templates ?? []).map((t) => t.title.replace(/^模板:/, '')));
      const first = CALLERS.find((c) => used.has(c));
      if (first && kind.get(p.title) === '正文直接调用') kind.set(p.title, first);
    }
  }
  const groups = {};
  for (const [t, k] of kind) (groups[k] ??= []).push(t);
  const titles = [];
  for (const [k, ts] of Object.entries(groups)) {
    const step = Math.max(1, Math.floor(ts.length / per));
    const pick = ts.filter((_, i) => i % step === 0).slice(0, per);
    console.log(`${k}：${ts.length} 页，抽 ${pick.length}`);
    titles.push(...pick.map((t) => [k, t]));
  }
  const recs = [];
  let next = 0;
  await Promise.all(Array.from({ length: CONC }, async () => {
    const desk = await newContext(browser, false), mob = await newContext(browser, true);
    while (next < titles.length) {
      const [k, t] = titles[next++];
      recs.push({ kind: k, ...(await measurePage(desk, mob, t)) });
      if (recs.length % 50 === 0) console.log(`  ${recs.length} / ${titles.length}`);
    }
    await desk.close(); await mob.close();
  }));
  await browser.close();
  writeFileSync(join(WORK, 'sample.jsonl'), recs.map((r) => JSON.stringify(r)).join('\n') + '\n');
  // 每类：每个环境下 前 / 后 被挤小的页数与头像数、改后变差的页
  const lines = ['| 类型 | 页 | 环境 | 有缩小的页 前 → 后 | 缩小头像 前 → 后 | 最小头像 前 → 后 | 改后变差的页 |', '| --- | ---: | --- | --- | --- | --- | --- |'];
  for (const k of Object.keys(groups)) {
    const rs = recs.filter((r) => r.kind === k && !r.error);
    for (const env of ENVS) {
      const ok = rs.filter((r) => r[env] && !r[env].before.error);
      if (!ok.length) continue;
      const pg = (s) => ok.filter((r) => r[env][s].small).length;
      const n = (s) => ok.reduce((a, r) => a + r[env][s].small, 0);
      const mins = (s) => { const v = ok.map((r) => r[env][s].min).filter((x) => x != null); return v.length ? Math.min(...v) : '-'; };
      const bad = ok.filter((r) => worse(r, env)).map((r) => r.title);
      lines.push(`| ${k} | ${ok.length} | ${env} | ${pg('before')} → ${pg('after')} | ${n('before')} → ${n('after')} | ${mins('before')} → ${mins('after')} | ${bad.length}${bad.length ? `：${bad.slice(0, 4).join('、')}` : ''} |`);
    }
  }
  const failed = recs.filter((r) => r.error);
  lines.push('', `失败 ${failed.length} 页${failed.length ? `：${failed.map((r) => r.title).join('、')}` : ''}`);
  lines.push('', '## 改后变差的页', '');
  for (const r of recs.filter((r) => !r.error)) {
    for (const env of ENVS.filter((e) => worse(r, e))) lines.push(`- ${r.title}（${r.kind}，${env}）`, `  - 前 ${brief(r[env].before)}`, `  - 后 ${brief(r[env].after)}`);
  }
  writeFileSync(join(WORK, 'summary.md'), lines.join('\n') + '\n');
  console.log(lines.join('\n'));
} else if (MODE === 'page') {
  const browser = await chromium.launch({ channel: 'chromium' });
  const desk = await newContext(browser, false), mob = await newContext(browser, true);
  const rec = await measurePage(desk, mob, process.argv[3]);
  for (const env of ENVS) if (rec[env]) console.log(`${env}\n  前 ${brief(rec[env].before)}\n  后 ${brief(rec[env].after)}`);
  if (rec.error) console.log(rec.error);
  await browser.close();
} else {
  console.error('用法：node scripts/enemy_icon_measure.mjs sample [每类页数] | page <标题>');
  process.exit(1);
}
