// 封面图被百分比列挤没的几页（情报处理室、好久不见、亘古长明、主题曲第十二 / 十三章预热）：量真实页面上封面的宽度、
// 竖排按钮格有没有出来、整页宽、伸出正文栏的表。配合 scripts/story_cover_apply.py、intelligence_room_nav_apply.py，
// 见 migration/story-play-button/README.md。
//   node scripts/story_cover_measure.mjs [标题…]
import { createRequire } from 'node:module';
const require = createRequire('/Users/starheart/Documents/Mooncell/prts-design/package.json');
const { chromium, webkit } = require('@playwright/test');

const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36';
const titles = process.argv.slice(2).length ? process.argv.slice(2) : ['情报处理室', '好久不见', '亘古长明', '主题曲第十二章预热', '主题曲第十三章预热'];
const pageUrl = (base, title, skin) =>
  `${base}/w/${encodeURIComponent(title.replace(/ /g, '_')).replace(/%2F/g, '/')}?${skin ? `useskin=${skin}&` : ''}scm=${Date.now()}`;

function measure() {
  const root = document.querySelector('#mw-content-text .mw-parser-output');
  const w = (el) => Math.round(el.getBoundingClientRect().width);
  // 封面：nomobile 表头格里文件名带「章节名称」或「情报处理室」的图；只看带 rowspan 的（公共事务实录那批不在这次范围）
  const covers = [...root.querySelectorAll('th.nomobile[rowspan] img.mw-file-element')]
    .filter((i) => /章节名称|情报处理室/.test(decodeURIComponent(i.src)))
    .map((i) => (getComputedStyle(i.closest('th')).display === 'none' ? '隐' : w(i)));
  const stacked = [...root.querySelectorAll('table > tbody > tr > td.nodesktop')].filter((td) => td.closest('table').querySelector(':scope > tbody > tr > th.nomobile[rowspan]'))
    .some((td) => getComputedStyle(td).display !== 'none');
  const wide = [...root.querySelectorAll('table')].filter((t) => !t.parentElement.closest('table') && t.getClientRects().length && w(t) > w(root) + 1).length;
  return `整页 ${document.documentElement.scrollWidth}，正文栏 ${w(root)}，封面 ${[...new Set(covers)].join('/') || '-'}（${covers.length}），竖排按钮 ${stacked ? '显示' : '不显示'}，伸出正文栏的表 ${wide}`;
}

const envs = [
  ...[390, 640, 680, 719, 720, 899, 900, 1000, 1280, 1440].map((w) => ['chromium', 'https://prts.wiki', 'arknights', w]),
  ['webkit', 'https://prts.wiki', 'arknights', 680], ['webkit', 'https://prts.wiki', 'arknights', 1000],
  ['chromium', 'https://prts.wiki', 'vector', 1000], ['chromium', 'https://m.prts.wiki', '', 390],
];
const browsers = { chromium: await chromium.launch({ channel: 'chromium' }), webkit: await webkit.launch() };
for (const title of titles) {
  console.log(`== ${title}`);
  for (const [eng, base, skin, width] of envs) {
    const ctx = await browsers[eng].newContext({ viewport: { width, height: 844 }, ...(eng === 'webkit' ? {} : { userAgent: UA }) });
    const page = await ctx.newPage();
    try {
      await page.goto(pageUrl(base, title, skin), { waitUntil: 'load', timeout: 90000 });
      await page.waitForTimeout(500);
      console.log(`  ${eng} · ${skin || 'minerva'} · ${width}：${await page.evaluate(measure)}`);
    } catch (e) {
      console.log(`  ${eng} · ${skin || 'minerva'} · ${width}：${String(e).slice(0, 120)}`);
    }
    await ctx.close();
  }
}
for (const b of Object.values(browsers)) await b.close();
