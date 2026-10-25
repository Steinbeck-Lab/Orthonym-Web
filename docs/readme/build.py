"""Draw the README's pictures in Orthonym's own world.

The bench (pink wash settling into cool grey under a dot grid), white 22px
cards, the site's three faces, the ring lamps with their neon glow, and
crimson only on the primary action and the header's reading light -- DESIGN.md's
rules, drawn as SVG because a GitHub README carries no CSS of its own.

Every picture is generated, not hand-edited, so a change to the product is a
re-run, not a redraw. The structures are real RDKit drawings of caffeine; the
name and the InChIKey are the app's own output for it.

    cd backend && .venv/bin/python ../docs/readme/build.py

(any interpreter with RDKit works; the backend's venv has it). The About
page's painted cross is computed by `node`, from BrushCross.jsx itself.
"""
import base64
import json
import pathlib
import re
import subprocess

from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
FONTS = REPO / "frontend/public/fonts"


def b64(path):
    return base64.b64encode(pathlib.Path(path).read_bytes()).decode()


# The Latin subsets the site preloads (frontend/src/fonts.css). Each picture
# embeds only the faces it sets: an SVG loaded as an <img> can fetch nothing.
FACES = {
    "disp": ("Saira Condensed", "", "saira-condensed-3.woff2"),
    "body": ("Public Sans", "font-weight:400;", "public-sans-3.woff2"),
    "bold": ("Public Sans", "font-weight:600;", "public-sans-b3.woff2"),
    "ital": ("Public Sans", "font-style:italic;", "public-sans-i3.woff2"),
    "mono": ("JetBrains Mono", "", "jetbrains-mono-6.woff2"),
}
CLASSES = """
.disp{font-family:'Saira Condensed','Arial Narrow',sans-serif;}
.body{font-family:'Public Sans','Helvetica Neue',Arial,sans-serif;}
.mono{font-family:'JetBrains Mono',ui-monospace,Menlo,monospace;}
.bold{font-family:'Public Sans','Helvetica Neue',Arial,sans-serif;font-weight:600;}
"""


def font_css(*faces):
    out = ""
    for f in faces:
        fam, extra, file = FACES[f]
        out += f"@font-face{{font-family:'{fam}';{extra}src:url(data:font/woff2;base64,{b64(FONTS / file)}) format('woff2');}}"
    return out + CLASSES


INK, BODY, MUTED, HAIR = "#000000", "#1a1a1a", "#666666", "#d9d9d9"
CRIMSON, CRIMSON_DEEP = "#c41e3a", "#9d1830"
SUCCESS = "#2f6b28"

# key, short label, lines under it, mark colour (deep, AA on white), glow
# colour (neon), glow strength -- index.css tokens and TierLamp's strengths.
TIERS = [
    ("pin", "PIN", "Verified, and the|preferred name.", "#2f6b28", "#3dff8f", 1.0),
    ("fallback", "FALLBACK", "Verified; preferred|status not certified.", "#556b2f", "#b6f24a", 0.8),
    ("best_effort", "BEST EFFORT", "From the general|engine; verdict below.", "#9c4109", "#ffb02e", 0.62),
    ("abstain", "NO NAME", "The engine declined|rather than guess.", "#666666", "#666666", 0.0),
    ("error", "ERROR", "The input could|not be named.", "#a3231a", "#ff4560", 0.4),
]

# Caffeine, as the app names it (a verified PIN) and as RDKit keys it.
CAF = "CN1C=NC2=C1C(=O)N(C(=O)N2C)C"
NAME = ("1,3,7-trimethyl-3,7-dihydro-", "1<tspan class='body' font-style='italic'>H</tspan>-purine-2,6-dione")
KEY = "RYYVLZVUVIJVGH-UHFFFAOYSA-N"

REDUCED = "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"


def lines(x, y, text, size, fill, lh=1.4, cls="body", anchor="start"):
    return "".join(
        f'<text class="{cls}" x="{x}" y="{y + i * size * lh:.1f}" font-size="{size}" fill="{fill}" text-anchor="{anchor}">{t}</text>'
        for i, t in enumerate(text.split("|"))
    )


def bench(uid, w, h, rx):
    return f"""<defs>
<linearGradient id="bench{uid}" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#f6e2e6"/><stop offset=".5" stop-color="#e6e6e9"/><stop offset="1" stop-color="#d5d8dc"/>
</linearGradient>
<radialGradient id="wash{uid}" cx=".1" cy=".02" r=".75">
  <stop offset="0" stop-color="#f2c4cd" stop-opacity=".6"/><stop offset="1" stop-color="#f2c4cd" stop-opacity="0"/>
</radialGradient>
<pattern id="dots{uid}" width="18" height="18" patternUnits="userSpaceOnUse">
  <circle cx="9" cy="9" r="1.05" fill="#1b1c20" fill-opacity=".09"/>
</pattern></defs>
<rect width="{w}" height="{h}" rx="{rx}" fill="url(#bench{uid})"/>
<rect width="{w}" height="{h}" rx="{rx}" fill="url(#wash{uid})"/>
<rect width="{w}" height="{h}" rx="{rx}" fill="url(#dots{uid})"/>"""


def lamp(tier, x, y, size, lit=True, uid="", glow_cls="", mark_cls=""):
    """One TierLamp: the 18-unit mark from TierLamp.jsx, its glow behind it."""
    key, _, _, mark, neon, strength = next(t for t in TIERS if t[0] == tier)
    s = size / 18
    glow = ""
    if lit and strength:
        glow = (f'<defs><radialGradient id="g{key}{uid}"><stop offset="0" stop-color="{neon}" stop-opacity=".88"/>'
                f'<stop offset=".3" stop-color="{neon}" stop-opacity=".4"/><stop offset=".64" stop-color="{neon}" stop-opacity="0"/></radialGradient></defs>'
                f'<circle class="{glow_cls}" cx="9" cy="9" r="16" fill="url(#g{key}{uid})" opacity="{strength}"/>')
    ring = f'fill="none" stroke="{mark}"'
    body = {
        "pin": f'<circle {ring} cx="9" cy="9" r="8" stroke-width="1.25"/><circle {ring} cx="9" cy="9" r="5.5" stroke-width="1.25"/><circle cx="9" cy="9" r="3" fill="{mark}"/>',
        "fallback": f'<circle {ring} cx="9" cy="9" r="7" stroke-width="1.75" stroke-dasharray="3.23 2.27"/><circle cx="9" cy="9" r="3" fill="{mark}"/>',
        "best_effort": f'<circle {ring} cx="9" cy="9" r="7" stroke-width="1.75" stroke-dasharray="1.1 3.3"/>',
        "abstain": f'<circle {ring} cx="9" cy="9" r="7" stroke-width="1"/>',
        "error": f'<circle {ring} cx="9" cy="9" r="7" stroke-width="1"/><line {ring} x1="3.4" y1="14.6" x2="14.6" y2="3.4" stroke-width="1.25"/>',
    }[key]
    return f'<g transform="translate({x - size / 2:.1f},{y - size / 2:.1f}) scale({s:.3f})"><g class="{mark_cls}">{glow}{body}</g></g>'


