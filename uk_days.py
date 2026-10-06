import argparse
import html
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

API_URL = "https://www.daysoftheyear.com/api/v2/today/"
COUNTRY = "GB"
MAX_DAYS = 10
TZ = ZoneInfo("Europe/London")


def uk_now() -> datetime:
    return datetime.now(TZ)


def fetch_events(api_key: str) -> list:
    offset = int(uk_now().utcoffset().total_seconds() // 3600)
    query = urllib.parse.urlencode({"countries[]": COUNTRY, "timezone_offset": offset})
    req = urllib.request.Request(
        f"{API_URL}?{query}",
        headers={"X-Api-Key": api_key, "User-Agent": "uk-days-script/1.0"},
    )
    
    # The API occasionally returns an empty or non-JSON body
    # so retries a few times and show what came back if it keeps failing.
    attempts = 4
    for attempt in range(1, attempts + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read()
                detail = f"HTTP {resp.status}, {resp.headers.get('Content-Type')}, body {body[:200]!r}"
            try:
                return json.loads(body)["data"]
            except (ValueError, KeyError):
                problem = f"unexpected response: {detail}"
        except OSError as err:
            problem = f"request failed: {err}"
        print(f"API attempt {attempt}/{attempts}: {problem}", file=sys.stderr)
        if attempt < attempts:
            time.sleep(30 * attempt)
    sys.exit("Giving up: the Days Of The Year API did not return usable data.")


def fetch_image(page_url: str) -> str:
    """The API has no images, so take the og:image from the day's own page ("" if unavailable)."""
    try:
        req = urllib.request.Request(page_url, headers={"User-Agent": "uk-days-script/1.0"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            page = resp.read().decode("utf-8", "replace")
    except OSError:
        return ""
    m = re.search(r'<meta property="og:image" content="([^"]+)"', page)
    return html.unescape(m.group(1)) if m else ""


def add_images(days: list) -> None:
    with ThreadPoolExecutor(max_workers=5) as pool:
        for e, image in zip(days, pool.map(fetch_image, [e["url"] for e in days])):
            e["image"] = image


def clean(text: str) -> str:
    """The API returns &amp, non-breaking spaces,etc"""
    return html.unescape(text or "").replace(" ", " ").strip()


def is_uk(event: dict) -> bool:
    """Free tier ignores the countries filter, so filters here as well"""
    return COUNTRY in (event.get("countries") or [])


def applies_to_uk(event: dict) -> bool:
    """Tagged GB, tagged international, or not tied to any country"""
    countries = event.get("countries") or []
    return not countries or COUNTRY in countries or "INT" in countries


def today_days(events: list) -> list:
    """Up to MAX_DAYS of today's days: UK first, then international/untagged ones."""
    days = [e for e in events if e.get("type") == "day" and applies_to_uk(e)]
    days.sort(key=lambda e: (not is_uk(e), -(e.get("grade") or 0)))
    return days[:MAX_DAYS]


def render_card(e: dict) -> str:
    name = html.escape(clean(e["name"]))
    url = html.escape(e["url"], quote=True)
    excerpt = html.escape(clean(e.get("excerpt")).split("\n")[0])
    # no-referrer: the site blocks images requested with another site's referer
    image = (
        f'\n          <img src="{html.escape(e["image"], quote=True)}" alt="" loading="lazy" referrerpolicy="no-referrer">'
        if e.get("image") else ""
    )
    return f"""
      <li>
        <a class="day" href="{url}" target="_blank" rel="noopener">
          <div>
            <h2>{name}</h2>
            <p>{excerpt}</p>
          </div>{image}
        </a>
      </li>"""


def render_list(events: list) -> str:
    if not events:
        return ""
    cards = "".join(render_card(e) for e in events)
    return f"""
    <ol>{cards}
    </ol>"""


def build_page(events: list) -> str:
    days = today_days(events)
    add_images(days)

    today = uk_now()
    date_str = f"{today:%A} {today.day} {today:%B %Y}"

    # Favicon is a calendar page showing today's date
    favicon = urllib.parse.quote(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        '<rect x="2" y="3" width="28" height="27" rx="6" fill="#c8102e"/>'
        '<path d="M3.5 12h25v12a4.5 4.5 0 0 1-4.5 4.5H8A4.5 4.5 0 0 1 3.5 24z" fill="#fff"/>'
        '<circle cx="10.5" cy="7.5" r="1.5" fill="#fff"/><circle cx="21.5" cy="7.5" r="1.5" fill="#fff"/>'
        '<text x="16" y="25.5" text-anchor="middle" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif"'
        f' font-size="14" font-weight="700" fill="#16181d">{today.day}</text></svg>'
    )

    body = render_list(days) or '<p class="empty">No UK days found for today.</p>'

    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UK Days · {date_str}</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,{favicon}">
<script>
  const root = document.documentElement;
  root.dataset.view = "compact";
  try {{
    const theme = localStorage.getItem("theme");
    if (theme === "light" || theme === "dark") root.dataset.theme = theme;
    if (localStorage.getItem("view") === "large") root.dataset.view = "large";
  }} catch (e) {{}}
</script>
<style>
  :root {{
    color-scheme: light dark;
    --bg: #f6f5f2; --card: #ffffff; --ink: #16181d; --body: #4a4e57; --muted: #7a7f88;
    --rule: #e5e3de; --accent: #c8102e;
    --sun: none; --moon: block;
  }}

  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme]) {{
      --bg: #0e0f11; --card: #17191d; --ink: #ececee; --body: #a9adb5; --muted: #7d828b;
      --rule: #26292e; --accent: #ff6b7d;
      --sun: block; --moon: none;
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --bg: #0e0f11; --card: #17191d; --ink: #ececee; --body: #a9adb5; --muted: #7d828b;
    --rule: #26292e; --accent: #ff6b7d;
    --sun: block; --moon: none;
  }}
  :root[data-theme="light"] {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--bg); color: var(--ink);
    font: 15px/1.55 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
    -webkit-font-smoothing: antialiased;
  }}
  main {{ max-width: 680px; margin: 0 auto; padding: 72px 24px 56px; }}
  header {{ display: flex; justify-content: space-between; align-items: flex-end; gap: 16px; margin-bottom: 40px; }}
  .site {{ margin: 0 0 6px; font-size: 14px; font-weight: 600; color: var(--accent); }}
  h1 {{ margin: 0; font-size: 34px; line-height: 1.15; font-weight: 600; letter-spacing: -.022em; }}
  ol {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }}
  li {{
    background: var(--card); border: 1px solid var(--rule); border-radius: 10px;
    overflow: hidden; transition: border-color .15s;
  }}
  li:hover {{ border-color: var(--muted); }}
  .day {{
    display: flex; justify-content: space-between; align-items: flex-start; gap: 24px;
    padding: 16px 18px; color: inherit; text-decoration: none;
  }}
  .day:focus-visible {{ outline: 2px solid var(--accent); outline-offset: -2px; border-radius: 10px; }}
  .day h2 {{ margin: 0; font-size: 17px; line-height: 1.3; font-weight: 600; letter-spacing: -.01em; transition: color .15s; }}
  .day:hover h2 {{ color: var(--accent); }}
  .day p {{ margin: 4px 0 0; color: var(--body); }}
  .day img {{
    flex: none; width: 132px; aspect-ratio: 3 / 2; object-fit: cover;
    border-radius: 4px; background: var(--rule);
  }}
  .controls {{ display: flex; align-items: center; gap: 6px; }}
  .controls button {{
    display: grid; place-items: center; width: 32px; height: 32px; padding: 0; border: 0;
    border-radius: 8px; background: var(--rule); color: var(--muted); cursor: pointer;
    transition: color .15s;
  }}
  .controls button:hover {{ color: var(--ink); }}
  .controls button:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 1px; }}
  .controls svg {{
    width: 16px; height: 16px; fill: none; stroke: currentColor;
    stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round;
  }}
  .view .to-compact, [data-view="large"] .view .to-large {{ display: none; }}
  [data-view="large"] .view .to-compact {{ display: block; }}
  .theme .sun {{ display: var(--sun); }}
  .theme .moon {{ display: var(--moon); }}
  [data-view="large"] ol {{ gap: 20px; }}
  [data-view="large"] .day {{ flex-direction: column-reverse; gap: 0; padding: 0; }}
  [data-view="large"] .day > div {{ padding: 16px 20px 20px; }}
  [data-view="large"] .day img {{ width: 100%; aspect-ratio: 16 / 9; border-radius: 0; }}
  [data-view="large"] .day h2 {{ font-size: 20px; }}
  .empty {{ color: var(--muted); }}
  footer {{ margin-top: 64px; font-size: 13px; color: var(--muted); }}
  footer a {{ color: inherit; text-underline-offset: 2px; }}
  footer a:hover {{ color: var(--accent); }}
  @media (max-width: 520px) {{
    main {{ padding: 40px 20px; }}
    h1 {{ font-size: 28px; }}
    .day {{ gap: 16px; }}
    .day img {{ width: 84px; aspect-ratio: 1; }}
  }}
