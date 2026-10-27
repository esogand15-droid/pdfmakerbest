/**
 * HamsYar PDF Renderer — تبدیل HTML صفحه‌آرایی‌شده به PDF با Chromium.
 *
 * اجرا: node render.mjs <input.html> <output.pdf> <config.json>
 * config: { headerRight, headerLeft, footerText, fontFile }
 *
 * انتخاب مرورگر:
 *  ۱) اگر CHROME_PATH تنظیم شده باشد، همان (محیط توسعهٔ معمولی/CI).
 *  ۲) وگرنه @sparticuz/chromium (باینری داخل npm) + استخراج کتابخانه‌های
 *     همراهش (al2023) و تنظیم LD_LIBRARY_PATH — برای محیط‌های بدون مرورگر سیستمی.
 */
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { brotliDecompressSync } from "node:zlib";
import { execSync } from "node:child_process";
import path from "node:path";
import puppeteer from "puppeteer-core";

const [, , inputHtml, outputPdf, configPath] = process.argv;
const cfg = JSON.parse(readFileSync(configPath, "utf8"));

async function launchBrowser() {
  if (process.env.CHROME_PATH) {
    return puppeteer.launch({
      executablePath: process.env.CHROME_PATH,
      args: ["--no-sandbox", "--disable-dev-shm-usage"],
      headless: true,
    });
  }
  const chromium = (await import("@sparticuz/chromium")).default;
  // کتابخانه‌های همراه پکیج (nspr/nss) را یک بار در tmp باز می‌کنیم
  const libDir = "/tmp/humsyar-chromium-libs";
  if (!existsSync(path.join(libDir, "lib", "libnspr4.so"))) {
    const brPath = path.join(
      path.dirname(new URL(import.meta.url).pathname),
      "node_modules/@sparticuz/chromium/bin/al2023.tar.br");
    mkdirSync(libDir, { recursive: true });
    writeFileSync("/tmp/humsyar-al2023.tar", brotliDecompressSync(readFileSync(brPath)));
    execSync(`tar xf /tmp/humsyar-al2023.tar -C ${libDir}`);
  }
  const ld = `${libDir}/lib:${process.env.LD_LIBRARY_PATH || ""}`;
  return puppeteer.launch({
    args: [...chromium.args, "--no-sandbox", "--disable-dev-shm-usage"],
    executablePath: await chromium.executablePath(),
    headless: true,
    env: { ...process.env, LD_LIBRARY_PATH: ld },
  });
}

const fontFace = cfg.fontFile
  ? `@font-face{font-family:Vazirmatn;src:url(file://${cfg.fontFile})}` : "";
const hdrStyle = `<style>${fontFace}
  .h{width:100%;font-family:Vazirmatn,DejaVu Sans,sans-serif;font-size:7.8pt;color:#5d707e;
     padding:0 14mm;display:flex;justify-content:space-between;direction:rtl}
  .h .b{font-weight:700;color:#074f5c}
  .f{width:100%;font-family:Vazirmatn,DejaVu Sans,sans-serif;font-size:7.8pt;color:#5d707e;
     padding:0 14mm;display:flex;justify-content:space-between;direction:rtl}
  .f .p b{color:#074f5c}
</style>`;

const browser = await launchBrowser();
try {
  const page = await browser.newPage();
  await page.goto(`file://${path.resolve(inputHtml)}`, { waitUntil: "networkidle0", timeout: 120000 });
  await page.evaluate(() => document.fonts.ready);
  await page.pdf({
    path: outputPdf,
    format: "A4",
    printBackground: true,
    displayHeaderFooter: true,
    tagged: true,
    margin: { top: "15mm", bottom: "13mm", left: "14mm", right: "14mm" },
    headerTemplate: `${hdrStyle}<div class="h"><span>${cfg.headerRight || ""}</span><span class="b">${cfg.headerLeft || ""}</span></div>`,
    footerTemplate: `${hdrStyle}<div class="f"><span>${cfg.footerText || ""}</span><span class="p">صفحهٔ <b><span class="pageNumber"></span></b> از <span class="totalPages"></span></span></div>`,
  });
  console.log("RENDER_OK", outputPdf);
} finally {
  await browser.close();
}
