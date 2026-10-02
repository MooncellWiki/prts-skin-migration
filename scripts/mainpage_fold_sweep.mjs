// 量现网首页各皮肤的「折叠线预算」：逐宽度算出让入口第一排整排露出（底下留 12px）
// 所需的 --mp-fold-above，按设计稿的视口断点分档取最大值，对照 build_mainpage_sandbox.py 的 FOLD_ABOVE。
// 视口压矮（默认 560），图框被压到最窄 / 说明栏最高，量的是最紧的情形。
//
//   node scripts/mainpage_fold_sweep.mjs                     # 四种皮肤全扫
//   node scripts/mainpage_fold_sweep.mjs arknights minerva   # 只扫这几种
//   STEP=5 FROM=1100 TO=1400 node scripts/mainpage_fold_sweep.mjs vector-2022
//
// Playwright 借用 ../prts-design 的依赖（pnpm install 过即可）；要用完整 Chromium
// （channel: 'chromium'），headless shell 会被 prts.wiki 的 Tengine 403。
import { createRequire } from 'node:module';

const require = createRequire(new URL('../../prts-design/package.json', import.meta.url));
const { chromium } = require('@playwright/test');

const SKINS = { arknights: 'useskin=arknights', vector: 'useskin=vector', 'vector-2022': 'useskin=vector-2022', minerva: 'useformat=mobile' };
const BANDS = [[1120, Infinity], [850, 1119], [690, 849], [640, 689], [0, 639]];   // 设计稿按视口切说明栏 / 入口格的断点
const H = Number(process.env.H ?? 560);
const FROM = Number(process.env.FROM ?? 360), TO = Number(process.env.TO ?? 1700), STEP = Number(process.env.STEP ?? 10);

const browser = await chromium.launch({ channel: 'chromium' });
for (const skin of process.argv.slice(2).length ? process.argv.slice(2) : Object.keys(SKINS)) {
  const page = await (await browser.newContext({ viewport: { width: 1440, height: H } })).newPage();
  // 随便带个参数绕开 CDN 上 ?useskin= 变体的缓存（purge 只清规范 URL）
  await page.goto(`https://prts.wiki/w/%E9%A6%96%E9%A1%B5?${SKINS[skin]}&nocache=${Date.now()}`, { waitUntil: 'load' });
  await page.evaluate(() => document.fonts.ready);
  const rows = [];
  for (let w = FROM; w <= TO; w += STEP) {
    await page.setViewportSize({ width: w, height: H });
    await page.waitForTimeout(60);
    rows.push(await page.evaluate(() => {
      const hero = document.querySelector('.mp-hero'), cs = getComputedStyle(hero);
      const px = (name) => parseFloat(cs.getPropertyValue(name)) || 0;
      const top = hero.getBoundingClientRect().top + scrollY;
      const pic = document.querySelector('.swiper-slide-active .mp-hero__pic').getBoundingClientRect().height;
      const tile = document.querySelector('.mp-nav__tile').getBoundingClientRect().bottom + scrollY;
      const n = px('--mp-fold-n');
      // 预算里除 Hero 上方以外的各项（设计稿的值），need = 实际要扣掉的 − 这些 = Hero 上方该填多少
      const budget = px('--mp-fold-caption') + n * px('--mp-fold-event') + Math.min(n, 1) * px('--mp-fold-events-label') + px('--mp-fold-below');
      return { w: innerWidth, top: Math.round(top), need: Math.ceil(tile + 12 - pic - budget), now: px('--mp-fold-above') };
    }));
  }
  console.log(`\n== ${skin}（视口高 ${H}，${FROM}–${TO} 每 ${STEP}px）`);
  for (const [lo, hi] of BANDS) {
    const band = rows.filter((r) => r.w >= lo && r.w <= hi);
    if (!band.length) continue;
    const max = band.reduce((a, b) => (b.need > a.need ? b : a));
    const min = Math.min(...band.map((r) => r.need));
    const label = hi === Infinity ? `≥${lo}` : `${lo}–${hi}`;
    const now = [...new Set(band.map((r) => r.now))].join('/');
    console.log(`  ${label.padEnd(9)} 需要 ${max.need}（${max.w}px 处；档内最小 ${min}）  现值 ${now}  Hero 上方 ${Math.min(...band.map((r) => r.top))}–${Math.max(...band.map((r) => r.top))}`);
  }
}
await browser.close();
