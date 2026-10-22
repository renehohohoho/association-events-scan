// usage: node details.js <urls.txt> <outdir>   (urls.txt lines: id<TAB>url)
const { chromium } = require('playwright-core');
const fs = require('fs');
(async () => {
  const [list, outdir] = process.argv.slice(2);
  fs.mkdirSync(outdir, { recursive: true });
  const items = fs.readFileSync(list, 'utf8').trim().split('\n').map(l => l.split('\t'));
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36' });
  const page = await ctx.newPage();
  for (const [id, url] of items) {
    try {
      const r = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
      await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
      await page.waitForTimeout(1500);
      const text = await page.evaluate(() => document.body.innerText);
      fs.writeFileSync(`${outdir}/${id}.txt`, url + '\n' + text);
      console.log(id, r && r.status(), text.length);
    } catch (e) { console.log(id, 'ERR', e.message.split('\n')[0]); }
  }
  await browser.close();
})();
