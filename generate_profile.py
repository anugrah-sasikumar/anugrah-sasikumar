#!/usr/bin/env python3
"""
Premium animated GitHub profile README generator
=================================================

Generates three self-contained SVGs (pure SMIL, zero external CSS/JS):

  1. github-contribution-animation.svg  - 53x7 contribution calendar, diagonal slant reveal + glints
  2. terminal-card.svg                  - macOS terminal, ASCII avatar row reveal + `$ whoami` typewriter
  3. info-card.svg                      - neofetch-style info card, staggered slide-up lines (0.06s)

...and injects them into README.md (terminal + info side by side in a <table>,
contribution graph centered below).

Usage
-----
    pip install pillow
    python generate_profile.py --username YOUR_GITHUB_USERNAME

Optional:
    --token  GITHUB_TOKEN     real contribution data via GraphQL (or set env GITHUB_TOKEN)
    --out-dir .               where SVGs are written
    --readme README.md        README to update (created if missing)
    --avatar ./me.png         use a local image instead of downloading the avatar
    --no-readme               skip README injection

Edit the PROFILE dict below to customise the neofetch card.
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import math
import os
import random
import re
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

try:
    from PIL import Image, ImageDraw, ImageEnhance, ImageOps
except ImportError:  # pragma: no cover
    sys.exit("Pillow is required:  pip install pillow")

# --------------------------------------------------------------------------- #
#  CONFIG - edit me
# --------------------------------------------------------------------------- #
PROFILE = {
    "username": "anugrah",
    "name": "Anugrah S",
    "host": "github",

    "about": [
        ("Name", "Anugrah S"),
        ("Role", "System Engineer"),
        ("Focus", "System Integration & Automation"),
        ("Status", "Building & Shipping"),
    ],

    "stack": [
        ("Languages", "Python, JavaScript, TypeScript"),
        ("Frontend", "React, Next.js"),
        ("Backend", "Django, FastAPI, Node.js"),
        ("Database", "PostgreSQL, Redis"),
        ("DevOps", "Linux, Docker, Git, GitHub Actions"),
        ("Systems", "Networking, APIs, WebSockets, MQTT"),
        ("Cloud", "AWS"),
    ],

    "highlights": [
        "Full-Stack & System Integration",
        "API & Backend Development",
        "Automation & DevOps",
        "Real-Time System Integration",
    ],
}

# Palette ------------------------------------------------------------------- #
BG = "#0d1117"
CYAN = "#39d0d8"
GREEN = "#3fb950"
NEON = "#4dff9a"
ORANGE = "#ff9e3d"
PURPLE = "#a78bfa"
BLUE = "#58a6ff"
WHITE = "#e6edf3"
GRAY = "#8b949e"
RED = "#ff5f56"
YELLOW = "#ffbd2e"

FONT = ("'SF Mono','SFMono-Regular',ui-monospace,Menlo,Consolas,"
        "'Liberation Mono','DejaVu Sans Mono',monospace")

CYCLE = 14.0   # seconds - terminal + info card loop length (kept equal so they stay in sync)
MARGIN = 14    # outer margin around the cards (room for glows)
TITLEBAR = 38  # height of the macOS title bar


# --------------------------------------------------------------------------- #
#  Small helpers
# --------------------------------------------------------------------------- #
def n(x: float) -> str:
    """Compact number formatting for SVG attributes."""
    s = f"{x:.4f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def kt(times: list[float], total: float) -> str:
    """keyTimes string from absolute times (seconds)."""
    return ";".join(n(t / total) for t in times)


def http_get(url: str, headers: dict | None = None, data: bytes | None = None, timeout: int = 20) -> bytes:
    req = urllib.request.Request(
        url, data=data, headers={"User-Agent": "profile-readme-generator", **(headers or {})}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def common_defs() -> str:
    """Gradients / filters shared by every SVG."""
    return f"""
    <linearGradient id="sheen" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#fff" stop-opacity="0.07"/>
      <stop offset="0.35" stop-color="#fff" stop-opacity="0.015"/>
      <stop offset="1" stop-color="#fff" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="edge" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{CYAN}" stop-opacity="0.65"/>
      <stop offset="0.5" stop-color="#fff" stop-opacity="0.10"/>
      <stop offset="1" stop-color="{PURPLE}" stop-opacity="0.60"/>
    </linearGradient>
    <filter id="blur40" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="40"/></filter>
    <filter id="glowSoft" x="-50%" y="-50%" width="200%" height="200%">
      <feGaussianBlur stdDeviation="2.2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>"""