def rule(tier, x, y, w):
    """The rule a name wears under it: DESIGN.md's confidence grammar."""
    if tier == "pin":
        return (f'<line x1="{x}" y1="{y + .5}" x2="{x + w}" y2="{y + .5}" stroke="{INK}" stroke-width="2"/>'
                f'<line x1="{x}" y1="{y + 7.5}" x2="{x + w}" y2="{y + 7.5}" stroke="{INK}" stroke-width="2"/>')
    if tier == "fallback":
        return f'<line x1="{x}" y1="{y + 4}" x2="{x + w}" y2="{y + 4}" stroke="{INK}" stroke-width="2" stroke-dasharray="13 9"/>'
    if tier == "best_effort":
        return f'<line x1="{x}" y1="{y + 4}" x2="{x + w}" y2="{y + 4}" stroke="{MUTED}" stroke-width="2.6" stroke-dasharray="2.5 8" stroke-linecap="round"/>'
    if tier == "abstain":
        return f'<line x1="{x}" y1="{y + 4}" x2="{x + w}" y2="{y + 4}" stroke="{HAIR}" stroke-width="1.6"/>'
    return (f'<line x1="{x}" y1="{y}" x2="{x + w}" y2="{y}" stroke="{INK}" stroke-width="1.6"/>'
            f'<line x1="{x}" y1="{y + 7}" x2="{x + w}" y2="{y + 7}" stroke="{INK}" stroke-width="1.6"/>')


def depiction(smiles, w, h, x, y, font=20):
    """A real RDKit drawing in ink, as a nested <svg> at (x, y)."""
    d = rdMolDraw2D.MolDraw2DSVG(w, h)
    o = d.drawOptions()
    o.clearBackground = False
    o.useBWAtomPalette()
    o.bondLineWidth = 2
    o.fixedFontSize = font
    o.padding = 0.06
    d.DrawMolecule(Chem.MolFromSmiles(smiles))
    d.FinishDrawing()
    svg = re.sub(r"<\?xml[^>]*>", "", d.GetDrawingText())
    svg = re.sub(r"<rect[^>]*/>", "", svg, count=1)
    return svg.replace("<svg ", f"<svg x='{x}' y='{y}' overflow='visible' ", 1)


def arrow(d, head, cls):
    return (f'<path class="draw {cls}" pathLength="1" d="{d}" fill="none" stroke="{INK}" stroke-width="2" stroke-linecap="round"/>'
            f'<path class="rise {cls}h" d="{head}" fill="none" stroke="{INK}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>')


def write(name, w, h, inner, css, pad=0):
    """`pad` adds transparent room under the drawing: GitHub puts a README image
    flush against whatever follows it, and markdown cannot add a margin."""
    h += pad
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
           f'<style>{css}</style>{inner}</svg>')
    (HERE / name).write_text(svg)
    print(f"{name}: {len(svg) // 1024} KB")


# One motion grammar for every picture: things arrive from an already-legible
# default (the reduced-motion rule simply removes the animation), lines draw
# themselves, and a verified PIN lamp breathes three times, as it does on the
# site when a result resolves (App.css tier-lamp-breath).
MOTION = """
.rise{animation:rise .7s cubic-bezier(.16,1,.3,1) both;}
.draw{stroke-dasharray:1;animation:draw .7s cubic-bezier(.65,0,.35,1) both;}
.breath{animation:breath .66s cubic-bezier(.37,0,.63,1) 3 both;}
@keyframes rise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
@keyframes draw{from{stroke-dashoffset:1}to{stroke-dashoffset:0}}
@keyframes breath{0%,100%{opacity:1}50%{opacity:.42}}
"""


# ------------------------------------------------------------------ banner
BANNER_CSS = """
.reader{transform:translateX(var(--rest));animation:read 14s linear infinite;}
@keyframes read{
  0%{transform:translateX(var(--from));opacity:0}
  12%{opacity:1}
  70%{opacity:1}
  82%{transform:translateX(var(--to));opacity:0}
  100%{transform:translateX(var(--to));opacity:0}
}
.on{animation:on .5s cubic-bezier(.16,1,.3,1) both;}
.on0{animation-delay:.6s}.on1{animation-delay:.8s}.on2{animation-delay:1s}.on3{animation-delay:1.2s}.on4{animation-delay:1.4s}
.breath{animation-delay:1.9s}
@keyframes on{from{opacity:.15;transform:scale(.7)}to{opacity:1;transform:none}}
"""


def reading_light(cy, w, h, rx, ry):
    """The header's one authored moment: a reading light. A soft crimson glow
    travels left to right behind the wordmark, the way the app reads every
    name back, and the bench's dots light up crimson as it passes over them,
    then settle. One unhurried pass, a pause, again.

    The glow is multiplied onto the bench (crimson light has to darken paper
    or it vanishes -- DESIGN.md, Home hero). The lit dots sit on the bench's
    own 18-unit grid, revealed through a mask that rides with the glow, so
    they cannot drift off the dots they light.

    Reduced motion removes the animation and leaves the light at rest behind
    the wordmark's centre: a still glow, not an empty header.
    """
    glow = f'<ellipse cx="0" cy="{cy}" rx="{rx}" ry="{ry}"'
    # Steady, like reading: linear travel, softened only by the fades at
    # either edge, so the light crosses the wordmark at one even pace.
    travel = f"--rest:{w / 2:.0f}px;--from:{-rx * .3:.0f}px;--to:{w + rx * .3:.0f}px"
    return f"""<defs>
  <radialGradient id="light"><stop offset="0" stop-color="{CRIMSON}" stop-opacity=".26"/><stop offset=".5" stop-color="{CRIMSON}" stop-opacity=".08"/><stop offset="1" stop-color="{CRIMSON}" stop-opacity="0"/></radialGradient>
  <radialGradient id="lightmask"><stop offset="0" stop-color="#fff"/><stop offset=".35" stop-color="#fff" stop-opacity=".7"/><stop offset=".75" stop-color="#fff" stop-opacity="0"/></radialGradient>
  <pattern id="litdots" width="18" height="18" patternUnits="userSpaceOnUse"><circle cx="9" cy="9" r="1.5" fill="{CRIMSON}" fill-opacity=".6"/></pattern>
  <mask id="reading" maskUnits="userSpaceOnUse" x="0" y="0" width="{w}" height="{h}"><g class="reader" style="{travel}">{glow} fill="url(#lightmask)"/></g></mask>
  <clipPath id="card"><rect width="{w}" height="{h}" rx="36"/></clipPath>
</defs>
<g clip-path="url(#card)" style="mix-blend-mode:multiply">
  <g class="reader" style="{travel}">{glow} fill="url(#light)"/></g>
  <rect width="{w}" height="{h}" fill="url(#litdots)" mask="url(#reading)"/>
</g>"""


