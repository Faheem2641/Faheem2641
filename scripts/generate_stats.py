#!/usr/bin/env python3
"""Draw the profile README's stat graphics from the GitHub GraphQL API.

No third-party services and no dependencies — standard library only.

Outputs, all sharing one visual language with ascii.svg (the portrait):
  stats.svg   hero total + weekly sparkline
  streak.svg  current and longest streak
  langs.svg   top languages, by bytes and by repo count
  year.svg    the year as a character map, in the portrait's own ramp

Every file uses the portrait's grey ink, a monospace face, a transparent
background, and the same left-to-right clipPath reveal with a cursor riding
the edge. Motion is SMIL because GitHub strips <script> from READMEs.

Env:
  GITHUB_TOKEN  required
  GH_LOGIN      user to summarise (default: Faheem2641)
  OUT_DIR       where to write (default: repository root)
"""
import base64
import functools
import json
import os
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

API = "https://api.github.com/graphql"

# Two things are pinned for determinism, both learned the hard way:
#  * the contribution window, to whole UTC days — otherwise "the past year" is
#    measured from request time and days drift between week buckets, moving the
#    sparkline a fraction of a pixel and committing noise every night;
#  * privacy: PUBLIC on repositories — otherwise a personal token sees private
#    repos and a workflow token doesn't, so language totals disagree.
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount date weekday } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false,
                 privacy: PUBLIC) {
      nodes {
        languages(first: 12, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""

# The portrait's ink is the data ink, so every graphic reads as one material.
LIGHT = dict(data="#6e7681", emph="#424a53", dim="#8c959f",
             rule="#d8dee4", surface="#ffffff")
DARK = dict(data="#58a6ff", emph="#ffffff", dim="#8b949e",
            rule="#30363d", surface="#0d1117")
# JBMono is the inlined subset below; the rest is a fallback for the unlikely
# case a renderer ignores the embedded face.
MONO = ("JBMono,ui-monospace,SFMono-Regular,Menlo,Consolas,"
        "&apos;Liberation Mono&apos;,monospace")
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


@functools.lru_cache(maxsize=None)
def face(filename, weight):
    """One @font-face rule with the subset inlined as a data URI.

    An external font URL cannot work here: these SVGs are loaded through <img>,
    and browsers refuse to fetch subresources for an image document. Inlining is
    also what pins the advance width — the portrait's grid assumes 0.600 em, and
    a viewer whose default monospace is narrower would otherwise see it squeezed.
    """
    with open(os.path.join(FONT_DIR, filename), "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return (f"@font-face{{font-family:JBMono;font-style:normal;"
            f"font-weight:{weight};font-display:block;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")


def font_text():
    """Basic latin, both weights — for the data graphics."""
    return face("jbmono-400.woff2", 400) + face("jbmono-600.woff2", 600)


def font_head():
    """Only the letters the section headings use."""
    return face("jbmono-head.woff2", 600)

WIDTH = 620            # every graphic shares one column width
LEFT = 34              # shared left inset, so stacked blocks line up
                       # (year.svg needs it for the weekday gutter)
REVEAL = 1.30          # seconds; matches the portrait's cadence
RAMP = [" ", ":", "+", "#", "@"]      # steps of the portrait's own ramp
MON = ["jan", "feb", "mar", "apr", "may", "jun",
       "jul", "aug", "sep", "oct", "nov", "dec"]


# ---------------------------------------------------------------- data

def window():
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=364)
    return (f"{start.isoformat()}T00:00:00Z", f"{today.isoformat()}T23:59:59Z")


def fetch(login, token):
    since, until = window()
    body = json.dumps({"query": QUERY,
                       "variables": {"login": login,
                                     "from": since, "to": until}}).encode()
    req = urllib.request.Request(
        API, data=body,
        headers={"Authorization": f"bearer {token}",
                 "Content-Type": "application/json",
                 "User-Agent": f"{login}-profile-stats"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.load(r)
    if "errors" in payload:
        raise SystemExit(f"GraphQL errors: {payload['errors']}")
    user = (payload.get("data") or {}).get("user")
    if not user:
        raise SystemExit(f"no such user: {login}")
    return user


def pretty(iso):
    d = date.fromisoformat(iso)
    return f"{MON[d.month - 1]} {d.day}"


def streaks(days):
    """Current and longest runs of days with at least one contribution.

    A zero on the final day doesn't break the current streak — the day isn't
    over yet. Any earlier zero does.
    """
    best = dict(length=0, start=None, end=None)
    run, run_start = 0, None
    for d in days:
        if d["contributionCount"] > 0:
            run += 1
            run_start = run_start or d["date"]
            if run > best["length"]:
                best = dict(length=run, start=run_start, end=d["date"])
        else:
            run, run_start = 0, None

    cur = dict(length=0, start=None, end=None)
    tail = days[:-1] if days and days[-1]["contributionCount"] == 0 else days
    for d in reversed(tail):
        if d["contributionCount"] == 0:
            break
        cur["length"] += 1
        cur["start"] = d["date"]
        cur["end"] = cur["end"] or d["date"]
    return cur, best


def languages(repos):
    by_size, by_repo = {}, {}
    for node in repos:
        edges = (node.get("languages") or {}).get("edges") or []
        for e in edges:
            name = e["node"]["name"]
            by_size[name] = by_size.get(name, 0) + e["size"]
        if edges:                       # primary language of the repo
            top = edges[0]["node"]["name"]
            by_repo[top] = by_repo.get(top, 0) + 1

    def rank(d):
        # sort by value, then name, so equal values never reorder between runs
        return sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:5]

    return rank(by_size), rank(by_repo)


def summarise(user):
    cal = user["contributionsCollection"]["contributionCalendar"]
    weeks = [w["contributionDays"] for w in cal["weeks"]]
    days = [d for w in weeks for d in w]
    weekly = [sum(d["contributionCount"] for d in w) for w in weeks]
    cur, best = streaks(days)
    by_size, by_repo = languages(user["repositories"]["nodes"])
    return dict(
        total=cal["totalContributions"],
        active=sum(1 for d in days if d["contributionCount"] > 0),
        best_week=max(weekly) if weekly else 0,
        weekly=weekly, weeks=weeks,
        current=cur, longest=best,
        by_size=by_size, by_repo=by_repo)


# ---------------------------------------------------------------- drawing

def style(extra="", font=None):
    def block(t):
        return (f".d-f{{fill:{t['data']}}}.d-s{{stroke:{t['data']}}}"
                f".e-f{{fill:{t['emph']}}}.m-f{{fill:{t['dim']}}}"
                f".u-s{{stroke:{t['rule']}}}.r{{stroke:{t['surface']}}}")
    levels_dark = ".l0{fill:#161b22}.l1{fill:#0d386b}.l2{fill:#1f6feb}.l3{fill:#388bfd}.l4{fill:#58a6ff}"
    return (f"<style>{font or font_text()}"
            f"{block(DARK)}{levels_dark}.w{{fill:{DARK['data']};opacity:.16}}{extra}</style>")


def head(w, h, font=None):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" fill="none" font-family="{MONO}">'
            + style(font=font))


def fade(delay, dur=0.45):
    return (f'<animate attributeName="opacity" from="0" to="1" '
            f'begin="{delay:.2f}s" dur="{dur}s" fill="freeze"/>')


def wipe(cid, x, y, w, h, delay, dur=REVEAL):
    """clipPath reveal plus the cursor block that rides its edge."""
    clip = (f'<clipPath id="{cid}"><rect x="{x}" y="{y}" height="{h}" width="0">'
            f'<animate attributeName="width" from="0" to="{w}" '
            f'begin="{delay:.2f}s" dur="{dur}s" fill="freeze"/></rect></clipPath>')
    cursor = (f'<rect y="{y}" width="2" height="{h}" class="d-f" opacity="0">'
              f'<animate attributeName="x" from="{x}" to="{x + w}" '
              f'begin="{delay:.2f}s" dur="{dur}s" fill="freeze"/>'
              f'<set attributeName="opacity" to="0.55" begin="{delay:.2f}s"/>'
              f'<set attributeName="opacity" to="0" '
              f'begin="{delay + dur:.2f}s"/></rect>')
    return clip, cursor


def label(x, y, text, size=11, cls="m-f", anchor="start", extra=""):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return (f'<text x="{x}" y="{y}" class="{cls}" font-size="{size}"{a}'
            f'{extra}>{text}</text>')


def hbar(x, y, w, h, cls="d-f", r=3.0):
    """Horizontal bar: rounded data-end on the right, square at the baseline."""
    if w <= 0.6:
        return ""
    r = min(r, h / 2.0, w)
    return (f'<path d="M{x:.1f} {y:.1f}H{x + w - r:.1f}'
            f'Q{x + w:.1f} {y:.1f} {x + w:.1f} {y + r:.1f}'
            f'V{y + h - r:.1f}Q{x + w:.1f} {y + h:.1f} {x + w - r:.1f} {y + h:.1f}'
            f'H{x:.1f}Z" class="{cls}"/>')


def draw_stats(s):
    """Hero number, the two secondary counts, and the weekly sparkline."""
    H = 148
    weekly = s["weekly"] or [0]
    peak = max(weekly) or 1
    p = [head(WIDTH, H)]
    p.append(f'<g opacity="0">{fade(0.10)}'
             + label(0, 50, s["total"], 52, "e-f", extra=' font-weight="600"')
             + label(0, 72, "contributions in the last year", 12) + '</g>')
    for i, (val, lab) in enumerate([(s["active"], "active days"),
                                    (s["best_week"], "best week")]):
        p.append(f'<g opacity="0">{fade(0.30 + i * 0.12)}'
                 + label(WIDTH, 30 + i * 40, val, 19, "e-f", "end",
                         ' font-weight="600"')
                 + label(WIDTH, 47 + i * 40, lab, 11, "m-f", "end") + '</g>')

    base, top = H - 10, H - 58
    span = base - top
    step = WIDTH / max(len(weekly) - 1, 1)
    pts = [(i * step, base - (v / peak) * span) for i, v in enumerate(weekly)]
    clip, cursor = wipe("rs", 0, top - 6, WIDTH, span + 8, 0.50)
    p.append(clip)
    p.append('<g clip-path="url(#rs)">')
    p.append(f'<path d="M{pts[0][0]:.1f} {base:.1f}'
             + "".join(f'L{x:.1f} {y:.1f}' for x, y in pts)
             + f'L{pts[-1][0]:.1f} {base:.1f}Z" class="w"/>')
    p.append(f'<path d="M{pts[0][0]:.1f} {pts[0][1]:.1f}'
             + "".join(f'L{x:.1f} {y:.1f}' for x, y in pts[1:])
             + f'" class="d-s" stroke-width="2" stroke-linejoin="round" '
             f'stroke-linecap="round"/>')
    p.append("</g>")
    p.append(cursor)
    ex, ey = pts[-1]
    p.append(f'<circle cx="{ex - 2:.1f}" cy="{ey:.1f}" r="4.5" class="e-f r" '
             f'stroke-width="2" opacity="0">{fade(0.50 + REVEAL, 0.35)}</circle>')
    p.append("</svg>")
    return "".join(p)


def draw_streak(s):
    """Current and longest streak, split by a hairline."""
    H = 96
    cells = []
    for k, lab in (("current", "current streak"), ("longest", "longest streak")):
        r = s[k]
        span = (f"{pretty(r['start'])} &#8211; {pretty(r['end'])}"
                if r["length"] else "&#8212;")
        cells.append((r["length"], lab, span))

    p = [head(WIDTH, H)]
    mid = WIDTH / 2
    p.append(f'<line x1="{mid:.0f}" y1="16" x2="{mid:.0f}" y2="80" '
             f'class="u-s" stroke-width="1" opacity="0">{fade(0.20)}</line>')
    for i, (val, lab, span) in enumerate(cells):
        x = LEFT if i == 0 else mid + LEFT
        p.append(f'<g opacity="0">{fade(0.12 + i * 0.14)}'
                 + label(x, 44, f"{val}", 34, "e-f", extra=' font-weight="600"')
                 + label(x, 64, lab, 11)
                 + label(x, 80, span, 10) + '</g>')
    p.append("</svg>")
    return "".join(p)


def draw_langs(s):
    """Two small charts: share of bytes, and count of repos by main language."""
    rows = max(len(s["by_size"]), len(s["by_repo"]), 1)
    H = 26 + rows * 22 + 6
    colw = (WIDTH - LEFT - 30) / 2
    name_w, bar_max = 82, colw - 82 - 44

    p = [head(WIDTH, H)]
    groups = [(LEFT, "by bytes", s["by_size"], True),
              (LEFT + colw + 30, "by repos", s["by_repo"], False)]
    for gi, (gx, title, data, as_pct) in enumerate(groups):
        p.append(f'<g opacity="0">{fade(0.10 + gi * 0.10)}'
                 + label(gx, 12, title.upper(), 9, "m-f",
                         extra=' letter-spacing="1.3"') + '</g>')
        if not data:
            continue
        top = max(v for _, v in data) or 1
        total = sum(v for _, v in data) or 1
        cid = f"rl{gi}"
        clip, cursor = wipe(cid, gx + name_w, 20, bar_max, rows * 22,
                            0.34 + gi * 0.12, 0.95)
        p.append(clip)
        for ri, (name, val) in enumerate(data):
            y = 26 + ri * 22
            shown = (f"{val / total * 100:.0f}%" if as_pct else f"{val}")
            p.append(f'<g opacity="0">{fade(0.24 + gi * 0.10 + ri * 0.05)}'
                     + label(gx, y + 8, name.lower()[:11], 11, "e-f")
                     + label(gx + colw - 6, y + 8, shown, 11, "m-f", "end")
                     + '</g>')
            p.append(f'<g clip-path="url(#{cid})">'
                     + hbar(gx + name_w, y, bar_max * val / top, 7)
                     + '</g>')
        p.append(cursor)
    p.append("</svg>")
    return "".join(p)


def draw_heading(word):
    """A section heading in the mono face, with a hairline running right.

    GitHub strips <style> and style= from markdown, so a real markdown heading
    can only ever be GitHub's own sans. Rendering the label as an SVG is the
    only way to put the page's own typeface on it. The rule starts past the
    longest plausible advance (0.6em is the widest common monospace ratio), so
    a narrower font on the viewer's machine widens the gap slightly rather than
    colliding with the text.
    """
    FS = 16
    H = 26
    text_end = len(word) * FS * 0.6 + 18
    p = [head(WIDTH, H, font=font_head())]
    p.append(label(0, 18, word, FS, "e-f", extra=' font-weight="600"'))
    p.append(f'<line x1="{text_end:.0f}" y1="12.5" x2="{WIDTH}" y2="12.5" '
             f'class="u-s" stroke-width="1"/>')
    p.append("</svg>")
    return "".join(p)


def draw_year(s):
    """Seven rows by fifty-three weeks drawn as sleek, rounded GitHub-style tiles."""
    TILE_SZ = 8.5
    STEP = 10.5
    pad_l, pad_t = LEFT + 24, 44
    weeks = s["weeks"]
    H = int(pad_t + 7 * STEP + 28)

    def level(v):
        if v <= 0:
            return 0
        elif v <= 2:
            return 1
        elif v <= 5:
            return 2
        elif v <= 9:
            return 3
        return 4

    p = [head(WIDTH, H)]
    p.append(f'<g opacity="0">{fade(0.10)}'
             + label(LEFT, 16, "THE YEAR", 9, "m-f", extra=' letter-spacing="1.3"')
             + label(LEFT, 32, f"{s['active']} of "
                     f"{sum(len(w) for w in weeks)} days had a contribution", 11)
             + '</g>')

    # Legend
    p.append(f'<g opacity="0">{fade(1.30)}'
             + label(524, 32, "less", 9, "m-f", "end"))
    for lvl_i in range(5):
        rect_x = 532 + lvl_i * 10
        p.append(f'<rect x="{rect_x}" y="24" width="8" height="8" rx="1.5" class="l{lvl_i}"/>')
    p.append(label(588, 32, "more", 9, "m-f", "start") + '</g>')

    # Grid of tiles
    p.append(f'<g opacity="0">{fade(0.30)}')
    for wi, w in enumerate(weeks):
        wx = pad_l + wi * STEP
        for d in w:
            r = d.get("weekday", 0)
            v = d.get("contributionCount", 0)
            wy = pad_t + r * STEP
            p.append(f'<rect x="{wx:.1f}" y="{wy:.1f}" width="{TILE_SZ}" height="{TILE_SZ}" rx="2" class="l{level(v)}"/>')
    p.append('</g>')

    # Weekday labels
    for r, lab in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        p.append(label(pad_l - 6, pad_t + r * STEP + 7, lab, 9, "m-f", "end"))

    # Month labels
    last_m, last_x = None, -999.0
    base_y = pad_t + 7 * STEP + 14
    for i, w in enumerate(weeks):
        if not w:
            continue
        m = int(w[0]["date"][5:7])
        x = pad_l + i * STEP
        if m != last_m and i < len(weeks) - 1 and x - last_x >= 32:
            p.append(label(x, base_y, MON[m - 1], 9, "m-f"))
            last_x = x
        last_m = m

    p.append("</svg>")
    return "".join(p)


def smooth_path(pts):
    if not pts:
        return ""
    if len(pts) == 1:
        return f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"
    path = [f"M{pts[0][0]:.1f} {pts[0][1]:.1f}"]
    for i in range(len(pts) - 1):
        x0, y0 = pts[max(i - 1, 0)][:2]
        x1, y1 = pts[i][:2]
        x2, y2 = pts[i + 1][:2]
        x3, y3 = pts[min(i + 2, len(pts) - 1)][:2]
        cp1x = x1 + (x2 - x0) / 6.0
        cp1y = y1 + (y2 - y0) / 6.0
        cp2x = x2 - (x3 - x1) / 6.0
        cp2y = y2 - (y3 - y1) / 6.0
        path.append(f"C {cp1x:.1f} {cp1y:.1f}, {cp2x:.1f} {cp2y:.1f}, {x2:.1f} {y2:.1f}")
    return " ".join(path)


def draw_activity_graph(s):
    """Refined interactive Activity graph with dynamic scaling and hover tooltips."""
    H, W = 250, WIDTH
    weeks = s["weeks"]
    
    all_days = []
    for w in weeks:
        for d in w:
            all_days.append(d)
    recent = all_days[-30:] if len(all_days) >= 30 else all_days
    
    counts = [d.get("contributionCount", 0) for d in recent]
    peak_val = max(counts) if counts else 0
    max_val = max(peak_val, 4)
    if max_val % 2 != 0:
        max_val += 1
    
    plot_x0, plot_y0 = 52, 52
    plot_w, plot_h = W - plot_x0 - 25, 138
    plot_y1 = plot_y0 + plot_h

    p = [head(W, H)]
    
    card_styles = (
        "<style>"
        ".bg-card{fill:#0d1117;stroke:#30363d;stroke-width:1}"
        ".grid-l{stroke:#21262d;stroke-dasharray:3 3;stroke-width:1}"
        ".title-t{fill:#58a6ff;font-weight:600}"
        ".line-p{stroke:#58a6ff;stroke-width:2.8;fill:none;stroke-linecap:round;stroke-linejoin:round}"
        ".dot-p{fill:#58a6ff;stroke:#0d1117;stroke-width:1.8;transition:all 0.2s ease}"
        ".point-group{cursor:pointer}"
        ".point-group:hover .dot-p{r:5.5;fill:#ffffff;stroke:#58a6ff;stroke-width:2.2}"
        ".point-group:hover .tip{opacity:1}"
        ".tip{pointer-events:none;opacity:0;transition:opacity 0.2s ease}"
        ".tip-bg{fill:#161b22;stroke:#58a6ff;stroke-width:1;filter:drop-shadow(0 2px 6px rgba(0,0,0,0.5))}"
        ".tip-txt{fill:#58a6ff;font-size:9.5px;font-weight:600}"
        "</style>"
        "<defs>"
        '<linearGradient id="area-g" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0%" stop-color="#58a6ff" stop-opacity="0.5"/>'
        '<stop offset="100%" stop-color="#58a6ff" stop-opacity="0.02"/>'
        '</linearGradient>'
        "</defs>"
    )
    p.append(card_styles)
    p.append(f'<rect width="{W}" height="{H}" rx="8" class="bg-card"/>')

    p.append(f'<g opacity="0">{fade(0.10)}'
             + label(W / 2, 32, "Faheem Ali&apos;s Contribution Graph", 13, "title-t", "middle")
             + '</g>')

    y_ticks = 4
    for i in range(y_ticks + 1):
        v = int(max_val * (y_ticks - i) / y_ticks)
        y = plot_y0 + (i / y_ticks) * plot_h
        p.append(f'<line x1="{plot_x0}" y1="{y:.1f}" x2="{plot_x0 + plot_w}" y2="{y:.1f}" class="grid-l"/>')
        p.append(label(plot_x0 - 8, y + 3.5, str(v), 9.5, "m-f", "end"))

    p.append(f'<text x="16" y="{plot_y0 + plot_h / 2:.1f}" class="m-f" font-size="9.5" '
             f'text-anchor="middle" transform="rotate(-90 16 {plot_y0 + plot_h / 2:.1f})">Contributions</text>')

    n = len(recent)
    x_step = plot_w / max(n - 1, 1)
    pts = []
    for i, d in enumerate(recent):
        cx = plot_x0 + i * x_step
        cy = plot_y1 - (d.get("contributionCount", 0) / max_val) * plot_h
        pts.append((cx, cy, d))

    for i, (cx, cy, d) in enumerate(pts):
        day_num = d["date"][8:10].lstrip("0")
        if i % 2 == 0 or i == n - 1:
            p.append(label(cx, plot_y1 + 15, day_num, 9, "m-f", "middle"))

    p.append(label(plot_x0 + plot_w / 2, H - 8, "Days", 9.5, "m-f", "middle"))

    path_d = smooth_path(pts)
    area_d = f"{path_d} L {pts[-1][0]:.1f} {plot_y1:.1f} L {pts[0][0]:.1f} {plot_y1:.1f} Z"

    cid = "act-wipe"
    clip, cursor = wipe(cid, plot_x0, plot_y0 - 5, plot_w, plot_h + 10, 0.35, 1.1)
    p.append(clip)

    p.append(f'<g clip-path="url(#{cid})">')
    p.append(f'<path d="{area_d}" fill="url(#area-g)"/>')
    p.append(f'<path d="{path_d}" class="line-p"/>')
    p.append('</g>')
    p.append(cursor)

    # Interactive points with tooltips
    for cx, cy, d in pts:
        cnt = d.get("contributionCount", 0)
        dt_str = d.get("date", "")
        # Format date string e.g. "Aug 24"
        if len(dt_str) >= 10:
            m_num = int(dt_str[5:7])
            m_str = MON[m_num - 1]
            day_str = dt_str[8:10].lstrip("0")
            tip_label = f"{m_str} {day_str}: {cnt} contrib{'s' if cnt != 1 else ''}"
        else:
            tip_label = f"{cnt} contribs"

        tip_w = len(tip_label) * 6.2 + 16
        tip_x = max(plot_x0 + 4, min(cx - tip_w / 2, W - tip_w - 10))
        tip_y = max(plot_y0 - 15, cy - 28)

        p.append(
            f'<g class="point-group">'
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="3.2" class="dot-p"/>'
            f'<g class="tip">'
            f'<rect x="{tip_x:.1f}" y="{tip_y:.1f}" width="{tip_w:.1f}" height="20" rx="4" class="tip-bg"/>'
            f'<text x="{tip_x + tip_w / 2:.1f}" y="{tip_y + 13.5:.1f}" text-anchor="middle" class="tip-txt">{tip_label}</text>'
            f'</g></g>'
        )

    p.append("</svg>")
    return "".join(p)


# ---------------------------------------------------------------- main

def write(path, svg):
    old = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = f.read()
    if old == svg:
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    return True


import random

def mock_summary(login):
    weeks = []
    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=364)
    cur_date = start_date
    weekly = []
    random.seed(123)
    days_list = []

    raw_counts = [0] * 300 + [1] * 35 + [2] * 18 + [3] * 8 + [4] * 3 + [5] * 1
    random.shuffle(raw_counts)

    idx = 0
    for w in range(52):
        week_days = []
        w_sum = 0
        for d in range(7):
            cnt = raw_counts[idx % len(raw_counts)]
            idx += 1
            date_str = cur_date.isoformat()
            wd = (cur_date.weekday() + 1) % 7
            week_days.append({"contributionCount": cnt, "date": date_str, "weekday": wd})
            days_list.append({"contributionCount": cnt, "date": date_str})
            w_sum += cnt
            cur_date += timedelta(days=1)
        weeks.append(week_days)
        weekly.append(w_sum)

    cur_streak, best_streak = streaks(days_list)
    by_size = [("TypeScript", 45000), ("C++", 32000), ("CSS", 18000), ("JavaScript", 12000), ("Python", 8000)]
    by_repo = [("TypeScript", 4), ("C++", 3), ("CSS", 2), ("JavaScript", 1), ("Python", 1)]

    return dict(
        login=login,
        total=sum(weekly),
        active=sum(1 for d in days_list if d["contributionCount"] > 0),
        best_week=max(weekly),
        weekly=weekly, weeks=weeks,
        current=cur_streak, longest=best_streak,
        by_size=by_size, by_repo=by_repo
    )


def main():
    token = os.environ.get("GITHUB_TOKEN")
    login = os.environ.get("GH_LOGIN", "Faheem2641")
    out_dir = os.environ.get("OUT_DIR", ".")

    if token:
        s = summarise(fetch(login, token))
    else:
        print("Note: GITHUB_TOKEN not set; generating baseline SVG stats for Faheem2641.")
        s = mock_summary(login)

    files = {"stats.svg": draw_stats(s), "streak.svg": draw_streak(s),
             "langs.svg": draw_langs(s), "year.svg": draw_year(s),
             "activity.svg": draw_activity_graph(s)}
    for word in ("about", "stack", "projects", "stats"):
        files[f"hd-{word.replace(' ', '-')}.svg"] = draw_heading(word)

    changed = [n for n, svg in files.items()
               if write(os.path.join(out_dir, n), svg)]
    print(f"{s['total']} contributions, {s['active']} active days, "
          f"best week {s['best_week']}, current streak "
          f"{s['current']['length']}, longest {s['longest']['length']}")
    print("languages by bytes: "
          + ", ".join(f"{n} {v}" for n, v in s["by_size"]))
    print("updated: " + (", ".join(sorted(changed)) if changed else "nothing"))


if __name__ == "__main__":
    main()
