"""
مولد کاور تمام‌صفحهٔ (full-bleed) هامزیار — هنر برداریِ تولیدشده با کد (SVG).

هر جلسه یک `cover_motif` دارد؛ موتیف‌ها هم‌خانواده‌اند (پس‌زمینهٔ تیل عمیق تا آبی شب،
خطوط درخشان) اما سوژه‌شان فرق می‌کند. فعلاً پیاده‌شده:
  histology-neuron-glia  (جلسهٔ ۱: نورون چندقطبی، آکسون میلین‌دار با گره‌های رانویه، سیناپس، گلیا)
موتیف‌های بعدی (spinal-cord, brainstem, cerebellum, ...) با همین قرارداد اضافه می‌شوند؛
موتیف ناشناخته خطای صریح می‌دهد، حدس زده نمی‌شود.

تولید قطعی (deterministic) است: بذر تصادفی از شمارهٔ جلسه می‌آید تا خروجی تکرارپذیر بماند
و کاور جلسات مختلف اندکی با هم فرق کنند.
"""
from __future__ import annotations

import math
import random
from html import escape

from .model import Session
from .planner import fa_num

# پالت کاور (هماهنگ با Design System؛ نسخهٔ تیره)
C = {
    "bg1": "#0A0F1E", "bg2": "#0D2B52", "bg3": "#0D1524",
    "glow": "#2DD4BF", "cyan": "#8FE8DC", "cyan2": "#3B82F6",
    "myelin": "#BFDBFE", "myelin2": "#93C5FD", "axon": "#7DD3FC",
    "soma": "#E0F2FE", "nucleus": "#2563EB", "ink": "#ffffff",
    "mint": "#99F6E4", "pale": "#BAE6FD",
}


def _branch(rng: random.Random, x: float, y: float, angle: float, length: float,
            width: float, depth: int, out: list[str], color: str) -> None:
    """شاخهٔ دندریتی بازگشتی با خم ملایم؛ خروجی پلی‌لاین‌های SVG."""
    if depth == 0 or length < 1.2:
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="0.55" fill="{color}" opacity="0.85"/>')
        return
    segs = 3
    pts = [(x, y)]
    a = angle
    cx, cy = x, y
    for _ in range(segs):
        a += rng.uniform(-0.16, 0.16)
        step = length / segs
        cx += math.cos(a) * step
        cy += math.sin(a) * step
        pts.append((cx, cy))
    pts_s = " ".join(f"{px:.1f},{py:.1f}" for px, py in pts)
    out.append(f'<polyline points="{pts_s}" fill="none" stroke="{color}" '
               f'stroke-width="{width:.2f}" stroke-linecap="round" opacity="0.92"/>')
    n = 2 if rng.random() < 0.82 else 3
    for _ in range(n):
        _branch(rng, cx, cy, a + rng.uniform(-0.62, 0.62),
                length * rng.uniform(0.62, 0.78), width * 0.68, depth - 1, out, color)


def _qpoint(p0, p1, p2, t: float):
    """نقطه روی منحنی بزیهٔ درجه‌دو؛ برای چیدن قطعات میلین روی مسیر آکسون."""
    mt = 1 - t
    return (mt * mt * p0[0] + 2 * mt * t * p1[0] + t * t * p2[0],
            mt * mt * p0[1] + 2 * mt * t * p1[1] + t * t * p2[1])


