from __future__ import annotations

import csv
import hashlib
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from normalize_schedule import Match


CALENDAR_NAME = "2026 FIFA World Cup"
CHINA_TIMEZONE = "Asia/Shanghai"
HOT_MATCH_COLOR = "#FF3B30"
GROUP_STAGE_COLOR = "#0A84FF"
KNOCKOUT_COLOR = "#34C759"

FLAG_OVERRIDES = {
    "CPV": "🇨🇻",
    "COD": "🇨🇩",
    "CIV": "🇨🇮",
    "CUW": "🇨🇼",
    "ENG": "🏴",
    "GER": "🇩🇪",
    "KSA": "🇸🇦",
    "MAR": "🇲🇦",
    "NED": "🇳🇱",
    "PAR": "🇵🇾",
    "RSA": "🇿🇦",
    "SCO": "🏴",
    "SUI": "🇨🇭",
    "TUR": "🇹🇷",
}

FIFA_TO_ISO2 = {
    "ALG": "DZ",
    "ARG": "AR",
    "AUS": "AU",
    "AUT": "AT",
    "BEL": "BE",
    "BIH": "BA",
    "BRA": "BR",
    "CAN": "CA",
    "COL": "CO",
    "CRO": "HR",
    "CZE": "CZ",
    "ECU": "EC",
    "EGY": "EG",
    "FRA": "FR",
    "GHA": "GH",
    "HAI": "HT",
    "IRN": "IR",
    "IRQ": "IQ",
    "JOR": "JO",
    "JPN": "JP",
    "KOR": "KR",
    "MEX": "MX",
    "NOR": "NO",
    "NZL": "NZ",
    "PAN": "PA",
    "POR": "PT",
    "QAT": "QA",
    "SEN": "SN",
    "ESP": "ES",
    "SWE": "SE",
    "TUN": "TN",
    "URU": "UY",
    "USA": "US",
    "UZB": "UZ",
}


def flag_for(code: str) -> str:
    code = (code or "").upper()
    if code in FLAG_OVERRIDES:
        return FLAG_OVERRIDES[code]
    iso2 = FIFA_TO_ISO2.get(code, code[:2])
    if len(iso2) != 2 or not iso2.isalpha():
        return ""
    return "".join(chr(127397 + ord(char)) for char in iso2.upper())


def event_title(match: Match) -> str:
    home_flag = flag_for(match.home_country_code)
    away_flag = flag_for(match.away_country_code)
    title = f"{home_flag} {match.home_team} vs {match.away_team} {away_flag}"
    title = " ".join(title.split())
    return f"🔥 {title}" if match.hot else title


def escape_ics_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def fold_line(line: str) -> str:
    encoded = line.encode("utf-8")
    if len(encoded) <= 75:
        return line

    output: list[str] = []
    current = ""
    for char in line:
        if len((current + char).encode("utf-8")) > 75:
            output.append(current)
            current = " " + char
        else:
            current += char
    output.append(current)
    return "\r\n".join(output)


def format_datetime(dt: datetime, tz_name: str | None = None) -> str:
    if tz_name:
        zoned = dt.astimezone(ZoneInfo(tz_name))
        return f"TZID={tz_name}:{zoned.strftime('%Y%m%dT%H%M%S')}"
    return dt.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def event_description(match: Match, start_dt: datetime) -> str:
    broadcaster = match.broadcaster or "Not published in the FIFA API response."
    hot_reason = match.hot_reason or "N/A"
    score = "Not played"
    if match.home_score is not None and match.away_score is not None:
        score = f"{match.home_team} {match.home_score}-{match.away_score} {match.away_team}"
        if match.home_penalty_score is not None and match.away_penalty_score is not None:
            score += f" (pens {match.home_penalty_score}-{match.away_penalty_score})"
    group_or_stage = match.group or match.stage
    return "\n".join(
        [
            f"Stage: {match.stage}",
            f"Group: {match.group or 'N/A'}",
            f"Round/Group: {group_or_stage}",
            f"Hot Match: {'Yes' if match.hot else 'No'}",
            f"Hot Reason: {hot_reason}",
            f"Final Score: {score}",
            f"FIFA Match Status: {match.match_status if match.match_status is not None else 'N/A'}",
            f"Venue: {match.venue}",
            f"City/Country: {match.city}, {match.country}",
            f"Kickoff: {start_dt.isoformat()}",
            f"Local timezone: {match.local_timezone}",
            f"Broadcaster: {broadcaster}",
            f"Data source: {match.source_page_url}",
            f"API source: {match.api_url}",
            "Notes: This is a subscription feed. FIFA updates to teams, scores, and later rounds are published with stable event UIDs.",
        ]
    )


def event_category(match: Match) -> str:
    if match.hot:
        return "Hot Match"
    if match.stage == "First Stage":
        return "Group Stage"
    return match.stage or "Knockout Stage"


def event_color(match: Match) -> str:
    if match.hot:
        return HOT_MATCH_COLOR
    if match.stage == "First Stage":
        return GROUP_STAGE_COLOR
    return KNOCKOUT_COLOR


