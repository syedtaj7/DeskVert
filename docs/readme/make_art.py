"""Generates the animated SVG artwork used by README.md.

    python docs/readme/make_art.py

Pure CSS animations inside SVG files: GitHub shows them as images, so they
play in the README without scripts. Colors match the app (Verdant palette,
dark surfaces). Viewers who ask for reduced motion get the still, final frame.
"""

from __future__ import annotations

import math
from pathlib import Path

OUT = Path(__file__).resolve().parent

BG = "#121214"
S1 = "#1C1C20"
S2 = "#26262B"
S3 = "#303036"
LINE = "rgba(255,255,255,0.08)"
TEXT = "#F0F0EE"
DIM = "#96969E"
ACC = "#34BE84"
ON_ACC = "#121214"
AMBER = "#E8B04B"
PAPER = "#F4F4F1"
INK = "#2A2A30"

SANS = "'Segoe UI Variable Display','Segoe UI',Inter,-apple-system,BlinkMacSystemFont,'Helvetica Neue',Arial,sans-serif"
MONO = "'Cascadia Code','Cascadia Mono',Consolas,'SF Mono',Menlo,ui-monospace,monospace"

BASE_CSS = f"""
.s{{font-family:{SANS}}} .m{{font-family:{MONO}}}
.b{{font-weight:700}} .sb{{font-weight:600}}
.fb{{transform-box:fill-box;transform-origin:center}}
@media (prefers-reduced-motion: reduce){{
*{{animation:none!important}}
.ren,.wm,.pn,.szlast,.zipt,.first,[class*="txt"],.line:first-of-type,.line:first-of-type .ok{{opacity:1}}
[class*="ink"],.cover{{opacity:0}}
}}
"""


def svg(w: int, h: int, body: str, css: str, title: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{title}">\n<title>{title}</title>\n<style>{BASE_CSS}{css}</style>\n'
            f'{body}\n</svg>\n')


def card(w: int, h: int, r: int = 28) -> str:
    return (f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="{r}" fill="{BG}" '
            f'stroke="{LINE}"/>')


def arc_slice(cx, cy, r0, r1, a0, a1) -> str:
    """Ring segment between angles a0..a1 (degrees, 0 = up, clockwise)."""
    def pt(r, a):
        t = math.radians(a - 90)
        return cx + r * math.cos(t), cy + r * math.sin(t)

    large = 1 if a1 - a0 > 180 else 0
    x0, y0 = pt(r1, a0)
    x1, y1 = pt(r1, a1)
    x2, y2 = pt(r0, a1)
    x3, y3 = pt(r0, a0)
    return (f"M{x0:.1f},{y0:.1f} A{r1},{r1} 0 {large} 1 {x1:.1f},{y1:.1f} L{x2:.1f},{y2:.1f} "
            f"A{r0},{r0} 0 {large} 0 {x3:.1f},{y3:.1f} Z")


def polar(cx, cy, r, a):
    t = math.radians(a - 90)
    return cx + r * math.cos(t), cy + r * math.sin(t)


def chip_w(text: str, size: float, pad: float = 14) -> float:
    return len(text) * size * 0.62 + pad * 2


def keycap(x, y, label, cls, w=None) -> str:
    w = w or chip_w(label, 22, 22)
    return (f'<g transform="translate({x},{y})"><g class="{cls}">'
            f'<rect x="0" y="6" width="{w:.0f}" height="58" rx="12" fill="#0B0B0D"/>'
            f'<rect class="cap" x="0" y="0" width="{w:.0f}" height="58" rx="12" fill="{S2}" stroke="{S3}"/>'
            f'<text class="s sb" x="{w / 2:.0f}" y="37" font-size="22" fill="{TEXT}" text-anchor="middle">{label}</text>'
            f'</g></g>'), w



# ======================================================================= orbit (the picker)

ORBIT_STEPS = [  # (ring, label, tag, caption, blurb line 1, blurb line 2, new file)
    ("o", "WEBP", "FORMAT", "quality 92", "Small and sharp,", "made for the web", "IMG_2041.webp"),
    ("i", "Compress", "TOOL", "under 100 KB", "Pick a size, see", "the quality first", "IMG_2041 (compressed).jpg"),
    ("o", "PDF", "FORMAT", "1 page", "One page per", "picture", "IMG_2041.pdf"),
    ("i", "Read text", "TOOL", "OCR", "Copy the words", "out of a scan", "IMG_2041 (text).txt"),
    ("o", "PNG", "FORMAT", "lossless", "Lossless, keeps", "transparency", "IMG_2041.png"),
    ("i", "ZIP", "TOOL", "pack", "Pack everything", "into one .zip", "IMG_2041.zip"),
]
ORBIT_OUTER = ["JPG", "PNG", "WEBP", "PDF", "HEIC", "AVIF", "ICO", "GIF"]
ORBIT_INNER = ["Compress", "Read text", "ZIP"]


