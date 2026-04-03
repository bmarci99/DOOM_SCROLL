from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..delivery.email_sender import send_email

logger = logging.getLogger("paper_digest")


def _load_daily_digests(outputs_dir: str = "outputs", days: int = 7) -> list[Item]:
    """Load items from the last N daily digest JSON files."""
    out = Path(outputs_dir)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Try loading from history
    hist_path = out / "history.json"
    if hist_path.exists():
        try:
            data = json.loads(hist_path.read_text(encoding="utf-8"))
            items_raw = data.get("items", [])
            # Filter to last 7 days and reconstruct minimal Items
            weekly_items = []
            for entry in items_raw:
                date_str = entry.get("date", "")
                if not date_str:
                    continue
                try:
                    dt = datetime.fromisoformat(date_str)
                    if dt < cutoff:
                        continue
                except (ValueError, TypeError):
                    continue
                weekly_items.append(entry)
            return weekly_items
        except (json.JSONDecodeError, OSError):
            pass

    return []


def generate_weekly(outputs_dir: str = "outputs") -> None:
    """Generate a weekly digest from the last 7 days of daily digests."""
    logger.info("Generating weekly digest...")

    hist_entries = _load_daily_digests(outputs_dir, days=7)

    if not hist_entries:
        logger.warning("No daily digest data found for weekly summary")
        return

    # Load the full digest.json for richer data
    digest_path = Path(outputs_dir) / "digest.json"
    if not digest_path.exists():
        logger.warning(f"No {digest_path} found")
        return

    # Build weekly summary from history entries
    total = len(hist_entries)
    source_counts: dict[str, int] = {}
    for e in hist_entries:
        src = e.get("source", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1

    now = datetime.now(timezone.utc)
    week_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    week_end = now.strftime("%Y-%m-%d")

    # Generate a simple weekly markdown summary
    lines = [
        f"# \U0001f4ca Weekly AI Digest — {week_start} to {week_end}",
        "",
        f"**{total} items curated this week** across {len(source_counts)} sources.",
        "",
        "## Source Breakdown",
        "",
    ]
    for src, count in sorted(source_counts.items(), key=lambda x: -x[1]):
        lines.append(f"- **{src}**: {count} items")

    lines.append("")
    lines.append("---")
    lines.append(f"_Generated {now.strftime('%Y-%m-%d %H:%M UTC')}_")

    md = "\n".join(lines) + "\n"

    weekly_md = Path(outputs_dir) / "weekly.md"
    weekly_md.write_text(md, encoding="utf-8")
    logger.info(f"Weekly digest written to {weekly_md}")

    # Send weekly email if configured
    to_email = os.getenv("DIGEST_TO_EMAIL")
    from_email = os.getenv("GMAIL_ADDRESS")
    app_password = os.getenv("GMAIL_APP_PASSWORD")
    if to_email and from_email and app_password:
        send_email(
            subject=f"Weekly AI Digest \u2014 {week_start} to {week_end}",
            body_plain=md,
            to_email=to_email,
            from_email=from_email,
            app_password=app_password,
        )
        logger.info(f"Weekly email sent to {to_email}")
