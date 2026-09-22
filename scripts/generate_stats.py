"""Genera las tarjetas SVG de actividad y lenguajes para el README del perfil.

Uso: GITHUB_TOKEN=... python scripts/generate_stats.py [usuario]
Solo usa la librería estándar para que el workflow no necesite dependencias.
"""

import json
import os
import sys
import urllib.request
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path

USER = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GH_USER", "jijaraba")
TOKEN = os.environ["GITHUB_TOKEN"]
OUT = Path(__file__).resolve().parent.parent / "assets" / "generated"

BG = "#0d1117"
BORDER = "#30363d"
TEXT = "#e6edf3"
MUTED = "#8b949e"
ACCENT_A = "#8b5cf6"
ACCENT_B = "#22d3ee"
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    contributionsCollection {
      totalCommitContributions
      totalPullRequestContributions
      totalIssueContributions
      totalPullRequestReviewContributions
      restrictedContributionsCount
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false, first: 100) {
      totalCount
      nodes {
        name
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def fetch():
    body = json.dumps({"query": QUERY, "variables": {"login": USER}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise SystemExit(f"GraphQL error: {data['errors']}")
    return data["data"]["user"]


def streaks(days):
    """Racha actual (tolera que hoy aún no tenga contribuciones) y racha más larga."""
    longest = run = 0
    for d in days:
        run = run + 1 if d["contributionCount"] > 0 else 0
        longest = max(longest, run)
    current = 0
    today = date.today().isoformat()
    for d in reversed(days):
        if d["contributionCount"] > 0:
            current += 1
        elif d["date"] == today and current == 0:
            continue
        else:
            break
    return current, longest


def card(width, height, title, inner):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">
  <defs>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{ACCENT_A}"/><stop offset="1" stop-color="{ACCENT_B}"/>
    </linearGradient>
    <style>
      text {{ font-family: {FONT}; }}
      .title {{ font-size: 16px; font-weight: 700; fill: {TEXT}; }}
      .label {{ font-size: 12px; fill: {MUTED}; }}
      .value {{ font-size: 24px; font-weight: 700; fill: {TEXT}; }}
      .small {{ font-size: 12px; fill: {TEXT}; }}
      .fade {{ animation: fade .6s ease both; }}
      @keyframes fade {{ from {{ opacity: .2; }} to {{ opacity: 1; }} }}
      @keyframes grow {{ from {{ transform: scaleY(0); }} to {{ transform: scaleY(1); }} }}
      .bar {{ transform-box: fill-box; transform-origin: bottom; animation: grow .8s ease-out both; }}
    </style>
  </defs>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" fill="{BG}" stroke="{BORDER}"/>
  <rect x="0.5" y="0.5" width="{width - 1}" height="3" rx="1.5" fill="url(#accent)"/>
  <text x="24" y="36" class="title">{escape(title)}</text>
{inner}
</svg>
"""


def activity_svg(user):
    cc = user["contributionsCollection"]
    days = [d for w in cc["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    current, longest = streaks(days)
    stats = [
        ("Contribuciones (12 meses)", cc["contributionCalendar"]["totalContributions"]),
        ("Racha actual", f"{current} d"),
        ("Racha más larga", f"{longest} d"),
        ("Repos públicos", user["repositories"]["totalCount"]),
    ]
    width, height = 860, 250
    parts = []
    col = (width - 48) / len(stats)
    for i, (label, value) in enumerate(stats):
        x = 24 + i * col
        parts.append(
            f'  <g class="fade" style="animation-delay:{i * 0.12:.2f}s">'
            f'<text x="{x:.0f}" y="84" class="value">{escape(str(value))}</text>'
            f'<text x="{x:.0f}" y="104" class="label">{escape(label)}</text></g>'
        )

    # Barras semanales de las últimas 52 semanas.
    weeks = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in cc["contributionCalendar"]["weeks"]][-52:]
    peak = max(weeks) or 1
    chart_top, chart_bottom = 130, 216
    slot = (width - 48) / len(weeks)
    for i, total in enumerate(weeks):
        h = max(2, (chart_bottom - chart_top) * total / peak)
        x = 24 + i * slot
        parts.append(
            f'  <rect class="bar" style="animation-delay:{i * 0.012:.3f}s" x="{x + 1.5:.1f}" y="{chart_bottom - h:.1f}" '
            f'width="{slot - 3:.1f}" height="{h:.1f}" rx="2" fill="url(#accent)" opacity="{0.35 + 0.65 * total / peak:.2f}"/>'
        )
    parts.append(f'  <text x="24" y="236" class="label">Contribuciones por semana · últimos 12 meses</text>')
    updated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    parts.append(f'  <text x="{width - 24}" y="236" class="label" text-anchor="end">Actualizado {updated}</text>')
    return card(width, height, "Actividad en GitHub", "\n".join(parts))


def languages_svg(user, top=6):
    totals, colors = {}, {}
    for repo in user["repositories"]["nodes"]:
        if repo["name"].lower() == USER.lower():  # el repo del perfil no cuenta
            continue
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            totals[name] = totals.get(name, 0) + edge["size"]
            colors[name] = edge["node"]["color"] or MUTED
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:top]
    grand = sum(v for _, v in ranked) or 1

    width, height = 860, 150
    parts = ['  <clipPath id="track"><rect x="24" y="56" width="812" height="12" rx="6"/></clipPath>', '  <g clip-path="url(#track)">']
    x = 24.0
    for name, size in ranked:
        w = 812 * size / grand
        parts.append(f'    <rect x="{x:.1f}" y="56" width="{w:.1f}" height="12" fill="{colors[name]}"/>')
        x += w
    parts.append("  </g>")
    col = 812 / 3
    for i, (name, size) in enumerate(ranked):
        cx = 24 + (i % 3) * col
        cy = 98 + (i // 3) * 26
        parts.append(
            f'  <g class="fade" style="animation-delay:{i * 0.1:.1f}s"><circle cx="{cx + 6:.0f}" cy="{cy - 4}" r="6" fill="{colors[name]}"/>'
            f'<text x="{cx + 20:.0f}" y="{cy}" class="small">{escape(name)}</text>'
            f'<text x="{cx + 20 + 7.5 * len(name) + 8:.0f}" y="{cy}" class="label">{100 * size / grand:.1f}%</text></g>'
        )
    return card(width, height, "Lenguajes más usados en repos públicos", "\n".join(parts))


def main():
    user = fetch()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "activity.svg").write_text(activity_svg(user), encoding="utf-8")
    (OUT / "languages.svg").write_text(languages_svg(user), encoding="utf-8")
    print(f"SVGs escritos en {OUT}")


if __name__ == "__main__":
    main()