def orbit_picker(cx, cy, R_out, R_in, pr, hub_r, step_s, start, prefix, card_x=None, center="IMG_2041.heic",
                 label_px=13, spin=(70, 50)):
    """The Orbit picker: inner ring of tools, outer ring of formats, drifting in opposite
    directions with labels kept upright; a highlight (plus tether, hub text and side card)
    steps through ORBIT_STEPS."""
    n = len(ORBIT_STEPS)
    total = step_s * n
    win = 100 / n
    css = f"""
.{prefix}ro{{animation:{prefix}spin {spin[0]}s linear infinite}}
.{prefix}uo{{animation:{prefix}spin {spin[0]}s linear infinite reverse}}
.{prefix}ri{{animation:{prefix}spin {spin[1]}s linear infinite reverse}}
.{prefix}ui{{animation:{prefix}spin {spin[1]}s linear infinite}}
@keyframes {prefix}spin{{to{{transform:rotate(360deg)}}}}
.{prefix}pop{{animation:{prefix}pop .7s cubic-bezier(.2,1.5,.4,1) both}}
@keyframes {prefix}pop{{from{{opacity:0;transform:scale(.3)}}to{{opacity:1;transform:none}}}}
.{prefix}hl{{opacity:0;animation:{prefix}hl {total}s linear infinite}}
@keyframes {prefix}hl{{0%{{opacity:0}}2%{{opacity:1}}{win - 2:.2f}%{{opacity:1}}{win:.2f}%{{opacity:0}}100%{{opacity:0}}}}
.{prefix}card{{opacity:0;animation:{prefix}card {total}s cubic-bezier(.2,.9,.2,1) infinite}}
@keyframes {prefix}card{{0%{{opacity:0;transform:translateX(-10px)}}2.5%{{opacity:1;transform:none}}{win - 2:.2f}%{{opacity:1;transform:none}}{win:.2f}%{{opacity:0}}100%{{opacity:0}}}}
"""
    step_of = {(r, lbl): j for j, (r, lbl, *_rest) in enumerate(ORBIT_STEPS)}
    delay = lambda j: f"animation-delay:{start + j * step_s:.2f}s"  # noqa: E731
    parts = []
    # orbits
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{R_out}" fill="none" stroke="rgba(255,255,255,0.16)" '
                 f'stroke-width="1.4" stroke-linecap="round" stroke-dasharray="0.1 7"/>')
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{R_in}" fill="none" stroke="rgba(255,255,255,0.14)" '
                 f'stroke-width="1.2" stroke-dasharray="4 7"/>')
    order = 0
    for ring, labels, R, rot, unrot in (("i", ORBIT_INNER, R_in, "ri", "ui"), ("o", ORBIT_OUTER, R_out, "ro", "uo")):
        m = len(labels)
        g = [f'<circle cx="{cx}" cy="{cy}" r="{R + pr + 2}" fill="none"/>']  # keeps the group centred on the hub
        for k, lbl in enumerate(labels):
            a = -90 + k * 360 / m + (180 / m if ring == "o" else 0)
            x, y = polar(cx, cy, R, a + 90)
            j = step_of.get((ring, lbl))
            tool = ring == "i"
            size = label_px if len(lbl) <= 5 else label_px * 0.82
            dot = (f'<circle cx="0" cy="{-pr * 0.42:.1f}" r="{pr * 0.09:.1f}" fill="{{dc}}"/>' if tool else
                   f'<circle cx="0" cy="{-pr * 0.42:.1f}" r="{pr * 0.085:.1f}" fill="none" stroke="{{dc}}" stroke-width="1.2"/>')
            label = (f'<text class="s b" x="0" y="{size * 0.42 + pr * 0.1:.1f}" font-size="{size:.1f}" '
                     f'text-anchor="middle" fill="{{tc}}">{lbl}</text>')
            hl = ""
            tether = ""
            if j is not None:
                hl = (f'<g class="{prefix}hl{" first" if j == 0 else ""}" style="{delay(j)}">'
                      f'<circle r="{pr + 6}" fill="none" stroke="{ACC}" stroke-opacity=".35" stroke-width="2"/>'
                      f'<circle r="{pr + 1}" fill="{ACC}"/>' + dot.format(dc=ON_ACC) + label.format(tc=ON_ACC) + '</g>')
                t0, t1 = hub_r + 4, R - pr - 7
                ax, ay = polar(cx, cy, t0, a + 90)
                bx, by = polar(cx, cy, t1, a + 90)
                tether = (f'<g class="{prefix}hl{" first" if j == 0 else ""}" style="{delay(j)}"><line x1="{ax:.1f}" '
                          f'y1="{ay:.1f}" x2="{bx:.1f}" y2="{by:.1f}" stroke="{ACC}" stroke-width="2.2" '
                          f'stroke-linecap="round"/></g>')
            g.append(tether)
            g.append(f'<g transform="translate({x:.1f},{y:.1f})"><g class="fb {prefix}{unrot}">'
                     f'<g class="fb {prefix}pop" style="animation-delay:{0.25 + order * 0.05:.2f}s">'
                     f'<circle r="{pr}" fill="{S2}" stroke="rgba(255,255,255,0.10)"/>' + dot.format(dc=ACC if tool else DIM)
                     + label.format(tc=TEXT) + hl + '</g></g></g>')
            order += 1
        parts.append(f'<g class="fb {prefix}{rot}">{"".join(g)}</g>')
    # hub
    parts.append(f'<g class="fb {prefix}pop" style="animation-delay:.1s"><circle cx="{cx}" cy="{cy}" r="{hub_r}" '
                 f'fill="{S1}" stroke="rgba(255,255,255,0.12)"/>'
                 f'<text class="s b" x="{cx}" y="{cy - 2}" font-size="{label_px}" text-anchor="middle" fill="{TEXT}">'
                 f'{center}</text></g>')
    for j, st in enumerate(ORBIT_STEPS):
        parts.append(f'<g class="{prefix}hl{" first" if j == 0 else ""}" style="{delay(j)}"><text class="s sb" x="{cx}" '
                     f'y="{cy + 17}" font-size="{label_px * 0.85:.1f}" text-anchor="middle" fill="{ACC}">→ {st[1]}</text></g>')
    # side card
    if card_x is not None:
        cw, chh = 190, 150
        y0 = cy - chh / 2
        for j, (ring, lbl, tag, cap, b1, b2, out) in enumerate(ORBIT_STEPS):
            capw = chip_w(cap, 11, 9)
            parts.append(
                f'<g class="{prefix}card{" first" if j == 0 else ""}" style="{delay(j)}">'
                f'<rect x="{card_x}" y="{y0}" width="{cw}" height="{chh}" rx="16" fill="{S1}" stroke="{S3}"/>'
                f'<text class="m b" x="{card_x + 16}" y="{y0 + 26}" font-size="10" letter-spacing="1" '
                f'fill="{ACC if tag == "TOOL" else DIM}">{tag}</text>'
                f'<rect x="{card_x + cw - 16 - capw:.1f}" y="{y0 + 12}" width="{capw:.1f}" height="20" rx="10" fill="{S2}"/>'
                f'<text class="s sb" x="{card_x + cw - 16 - capw / 2:.1f}" y="{y0 + 26}" font-size="11" fill="{DIM}" '
                f'text-anchor="middle">{cap}</text>'
                f'<text class="s b" x="{card_x + 16}" y="{y0 + 58}" font-size="22" fill="{TEXT}">{lbl}</text>'
                f'<text class="s" x="{card_x + 16}" y="{y0 + 82}" font-size="13" fill="{TEXT}" fill-opacity=".82">{b1}</text>'
                f'<text class="s" x="{card_x + 16}" y="{y0 + 99}" font-size="13" fill="{TEXT}" fill-opacity=".82">{b2}</text>'
                f'<text class="m" x="{card_x + 16}" y="{y0 + 128}" font-size="11"><tspan fill="{ACC}">→ </tspan>'
                f'<tspan fill="{DIM}">{out if len(out) <= 22 else out[:20] + "…"}</tspan></text></g>')
    return "".join(parts), css


# ======================================================================= hero

WHEEL = ["Compress", "PNG", "WEBP", "Lock", "Read text", "PDF", "ZIP", "More"]
WHEEL_SUB = ["under 100 KB", "lossless", "quality 92", "AES-256", "OCR", "1 file", "pack", "all formats"]


def wheel(cx, cy, r0, r1, names, subs, step_s, prefix, label_size=17, sub_size=11, center=("convert to", "")):
    n = len(names)
    gap = 2.2
    total = step_s * n
    parts = []
    css = [f"""
.{prefix}pop{{animation:{prefix}pop .7s cubic-bezier(.2,1.4,.4,1) both}}
@keyframes {prefix}pop{{0%{{opacity:0;transform:scale(.4)}}100%{{opacity:1;transform:scale(1)}}}}
.{prefix}hl{{opacity:0;animation:{prefix}hl {total}s linear infinite}}
@keyframes {prefix}hl{{0%{{opacity:0}}1.5%{{opacity:1}}{100 / n - 1.5:.2f}%{{opacity:1}}{100 / n:.2f}%{{opacity:0}}100%{{opacity:0}}}}
"""]
    for i, name in enumerate(names):
        a0, a1 = i * 360 / n + gap / 2, (i + 1) * 360 / n - gap / 2
        mid = (a0 + a1) / 2
        lx, ly = polar(cx, cy, (r0 + r1) / 2, mid)
        d = arc_slice(cx, cy, r0, r1, a0, a1)
        sub = subs[i] if subs else ""
        lab = (f'<text class="s b" x="{lx:.1f}" y="{ly + (0 if sub else 6):.1f}" font-size="{label_size}" '
               f'text-anchor="middle" fill="{{c}}">{name}</text>')
        sl = (f'<text class="s" x="{lx:.1f}" y="{ly + sub_size + 6:.1f}" font-size="{sub_size}" '
              f'text-anchor="middle" fill="{{c2}}">{sub}</text>') if sub else ""
        delay = 0.15 + i * 0.09
        parts.append(
            f'<g class="fb {prefix}pop" style="animation-delay:{delay:.2f}s">'
            f'<path d="{d}" fill="{S2}" stroke="{BG}" stroke-width="1"/>'
            + lab.format(c=TEXT) + sl.format(c2=DIM) +
            f'<g class="{prefix}hl" style="animation-delay:{1.4 + i * step_s:.2f}s">'
            f'<path d="{d}" fill="{ACC}"/>' + lab.format(c=ON_ACC) + sl.format(c2="rgba(18,18,20,.7)") +
            '</g></g>')
    parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r0 - 6}" fill="{S1}" stroke="{S3}"/>')
    if center[0]:
        parts.append(f'<text class="s b" x="{cx}" y="{cy + (-2 if center[1] else 6)}" font-size="{label_size + 1}" '
                     f'text-anchor="middle" fill="{TEXT}">{center[0]}</text>')
    if center[1]:
        parts.append(f'<text class="s" x="{cx}" y="{cy + 18}" font-size="{sub_size + 1}" text-anchor="middle" '
                     f'fill="{DIM}">{center[1]}</text>')
    return "".join(parts), "".join(css)