def banner_lamps(x0, step, y, size):
    return "".join(
        lamp(t[0], x0 + i * step, y, size, uid="b", mark_cls=f"on on{i}", glow_cls="breath" if t[0] == "pin" else "")
        for i, t in enumerate(TIERS)
    )


def product_line(cx, y, size, spacing, rule, text="WEB", fill=INK, hair="#c5c5c5"):
    """Spaced mono caps between two hairlines. Under the wordmark it says
    "WEB": this repository is Orthonym Web, the app, not the engine, and the
    hairlines make it read as part of the product's name rather than as a
    second tagline. The footer's collaboration line uses the same setting.

    JetBrains Mono advances .6em per glyph, so the width is known without
    measuring. The text sits half a letter-space right: SVG spacing trails the
    last letter too, which would pull it off the centre the hairlines share."""
    half = (len(text) * size * .6 + (len(text) - 1) * spacing) / 2 + size * .6
    ly = f"{y - size * .36:.1f}"
    return (f'<text class="mono" x="{cx + spacing / 2}" y="{y}" text-anchor="middle" font-size="{size}" letter-spacing="{spacing}" fill="{fill}">{text}</text>'
            f'<line x1="{cx - half - rule:.1f}" y1="{ly}" x2="{cx - half:.1f}" y2="{ly}" stroke="{hair}" stroke-width="1.6"/>'
            f'<line x1="{cx + half:.1f}" y1="{ly}" x2="{cx + half + rule:.1f}" y2="{ly}" stroke="{hair}" stroke-width="1.6"/>')


def banner_narrow():
    """The banner for a phone-width README: bigger tagline and lamps, no
    sub-line (it cannot be read at a third of its size)."""
    w, h = 800, 680
    wordmark = b64(REPO / "frontend/public/logos/ORTHONYM.png")
    css = font_css("body", "mono") + MOTION + BANNER_CSS + REDUCED
    write("banner-narrow.svg", w, h, f"""
{bench('bn', w, h, 36)}
{reading_light(170, w, h, 300, 200)}
<image href="data:image/png;base64,{wordmark}" x="60" y="92" width="680" height="150"/>
{product_line(400, 312, 40, 20, 90)}
<text class="body" x="400" y="412" text-anchor="middle" font-size="46" fill="{BODY}">Verified IUPAC names</text>
<text class="body" x="400" y="474" text-anchor="middle" font-size="46" fill="{BODY}">for Chemical Structures</text>
{banner_lamps(240, 80, 584, 40)}
""", css, pad=40)


def banner():
    w, h = 1600, 600
    wordmark = b64(REPO / "frontend/public/logos/ORTHONYM.png")
    css = font_css("body", "mono") + MOTION + BANNER_CSS + REDUCED
    write("banner.svg", w, h, f"""
{bench('b', w, h, 36)}
{reading_light(196, w, h, 420, 240)}
<image href="data:image/png;base64,{wordmark}" x="360" y="100" width="880" height="194"/>
{product_line(800, 360, 32, 16, 110)}
<text class="body" x="800" y="428" text-anchor="middle" font-size="37" fill="{BODY}">Verified IUPAC names for Chemical Structures</text>
<text class="mono" x="800" y="484" text-anchor="middle" font-size="21" letter-spacing="4" fill="{MUTED}">DETERMINISTIC  ·  RULE-BASED  ·  EVERY NAME READ BACK BY OPSIN</text>
{banner_lamps(704, 48, 544, 22)}
""", css, pad=44)


# ------------------------------------------------------------------ buttons
def pill(name, label, w, primary):
    h = 96
    if primary:
        face = (f'<defs><linearGradient id="c" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#d63553"/>'
                f'<stop offset="1" stop-color="{CRIMSON_DEEP}"/></linearGradient>'
                f'<linearGradient id="gl" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".42"/>'
                f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>'
                f'<rect x="2" y="4" width="{w - 4}" height="{h - 8}" rx="44" fill="url(#c)"/>'
                f'<rect x="10" y="9" width="{w - 20}" height="34" rx="17" fill="url(#gl)"/>')
        color, tx = "#ffffff", (w - 40) / 2
        arrow_ = (f'<path d="M{w - 78} 60 L{w - 60} 42 M{w - 72} 42 L{w - 60} 42 L{w - 60} 54" fill="none" '
                  f'stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>')
    else:
        face = f'<rect x="3" y="5" width="{w - 6}" height="{h - 10}" rx="43" fill="#ffffff" stroke="#c5c5c5" stroke-width="2"/>'
        color, tx, arrow_ = INK, w / 2, ""
    write(name, w, h, f'{face}<text class="mono" x="{tx}" y="59" text-anchor="middle" font-size="25" '
                      f'letter-spacing="5" fill="{color}">{label}</text>{arrow_}', font_css("mono"))


# ------------------------------------------------------------------ the round trip
def tier_row(x0, y, col, width, delay0):
    out = ""
    for i, (key, short, text, *_rest) in enumerate(TIERS):
        x = x0 + i * col
        lit = key == "pin"
        out += f"""<g class="rise" style="animation-delay:{delay0 + i * .1:.1f}s">
  {lamp(key, x + 20, y, 36, lit=lit, uid='rt', glow_cls='breath' if lit else '')}
  <text class="mono" x="{x + 54}" y="{y + 9}" font-size="22" letter-spacing="3" fill="{INK if lit else MUTED}">{short}</text>
  {rule(key, x, y + 40, width)}
  {lines(x, y + 100, text, 23, BODY if lit else MUTED)}
</g>"""
    return out


