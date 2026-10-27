/**
 * اندازه‌گیری ارتفاع واقعی بلوک‌ها در موتور رندر (برای پلنر بسته‌بندی).
 * اجرا: node measure.mjs <input.html> <output.json>
 * خروجی: [{bid, top, height}] برحسب میلی‌متر — فاصلهٔ بالای هر بلوک تا بلوک بعدی
 * (شامل margin) تا شبیه‌سازی صفحه‌بندی دقیق باشد.
 */
import { writeFileSync } from "node:fs";
import path from "node:path";
import puppeteer from "puppeteer-core";

const [, , inputHtml, outputJson] = process.argv;

async function launchBrowser() {
  if (process.env.CHROME_PATH) {
    return puppeteer.launch({
      executablePath: process.env.CHROME_PATH,
      args: ["--no-sandbox", "--disable-dev-shm-usage"], headless: true,
    });
  }
  const chromium = (await import("@sparticuz/chromium")).default;
  const ld = `/tmp/humsyar-chromium-libs/lib:${process.env.LD_LIBRARY_PATH || ""}`;
  return puppeteer.launch({
    args: [...chromium.args, "--no-sandbox", "--disable-dev-shm-usage"],
    executablePath: await chromium.executablePath(), headless: true,
    env: { ...process.env, LD_LIBRARY_PATH: ld },
  });
}

const browser = await launchBrowser();
try {
  const page = await browser.newPage();
  // عرض ناحیهٔ متن A4 با حاشیهٔ ۱۴mm دو طرف: 182mm ≈ 688px
  await page.setViewport({ width: 688, height: 1200 });
  await page.emulateMediaType("print");
  await page.goto(`file://${path.resolve(inputHtml)}`, { waitUntil: "networkidle0", timeout: 120000 });
  await page.evaluate(() => document.fonts.ready);
  const data = await page.evaluate(() => {
    const PX2MM = 25.4 / 96;
    const els = [...document.querySelectorAll("[data-bid]")];
    const rects = els.map((el) => ({ bid: el.dataset.bid, r: el.getBoundingClientRect() }));
    const blocks = rects.map((it, i) => {
      const next = rects[i + 1];
      const h = next ? next.r.top - it.r.top : it.r.height;
      return { bid: it.bid, top: +(it.r.top * PX2MM).toFixed(2), height: +(h * PX2MM).toFixed(2) };
    });
    const tocLinks = [...document.querySelectorAll(".toc a")].map((a) => {
      const r = a.getBoundingClientRect();
      return { href: a.getAttribute("href"), x: +(r.left * PX2MM).toFixed(2),
               y: +(r.top * PX2MM).toFixed(2), w: +(r.width * PX2MM).toFixed(2),
               h: +(r.height * PX2MM).toFixed(2) };
    });
    return { blocks, tocLinks };
  });
  writeFileSync(outputJson, JSON.stringify(data));
  console.log("MEASURE_OK", data.blocks.length, data.tocLinks.length);
} finally {
  await browser.close();
}
