// Load my.asq.org calendar with the largest page size, dump text + event links.
// usage: node asq_all.js <outprefix>
const { chromium } = require('playwright-core');
const fs = require('fs');
(async () => {
  const out = process.argv[2];
  const browser = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--no-sandbox'] });
  const page = await (await browser.newContext({ userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36' })).newPage();
  await page.goto('https://my.asq.org/events/calendar', { waitUntil: 'networkidle', timeout: 90000 });
  const opts = await page.$$eval('#MainCopy_ctl06_ddlResultsPerPage option', os => os.map(o => o.value)); console.log('opts', opts); await page.selectOption('#MainCopy_ctl06_ddlResultsPerPage', opts[opts.length - 1]);
  await page.waitForLoadState('networkidle', { timeout: 60000 }).catch(() => {});
  await page.waitForTimeout(6000);
  const text = await page.evaluate(() => document.body.innerText);
  const links = await page.evaluate(() => [...document.querySelectorAll('a[href*="event-description"]')].map(a => a.innerText.trim().replace(/\s+/g, ' ') + ' | ' + a.href));
  fs.writeFileSync(out + '.txt', text);
  fs.writeFileSync(out + '.links.txt', [...new Set(links)].join('\n'));
  console.log('textlen', text.length, 'eventlinks', new Set(links).size);
  await browser.close();
})();
