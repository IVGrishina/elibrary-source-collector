"""Генератор саммари по таблице источников eLIBRARY.

Использование (CLI):
    python -I scripts/elib_summary.py --csv data/processed/sources.csv --out report.md

Функции compute_summary() и format_markdown() также используются веб-приложением app.py.
"""
import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

TOP_CITED = 15
TOP_JOURNALS = 12
YEAR_BUCKETS = [(None, 2009), (2010, 2014), (2015, 2019), (2020, 2022), (2023, 2024), (2025, 2027)]


def compute_summary(rows: list[dict]) -> dict:
    """rows — записи из таблицы источников (dict с полями HEADERS)."""
    for r in rows:
        r["citations"] = int(r["citations"] or 0)
        r["year"] = int(r["year"]) if str(r["year"]).isdigit() else None

    years = Counter(r["year"] for r in rows if r["year"])
    journals = Counter(r["journal"] for r in rows if r["journal"])
    buckets = []
    for y0, y1 in YEAR_BUCKETS:
        c = sum(v for y, v in years.items() if (y0 is None or y0 <= y) and y <= y1)
        if c:
            buckets.append((f"до {y1}" if y0 is None else f"{y0}–{y1}", c))
    n = len(rows)
    return {
        "total": n,
        "fulltext": sum(r["fulltext_available"] == "1" for r in rows),
        "annotated": sum(bool(r["annotation"]) for r in rows),
        "year_buckets": buckets,
        "no_year": sum(1 for r in rows if r["year"] is None),
        "top_cited": sorted(rows, key=lambda r: -r["citations"])[:TOP_CITED],
        "n_journals": len(journals),
        "top_journals": journals.most_common(TOP_JOURNALS),
    }


def format_markdown(s: dict, query: str = "") -> str:
    lines = [
        "# Саммари источников из eLIBRARY по подборке",
        "",
        f"**Всего публикаций:** {s['total']}",
        f"**Полный текст открыт (есть значок доступа):** {s['fulltext']} ({s['fulltext'] / s['total']:.0%})",
        f"**Аннотации извлечены (по карточкам):** {s['annotated']}",
        "",
        "## Распределение по годам",
        "",
        "| Период | Публикаций |",
        "|---|---|",
    ]
    for label, c in s["year_buckets"]:
        lines.append(f"| {label} | {c} |")
    if s["no_year"]:
        lines.append(f"| год не определён | {s['no_year']} |")

    lines += ["", "## Наиболее цитируемые публикации", ""]
    for r in s["top_cited"]:
        title = (r["title"][:110] + "…") if len(r["title"]) > 110 else r["title"]
        lines.append(
            f"{r['record_no']}. **{title}** — {r['authors']}; *{r['journal']}*, "
            f"{r['year']} №{r['issue'] or '—'}; цит. **{r['citations']}**; стр. {r['pages'] or '—'}"
        )

    lines += ["", "## Основные журналы подборки", ""]
    for j, c in s["top_journals"]:
        lines.append(f"- {j} — {c} публ.")

    recent = sum(c for label, c in s["year_buckets"] if label in ("2023–2024", "2025–2027"))
    lines += [
        "",
        "## Выводы",
        "",
        f"1. Подборка из {s['total']} публикаций покрывает тематику подборки"
        + (f" «{query}»" if query else "")
        + ".",
        f"2. Публикационная активность по теме за 2023–2025 гг.: {recent} из {s['total']} публикаций.",
        f"3. Доля публикаций с открытым доступом к полному тексту — {s['fulltext'] / s['total']:.0%}.",
        f"4. Ядро массива — {s['n_journals']} журналов; наиболее продуктивный канал: "
        f"{s['top_journals'][0][0]} ({s['top_journals'][0][1]} публ.).",
        f"5. Для содержательной оценки релевантности нужны аннотации (карточки статей); сейчас извлечено {s['annotated']} шт.",
    ]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--query", default="")
    args = ap.parse_args(argv)
    rows = list(csv.DictReader(open(args.csv, encoding="utf-8-sig")))
    text = format_markdown(compute_summary(rows), args.query)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"Отчёт: {args.out} ({len(rows)} записей)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