def roundtrip():
    """The loop, clockwise: your structure, the name, OPSIN's structure, the
    verdict, and back to where you started."""
    w, h = 1600, 1140
    css = font_css("body", "bold", "ital", "mono") + MOTION + """
.a1{animation-delay:.1s}.a2{animation-delay:.8s}.a3{animation-delay:1.6s}.a4{animation-delay:2.4s}
.d1{animation-delay:.5s}.d1h{animation-delay:1.1s}.d2{animation-delay:1.3s}.d2h{animation-delay:1.9s}
.d3{animation-delay:2.1s}.d3h{animation-delay:2.7s}.d4{animation-delay:2.9s}.d4h{animation-delay:3.5s}
.band{animation-delay:3.6s}
.breath{animation-delay:3.9s}
""" + REDUCED
    label = lambda x, y, t, d: f'<text class="bold rise {d}" x="{x}" y="{y}" font-size="26" fill="{INK}">{t}</text>'
    write("roundtrip.svg", w, h, f"""
<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="30" fill="#ffffff" stroke="#e2e4e8" stroke-width="2"/>
{label(80, 92, 'Your structure', 'a1')}
<g class="rise a1">{depiction(CAF, 340, 260, 70, 118)}
  <text class="mono" x="80" y="416" font-size="21" fill="{MUTED}">{CAF}</text></g>
{label(620, 92, 'The Orthonym engine writes a name', 'a2')}
<g class="rise a2">
  <text class="body" x="620" y="212" font-size="46" fill="{INK}">{NAME[0]}</text>
  <text class="body" x="620" y="272" font-size="46" fill="{INK}">{NAME[1]}</text>
  <text class="mono" x="620" y="336" font-size="21" fill="{MUTED}">deterministic · rule-based · no sampling</text>
</g>
{label(1010, 520, 'OPSIN reads the name back', 'a3')}
<g class="rise a3">{depiction(CAF, 330, 250, 1000, 548)}</g>
{label(80, 520, 'Verdict', 'a4')}
<g class="rise a4">
  <text class="body" x="80" y="580" font-size="22" fill="{MUTED}">InChIKey of your structure</text>
  <text class="mono" x="80" y="614" font-size="23" fill="{INK}">{KEY}</text>
  <text class="body" x="80" y="664" font-size="22" fill="{MUTED}">InChIKey of what OPSIN read</text>
  <text class="mono" x="80" y="698" font-size="23" fill="{INK}">{KEY}</text>
  {lamp('pin', 98, 758, 36, uid='v', glow_cls='breath')}
  <text class="bold" x="132" y="767" font-size="26" fill="{SUCCESS}">Same molecule: a verified PIN</text>
</g>
{arrow('M430 250 L590 250', 'M578 240 L590 250 L578 260', 'd1')}
{arrow('M1180 370 L1180 470', 'M1170 458 L1180 470 L1190 458', 'd2')}
{arrow('M980 690 L720 690', 'M732 680 L720 690 L732 700', 'd3')}
{arrow('M240 480 L240 440', 'M230 452 L240 440 L250 452', 'd4')}
<g class="rise band">
  <line x1="80" y1="846" x2="{w - 80}" y2="846" stroke="{HAIR}" stroke-width="1.6"/>
  <text class="body" x="80" y="900" font-size="24" fill="{MUTED}">Every verdict lands on one of five tiers, and the tier is drawn under the name wherever it appears.</text>
</g>
{tier_row(80, 960, 294, 250, 3.8)}
""", css, pad=48)


def roundtrip_narrow():
    """The same loop for a phone-width README: one column, top to bottom."""
    w, h = 800, 2240
    css = font_css("body", "bold", "ital", "mono") + MOTION + """
.a1{animation-delay:.1s}.a2{animation-delay:.7s}.a3{animation-delay:1.3s}.a4{animation-delay:1.9s}
.d1{animation-delay:.4s}.d1h{animation-delay:.9s}.d2{animation-delay:1s}.d2h{animation-delay:1.5s}
.d3{animation-delay:1.6s}.d3h{animation-delay:2.1s}
.breath{animation-delay:2.6s}
""" + REDUCED
    rows = ""
    for i, (key, short, text, *_r) in enumerate(TIERS):
        y = 1672 + i * 110
        lit = key == "pin"
        rows += f"""<g class="rise" style="animation-delay:{2.3 + i * .1:.1f}s">
  {lamp(key, 76, y, 40, lit=lit, uid='n', glow_cls='breath' if lit else '')}
  <text class="mono" x="116" y="{y + 10}" font-size="30" letter-spacing="3" fill="{INK if lit else MUTED}">{short}</text>
  {lines(116, y + 52, text.replace('|', ' '), 28, BODY if lit else MUTED)}
</g>"""
    write("roundtrip-narrow.svg", w, h, f"""
<rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="30" fill="#ffffff" stroke="#e2e4e8" stroke-width="2"/>
<text class="bold rise a1" x="56" y="84" font-size="34" fill="{INK}">Your structure</text>
<g class="rise a1">{depiction(CAF, 420, 300, 190, 104, font=24)}</g>
{arrow('M400 420 L400 480', 'M388 468 L400 480 L412 468', 'd1')}
<text class="bold rise a2" x="56" y="546" font-size="34" fill="{INK}">The engine writes a name</text>
<g class="rise a2">
  <text class="body" x="56" y="620" font-size="46" fill="{INK}">{NAME[0]}</text>
  <text class="body" x="56" y="680" font-size="46" fill="{INK}">{NAME[1]}</text>
</g>
{arrow('M400 712 L400 772', 'M388 760 L400 772 L412 760', 'd2')}
<text class="bold rise a3" x="56" y="838" font-size="34" fill="{INK}">OPSIN reads it back</text>
<g class="rise a3">{depiction(CAF, 400, 280, 200, 858, font=24)}</g>
{arrow('M400 1150 L400 1210', 'M388 1198 L400 1210 L412 1198', 'd3')}
<g class="rise a4">
  <text class="bold" x="56" y="1276" font-size="34" fill="{INK}">Verdict</text>
  <text class="body" x="56" y="1330" font-size="27" fill="{MUTED}">InChIKey of your structure</text>
  <text class="mono" x="56" y="1374" font-size="30" fill="{INK}">{KEY}</text>
  <text class="body" x="56" y="1432" font-size="27" fill="{MUTED}">InChIKey of what OPSIN read</text>
  <text class="mono" x="56" y="1476" font-size="30" fill="{INK}">{KEY}</text>
  {lamp('pin', 78, 1540, 40, uid='nv', glow_cls='breath')}
  <text class="bold" x="116" y="1551" font-size="32" fill="{SUCCESS}">Same molecule: a verified PIN</text>
  <line x1="56" y1="1604" x2="{w - 56}" y2="1604" stroke="{HAIR}" stroke-width="1.6"/>
</g>
{rows}
""", css, pad=40)


