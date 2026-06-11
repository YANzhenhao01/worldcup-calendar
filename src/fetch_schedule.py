from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

try:
    import requests
except ImportError:  # pragma: no cover - exercised on minimal Python installs.
    requests = None


OFFICIAL_PAGE_URL = (
    "https://www.fifa.com/en/tournaments/mens/worldcup/"
    "canadamexicousa2026/articles/"
    "match-schedule-fixtures-results-teams-stadiums"
)

FIFA_API_BASE_URL = "https://api.fifa.com/api/v3/calendar/matches"

DEFAULT_PARAMS = {
    "language": "en",
    "count": "500",
    "idCompetition": "17",
    "from": "2026-06-01T00:00:00Z",
    "to": "2026-07-30T00:00:00Z",
}


class ScheduleFetchError(RuntimeError):
    """Raised when live fetch and cache fallback both fail."""


def build_api_url(params: dict[str, str] | None = None) -> str:
    query = DEFAULT_PARAMS.copy()
    if params:
        query.update(params)
    return f"{FIFA_API_BASE_URL}?{urlencode(query)}"


def fetch_fifa_schedule(timeout: int = 30) -> dict[str, Any]:
    api_url = build_api_url()
    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 worldcup-calendar/1.0",
    }
    if requests is not None:
        response = requests.get(api_url, headers=headers, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
    else:
        request = Request(api_url, headers=headers)
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    if "Results" not in payload:
        raise ScheduleFetchError("FIFA API response did not include Results.")
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source_page_url": OFFICIAL_PAGE_URL,
        "api_url": api_url,
        "payload": payload,
    }


def load_schedule(cache_path: Path, refresh: bool = False) -> dict[str, Any]:
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    if not refresh and cache_path.exists():
        with cache_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)

    try:
        data = fetch_fifa_schedule()
    except Exception as exc:
        if cache_path.exists():
            print(f"Live fetch failed, using cache at {cache_path}: {exc}")
            with cache_path.open("r", encoding="utf-8") as fh:
                return json.load(fh)
        raise ScheduleFetchError(
            "Could not fetch FIFA schedule and no cache is available."
        ) from exc

    with cache_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    return data