def event_uid(match: Match) -> str:
    return f"fifa-2026-match-{match.id_match}@worldcup-calendar"


def write_ics(
    matches: list[Match],
    output_path: Path,
    calendar_name: str = CALENDAR_NAME,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "PRODID:-//Codex//2026 FIFA World Cup Calendar//EN",
        f"X-WR-CALNAME:{escape_ics_text(calendar_name)}",
        f"X-WR-TIMEZONE:{escape_ics_text(CHINA_TIMEZONE)}",
        f"X-APPLE-CALENDAR-COLOR:{GROUP_STAGE_COLOR}",
        "REFRESH-INTERVAL;VALUE=DURATION:PT30M",
        "X-PUBLISHED-TTL:PT30M",
    ]

    for match in matches:
        start = match.start_utc.astimezone(ZoneInfo(CHINA_TIMEZONE))
        end = start + timedelta(hours=2)
        description = event_description(match, start)
        categories = event_category(match)
        color = event_color(match)
        revision_seed = "|".join(
            [
                match.id_match,
                match.home_team,
                match.away_team,
                str(match.home_score),
                str(match.away_score),
                str(match.match_status),
            ]
        )
        revision_hash = hashlib.sha1(revision_seed.encode("utf-8")).hexdigest()[:12]

        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{event_uid(match)}",
                f"DTSTAMP:{now.strftime('%Y%m%dT%H%M%SZ')}",
                f"LAST-MODIFIED:{now.strftime('%Y%m%dT%H%M%SZ')}",
                "SEQUENCE:0",
                f"DTSTART;{format_datetime(start, CHINA_TIMEZONE)}",
                f"DTEND;{format_datetime(end, CHINA_TIMEZONE)}",
                f"SUMMARY:{escape_ics_text(event_title(match))}",
                f"LOCATION:{escape_ics_text(f'{match.venue}, {match.city}, {match.country}')}",
                f"DESCRIPTION:{escape_ics_text(description)}",
                f"CATEGORIES:{escape_ics_text(categories)}",
                f"COLOR:{color}",
                f"X-APPLE-CALENDAR-COLOR:{color}",
                f"X-APPLE-EVENT-COLOR:{color}",
                f"X-WORLDCUP-REVISION:{revision_hash}",
                f"URL:{escape_ics_text(match.source_page_url)}",
            ]
        )
        for trigger, label in [
            ("-P1D", "Match starts in 1 day"),
            ("-PT2H", "Match starts in 2 hours"),
            ("-PT15M", "Match starts in 15 minutes"),
        ]:
            lines.extend(
                [
                    "BEGIN:VALARM",
                    "ACTION:DISPLAY",
                    f"DESCRIPTION:{escape_ics_text(label)}",
                    f"TRIGGER:{trigger}",
                    "END:VALARM",
                ]
            )
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    output = "\r\n".join(fold_line(line) for line in lines) + "\r\n"
    output_path.write_text(output, encoding="utf-8")


def write_preview_csv(matches: list[Match], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    china_tz = ZoneInfo("Asia/Shanghai")
    fields = [
        "id_match",
        "match_number",
        "stage",
        "group",
        "home_team",
        "away_team",
        "hot",
        "hot_reason",
        "home_score",
        "away_score",
        "match_status",
        "start_utc",
        "start_local",
        "local_timezone",
        "start_china",
        "venue",
        "city",
        "country",
        "source_page_url",
        "api_url",
    ]
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for match in matches:
            writer.writerow(
                {
                    "id_match": match.id_match,
                    "match_number": match.match_number,
                    "stage": match.stage,
                    "group": match.group,
                    "home_team": match.home_team,
                    "away_team": match.away_team,
                    "hot": match.hot,
                    "hot_reason": match.hot_reason or "",
                    "home_score": match.home_score,
                    "away_score": match.away_score,
                    "match_status": match.match_status,
                    "start_utc": match.start_utc.isoformat(),
                    "start_local": match.start_local.isoformat(),
                    "local_timezone": match.local_timezone,
                    "start_china": match.start_utc.astimezone(china_tz).isoformat(),
                    "venue": match.venue,
                    "city": match.city,
                    "country": match.country,
                    "source_page_url": match.source_page_url,
                    "api_url": match.api_url,
                }
            )


def publish_subscription_files(ics_path: Path, publish_dir: Path) -> None:
    publish_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ics_path, publish_dir / "worldcup_2026.ics")
    (publish_dir / "index.html").write_text(
        """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>2026 FIFA World Cup Calendar</title>
</head>
<body>
  <h1>2026 FIFA World Cup Calendar</h1>
  <p>Subscribe to <a href="worldcup_2026.ics">worldcup_2026.ics</a> in Apple Calendar.</p>
  <p>This feed is generated from FIFA's official schedule data and uses Asia/Shanghai time.</p>
</body>
</html>
""",
        encoding="utf-8",
    )