def backdrop(W: float, H: float) -> str:
    """Deep dark background with drifting cinematic colour blooms."""
    return f"""
  <rect width="{n(W)}" height="{n(H)}" rx="18" fill="{BG}"/>
  <g filter="url(#blur40)" opacity="0.5">
    <ellipse cx="{n(W*0.12)}" cy="{n(H*0.1)}" rx="{n(W*0.22)}" ry="{n(H*0.18)}" fill="{CYAN}" opacity="0.55">
      <animateTransform attributeName="transform" type="translate" values="0 0;26 14;0 0" dur="11s" repeatCount="indefinite"/>
    </ellipse>
    <ellipse cx="{n(W*0.92)}" cy="{n(H*0.35)}" rx="{n(W*0.2)}" ry="{n(H*0.2)}" fill="{PURPLE}" opacity="0.5">
      <animateTransform attributeName="transform" type="translate" values="0 0;-24 18;0 0" dur="13s" repeatCount="indefinite"/>
    </ellipse>
    <ellipse cx="{n(W*0.55)}" cy="{n(H*0.98)}" rx="{n(W*0.25)}" ry="{n(H*0.16)}" fill="{GREEN}" opacity="0.4">
      <animateTransform attributeName="transform" type="translate" values="0 0;18 -12;0 0" dur="15s" repeatCount="indefinite"/>
    </ellipse>
  </g>"""


def window_chrome(W: float, H: float, title: str) -> str:
    """Glassmorphism macOS window (title bar, traffic lights, gradient edge)."""
    return f"""
  <rect width="{n(W)}" height="{n(H)}" rx="14" fill="#10151d" fill-opacity="0.80"/>
  <rect width="{n(W)}" height="{n(H)}" rx="14" fill="url(#sheen)"/>
  <path d="M0 {TITLEBAR}V14a14 14 0 0 1 14-14H{n(W-14)}a14 14 0 0 1 14 14V{TITLEBAR}Z" fill="#fff" fill-opacity="0.045"/>
  <line x1="0" y1="{TITLEBAR}" x2="{n(W)}" y2="{TITLEBAR}" stroke="#fff" stroke-opacity="0.08"/>
  <circle cx="22" cy="19" r="5.5" fill="{RED}"/>
  <circle cx="42" cy="19" r="5.5" fill="{YELLOW}"/>
  <circle cx="62" cy="19" r="5.5" fill="#27c93f"/>
  <text x="{n(W/2)}" y="23" text-anchor="middle" font-family="{FONT}" font-size="11" fill="{GRAY}">{escape(title)}</text>
  <rect x="0.5" y="0.5" width="{n(W-1)}" height="{n(H-1)}" rx="13.5" fill="none" stroke="url(#edge)"/>"""


def svg_open(W: float, H: float, title: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{n(W)}" height="{n(H)}" '
            f'viewBox="0 0 {n(W)} {n(H)}" role="img" aria-label="{escape(title)}">\n'
            f'  <title>{escape(title)}</title>')


# --------------------------------------------------------------------------- #
#  1. CONTRIBUTION GRAPH
# --------------------------------------------------------------------------- #
LEVEL_COLORS = ["#151b23", "#0e4429", "#00753a", "#26c65a", NEON]
LEVEL_FROM_GQL = {"NONE": 0, "FIRST_QUARTER": 1, "SECOND_QUARTER": 2, "THIRD_QUARTER": 3, "FOURTH_QUARTER": 4}


