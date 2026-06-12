from __future__ import annotations

import argparse
import os
from pathlib import Path

from fetch_schedule import load_schedule
from generate_ics import CALENDAR_NAME, publish_subscription_files, write_ics, write_preview_csv
from hot_match import apply_hot_flags
from normalize_schedule import normalize_schedule


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
CONFIG_DIR = ROOT / "config"
SITE_DIR = ROOT / "site"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate an Apple Calendar subscription feed for the 2026 FIFA World Cup "
            "in Asia/Shanghai time."
        )
    )
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Refetch FIFA data instead of using data/schedule_cache.json.",
    )
    parser.add_argument(
        "--publish-dir",
        default=str(SITE_DIR),
        help="Directory for static subscription files used by GitHub Pages.",
    )
    parser.add_argument(
        "--public-base-url",
        default=os.environ.get(
            "PUBLIC_BASE_URL",
            "https://YANzhenhao01.github.io/worldcup-calendar",
        ),
        help="Public HTTPS base URL used to build webcal and QR subscription links.",
    )
    return parser.parse_args()


def remove_legacy_ics_files(keep_path: Path) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for path in OUTPUT_DIR.glob("*.ics"):
        if path.resolve() != keep_path.resolve():
            path.unlink()


def main() -> None:
    args = parse_args()
    raw = load_schedule(DATA_DIR / "schedule_cache.json", refresh=args.refresh)
    matches = normalize_schedule(raw)
    matches = apply_hot_flags(
        matches,
        CONFIG_DIR / "hot_teams.yaml",
        CONFIG_DIR / "hot_matches.yaml",
    )

    hot_matches = [match for match in matches if match.hot]
    preview_path = OUTPUT_DIR / "schedule_preview.csv"
    ics_path = OUTPUT_DIR / "worldcup_2026_china.ics"

    remove_legacy_ics_files(ics_path)
    write_preview_csv(matches, preview_path)
    write_ics(matches, ics_path, CALENDAR_NAME)
    publish_dir = Path(args.publish_dir)
    if not publish_dir.is_absolute():
        publish_dir = ROOT / publish_dir
    publish_subscription_files(ics_path, publish_dir, args.public_base_url)

    written = [
        preview_path,
        ics_path,
        publish_dir / "worldcup_2026.ics",
        publish_dir / "index.html",
        publish_dir / "subscribe-qr.svg",
    ]
    group_stage_count = sum(1 for match in matches if match.stage == "First Stage")
    print(
        f"Loaded {len(matches)} tournament matches; "
        f"group-stage matches: {group_stage_count}; hot matches: {len(hot_matches)}"
    )
    print("Generated files:")
    for path in written:
        print(f"- {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
