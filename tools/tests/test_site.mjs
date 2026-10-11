// Сквозной тест интерфейса (Playwright). Запуск: node tools/tests/test_site.mjs
// Нужен пакет playwright; путь к Chromium можно задать в CHROMIUM=/usr/bin/chromium
import { chromium } from 'playwright';
import { fileURLToPath, pathToFileURL } from 'url';
import path from 'path';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const url = f => pathToFileURL(path.join(root, f)).href;
const b = await chromium.launch(process.env.CHROMIUM ? { executablePath: process.env.CHROMIUM } : {});
const p = await b.newPage({ viewport: { width: 1440, height: 900 }, acceptDownloads: true });
const errs = []; p.on('pageerror', e => errs.push(e.message));
const ok = (c, m) => { console.log((c ? 'OK  ' : 'FAIL') + ' ' + m); if (!c) process.exitCode = 1; };
await p.goto(url('index.html'));
await p.click('aside [data-open-params]');
await p.fill('#p_V_SRV', '110'); await p.fill('#p_HQ_SRV_IP', '10.0.200.20');
await p.click('[data-apply]');
ok(await p.$eval('#params', e => e.open), 'ошибочные параметры не применяются');
await p.fill('#p_HQ_SRV_IP', '10.0.100.20'); await p.click('[data-apply]');
ok((await p.$eval('#t4-1 code', e => e.textContent)).includes('enp0s9.110'), 'команды пересобраны');
await p.click('.filter [data-f="HQ-RTR"]');
const [dl] = await Promise.all([p.waitForEvent('download'), p.click('[data-download]')]);
ok(dl.suggestedFilename() === 'hq-rtr.sh', 'скачивание скрипта ВМ');
await p.click('.filter [data-f=""]'); await p.click('#t1-2 .done');
await p.reload();
ok(await p.$eval('#t4-1 code', e => e.textContent.includes('.110')), 'параметры сохраняются');
ok(await p.$eval('#t1-2 .done input', e => e.checked), 'отметки сохраняются');
await p.goto(url('module2.html'));
ok(await p.$eval('#m2t1-1 code', e => e.textContent.includes('.110')), 'параметры общие для модулей');
ok(errs.length === 0, 'нет ошибок JS ' + errs.join('; '));
await b.close();
