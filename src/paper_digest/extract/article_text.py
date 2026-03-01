from __future__ import annotations
import requests
from bs4 import BeautifulSoup
from readability import Document

def fetch_readable_text(url: str, timeout: int = 20) -> str:
    r = requests.get(url, timeout=timeout, headers={"User-Agent": "paper-digest/0.1"})
    r.raise_for_status()
    doc = Document(r.text)
    html = doc.summary()
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n")
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())