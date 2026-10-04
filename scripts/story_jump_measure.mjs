// 剧情跳转按钮（模板:剧情跳转）文字被裁：框写死 height:41px; overflow:hidden; line-height:initial，
// 新皮肤正文 16px 思源黑体，两行 46px 放不下。拟改成 font-size:14px; line-height:19px（同 Vector 的 14px，两行 38px）。
// 配合 scripts/story_jump_apply.py，见 migration/story-play-button/README.md。
//   node scripts/story_jump_measure.mjs sample [页数]   # 嵌入页固定间隔抽样，默认 40；页内预演改法，量改前改后被裁的按钮数
//   node scripts/story_jump_measure.mjs page 标题…      # 指定页面
import { createRequire } from 'node:module';
const require = createRequire('/Users/starheart/Documents/Mooncell/prts-design/package.json');
const { chromium, webkit } = require('@playwright/test');

const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36';
const PATCH = 'font-size:14px;line-height:19px';
const pageUrl = (base, title, skin) =>
  `${base}/w/${encodeURIComponent(title.replace(/ /g, '_')).replace(/%2F/g, '/')}?${skin ? `useskin=${skin}&` : ''}sjm=${Date.now()}`;

// 按钮的文字框：剧情跳转 写的 height:41px + overflow:hidden；改后行内已有 PATCH 的也认
function boxes() {
  return [...document.querySelectorAll('#mw-content-text div[style*="width: 141px"][style*="height: 41px"]')].filter((b) => b.getClientRects().length);
}

function measure(src) {
  const bs = (0, eval)(`(${src})`)();
  const clipped = bs.filter((b) => b.scrollHeight > b.clientHeight + 1 || b.scrollWidth > b.clientWidth + 1);
  return { buttons: bs.length, clipped: clipped.length, sample: clipped.slice(0, 2).map((b) => b.innerText.replace(/\n/g, '/')).join('，'), pageW: document.documentElement.scrollWidth };
}

function patch([src, css]) {
  (0, eval)(`(${src})`)().forEach((b) => { b.style.lineHeight = ''; b.setAttribute('style', `${b.getAttribute('style').replace(/line-height:\s*initial;?/, '')};${css}`); });
}

const envs = [
  ['chromium', 'https://prts.wiki', 'arknights', 1000], ['chromium', 'https://prts.wiki', 'arknights', 390],
  ['webkit', 'https://prts.wiki', 'arknights', 1000], ['chromium', 'https://prts.wiki', 'vector', 1000],
  ['chromium', 'https://m.prts.wiki', '', 390],
];

async function run(titles) {
  const browsers = { chromium: await chromium.launch({ channel: 'chromium' }), webkit: await webkit.launch() };
  const total = Object.fromEntries(envs.map((e) => [e.join(' '), { pages: 0, buttons: 0, before: 0, after: 0, wider: 0, ex: [] }]));
  for (const title of titles) {
    for (const env of envs) {
      const [eng, base, skin, width] = env;
      const ctx = await browsers[eng].newContext({ viewport: { width, height: 900 }, ...(eng === 'webkit' ? {} : { userAgent: UA }) });
      const page = await ctx.newPage();
      try {
        await page.goto(pageUrl(base, title, skin), { waitUntil: 'load', timeout: 90000 });
        await page.waitForTimeout(400);
        const src = boxes.toString();
        const before = await page.evaluate(measure, src);
        await page.evaluate(patch, [src, PATCH]);
        await page.waitForTimeout(100);
        const after = await page.evaluate(measure, src);
        const t = total[env.join(' ')];
        if (before.buttons) {
          t.pages++; t.buttons += before.buttons; t.before += before.clipped; t.after += after.clipped;
          if (after.pageW > before.pageW) t.wider++;
          if (after.clipped && t.ex.length < 3) t.ex.push(`${title}：${after.sample}`);
        }
        if (titles.length <= 5) console.log(`${title} · ${eng} · ${skin || 'minerva'} · ${width}：按钮 ${before.buttons}，被裁 ${before.clipped} → ${after.clipped}${before.sample ? `（${before.sample}）` : ''}，整页 ${before.pageW} → ${after.pageW}`);
      } catch (e) {
        console.log(`${title} · ${env.join(' ')}：${String(e).slice(0, 100)}`);
      }
      await ctx.close();
    }
  }
  for (const b of Object.values(browsers)) await b.close();
  for (const [env, t] of Object.entries(total)) {
    console.log(`${env}：${t.pages} 页 ${t.buttons} 个按钮，被裁 ${t.before} → ${t.after}，整页变宽 ${t.wider} 页${t.ex.length ? `；改后仍被裁：${t.ex.join('；')}` : ''}`);
  }
}

if (process.argv[2] === 'page') {
  await run(process.argv.slice(3));
} else if (process.argv[2] === 'sample') {
  const n = Number(process.argv[3] ?? 40);
  const browser = await chromium.launch({ channel: 'chromium' });
  const ctx = await browser.newContext({ userAgent: UA });
  const page = await ctx.newPage();
  await page.goto('https://prts.wiki/api.php', { waitUntil: 'domcontentloaded' });
  const all = await page.evaluate(async () => {
    const out = [];
    let cont = {};
    for (;;) {
      const q = new URLSearchParams({ action: 'query', format: 'json', list: 'embeddedin', eititle: '模板:剧情跳转', einamespace: '0', eilimit: 'max', ...cont });
      const j = await (await fetch(`/api.php?${q}`)).json();
      out.push(...j.query.embeddedin.map((p) => p.title));
      if (!j.continue) return out;
      cont = j.continue;
    }
  });
  await browser.close();
  const step = Math.max(1, Math.floor(all.length / n));
  const titles = all.filter((_, i) => i % step === 0).slice(0, n);
  console.log(`主名字空间嵌入页 ${all.length}，抽 ${titles.length}（每 ${step} 个取 1）`);
  await run(titles);
} else {
  console.error('用法：node scripts/story_jump_measure.mjs sample [页数] | page <标题…>');
  process.exit(1);
}
