"""Парсер HTML-списков публикаций eLIBRARY.RU → таблица (CSV + XLSX).

Использование:
    python -I scripts/elib_list_parser.py \
        --in "data/raw/probe/*список-публикаций-страница-*.html" \
        --out-csv data/processed/sources.csv \
        --out-xlsx data/processed/sources.xlsx \
        [--cards "data/raw/probe/*статья-*.html"]

Формат входа: страницы поиска «Список публикаций», сохранённые браузером (Ctrl+S).
Кодировка файлов — смешанная (UTF-8 / cp1251 / двойное кодирование); разворачивается
функциями decode_bytes() и fix_mojibake().
"""
import argparse
import csv
import html as html_mod
import re
import sys
from pathlib import Path

HEADERS = [
    "record_no", "elib_id", "title", "authors", "journal", "year", "volume",
    "issue", "pages", "citations", "kernel_citations", "fulltext_available",
    "annotation", "keywords", "source_file",
]

MOJIBAKE_RE = re.compile(r"[À-ÿ][\u0080-¿]{1,3}")


def fix_mojibake(s: str) -> str:
    """Двойное кодирование cp1251→utf8 (‘РІС‹...’) возвращает к нормальному тексту."""
    return MOJIBAKE_RE.sub(
        lambda m: bytes(ord(c) for c in m.group(0)).decode("cp1251", errors="ignore"),
        s,
    )


