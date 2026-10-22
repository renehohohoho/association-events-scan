// usage: node render.js <url> <outprefix> [waitMs]
const { chromium } = require('playwright-core');
const fs = require('fs');
(async () => {
  const [url, out, wait] = process.argv.slice(2);
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--no-sandbox'] });
  const ctx = await browser.newContext({ userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36', ignoreHTTPSErrors: false });
  const page = await ctx.newPage();
  let status = null;
  try {
    const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 60000 });
    status = resp && resp.status();
    await page.waitForLoadState('networkidle', { timeout: 30000 }).catch(() => {});
    await page.waitForTimeout(parseInt(wait || '4000'));
  } catch (e) { console.log('ERR', e.message); }
  const text = await page.evaluate(() => document.body ? document.body.innerText : '');
  const links = await page.evaluate(() => [...document.querySelectorAll('a[href]')].map(a => (a.innerText.trim().replace(/\s+/g, ' ') + ' | ' + a.href)));
  fs.writeFileSync(out + '.txt', text);
  fs.writeFileSync(out + '.links.txt', links.join('\n'));
  console.log(url, 'status', status, 'textlen', text.length, 'links', links.length);
  await browser.close();
})();
