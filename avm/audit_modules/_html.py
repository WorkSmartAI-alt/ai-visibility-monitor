"""Shared HTML parser for audit modules.

Parses a page body once and exposes structured data for use by
schema_markup, meta_html_quality, and og_social modules.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from html.parser import HTMLParser


@dataclass
class PageData:
    url: str
    title: str | None = None
    description: str | None = None
    h1_count: int = 0
    canonical: str | None = None
    og: dict[str, str] = field(default_factory=dict)
    twitter_card: str | None = None
    json_ld_blocks: list[dict] = field(default_factory=list)


class _PageParser(HTMLParser):
    def __init__(self, url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.data = PageData(url=url)
        self._in_title = False
        self._in_script_ld = False
        self._script_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "title":
            self._in_title = True
        elif tag == "h1":
            self.data.h1_count += 1
        elif tag == "meta":
            name = a.get("name", "").lower()
            prop = a.get("property", "").lower()
            content = a.get("content", "")
            if name == "description":
                self.data.description = content
            elif name == "twitter:card":
                self.data.twitter_card = content
            elif prop in ("og:title", "og:description", "og:image", "og:type"):
                self.data.og[prop] = content
        elif tag == "link":
            rel = a.get("rel", "").lower()
            if "canonical" in rel:
                self.data.canonical = a.get("href", "")
        elif tag == "script":
            if a.get("type", "").lower() == "application/ld+json":
                self._in_script_ld = True
                self._script_buf = []

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.data.title = (self.data.title or "") + data
        if self._in_script_ld:
            self._script_buf.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False
        elif tag == "script" and self._in_script_ld:
            self._in_script_ld = False
            raw = "".join(self._script_buf).strip()
            if raw:
                try:
                    obj = json.loads(raw)
                    if isinstance(obj, list):
                        self.data.json_ld_blocks.extend(
                            item for item in obj if isinstance(item, dict)
                        )
                    elif isinstance(obj, dict):
                        self.data.json_ld_blocks.append(obj)
                except (json.JSONDecodeError, ValueError):
                    pass
            self._script_buf = []


def parse_page(url: str, body: str) -> PageData:
    """Parse HTML body and return structured PageData."""
    parser = _PageParser(url)
    try:
        parser.feed(body)
    except Exception:
        pass
    if parser.data.title:
        parser.data.title = parser.data.title.strip()
    return parser.data