def decode_bytes(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp1251", errors="replace")


def strip_tags(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", "", fragment)
    text = html_mod.unescape(text).replace(" ", " ")
    return re.sub(r"\s+", " ", text).strip()


ROW_RE = re.compile(r'<tr valign="middle"[^>]*\bid="a(\d+)">(.*?)</tr>', re.S)
TITLE_RE = re.compile(
    r'<a href="https://elibrary\.ru/item\.asp\?id=(\d+)"><b>(?:<span[^>]*>)?(.*?)</span>', re.S
)
AUTHORS_RE = re.compile(r"<i>(.*?)</i>", re.S)
JOURNAL_RE = re.compile(r"</i></font><br>\s*(<font[^>]*>.*?</font>)", re.S)
CIT_RE = re.compile(r'cit_items\.asp\?id=\d+"[^>]*>\s*(\d+)\s*</a>', re.S)
BIBLIO_RE = re.compile(
    r"^(?P<journal>.+?)\.?\s*(?P<year>\d{4})\."
    r"(?:\s*Т\.\s*(?P<volume>\d+))?"
    r"(?:\s*№\s*(?P<issue>[\dA-Za-z]+(?:\s*\(\d+\))?))?"
    r"(?:.*?С\.\s*(?P<pages>\d+[-–]\d+).?)?"
)


def parse_biblio(journal_line: str) -> dict:
    out = {"journal": "", "year": "", "volume": "", "issue": "", "pages": ""}
    m = BIBLIO_RE.search(journal_line)
    if not m:
        return out
    d = m.groupdict(default="")
    return {
        "journal": strip_tags(d["journal"]).rstrip(" ."),
        "year": d["year"],
        "volume": d["volume"] or "",
        "issue": d["issue"] or "",
        "pages": d["pages"] or "",
    }


def parse_card_text(text: str) -> dict | None:
    """Ключевые слова, аннотация и цитирования по ядру РИНЦ из HTML карточки статьи."""
    m = re.search(r"item\.asp\?id=(\d+)", text)
    if not m:
        return None

    def field(start: str, end: str) -> str | None:
        sm = re.search(re.escape(start) + r"(.*?)" + re.escape(end), text, re.S)
        if not sm:
            return None
        return strip_tags(sm.group(1)).strip(" /,")

    kernel = ""
    stripped = re.sub(r"<[^>]+>", "\n", text)
    lines = [l.strip() for l in stripped.split("\n") if l.strip()]
    for i, l in enumerate(lines):
        if "Цитирований из ядра РИНЦ" in l and i + 1 < len(lines):
            vm = re.match(r"^(\d+)$", lines[i + 1])
            if vm:
                kernel = vm.group(1)
            break
    return {
        "elib_id": m.group(1),
        "keywords": field("КЛЮЧЕВЫЕ СЛОВА:", "АННОТАЦИЯ:"),
        "annotation": field("АННОТАЦИЯ:", "БИБЛИОМЕТРИЧЕСКИЕ ПОКАЗАТЕЛИ:"),
        "kernel_citations": kernel,
    }


def parse_card(fn: Path) -> dict | None:
    return parse_card_text(decode_bytes(fn.read_bytes()))


def parse_html_text(html_text: str, source_name: str) -> list[dict]:
    """Разбор уже декодированного HTML страницы списка публикаций."""
    rows = []
    for row_id, block in ROW_RE.findall(html_text):
        m_title = TITLE_RE.search(block)
        title = strip_tags(m_title.group(2)) if m_title else ""
        elib_id = m_title.group(1) if m_title else row_id
        m_authors = AUTHORS_RE.search(block)
        authors = strip_tags(m_authors.group(1)) if m_authors else ""
        m_journal = JOURNAL_RE.search(block)
        if m_journal:
            journal_line_part = m_journal.group(1)
        else:
            # записи без авторов: журнальная строка — «font»-блок со ссылкой на выпуск журнала
            cand = re.findall(
                r'<font color="#00008f">\s*(<a href="https://elibrary\.ru/contents\.asp.*?)</font>',
                block,
                re.S,
            )
            journal_line_part = cand[-1] if cand else ""
        journal_line = strip_tags(journal_line_part)
        m_cit = CIT_RE.search(block)
        rec = {
            "elib_id": elib_id,
            "title": title,
            "authors": authors,
            "citations": int(m_cit.group(1)) if m_cit else "",
            "kernel_citations": "",
            "fulltext_available": str(int("download_green" in block)),
            "record_no": "",
            "annotation": "",
            "keywords": "",
            "source_file": source_name,
        }
        rec.update(parse_biblio(journal_line))
        rows.append(rec)
    return rows


def parse_page(fn: Path) -> list[dict]:
    html_text = fix_mojibake(decode_bytes(fn.read_bytes()))
    return parse_html_text(html_text, fn.name)


def write_csv(rows_out: list[dict], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=HEADERS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows_out)


def write_xlsx(rows_out: list[dict], path: str | Path) -> None:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Источники"
    ws.append(HEADERS)
    for r in rows_out:
        ws.append([r.get(h, "") for h in HEADERS])
    ws.freeze_panes = "A2"
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out-csv", dest="out_csv", required=True)
    ap.add_argument("--out-xlsx", dest="out_xlsx", default="")
    ap.add_argument("--cards", default="", help="glob карточек статей для аннотаций")
    args = ap.parse_args(argv)

    files = sorted(Path().glob(args.inp))
    if not files:
        print(f"Файлы не найдены: {args.inp}")
        return 1

    records: dict[str, dict] = {}
    num_re = re.compile(r"\d+")
    for fn in files:
        rows = parse_page(fn)
        # порядковый номер записи восстанавливаем по позиции: rows идут по порядку
        for i, rec in enumerate(rows, 1):
            base = fn.stem.rsplit("-страница-", 1)[-1]
            page_no = int(re.match(r"\d+", base).group()) if base.isdigit() else 1
            rec["record_no"] = (page_no - 1) * 100 + i
        before = len(records)
        for rec in rows:
            records.setdefault(rec["elib_id"], rec)
        print(f"{fn.name}: записей {len(rows)} (новых {len(records) - before})")

    # обогащение аннотациями из карточек
    cards_found = 0
    if args.cards:
        for cfn in sorted(Path().glob(args.cards)):
            card = parse_card(Path(cfn))
            if card and card["elib_id"] in records:
                records[card["elib_id"]]["annotation"] = card["annotation"] or ""
                records[card["elib_id"]]["keywords"] = card["keywords"] or ""
                cards_found += 1
        print(f"Карточек для обогащения: {cards_found}")

    rows_out = sorted(records.values(), key=lambda r: r["record_no"])
    missing = [
        r["elib_id"]
        for r in rows_out
        if not (r["title"] and r["journal"] and r["year"])
    ]
    write_csv(rows_out, args.out_csv)
    if args.out_xlsx:
        write_xlsx(rows_out, args.out_xlsx)

    print(
        f"Итого записей: {len(rows_out)}; без полного разбора (нет названия/журнала/года): {len(missing)}"
    )
    if missing:
        print("id с неполным разбором:", ", ".join(missing[:20]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