def motif_histology_neuron_glia(seed: int) -> str:
    rng = random.Random(seed)
    g: list[str] = []

    # ——— پس‌زمینه و هاله‌ها ———
    g.append(f'<rect width="210" height="297" fill="url(#bg)"/>')
    g.append(f'<ellipse cx="150" cy="70" rx="95" ry="70" fill="{C["glow"]}" opacity="0.07"/>')
    g.append(f'<ellipse cx="40" cy="235" rx="90" ry="85" fill="{C["cyan2"]}" opacity="0.06"/>')
    # ردّ محو مغز/نخاع: دو تودهٔ نرم بسیار کم‌رنگ
    g.append(f'<g opacity="0.055" fill="#ffffff"><ellipse cx="105" cy="46" rx="58" ry="30"/>'
             f'<rect x="99" y="60" width="12" height="52" rx="6"/></g>')
    # ذرات نورانی
    for _ in range(44):
        g.append(f'<circle cx="{rng.uniform(4,206):.1f}" cy="{rng.uniform(4,293):.1f}" '
                 f'r="{rng.uniform(0.25,0.7):.2f}" fill="#cfeee8" opacity="{rng.uniform(0.08,0.3):.2f}"/>')

    # ——— شبکهٔ گلیال پس‌زمینه (ستاره‌های آستروسیتی کم‌رنگ) ———
    for gx, gy, gs in [(24, 96, 7), (44, 168, 6), (178, 96, 6.5), (188, 178, 7.5),
                       (96, 252, 6), (24, 262, 5.5), (168, 262, 6)]:
        lines = []
        for k in range(6):
            ang = k * math.pi / 3 + rng.uniform(-0.2, 0.2)
            ln = gs * rng.uniform(0.7, 1.15)
            lines.append(f'<line x1="{gx}" y1="{gy}" x2="{gx + math.cos(ang) * ln:.1f}" '
                         f'y2="{gy + math.sin(ang) * ln:.1f}"/>')
        g.append(f'<g stroke="{C["cyan"]}" stroke-width="0.5" stroke-linecap="round" opacity="0.26">'
                 + "".join(lines) + f'<circle cx="{gx}" cy="{gy}" r="1.1" fill="{C["cyan"]}" stroke="none"/></g>')

    # ——— سیناپس (گوشهٔ بالا-چپ صحنه) ———
    sx, sy = 52.0, 112.0
    ves = "".join(
        f'<circle cx="{sx + rng.uniform(-3.4, 3.4):.1f}" cy="{sy + rng.uniform(0.5, 4.2):.1f}" '
        f'r="0.8" fill="{C["cyan"]}"/>'
        for _ in range(7))
    g.append(f'''<g opacity="0.95">
      <path d="M {sx-9} {sy-14} Q {sx-4} {sy-7} {sx-5.5} {sy-2}" fill="none" stroke="{C['axon']}" stroke-width="0.9"/>
      <circle cx="{sx}" cy="{sy}" r="5.6" fill="#0D2B52" stroke="{C['cyan']}" stroke-width="0.7"/>{ves}
      <path d="M {sx-7} {sy+8.4} Q {sx} {sy+11} {sx+7} {sy+8.4}" fill="none" stroke="{C['mint']}" stroke-width="0.8"/>
      <path d="M {sx-7} {sy+11.4} Q {sx} {sy+14} {sx+7} {sy+11.4}" fill="none" stroke="{C['mint']}" stroke-width="0.8" opacity="0.75"/>
      <circle cx="{sx-1.5}" cy="{sy+8}" r="0.55" fill="{C['cyan']}"/><circle cx="{sx+1.8}" cy="{sy+7.6}" r="0.55" fill="{C['cyan']}"/>
    </g>''')

    # ——— میکروگلیا (کوچک، موج‌دار) ———
    mx, my = 30.0, 196.0
    micro = [f'<circle cx="{mx}" cy="{my}" r="1.7" fill="{C["cyan"]}" opacity="0.8"/>']
    for k in range(6):
        ang = k * math.pi / 3 + 0.4
        x2 = mx + math.cos(ang) * 6.5
        y2 = my + math.sin(ang) * 6.5
        qx = mx + math.cos(ang + 0.5) * 3.6
        qy = my + math.sin(ang + 0.5) * 3.6
        micro.append(f'<path d="M {mx} {my} Q {qx:.1f} {qy:.1f} {x2:.1f} {y2:.1f}" fill="none" '
                     f'stroke="{C["cyan"]}" stroke-width="0.42" opacity="0.65"/>')
    g.append("".join(micro))

    # ——— نورون قهرمان ———
    soma_x, soma_y, soma_r = 130.0, 190.0, 12.5  # پایین‌تر: ناحیهٔ عنوان/برند/لوگو آزاد بماند
    dend: list[str] = []
    # شش دندریت اصلی: پرهیز از قطاع پایین-چپ (مسیر آکسون)
    for base_ang in (-2.75, -2.15, -1.55, -0.95, -0.35, 0.35, 2.95):
        _branch(rng, soma_x + math.cos(base_ang) * soma_r * 0.8,
                soma_y + math.sin(base_ang) * soma_r * 0.8,
                base_ang, rng.uniform(13, 17), 1.5, 4, dend, C["cyan"])
    g.append("".join(dend))

    # آکسون میلین‌دار: مسیر منحنی از سوما به پایین-چپ + قطعات میلین و گره‌های رانویه
    p0 = (soma_x - 8, soma_y + 9)
    p1 = (92.0, 184.0)
    p2 = (58.0, 200.0)
    p3 = (30.0, 232.0)
    g.append(f'<path d="M {p0[0]} {p0[1]} Q {p1[0]} {p1[1]} {p2[0]} {p2[1]} Q 40 212 {p3[0]} {p3[1]}" '
             f'fill="none" stroke="{C["axon"]}" stroke-width="1.5" stroke-linecap="round"/>')
    # نمونه‌برداری مسیر برای قطعات
    path_pts = []
    for i in range(41):
        t = i / 40
        if t < 0.55:
            path_pts.append(_qpoint(p0, p1, p2, t / 0.55))
        else:
            path_pts.append(_qpoint(p2, (40.0, 212.0), p3, (t - 0.55) / 0.45))
    seg_len, gap = 9, 3  # برحسب گام نمونه‌برداری
    idx = 0
    seg_no = 0
    while idx + seg_len < len(path_pts) - 2:
        sub = path_pts[idx:idx + seg_len + 1]
        d = "M " + " L ".join(f"{px:.1f} {py:.1f}" for px, py in sub)
        g.append(f'<path d="{d}" fill="none" stroke="url(#myelin)" stroke-width="5.4" '
                 f'stroke-linecap="round" opacity="0.96"/>')
        node = path_pts[idx + seg_len + 1]
        g.append(f'<circle cx="{node[0]:.1f}" cy="{node[1]:.1f}" r="1.15" fill="#eafffa"/>')
        if seg_no == 1:  # هستهٔ سلول شوان روی یک قطعه
            sp = path_pts[idx + 4]
            g.append(f'<ellipse cx="{sp[0]:.1f}" cy="{sp[1] - 2.4:.1f}" rx="2.1" ry="1.25" '
                     f'fill="{C["nucleus"]}" opacity="0.9"/>')
        idx += seg_len + gap
        seg_no += 1
    # انشعابات انتهایی + دکمه‌ها
    for ang in (2.5, 2.85, 3.2, 3.55):
        ex = p3[0] + math.cos(ang) * 9
        ey = p3[1] + math.sin(ang) * 9
        g.append(f'<path d="M {p3[0]} {p3[1]} Q {p3[0] + math.cos(ang) * 5:.1f} '
                 f'{p3[1] + math.sin(ang) * 4:.1f} {ex:.1f} {ey:.1f}" fill="none" '
                 f'stroke="{C["axon"]}" stroke-width="0.8"/>'
                 f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="1.7" fill="{C["cyan"]}" opacity="0.9"/>')
    # سوما و هسته (روی همه‌چیز)
    g.append(f'''<circle cx="{soma_x}" cy="{soma_y}" r="{soma_r}" fill="url(#soma)" opacity="0.97"/>
      <circle cx="{soma_x - 1}" cy="{soma_y - 1}" r="4.6" fill="{C['nucleus']}" opacity="0.85"/>
      <circle cx="{soma_x - 1}" cy="{soma_y - 1}" r="1.5" fill="#1D4ED8"/>''')

    # ——— الیگودندروسیت (پایین-راست): یک سلول، چند قطعه ———
    ox, oy = 164.0, 238.0
    g.append(f'<circle cx="{ox}" cy="{oy}" r="4.2" fill="{C["soma"]}" opacity="0.95"/>'
             f'<circle cx="{ox}" cy="{oy}" r="1.7" fill="{C["nucleus"]}"/>')
    for k, (ax, ay) in enumerate([(146, 250), (168, 258), (190, 250)]):
        g.append(f'<path d="M {ox} {oy + 3} Q {(ox + ax) / 2:.0f} {(oy + ay) / 2 + 4:.0f} {ax} {ay}" '
                 f'fill="none" stroke="{C["cyan"]}" stroke-width="0.7" opacity="0.9"/>'
                 f'<line x1="{ax - 6.5}" y1="{ay}" x2="{ax + 6.5}" y2="{ay}" stroke="url(#myelin)" '
                 f'stroke-width="3.6" stroke-linecap="round"/>'
                 f'<line x1="{ax - 9}" y1="{ay}" x2="{ax + 9}" y2="{ay}" stroke="{C["axon"]}" '
                 f'stroke-width="0.8" opacity="0.6"/>')

    defs = f'''<defs>
      <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
        <stop offset="0" stop-color="{C['bg1']}"/><stop offset="0.55" stop-color="{C['bg2']}"/>
        <stop offset="1" stop-color="{C['bg3']}"/>
      </linearGradient>
      <linearGradient id="myelin" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" stop-color="{C['myelin']}"/><stop offset="1" stop-color="{C['myelin2']}"/>
      </linearGradient>
      <radialGradient id="soma" cx="0.42" cy="0.4" r="0.75">
        <stop offset="0" stop-color="#EFF6FF"/><stop offset="1" stop-color="{C['myelin2']}"/>
      </radialGradient>
    </defs>'''
    return defs + "".join(g)


MOTIFS = {"histology-neuron-glia": motif_histology_neuron_glia}


def cover_svg(session: Session) -> str:
    fn = MOTIFS.get(session.cover_motif)
    if fn is None:
        raise ValueError(
            f"موتیف کاور ناشناخته: «{session.cover_motif}» — موتیف‌های موجود: {sorted(MOTIFS)}")
    seed = session.session_number * 1000 + 13
    return (f'<svg class="cover-art" viewBox="0 0 210 297" preserveAspectRatio="xMidYMid slice" '
            f'xmlns="http://www.w3.org/2000/svg">{fn(seed)}</svg>')


def cover_html(session: Session, brand: dict[str, str], font_css: str) -> str:
    """سند HTML مستقل کاور؛ با حاشیهٔ صفر رندر و به ابتدای PDF چسبانده می‌شود."""
    draft_badge = ('<span class="cv-draft">پایلوت موتور — نسخهٔ آزمایشی</span>'
                   if session.draft else "")
    # لوگوی رسمی شفاف زیر عنوان؛ اگر فایل نبود، همان برند تایپوگرافیک می‌ماند
    logo_img = (f'<img class="cv-logo" src="{brand["logo_uri"]}" alt="{escape(brand["fa"])}">'
                if brand.get("logo_uri") else "")
    title_parts = session.title.split(": ", 1)
    t1 = escape(title_parts[0])
    t2 = escape(title_parts[1]) if len(title_parts) > 1 else ""
    return f"""<!DOCTYPE html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<style>
{font_css}
@page {{ size: A4; margin: 0; }}
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family:"Vazirmatn",sans-serif; }}
.cover {{ position:relative; width:210mm; height:297mm; overflow:hidden; background:#0A0F1E; }}
.cover-art {{ position:absolute; inset:0; width:210mm; height:297mm; }}
.cv-scrim {{ position:absolute; top:0; left:0; right:0; height:118mm;
  background:linear-gradient(180deg, rgba(3,16,22,.62), rgba(3,16,22,.28) 62%, rgba(3,16,22,0)); }}
.cv-top {{ position:absolute; top:17mm; left:0; right:0; text-align:center; color:{C['pale']}; }}
.cv-course {{ font-size:12.5pt; font-weight:500; letter-spacing:.4px; }}
.cv-course::before,.cv-course::after {{ content:""; display:inline-block; width:16mm; height:1px;
  background:{C['cyan']}; opacity:.65; vertical-align:middle; margin:0 4mm; }}
.cv-center {{ position:absolute; top:30mm; left:14mm; right:14mm; text-align:center; color:#fff;
  padding:6mm 4mm 7mm; background:radial-gradient(ellipse 62% 58% at 50% 44%, rgba(7,12,26,.62), rgba(7,12,26,.32) 55%, rgba(7,12,26,0) 74%); }}
.cv-sess {{ display:inline-block; border:1.2px solid {C['cyan']}; color:{C['cyan']};
  border-radius:20px; padding:1.2mm 6mm; font-size:11pt; font-weight:700; background:rgba(4,20,26,.45); }}
.cv-sess b {{ font-size:14pt; color:#fff; }}
.cv-title {{ margin-top:5.5mm; font-size:27pt; font-weight:700; line-height:1.55;
  text-shadow:0 1px 14px rgba(0,0,0,.45); }}
.cv-title .t2 {{ display:block; font-size:19pt; font-weight:500; color:{C['mint']}; margin-top:1.5mm; }}
.cv-sub {{ margin-top:4mm; font-size:11.5pt; color:{C['pale']}; }}
.cv-brand {{ position:relative; margin-top:5mm; color:#fff; padding:3mm 0 2mm; }}
.cv-brand::before {{ content:""; position:absolute; inset:-6mm -22mm -4mm; z-index:-1;
  background:radial-gradient(ellipse 58% 62% at 50% 50%, rgba(6,11,24,.94), rgba(6,11,24,.78) 55%, rgba(6,11,24,0) 78%); }}
.cv-brand .fa, .cv-brand .en {{ text-shadow:0 1px 10px rgba(0,0,0,.9), 0 0 3px rgba(0,0,0,.9); }}
.cv-logo {{ display:block; width:28mm; height:auto; margin:0 auto 2.5mm;
  filter:drop-shadow(0 1.5mm 5mm rgba(45,212,191,.28)); }}
.cv-brand .fa {{ font-size:17pt; font-weight:700; }}
.cv-brand .en {{ display:block; margin-top:1mm; font-family:"DejaVu Sans",sans-serif;
  font-size:10.5pt; font-weight:700; letter-spacing:3.5px; color:{C['cyan']}; direction:ltr; }}
.cv-bottom {{ position:absolute; bottom:10mm; left:12mm; right:12mm; display:flex;
  justify-content:space-between; align-items:center; color:{C['pale']}; font-size:9pt;
  border-top:0.6px solid rgba(168,230,216,.4); padding-top:3mm; }}
.cv-draft {{ border:1px dashed #7DD3FC; color:#7DD3FC; border-radius:20px; padding:.6mm 4mm; font-size:8.4pt; }}
</style></head><body>
<div class="cover">
  {cover_svg(session)}
  <div class="cv-scrim"></div>
  <div class="cv-top"><span class="cv-course">{escape(session.course)}</span></div>
  <div class="cv-center">
    <span class="cv-sess">جلسهٔ <b>{fa_num(session.session_number)}</b> از {fa_num(session.session_total)}</span>
    <div class="cv-title">{t1}<span class="t2">{t2}</span></div>
    <div class="cv-sub">{escape(session.subtitle)}</div>
    <div class="cv-brand">{logo_img}<span class="fa">{escape(brand['fa'])}</span><span class="en">{escape(brand['en'])}</span></div>
  </div>
  <div class="cv-bottom"><span>{escape(brand['tagline_fa'])}</span>{draft_badge}
    <span>نسخهٔ {escape(session.version)}</span></div>
</div>
</body></html>"""