def hero() -> str:
    W, H = 1200, 640
    cx, cy = 752, 300
    css = f"""
.grid{{animation:drift 18s linear infinite}}
@keyframes drift{{from{{transform:translate(0,0)}}to{{transform:translate(-32px,-32px)}}}}
.rise{{animation:rise .9s cubic-bezier(.2,.9,.2,1) both}}
@keyframes rise{{from{{opacity:0;transform:translateY(26px)}}to{{opacity:1;transform:none}}}}
.under{{animation:under 1.1s .5s cubic-bezier(.6,0,.2,1) both}}
@keyframes under{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
.dot{{animation:blink 1.6s ease-in-out infinite}}
@keyframes blink{{50%{{opacity:.25}}}}
.k1{{animation:press 4s ease-in-out infinite}}
.k2{{animation:press 4s .18s ease-in-out infinite}}
@keyframes press{{0%,8%,30%,100%{{transform:none}}14%,22%{{transform:translateY(6px)}}}}
.ripple{{animation:ripple 4s cubic-bezier(.1,.6,.3,1) infinite;opacity:0}}
@keyframes ripple{{0%,12%{{opacity:0;transform:scale(.55)}}16%{{opacity:.9}}60%,100%{{opacity:0;transform:scale(1.35)}}}}
.orbit{{animation:spin 48s linear infinite}}
.unspin{{animation:spin 48s linear infinite reverse}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
.dash{{animation:dash 6s linear infinite}}
@keyframes dash{{to{{stroke-dashoffset:-120}}}}
.toast{{animation:toast 8s 1.4s cubic-bezier(.2,.9,.2,1) infinite both}}
@keyframes toast{{0%,4%{{opacity:0;transform:translateY(24px)}}9%,40%{{opacity:1;transform:none}}46%,100%{{opacity:0;transform:translateY(-10px)}}}}
.check{{stroke-dasharray:30;animation:check 8s 1.4s ease-out infinite both}}
@keyframes check{{0%,8%{{stroke-dashoffset:30}}14%,100%{{stroke-dashoffset:0}}}}
.stat{{animation:rise .8s cubic-bezier(.2,.9,.2,1) both}}
"""
    body = [card(W, H)]
    body.append(f'<defs><pattern id="dots" width="32" height="32" patternUnits="userSpaceOnUse">'
                f'<circle cx="2" cy="2" r="1.4" fill="rgba(255,255,255,0.07)"/></pattern>'
                f'<clipPath id="cardclip"><rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="27"/></clipPath></defs>')
    body.append(f'<g clip-path="url(#cardclip)"><g class="grid"><rect x="0" y="0" width="{W + 64}" height="{H + 64}" '
                f'fill="url(#dots)"/></g></g>')
    # --- left column
    body.append(f'<g class="rise" style="animation-delay:.05s"><rect x="80" y="92" width="268" height="36" rx="18" '
                f'fill="{S1}" stroke="{S3}"/><circle class="dot" cx="102" cy="110" r="5" fill="{ACC}"/>'
                f'<text class="s sb" x="118" y="116" font-size="15" fill="{TEXT}">v1.2 · free &amp; open source</text></g>')
    body.append(f'<g class="rise" style="animation-delay:.15s"><text class="s b" x="76" y="236" font-size="104" '
                f'fill="{TEXT}" letter-spacing="-3">Tapshift</text></g>')
    body.append(f'<rect class="fb under" x="82" y="258" width="150" height="8" rx="4" fill="{ACC}" '
                f'style="transform-origin:left center"/>')
    for i, (txt, col) in enumerate((("Select a file.", TEXT), ("Tap Ctrl + Shift.", TEXT), ("Pick a format.", ACC))):
        body.append(f'<g class="rise" style="animation-delay:{.45 + i * .2:.2f}s"><text class="s sb" x="80" '
                    f'y="{318 + i * 40}" font-size="30" fill="{col}">{txt}</text></g>')
    k1, w1 = keycap(80, 450, "Ctrl", "k1", 108)
    k2, w2 = keycap(80 + 108 + 52, 450, "Shift", "k2", 124)
    body.append(f'<g class="rise" style="animation-delay:1.1s">{k1}'
                f'<text class="s b" x="{80 + 108 + 26}" y="488" font-size="28" fill="{DIM}" text-anchor="middle">+</text>'
                f'{k2}<text class="s" x="{80 + 108 + 52 + 124 + 22}" y="486" font-size="16" fill="{DIM}">'
                f'tap, don\'t hold</text></g>')
    stats = (("40+", "formats"), ("17", "tools"), ("0%", "CPU when idle"))
    for i, (big, small) in enumerate(stats):
        x = 80 + i * 150
        body.append(f'<g class="stat" style="animation-delay:{1.3 + i * .12:.2f}s"><text class="s b" x="{x}" y="574" '
                    f'font-size="30" fill="{TEXT}">{big}</text><text class="s" x="{x}" y="598" font-size="14" '
                    f'fill="{DIM}">{small}</text></g>')
    # --- right: ripples behind the picker, then the picker itself (Orbit)
    for i in range(3):
        body.append(f'<circle class="fb ripple" style="animation-delay:{i * .22:.2f}s" cx="{cx}" cy="{cy}" r="190" '
                    f'fill="none" stroke="{ACC}" stroke-width="2"/>')
    orb, ocss = orbit_picker(cx, cy, 168, 102, 29, 58, 1.6, 1.4, "h", card_x=cx + 168 + 29 + 38)
    css += ocss
    body.append(orb)
    # --- toast
    tw = 452
    body.append(f'<g transform="translate({cx + 60 - tw / 2},{H - 74})"><g class="toast">'
                f'<rect width="{tw}" height="50" rx="25" fill="{S1}" stroke="{S3}"/>'
                f'<circle cx="25" cy="25" r="14" fill="{ACC}"/>'
                f'<path class="check" d="M18.5 25.5 l4.5 4.5 l8.5 -9" fill="none" stroke="{ON_ACC}" stroke-width="3" '
                f'stroke-linecap="round" stroke-linejoin="round"/>'
                f'<text class="s sb" x="50" y="31" font-size="16" fill="{TEXT}">photo (compressed).jpg</text>'
                f'<text class="s" x="{tw - 22}" y="31" font-size="14" fill="{DIM}" text-anchor="end">96 KB · verified</text>'
                f'</g></g>')
    return svg(W, H, "\n".join(body), css, "Tapshift: select a file, tap Ctrl + Shift, pick a format")


# ======================================================================= ticker

TICKS = [
    ("IMG_2041.HEIC", "Compress · under 100 KB", "96 KB at quality 82%"),
    ("contract.pdf", "Lock · AES-256", "contract (locked).pdf"),
    ("scan-001.jpg", "Read text", "214 words recognized"),
    ("sales.csv", "Excel", "1,204 rows · 007 stays 007"),
    ("12 photos", "ZIP", "12 files checked"),
    ("notes.md", "PDF", "3 A4 pages"),
]


