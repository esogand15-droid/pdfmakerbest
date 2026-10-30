# HumsYar — دستورهای یکپارچهٔ ساخت و تست
PY ?= .venv/bin/python

.PHONY: build test test-brand samples

build:
	cd engine && ../$(PY) -m humsyar.cli build ../content/session01_pilot.yaml --out ../output

test:
	$(PY) -m pytest tests/ -q

# تست‌های هویت بصری برند (T1/T2/T3/T5/T12 + یکپارچگی مؤلفه‌ها)
test-brand:
	$(PY) -m pytest tests/test_round10_brand.py tests/test_round9.py -q

# تصاویر نمونهٔ رنگی و خاکستری از PDF ساخته‌شده
samples:
	$(PY) scripts/brand_samples.py

# برگهٔ مرور فوق‌فشرده — ابزار داخلی؛ در build داخل PDF نهایی ادغام می‌شود
ultra:
	cd engine && ../$(PY) -m humsyar.cli ultra ../content/session01_pilot.yaml --out ../output
