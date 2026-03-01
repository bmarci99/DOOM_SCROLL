from __future__ import annotations
from datetime import datetime, timedelta, timezone
from typing import List
from ..models import Item

def filter_last_hours(items: List[Item], hours: int) -> List[Item]:
    now = datetime.now(tz=timezone.utc)
    cutoff = now - timedelta(hours=hours)
    return [i for i in items if i.published >= cutoff]