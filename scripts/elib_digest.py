"""Тематический дайджест по аннотациям: «о чём повествуют статьи» + ссылки на eLIBRARY.

Используется веб-приложением app.py. Работает локально, без внешних API.
Дайджест одновременно служит входом для субагента-райтера (скилл
elibrary-literature-review): полные аннотации + ключевые слова + ссылки.
"""
from collections import Counter


def link(elib_id: str) -> str:
    return f"https://elibrary.ru/item.asp?id={elib_id}"


def build_digest(rows: list[dict], limit: int = 30) -> dict:
    items, kw = [], Counter()
    for r in rows:
        if not r.get("annotation"):
            continue
        keywords = [k.strip().lower() for k in (r.get("keywords") or "").split(",") if k.strip()]
        kw.update(keywords)
        items.append(
            {
                "record_no": r["record_no"],
                "elib_id": r["elib_id"],
                "title": r["title"],
                "authors": r["authors"],
                "journal": r["journal"],
                "year": r["year"],
                "link": link(r["elib_id"]),
                # полная аннотация — как в таблице Excel, без обрезки
                "annotation": " ".join(r["annotation"].split()),
                "keywords_list": keywords,
            }
        )
        if len(items) >= limit:
            break
    return {
        "items": items,
        "n_items": len(items),
        "n_annotated_total": sum(1 for r in rows if r.get("annotation")),
        "top_keywords": kw.most_common(12),
    }


def format_markdown(d: dict, topic: str = "") -> str:
    lines = [
        "# Тематический дайджест по аннотациям",
        "",
        f"Карточек с аннотациями: **{d['n_items']}** (из поданных {d['n_annotated_total']}).",
        "",
        "## Тематика массива (частотные ключевые слова)",
        "",
        ", ".join(f"{k} ({c})" for k, c in d["top_keywords"]) or "—",
        "",
        "## Публикации и аннотации",
        "",
    ]
    for it in d["items"]:
        kws = ", ".join(it["keywords_list"]) or "—"
        lines.append(
            f"### {it['record_no']}. [{it['title']}]({it['link']})\n"
            f"*{it['authors']}*; {it['journal'] or '—'}{', ' + str(it['year']) if it['year'] else ''}\n\n"
            f"**Ключевые слова:** {kws}\n\n"
            f"{it['annotation']}\n"
        )
    lines.append(
        "\n> Ссылки на публикации ведут на elibrary.ru/item.asp?id=… "
        "(для просмотра нужна открытая сессия eLIBRARY в этом же браузере).\n"
    )
    return "\n".join(lines) + "\n"
