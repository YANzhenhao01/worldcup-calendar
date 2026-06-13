from __future__ import annotations

import csv
import html
import hashlib
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import qrcode
import qrcode.image.svg

from normalize_schedule import Match


CALENDAR_NAME = "2026 FIFA World Cup"
CHINA_TIMEZONE = "Asia/Shanghai"
DEFAULT_PUBLIC_BASE_URL = "https://YANzhenhao01.github.io/worldcup-calendar"
MATCH_DURATION = timedelta(hours=2)
FEED_REFRESH_INTERVAL = "PT2H"
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


def score_or_status(match: Match, start_dt: datetime, generated_at: datetime) -> str:
    if match.home_score is not None and match.away_score is not None:
        score = f"{match.home_team} {match.home_score}-{match.away_score} {match.away_team}"
        if match.home_penalty_score is not None and match.away_penalty_score is not None:
            score += f" (pens {match.home_penalty_score}-{match.away_penalty_score})"
        return f"Final Score: {score}"

    end_dt = start_dt + MATCH_DURATION
    generated_local = generated_at.astimezone(start_dt.tzinfo)
    if generated_local < start_dt:
        return "Match Status: Not started"
    if generated_local <= end_dt:
        return "Match Status: In progress; live score not yet published by FIFA."
    return "Match Status: Waiting for FIFA result update."


def event_description(match: Match, start_dt: datetime, generated_at: datetime) -> str:
    hot_reason = match.hot_reason or "N/A"
    return "\n".join(
        [
            f"Stage: {match.stage}",
            f"Group: {match.group or 'N/A'}",
            f"Hot Match: {'Yes' if match.hot else 'No'}",
            f"Hot Reason: {hot_reason}",
            score_or_status(match, start_dt, generated_at),
            f"Venue: {match.venue}",
            f"City/Country: {match.city}, {match.country}",
            f"Kickoff: {start_dt.isoformat()}",
            f"Local timezone: {match.local_timezone}",
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
        f"REFRESH-INTERVAL;VALUE=DURATION:{FEED_REFRESH_INTERVAL}",
        f"X-PUBLISHED-TTL:{FEED_REFRESH_INTERVAL}",
    ]

    for match in matches:
        start = match.start_utc.astimezone(ZoneInfo(CHINA_TIMEZONE))
        end = start + MATCH_DURATION
        description = event_description(match, start, now)
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


def normalize_public_base_url(public_base_url: str) -> str:
    public_base_url = (public_base_url or DEFAULT_PUBLIC_BASE_URL).strip().rstrip("/")
    if not public_base_url:
        return DEFAULT_PUBLIC_BASE_URL
    if "://" not in public_base_url:
        public_base_url = f"https://{public_base_url}"
    return public_base_url


def subscription_urls(public_base_url: str) -> tuple[str, str, str]:
    public_base_url = normalize_public_base_url(public_base_url)
    split = urlsplit(public_base_url)
    https_base_url = urlunsplit(("https", split.netloc, split.path.rstrip("/"), "", ""))
    https_ics_url = f"{https_base_url}/worldcup_2026.ics"
    webcal_url = urlunsplit(("webcal", split.netloc, f"{split.path.rstrip('/')}/worldcup_2026.ics", "", ""))
    page_url = f"{https_base_url}/"
    return https_ics_url, webcal_url, page_url


def write_subscription_qr(output_path: Path, webcal_url: str) -> None:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=2,
    )
    qr.add_data(webcal_url)
    qr.make(fit=True)
    image = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    image.save(output_path)


