// 剧情播放按钮被挤小：量真实页面上 模板:剧情简介 的播放按钮尺寸、整页宽。
// 配合 scripts/story_play_button_apply.py，见 migration/story-play-button/README.md。
//   node scripts/story_play_button_measure.mjs [标题]      # 默认 情报处理室；各皮肤 / 引擎 / 宽度量一遍
//   UNDO=1 …                                              # 模板改完后：同一次加载里先摘掉外套的样式量「前」，再放回去量「后」
import { createRequire } from 'node:module';
const require = createRequire('/Users/starheart/Documents/Mooncell/prts-design/package.json');
const { chromium, webkit } = require('@playwright/test');

const UNDO = process.env.UNDO === '1';
const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36';
const title = process.argv[2] ?? '情报处理室';
const pageUrl = (base, skin) =>
  `${base}/w/${encodeURIComponent(title.replace(/ /g, '_')).replace(/%2F/g, '/')}?${skin ? `useskin=${skin}&` : ''}spb=${Date.now()}`;

// ---- 页面里跑的函数 ----

function measure() {
  const root = document.querySelector('#mw-content-text .mw-parser-output');
  if (!root) return { error: 'no content' };
  const imgs = [...root.querySelectorAll('td.event-story-play img')].filter((i) => i.getClientRects().length);
  const w = (el) => el.getBoundingClientRect().width;
  const small = imgs.filter((i) => w(i) < (+i.getAttribute('width') || 0) - 1);
  const spill = imgs.filter((i) => {
    const a = i.getBoundingClientRect(), b = i.closest('td').getBoundingClientRect();
    return a.right > b.right + 1 || a.left < b.left - 1;
  }).length;
  const cells = imgs.map((i) => w(i.closest('td')));
  // 最外层的「伸出正文栏」的元素；被裁剪 / 滚动容器包住的不算
  const limit = root.getBoundingClientRect().right + 1;
  const out = [];
  (function walk(el) {
    for (const c of el.children) {
      const cs = getComputedStyle(c);
      if (cs.display === 'none' || cs.position === 'fixed') continue;
      const r = c.getBoundingClientRect();
      if (r.width && r.height && r.right > limit) {
        out.push(`${c.tagName.toLowerCase()}.${String(c.className).split(' ').pop()}「${c.innerText.trim().slice(0, 6)}」${Math.round(r.width)}`);
        continue;
      }
      if (cs.overflowX !== 'visible') continue;
      walk(c);
    }
  })(root);
  return {
    buttons: imgs.length, small: small.length,
    min: imgs.length ? Math.round(Math.min(...imgs.map(w))) : null,
    max: imgs.length ? Math.round(Math.max(...imgs.map(w))) : null,
    cellMin: cells.length ? Math.round(Math.min(...cells)) : null,
    spill, pageW: document.documentElement.scrollWidth, contentW: Math.round(root.getBoundingClientRect().width), out,
    // 情报处理室手机索引表：行宽 / 表宽（display:block 时行组按内容收缩，填不满）
    index: [...root.querySelectorAll('table.intelligence-room-mobile-index')].filter((t) => t.getClientRects().length)
      .map((t) => `${Math.round(w(t.rows[0]))}/${Math.round(w(t))}`).join(' '),
    // 情报处理室「特别行动记述」的封面（rowspan 的 th.nomobile）：宽度，或「隐」
    covers: [...new Set([...root.querySelectorAll('table.intelligence-room-story-table > tbody > tr > th.nomobile[rowspan]')]
      .map((th) => (getComputedStyle(th).display === 'none' ? '隐' : Math.round(w(th.querySelector('img'))))))].join('/'),
  };
}

// 外套是模板写的 <span style="display:inline-block;width:50px">，摘掉样式 = 改前
function undo() {
  document.querySelectorAll('td.event-story-play > span[style*="inline-block"]').forEach((s) => {
    s.dataset.spb = s.getAttribute('style');
    s.removeAttribute('style');
  });
}

function redo() {
  document.querySelectorAll('td.event-story-play > span[data-spb]').forEach((s) => s.setAttribute('style', s.dataset.spb));
}

// ---- 驱动 ----

const brief = (m) => (m.error ? m.error : `按钮 ${m.buttons}，缩小 ${m.small}（${m.min}–${m.max}px，格子最窄 ${m.cellMin}px），伸出格子 ${m.spill}，整页 ${m.pageW}，正文栏 ${m.contentW}${m.index ? `，索引表 ${m.index}` : ''}${m.covers ? `，封面 ${m.covers}` : ''}${m.out.length ? `，伸出正文栏 ${m.out.length} 个：${[...new Set(m.out)].slice(0, 3).join('；')}` : ''}`);

const envs = [
  ['chromium', 'https://prts.wiki', 'arknights', 320], ['chromium', 'https://prts.wiki', 'arknights', 360],
  ['chromium', 'https://prts.wiki', 'arknights', 390], ['chromium', 'https://prts.wiki', 'arknights', 600],
  ['chromium', 'https://prts.wiki', 'arknights', 640], ['chromium', 'https://prts.wiki', 'arknights', 720],
  ['chromium', 'https://prts.wiki', 'arknights', 846], ['chromium', 'https://prts.wiki', 'arknights', 899],
  ['chromium', 'https://prts.wiki', 'arknights', 900], ['chromium', 'https://prts.wiki', 'arknights', 1000],
  ['chromium', 'https://prts.wiki', 'arknights', 1100], ['chromium', 'https://prts.wiki', 'arknights', 1280],
  ['chromium', 'https://prts.wiki', 'arknights', 1440], ['chromium', 'https://prts.wiki', 'arknights', 1920],
  ['webkit', 'https://prts.wiki', 'arknights', 390], ['webkit', 'https://prts.wiki', 'arknights', 600], ['webkit', 'https://prts.wiki', 'arknights', 846], ['webkit', 'https://prts.wiki', 'arknights', 1000],
  ['chromium', 'https://prts.wiki', 'vector', 1000], ['chromium', 'https://prts.wiki', 'vector', 1280],
  ['chromium', 'https://m.prts.wiki', '', 390], ['webkit', 'https://m.prts.wiki', '', 390],
];
const browsers = {};
for (const [eng, base, skin, width] of envs) {
  browsers[eng] ??= await (eng === 'webkit' ? webkit.launch() : chromium.launch({ channel: 'chromium' }));
  const ctx = await browsers[eng].newContext({
    viewport: { width, height: 844 },
    ...(eng === 'webkit' ? {} : { userAgent: UA }),
    ...(base.includes('//m.') ? { isMobile: eng !== 'webkit', hasTouch: true } : {}),
  });
  const page = await ctx.newPage();
  let line;
  try {
    await page.goto(pageUrl(base, skin), { waitUntil: 'load', timeout: 90000 });
    await page.waitForTimeout(800);
    // Minerva 的章节默认收起
    await page.evaluate(() => document.querySelectorAll('.collapsible-block').forEach((s) => { s.hidden = false; s.classList.add('open-block'); }));
    if (UNDO) await page.evaluate(undo);
    const before = await page.evaluate(measure);
    line = `  ${UNDO ? '前 ' : ''}${brief(before)}`;
    if (UNDO) {
      await page.evaluate(redo);
      await page.waitForTimeout(300);
      line += `\n  后 ${brief(await page.evaluate(measure))}`;
    }
  } catch (e) {
    line = `  ${String(e).slice(0, 200)}`;
  }
  console.log(`${eng} · ${skin || 'minerva'} · ${width}\n${line}`);
  await ctx.close();
}
for (const b of Object.values(browsers)) await b.close();
