from __future__ import annotations

ELLIPSIS = "…"

MAX_SIMPLE_PAGES = 8
EDGE_COUNT = 4
ANCHOR_COUNT = 2
WINDOW_BEFORE = 1
WINDOW_AFTER = 2


def normalize_page(raw_page: object, total_pages: int) -> int:
    try:
        page = int(raw_page)
    except (TypeError, ValueError):
        page = 1

    if page < 1:
        page = 1
    if not total_pages:
        return 1
    if page > total_pages:
        page = total_pages
    return page


def page_sequence(current: int, total: int) -> list[int | str]:
    if total <= 0:
        return []

    current = max(1, min(current, total))

    if total <= MAX_SIMPLE_PAGES:
        return list(range(1, total + 1))

    if current <= EDGE_COUNT or current > total - EDGE_COUNT:
        must_show = set(range(1, EDGE_COUNT + 1)) | set(range(total - EDGE_COUNT + 1, total + 1))
    else:
        must_show = (
            set(range(1, ANCHOR_COUNT + 1))
            | set(range(current - WINDOW_BEFORE, current + WINDOW_AFTER + 1))
            | set(range(total - ANCHOR_COUNT + 1, total + 1))
        )

    ordered = sorted(page for page in must_show if 1 <= page <= total)

    sequence: list[int | str] = []
    previous: int | None = None
    for page in ordered:
        if previous is not None and page - previous > 1:
            sequence.append(ELLIPSIS)
        sequence.append(page)
        previous = page
    return sequence