def fetch_contribs_graphql(user: str, token: str):
    q = ("query($u:String!){user(login:$u){contributionsCollection{contributionCalendar{"
         "totalContributions weeks{contributionDays{date contributionCount contributionLevel}}}}}}")
    raw = http_get(
        "https://api.github.com/graphql",
        {"Authorization": f"bearer {token}", "Content-Type": "application/json"},
        json.dumps({"query": q, "variables": {"u": user}}).encode(),
    )
    cal = json.loads(raw)["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    days = {}
    for w in cal["weeks"]:
        for d in w["contributionDays"]:
            days[d["date"]] = (LEVEL_FROM_GQL[d["contributionLevel"]], d["contributionCount"])
    return days, cal["totalContributions"]


def fetch_contribs_html(user: str):
    """Token-less fallback: scrape the public contribution calendar fragment."""
    html = http_get(f"https://github.com/users/{user}/contributions").decode("utf-8", "replace")
    days = {}
    for tag in re.findall(r"<td[^>]*data-date=[^>]*>", html):
        d = re.search(r'data-date="([\d-]+)"', tag)
        l = re.search(r'data-level="(\d)"', tag)
        if d and l:
            days[d.group(1)] = (int(l.group(1)), 0)
    if not days:
        raise RuntimeError("no contribution cells found")
    m = re.search(r"([\d,]+)\s+contributions?\s+in\s+the\s+last\s+year", html)
    return days, (int(m.group(1).replace(",", "")) if m else None)


def synthetic_contribs(seed: str):
    rnd = random.Random(seed)
    today = dt.date.today()
    days, total = {}, 0
    for i in range(400):
        d = today - dt.timedelta(days=i)
        wave = 0.55 + 0.45 * math.sin(i / 23.0)
        p = (0.35 if d.weekday() >= 5 else 0.82) * wave
        cnt = int(rnd.random() ** 1.6 * 14 * wave) if rnd.random() < p else 0
        lvl = 0 if cnt == 0 else 1 if cnt < 3 else 2 if cnt < 6 else 3 if cnt < 10 else 4
        days[d.isoformat()] = (lvl, cnt)
        total += cnt
    return days, total


def get_contribs(user: str, token: str | None):
    if token:
        try:
            return fetch_contribs_graphql(user, token)
        except Exception as e:
            print(f"  ! GraphQL failed ({e}); trying public page")
    try:
        return fetch_contribs_html(user)
    except Exception as e:
        print(f"  ! could not fetch real contributions ({e}); using synthetic demo data")
        return synthetic_contribs(user)


def build_grid(days: dict):
    """53 columns x 7 rows (Sunday first). Cells in the future are None."""
    today = dt.date.today()
    last_sun = today - dt.timedelta(days=(today.weekday() + 1) % 7)
    start = last_sun - dt.timedelta(weeks=52)
    grid = []
    for c in range(53):
        col = []
        for r in range(7):
            d = start + dt.timedelta(weeks=c, days=r)
            col.append(None if d > today else (d, *days.get(d.isoformat(), (0, 0))))
        grid.append(col)
    return grid


def build_contrib_svg(grid, total, user: str) -> str:
    STEP, CELL = 15, 12
    GX, GY = 52, 84
    W = GX + 53 * STEP + 34
    H = GY + 7 * STEP + 78
    T = 12.0          # loop length
    D0, DT = 0.5, 0.032   # first reveal + delay per diagonal
    FADE = 0.9        # fade-out at end of loop

    normal, glow = [], []
    for c, col in enumerate(grid):
        for r, cell in enumerate(col):
            if cell is None:
                continue
            _, lvl, _cnt = cell
            x, y = GX + c * STEP, GY + r * STEP
            # diagonal index: bottom-left (c=0,r=6) -> 0 ... top-right -> 58
            s = D0 + (c + (6 - r)) * DT
            col_hex = LEVEL_COLORS[lvl]
            op_t = [0, s, s + 0.35, T - FADE, T]
            g_peak = 0.95 if lvl else 0.16
            gl_t = [0, s, s + 0.07, s + 0.75, T]
            fill_anim = ""
            if lvl:
                fill_anim = (f'<animate attributeName="fill" values="#eafff1;#eafff1;{col_hex};{col_hex}" '
                             f'keyTimes="{kt([0, s, s + 0.55, T], T)}" dur="{n(T)}s" repeatCount="indefinite"/>')
            el = (
                f'<g><rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="3" fill="{col_hex}" opacity="0">'
                f'<animate attributeName="opacity" values="0;0;1;1;0" keyTimes="{kt(op_t, T)}" dur="{n(T)}s" repeatCount="indefinite"/>'
                f'{fill_anim}</rect>'
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="3" fill="#d9ffe8" opacity="0">'
                f'<animate attributeName="opacity" values="0;0;{g_peak};0;0" keyTimes="{kt(gl_t, T)}" dur="{n(T)}s" repeatCount="indefinite"/>'
                f'</rect></g>'
            )
            (glow if lvl >= 3 else normal).append(el)

    # month + weekday labels
    labels, prev_m, last_c = [], None, -9
    for c in range(53):
        d = grid[c][0][0]
        if d.month != prev_m and c - last_c >= 3:
            labels.append(f'<text x="{GX + c * STEP}" y="{GY - 10}" font-size="10" fill="{GRAY}">{d.strftime("%b")}</text>')
            last_c = c
        prev_m = d.month
    for r, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        labels.append(f'<text x="{GX - 10}" y="{GY + r * STEP + 10}" text-anchor="end" font-size="10" fill="{GRAY}">{name}</text>')

    # sweeping light beam that rides the reveal front
    beam_travel = 60 * STEP
    beam_s, beam_e = D0 - 0.1, D0 + 59 * DT + 0.1
    bx0 = GX - 6 * STEP - 6
    beam = f"""
  <g opacity="0">
    <animate attributeName="opacity" values="0;0;0.9;0.9;0;0" keyTimes="{kt([0, beam_s, beam_s + 0.15, beam_e - 0.15, beam_e, T], T)}" dur="{n(T)}s" repeatCount="indefinite"/>
    <animateTransform attributeName="transform" type="translate" values="0 0;0 0;{beam_travel} 0;{beam_travel} 0" keyTimes="{kt([0, beam_s, beam_e, T], T)}" dur="{n(T)}s" repeatCount="indefinite"/>
    <polygon points="{bx0},{GY - 4} {bx0 + 14},{GY - 4} {bx0 + 6 * STEP + 14},{GY + 7 * STEP} {bx0 + 6 * STEP},{GY + 7 * STEP}" fill="url(#beam)" filter="url(#glowSoft)"/>
  </g>"""

    legend_y = GY + 7 * STEP + 26
    lx = W - 34 - (5 * 15) - 40
    legend = [f'<text x="{lx - 8}" y="{legend_y + 10}" text-anchor="end" font-size="10" fill="{GRAY}">Less</text>']
    for i, cc in enumerate(LEVEL_COLORS):
        legend.append(f'<rect x="{lx + i * 15}" y="{legend_y}" width="12" height="12" rx="3" fill="{cc}"/>')
    legend.append(f'<text x="{lx + 5 * 15 + 4}" y="{legend_y + 10}" font-size="10" fill="{GRAY}">More</text>')

    total_txt = f"{total:,} contributions in the last year" if total is not None else "contributions in the last year"

    return f"""{svg_open(W, H, f'{user} contribution graph')}
  <defs>{common_defs()}
    <linearGradient id="beam" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="0.5" stop-color="#bfffd8" stop-opacity="0.85"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="rule" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{CYAN}" stop-opacity="0.9"/><stop offset="0.5" stop-color="{NEON}" stop-opacity="0.5"/><stop offset="1" stop-color="{PURPLE}" stop-opacity="0"/>
    </linearGradient>
    <filter id="glow" filterUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">
      <feGaussianBlur stdDeviation="2.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
  </defs>
  {backdrop(W, H)}
  <rect x="12" y="12" width="{W - 24}" height="{H - 24}" rx="18" fill="#10151d" fill-opacity="0.78"/>
  <rect x="12" y="12" width="{W - 24}" height="{H - 24}" rx="18" fill="url(#sheen)"/>
  <rect x="12.5" y="12.5" width="{W - 25}" height="{H - 25}" rx="17.5" fill="none" stroke="url(#edge)"/>

  <g font-family="{FONT}">
    <circle cx="36" cy="38" r="4" fill="{NEON}" filter="url(#glowSoft)">
      <animate attributeName="r" values="3;5;3" dur="2s" repeatCount="indefinite"/>
      <animate attributeName="opacity" values="1;0.45;1" dur="2s" repeatCount="indefinite"/>
    </circle>
    <text x="50" y="42" font-size="13" font-weight="700" fill="{CYAN}" letter-spacing="2">CONTRIBUTION GRAPH</text>
    <text x="{W - 36}" y="42" text-anchor="end" font-size="12" fill="{NEON}">{escape(total_txt)}</text>
    <rect x="36" y="54" width="{W - 72}" height="1.5" rx="1" fill="url(#rule)"/>
    {"".join(labels)}
    {"".join(normal)}
    <g filter="url(#glow)">{"".join(glow)}</g>
    {beam}
    {"".join(legend)}
    <text x="36" y="{legend_y + 10}" font-size="10" fill="{GRAY}">// @{escape(user)} · commit history</text>
  </g>
</svg>
"""


# --------------------------------------------------------------------------- #
#  2. TERMINAL CARD (ASCII portrait)
# --------------------------------------------------------------------------- #
RAMP = " .`'^\",:;Il!i><~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
A_COLS, A_CW, A_LH, A_FS = 80, 4.0, 7.4, 6.67   # columns, char width, line height, font size


def _resample():
    return getattr(Image, "Resampling", Image).LANCZOS


def placeholder_avatar() -> Image.Image:
    """Used only if the avatar cannot be downloaded."""
    im = Image.new("L", (256, 256), 20)
    d = ImageDraw.Draw(im)
    for i in range(120, 0, -4):
        v = int(255 * (1 - i / 120) ** 0.8)
        d.ellipse((128 - i, 118 - i, 128 + i, 118 + i), fill=v)
    d.ellipse((60, 190, 196, 340), fill=150)
    return im


def load_avatar(user: str, local: str | None) -> Image.Image:
    if local:
        return Image.open(local)
    try:
        return Image.open(io.BytesIO(http_get(f"https://github.com/{user}.png?size=460")))
    except Exception as e:
        print(f"  ! could not download avatar ({e}); using placeholder")
        return placeholder_avatar()


def to_ascii(img: Image.Image, cols: int = A_COLS, invert: bool = False) -> list[str]:
    img = img.convert("RGBA")
    flat = Image.new("RGBA", img.size, (0, 0, 0, 255))
    flat.alpha_composite(img)
    g = ImageOps.autocontrast(flat.convert("L"), cutoff=2)
    g = ImageEnhance.Contrast(g).enhance(1.25)
    w, h = g.size
    rows = max(1, round(cols * (h / w) * (A_CW / A_LH)))
    g = g.resize((cols, rows), _resample())
    px = g.load()
    ramp = RAMP[::-1] if invert else RAMP
    L = len(ramp) - 1
    return ["".join(ramp[px[x, y] * L // 255] for x in range(cols)) for y in range(rows)]


def build_terminal_svg(rows: list[str], user: str, name: str):
    cols, nrows = len(rows[0]), len(rows)
    PADX = 22
    W = cols * A_CW + 2 * PADX
    ascii_top = TITLEBAR + 16
    foot_top = ascii_top + nrows * A_LH + 14
    H = foot_top + 76
    OW, OH = W + 2 * MARGIN, H + 2 * MARGIN
    T = CYCLE
    FADE = 1.0
    ROW0, ROW_DT, SWEEP = 0.5, 0.075, 0.28
    aw = cols * A_CW

    clips, texts, cursors = [], [], []
    for i, row in enumerate(rows):
        s = ROW0 + i * ROW_DT
        e = s + SWEEP
        top = ascii_top + i * A_LH
        clips.append(
            f'<clipPath id="r{i}"><rect x="{PADX}" y="{n(top)}" width="0" height="{A_LH}">'
            f'<animate attributeName="width" values="0;0;{n(aw)};{n(aw)}" keyTimes="{kt([0, s, e, T], T)}" dur="{n(T)}s" repeatCount="indefinite"/>'
            f'</rect></clipPath>'
        )
        if row.strip():
            texts.append(
                f'<text x="{PADX}" y="{n(top + A_LH - 1.6)}" textLength="{n(aw)}" lengthAdjust="spacing" '
                f'xml:space="preserve" clip-path="url(#r{i})">{escape(row)}</text>'
            )
        cursors.append(
            f'<rect x="{PADX}" y="{n(top)}" width="{A_CW * 1.2}" height="{A_LH}" fill="#fff" opacity="0">'
            f'<animate attributeName="x" values="{PADX};{PADX};{n(PADX + aw)};{PADX}" keyTimes="{kt([0, s, e, T], T)}" dur="{n(T)}s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values="0;0;1;1;0;0" keyTimes="{kt([0, s, s + 0.01, e, e + 0.01, T], T)}" dur="{n(T)}s" repeatCount="indefinite"/>'
            f'</rect>'
        )

    # ---- typewriter footer ($ whoami -> name) ----
    CW = 7.2   # 12px monospace
    l1, l2 = "$ whoami", "Anugrah S — System Engineer"
    y1, y2 = foot_top + 14, foot_top + 38    # line tops (cursor)
    ty0 = ROW0 + nrows * ROW_DT + SWEEP + 0.4
    STEP1, STEP2 = 0.09, 0.075
    t1 = [ty0 + i * STEP1 for i in range(len(l1))]
    t_move = t1[-1] + 0.45
    t2s = t_move + 0.35
    t2 = [t2s + i * STEP2 for i in range(len(l2))]

    def disc(attr, times, values):
        return (f'<animate attributeName="{attr}" calcMode="discrete" values="{";".join(str(v) for v in values)}" '
                f'keyTimes="{kt(times, T)}" dur="{n(T)}s" repeatCount="indefinite"/>')

    clip1 = f'<clipPath id="f1"><rect x="{PADX}" y="{y1 - 2}" width="0" height="17">{disc("width", [0] + t1, [0] + [n((i + 1) * CW) for i in range(len(l1))])}</rect></clipPath>'
    clip2 = f'<clipPath id="f2"><rect x="{PADX}" y="{y2 - 2}" width="0" height="17">{disc("width", [0] + t2, [0] + [n((i + 1) * CW) for i in range(len(l2))])}</rect></clipPath>'
    cur_times = [0] + t1 + [t_move] + t2
    cur_x = [PADX] + [n(PADX + (i + 1) * CW) for i in range(len(l1))] + [PADX] + [n(PADX + (i + 1) * CW) for i in range(len(l2))]
    cur_y = [y1] * (1 + len(l1)) + [y2] * (1 + len(l2))
    footer = f"""
    <line x1="{PADX}" y1="{n(foot_top - 4)}" x2="{n(W - PADX)}" y2="{n(foot_top - 4)}" stroke="#fff" stroke-opacity="0.08"/>
    <text x="{PADX}" y="{y1 + 11}" font-size="12" textLength="{n(len(l1) * CW)}" lengthAdjust="spacing" xml:space="preserve" clip-path="url(#f1)"><tspan fill="{GREEN}" font-weight="700">$</tspan><tspan fill="{WHITE}"> whoami</tspan></text>
    <text x="{PADX}" y="{y2 + 11}" font-size="12" font-weight="700" fill="{CYAN}" textLength="{n(len(l2) * CW)}" lengthAdjust="spacing" xml:space="preserve" clip-path="url(#f2)" filter="url(#glowSoft)">{escape(l2)}</text>
    <rect x="{PADX}" y="{y1}" width="{CW}" height="14" fill="{WHITE}">
      {disc("x", cur_times, cur_x)}{disc("y", cur_times, cur_y)}
      <animate attributeName="opacity" calcMode="discrete" values="1;0" keyTimes="0;0.5" dur="1s" repeatCount="indefinite"/>
    </rect>"""

    fade = (f'<animate attributeName="opacity" values="1;1;0;0" keyTimes="{kt([0, T - FADE, T - 0.2, T], T)}" '
            f'dur="{n(T)}s" repeatCount="indefinite"/>')

    svg = f"""{svg_open(OW, OH, f'{user} ASCII terminal portrait')}
  <defs>{common_defs()}
    <linearGradient id="ascii" gradientUnits="userSpaceOnUse" x1="0" y1="{n(ascii_top)}" x2="0" y2="{n(ascii_top + nrows * A_LH)}">
      <stop offset="0" stop-color="{CYAN}"/><stop offset="0.55" stop-color="{NEON}"/><stop offset="1" stop-color="{PURPLE}"/>
    </linearGradient>
    <pattern id="scan" width="4" height="3" patternUnits="userSpaceOnUse"><rect width="4" height="1" fill="#000" opacity="0.28"/></pattern>
    <filter id="glowCursor" filterUnits="userSpaceOnUse" x="0" y="{n(ascii_top - 6)}" width="{n(W)}" height="{n(nrows * A_LH + 12)}">
      <feGaussianBlur stdDeviation="1.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    {"".join(clips)}{clip1}{clip2}
  </defs>
  {backdrop(OW, OH)}
  <g transform="translate({MARGIN} {MARGIN})" font-family="{FONT}">
    {window_chrome(W, H, f"{user} — zsh — 80×24")}
    <g>
      {fade}
      <g font-size="{A_FS}" fill="url(#ascii)">{"".join(texts)}</g>
      <g filter="url(#glowCursor)">{"".join(cursors)}</g>
      <rect x="{PADX}" y="{n(ascii_top)}" width="{n(aw)}" height="{n(nrows * A_LH)}" fill="url(#scan)" opacity="0.35"/>
      {footer}
    </g>
  </g>
</svg>
"""
    return svg, OW, OH, H


# --------------------------------------------------------------------------- #
#  3. NEOFETCH INFO CARD
# --------------------------------------------------------------------------- #
def build_info_svg(user: str, host: str, H: float, prof: dict):
    PADX = 22
    W = 348
    OW, OH = W + 2 * MARGIN, H + 2 * MARGIN
    T = CYCLE
    FADE = 1.0
    START, DELAY = 0.6, 0.06
    CWI = 7.2
    keyx, valx = PADX + 2, PADX + 88
    vmax = int((W - valx - 14) / CWI)
    bmax = int((W - PADX - 16 - 14) / CWI)

    def clip(s, m):
        return s if len(s) <= m else s[: m - 1] + "…"

    items = [("header", 1.0), ("rule", 0.7), ("section:About", 1.0)]
    items += [(f"kv:{k}|{v}", 1.0) for k, v in prof["about"]]
    items += [("blank", 0.55), ("section:Stack", 1.0)]
    items += [(f"kv:{k}|{v}", 1.0) for k, v in prof["stack"]]
    items += [("blank", 0.55), ("section:Highlights", 1.0)]
    items += [(f"star:{h}", 1.0) for h in prof["highlights"]]
    items += [("blank", 0.55), ("palette", 1.0), ("prompt", 1.0)]

    avail = H - TITLEBAR - 18 - 20
    unit = min(19.0, avail / sum(w for _, w in items))
    y = TITLEBAR + 18

    def anim(i):
        s = START + i * DELAY
        op = (f'<animate attributeName="opacity" values="0;0;1;1;0" keyTimes="{kt([0, s, s + 0.3, T - FADE, T], T)}" '
              f'dur="{n(T)}s" repeatCount="indefinite"/>')
        tr = (f'<animateTransform attributeName="transform" type="translate" values="0 9;0 9;0 0;0 0" '
              f'keyTimes="{kt([0, s, s + 0.45, T], T)}" calcMode="spline" '
              f'keySplines="0 0 1 1;0.16 1 0.3 1;0 0 1 1" dur="{n(T)}s" repeatCount="indefinite"/>')
        return op + tr

    out = []
    for i, (spec, w) in enumerate(items):
        base = y + unit * 0.78
        kind, _, rest = spec.partition(":")
        body = ""
        if kind == "header":
            body = (f'<text x="{keyx}" y="{n(base)}" font-size="13" font-weight="700">'
                    f'<tspan fill="{CYAN}">{escape(user)}</tspan><tspan fill="{WHITE}">@</tspan><tspan fill="{NEON}">{escape(host)}</tspan></text>')
        elif kind == "rule":
            body = (f'<line x1="{keyx}" y1="{n(base - 4)}" x2="{W - PADX}" y2="{n(base - 4)}" stroke="url(#edge)" stroke-width="1.2"/>')
        elif kind == "section":
            body = (f'<text x="{keyx}" y="{n(base)}" font-size="12" font-weight="700" fill="{ORANGE}" letter-spacing="1" filter="url(#glowSoft)">'
                    f'◆ {escape(rest.upper())}</text>')
        elif kind == "kv":
            k, v = rest.split("|", 1)
            body = (f'<text x="{keyx + 12}" y="{n(base)}" font-size="12" fill="{BLUE}" font-weight="700">{escape(k)}</text>'
                    f'<text x="{valx}" y="{n(base)}" font-size="12" fill="{WHITE}" xml:space="preserve">{escape(clip(v, vmax))}</text>')
        elif kind == "star":
            body = (f'<text x="{keyx + 12}" y="{n(base)}" font-size="12" fill="{GREEN}">▸</text>'
                    f'<text x="{keyx + 28}" y="{n(base)}" font-size="12" fill="{WHITE}" xml:space="preserve">{escape(clip(rest, bmax))}</text>')
        elif kind == "palette":
            cols = [ORANGE, BLUE, GREEN, CYAN, PURPLE, WHITE, RED, YELLOW]
            body = "".join(f'<rect x="{keyx + 12 + j * 20}" y="{n(base - 10)}" width="16" height="11" rx="2.5" fill="{c}"/>' for j, c in enumerate(cols))
        elif kind == "prompt":
            body = (f'<text x="{keyx}" y="{n(base)}" font-size="12" font-weight="700" fill="{GREEN}">$</text>'
                    f'<rect x="{keyx + 14}" y="{n(base - 11)}" width="7.2" height="14" fill="{WHITE}">'
                    f'<animate attributeName="opacity" calcMode="discrete" values="1;0" keyTimes="0;0.5" dur="1s" repeatCount="indefinite"/></rect>')
        if body:
            out.append(f"<g opacity=\"0\">{anim(i)}{body}</g>")
        y += unit * w

    svg = f"""{svg_open(OW, OH, f'{user} neofetch info card')}
  <defs>{common_defs()}</defs>
  {backdrop(OW, OH)}
  <g transform="translate({MARGIN} {MARGIN})" font-family="{FONT}">
    {window_chrome(W, H, f"neofetch — {user}@{host}")}
    {"".join(out)}
  </g>
</svg>
"""
    return svg, OW, OH


# --------------------------------------------------------------------------- #
#  README injection
# --------------------------------------------------------------------------- #
MARK_START, MARK_END = "<!-- PROFILE-CARDS:START -->", "<!-- PROFILE-CARDS:END -->"


def inject_readme(readme: Path, out_dir: Path, files: dict, sizes: dict, user: str) -> None:
    def rel(name):
        return Path(os.path.relpath(out_dir / name, readme.parent.resolve())).as_posix()

    t, i, c = files["terminal"], files["info"], files["contrib"]
    block = f"""{MARK_START}
<table align="center">
  <tr>
    <td valign="top"><img src="{rel(t)}" width="{sizes['terminal'][0]}" alt="{user} terminal portrait"/></td>
    <td valign="top"><img src="{rel(i)}" width="{sizes['info'][0]}" alt="{user} info card"/></td>
  </tr>
</table>

<p align="center">
  <img src="{rel(c)}" width="100%" alt="{user} contribution graph"/>
</p>
{MARK_END}"""
    if readme.exists():
        txt = readme.read_text(encoding="utf-8")
        if MARK_START in txt and MARK_END in txt:
            txt = re.sub(re.escape(MARK_START) + r".*?" + re.escape(MARK_END), lambda m: block, txt, flags=re.S)
        else:
            txt = block + "\n\n" + txt
    else:
        txt = block + "\n"
    readme.write_text(txt, encoding="utf-8")


# --------------------------------------------------------------------------- #
#  main
# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description="Generate animated GitHub profile SVGs + README")
    ap.add_argument("--username", default=PROFILE["username"])
    ap.add_argument("--name", default=None, help="display name for `$ whoami` (default: PROFILE name)")
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    ap.add_argument("--out-dir", default=".")
    ap.add_argument("--readme", default="README.md")
    ap.add_argument("--avatar", default=None, help="local image path instead of downloading")
    ap.add_argument("--invert", action="store_true", help="invert ASCII brightness")
    ap.add_argument("--no-readme", action="store_true")
    a = ap.parse_args()

    user = a.username
    name = a.name or (PROFILE["name"] if user == PROFILE["username"] else user)
    out = Path(a.out_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    prof = dict(PROFILE)

    print(f"[1/3] contribution graph for @{user}")
    days, total = get_contribs(user, a.token)
    f_contrib = "github-contribution-animation.svg"
    (out / f_contrib).write_text(build_contrib_svg(build_grid(days), total, user), encoding="utf-8")

    print("[2/3] ASCII terminal card")
    rows = to_ascii(load_avatar(user, a.avatar), invert=a.invert)
    t_svg, tw, th, inner_h = build_terminal_svg(rows, user, name)
    f_term = "terminal-card.svg"
    (out / f_term).write_text(t_svg, encoding="utf-8")

    print("[3/3] neofetch info card")
    i_svg, iw, ih = build_info_svg(user, prof["host"], inner_h, prof)
    f_info = "info-card.svg"
    (out / f_info).write_text(i_svg, encoding="utf-8")

    if not a.no_readme:
        readme = Path(a.readme).resolve()
        inject_readme(
            readme, out,
            {"terminal": f_term, "info": f_info, "contrib": f_contrib},
            {"terminal": (round(tw), round(th)), "info": (round(iw), round(ih))},
            user,
        )
        print(f"README updated: {readme}")
    for f in (f_contrib, f_term, f_info):
        print(f"  wrote {out / f}  ({(out / f).stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
