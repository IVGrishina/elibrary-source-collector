"""eLIBRARY Source Collector — веб-интерфейс (Flask).

Запуск: python app.py  →  http://127.0.0.1:5000
Загружаются сохранённые из браузера HTML-страницы результатов поиска eLIBRARY
(и карточки статей — приложение распознаёт их автоматически).

Порядок выдачи (в таблице и в скачиваемых файлах) переключается:
collection — как в подборке; citations — по цитированиям; year — по году.
"""
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "scripts"))

from flask import Flask, abort, render_template, request, send_from_directory  # noqa: E402

import elib_list_parser as elp  # noqa: E402
import elib_summary as els  # noqa: E402
import elib_digest as eld  # noqa: E402

OUT_DIR = ROOT / "data" / "processed"
TMP_DIR = ROOT / "tmp"
MAX_TABLE_ROWS = 100
SORTS = ("collection", "citations", "year")
SORT_LABELS = {
    "collection": "как в подборке",
    "citations": "по цитированиям",
    "year": "по году",
}
STAMP_RE = re.compile(r"^[0-9-]+$")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024 * 1024


@app.route("/")
def index():
    return render_template("index.html")


def parse_uploaded_files(upload_dir: Path):
    """Разбор всех файлов загрузки: страницы списков, карточки, пропущенные."""
    pages: list[tuple[str, str]] = []  # (имя файла, HTML), порядок — по имени
    cards: list[str] = []
    skipped: list[str] = []
    for fn in sorted(upload_dir.iterdir()):
        text = elp.fix_mojibake(elp.decode_bytes(fn.read_bytes()))
        if "КЛЮЧЕВЫЕ СЛОВА:" in text and "АННОТАЦИЯ:" in text:
            cards.append(text)
        elif elp.ROW_RE.search(text):
            pages.append((fn.name, text))
        else:
            skipped.append(fn.name)

    records: dict[str, dict] = {}
    rows: list[dict] = []
    for _, text in pages:
        for rec in elp.parse_html_text(text, "страница списка"):
            if rec["elib_id"] not in records:
                records[rec["elib_id"]] = rec
                rows.append(rec)
    for i, rec in enumerate(rows, 1):
        rec["record_no"] = str(i)

    enriched = 0
    for ctext in cards:
        card = elp.parse_card_text(ctext)
        if card and card["elib_id"] in records:
            rec = records[card["elib_id"]]
            rec["annotation"] = card["annotation"] or ""
            rec["keywords"] = card["keywords"] or ""
            rec["kernel_citations"] = card["kernel_citations"] or ""
            enriched += 1
    return rows, enriched, skipped


def sort_rows(rows: list[dict], sort: str):
    """Стабильная сортировка: '_order' сохраняет порядок подборки."""
    for i, r in enumerate(rows):
        r["_order"] = i
        r["_year"] = int(r["year"]) if str(r["year"]).isdigit() else -1
        r["_cit"] = int(r["citations"] or 0)
    if sort == "citations":
        return sorted(rows, key=lambda r: (-r["_cit"], r["_order"]))
    if sort == "year":
        return sorted(rows, key=lambda r: (-r["_year"], -r["_cit"], r["_order"]))
    return sorted(rows, key=lambda r: r["_order"])


def render_result(rows, enriched, skipped, stamp, sort):
    display_time = time.strftime("%d.%m.%Y %H:%M:%S", time.strptime(stamp, "%Y%m%d-%H%M%S"))
    if not rows:
        return render_template(
            "error.html",
            message="Не найдено записей публикаций. Карточки статей обрабатываются вместе со "
                    "списком публикаций: загрузите сохранённые страницы «Список публикаций» "
                    "(Ctrl+S, формат HTML). Если сессия уже создана — используйте блок "
                    "«Дополнить набор» на странице результата.",
        ), 400

    summary = els.compute_summary(rows)
    ordered = sort_rows(rows, sort)
    digest = eld.build_digest(rows)
    csv_name = f"sources_{stamp}_{sort}.csv"
    xlsx_name = f"sources_{stamp}_{sort}.xlsx"
    md_name = f"summary_{stamp}.md"
    digest_name = f"digest_{stamp}.md"
    elp.write_csv(ordered, OUT_DIR / csv_name)
    elp.write_xlsx(ordered, OUT_DIR / xlsx_name)
    (OUT_DIR / md_name).write_text(els.format_markdown(summary), encoding="utf-8")
    (OUT_DIR / digest_name).write_text(eld.format_markdown(digest), encoding="utf-8")

    return render_template(
        "result.html",
        s=summary,
        table=ordered[:MAX_TABLE_ROWS],
        table_shown=min(MAX_TABLE_ROWS, len(ordered)),
        enriched=enriched,
        skipped=skipped,
        digest=digest,
        csv_name=csv_name,
        xlsx_name=xlsx_name,
        md_name=md_name,
        digest_name=digest_name,
        sort=sort,
        sort_label=SORT_LABELS[sort],
        sort_labels=SORT_LABELS,
        display_time=display_time,
        stamp=stamp,
    )


@app.route("/process", methods=["POST"])
def process():
    files = [f for f in request.files.getlist("files") if f.filename]
    if not files:
        return render_template("error.html", message="Не выбран ни один файл."), 400

    # повторный запрос с тем же stamp дописывает файлы в существующую сессию
    stamp = request.form.get("stamp", "")
    if not (STAMP_RE.match(stamp) and (TMP_DIR / f"uploads-{stamp}").is_dir()):
        stamp = time.strftime("%Y%m%d-%H%M%S")
    upload_dir = TMP_DIR / f"uploads-{stamp}"
    upload_dir.mkdir(parents=True, exist_ok=True)
    for fs in files:
        fs.save(upload_dir / Path(fs.filename).name)

    rows, enriched, skipped = parse_uploaded_files(upload_dir)
    return render_result(rows, enriched, skipped, stamp, "collection")


@app.route("/rebuild")
def rebuild():
    """Пересборка результатов в другом порядке (файлы остаются от загрузки)."""
    stamp = request.args.get("stamp", "")
    sort = request.args.get("sort", "collection")
    if not STAMP_RE.match(stamp) or sort not in SORTS:
        abort(404)
    upload_dir = TMP_DIR / f"uploads-{stamp}"
    if not upload_dir.is_dir():
        return render_template(
            "error.html",
            message="Загруженные файлы не найдены. Загрузите страницы заново.",
        ), 404
    rows, enriched, skipped = parse_uploaded_files(upload_dir)
    return render_result(rows, enriched, skipped, stamp, sort)


@app.route("/download/<name>")
def download(name):
    if "/" in name or "\\" in name or not name.startswith(("sources_", "summary_", "digest_")):
        abort(404)
    return send_from_directory(OUT_DIR, name)


if __name__ == "__main__":
    print("eLIBRARY Source Collector: http://127.0.0.1:5000")
    app.run(debug=False, host="127.0.0.1", port=5000)