def ticker() -> str:
    W, H = 1200, 96
    n = len(TICKS)
    per = 3.2
    total = per * n
    win = 100 / n
    css = f"""
.line{{opacity:0;animation:line {total}s linear infinite}}
@keyframes line{{0%{{opacity:0}}1%{{opacity:1}}{win - 1.5:.2f}%{{opacity:1}}{win:.2f}%{{opacity:0}}100%{{opacity:0}}}}
.cover{{animation:type {total}s steps(48,end) infinite}}
@keyframes type{{0%{{transform:translateX(0)}}{win * .55:.2f}%,100%{{transform:translateX(1000px)}}}}
.ok{{opacity:0;animation:ok {total}s linear infinite}}
@keyframes ok{{0%,{win * .55:.2f}%{{opacity:0}}{win * .6:.2f}%,{win - 1.5:.2f}%{{opacity:1}}{win:.2f}%,100%{{opacity:0}}}}
.caret{{animation:caret 1s steps(1) infinite}}
@keyframes caret{{50%{{opacity:0}}}}
"""
    body = [card(W, H, 20)]
    body.append(f'<circle cx="34" cy="48" r="6" fill="{ACC}"/><circle cx="34" cy="48" r="11" fill="none" '
                f'stroke="{ACC}" stroke-opacity=".35"/>')
    body.append(f'<defs><clipPath id="tc"><rect x="60" y="10" width="{W - 80}" height="{H - 20}"/></clipPath></defs>')
    lines = []
    for i, (src, tool, res) in enumerate(TICKS):
        d = f"animation-delay:{i * per:.2f}s"
        lines.append(
            f'<g class="line" style="{d}">'
            f'<text class="m" x="64" y="56" font-size="20"><tspan fill="{TEXT}">{src}</tspan>'
            f'<tspan fill="{DIM}">  →  </tspan><tspan fill="{ACC}" font-weight="600">{tool}</tspan></text>'
            f'<g class="cover" style="{d}"><rect x="60" y="14" width="1100" height="68" fill="{BG}"/>'
            f'<rect class="caret" x="62" y="34" width="3" height="28" fill="{ACC}"/></g>'
            f'<g class="ok" style="{d}"><text class="s sb" x="{W - 34}" y="55" font-size="18" fill="{TEXT}" '
            f'text-anchor="end">✓  {res}</text></g></g>')
    body.append(f'<g clip-path="url(#tc)">{"".join(lines)}</g>')
    return svg(W, H, "\n".join(body), css, "Examples: compress a photo, lock a PDF, read text, CSV to Excel, zip, Markdown to PDF")


# ======================================================================= flow

def flow() -> str:
    W, H = 1200, 300
    xs = [150, 450, 750, 1050]
    cy = 128
    T = 8
    css = f"""
.ring{{animation:ring {T}s linear infinite}}
@keyframes ring{{0%{{stroke:{S3}}}2%,22%{{stroke:{ACC}}}25%,100%{{stroke:{S3}}}}}
.lbl{{animation:lbl {T}s linear infinite}}
@keyframes lbl{{0%{{fill:{DIM}}}2%,22%{{fill:{TEXT}}}25%,100%{{fill:{DIM}}}}}
.flowline{{animation:flowline 1.2s linear infinite}}
@keyframes flowline{{to{{stroke-dashoffset:-24}}}}
.packet{{animation:packet {T}s cubic-bezier(.6,0,.4,1) infinite}}
@keyframes packet{{0%{{transform:translateX(0);opacity:0}}3%{{opacity:1}}22%{{transform:translateX(0)}}27%{{transform:translateX(300px)}}47%{{transform:translateX(300px)}}52%{{transform:translateX(600px)}}72%{{transform:translateX(600px)}}77%{{transform:translateX(900px)}}97%{{transform:translateX(900px);opacity:1}}100%{{transform:translateX(900px);opacity:0}}}}
.sel{{animation:sel {T}s linear infinite}}
@keyframes sel{{0%,4%{{opacity:0}}7%,24%{{opacity:1}}27%,100%{{opacity:0}}}}
.cursor{{animation:cursor {T}s cubic-bezier(.4,0,.2,1) infinite}}
@keyframes cursor{{0%{{transform:translate(40px,40px);opacity:0}}3%{{opacity:1}}6%,22%{{transform:none;opacity:1}}25%,100%{{opacity:0}}}}
.fk1{{animation:fpress {T}s infinite}} .fk2{{animation:fpress {T}s .15s infinite}}
@keyframes fpress{{0%,27%{{transform:none}}31%,34%{{transform:translateY(5px)}}37%,100%{{transform:none}}}}
.done{{stroke-dasharray:44;animation:done {T}s ease-out infinite}}
@keyframes done{{0%,78%{{stroke-dashoffset:44}}86%,100%{{stroke-dashoffset:0}}}}
.badge{{animation:badge {T}s cubic-bezier(.2,1.6,.4,1) infinite}}
@keyframes badge{{0%,76%{{transform:scale(0)}}82%,98%{{transform:scale(1)}}100%{{transform:scale(0)}}}}
"""
    body = [card(W, H)]
    for a, b in zip(xs, xs[1:]):
        body.append(f'<line class="flowline" x1="{a + 76}" y1="{cy}" x2="{b - 76}" y2="{cy}" stroke="{S3}" '
                    f'stroke-width="3" stroke-dasharray="2 10" stroke-linecap="round"/>')
    labels = [("Select files", "in Explorer or on the Desktop"), ("Tap Ctrl + Shift", "press both, let go"),
              ("Pick a format", "or a tool, like Compress"), ("Saved &amp; verified", "next to the original")]
    for i, x in enumerate(xs):
        d = f"animation-delay:{i * T / 4:.2f}s"
        body.append(f'<circle class="ring" style="{d}" cx="{x}" cy="{cy}" r="68" fill="{S1}" stroke="{S3}" '
                    f'stroke-width="3"/>')
        body.append(f'<text class="s b lbl" style="{d}" x="{x}" y="{cy + 112}" font-size="21" fill="{DIM}" '
                    f'text-anchor="middle">{labels[i][0]}</text>')
        body.append(f'<text class="s" x="{x}" y="{cy + 138}" font-size="14" fill="{DIM}" text-anchor="middle">'
                    f'{labels[i][1]}</text>')
    # 1: file + selection + cursor
    x = xs[0]
    body.append(f'<rect class="sel" x="{x - 38}" y="{cy - 44}" width="76" height="88" rx="10" fill="rgba(52,190,132,.18)" '
                f'stroke="{ACC}" stroke-width="2"/>')
    body.append(f'<path d="M{x - 20},{cy - 32} h26 l14,14 v50 h-40 z" fill="{PAPER}"/>'
                f'<path d="M{x + 6},{cy - 32} v14 h14" fill="#D9D9D4"/>'
                f'<rect x="{x - 13}" y="{cy - 6}" width="26" height="4" rx="2" fill="#C9C9C4"/>'
                f'<rect x="{x - 13}" y="{cy + 3}" width="20" height="4" rx="2" fill="#C9C9C4"/>'
                f'<text class="s b" x="{x}" y="{cy + 26}" font-size="10" fill="{INK}" text-anchor="middle">JPG</text>')
    body.append(f'<g transform="translate({x + 14},{cy + 12})"><g class="cursor"><path d="M0,0 L0,24 L6,18 L11,29 '
                f'L15,27 L10,16 L18,16 Z" fill="{TEXT}" stroke="{BG}" stroke-width="1.5"/></g></g>')
    # 2: keys
    x = xs[1]
    for j, (lab, w, cls) in enumerate((("Ctrl", 50, "fk1"), ("Shift", 58, "fk2"))):
        kx = x - 56 + j * 56
        body.append(f'<g transform="translate({kx},{cy - 20})"><g class="{cls}"><rect y="4" width="{w}" height="38" '
                    f'rx="8" fill="#0B0B0D"/><rect width="{w}" height="38" rx="8" fill="{S2}" stroke="{S3}"/>'
                    f'<text class="s sb" x="{w / 2}" y="25" font-size="14" fill="{TEXT}" text-anchor="middle">{lab}'
                    f'</text></g></g>')
    # 3: mini wheel
    x = xs[2]
    mini = [f'<circle cx="{x}" cy="{cy}" r="46" fill="none" stroke="rgba(255,255,255,0.16)" stroke-dasharray="0.1 5" '
            f'stroke-linecap="round" stroke-width="1.3"/>', f'<g class="fb mspin"><circle cx="{x}" cy="{cy}" r="56" fill="none"/>']
    for k in range(6):
        px, py = polar(x, cy, 46, k * 60 + 90)
        mini.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="9" fill="{S2}" stroke="rgba(255,255,255,0.12)"/>'
                    f'<circle class="mhl" style="animation-delay:{k * 0.5:.1f}s" cx="{px:.1f}" cy="{py:.1f}" r="9.5" fill="{ACC}"/>')
    mini.append('</g>')
    mini.append(f'<circle cx="{x}" cy="{cy}" r="17" fill="{S1}" stroke="rgba(255,255,255,0.14)"/>')
    css += """
.mspin{animation:mspin 24s linear infinite}
@keyframes mspin{to{transform:rotate(360deg)}}
.mhl{opacity:0;animation:mhl 3s linear infinite}
@keyframes mhl{0%{opacity:0}3%{opacity:1}14%{opacity:1}17%{opacity:0}100%{opacity:0}}
"""
    body.append("".join(mini))
    # 4: done
    x = xs[3]
    body.append(f'<path d="M{x - 20},{cy - 32} h26 l14,14 v50 h-40 z" fill="{PAPER}"/>'
                f'<path d="M{x + 6},{cy - 32} v14 h14" fill="#D9D9D4"/>'
                f'<text class="s b" x="{x}" y="{cy + 26}" font-size="10" fill="{INK}" text-anchor="middle">WEBP</text>')
    body.append(f'<g class="fb badge"><circle cx="{x + 22}" cy="{cy - 30}" r="17" fill="{ACC}"/></g>'
                f'<path class="done" d="M{x + 14},{cy - 30} l6,6 l10,-12" fill="none" stroke="{ON_ACC}" '
                f'stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/>')
    # traveling packet
    body.append(f'<g class="packet"><circle cx="{xs[0] + 76}" cy="{cy}" r="7" fill="{ACC}"/></g>')
    return svg(W, H, "\n".join(body), css, "How it works: select files, tap Ctrl + Shift, pick a format, saved and verified")


