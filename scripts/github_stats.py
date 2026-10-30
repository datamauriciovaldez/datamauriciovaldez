"""Generate a small GitHub stats card (light + dark SVG) for the profile README.

Runs daily from .github/workflows/stats.yml so the README never depends on a
third-party image service. Standard library only.

Env vars:
  GH_USER        GitHub login (default: datamauriciovaldez)
  GITHUB_TOKEN   optional; enables the "commits in the last 12 months" metric
  EXCLUDE_REPOS  optional, comma-separated repo names left out of the language bar
"""
import json
import os
import urllib.request
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

USER = os.getenv("GH_USER", "datamauriciovaldez")
TOKEN = os.getenv("GITHUB_TOKEN", "")
EXCLUDE = {r.strip() for r in os.getenv("EXCLUDE_REPOS", "").split(",") if r.strip()}
OUT_DIR = Path(__file__).resolve().parent.parent / "assets"

# Fixed language -> slot mapping: colour follows the language, never its rank.
# Palettes validated with the dataviz validator (adjacent CVD/normal-vision pass).
SLOTS = ["Python", "SQL", "R", "JavaScript", "Shell"]
THEMES = {
    "light": dict(bg="#ffffff", border="#d0d7de", text="#1f2328", muted="#59636e",
                  accent="#0f766e", other="#8c959f",
                  series=["#0d9488", "#2a78d6", "#eb6834", "#6250d6", "#e87ba4"]),
    "dark": dict(bg="#0d1117", border="#30363d", text="#e6edf3", muted="#9198a1",
                 accent="#2dd4bf", other="#6e7681",
                 series=["#0f9f90", "#3987e5", "#d95926", "#9085e9", "#d55181"]),
}
# Linguist names folded into one of the slots above.
ALIASES = {"Jupyter Notebook": "Python", "PLpgSQL": "SQL", "TSQL": "SQL", "PLSQL": "SQL",
           "RMarkdown": "R", "TypeScript": "JavaScript"}


def api(url, body=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-stats"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(url, data, headers), timeout=30) as r:
        return json.load(r)


def collect():
    repos = [r for r in api(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner")
             if not r["fork"]]
    langs = {}
    for r in repos:
        if r["name"] in EXCLUDE or r["name"] == USER:
            continue
        for lang, size in api(r["languages_url"]).items():
            key = ALIASES.get(lang, lang)
            langs[key] = langs.get(key, 0) + size

    commits = None
    if TOKEN:
        q = {"query": "query($u:String!){user(login:$u){contributionsCollection{totalCommitContributions}}}",
             "variables": {"u": USER}}
        try:
            commits = api("https://api.github.com/graphql", q)["data"]["user"][
                "contributionsCollection"]["totalCommitContributions"]
        except Exception as e:  # metric is optional; never fail the card for it
            print(f"commit count unavailable: {e}")

    return {"repos": len(repos), "stars": sum(r["stargazers_count"] for r in repos),
            "commits": commits, "langs": langs}


def render(stats, t):
    total = sum(stats["langs"].values()) or 1
    parts = [(name, size) for name, size in stats["langs"].items() if name in SLOTS]
    parts.sort(key=lambda p: SLOTS.index(p[0]))
    other = total - sum(size for _, size in parts)
    rows = [(name, size / total, t["series"][SLOTS.index(name)]) for name, size in parts]
    if other > 0:
        rows.append(("Other", other / total, t["other"]))
    rows = [r for r in rows if r[1] >= 0.005]

    W, X = 480, 24
    # Lay out legend items first so the card grows a line instead of clipping.
    legend, x, y = [], X, 136
    for name, p, c in rows:
        label = f"{name} {p:.0%}"
        width = 13 + 6.6 * len(label) + 14
        if x + width > W - X and x > X:
            x, y = X, y + 20
        legend.append((x, y, label, c))
        x += width
    H = y + 32
    font = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"
    s = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
         f'role="img" aria-labelledby="t d">',
         f'<title id="t">GitHub stats for {escape(USER)}</title>',
         '<desc id="d">' + escape(
             f"{stats['repos']} public repositories, {stats['stars']} stars. Languages: "
             + ", ".join(f"{n} {p:.0%}" for n, p, _ in rows)) + '</desc>',
         f'<rect x="0.5" y="0.5" width="{W - 1}" height="{H - 1}" rx="8" fill="{t["bg"]}" stroke="{t["border"]}"/>',
         f'<g font-family="{font}">']

    metrics = [("Public repos", stats["repos"]), ("Stars", stats["stars"])]
    if stats["commits"] is not None:
        metrics.append(("Commits · last 12 mo", stats["commits"]))
    col = (W - 2 * X) / len(metrics)
    for i, (label, value) in enumerate(metrics):
        x = X + i * col
        s.append(f'<text x="{x}" y="46" font-size="22" font-weight="600" fill="{t["text"]}">{value}</text>')
        s.append(f'<text x="{x}" y="64" font-size="12" fill="{t["muted"]}">{escape(label)}</text>')

    s.append(f'<text x="{X}" y="96" font-size="12" font-weight="600" fill="{t["text"]}">Languages</text>')
    bar_w, gap, x = W - 2 * X, 2, X
    widths = [max(p * (bar_w - gap * (len(rows) - 1)), 4) for _, p, _ in rows]
    s.append(f'<clipPath id="bar"><rect x="{X}" y="104" width="{bar_w}" height="8" rx="4"/></clipPath><g clip-path="url(#bar)">')
    for w, (_, _, c) in zip(widths, rows):
        s.append(f'<rect x="{x:.1f}" y="104" width="{w:.1f}" height="8" fill="{c}"/>')
        x += w + gap
    s.append('</g>')

    for x, y, label, c in legend:
        s.append(f'<circle cx="{x + 4:.1f}" cy="{y - 4}" r="4" fill="{c}"/>')
        s.append(f'<text x="{x + 13:.1f}" y="{y}" font-size="12" fill="{t["text"]}">{escape(label)}</text>')

    s.append(f'<text x="{X}" y="{H - 12}" font-size="10" fill="{t["muted"]}">'
             f'Updated {date.today().isoformat()} · notebooks counted under their kernel language</text>')
    s.append('</g></svg>')
    return "\n".join(s) + "\n"


if __name__ == "__main__":
    stats = collect()
    OUT_DIR.mkdir(exist_ok=True)
    for mode, theme in THEMES.items():
        (OUT_DIR / f"github-stats-{mode}.svg").write_text(render(stats, theme))
    print(json.dumps(stats))
