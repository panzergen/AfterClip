"""Small, dependency-free Markdown-to-HTML renderer for the report.

The AI summary is Markdown. The full HTML report should render its headings,
lists and tables instead of showing literal ``#`` and pipe characters. Raw HTML
is escaped before any formatting is applied.
"""

import html
import re

_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_UNORDERED = re.compile(r"^\s*[-*+]\s+(.*)$")
_ORDERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$")
_INLINE_CODE = re.compile(r"`([^`]+)`")
_BOLD = re.compile(r"\*\*(.+?)\*\*|__(.+?)__")
_ITALIC = re.compile(r"(?<!\*)\*([^*]+)\*(?!\*)")


def _inline(text: str) -> str:
    escaped = html.escape(text.strip())
    escaped = _INLINE_CODE.sub(lambda match: f"<code>{match.group(1)}</code>", escaped)
    escaped = _BOLD.sub(
        lambda match: f"<strong>{match.group(1) or match.group(2)}</strong>", escaped
    )
    return _ITALIC.sub(r"<em>\1</em>", escaped)


def _table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _table(header: str, rows: list[str]) -> str:
    head = "".join(f"<th>{_inline(cell)}</th>" for cell in _table_cells(header))
    body = "".join(
        "<tr>" + "".join(f"<td>{_inline(cell)}</td>" for cell in _table_cells(row)) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_markdown(text: str | None, heading_offset: int = 0) -> str:
    """Return safe HTML for the subset of Markdown used in AI reports."""
    if not text:
        return ""
    lines = text.splitlines()
    output: list[str] = []
    list_items: list[str] = []
    list_kind: str | None = None
    index = 0

    def flush_list() -> None:
        nonlocal list_items, list_kind
        if list_kind and list_items:
            items = "".join(f"<li>{item}</li>" for item in list_items)
            output.append(f"<{list_kind}>{items}</{list_kind}>")
        list_items = []
        list_kind = None

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            flush_list()
            index += 1
            continue

        heading = _HEADING.match(line)
        if heading:
            flush_list()
            level = min(6, len(heading.group(1)) + heading_offset)
            output.append(f"<h{level}>{_inline(heading.group(2))}</h{level}>")
            index += 1
            continue

        if "|" in line and index + 1 < len(lines) and _TABLE_SEPARATOR.match(lines[index + 1]):
            flush_list()
            rows: list[str] = []
            index += 2
            while index < len(lines) and "|" in lines[index] and lines[index].strip():
                rows.append(lines[index])
                index += 1
            output.append(_table(line, rows))
            continue

        unordered = _UNORDERED.match(line)
        ordered = _ORDERED.match(line) if not unordered else None
        if unordered or ordered:
            kind = "ul" if unordered else "ol"
            if list_kind != kind:
                flush_list()
                list_kind = kind
            list_items.append(_inline((unordered or ordered).group(1)))
            index += 1
            continue

        if stripped.startswith(">"):
            flush_list()
            quote = [stripped.lstrip("> ").strip()]
            index += 1
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote.append(lines[index].strip().lstrip("> ").strip())
                index += 1
            quote_html = "<br>".join(_inline(item) for item in quote)
            output.append(f"<blockquote>{quote_html}</blockquote>")
            continue

        flush_list()
        paragraph = [stripped]
        index += 1
        while index < len(lines):
            next_line = lines[index]
            next_stripped = next_line.strip()
            if not next_stripped:
                break
            if (
                _HEADING.match(next_line)
                or _UNORDERED.match(next_line)
                or _ORDERED.match(next_line)
                or next_stripped.startswith(">")
                or (
                    "|" in next_line
                    and index + 1 < len(lines)
                    and _TABLE_SEPARATOR.match(lines[index + 1])
                )
            ):
                break
            paragraph.append(next_stripped)
            index += 1
        output.append("<p>" + "<br>".join(_inline(item) for item in paragraph) + "</p>")

    flush_list()
    return "".join(output)
