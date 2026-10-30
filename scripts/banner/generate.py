"""Generate the animated `profile.sh --live` banner (dark + light SVG).

The left panel shows 1-bit dithered "data silhouettes" that cycle; the right
panel is a neofetch-style SYSTEM.INFO block. Pass --photo path/to/photo.jpg to
add a dithered portrait as the first scene.

    python scripts/banner/generate.py [--photo me.jpg]

Requires Pillow and numpy.
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageOps

ROOT = Path(__file__).resolve().parents[2]
W, H = 1180, 610
GRID_W, GRID_H, CELL = 150, 170, 2.4  # dither grid → 360×408 px
MAP_X, MAP_Y = 64, 130  # centred in the 390 px visual area
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

INFO = [
    ("Subject", "Mauricio Valdez Fusté"),
    ("Role", "BI & Data Analytics student"),
    ("Org", "La Salle · Universitat Ramon Llull"),
    ("Year", "3rd year · graduating Jun 2028"),
    ("Origin", "Barcelona, Spain"),
    ("Status", "Open to Data / BI internships"),
    ("Core.Lang", "Python · SQL · R"),
    ("Core.Analysis", "pandas · scikit-learn · ARIMA"),
    ("Core.BI", "Power BI · ggplot2 · seaborn"),
    ("Core.Data", "PostgreSQL · DuckDB · Databricks · n8n"),
    ("ToolChain", "Git · GitHub · OpenClaw"),
    ("Certs", "IBM Data Analyst · Google Data Analytics"),
    ("Speaks", "ES native · EN C2 · CA C1"),
    ("Grid.Mail", "mauriciovaldezfuste@gmail.com"),
    ("Grid.LinkedIn", "/in/mauricio-valdezf"),
    ("Grid.GitHub", "datamauriciovaldez"),
]
BOOT = ["[ ok ] mounting /data/bronze", "[ ok ] cleaning → /data/silver",
        "[ ok ] aggregating → /data/gold", "[ ok ] loading pandas, sklearn",
        "[ ok ] rendering dashboards", "> profile ready"]

THEMES = {
    "dark": dict(bg="#0A101F", win="#0D1628", panel="#101B30", line="#25344C", text="#E6EDF3",
                 muted="#8291A8", accent="#2DD4BF", dots="#2DD4BF", ok="#3FB950", shadow=".28"),
    "light": dict(bg="#EEF2F6", win="#FFFFFF", panel="#F6F8FA", line="#D0D7DE", text="#1F2328",
                  muted="#59636E", accent="#0F766E", dots="#0F766E", ok="#1A7F37", shadow=".10"),
}


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def vgrad(h, top, bottom):
    return np.linspace(top, bottom, h)[:, None]


def scene_bars():
    img = np.zeros((GRID_H, GRID_W))
    heights = [48, 78, 62, 108, 92, 132]
    for i, bh in enumerate(heights):
        x0 = 12 + i * 22
        y0 = 150 - bh
        img[y0:150, x0:x0 + 16] = vgrad(bh, 0.95, 0.35)
    pil = Image.fromarray((img * 255).astype("uint8"))
    d = ImageDraw.Draw(pil)
    pts = [(20 + i * 22, 150 - h - 12) for i, h in enumerate(heights)]
    d.line(pts, fill=255, width=3)
    for p in pts:
        d.ellipse([p[0] - 3, p[1] - 3, p[0] + 3, p[1] + 3], fill=255)
    d.line([(6, 152), (144, 152)], fill=170, width=2)
    return pil


def scene_medallion():
    pil = Image.new("L", (GRID_W, GRID_H), 0)
    d = ImageDraw.Draw(pil)
    for i, shade in enumerate([95, 165, 245]):  # bronze → silver → gold, darker to brighter
        top = 14 + i * 52
        d.rectangle([28, top + 9, 122, top + 38], fill=shade)
        d.ellipse([28, top + 28, 122, top + 48], fill=shade)
        d.ellipse([28, top, 122, top + 18], fill=min(255, shade + 35))
        if i < 2:
            d.polygon([(72, top + 47), (78, top + 47), (75, top + 54)], fill=200)
    return pil


def scene_scatter():
    rng = np.random.default_rng(7)
    img = np.zeros((GRID_H, GRID_W))
    yy, xx = np.mgrid[0:GRID_H, 0:GRID_W]
    for _ in range(70):
        cx = rng.uniform(15, 135)
        cy = 150 - (cx - 15) * 0.95 + rng.normal(0, 14)
        img += np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * rng.uniform(2, 4.5) ** 2))
    pil = Image.fromarray((np.clip(img, 0, 1) * 235).astype("uint8"))
    ImageDraw.Draw(pil).line([(10, 158), (142, 30)], fill=255, width=2)
    return pil


def scene_photo(path):
    """Portrait on a plain backdrop: drop the backdrop so only the person is lit."""
    from PIL import ImageFilter

    rgb = ImageOps.fit(ImageOps.exif_transpose(Image.open(path)).convert("RGB"), (GRID_W, GRID_H),
                       method=Image.LANCZOS, centering=(0.5, 0.3))
    px = np.asarray(rgb, dtype=float)
    border = np.concatenate([px[:4].reshape(-1, 3), px[:, :4].reshape(-1, 3), px[:, -4:].reshape(-1, 3)])
    dist = np.linalg.norm(px - np.median(border, axis=0), axis=2)
    keep = dist > 38
    keep[:, :5] = keep[:, -5:] = False  # scanned photo edges
    keep[:3] = False
    mask = Image.fromarray((keep * 255).astype("uint8")).filter(ImageFilter.MedianFilter(5))
    gray = ImageOps.autocontrast(ImageOps.grayscale(rgb), cutoff=1)
    gray = Image.fromarray((np.asarray(gray, dtype=float) ** 0.85 / 255 ** 0.85 * 255).astype("uint8"))
    gray = Image.fromarray(np.maximum(np.asarray(gray), 1))  # 0 is reserved for "no person"
    return Image.composite(gray, Image.new("L", gray.size, 0), mask)


def dither_path(pil):
    """Floyd–Steinberg (serpentine via Pillow) → one short stroke per lit cell."""
    bits = np.array(pil.convert("1"), dtype=bool)
    ys, xs = np.nonzero(bits)
    segs = [f"M{MAP_X + x * CELL:.1f} {MAP_Y + y * CELL:.1f}h{CELL * .8:.1f}" for y, x in zip(ys, xs)]
    return "".join(segs), len(segs)


def render(theme, scenes):
    t = THEMES[theme]
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
           'role="img" aria-labelledby="title desc">',
           "<title id=\"title\">Mauricio's live data profile</title>",
           '<desc id="desc">Animated terminal profile: a boot sequence, then dithered data silhouettes '
           '(bar chart, bronze-silver-gold layers, regression) next to a system-info card with '
           'Mauricio Valdez Fusté\'s role, stack and contact.</desc>',
           f'<defs><filter id="shadow" x="-10%" y="-10%" width="120%" height="130%"><feDropShadow dx="0" dy="10" '
           f'stdDeviation="14" flood-color="#02050B" flood-opacity="{t["shadow"]}"/></filter>'
           f'<clipPath id="map"><rect x="49" y="126" width="390" height="432" rx="3"/></clipPath>'
           f'<linearGradient id="scan" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{t["accent"]}" stop-opacity="0"/>'
           f'<stop offset="1" stop-color="{t["accent"]}" stop-opacity=".35"/></linearGradient></defs>',
           f'<rect width="{W}" height="{H}" rx="18" fill="{t["bg"]}"/>',
           f'<rect x="13" y="13" width="1154" height="584" rx="13" fill="{t["win"]}" stroke="{t["line"]}" filter="url(#shadow)"/>',
           f'<path d="M13 62H1167" stroke="{t["line"]}"/>',
           '<circle cx="38" cy="38" r="6" fill="#FF5F57"/><circle cx="59" cy="38" r="6" fill="#FEBC2E"/>'
           '<circle cx="80" cy="38" r="6" fill="#28C840"/>',
           f'<g font-family="{MONO}">',
           f'<text x="590" y="43" text-anchor="middle" fill="{t["muted"]}" font-size="13" letter-spacing=".4">profile.sh --live</text>',
           # left panel frame
           f'<rect x="35" y="88" width="418" height="472" rx="6" fill="{t["panel"]}" stroke="{t["line"]}"/>',
           f'<path d="M35 124H453" stroke="{t["line"]}"/>',
           f'<text x="49" y="111" fill="{t["accent"]}" font-size="13" font-weight="700" letter-spacing="1.2">VISUAL.MAP</text>']

    # boot lines (0–3 s), then hidden
    out.append('<g>')
    for i, line in enumerate(BOOT):
        color = t["ok"] if line.startswith("[ ok ]") else t["accent"]
        out.append(f'<text x="55" y="{160 + i * 26}" font-size="13" fill="{color}" opacity="0">{esc(line)}'
                   f'<animate attributeName="opacity" begin="{0.15 + i * 0.4:.2f}s" dur=".2s" values="0;1" fill="freeze"/></text>')
    out.append('<animate attributeName="opacity" begin="3.05s" dur=".15s" values="1;0" fill="freeze"/></g>')

    # dithered scenes: cycle after boot
    n, period, start = len(scenes), 5.0 * len(scenes), 3.2
    total_pts = 0
    out.append('<g clip-path="url(#map)">')
    for i, (label, pil) in enumerate(scenes):
        if theme == "light" and label.startswith("portrait"):
            # dark dots on a light card: shade the person, keep the backdrop empty
            a = np.asarray(pil).astype(int)
            pil = Image.fromarray(np.where(a > 0, 256 - a, 0).astype("uint8"))
        d, cnt = dither_path(pil)
        total_pts += cnt
        # fade in over [a, a+f], hold, fade out over [b-f, b]
        a, b, f = i / n, (i + 1) / n, 0.6 / period
        key, val = [a, a + f, b - f, b], ["0", "1", "1", "0"]
        if a > 0:
            key, val = [0] + key, ["0"] + val
        if b < 1:
            key, val = key + [1], val + ["0"]
        out.append(f'<g opacity="0"><animate attributeName="opacity" begin="{start}s" dur="{period}s" repeatCount="indefinite" '
                   f'keyTimes="{";".join(f"{k:.4f}" for k in key)}" values="{";".join(val)}"/>'
                   f'<path d="{d}" fill="none" stroke="{t["dots"]}" stroke-width="{CELL * .8:.1f}" opacity=".92"/>'
                   f'<text x="438" y="551" text-anchor="end" font-size="11" fill="{t["accent"]}">{esc(label)}</text></g>')
    out.append(f'<rect x="49" y="{MAP_Y - 40}" width="390" height="40" fill="url(#scan)" opacity="0">'
               f'<animate attributeName="opacity" begin="{start}s" dur=".01s" values="0;1" fill="freeze"/>'
               f'<animate attributeName="y" begin="{start}s" dur="3.5s" values="{MAP_Y - 40};{MAP_Y + 410}" repeatCount="indefinite"/></rect>')
    out.append('</g>')
    out.append(f'<text x="438" y="111" text-anchor="end" fill="{t["muted"]}" font-size="11">{GRID_W}×{GRID_H} / 1-BIT</text>')
    X0, Y0 = 49, 128
    corners = (f"M{X0} {Y0}h12M{X0} {Y0}v12M{X0 + 390} {Y0}h-12M{X0 + 390} {Y0}v12"
               f"M{X0} {Y0 + 410}h12M{X0} {Y0 + 410}v-12M{X0 + 390} {Y0 + 410}h-12M{X0 + 390} {Y0 + 410}v-12")
    out.append(f'<path d="{corners}" fill="none" stroke="{t["accent"]}" opacity=".55"/>')
    out.append(f'<text x="49" y="551" fill="{t["muted"]}" font-size="11">PTS {total_pts // len(scenes)} · FLOYD–STEINBERG</text>')

    # right panel: SYSTEM.INFO
    out.append(f'<rect x="476" y="88" width="668" height="472" rx="6" fill="{t["panel"]}" stroke="{t["line"]}"/>')
    out.append(f'<path d="M476 124H1144" stroke="{t["line"]}"/>')
    out.append(f'<text x="490" y="111" fill="{t["accent"]}" font-size="13" font-weight="700" letter-spacing="1.2">SYSTEM.INFO</text>')
    out.append(f'<circle cx="915" cy="107" r="4" fill="{t["ok"]}"><animate attributeName="opacity" values="1;.25;1" dur="1.6s" repeatCount="indefinite"/></circle>')
    out.append(f'<text x="927" y="111" fill="{t["ok"]}" font-size="11" font-weight="700">LIVE</text>')
    out.append(f'<text x="1128" y="111" text-anchor="end" fill="{t["muted"]}" font-size="11">@datamauriciovaldez</text>')
    for i, (k, v) in enumerate(INFO):
        y = 153 + i * 23
        out.append(f'<g opacity="0"><animate attributeName="opacity" begin="{0.1 + i * 0.12:.2f}s" dur=".6s" values="0;1" fill="freeze"/>'
                   f'<text x="491" y="{y}" font-size="13" fill="{t["accent"]}">{esc(k)}</text>'
                   f'<path d="M{491 + 8.2 * len(k) + 10} {y - 4}H{1127 - 7.9 * len(v) - 10}" stroke="{t["line"]}" stroke-dasharray="2 4"/>'
                   f'<text x="1127" y="{y}" text-anchor="end" font-size="13" fill="{t["text"]}">{esc(v)}</text></g>')
    out.append(f'<path d="M476 524H1144" stroke="{t["line"]}"/>')
    out.append(f'<text x="491" y="548" font-size="12" font-weight="700" fill="{t["ok"]}">● PIPELINE STATUS: GOLD</text>')
    out.append(f'<text x="1128" y="548" text-anchor="end" font-size="12" fill="{t["muted"]}">UTC+1 · BCN NODE</text>')
    out.append('</g></svg>')
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--photo", help="optional portrait to dither as the first scene")
    args = ap.parse_args()
    scenes = [("bar_chart + trend", scene_bars()), ("bronze ▸ silver ▸ gold", scene_medallion()),
              ("regression.fit()", scene_scatter())]
    if args.photo:
        scenes.insert(0, ("portrait.dither()", scene_photo(args.photo)))
    for theme in THEMES:
        p = ROOT / "assets" / f"banner-{theme}.svg"
        p.write_text(render(theme, scenes))
        print(p.relative_to(ROOT), f"{p.stat().st_size // 1024} KB")