</style>
</head>
<body>
<main>
  <header>
    <div>
      <p class="site">UK Days</p>
      <h1>{date_str}</h1>
    </div>
    <div class="controls">
      <button type="button" class="view" aria-label="Switch between large and compact layout" title="Large / compact">
        <svg class="to-compact" viewBox="0 0 16 16" aria-hidden="true"><path d="M2.75 4h10.5M2.75 8h10.5M2.75 12h10.5"/></svg>
        <svg class="to-large" viewBox="0 0 16 16" aria-hidden="true"><rect x="2.75" y="2.75" width="10.5" height="7" rx="1.5"/><path d="M2.75 13.25h6.5"/></svg>
      </button>
      <button type="button" class="theme" aria-label="Switch between light and dark theme" title="Light / dark">
        <svg class="moon" viewBox="0 0 16 16" aria-hidden="true"><path d="M13.5 9.2A5.75 5.75 0 0 1 6.8 2.5a5.75 5.75 0 1 0 6.7 6.7z"/></svg>
        <svg class="sun" viewBox="0 0 16 16" aria-hidden="true"><circle cx="8" cy="8" r="2.75"/><path d="M8 1.5V3M8 13v1.5M1.5 8H3M13 8h1.5M3.4 3.4l1.06 1.06M11.54 11.54l1.06 1.06M3.4 12.6l1.06-1.06M11.54 4.46l1.06-1.06"/></svg>
      </button>
    </div>
  </header>
  {body}
  <footer>
    Data from <a href="https://www.daysoftheyear.com">Days Of The Year</a>, filtered to UK events
    by <a href="https://lucasw.uk">Lucas</a> · Last updated {today:%Y-%m-%d %H:%M}
  </footer>