# ======================================================================= tools

def tools() -> str:
    W, H = 1200, 720
    cw, ch, gx, gy = 368, 324, 24, 24
    T = 6
    css = f"""
.photo{{animation:photo {T}s cubic-bezier(.6,0,.3,1) infinite}}
@keyframes photo{{0%,10%{{transform:scale(1)}}55%,88%{{transform:scale(.46)}}100%{{transform:scale(1)}}}}
.bar{{animation:bar {T}s cubic-bezier(.6,0,.3,1) infinite}}
@keyframes bar{{0%,10%{{transform:scaleX(1)}}55%,88%{{transform:scaleX(.06)}}100%{{transform:scaleX(1)}}}}
.sz{{opacity:0;animation:sz {T}s linear infinite}}
@keyframes sz{{0%{{opacity:0}}1%,17%{{opacity:1}}18%,100%{{opacity:0}}}}
.szlast{{opacity:0;animation:szl {T}s linear infinite}}
@keyframes szl{{0%,54%{{opacity:0}}55%,96%{{opacity:1}}97%,100%{{opacity:0}}}}
.pill{{animation:pill {T}s cubic-bezier(.2,1.6,.4,1) infinite}}
@keyframes pill{{0%,56%{{transform:scale(0)}}62%,92%{{transform:scale(1)}}97%,100%{{transform:scale(0)}}}}
.shackle{{animation:shackle {T}s cubic-bezier(.5,0,.2,1.4) infinite}}
@keyframes shackle{{0%,18%{{transform:translateY(-12px)}}28%,92%{{transform:none}}100%{{transform:translateY(-12px)}}}}
.lockb{{animation:lockb {T}s cubic-bezier(.2,1.5,.4,1) infinite}}
@keyframes lockb{{0%,4%{{transform:scale(0)}}14%,94%{{transform:scale(1)}}100%{{transform:scale(0)}}}}
.wm{{opacity:0;animation:wm {T}s ease-out infinite}}
@keyframes wm{{0%,34%{{opacity:0;transform:scale(1.4)}}44%,92%{{opacity:1;transform:scale(1)}}100%{{opacity:0}}}}
.pn{{opacity:0;animation:pn {T}s linear infinite}}
@keyframes pn{{0%,50%{{opacity:0}}54%,92%{{opacity:1}}100%{{opacity:0}}}}
.scan{{animation:scan {T}s linear infinite}}
@keyframes scan{{0%,6%{{transform:translateY(0);opacity:0}}8%{{opacity:1}}62%{{transform:translateY(150px);opacity:1}}66%,100%{{transform:translateY(150px);opacity:0}}}}
.fly{{animation:fly 3s cubic-bezier(.5,0,.3,1) infinite alternate both}}
@keyframes fly{{0%,15%{{transform:none;opacity:1}}70%,100%{{transform:translateY(96px) scale(.6);opacity:0}}}}
.lid{{animation:lid 3s cubic-bezier(.5,0,.3,1) infinite alternate both}}
@keyframes lid{{0%,55%{{transform:translateY(-34px);opacity:.55}}80%,100%{{transform:none;opacity:1}}}}
.zipt{{animation:zipt 3s infinite alternate both}}
@keyframes zipt{{0%,75%{{opacity:0}}90%,100%{{opacity:1}}}}
.cell{{animation:cell {T}s cubic-bezier(.2,1.5,.4,1) infinite}}
@keyframes cell{{0%,8%{{transform:scale(0);opacity:0}}16%,90%{{transform:scale(1);opacity:1}}98%,100%{{transform:scale(0);opacity:0}}}}
.arrow{{animation:arrow 1.2s ease-in-out infinite}}
@keyframes arrow{{50%{{transform:translateX(8px)}}}}
.raw{{animation:raw {T}s ease-in-out infinite}}
@keyframes raw{{0%,15%{{opacity:1;transform:none}}35%,85%{{opacity:.28;transform:translateX(-6px)}}100%{{opacity:1;transform:none}}}}
.ren{{opacity:0;animation:ren {T}s cubic-bezier(.2,.9,.2,1) infinite}}
@keyframes ren{{0%,18%{{opacity:0;transform:translateY(10px)}}30%,86%{{opacity:1;transform:none}}96%,100%{{opacity:0}}}}
"""
    body = [f'<rect width="{W}" height="{H}" fill="none"/>']
    cards = []

    def frame(i):
        col, row = i % 3, i // 3
        return gx + col * (cw + gx), gy + row * (ch + gy)

    def shell(x, y, title, sub):
        return (f'<rect x="{x + .5}" y="{y + .5}" width="{cw - 1}" height="{ch - 1}" rx="22" fill="{BG}" stroke="{LINE}"/>'
                f'<rect x="{x + 16}" y="{y + 16}" width="{cw - 32}" height="206" rx="14" fill="{S1}"/>'
                f'<text class="s b" x="{x + 24}" y="{y + 264}" font-size="22" fill="{TEXT}">{title}</text>'
                f'<text class="s" x="{x + 24}" y="{y + 292}" font-size="14" fill="{DIM}">{sub}</text>')

    # 1 compress
    x, y = frame(0)
    sx, sy = x + cw / 2, y + 108
    cards.append(shell(x, y, "Compress images", "Pick “under 100 KB”; see quality &amp; size first"))
    cards.append(f'<g class="fb photo"><rect x="{sx - 110}" y="{sy - 68}" width="220" height="136" rx="10" fill="#2D6A8E"/>'
                 f'<circle cx="{sx + 62}" cy="{sy - 34}" r="16" fill="{AMBER}"/>'
                 f'<path d="M{sx - 110},{sy + 68} L{sx - 46},{sy - 6} L{sx},{sy + 34} L{sx + 46},{sy - 18} '
                 f'L{sx + 110},{sy + 50} L{sx + 110},{sy + 58} Q{sx + 110},{sy + 68} {sx + 100},{sy + 68} Z" fill="{ACC}"/>'
                 f'<path d="M{sx - 110},{sy + 68} L{sx - 20},{sy + 22} L{sx + 50},{sy + 68} Z" fill="#1F8A5F"/></g>')
    cards.append(f'<rect x="{x + 40}" y="{y + 198}" width="{cw - 80}" height="8" rx="4" fill="{S3}"/>'
                 f'<rect class="fb bar" x="{x + 40}" y="{y + 198}" width="{cw - 80}" height="8" rx="4" fill="{ACC}" '
                 f'style="transform-origin:left center"/>')
    for j, s in enumerate(("3.8 MB", "2.1 MB", "820 KB")):
        cards.append(f'<text class="s b sz" style="animation-delay:{j * T * .18:.2f}s" x="{x + cw - 40}" y="{y + 186}" '
                     f'font-size="16" fill="{TEXT}" text-anchor="end">{s}</text>')
    cards.append(f'<text class="s b szlast" x="{x + cw - 40}" y="{y + 186}" font-size="16" fill="{ACC}" '
                 f'text-anchor="end">96 KB</text>')
    cards.append(f'<g class="fb pill"><rect x="{x + 40}" y="{y + 168}" width="132" height="24" rx="12" fill="{ACC}"/>'
                 f'<text class="s b" x="{x + 106}" y="{y + 185}" font-size="13" fill="{ON_ACC}" text-anchor="middle">'
                 f'quality 82% ✓</text></g>')

    # 2 pdf
    x, y = frame(1)
    px, py = x + 104, y + 34
    cards.append(shell(x, y, "PDF toolkit", "Compress · Lock · Pages · Numbers · Watermark"))
    cards.append(f'<rect x="{px}" y="{py}" width="128" height="170" rx="8" fill="{PAPER}"/>')
    for j in range(7):
        cards.append(f'<rect x="{px + 16}" y="{py + 22 + j * 18}" width="{96 - (j % 3) * 18}" height="6" rx="3" '
                     f'fill="#CFCFCA"/>')
    cards.append(f'<g class="fb wm"><text class="s b" x="{px + 64}" y="{py + 96}" font-size="17" fill="rgba(200,60,60,.55)" '
                 f'text-anchor="middle" transform="rotate(-38 {px + 64} {py + 90})">CONFIDENTIAL</text></g>')
    cards.append(f'<g class="pn"><text class="s sb" x="{px + 64}" y="{py + 162}" font-size="11" fill="{INK}" '
                 f'text-anchor="middle">Page 1 of 3</text></g>')
    lx, ly = x + 262, y + 120
    cards.append(f'<g class="fb lockb"><g class="shackle"><path d="M{lx - 16},{ly} v-16 a16,16 0 0 1 32,0 v16" '
                 f'fill="none" stroke="{TEXT}" stroke-width="7" stroke-linecap="round"/></g>'
                 f'<rect x="{lx - 28}" y="{ly - 4}" width="56" height="46" rx="10" fill="{ACC}"/>'
                 f'<circle cx="{lx}" cy="{ly + 16}" r="5" fill="{ON_ACC}"/><rect x="{lx - 2}" y="{ly + 18}" width="4" '
                 f'height="10" rx="2" fill="{ON_ACC}"/>'
                 f'<text class="s b" x="{lx}" y="{ly + 66}" font-size="12" fill="{DIM}" text-anchor="middle">AES-256'
                 f'</text></g>')

    # 3 ocr
    x, y = frame(2)
    px, py = x + 84, y + 30
    cards.append(shell(x, y, "Read text (OCR)", "Pictures &amp; scans → text or searchable PDF"))
    cards.append(f'<rect x="{px}" y="{py}" width="200" height="176" rx="8" fill="{PAPER}"/>')
    words = ["Invoice 2026-114", "Northwind Traders", "2 × Coffee   9.40", "Delivery     4.00", "Total due 13.40"]
    for j, wtxt in enumerate(words):
        yy = py + 34 + j * 30
        cards.append(f'<g><path d="M{px + 18},{yy - 4} q12,-8 24,0 t24,0 t24,0 t24,0 t24,0 t24,0" fill="none" '
                     f'stroke="#8E8E88" stroke-width="5" stroke-linecap="round" class="ink{j}"/></g>'
                     f'<text class="m sb txt{j}" x="{px + 18}" y="{yy + 2}" font-size="13" fill="{INK}">{wtxt}</text>')
        css += (f".ink{j}{{animation:ink{j} {T}s linear infinite}}"
                f"@keyframes ink{j}{{0%,{8 + j * 10.5:.1f}%{{opacity:1}}{10 + j * 10.5:.1f}%,90%{{opacity:0}}96%,100%{{opacity:1}}}}"
                f".txt{j}{{opacity:0;animation:txt{j} {T}s linear infinite}}"
                f"@keyframes txt{j}{{0%,{8 + j * 10.5:.1f}%{{opacity:0}}{11 + j * 10.5:.1f}%,90%{{opacity:1}}96%,100%{{opacity:0}}}}")
    cards.append(f'<g class="scan"><rect x="{px - 8}" y="{py + 12}" width="216" height="3" rx="1.5" fill="{ACC}"/>'
                 f'<rect x="{px - 8}" y="{py - 8}" width="216" height="20" fill="rgba(52,190,132,.16)"/></g>')

    # 4 zip
    x, y = frame(3)
    bx, by = x + cw / 2, y + 168
    cards.append(shell(x, y, "Zip &amp; extract", "ZIP · 7Z · RAR · TAR · GZ · ISO"))
    for j, (lab, col) in enumerate((("JPG", "#2D6A8E"), ("PDF", "#C0503C"), ("DOCX", "#3A6FC4"))):
        fx = bx - 92 + j * 66
        cards.append(f'<g class="fly" style="animation-delay:{j * .12:.2f}s"><rect x="{fx}" y="{y + 40}" width="52" '
                     f'height="62" rx="8" fill="{PAPER}"/><rect x="{fx}" y="{y + 84}" width="52" height="18" rx="0" '
                     f'fill="{col}"/><text class="s b" x="{fx + 26}" y="{y + 98}" font-size="11" fill="#fff" '
                     f'text-anchor="middle">{lab}</text></g>')
    cards.append(f'<rect x="{bx - 74}" y="{by - 26}" width="148" height="56" rx="10" fill="{AMBER}"/>'
                 f'<rect x="{bx - 8}" y="{by - 26}" width="16" height="56" fill="#C9902F"/>'
                 f'<g class="lid">'
                 f'<rect x="{bx - 80}" y="{by - 40}" width="160" height="16" rx="6" fill="#F2C266"/></g>'
                 f'<g class="zipt"><text class="s b" x="{bx}" y="{by + 10}" font-size="16" fill="{ON_ACC}" '
                 f'text-anchor="middle">.zip</text></g>')

    # 5 data
    x, y = frame(4)
    cards.append(shell(x, y, "Data files", "CSV · TSV · JSON → Excel, JSON, CSV"))
    rows = ["id,name,price", "1,Ana,1.50", "2,Bo,007", "3,Cé,12"]
    for j, r in enumerate(rows):
        cards.append(f'<text class="m" x="{x + 32}" y="{y + 74 + j * 30}" font-size="13" fill="{TEXT if j else ACC}">'
                     f'{r}</text>')
    cards.append(f'<g class="arrow"><path d="M{x + 160},{y + 118} h22 m-8,-8 l8,8 l-8,8" fill="none" stroke="{ACC}" '
                 f'stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></g>')
    gx0, gy0 = x + 200, y + 50
    for r_i, r in enumerate(rows):
        for c_i, v in enumerate(r.split(",")):
            k = r_i * 3 + c_i
            head = r_i == 0
            cards.append(f'<g class="fb cell" style="animation-delay:{.25 + k * .07:.2f}s">'
                         f'<rect x="{gx0 + c_i * 48}" y="{gy0 + r_i * 32}" width="46" height="30" rx="4" '
                         f'fill="{ACC if head else S2}"/><text class="s {"b" if head else ""}" x="{gx0 + c_i * 48 + 23}" '
                         f'y="{gy0 + r_i * 32 + 20}" font-size="12" fill="{ON_ACC if head else TEXT}" '
                         f'text-anchor="middle">{v}</text></g>')

    # 6 markdown
    x, y = frame(5)
    cards.append(shell(x, y, "Markdown", "→ PDF · HTML · Word"))
    raw = ["# Notes", "- **fast** and light", "- `code` blocks", "> quotes"]
    for j, r in enumerate(raw):
        cards.append(f'<g class="raw" style="animation-delay:{j * .1:.2f}s"><text class="m" x="{x + 32}" '
                     f'y="{y + 66 + j * 34}" font-size="13" fill="{DIM}">{r}</text></g>')
    rx0 = x + 180
    cards.append(f'<g class="ren"><rect x="{rx0}" y="{y + 32}" width="160" height="176" rx="8" fill="{PAPER}"/>'
                 f'<text class="s b" x="{rx0 + 14}" y="{y + 64}" font-size="22" fill="{INK}">Notes</text>'
                 f'<circle cx="{rx0 + 18}" cy="{y + 89}" r="3" fill="{INK}"/><text class="s" x="{rx0 + 28}" y="{y + 94}" '
                 f'font-size="13" fill="{INK}"><tspan font-weight="700">fast</tspan> and light</text>'
                 f'<circle cx="{rx0 + 18}" cy="{y + 117}" r="3" fill="{INK}"/><rect x="{rx0 + 27}" y="{y + 108}" '
                 f'width="40" height="18" rx="4" fill="#E2E2DD"/><text class="m" x="{rx0 + 31}" y="{y + 121}" '
                 f'font-size="12" fill="#B4442E">code</text><text class="s" x="{rx0 + 72}" y="{y + 122}" font-size="13" '
                 f'fill="{INK}">blocks</text><rect x="{rx0 + 14}" y="{y + 140}" width="4" height="26" fill="{ACC}"/>'
                 f'<text class="s" x="{rx0 + 26}" y="{y + 158}" font-size="13" font-style="italic" fill="#55555C">'
                 f'quotes</text></g>')
    body += cards
    return svg(W, H, "\n".join(body), css, "Everyday tools: compress images, PDF toolkit, OCR, zip, data files, Markdown")


