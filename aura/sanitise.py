"""Allow-list HTML sanitiser for LLM-generated content (stdlib only)."""

from html import escape
from html.parser import HTMLParser

ALLOWED_TAGS = frozenset({
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "br", "hr", "ul", "ol", "li",
    "strong", "b", "em", "i", "u", "code", "pre", "blockquote", "a", "span",
    "table", "thead", "tbody", "tr", "th", "td", "sub", "sup",
})
VOID_TAGS = frozenset({"br", "hr"})
# Content of these tags is dropped entirely, not just the tags themselves.
DROP_CONTENT_TAGS = frozenset({"script", "style", "iframe", "object", "embed", "template"})
SAFE_URL_SCHEMES = ("http://", "https://", "mailto:", "/", "#")


class _Sanitiser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._drop_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in DROP_CONTENT_TAGS:
            self._drop_depth += 1
            return
        if self._drop_depth or tag not in ALLOWED_TAGS:
            return
        rendered = ""
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if href.strip().lower().startswith(SAFE_URL_SCHEMES):
                rendered = f' href="{escape(href.strip(), quote=True)}" rel="noopener noreferrer" target="_blank"'
        self.out.append(f"<{tag}{rendered}>")

    def handle_endtag(self, tag):
        if tag in DROP_CONTENT_TAGS:
            self._drop_depth = max(0, self._drop_depth - 1)
            return
        if self._drop_depth or tag not in ALLOWED_TAGS or tag in VOID_TAGS:
            return
        self.out.append(f"</{tag}>")

    def handle_data(self, data):
        if not self._drop_depth:
            self.out.append(escape(data))


def sanitise_html(value: str | None) -> str:
    """Return ``value`` reduced to allow-listed tags with no event handlers or scripts."""
    if not value:
        return ""
    parser = _Sanitiser()
    parser.feed(str(value))
    parser.close()
    return "".join(parser.out)


def escape_keep_mark(value: str | None) -> str:
    """Escape all HTML except the ``<mark>`` tags used for search-hit highlighting."""
    if value is None:
        return ""
    text = escape(str(value))
    return text.replace("&lt;mark&gt;", "<mark>").replace("&lt;/mark&gt;", "</mark>")
