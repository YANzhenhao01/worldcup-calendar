from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - exercised on minimal Python installs.
    yaml = None

from normalize_schedule import Match


def parse_simple_yaml(text: str) -> dict[str, Any]:
    """Parse the small list-oriented YAML files used by this project.

    This fallback is intentionally narrow; install PyYAML for general YAML.
    """
    data: dict[str, Any] = {}
    current_key: str | None = None
    current_match: dict[str, Any] | None = None
    current_match_list_key: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if not line.startswith(" ") and stripped.endswith(":"):
            current_key = stripped[:-1]
            data[current_key] = []
            current_match = None
            current_match_list_key = None
            continue
        if current_key is None:
            continue
        if (
            current_key == "hot_matches"
            and current_match is not None
            and current_match_list_key
            and stripped.startswith("- ")
        ):
            current_match[current_match_list_key].append(stripped[2:].strip())
            continue
        if stripped.startswith("- "):
            value = stripped[2:].strip()
            if current_key == "hot_matches":
                current_match = {}
                data[current_key].append(current_match)
                current_match_list_key = None
                if value and ":" in value:
                    key, item_value = value.split(":", 1)
                    key = key.strip()
                    item_value = item_value.strip()
                    if item_value:
                        current_match[key] = item_value
                    else:
                        current_match[key] = []
                        current_match_list_key = key
            else:
                data[current_key].append(value)
            continue
        if current_key == "hot_matches" and current_match is not None:
            if stripped.endswith(":"):
                current_match_list_key = stripped[:-1]
                current_match[current_match_list_key] = []
            elif ":" in stripped:
                key, value = stripped.split(":", 1)
                current_match[key.strip()] = value.strip()
                current_match_list_key = None

    return data


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as fh:
        text = fh.read()
    if yaml is not None:
        return yaml.safe_load(text) or {}
    return parse_simple_yaml(text)


def ordered_pair(home: str, away: str) -> tuple[str, str]:
    return (home.strip().casefold(), away.strip().casefold())


def unordered_pair(home: str, away: str) -> frozenset[str]:
    return frozenset({home.strip().casefold(), away.strip().casefold()})


def manual_hot_reason(match: Match, manual_matches: list[dict[str, Any]]) -> str | None:
    current_ordered = ordered_pair(match.home_team, match.away_team)
    current_unordered = unordered_pair(match.home_team, match.away_team)
    for item in manual_matches:
        reason = item.get("reason") or "Manual hot match"
        if "match_number" in item and int(item["match_number"]) == match.match_number:
            return reason
        if "home" in item and "away" in item:
            if ordered_pair(item["home"], item["away"]) == current_ordered:
                return reason
        if "teams" in item and len(item["teams"]) == 2:
            if unordered_pair(item["teams"][0], item["teams"][1]) == current_unordered:
                return reason
    return None


def apply_hot_flags(
    matches: list[Match], hot_teams_path: Path, hot_matches_path: Path
) -> list[Match]:
    team_config = load_yaml(hot_teams_path)
    match_config = load_yaml(hot_matches_path)

    traditional = set(team_config.get("traditional_powers", []))
    hosts = set(team_config.get("hosts", []))
    high_attention = set(team_config.get("high_attention", []))
    traditional_cf = {name.casefold() for name in traditional}
    hosts_cf = {name.casefold() for name in hosts}
    high_attention_cf = {name.casefold() for name in high_attention}
    manual_matches = match_config.get("hot_matches", [])

    result: list[Match] = []
    for match in matches:
        teams = {match.home_team.casefold(), match.away_team.casefold()}
        reason = manual_hot_reason(match, manual_matches)

        if not reason and teams & hosts_cf:
            reason = "Host nation match"
        if not reason and len(teams & traditional_cf) >= 2:
            reason = "Traditional power matchup"
        if not reason and teams & high_attention_cf:
            reason = "High-attention team"

        result.append(replace(match, hot=bool(reason), hot_reason=reason))
    return result
