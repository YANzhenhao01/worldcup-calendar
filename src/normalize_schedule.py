from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


CITY_TIMEZONES = {
    "Atlanta": "America/New_York",
    "Boston": "America/New_York",
    "Dallas": "America/Chicago",
    "Guadalajara": "America/Mexico_City",
    "Houston": "America/Chicago",
    "Kansas City": "America/Chicago",
    "Los Angeles": "America/Los_Angeles",
    "Mexico City": "America/Mexico_City",
    "Miami": "America/New_York",
    "Monterrey": "America/Monterrey",
    "New Jersey": "America/New_York",
    "Philadelphia": "America/New_York",
    "San Francisco Bay Area": "America/Los_Angeles",
    "Seattle": "America/Los_Angeles",
    "Toronto": "America/Toronto",
    "Vancouver": "America/Vancouver",
}

HOST_COUNTRIES = {
    "CAN": "Canada",
    "MEX": "Mexico",
    "USA": "USA",
}


@dataclass(frozen=True)
class Match:
    id_match: str
    match_number: int
    stage: str
    group: str
    home_team: str
    away_team: str
    home_code: str
    away_code: str
    home_country_code: str
    away_country_code: str
    start_utc: datetime
    start_local: datetime
    local_timezone: str
    venue: str
    city: str
    country: str
    source_page_url: str
    api_url: str
    match_status: int | None = None
    home_score: int | None = None
    away_score: int | None = None
    home_penalty_score: int | None = None
    away_penalty_score: int | None = None
    winner_team_id: str | None = None
    broadcaster: str | None = None
    hot: bool = False
    hot_reason: str | None = None


def localized_text(items: list[dict] | None, default: str = "") -> str:
    if not items:
        return default
    for item in items:
        if item.get("Locale", "").lower() in {"en-gb", "en-us", "en"}:
            return item.get("Description", default)
    return items[0].get("Description", default)


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def team_name(team: dict) -> str:
    return team.get("ShortClubName") or localized_text(team.get("TeamName"))


def participant_name(team: dict, placeholder: str | None) -> str:
    name = team_name(team)
    if name:
        return name
    return placeholder or "TBD"


def normalize_schedule(raw_data: dict, group_stage_only: bool = False) -> list[Match]:
    payload = raw_data["payload"]
    matches: list[Match] = []

    for row in payload.get("Results", []):
        stage = localized_text(row.get("StageName"))
        if group_stage_only and stage != "First Stage":
            continue

        stadium = row.get("Stadium") or {}
        city = localized_text(stadium.get("CityName"))
        if city not in CITY_TIMEZONES:
            raise ValueError(f"No timezone mapping for host city: {city}")

        tz_name = CITY_TIMEZONES[city]
        local_tz = ZoneInfo(tz_name)
        start_utc = parse_utc(row["Date"])
        start_local = start_utc.astimezone(local_tz)

        fifa_local = row.get("LocalDate")
        if fifa_local:
            local_wall = start_local.replace(tzinfo=None).isoformat(timespec="seconds")
            fifa_wall = fifa_local.replace("Z", "")
            if fifa_wall != local_wall:
                raise ValueError(
                    f"Local time mismatch for match {row.get('MatchNumber')}: "
                    f"FIFA LocalDate={fifa_local}, calculated={local_wall} {tz_name}"
                )

        home = row.get("Home") or {}
        away = row.get("Away") or {}
        country_code = stadium.get("IdCountry", "")

        matches.append(
            Match(
                id_match=str(row["IdMatch"]),
                match_number=int(row["MatchNumber"]),
                stage=stage,
                group=localized_text(row.get("GroupName")),
                home_team=participant_name(home, row.get("PlaceHolderA")),
                away_team=participant_name(away, row.get("PlaceHolderB")),
                home_code=home.get("Abbreviation", ""),
                away_code=away.get("Abbreviation", ""),
                home_country_code=home.get("IdCountry", ""),
                away_country_code=away.get("IdCountry", ""),
                start_utc=start_utc,
                start_local=start_local,
                local_timezone=tz_name,
                venue=localized_text(stadium.get("Name")),
                city=city,
                country=HOST_COUNTRIES.get(country_code, country_code),
                source_page_url=raw_data.get("source_page_url", ""),
                api_url=raw_data.get("api_url", ""),
                match_status=row.get("MatchStatus"),
                home_score=row.get("HomeTeamScore"),
                away_score=row.get("AwayTeamScore"),
                home_penalty_score=row.get("HomeTeamPenaltyScore"),
                away_penalty_score=row.get("AwayTeamPenaltyScore"),
                winner_team_id=row.get("Winner"),
                broadcaster=None,
            )
        )

    matches.sort(key=lambda match: match.match_number)
    expected_count = 72 if group_stage_only else 104
    if len(matches) != expected_count:
        label = "group-stage" if group_stage_only else "tournament"
        raise ValueError(f"Expected {expected_count} {label} matches, found {len(matches)}.")

    group_stage_count = sum(1 for match in matches if match.stage == "First Stage")
    if group_stage_count != 72:
        raise ValueError(f"Expected 72 group-stage matches, found {group_stage_count}.")
    return matches