</main>
<script>
  // Layout switch
  document.querySelector(".view").addEventListener("click", () => {{
    root.dataset.view = root.dataset.view === "large" ? "compact" : "large";
    try {{ localStorage.setItem("view", root.dataset.view); }} catch (e) {{}}
  }});

  // Theme switch
  document.querySelector(".theme").addEventListener("click", () => {{
    const dark = root.dataset.theme
      ? root.dataset.theme === "dark"
      : matchMedia("(prefers-color-scheme: dark)").matches;
    root.dataset.theme = dark ? "light" : "dark";
    try {{ localStorage.setItem("theme", root.dataset.theme); }} catch (e) {{}}
  }});
</script>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Build today's UK days page.")
    parser.add_argument("-o", "--output", default="uk-days.html", help="output HTML file")
    parser.add_argument("--from-file", help="use a saved API JSON response instead of calling the API")
    args = parser.parse_args()

    if args.from_file:
        with open(args.from_file, encoding="utf-8") as f:
            events = json.load(f)["data"]
    else:
        load_dotenv()
        api_key = os.environ.get("DOTY_API_KEY")
        if not api_key:
            sys.exit("Set DOTY_API_KEY (environment variable or .env file) to your Days Of The Year API key.")
        events = fetch_events(api_key)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(build_page(events))
    print(f"Wrote {args.output} ({len(today_days(events))} days today)")


if __name__ == "__main__":
    main()