# ======================================================================= marquee

def marquee() -> str:
    W, H = 1200, 150
    rows = [
        ["JPG", "PNG", "WEBP", "HEIC", "AVIF", "GIF", "TIFF", "BMP", "ICO", "TGA", "PSD", "SVG", "RAW", "PDF", "DOCX",
         "DOC", "ODT", "RTF"],
        ["XLSX", "XLS", "ODS", "CSV", "TSV", "JSON", "PPTX", "PPT", "ODP", "MD", "HTML", "TXT", "ZIP", "7Z", "RAR",
         "TAR", "GZ", "ISO"],
    ]
    css = """
.mq0{animation:mq0 36s linear infinite} .mq1{animation:mq1 40s linear infinite}
"""
    body = [card(W, H, 22)]
    body.append(f'<defs><linearGradient id="fade" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
                f'<stop offset=".08" stop-color="#fff"/><stop offset=".92" stop-color="#fff"/>'
                f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
                f'<mask id="mfade"><rect width="{W}" height="{H}" fill="url(#fade)"/></mask></defs>')
    groups = []
    for r_i, row in enumerate(rows):
        x = 0.0
        chips = []
        for k, f in enumerate(row):
            w = chip_w(f, 16, 16)
            accent = (k + r_i) % 5 == 0
            chips.append(f'<rect x="{x:.1f}" y="0" width="{w:.1f}" height="40" rx="20" fill="{ACC if accent else S1}" '
                         f'stroke="{ACC if accent else S3}"/><text class="m b" x="{x + w / 2:.1f}" y="26" '
                         f'font-size="16" fill="{ON_ACC if accent else TEXT}" text-anchor="middle">{f}</text>')
            x += w + 14
        span = x
        one = "".join(chips)
        y = 22 + r_i * 58
        direction = f"@keyframes mq{r_i}{{from{{transform:translateX({0 if r_i == 0 else -span:.1f}px)}}" \
                    f"to{{transform:translateX({-span if r_i == 0 else 0:.1f}px)}}}}"
        css += direction
        groups.append(f'<g transform="translate(0,{y})"><g class="mq{r_i}">{one}<g transform="translate({span:.1f},0)">'
                      f'{one}</g><g transform="translate({2 * span:.1f},0)">{one}</g></g></g>')
    body.append(f'<g mask="url(#mfade)">{"".join(groups)}</g>')
    return svg(W, H, "\n".join(body), css, "Supported formats")