def cup():
    """The footer's coffee cup (Footer.jsx CoffeeMark), in the credit's crimson."""
    (HERE / "cup.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" fill="none" '
        f'stroke="{CRIMSON}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">'
        '<path d="M9 2.5c-.6.8-.6 1.6 0 2.4"/><path d="M12.5 2c-.7.9-.7 1.9 0 2.9"/><path d="M16 2.5c-.6.8-.6 1.6 0 2.4"/>'
        '<path d="M3.5 8h14v5.5a5 5 0 0 1-5 5h-4a5 5 0 0 1-5-5V8Z"/><path d="M17.5 9.5h1.6a2.4 2.4 0 0 1 0 4.8h-1.6"/></svg>')


# ------------------------------------------------------------------ partners
# The footer's partners, as the About page shows them ("Made together"): the
# two logos joined by the painted BrushCross, not a typed cross. Three pictures
# rather than one, because each logo must stay its own link, and GitHub strips
# image maps. Each logo sits on its own white card so it stays legible on
# GitHub's dark theme; the three share one height so they line up inline.
PARTNER_H = 160


def brush_strokes():
    """BrushCross.jsx's STROKES, computed by the component's own code: the
    module up to its JSX, run by node. A port to Python would be a second copy
    of a mark that must be THIS painted mark everywhere."""
    src = (REPO / "frontend/src/components/BrushCross.jsx").read_text()
    js = src[: src.index("export default function BrushCross")] + "console.log(JSON.stringify(STROKES))"
    out = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def partner(name, logo, mime, logo_w, logo_h, scale=1):
    """One partner logo, centred on a white 22px card (About.css .collab__org).
    `scale` is About.css's own correction: the Steinbeck mark carries its words
    small, so it is drawn 74/62 as tall as the Beilstein one."""
    h, pad = PARTNER_H, 34
    lh = (h - 2 * pad) * scale
    lw = lh * logo_w / logo_h
    w = round(lw + 2 * pad * .8)
    data = b64(logo)
    (HERE / name).write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
        f'<rect width="{w}" height="{h}" rx="22" fill="#fff"/>'
        f'<image href="data:{mime};base64,{data}" x="{(w - lw) / 2:.1f}" y="{(h - lh) / 2:.1f}" width="{lw:.1f}" height="{lh:.1f}"/></svg>')
    print(f"{name}: {(HERE / name).stat().st_size // 1024} KB")


def partners():
    partner("beilstein.svg", REPO / "frontend/public/Logo_Beilstein_schmal_RGB.svg", "image/svg+xml", 876, 202)
    partner("steinbeck.svg", REPO / "frontend/public/logos/steinbeck.png", "image/png", 1666, 400, scale=74 / 62)
    # About.css paints every part in --thread (the accent), bristles at .82
    # and flecks at .62. The cross's viewBox is 0-100; bristles and flecks run
    # past the ends, so the canvas gives them room.
    opacity = {"brush-x__body": 1, "brush-x__bristle": .82, "brush-x__fleck": .62}
    strokes = "".join(
        f'<g class="s{n}">' + "".join(
            f'<path d="{p["d"]}" fill="{CRIMSON}" fill-opacity="{opacity[p["cls"]]}"/>' for p in stroke
        ) + "</g>"
        for n, stroke in enumerate(brush_strokes(), 1)
    )
    # The About page repaints the cross on hover (About.css .collab:hover).
    # An <img> on GitHub gets no hover, so the same repaint plays on its own:
    # the two strokes wipe in (400 ms, the second 150 ms later) under the
    # 620 ms press, then the cross rests whole for the rest of an 8 s cycle.
    # Percentages are of that cycle: 400 ms = 5%, 620 ms = 7.75%.
    css = (
        ".x{transform-box:fill-box;transform-origin:center;animation:press 8s cubic-bezier(.16,1,.3,1) infinite}"
        ".s1{animation:right 8s cubic-bezier(.22,1,.36,1) infinite both}"
        ".s2{animation:left 8s cubic-bezier(.22,1,.36,1) .15s infinite both}"
        "@keyframes right{0%{clip-path:inset(0 100% 0 0)}5%,100%{clip-path:inset(0 -10% 0 0)}}"
        "@keyframes left{0%{clip-path:inset(0 0 0 100%)}5%,100%{clip-path:inset(0 0 0 -10%)}}"
        "@keyframes press{0%,7.75%,100%{transform:none}2.95%{transform:rotate(-3.5deg) scale(1.07)}}"
        "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
    )
    (HERE / "brush-x.svg").write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{PARTNER_H}" height="{PARTNER_H}" viewBox="-30 -30 160 160">'
        f'<style>{css}</style><g class="x">{strokes}</g></svg>')
    # The About page's line under the pair, set like the header's "WEB". On a
    # transparent ground, so it comes in two inks and README.md swaps them by
    # prefers-color-scheme: #666 on GitHub's white, #9da5b0 on its #0d1117,
    # and at phone width by a two-line pair.
    text = "AN OFFICIAL COLLABORATION FOR OPEN SCIENCE"
    size, spacing, rule = 22, 5, 70
    w = round(len(text) * (size * .6 + spacing) + 2 * (rule + size * .6) + 8)
    css = font_css("mono")
    # One line is 42 glyphs; at phone width it would shrink to ~8px, so the
    # narrow pair breaks it in two, the hairlines on the second line only.
    head, tail = "AN OFFICIAL COLLABORATION", "FOR OPEN SCIENCE"
    wn = round(len(head) * (size * .6 + spacing) + 48)
    for suffix, fill, hair in (("", MUTED, "#c5c5c5"), ("-dark", "#9da5b0", "#30363d")):
        write(f"collab-line{suffix}.svg", w, 44, product_line(w / 2, 32, size, spacing, rule, text, fill, hair), css)
        write(f"collab-line-narrow{suffix}.svg", wn, 84,
              f'<text class="mono" x="{wn / 2 + spacing / 2}" y="32" text-anchor="middle" font-size="{size}" letter-spacing="{spacing}" fill="{fill}">{head}</text>'
              + product_line(wn / 2, 72, size, spacing, 40, tail, fill, hair), css)


# ------------------------------------------------------------------ text width
# Advance widths per 1000 units, measured in Chrome from the site's own woff2
# subsets (canvas measureText). An SVG drawn for an <img> cannot measure its
# own text, and a highlight behind one part of a chemical name has to land on
# that part. Each marked run is set as its own <tspan x=...>, so the browser's
# kerning inside a run cannot drift the next run off its mark.
_PS = dict(zip(
    " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~·",
    (243, 251, 426, 603, 659, 904, 709, 248, 303, 309, 394, 555, 242, 378, 225, 351, 612, 407, 596, 630, 629,
     641, 623, 601, 648, 625, 226, 240, 546, 555, 546, 521, 831, 710, 671, 689, 694, 621, 594, 733, 766, 283,
     389, 682, 578, 886, 754, 734, 637, 748, 677, 670, 594, 701, 673, 954, 688, 607, 637, 303, 351, 303, 473,
     518, 219, 553, 597, 544, 597, 567, 396, 623, 577, 248, 263, 562, 303, 865, 577, 566, 596, 596, 391, 506,
     389, 581, 504, 780, 565, 535, 481, 328, 263, 332, 568, 230)))
