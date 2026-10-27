"""کتابخانهٔ مرکزی آیکون‌های SVG هامزیار (HumsYar).

قواعد سبک (یکدست در همهٔ آیکون‌ها):
- شبکهٔ ۲۴×۲۴، خط‌محور (stroke) با `currentColor`، ضخامت ۱٫۹، انتهای گرد؛
  بدون فونت آیکون و بدون منبع خارجی — در PDF چاپی و نمایشگر یکسان رندر می‌شود
  و هرگز به مربع خالی (tofu) تبدیل نمی‌شود.
- هر آیکون یک شناسهٔ پایدار و یک معنای فارسی ثبت‌شده دارد؛ معنا در همهٔ
  جزوه‌ها ثابت می‌ماند (رنگ/آیکون = معنا).
- آیکون تزئینیِ بی‌معنا ممنوع: هر ورودی باید کاربرد آموزشی مشخص داشته باشد.
"""
from __future__ import annotations

# شناسه ← (معنای فارسی ثابت, درون SVG)
ICONS: dict[str, tuple[str, str]] = {
    "key": ("نکتهٔ کلیدی",
            '<circle cx="8" cy="14.5" r="4.6"/><path d="M11.2 11.3 20 2.8M16.8 6l2.7 2.7M14 8.8l2.2 2.2"/>'),
    "definition": ("تعریف",
                   '<path d="M12 6.2C10 4.5 7.4 4 4 4v14.2c3.4 0 6 .5 8 2.2 2-1.7 4.6-2.2 8-2.2V4c-3.4 0-6 .5-8 2.2z"/><path d="M12 6.2v14.2"/>'),
    "note": ("نکتهٔ مهم",
             '<circle cx="12" cy="12" r="8.8"/><path d="M12 11.2v5"/><circle cx="12" cy="8" r="1.25" fill="currentColor" stroke="none"/>'),
    "warning": ("هشدار",
                '<path d="M12 3.8 2.8 20h18.4z"/><path d="M12 10v4.4"/><circle cx="12" cy="17.1" r="1.15" fill="currentColor" stroke="none"/>'),
    "exception": ("استثنا",
                  '<circle cx="12" cy="12" r="8.8"/><path d="M8.2 10h7.6M8.2 14h7.6M14.8 7.2 9.2 16.8"/>'),
    "conflict": ("اختلاف منابع",
                 '<circle cx="6" cy="5" r="2.3"/><circle cx="6" cy="19" r="2.3"/><circle cx="18" cy="8" r="2.3"/><path d="M6 7.3v9.4M18 10.3c0 4.8-7.6 3.4-9.8 6.2"/>'),
    "exam": ("نکتهٔ امتحانی",
             '<circle cx="12" cy="12" r="8.6"/><circle cx="12" cy="12" r="4.9"/><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none"/>'),
    "mnemonic": ("یادیار",
                 '<path d="M10.2 13.8a4.1 4.1 0 0 0 5.8 0l3-3a4.15 4.15 0 1 0-5.9-5.9l-1.6 1.6"/><path d="M13.8 10.2a4.1 4.1 0 0 0-5.8 0l-3 3A4.15 4.15 0 1 0 10.9 19l1.6-1.6"/>'),
    "clinical": ("ارتباط بالینی",
                 '<rect x="4" y="4" width="16" height="16" rx="4.5"/><path d="M12 8.4v7.2M8.4 12h7.2"/>'),
    "process": ("مسیر و فرایند",
                '<circle cx="5" cy="19" r="2.3"/><circle cx="19" cy="5" r="2.3"/><path d="M5 16.7v-3.2A3.5 3.5 0 0 1 8.5 10h7A3.5 3.5 0 0 0 19 6.6" stroke-dasharray="3.2 2.6"/>'),
    "summary": ("جمع‌بندی",
                '<path d="M9.5 6H20M9.5 12H20M9.5 18h6.5"/><path d="M3.4 6l1.3 1.3L7.2 4.7M3.4 12l1.3 1.3 2.5-2.6M3.4 18l1.3 1.3 2.5-2.6"/>'),
    "example": ("مثال",
                '<path d="M9.2 18.2h5.6M10.2 21h3.6"/><path d="M12 3a6.1 6.1 0 0 0-3.4 11.1c.6.5 1 1.1 1.2 2h4.4c.2-.9.6-1.5 1.2-2A6.1 6.1 0 0 0 12 3z"/>'),
    "formula": ("فرمول",
                '<path d="M17.5 4.8H8.2L14 12l-5.8 7.2h9.3"/>'),
    "terminology": ("اصطلاح‌شناسی",
                    '<path d="M4 4h8.8L21 12.2a2.15 2.15 0 0 1 0 3L15.2 21a2.15 2.15 0 0 1-3 0L4 12.8z"/><circle cx="8.3" cy="8.3" r="1.4" fill="currentColor" stroke="none"/>'),
    "unresolved": ("نیازمند بررسی",
                   '<circle cx="12" cy="12" r="8.8"/><path d="M9.6 9.4A2.6 2.6 0 1 1 12 12.5v1.6"/><circle cx="12" cy="17" r="1.15" fill="currentColor" stroke="none"/>'),
    "bridge": ("از ساختار تا عملکرد",
               '<path d="M3 17.5c3-6.2 6-8.6 9-8.6s6 2.4 9 8.6"/><path d="M3 17.5h18M7.2 17.5v-3.6M12 17.5V9M16.8 17.5v-3.6"/>'),
    "compare": ("مقایسه",
                '<rect x="3.8" y="4" width="7" height="16" rx="1.6"/><rect x="13.2" y="4" width="7" height="16" rx="1.6"/>'),
    "structure": ("ساختار",
                  '<path d="M12 3.2 21 8l-9 4.8L3 8z"/><path d="M3.6 12.8 12 17.3l8.4-4.5M3.6 16.8 12 21.3l8.4-4.5"/>'),
    "function": ("عملکرد",
                 '<path d="M3 12h4.2l2.4-6.4 4.2 11.4 2.4-5H21"/>'),
    "location": ("محل",
                 '<path d="M12 21s-6.6-5.5-6.6-10.5A6.6 6.6 0 0 1 12 3.9a6.6 6.6 0 0 1 6.6 6.6C18.6 15.5 12 21 12 21z"/><circle cx="12" cy="10.4" r="2.3"/>'),
    "origin": ("منشأ",
               '<path d="M12 21v-7.6"/><path d="M12 13.4c0-4.1 2.9-6.7 7-6.7 0 4.1-2.6 6.7-7 6.7zM12 11C12 7.4 9.5 5.3 6 5.3c0 3.6 2.1 5.7 6 5.7z"/>'),
    "microscope": ("نمای میکروسکوپی",
                   '<path d="M9.5 3h5M12 3l.9 5.6"/><path d="M12.9 8.6 15.6 13"/><path d="M7.2 16.8a5.2 5.2 0 0 0 8.4 0"/><path d="M12 16.8v2.7M5 21h14"/>'),
    "time": ("زمان",
             '<circle cx="12" cy="12" r="8.7"/><path d="M12 7.2V12l3.4 2"/>'),
    "reference": ("ارجاع",
                  '<path d="M7 3.5h10V21l-5-3.7L7 21z"/>'),
    "check": ("تأیید",
              '<path d="M4.5 12.6l5 5L19.5 6.8"/>'),
    "arrow": ("جهت",
              '<path d="M20.5 12h-16M9.4 6.4 3.9 12l5.5 5.6"/>'),
    "glance": ("در یک نگاه",
               '<path d="M2.8 12S6 5.8 12 5.8 21.2 12 21.2 12 18 18.2 12 18.2 2.8 12 2.8 12z"/><circle cx="12" cy="12" r="2.8"/>'),
}


def icon_svg(name: str, size: float = 14) -> str:
    """SVG کامل یک آیکون؛ شناسهٔ ناشناس به آیکون «نکته» برمی‌گردد (هرگز خالی نیست)."""
    _meaning, inner = ICONS.get(name, ICONS["note"])
    return (f'<svg class="ic ic--{name}" width="{size:g}" height="{size:g}" '
            f'viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            f'stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" '
            f'aria-hidden="true">{inner}</svg>')


# نگاشت نوع کادر معنایی ← آیکون ثابت آن
CALLOUT_ICONS: dict[str, str] = {
    "key": "key",
    "clinical": "clinical",
    "warning": "warning",
    "exception": "exception",
    "bridge": "bridge",
    "conflict": "conflict",
    "exam": "exam",
    "definition": "definition",
    "example": "example",
    "summary": "summary",
    "mnemonic": "mnemonic",
    "formula": "formula",
    "terminology": "terminology",
    "unresolved": "unresolved",
}
