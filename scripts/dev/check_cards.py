"""Проверка карточек статей elibrary: какие поля извлекаются.

Запуск: python -I scripts/check_cards.py
Слежение за кодировкой: файлы сохранены браузером, смешанная UTF-8/cp1251.
"""
import glob
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

PROBE = Path(__file__).resolve().parents[1] / "data" / "raw" / "probe"


def get_lines(fn: Path) -> list[str]:
    html = fn.read_bytes().decode("utf-8", errors="replace")
    text = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    text = re.sub(r"<style.*?</style>", " ", text, flags=re.S)
    text = re.sub(r"<[^>]+>", "\n", text)
    return [l.strip() for l in text.split("\n") if l.strip()]


def pair_values(lines: list[str], anchors: list[str]) -> dict:
    """Значение = следующая непустая строка после строки-якоря."""
    out = {}
    for anchor in anchors:
        for i, l in enumerate(lines):
            if anchor in l:
                out[anchor] = lines[i + 1].replace("&nbsp;", " ").strip()
                break
    return out


def field_between(lines: list[str], start: str, end: str) -> str:
    try:
        i = next(i for i, l in enumerate(lines) if l.startswith(start))
        j = next(j for j in range(i + 1, len(lines)) if lines[j].startswith(end))
    except StopIteration:
        return "<нет>"
    return " / ".join(x for x in lines[i + 1 : j] if x not in (",", "/", "&nbsp;"))


for fn in sorted(PROBE.glob("2026-11-16-elibrary-кадры-сх-регионов-статья-*.html")):
    lines = get_lines(fn)
    print("=" * 70)
    print(fn.name.replace("2026-11-16-elibrary-кадры-сх-регионов-", ""))
    vals = pair_values(lines, ["EDN:", "DOI:", "УДК:", "ISSN:", "Поступила", "Страницы:"])
    for k, v in vals.items():
        print(f"  {k:28} {v[:60]}")
    print(f"  {'КЛЮЧЕВЫЕ СЛОВА:':28} {field_between(lines, 'КЛЮЧЕВЫЕ СЛОВА:', 'АННОТАЦИЯ:')[:90]}")
    abs_text = field_between(lines, "АННОТАЦИЯ:", "БИБЛИОМЕТРИЧЕСКИЕ ПОКАЗАТЕЛИ:")
    print(f"  {'АННОТАЦИЯ (длина):':28} {len(abs_text)} симв. фрагмент: {abs_text[:70]}…")
    cit = pair_values(lines, ["Цитирований в РИНЦ:", "Цитирований из ядра РИНЦ:"])
    for k, v in cit.items():
        print(f"  {k:28} {v}")