_SC = dict(zip(
    " !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    (192, 209, 294, 526, 418, 636, 529, 166, 246, 246, 406, 484, 194, 309, 194, 290, 484, 274, 436, 423, 468,
     439, 476, 403, 490, 476, 194, 194, 484, 484, 484, 361, 683, 494, 492, 400, 497, 433, 408, 483, 527, 220,
     250, 481, 379, 665, 528, 518, 465, 518, 493, 443, 413, 514, 462, 691, 484, 433, 424)))
_SC.update(zip("abcdefghijklmnopqrstuvwxyz", (425, 450, 351, 450, 428, 281, 450, 453, 196, 196, 408, 196, 689, 453, 439,
                                               450, 450, 285, 377, 273, 453, 405, 612, 411, 453, 373)))


def width(text, size, face="body", spacing=0):
    if face == "mono":
        return len(text) * (size * .6 + spacing)
    table = _SC if face == "disp" else _PS
    return sum(table[c] for c in text) * size / 1000 + len(text) * spacing


def runs(x, y, parts, size, fill=INK):
    """A name set as consecutive runs [(text, kind)], each at its own x.
    kind None is plain ink; "active" wears the hovered part's glow wash and ink
    underline (Explain.css .explain-name__part--active); "differs" is /compare's
    grey fill inside a muted outline; "hidden" is classroom mode's muted dot
    per letter; "italic" is an italic H. Returns (svg, x after the last run)."""
    marks, text = "", ""
    for t, kind in parts:
        w = width(t, size, spacing=size * .08 if kind == "hidden" else 0)
        if kind == "active":
            marks += (f'<rect x="{x - 3:.1f}" y="{y - size * .86:.1f}" width="{w + 6:.1f}" height="{size * 1.12:.1f}" rx="3" fill="#fff3b8"/>'
                      f'<line x1="{x - 3:.1f}" y1="{y + size * .26:.1f}" x2="{x + w + 3:.1f}" y2="{y + size * .26:.1f}" stroke="{INK}" stroke-width="2"/>')
        if kind == "hidden":
            # Drawn, not typed: one muted dot per hidden letter, on the
            # advance the site gives it ('·' plus .08em), centred at
            # x-height, so the run reads as letters held back.
            marks += "".join(f'<circle cx="{x + (i + .5) * w / len(t):.1f}" cy="{y - size * .3:.1f}" r="{size * .08:.1f}" fill="{MUTED}"/>'
                             for i in range(len(t)))
            x += w
            continue
        if kind == "differs":
            marks += (f'<rect x="{x - 4:.1f}" y="{y - size * .84:.1f}" width="{w + 8:.1f}" height="{size * 1.1:.1f}" rx="4" '
                      f'fill="#e0e0e0" stroke="{MUTED}" stroke-width="2"/>')
        style = ' font-style="italic"' if kind == "italic" else ""
        text += f'<tspan x="{x:.1f}"{style}>{t}</tspan>'
        x += w
    return marks + f'<text class="body" y="{y}" font-size="{size}" fill="{fill}">{text}</text>', x


def lit_depiction(smiles, w, h, x, y, lights=(), font=20):
    """depiction(), with Explain's pointer glow on the atoms a part lights:
    --glow (#ffd400) discs behind those atoms, as the app draws them."""
    d = rdMolDraw2D.MolDraw2DSVG(w, h)
    o = d.drawOptions()
    o.clearBackground = False
    o.useBWAtomPalette()
    o.bondLineWidth = 2
    o.fixedFontSize = font
    o.padding = 0.1
    o.highlightRadius = .42
    o.fillHighlights = True
    o.continuousHighlight = False
    lights = list(lights)
    d.DrawMolecule(Chem.MolFromSmiles(smiles), highlightAtoms=lights,
                   highlightAtomColors={i: (1, .83, 0) for i in lights}, highlightBonds=[])
    d.FinishDrawing()
    svg = re.sub(r"<\?xml[^>]*>", "", d.GetDrawingText())
    svg = re.sub(r"<rect[^>]*/>", "", svg, count=1)
    return svg.replace("<svg ", f"<svg x='{x}' y='{y}' overflow='visible' ", 1)


# ------------------------------------------------------------------ the tools
# Six tools, each shown doing its job on a real molecule: every name, atom set,
# InChIKey and verdict below is the app's own output (explain_iupac_name and
# check_pair, engine 1.0.9), not a mock. Tiles share one width so the wide
# figure (two across) and the phone figure (one column) are the same drawings.
TILE_W = 748
CARD_SHADOW = ('<filter id="lift" x="-10%" y="-10%" width="120%" height="130%">'
               '<feDropShadow dx="0" dy="6" stdDeviation="10" flood-color="#1b1c20" flood-opacity=".09"/></filter>')


def tile(title, route, lede, h, body, title_parts=None):
    w = TILE_W
    head = (title_parts or f'<text class="disp" x="40" y="80" font-size="48" letter-spacing="3" fill="{INK}">{title}</text>')
    assert width(lede, 26) < w - 80, lede
    return h, (f'<rect width="{w}" height="{h}" rx="30" fill="#fff" filter="url(#lift)"/>'
               f'{head}<text class="mono" x="{w - 40}" y="78" font-size="22" text-anchor="end" fill="{MUTED}">{route}</text>'
               f'<text class="body" x="40" y="126" font-size="26" fill="{BODY}">{lede}</text>{body}')


CAF_TRACED = "CN1C(N(C=2N=CN(C2C1=O)C)C)=O"   # OPSIN's own atom order for the name


def tool_explain():
    line1, _ = runs(40, 206, [("1,3,7-trimethyl-3,7-dihydro-", None)], 36)
    line2, _ = runs(40, 254, [("1", None), ("H", "italic"), ("-purine-", None), ("2,6-dione", "active")], 36)
    body = (line1 + line2
            + lit_depiction(CAF_TRACED, 460, 290, 144, 270, lights=(2, 9, 10, 13), font=22)
            + '<rect x="40" y="572" width="668" height="56" rx="14" fill="#edeff2"/>'
            + f'<text class="body" x="60" y="608" font-size="23" fill="{BODY}">The “dione” ending means a C=O group (a carbonyl).</text>')
    return tile("EXPLAIN", "/explain", "Point at a part of the name; its atoms light up.", 660, body)


