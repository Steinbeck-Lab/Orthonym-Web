"""Draw the README's pictures in Orthonym's own world.

The bench (pink wash settling into cool grey under a dot grid), white 22px
cards, the site's three faces, the ring lamps with their neon glow, and
crimson only on the primary action and the header's flare -- DESIGN.md's
rules, drawn as SVG because a GitHub README carries no CSS of its own.

Every picture is generated, not hand-edited, so a change to the product is a
re-run, not a redraw. The structures are real RDKit drawings of caffeine; the
name and the InChIKey are the app's own output for it.

    cd backend && .venv/bin/python ../docs/readme/build.py

(any interpreter with RDKit works; the backend's venv has it).
"""
import base64
import math
import pathlib
import re

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
    ("best_effort", "BEST EFFORT", "From the general|engine; read back.", "#9c4109", "#ffb02e", 0.62),
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


def write(name, w, h, inner, css):
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
def banner():
    w, h = 1600, 540
    wordmark = b64(REPO / "frontend/public/logos/ORTHONYM.png")
    # The hero's flare, redrawn in SVG: a crimson core that breathes, a slow
    # fan of rays turning behind it, multiplied onto the bench -- crimson light
    # has to darken paper or it vanishes (DESIGN.md, Home hero).
    rays = "".join(
        f'<path d="M0 0 L{620 * math.cos(a):.1f} {620 * math.sin(a):.1f} '
        f'L{620 * math.cos(a + .045):.1f} {620 * math.sin(a + .045):.1f} Z"/>'
        for a in (i * math.tau / 28 for i in range(28))
    )
    lamps = "".join(
        lamp(t[0], 704 + i * 48, 478, 22, uid="b", mark_cls=f"on on{i}", glow_cls="breath" if t[0] == "pin" else "")
        for i, t in enumerate(TIERS)
    )
    css = font_css("body", "mono") + MOTION + """
.core{transform-origin:800px 196px;animation:core 9s ease-in-out infinite;}
.fan{transform-origin:0 0;animation:turn 80s linear infinite;}
.on{animation:on .5s cubic-bezier(.16,1,.3,1) both;}
.on0{animation-delay:.6s}.on1{animation-delay:.8s}.on2{animation-delay:1s}.on3{animation-delay:1.2s}.on4{animation-delay:1.4s}
.breath{animation-delay:1.9s}
@keyframes core{0%,100%{opacity:.55;transform:scale(1)}50%{opacity:.85;transform:scale(1.08)}}
@keyframes turn{to{transform:rotate(360deg)}}
@keyframes on{from{opacity:.15;transform:scale(.7)}to{opacity:1;transform:none}}
""" + REDUCED
    write("banner.svg", w, h, f"""
{bench('b', w, h, 36)}
<defs>
  <radialGradient id="core"><stop offset="0" stop-color="{CRIMSON}" stop-opacity=".30"/><stop offset=".45" stop-color="{CRIMSON}" stop-opacity=".10"/><stop offset="1" stop-color="{CRIMSON}" stop-opacity="0"/></radialGradient>
  <radialGradient id="fanfade"><stop offset=".1" stop-color="#fff" stop-opacity="1"/><stop offset=".8" stop-color="#fff" stop-opacity="0"/></radialGradient>
  <mask id="fanmask"><rect x="-700" y="-700" width="1400" height="1400" fill="url(#fanfade)"/></mask>
  <clipPath id="card"><rect width="{w}" height="{h}" rx="36"/></clipPath>
</defs>
<g clip-path="url(#card)" style="mix-blend-mode:multiply">
  <g transform="translate(800 196)"><g mask="url(#fanmask)"><g class="fan" fill="{CRIMSON}" fill-opacity=".035">{rays}</g></g></g>
  <ellipse class="core" cx="800" cy="196" rx="560" ry="230" fill="url(#core)"/>
</g>
<image href="data:image/png;base64,{wordmark}" x="360" y="100" width="880" height="194"/>
<text class="body" x="800" y="366" text-anchor="middle" font-size="37" fill="{BODY}">Verified IUPAC names for Chemical Structures</text>
<text class="mono" x="800" y="420" text-anchor="middle" font-size="16" letter-spacing="4" fill="{MUTED}">DETERMINISTIC  ·  RULE-BASED  ·  EVERY NAME READ BACK BY OPSIN</text>
{lamps}
""", css)


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
""", css)


def roundtrip_narrow():
    """The same loop for a phone-width README: one column, top to bottom."""
    w, h = 800, 2010
    css = font_css("body", "bold", "ital", "mono") + MOTION + """
.a1{animation-delay:.1s}.a2{animation-delay:.7s}.a3{animation-delay:1.3s}.a4{animation-delay:1.9s}
.d1{animation-delay:.4s}.d1h{animation-delay:.9s}.d2{animation-delay:1s}.d2h{animation-delay:1.5s}
.d3{animation-delay:1.6s}.d3h{animation-delay:2.1s}
.breath{animation-delay:2.6s}
""" + REDUCED
    rows = ""
    for i, (key, short, text, *_r) in enumerate(TIERS):
        y = 1440 + i * 110
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
  <text class="body" x="56" y="1330" font-size="30" fill="{SUCCESS}">Same InChIKey: a verified PIN</text>
  <line x1="56" y1="1372" x2="{w - 56}" y2="1372" stroke="{HAIR}" stroke-width="1.6"/>
</g>
{rows}
""", css)


if __name__ == "__main__":
    banner()
    pill("try.svg", "TRY ORTHONYM", 440, True)
    pill("run.svg", "RUN IT YOURSELF", 460, False)
    roundtrip()
    roundtrip_narrow()