# ======================================================================= safety

def safety() -> str:
    W, H = 1200, 330
    T = 7
    nodes = [(200, "Work copy", "built in a private folder"), (600, "Verify", "re-opened and compared"),
             (1000, "Commit", "moved next to the original")]
    cy = 120
    css = f"""
.pk{{animation:pk {T}s cubic-bezier(.6,0,.4,1) infinite}}
@keyframes pk{{0%{{transform:translateX(0);opacity:0}}4%{{opacity:1}}22%{{transform:translateX(0)}}34%{{transform:translateX(400px)}}62%{{transform:translateX(400px)}}74%{{transform:translateX(800px)}}94%{{transform:translateX(800px);opacity:1}}100%{{transform:translateX(800px);opacity:0}}}}
.pkok{{animation:pkok {T}s infinite}}
@keyframes pkok{{0%,70%{{fill:{S2}}}74%,100%{{fill:{ACC}}}}}
.pktx{{animation:pktx {T}s infinite}}
@keyframes pktx{{0%,70%{{fill:{TEXT}}}74%,100%{{fill:{ON_ACC}}}}}
.beam{{opacity:0;animation:beam {T}s linear infinite}}
@keyframes beam{{0%,36%{{opacity:0;transform:translateY(-36px)}}38%{{opacity:1}}58%{{opacity:1;transform:translateY(36px)}}60%,100%{{opacity:0;transform:translateY(36px)}}}}
.chk{{opacity:0;animation:chk {T}s linear infinite}}
@keyframes chk{{0%{{opacity:0}}1%,21%{{opacity:1}}24%,100%{{opacity:0}}}}
.pipe{{animation:pipe 1s linear infinite}}
@keyframes pipe{{to{{stroke-dashoffset:-20}}}}
.nring{{animation:nring {T}s linear infinite}}
@keyframes nring{{0%{{stroke:{S3}}}3%,30%{{stroke:{ACC}}}34%,100%{{stroke:{S3}}}}}
"""
    body = [card(W, H)]
    for a, b in zip(nodes, nodes[1:]):
        body.append(f'<line class="pipe" x1="{a[0] + 90}" y1="{cy}" x2="{b[0] - 90}" y2="{cy}" stroke="{S3}" '
                    f'stroke-width="4" stroke-dasharray="10 10"/>')
    checks = ["pixels", "pages", "words", "cells"]
    for i, (x, title, sub) in enumerate(nodes):
        d = f"animation-delay:{i * T * .32:.2f}s"
        body.append(f'<rect class="nring" style="{d}" x="{x - 90}" y="{cy - 60}" width="180" height="120" rx="20" '
                    f'fill="{S1}" stroke="{S3}" stroke-width="3"/>')
        body.append(f'<text class="s b" x="{x}" y="{cy + 104}" font-size="22" fill="{TEXT}" text-anchor="middle">'
                    f'{i + 1} · {title}</text><text class="s" x="{x}" y="{cy + 130}" font-size="15" fill="{DIM}" '
                    f'text-anchor="middle">{sub}</text>')
    # verify: what gets compared, cycling
    for j, c in enumerate(checks):
        body.append(f'<g class="chk" style="animation-delay:{T * .36 + j * T * .06:.2f}s">'
                    f'<text class="s sb" x="600" y="{cy + 48}" font-size="14" fill="{ACC}" text-anchor="middle">'
                    f'✓ same {c}</text></g>')
    body.append(f'<g class="beam"><rect x="530" y="{cy - 2}" width="140" height="4" rx="2" fill="{ACC}"/></g>')
    body.append(f'<text class="s" x="1000" y="{cy + 48}" font-size="13" fill="{DIM}" text-anchor="middle">never overwrites'
                f'</text><text class="s" x="200" y="{cy + 48}" font-size="13" fill="{DIM}" text-anchor="middle">'
                f'original untouched</text>')
    body.append(f'<g class="pk"><rect class="pkok" x="146" y="{cy - 36}" width="108" height="34" rx="17" fill="{S2}"/>'
                f'<text class="m sb pktx" x="200" y="{cy - 14}" font-size="13" fill="{TEXT}" text-anchor="middle">'
                f'photo.webp</text></g>')
    return svg(W, H, "\n".join(body), css, "Safety: built in a private folder, verified, then saved next to the original")


