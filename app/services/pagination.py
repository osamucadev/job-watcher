from __future__ import annotations

ELLIPSIS = "…"

MAX_SIMPLE_PAGES = 7
SIBLING_COUNT = 2


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
    """Build a contextual, sliding-window page sequence.

    Page 1 and the last page are always present. Around the current page we
    prefer showing SIBLING_COUNT pages before and after it; near either edge
    that window is widened (never just clamped) so the same number of pages
    stays visible instead of shrinking toward the boundary. "…" is only
    inserted where a real gap remains between two shown page numbers -
    adjacent numbers are never separated by an ellipsis.
    """
    if total <= 0:
        return []

    current = max(1, min(current, total))

    if total <= MAX_SIMPLE_PAGES:
        return list(range(1, total + 1))

    raw_start = current - SIBLING_COUNT
    raw_end = current + SIBLING_COUNT

    window_start = raw_start
    window_end = raw_end

    if raw_start <= 1:
        window_end = max(window_end, 2 * SIBLING_COUNT + 2)
    if raw_end >= total:
        window_start = min(window_start, total - (2 * SIBLING_COUNT + 1))

    window_start = max(window_start, 1)
    window_end = min(window_end, total)

    must_show = {1, total} | set(range(window_start, window_end + 1))
    ordered = sorted(page for page in must_show if 1 <= page <= total)

    sequence: list[int | str] = []
    previous: int | None = None
    for page in ordered:
        if previous is not None and page - previous > 1:
            sequence.append(ELLIPSIS)
        sequence.append(page)
        previous = page
    return sequence
