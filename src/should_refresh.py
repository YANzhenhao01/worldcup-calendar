from __future__ import annotations

import json
import os
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CACHE_PATH = ROOT / "data" / "schedule_cache.json"
PRE_MATCH_REFRESH_OFFSET = timedelta(hours=2)
MATCH_DURATION = timedelta(hours=2)
POST_MATCH_REFRESH_WINDOW = timedelta(hours=3)
POST_MATCH_REFRESH_INTERVAL = timedelta(minutes=20)
REFRESH_GRACE = timedelta(minutes=15)
DAILY_REFRESH_TIME_UTC = time(hour=0, minute=0)
DAILY_REFRESH_GRACE = timedelta(minutes=15)


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def current_utc() -> datetime:
    override = os.environ.get("NOW_UTC")
    if override:
        return parse_utc(override)
    return datetime.now(timezone.utc)


def daily_refresh_window(now: datetime) -> tuple[datetime, datetime]:
    start = datetime.combine(now.date(), DAILY_REFRESH_TIME_UTC, tzinfo=timezone.utc)
    return start, start + DAILY_REFRESH_GRACE


def in_refresh_grace(now: datetime, target: datetime) -> bool:
    return target <= now < target + REFRESH_GRACE


def in_post_match_refresh_slot(now: datetime, match_end: datetime) -> bool:
    post_window_end = match_end + POST_MATCH_REFRESH_WINDOW
    if not match_end <= now <= post_window_end:
        return False
    elapsed = now - match_end
    slot_offset = elapsed.total_seconds() % POST_MATCH_REFRESH_INTERVAL.total_seconds()
    return slot_offset < REFRESH_GRACE.total_seconds()


def match_refresh_due(raw_data: dict[str, Any], now: datetime) -> tuple[bool, str]:
    for row in raw_data.get("payload", {}).get("Results", []):
        kickoff = parse_utc(row["Date"])
        match_end = kickoff + MATCH_DURATION
        match_number = str(row.get("MatchNumber", row.get("IdMatch", "unknown")))

        pre_match_refresh = kickoff - PRE_MATCH_REFRESH_OFFSET
        if in_refresh_grace(now, pre_match_refresh):
            return (
                True,
                f"pre-match refresh for match {match_number}: "
                f"{pre_match_refresh.isoformat()} to "
                f"{(pre_match_refresh + REFRESH_GRACE).isoformat()}",
            )

        if in_refresh_grace(now, kickoff):
            return (
                True,
                f"kickoff refresh for match {match_number}: "
                f"{kickoff.isoformat()} to {(kickoff + REFRESH_GRACE).isoformat()}",
            )

        if in_post_match_refresh_slot(now, match_end):
            return (
                True,
                f"post-match 20-minute refresh slot for match {match_number}: "
                f"{match_end.isoformat()} to "
                f"{(match_end + POST_MATCH_REFRESH_WINDOW).isoformat()}",
            )

    return False, "no match refresh due"


def should_refresh(now: datetime, cache_path: Path) -> tuple[bool, str]:
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    if event_name == "workflow_dispatch":
        return True, "manual workflow_dispatch run"

    with cache_path.open("r", encoding="utf-8") as fh:
        raw_data = json.load(fh)

    match_due, match_reason = match_refresh_due(raw_data, now)
    if match_due:
        return True, match_reason

    daily_start, daily_end = daily_refresh_window(now)
    if daily_start <= now < daily_end:
        return (
            True,
            f"within daily safety refresh window: "
            f"{daily_start.isoformat()} to {daily_end.isoformat()}",
        )

    return False, f"{match_reason}; outside daily safety refresh window"


def write_github_output(should_run: bool, reason: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8") as fh:
        fh.write(f"should_run={'true' if should_run else 'false'}\n")
        fh.write(f"reason={reason}\n")


def main() -> None:
    now = current_utc()
    cache_path = Path(os.environ.get("SCHEDULE_CACHE_PATH", DEFAULT_CACHE_PATH))
    should_run, reason = should_refresh(now, cache_path)
    print(f"Refresh decision: {'run' if should_run else 'skip'}")
    print(f"Reason: {reason}")
    print(f"Now: {now.isoformat()}")
    write_github_output(should_run, reason)


if __name__ == "__main__":
    main()
