# /// script
# dependencies = ["fonttools"]
# ///
"""Build "Fretscribe Tab": Atkinson Hyperlegible Mono at 600 with the plain zero as the default 0."""
import sys
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
name.setName("Modified from Atkinson Hyperlegible Mono (OFL 1.1): static weight 600, plain zero by default.", 10, 3, 1, 0x409)
f["OS/2"].usWeightClass = 600
f.save(out)
