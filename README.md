# HamsYar PDF Engine — موتور جزوه‌ساز هام‌یار

موتور تولید جزوات علوم پایهٔ پزشکی: «جزوهٔ مادر» هر جلسه را به PDF نهایی حرفه‌ای تبدیل می‌کند —
مدل محتوای ساختاریافته + Design System فارسی/RTL + موتور چیدمان + رندر Chromium + QA خودکار.

گزارش ممیزی و تصمیم‌های معماری: [`docs/AUDIT.md`](docs/AUDIT.md) · مشخصات پروژه: [`docs/AGENT_PROMPT.md`](docs/AGENT_PROMPT.md)

## اجرای سریع

```bash
python3 -m venv .venv && .venv/bin/pip install -r engine/requirements.txt pillow
cd engine && npm install        # puppeteer-core + Chromium بسته‌بندی‌شده (آفلاین‌پسند)
# اگر Chrome سیستمی دارید، به‌جای npm کافی است: export CHROME_PATH=/path/to/chrome

# ساخت پایلوت (جلسهٔ ۱، مباحث ۴ و ۶)
../.venv/bin/python -m humsyar.cli build ../content/session01_pilot.yaml --edition final --out ../output

# تست‌ها
cd .. && .venv/bin/python -m pytest tests/ -q
```

خروجی‌ها در `output/`: فایل PDF، نسخهٔ HTML، `build_report.json` (تصمیم‌های چیدمان + QA)،
`review_report.md` (موارد نیازمند بازبینی انسانی) و رندر تصویری صفحات در `output/pages/`.

## گزینه‌های ساخت

| پرچم | مقادیر | پیش‌فرض | توضیح |
|---|---|---|---|
| `--edition` | `final` / `workbook` | `final` | workbook کادرهای یادداشت تیم را نگه می‌دارد |
| `--theme` | `a` / `b` | `a` | A: تیل بالینی · B: سرمه‌ای تحریریه‌ای (فقط توکن رنگ) |
| `--no-sources` | — | خاموش | پنهان‌کردن برچسب‌های منبع |

## استخراج از جزوهٔ مادر

```bash
../.venv/bin/python -m humsyar.cli extract ../HumsYar_NeuroAnat_Jalase1.pdf --out ../audit/s01
```

خروجی «پیش‌نویس استخراج» است (متن با ترتیب منطقی بازسازی‌شده + تصاویر اصلی + فهرست وضوح)؛
ساختاربندی آن به YAML گام ویرایشی جداست و وضعیت همهٔ بلوک‌ها تا تأیید تیم `needs_review` می‌ماند.

## افزودن جلسهٔ جدید

۱) استخراج (بالا) ← ۲) ساختاربندی در `content/sessionXX.yaml` با همان قرارداد بلوک‌ها ←
۳) `build` ← ۴) خواندن `review_report.md` و رندر صفحات ← ۵) تأیید علمی و تغییر وضعیت بلوک‌ها به `approved`.
هیچ تغییری در کد لازم نیست.

## قرارداد محتوای YAML (خلاصه)

هر بلوک: `id` پایدار، `type`، `status` (`extracted|editorial|needs_review|approved|unresolved_conflict`)،
`sources: [{book, pages, figure}]` و فیلدهای خودش. انواع بلوک: `section, paragraph, callout
(key|clinical|warning|bridge|conflict|exam), table, figure, process, dual_process, tree,
checklist, summary_box, team_note`.

نشانه‌گذاری درون‌متنی: `**برجسته**` · `[[term:فارسی|English]]` (اصطلاح دوزبانه) · `[en:Na+/K+-ATPase]` (لاتین ایزوله برای سلامت bidi).

**قانون محتوا:** موتور هرگز عدد/اصطلاح/مطلب علمی را تغییر نمی‌دهد و اختلاف منابع را حل نمی‌کند؛
ابهام‌ها در `review_report.md` ثبت می‌شوند.

## ساختار مخزن

```
content/            فایل‌های محتوای جلسات (YAML)
engine/humsyar/     model · planner · typeset · diagrams · build · qa · extract · cli
engine/themes/      Design System (CSS توکن‌محور)
engine/render.mjs   رندر Chromium
assets/fonts/       Vazirmatn (OFL — ببینید OFL.txt)
assets/figures/     تصاویر اصلی استخراج‌شده (دست‌نخورده)
tests/              تست‌های pytest (مدل، چیدمان، QA روی PDF واقعی، حقایق کنترلی)
docs/               ممیزی/معماری و مشخصات پروژه
output/             خروجی‌های ساخت
```
