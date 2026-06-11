# 2026 FIFA World Cup Subscription Calendar

Generate an auto-updating Apple Calendar subscription feed for the full 2026 FIFA World Cup schedule.

The project now produces a subscription-ready ICS feed, not a one-time import file. After it is hosted on GitHub Pages or another HTTPS host, Apple Calendar only needs to subscribe once. Later FIFA updates to knockout teams, scores, and results are picked up when the feed refreshes.

## Data Source

Primary source:

- FIFA official schedule page: <https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/articles/match-schedule-fixtures-results-teams-stadiums>
- FIFA structured API used by the page: `https://api.fifa.com/api/v3/calendar/matches`

The generator fetches FIFA's official API, validates that the full tournament contains 104 matches, and separately validates that the group stage contains 72 matches. The raw response is cached at `data/schedule_cache.json`; if a live fetch fails, the script falls back to that cache.

The knockout schedule is generated from FIFA's official match records. When FIFA still shows placeholders such as `2A vs 2B`, the feed shows those placeholders. When FIFA later publishes real teams, the same event UID is updated with the real team names.

## Local Generation

Generate from cache if available:

```bash
python3 src/main.py
```

Refresh FIFA data and regenerate:

```bash
python3 src/main.py --refresh
```

Generated local files:

- `output/worldcup_2026_china.ics`: full 104-match China-time ICS feed.
- `output/schedule_preview.csv`: preview table for manual checking.
- `site/worldcup_2026.ics`: static file intended for web hosting.
- `site/index.html`: tiny landing page for the hosted feed.

All event times are converted to `Asia/Shanghai`.

## Auto-Update Hosting

The recommended hosting path is GitHub Pages with GitHub Actions.

This repository includes:

```text
.github/workflows/update-calendar.yml
```

The workflow:

1. Runs every 30 minutes and also supports manual runs.
2. Fetches the latest FIFA schedule.
3. Regenerates `site/worldcup_2026.ics`.
4. Publishes the `site/` directory to GitHub Pages.

After GitHub Pages is enabled, the subscription URL will look like:

```text
https://<your-github-username>.github.io/<repo-name>/worldcup_2026.ics
```

For example, if the repository is named `worldcup-calendar` under `YANzhenhao01`, the URL will be:

```text
https://YANzhenhao01.github.io/worldcup-calendar/worldcup_2026.ics
```

In Apple Calendar, use `File > New Calendar Subscription...` and paste that HTTPS URL.

Important: make `worldcup-calendar/` the repository root. The workflow must live at `.github/workflows/update-calendar.yml` at the root of the GitHub repository.

## GitHub Setup Checklist

1. Create a new public GitHub repository, recommended name: `worldcup-calendar`.
2. Push or upload the contents of this local `worldcup-calendar/` folder to that repository root.
3. In the GitHub repository, open `Settings > Pages`.
4. Under `Build and deployment`, set `Source` to `GitHub Actions`.
5. Open the `Actions` tab.
6. Run `Update World Cup Calendar` manually once, or wait for the scheduled run.
7. After the workflow succeeds, subscribe in Apple Calendar to:

```text
https://YANzhenhao01.github.io/worldcup-calendar/worldcup_2026.ics
```

## Apple Calendar Setup

Do not use `File > Import...` for the auto-updating version. Importing copies a snapshot and will not update later.

Use subscription instead:

1. Open Apple Calendar on macOS.
2. Choose `File > New Calendar Subscription...`.
3. Paste the hosted `worldcup_2026.ics` URL.
4. Set Auto-refresh to the shortest interval Apple Calendar offers.
5. Keep it as a separate subscribed calendar, so it can be removed cleanly later.

iPhone:

1. Open the hosted `worldcup_2026.ics` or `webcal://` URL.
2. Add it as a subscribed calendar.
3. Avoid importing it as a static file.

## Update Behavior

To avoid duplicate events, each match uses a stable UID based on FIFA's `IdMatch`:

```text
fifa-2026-match-<IdMatch>@worldcup-calendar
```

When a placeholder matchup becomes a real matchup, or when scores become available, the feed updates the existing event with the same UID.

Each event includes:

- 2-hour duration
- 1 day before kickoff reminder
- 2 hours before kickoff reminder
- 15 minutes before kickoff reminder
- `CATEGORIES:Hot Match` for hot matches
- `CATEGORIES:Group Stage` for normal group matches
- Knockout-stage category names for non-hot knockout matches

The ICS also writes `COLOR`, `X-APPLE-CALENDAR-COLOR`, and `X-APPLE-EVENT-COLOR`. Apple Calendar may ignore per-event colors in subscribed ICS feeds. Hot matches are still clearly marked with `🔥` and `Hot Match: Yes`.

## Hot Matches

Hot-match rules are controlled by:

- `config/hot_teams.yaml`
- `config/hot_matches.yaml`

Hot matches get:

- `🔥` at the start of the event title
- `Hot Match: Yes` in the event description
- `Hot Reason: ...` in the event description
- `CATEGORIES:Hot Match`

Normal matches get `Hot Match: No`.

## Notes

Apple Calendar controls the actual refresh timing. The feed advertises a 30-minute refresh interval with `REFRESH-INTERVAL` and `X-PUBLISHED-TTL`, and the GitHub Action publishes every 30 minutes, but Apple may refresh less aggressively depending on account and device settings.