def tool_check():
    a, b = "QNAYBMKLOCPYGJ-REOHCLBHSA-N", "QNAYBMKLOCPYGJ-UWTATZPHSA-N"

    def key(y, k):
        # The stereo block is the part that differs: marked as /compare marks
        # a differing part, grey inside an outline -- never a tier's line.
        x0, cw = 40 + 15 * 24 * .6, 24 * .6
        return (f'<rect x="{x0 - 2:.1f}" y="{y - 22}" width="{10 * cw + 4:.1f}" height="30" rx="4" fill="#e0e0e0" stroke="{MUTED}" stroke-width="2"/>'
                f'<text class="mono" x="40" y="{y}" font-size="24" fill="{INK}">{k}</text>')
    name, _ = runs(40, 306, [("D", None), ("-alanine", None)], 36)
    body = (f'<text class="mono" x="40" y="186" font-size="19" letter-spacing="3" fill="{MUTED}">STRUCTURE</text>'
            f'<text class="mono" x="40" y="222" font-size="26" fill="{INK}">C[C@H](N)C(=O)O</text>'
            f'<text class="mono" x="40" y="268" font-size="19" letter-spacing="3" fill="{MUTED}">THE NAME IT WAS GIVEN</text>'
            + name
            + f'<line x1="40" y1="344" x2="708" y2="344" stroke="{HAIR}" stroke-width="1.6"/>'
            f'<text class="disp" x="40" y="410" font-size="46" letter-spacing="2" fill="{INK}">SAME SKELETON;</text>'
            f'<text class="disp" x="40" y="462" font-size="46" letter-spacing="2" fill="{INK}">STEREO OR ISOTOPES DIFFER</text>'
            f'<text class="body" x="40" y="520" font-size="21" fill="{MUTED}">InChIKey of your structure</text>'
            + key(554, a)
            + f'<text class="body" x="40" y="600" font-size="21" fill="{MUTED}">InChIKey of what OPSIN read from the name</text>'
            + key(634, b))
    return tile("CHECK", "/check", "A structure, and the name it was given.", 680, body)


def tool_compare():
    out = ""
    for i, (side, smi, loc) in enumerate((("A", "OCCC", "1"), ("B", "CC(O)C", "2"))):
        x = 40 + i * 354
        nm, _ = runs(x + 44, 214, [("propan-", None), (loc, "differs"), ("-ol", None)], 38)
        out += (f'<text class="disp" x="{x}" y="214" font-size="44" fill="{INK}">{side}</text>' + nm
                + f'<rect x="{x}" y="250" width="314" height="250" rx="14" fill="#edeff2"/>'
                + depiction(smi, 274, 210, x + 20, 270, font=22))
    out += f'<text class="body" x="40" y="556" font-size="22" fill="{MUTED}">Grey marks a part the other name does not have.</text>'
    return tile("COMPARE", "/compare", "Two molecules side by side, by name or SMILES.", 600, out)


def tool_classroom():
    l1, _ = runs(40, 206, [("1,3,7-tri", None), ("methyl", "active"), ("-", None), ("·", "hidden"), (",", None),
                           ("·", "hidden"), ("-", None), ("·" * 7, "hidden"), ("-", None)], 36)
    l2, _ = runs(40, 254, [("··", "hidden"), ("-", None), ("·" * 6, "hidden"), ("-", None),
                           ("·", "hidden"), (",", None), ("·", "hidden"), ("-", None), ("·" * 5, "hidden")], 36)
    pills, x = "", 40
    for label, framed in (("Hide all", True), ("Back", True), ("5 of 15", False), ("Next", True), ("Reveal all", True)):
        w = width(label, 20, "mono") + (36 if framed else 12)
        if framed:
            pills += f'<rect x="{x}" y="528" width="{w:.0f}" height="46" rx="23" fill="#fff" stroke="#c5c5c5" stroke-width="1.6"/>'
        pills += f'<text class="mono" x="{x + w / 2:.1f}" y="558" font-size="20" text-anchor="middle" fill="{INK if framed else MUTED}">{label}</text>'
        x += w + 12
    body = l1 + l2 + lit_depiction(CAF_TRACED, 380, 230, 184, 280, lights=(0, 11, 12), font=20) + pills
    return tile("CLASSROOM MODE", "/explain", "The name revealed one part at a time, for teaching.", 600, body)


def tool_from_name():
    arrow_w = 54
    w1 = width("NAME", 48, "disp", 3)
    title = (f'<text class="disp" x="40" y="80" font-size="48" letter-spacing="3" fill="{INK}">NAME</text>'
             f'<path d="M{40 + w1 + 8:.0f} 64 h{arrow_w - 16} m-12 -10 l12 10 l-12 10" fill="none" stroke="{INK}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>'
             f'<text class="disp" x="{40 + w1 + arrow_w:.0f}" y="80" font-size="48" letter-spacing="3" fill="{INK}">STRUCTURE</text>')
    nm, end = runs(40, 236, [("2-(acetyloxy)benzoic acid", None)], 36)
    body = (nm + f'<text class="mono" x="40" y="290" font-size="21" fill="{MUTED}">CC(=O)Oc1ccccc1C(=O)O</text>'
            + arrow('M486 220 L530 220', 'M520 210 L530 220 L520 230', '')
            + depiction("CC(=O)Oc1ccccc1C(=O)O", 200, 200, 528, 152, font=18))
    return tile("", "/from-name", "OPSIN parses a name back into a structure.", 400, body, title_parts=title)


def tool_batch():
    def chips(y, label, items):
        out, x = f'<text class="mono" x="40" y="{y + 30}" font-size="19" letter-spacing="3" fill="{MUTED}">{label}</text>', 130
        for it in items:
            w = width(it, 21, "mono") + 32
            out += (f'<rect x="{x}" y="{y}" width="{w:.0f}" height="44" rx="22" fill="#fff" stroke="#c5c5c5" stroke-width="1.6"/>'
                    f'<text class="mono" x="{x + w / 2:.1f}" y="{y + 29}" font-size="21" text-anchor="middle" fill="{INK}">{it}</text>')
            x += w + 12
        return out
    lamps, x = "", 40
    for t in TIERS:
        lamps += lamp(t[0], x + 13, 324, 26, uid="tb") + f'<text class="mono" x="{x + 34}" y="330" font-size="16" fill="{MUTED}">{t[1]}</text>'
        x += 34 + width(t[1], 16, "mono") + 22
    assert x - 22 < TILE_W - 40, x
    body = chips(160, "IN", (".sdf", ".mol", ".csv", "SMILES")) + chips(222, "OUT", ("CSV", "SDF")) + lamps
    return tile("BATCH JOBS", "/", "More than ten molecules run as a job, tallied by tier.", 400, body)


