from __future__ import annotations
import re

def quick_summary(text: str, max_sentences: int = 4) -> str:
    # naive sentence split (good enough for MVP)
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    sents = [s for s in sents if 40 <= len(s) <= 300]
    return " ".join(sents[:max_sentences])