# ======================================================================= cpu

def cpu() -> str:
    W, H = 1200, 230
    gx0, gx1, gy0, gy1 = 60, 1140, 40, 190
    cap_y = gy1 - (gy1 - gy0) * .25 / .6  # 0..60% scale
    import random

    random.seed(7)
    pts = []
    span = 1080
    n = 90
    for i in range(n + 1):
        t = i / n
        busy = 0.35 < (t * 3) % 1 < 0.8
        v = (random.uniform(.18, .245) if busy else random.uniform(0, .015))
        pts.append((gx0 + t * span, gy1 - (gy1 - gy0) * v / .6))
    pts[-1] = (pts[-1][0], pts[0][1])
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{gx0},{gy1} " + line + f" {gx0 + span},{gy1}"
    css = """
.graph{animation:graph 12s linear infinite}
@keyframes graph{to{transform:translateX(-1080px)}}
.capl{animation:capl 2s ease-in-out infinite}
@keyframes capl{50%{opacity:.45}}
"""
    body = [card(W, H, 22)]
    body.append(f'<defs><clipPath id="gc"><rect x="{gx0}" y="{gy0 - 10}" width="{gx1 - gx0}" height="{gy1 - gy0 + 12}"/>'
                f'</clipPath></defs>')
    for k in range(4):
        yy = gy1 - (gy1 - gy0) * k / 3
        body.append(f'<line x1="{gx0}" x2="{gx1}" y1="{yy:.1f}" y2="{yy:.1f}" stroke="{LINE}"/>')
    graph = (f'<polygon points="{area}" fill="rgba(52,190,132,.14)"/><polyline points="{line}" fill="none" '
             f'stroke="{ACC}" stroke-width="2.5" stroke-linejoin="round"/>')
    body.append(f'<g clip-path="url(#gc)"><g class="graph">{graph}<g transform="translate({span},0)">{graph}</g></g></g>')
    body.append(f'<g class="capl"><line x1="{gx0}" x2="{gx1}" y1="{cap_y:.1f}" y2="{cap_y:.1f}" stroke="{AMBER}" '
                f'stroke-width="2" stroke-dasharray="8 8"/></g>')
    body.append(f'<rect x="{gx1 - 238}" y="{cap_y - 34:.1f}" width="232" height="26" rx="13" fill="{S1}" stroke="{S3}"/>'
                f'<text class="s sb" x="{gx1 - 122}" y="{cap_y - 16:.1f}" font-size="13" fill="{AMBER}" '
                f'text-anchor="middle">25% CPU cap, enforced by Windows</text>')
    body.append(f'<text class="s b" x="{gx0}" y="28" font-size="15" fill="{TEXT}">CPU while converting</text>'
                f'<text class="s" x="{gx0 + 186}" y="28" font-size="14" fill="{DIM}">idle: 0% · converting: stays under '
                f'the cap you choose (15, 25 or 50%)</text>')
    return svg(W, H, "\n".join(body), css, "CPU use stays under a hard cap")


# ======================================================================= divider & footer

def divider() -> str:
    W, H = 1200, 28
    css = """
.comet{animation:comet 3.2s cubic-bezier(.5,0,.5,1) infinite}
@keyframes comet{from{transform:translateX(-220px)}to{transform:translateX(1220px)}}
"""
    body = (f'<defs><linearGradient id="cg" x1="0" x2="1"><stop offset="0" stop-color="{ACC}" stop-opacity="0"/>'
            f'<stop offset="1" stop-color="{ACC}"/></linearGradient></defs>'
            f'<rect x="0" y="13" width="{W}" height="2" rx="1" fill="{S3}"/>'
            f'<g class="comet"><rect x="0" y="12" width="200" height="4" rx="2" fill="url(#cg)"/>'
            f'<circle cx="200" cy="14" r="5" fill="{ACC}"/></g>')
    return svg(W, H, body, css, "")


def footer() -> str:
    W, H = 1200, 220
    css = """
.wv{animation:wv 2.4s cubic-bezier(.4,0,.2,1) infinite}
@keyframes wv{0%,60%,100%{transform:none}20%{transform:translateY(-16px)}40%{transform:translateY(3px)}}
"""
    body = [card(W, H)]
    words = [("Tap.", TEXT, 420), ("Pick.", TEXT, 600), ("Done.", ACC, 786)]
    for i, (w, c, x) in enumerate(words):
        body.append(f'<g class="wv" style="animation-delay:{i * .18:.2f}s"><text class="s b" x="{x}" y="122" '
                    f'font-size="64" fill="{c}" text-anchor="middle" letter-spacing="-1.5">{w}</text></g>')
    body.append(f'<text class="s" x="600" y="170" font-size="17" fill="{DIM}" text-anchor="middle">Free and open source '
                f'· made for Windows 10 and 11 · no account, no uploads</text>')
    return svg(W, H, "\n".join(body), css, "Tap. Pick. Done.")


def main() -> None:
    files = {
        "hero.svg": hero(), "ticker.svg": ticker(), "flow.svg": flow(), "tools.svg": tools(),
        "formats.svg": marquee(), "safety.svg": safety(), "cpu.svg": cpu(), "divider.svg": divider(),
        "footer.svg": footer(),
    }
    for name, text in files.items():
        (OUT / name).write_text(text, encoding="utf-8", newline="\n")
        print(f"{name}: {len(text.encode()) / 1024:.1f} KB")


if __name__ == "__main__":
    main()