def tools():
    tiles = [tool_explain(), tool_check(), tool_compare(), tool_classroom(), tool_from_name(), tool_batch()]
    css = font_css("disp", "body", "ital", "mono") + "@font-face{font-family:'Public Sans';font-style:italic;src:url(data:font/woff2;base64," + b64(FONTS / "public-sans-i3.woff2") + ") format('woff2');}"
    pad, gap = 40, 24
    # Wide: two across, each row as tall as its taller tile.
    w = pad * 2 + TILE_W * 2 + gap
    inner, y = "", pad
    for left, right in zip(tiles[::2], tiles[1::2]):
        row = max(left[0], right[0])
        for i, (h, body) in enumerate((left, right)):
            inner += f'<g transform="translate({pad + i * (TILE_W + gap)},{y})">{body.replace(f"height=\"{h}\" rx=\"30\"", f"height=\"{row}\" rx=\"30\"", 1)}</g>'
        y += row + gap
    h = y - gap + pad
    write("tools.svg", w, h, f"<defs>{CARD_SHADOW}</defs>{bench('t', w, h, 36)}{inner}", css)
    # Narrow: one column, the same tiles.
    wn = pad * 2 + TILE_W
    inner, y = "", pad
    for h_, body in tiles:
        inner += f'<g transform="translate({pad},{y})">{body}</g>'
        y += h_ + gap
    hn = y - gap + pad
    write("tools-narrow.svg", wn, hn, f"<defs>{CARD_SHADOW}</defs>{bench('tn', wn, hn, 36)}{inner}", css)


# ------------------------------------------------------------------ the paper
PAPER_TITLE = ("Orthonym: verified IUPAC names for", "chemical structures in the wild")
PAPER_AUTHORS = "Kohulan Rajan, Achim Zielesny, Christoph Steinbeck"
PAPER_META = "CHEMRXIV  ·  PREPRINT  ·  OCTOBER 2026"
PAPER_DOI = "doi.org/10.26434/chemrxiv.15009769/v1"


def paper_figure(x, y, w, h, uid):
    """The paper's subject in one cell: caffeine, its name, the double rule
    and lit lamp of a verified PIN -- the round trip's outcome, in a soft frame."""
    nm = (f'<text class="body" x="{x + 32}" y="{y + h - 126}" font-size="26" fill="{INK}">{NAME[0]}</text>'
          f'<text class="body" x="{x + 32}" y="{y + h - 92}" font-size="26" fill="{INK}">{NAME[1]}</text>')
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="22" fill="#edeff2"/>'
            + depiction(CAF, w - 120, h - 190, x + 60, y + 16, font=18) + nm
            + rule("pin", x + 32, y + h - 74, 300)
            + lamp("pin", x + 46, y + h - 34, 26, uid=uid, glow_cls="breath")
            + f'<text class="mono" x="{x + 70}" y="{y + h - 27}" font-size="18" letter-spacing="2" fill="{INK}">PIN</text>')


def paper_link(x, y):
    label = "READ THE PAPER"
    w = width(label, 22, "mono", 4) + 84
    return (f'<rect x="{x}" y="{y}" width="{w:.0f}" height="58" rx="29" fill="#fff" stroke="#c5c5c5" stroke-width="2"/>'
            f'<text class="mono" x="{x + 30}" y="{y + 37}" font-size="22" letter-spacing="4" fill="{INK}">{label}</text>'
            f'<path d="M{x + w - 44:.0f} {y + 38} l14 -14 m-10 0 h10 v10" fill="none" stroke="{INK}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>')


def paper():
    css = font_css("disp", "body", "ital", "mono") + MOTION + ".breath{animation-delay:.4s}" + REDUCED
    w, h = 1600, 600
    for t in PAPER_TITLE:
        assert width(t, 60, "disp", 1) < 900, t
    write("paper.svg", w, h, f"""<defs>{CARD_SHADOW}</defs>{bench('p', w, h, 36)}
<rect x="40" y="40" width="{w - 80}" height="{h - 80}" rx="30" fill="#fff" filter="url(#lift)"/>
<text class="disp" x="96" y="168" font-size="60" letter-spacing="1" fill="{INK}">{PAPER_TITLE[0]}</text>
<text class="disp" x="96" y="238" font-size="60" letter-spacing="1" fill="{INK}">{PAPER_TITLE[1]}</text>
<text class="body" x="96" y="304" font-size="28" fill="{BODY}">{PAPER_AUTHORS}</text>
<line x1="96" y1="352" x2="980" y2="352" stroke="{HAIR}" stroke-width="1.6"/>
<text class="mono" x="96" y="398" font-size="21" letter-spacing="3" fill="{MUTED}">{PAPER_META}</text>
<text class="mono" x="96" y="434" font-size="21" fill="{MUTED}">{PAPER_DOI}</text>
{paper_link(96, 458)}
{paper_figure(1040, 84, 476, 432, 'p')}
""", css)
    wn, hn = 800, 1180
    write("paper-narrow.svg", wn, hn, f"""<defs>{CARD_SHADOW}</defs>{bench('pn', wn, hn, 36)}
<rect x="32" y="32" width="{wn - 64}" height="{hn - 64}" rx="30" fill="#fff" filter="url(#lift)"/>
<text class="disp" x="80" y="140" font-size="58" letter-spacing="1" fill="{INK}">Orthonym: verified IUPAC</text>
<text class="disp" x="80" y="206" font-size="58" letter-spacing="1" fill="{INK}">names for chemical</text>
<text class="disp" x="80" y="272" font-size="58" letter-spacing="1" fill="{INK}">structures in the wild</text>
<text class="body" x="80" y="336" font-size="30" fill="{BODY}">Kohulan Rajan, Achim Zielesny,</text>
<text class="body" x="80" y="376" font-size="30" fill="{BODY}">Christoph Steinbeck</text>
<line x1="80" y1="416" x2="{wn - 80}" y2="416" stroke="{HAIR}" stroke-width="1.6"/>
<text class="mono" x="80" y="462" font-size="24" letter-spacing="3" fill="{MUTED}">{PAPER_META}</text>
<text class="mono" x="80" y="500" font-size="22" fill="{MUTED}">{PAPER_DOI}</text>
{paper_link(80, 530)}
{paper_figure(80, 628, wn - 160, 480, 'pn')}
""", css)

if __name__ == "__main__":
    banner()
    banner_narrow()
    cup()
    partners()
    pill("try.svg", "TRY ORTHONYM", 460, True)
    pill("run.svg", "RUN IT YOURSELF", 460, False)
    roundtrip()
    roundtrip_narrow()
    tools()
    paper()
