#!/usr/bin/env python3
"""Adaptive ASCII Portrait Generator.

Automatically converts a local image or fetches the live GitHub profile picture
for a user (default: Faheem2641) into an animated SMIL ASCII SVG portrait.
Inlines JetBrains Mono font automatically for pinned character geometry.
"""
import sys
import os
import io
import re
import base64
import urllib.request
import cv2
import numpy as np
from PIL import Image

RAMP = " .`:-=+*cs#%@"
COLS = 85
ROW_RATIO = 0.48
FG_LIGHT = "#58a6ff"
FG_DARK = "#f0f6fc"
CHAR_W = 7.74
FONT_SIZE = 12.9
LINE_H = 15
ROW_DELAY = 0.05
FAMILY = "JBMono,ui-monospace,SFMono-Regular,Menlo,Consolas,&apos;Liberation Mono&apos;,monospace"
HERE = os.path.dirname(os.path.abspath(__file__))
FONT_PATH = os.path.join(HERE, "fonts", "jbmono-ramp.woff2")


def fetch_github_avatar(username):
    url = f"https://github.com/{username}.png"
    print(f"Fetching live profile picture for @{username} from {url}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 Profile-Avatar-Generator"})
    with urllib.request.urlopen(req, timeout=15) as res:
        return Image.open(io.BytesIO(res.read())).convert("RGB")


def get_image(target):
    if target and os.path.isfile(target):
        print(f"Processing specified local image: {target}")
        return Image.open(target).convert("RGB")

    # Check common local avatar filenames in repository root
    repo_root = os.path.dirname(HERE)
    for fname in ("download.jpg", "avatar.jpg", "avatar.png", "profile.jpg", "profile.png"):
        candidate = os.path.join(repo_root, fname)
        if os.path.isfile(candidate):
            print(f"Processing local avatar file: {candidate}")
            return Image.open(candidate).convert("RGB")

    username = os.environ.get("GH_LOGIN", "Faheem2641")
    return fetch_github_avatar(username)


def embed_font(svg_content):
    if "JBMono" in svg_content and "@font-face" in svg_content:
        return svg_content
    if os.path.exists(FONT_PATH):
        with open(FONT_PATH, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
        rule = (f"@font-face{{font-family:JBMono;font-style:normal;"
                f"font-weight:400;font-display:block;"
                f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
        if "<style>" in svg_content:
            svg_content = svg_content.replace("<style>", f"<style>{rule}", 1)
    return svg_content


def process_avatar(target=None, out_path=None):
    if not out_path:
        out_path = os.path.join(os.path.dirname(HERE), "ascii.svg")

    src = get_image(target)
    w, h = src.size

    gray = cv2.cvtColor(np.array(src), cv2.COLOR_RGB2GRAY)
    gray[gray > 220] = 255  # clear off-white / light background

    gray = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
    gray = (255.0 * (gray / 255.0) ** 1.3).astype("uint8")

    img = Image.fromarray(gray)
    rows = int(COLS * (h / w) * ROW_RATIO)
    img = img.resize((COLS, rows), Image.LANCZOS)
    px = list(img.get_flattened_data()) if hasattr(img, "get_flattened_data") else list(img.getdata())
    n = len(RAMP)

    lines = []
    for r in range(rows):
        line = "".join(
            RAMP[min(n - 1, int((1 - px[r * COLS + c] / 255.0) * n))]
            for c in range(COLS)
        ).rstrip()
        lines.append(line)

    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    pad = 14
    width = int(COLS * CHAR_W + pad * 2)
    height = len(lines) * LINE_H + pad * 2

    p = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
         f'height="{height}" viewBox="0 0 {width} {height}" '
         f'font-family="{FAMILY}">',
         f'<style>.a{{fill:{FG_LIGHT}}}'
         f'@media(prefers-color-scheme:dark){{.a{{fill:{FG_DARK}}}}}</style>']

    for i, line in enumerate(lines):
        y = pad + i * LINE_H
        begin = f"{i * ROW_DELAY:.2f}s"
        end = f"{(i + 1) * ROW_DELAY:.2f}s"
        w_px = max(len(line), 1) * CHAR_W
        safe = (line.replace("&", "&amp;").replace("<", "&lt;")
                    .replace(">", "&gt;"))

        p.append(f'<clipPath id="c{i}"><rect x="{pad}" y="{y}" '
                 f'height="{LINE_H}" width="0">'
                 f'<animate attributeName="width" from="0" to="{w_px:.1f}" '
                 f'begin="{begin}" dur="{ROW_DELAY}s" fill="freeze"/>'
                 f'</rect></clipPath>')
        p.append(f'<g clip-path="url(#c{i})"><text xml:space="preserve" '
                 f'x="{pad}" y="{y + 11.2:.1f}" class="a" '
                 f'font-size="{FONT_SIZE}">{safe}</text></g>')
        p.append(f'<rect y="{y + 1}" width="6" height="12" class="a" opacity="0">'
                 f'<animate attributeName="x" from="{pad}" to="{pad + w_px:.1f}" '
                 f'begin="{begin}" dur="{ROW_DELAY}s" fill="freeze"/>'
                 f'<set attributeName="opacity" to="0.8" begin="{begin}"/>'
                 f'<set attributeName="opacity" to="0" begin="{end}"/></rect>')

    p.append("</svg>")
    svg_content = embed_font("".join(p))

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"Generated {out_path} ({len(lines)} rows x {COLS} cols) with embedded font.")

if __name__ == "__main__":
    target_img = sys.argv[1] if len(sys.argv) > 1 else None
    process_avatar(target_img)
