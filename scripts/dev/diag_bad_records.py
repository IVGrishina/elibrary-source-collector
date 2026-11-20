"""Диагностика записей с неполным разбором: смотрим их HTML-блоки."""
import csv
import re
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
PROBE = ROOT / "data" / "raw" / "probe"

rows = list(csv.DictReader(open(ROOT / "data/processed/sources_кадры-сх-регионов_2026-11-16.csv", encoding="utf-8-sig")))
bad = [r for r in rows if not (r["title"] and r["journal"] and r["year"])]

missing_journal = sum(1 for r in bad if not r["journal"])
missing_title = sum(1 for r in bad if not r["title"])
print(f"плохих: {len(bad)}; из них без журнала: {missing_journal}, без названия: {missing_title}, "
      f"без года: {sum(1 for r in bad if not r['year'])}")

# показываем исходные tr-блоки нескольких образцов
page_re = {}
for fn in PROBE.glob("*список-публикаций-страница-*.html"):
    page_re[fn.stem[-2:]] = fn.read_bytes().decode("utf-8", errors="replace")

by_page = Counter(r["source_file"][-2:] for r in bad)
print("распределение по страницам:", dict(by_page))

shown = 0
for r in bad[:8]:
    page = re.search(r"страница-(\d+)", r["source_file"]).group(1).zfill(2)
    html_text = page_re.get(page, "")
    html_text = page_re.get(page, "")
    m = re.search(r'<tr valign="middle"[^>]*id="a%s">(.*?)</tr>' % r["elib_id"], html_text, re.S)
    if not m:
        continue
    block = m.group(1)
    # печатаем текстовый хвост записи (после авторов)
    tail = re.sub(r"<[^>]+>", "|", block)
    tail = re.sub(r"\|+", " | ", tail).strip()
    print("=" * 20, r["elib_id"])
    print(tail[:450].replace("&nbsp;", " "))
    shown += 1
