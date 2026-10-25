# /// script
# dependencies = ["fonttools"]
# ///
"""Build "Fretscribe Tab": Atkinson Hyperlegible Mono at 600 with a plain zero as the default 0.

    uv run build_tab_font.py "AtkinsonHyperlegibleMono[wght].ttf" FretscribeTab-Regular.ttf

The source face has no plain zero: its default 0 has a slash and its `zero` feature gives a 0 with a
dot. Tab is written with a plain 0, and 0 is the most common number on a tab page, so the dot is taken
out of the dotted zero (its outer shape and its counter stay) and that glyph is made the default.
"""
import sys
from fontTools.pens.boundsPen import BoundsPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

src, out = sys.argv[1], sys.argv[2]
f = TTFont(src)
f = instantiateVariableFont(f, {"wght": 600})
cmap = f.getBestCmap()
zero = cmap[0x30]
alt = None
for fi in f["GSUB"].table.FeatureList.FeatureRecord:
    if fi.FeatureTag == "zero":
        for li in fi.Feature.LookupListIndex:
            for st in f["GSUB"].table.LookupList.Lookup[li].SubTable:
                m = getattr(st, "mapping", None) or getattr(getattr(st, "ExtSubTable", None), "mapping", {})
                alt = m.get(zero, alt)
print("default zero:", zero, "-> zero feature:", alt)
assert alt, "no zero alternate"


def contours(glyph_name):
    """The glyph's contours, each as its pen calls and its bounding box."""
    pen = DecomposingRecordingPen(f.getGlyphSet())
    f.getGlyphSet()[glyph_name].draw(pen)
    found, current = [], []
    for call in pen.value:
        current.append(call)
        if call[0] in ("closePath", "endPath"):
            bounds = BoundsPen(None)
            for op, args in current:
                getattr(bounds, op)(*args)
            found.append((current, bounds.bounds))
            current = []
    return found


def area(box):
    return (box[2] - box[0]) * (box[3] - box[1])


def inside(inner, outer):
    return outer[0] < inner[0] and outer[1] < inner[1] and inner[2] < outer[2] and inner[3] < outer[3]


# The dotted zero is three contours: the outer shape, the counter inside it and the dot inside the counter.
parts = sorted(contours(alt), key=lambda c: area(c[1]), reverse=True)
assert len(parts) == 3, f"{alt} has {len(parts)} contours, not an outer shape, a counter and a dot"
outer, counter, dot = parts
assert inside(counter[1], outer[1]) and inside(dot[1], counter[1]), "the smallest contour is not a dot inside the counter"
assert area(dot[1]) < 0.25 * area(counter[1]), "the smallest contour is too large to be the dot"
pen = TTGlyphPen(None)
for calls, _ in (outer, counter):
    for op, args in calls:
        getattr(pen, op)(*args)
width = f["hmtx"][alt]
f["glyf"][alt] = pen.glyph()
f["hmtx"][alt] = width
print("plain zero:", alt, "without its dot", dot[1])

for t in f["cmap"].tables:
    if 0x30 in t.cmap:
        t.cmap[0x30] = alt
name = f["name"]
for rec in list(name.names):
    if rec.nameID in (1, 3, 4, 6, 16, 17, 21, 22, 25):
        name.removeNames(nameID=rec.nameID)
for nid, val in {1: "Fretscribe Tab", 2: "Regular", 3: "Fretscribe Tab 600", 4: "Fretscribe Tab",
                 6: "FretscribeTab-Regular"}.items():
    name.setName(val, nid, 3, 1, 0x409)
name.setName("Modified from Atkinson Hyperlegible Mono (OFL 1.1): static weight 600, a plain zero (the dotted zero "
             "without its dot) by default.", 10, 3, 1, 0x409)
f["OS/2"].usWeightClass = 600
f.save(out)
