from __future__ import annotations

import logging
from datetime import datetime, timezone
from html import escape
from typing import List
from xml.etree.ElementTree import Element, SubElement, tostring

from ..models import Item

logger = logging.getLogger("paper_digest")


def generate_rss(
    items: List[Item],
    title: str = "Daily AI Digest",
    link: str = "",
    description: str = "Curated AI/ML signals — zero LLMs, pure algorithmic curation",
) -> str:
    """Generate an RSS 2.0 feed from items."""
    rss = Element("rss", version="2.0")
    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = title
    SubElement(channel, "link").text = link
    SubElement(channel, "description").text = description
    SubElement(channel, "lastBuildDate").text = datetime.now(timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )

    for it in items:
        item_el = SubElement(channel, "item")
        SubElement(item_el, "title").text = it.title
        SubElement(item_el, "link").text = str(it.url)
        SubElement(item_el, "guid").text = it.id

        desc_parts = []
        if it.why_it_matters:
            desc_parts.append(it.why_it_matters)
        if it.summary:
            s = it.summary
            if len(s) > 300:
                s = s[:297] + "..."
            desc_parts.append(s)
        SubElement(item_el, "description").text = escape(" — ".join(desc_parts) if desc_parts else it.title)

        try:
            pub_str = it.published.strftime("%a, %d %b %Y %H:%M:%S +0000")
            SubElement(item_el, "pubDate").text = pub_str
        except Exception:
            pass

        for tag in (it.tags or [])[:3]:
            SubElement(item_el, "category").text = tag

    xml_bytes = tostring(rss, encoding="unicode", xml_declaration=False)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_bytes
