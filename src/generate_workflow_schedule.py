from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from should_refresh import (
    DAILY_REFRESH_TIME_UTC,
    MATCH_DURATION,
    POST_MATCH_REFRESH_INTERVAL,
    POST_MATCH_REFRESH_WINDOW,
    PRE_MATCH_REFRESH_OFFSET,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_PATH = ROOT / "data" / "schedule_cache.json"
DEFAULT_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "update-calendar.yml"
SCHEDULE_TRIGGER_DELAY = timedelta(minutes=5)


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def load_schedule(cache_path: Path) -> dict[str, Any]:
    with cache_path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def match_refresh_points(raw_data: dict[str, Any]) -> set[datetime]:
    points: set[datetime] = set()
    for row in raw_data.get("payload", {}).get("Results", []):
        kickoff = parse_utc(row["Date"]).replace(second=0, microsecond=0)
        points.add(kickoff - PRE_MATCH_REFRESH_OFFSET)
        points.add(kickoff)

        match_end = kickoff + MATCH_DURATION
        post_match_end = match_end + POST_MATCH_REFRESH_WINDOW
        current = match_end
        while current <= post_match_end:
            points.add(current)
            current += POST_MATCH_REFRESH_INTERVAL
    return points


def grouped_cron_entries(points: set[datetime]) -> list[str]:
    grouped: dict[tuple[int, int, int], set[int]] = defaultdict(set)
    for point in points:
        trigger_time = point + SCHEDULE_TRIGGER_DELAY
        grouped[(trigger_time.month, trigger_time.day, trigger_time.hour)].add(trigger_time.minute)

    entries: list[str] = []
    for month, day, hour in sorted(grouped):
        minutes = ",".join(str(minute) for minute in sorted(grouped[(month, day, hour)]))
        entries.append(f'    - cron: "{minutes} {hour} {day} {month} *"')
    return entries


def daily_safety_entry(points: set[datetime]) -> str:
    months = ",".join(str(month) for month in sorted({point.month for point in points}))
    trigger_time = datetime.combine(
        datetime.now(timezone.utc).date(),
        DAILY_REFRESH_TIME_UTC,
        tzinfo=timezone.utc,
    ) + SCHEDULE_TRIGGER_DELAY
    return f'    - cron: "{trigger_time.minute} {trigger_time.hour} * {months} *"'


def generated_schedule_block(raw_data: dict[str, Any]) -> str:
    points = match_refresh_points(raw_data)
    entries = [
        "  schedule:",
        "    # Generated from data/schedule_cache.json by src/generate_workflow_schedule.py.",
        "    # Cron entries fire 5 minutes after target refresh points to avoid top-of-hour scheduler load.",
        "    # Daily safety refresh; workflow cutoff prevents runs after the tournament window.",
        daily_safety_entry(points),
        "    # Match refresh points: kickoff-2h, kickoff, then every 20 minutes for 3 hours after the scheduled match block.",
        *grouped_cron_entries(points),
    ]
    return "\n".join(entries)


def replace_schedule_block(workflow_text: str, schedule_block: str) -> str:
    start_marker = "  schedule:\n"
    end_marker = "\n\npermissions:"
    start = workflow_text.index(start_marker)
    end = workflow_text.index(end_marker, start)
    return f"{workflow_text[:start]}{schedule_block}{workflow_text[end:]}"


def main() -> None:
    raw_data = load_schedule(DEFAULT_CACHE_PATH)
    workflow_text = DEFAULT_WORKFLOW_PATH.read_text(encoding="utf-8")
    schedule_block = generated_schedule_block(raw_data)
    updated = replace_schedule_block(workflow_text, schedule_block)
    DEFAULT_WORKFLOW_PATH.write_text(updated, encoding="utf-8")

    point_count = len(match_refresh_points(raw_data))
    cron_count = schedule_block.count("- cron:")
    print(f"Generated {point_count} match refresh points into {cron_count} cron entries.")
    print(f"Updated {DEFAULT_WORKFLOW_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