def landing_page_html(public_base_url: str) -> str:
    https_ics_url, webcal_url, page_url = subscription_urls(public_base_url)
    escaped_https_url = html.escape(https_ics_url, quote=True)
    escaped_webcal_url = html.escape(webcal_url, quote=True)
    escaped_page_url = html.escape(page_url, quote=True)
    project_root = Path(__file__).resolve().parents[1]
    checked_in_page = project_root / "site" / "index.html"
    if checked_in_page.exists():
        page_html = checked_in_page.read_text(encoding="utf-8")
        if "data-last-updated" in page_html and "worldcup-hero-bg.png" in page_html:
            escaped_default_page_url = html.escape(
                normalize_public_base_url(DEFAULT_PUBLIC_BASE_URL) + "/",
                quote=True,
            )
            escaped_default_webcal_url = html.escape(
                subscription_urls(DEFAULT_PUBLIC_BASE_URL)[1],
                quote=True,
            )
            display_page_url = escaped_page_url.removesuffix("/")
            display_default_page_url = escaped_default_page_url.removesuffix("/")
            return (
                page_html
                .replace(escaped_default_webcal_url, escaped_webcal_url)
                .replace(escaped_default_page_url, escaped_page_url)
                .replace(display_default_page_url, display_page_url)
            )

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#101410">
  <link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Ctext y='52' font-size='52'%3E%E2%9A%BD%3C/text%3E%3C/svg%3E">
  <title>2026 世界杯订阅日历</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #101410;
      --muted: #5b635c;
      --line: #dbe4dc;
      --field: #f6fbf5;
      --surface: #ffffff;
      --grass: #0f8a3b;
      --grass-dark: #08662a;
      --gold: #d9a441;
      --red: #f14b3f;
      --shadow: 0 18px 55px rgba(16, 20, 16, 0.12);
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 16% 8%, rgba(15, 138, 59, 0.16), transparent 28rem),
        linear-gradient(180deg, #ffffff 0%, #f3faf2 46%, #e8f4e8 100%);
      color: var(--ink);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }}

    a {{
      color: inherit;
    }}

    .page {{
      width: min(1120px, calc(100% - 32px));
      margin: 0 auto;
      padding: 22px 0 42px;
    }}

    .nav {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 34px;
    }}

    .brand {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      font-weight: 850;
      font-size: 15px;
    }}

    .ball {{
      display: grid;
      place-items: center;
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: var(--ink);
      color: #ffffff;
      box-shadow: 0 8px 20px rgba(16, 20, 16, 0.18);
    }}

    .nav-link {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 38px;
      padding: 0 14px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.74);
      font-size: 14px;
      font-weight: 750;
      text-decoration: none;
    }}

    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 1.08fr) minmax(320px, 0.72fr);
      gap: 28px;
      align-items: stretch;
    }}

    .hero-copy {{
      padding: 48px 0 22px;
    }}

    h1 {{
      max-width: 760px;
      margin: 0;
      font-size: clamp(42px, 6vw, 82px);
      line-height: 0.96;
      letter-spacing: 0;
    }}

    h1 span {{
      display: block;
      white-space: nowrap;
    }}

    .lead {{
      max-width: 640px;
      margin: 22px 0 0;
      color: var(--muted);
      font-size: clamp(17px, 2vw, 22px);
      line-height: 1.58;
    }}

    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      margin-top: 30px;
    }}

    .button {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 52px;
      padding: 0 20px;
      border-radius: 8px;
      border: 1px solid transparent;
      font-size: 16px;
      font-weight: 850;
      text-decoration: none;
      cursor: pointer;
    }}

    .button.primary {{
      background: var(--ink);
      color: #ffffff;
      box-shadow: 0 14px 34px rgba(16, 20, 16, 0.2);
    }}

    .button.secondary {{
      background: #ffffff;
      border-color: var(--line);
      color: var(--ink);
    }}

    .signal-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 26px;
    }}

    .signal {{
      display: inline-flex;
      align-items: center;
      min-height: 34px;
      padding: 0 11px;
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.78);
      border: 1px solid var(--line);
      color: #303830;
      font-size: 13px;
      font-weight: 760;
    }}

    .subscribe-panel {{
      position: relative;
      overflow: hidden;
      border-radius: 8px;
      background:
        linear-gradient(160deg, rgba(16, 20, 16, 0.96), rgba(15, 88, 42, 0.94)),
        repeating-linear-gradient(90deg, transparent 0 58px, rgba(255, 255, 255, 0.05) 58px 60px);
      color: #ffffff;
      box-shadow: var(--shadow);
      padding: 22px;
    }}

    .subscribe-panel::before {{
      content: "";
      position: absolute;
      inset: 18px;
      border: 1px solid rgba(255, 255, 255, 0.16);
      border-radius: 8px;
      pointer-events: none;
    }}

    .panel-content {{
      position: relative;
      display: grid;
      gap: 18px;
    }}

    .status {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}

    .live {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      color: #d9ffe1;
      font-size: 13px;
      font-weight: 850;
    }}

    .live-dot {{
      width: 9px;
      height: 9px;
      border-radius: 50%;
      background: #35f071;
      box-shadow: 0 0 0 7px rgba(53, 240, 113, 0.15);
    }}

    .cup {{
      font-size: 34px;
    }}

    .qr-card {{
      display: grid;
      place-items: center;
      min-height: 278px;
      padding: 20px;
      border-radius: 8px;
      background: #ffffff;
      color: var(--ink);
    }}

    .qr-card img {{
      width: min(220px, 70vw);
      height: auto;
      display: block;
    }}

    .qr-caption {{
      margin: 12px 0 0;
      color: var(--muted);
      font-size: 13px;
      font-weight: 740;
      text-align: center;
    }}

    .url-box {{
      display: grid;
      gap: 10px;
      padding: 14px;
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.1);
      border: 1px solid rgba(255, 255, 255, 0.16);
    }}

    .url-label {{
      color: #cfe8d2;
      font-size: 12px;
      font-weight: 800;
    }}

    code {{
      overflow-wrap: anywhere;
      font-family: "SFMono-Regular", Consolas, monospace;
      font-size: 12px;
      color: #ffffff;
    }}

    .copy-button {{
      width: 100%;
      min-height: 44px;
      border: 0;
      border-radius: 8px;
      background: var(--gold);
      color: var(--ink);
      font-size: 14px;
      font-weight: 900;
      cursor: pointer;
    }}

    .section-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
      margin-top: 34px;
    }}

    .info-card {{
      min-height: 166px;
      padding: 20px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.82);
      box-shadow: 0 10px 30px rgba(16, 20, 16, 0.06);
    }}

    .info-card strong {{
      display: block;
      margin-bottom: 10px;
      font-size: 18px;
    }}

    .info-card p {{
      margin: 0;
      color: var(--muted);
      line-height: 1.58;
      font-size: 15px;
    }}

    .steps {{
      margin-top: 18px;
      padding: 0;
      list-style: none;
    }}

    .steps li {{
      display: flex;
      gap: 10px;
      align-items: flex-start;
      margin-top: 10px;
      color: var(--muted);
      line-height: 1.5;
    }}

    .step-num {{
      flex: 0 0 auto;
      display: grid;
      place-items: center;
      width: 24px;
      height: 24px;
      border-radius: 50%;
      background: var(--grass);
      color: #ffffff;
      font-size: 12px;
      font-weight: 850;
    }}

    .footer {{
      margin-top: 34px;
      padding-top: 22px;
      border-top: 1px solid var(--line);
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
    }}

    .toast {{
      position: fixed;
      left: 50%;
      bottom: 22px;
      transform: translateX(-50%);
      padding: 12px 16px;
      border-radius: 8px;
      background: var(--ink);
      color: #ffffff;
      font-size: 14px;
      font-weight: 800;
      opacity: 0;
      pointer-events: none;
      transition: opacity 160ms ease, transform 160ms ease;
    }}

    .toast.show {{
      opacity: 1;
      transform: translateX(-50%) translateY(-4px);
    }}

    @media (max-width: 820px) {{
      .page {{
        width: min(100% - 22px, 680px);
        padding-top: 14px;
      }}

      .nav {{
        margin-bottom: 12px;
      }}

      .nav-link {{
        display: none;
      }}

      .hero {{
        grid-template-columns: 1fr;
      }}

      .hero-copy {{
        padding: 22px 0 0;
      }}

      h1 {{
        font-size: clamp(42px, 14vw, 64px);
      }}

      .button {{
        width: 100%;
      }}

      .section-grid {{
        grid-template-columns: 1fr;
      }}
    }}

    @media (prefers-reduced-motion: reduce) {{
      *, *::before, *::after {{
        scroll-behavior: auto !important;
        transition-duration: 0.01ms !important;
        animation-duration: 0.01ms !important;
      }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <nav class="nav" aria-label="页面导航">
      <div class="brand"><span class="ball">⚽</span><span>World Cup Calendar</span></div>
      <a class="nav-link" href="{escaped_https_url}">📄 ICS 文件</a>
    </nav>

    <section class="hero">
      <div class="hero-copy">
        <h1><span>2026 世界杯</span><span>订阅日历</span></h1>
        <p class="lead">把 104 场比赛一次性订阅到 iPhone 日历。北京时间显示，热门比赛 🔥 标记，FIFA 后续更新球队、比分和淘汰赛信息时会自动同步。</p>
        <div class="actions" aria-label="订阅操作">
          <a class="button primary" href="{escaped_webcal_url}">📲 一键订阅到 iPhone 日历</a>
          <a class="button secondary" href="worldcup_2026.ics">⬇️ 下载 ICS 文件</a>
        </div>
        <div class="signal-row" aria-label="日历特性">
          <span class="signal">⏰ 赛前 1 天 / 2 小时 / 15 分钟提醒</span>
          <span class="signal">🌏 Asia/Shanghai 北京时间</span>
          <span class="signal">🔄 公开订阅源自动刷新</span>
        </div>
      </div>

      <aside class="subscribe-panel" aria-label="扫码订阅">
        <div class="panel-content">
          <div class="status">
            <span class="live"><span class="live-dot"></span>订阅源已就绪</span>
            <span class="cup" aria-hidden="true">🏆</span>
          </div>
          <div class="qr-card">
            <div>
              <img src="subscribe-qr.svg" alt="世界杯日历订阅二维码">
              <p class="qr-caption">用 iPhone 相机扫码，也可以直接点左侧按钮</p>
            </div>
          </div>
          <div class="url-box">
            <span class="url-label">订阅地址</span>
            <code>{escaped_webcal_url}</code>
            <button class="copy-button" type="button" data-copy="{escaped_webcal_url}">复制订阅链接 ✨</button>
          </div>
        </div>
      </aside>
    </section>

    <section class="section-grid" aria-label="使用说明">
      <article class="info-card">
        <strong>📱 iPhone 怎么添加</strong>
        <ol class="steps">
          <li><span class="step-num">1</span><span>点“一键订阅”或扫码。</span></li>
          <li><span class="step-num">2</span><span>系统弹窗里选择“订阅”。</span></li>
          <li><span class="step-num">3</span><span>在日历 App 里查看完整赛程。</span></li>
        </ol>
      </article>
      <article class="info-card">
        <strong>🔥 热门比赛标记</strong>
        <p>重点球队和焦点对阵会在标题前显示 🔥，并写入 Hot Match 分类，方便你一眼找到值得熬夜的场次。</p>
      </article>
      <article class="info-card">
        <strong>🔄 自动更新机制</strong>
        <p>订阅源由 GitHub Actions 定时重新生成。Apple Calendar 的实际刷新频率由 iOS 控制，通常不需要重复添加。</p>
      </article>
    </section>

    <footer class="footer">
      数据来自 FIFA 官方赛程接口。页面地址：<a href="{escaped_page_url}">{escaped_page_url}</a><br>
      如果按钮没有唤起订阅，请复制订阅地址，在 iOS 设置或日历 App 中手动添加“订阅日历”。
    </footer>
  </main>
  <div class="toast" role="status" aria-live="polite">订阅链接已复制 ✅</div>
  <script>
    const copyButton = document.querySelector("[data-copy]");
    const toast = document.querySelector(".toast");
    copyButton?.addEventListener("click", async () => {{
      const value = copyButton.getAttribute("data-copy");
      try {{
        await navigator.clipboard.writeText(value);
        toast.classList.add("show");
        window.setTimeout(() => toast.classList.remove("show"), 1800);
      }} catch (error) {{
        window.prompt("复制这个订阅链接：", value);
      }}
    }});
  </script>
</body>
</html>
"""


def publish_subscription_files(
    ics_path: Path,
    publish_dir: Path,
    public_base_url: str = DEFAULT_PUBLIC_BASE_URL,
) -> None:
    publish_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ics_path, publish_dir / "worldcup_2026.ics")
    _, webcal_url, _ = subscription_urls(public_base_url)
    write_subscription_qr(publish_dir / "subscribe-qr.svg", webcal_url)
    (publish_dir / "index.html").write_text(
        landing_page_html(public_base_url),
        encoding="utf-8",
    )
