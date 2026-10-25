"""Instrument ranges from the MuseScore 4 app bundle's templates (instruments.xml is compiled in)."""
import glob
import re

ROOT = "/Applications/MuseScore 4.app/Contents/Resources/templates"
IDS = ["c-cornet", "bb-trumpet", "c-trumpet", "piccolo-trumpet", "bb-cornet", "eb-cornet", "flugelhorn", "eb-alto-horn", "euphonium"]
seen = {}
for f in sorted(glob.glob(ROOT + "/**/*.mscx", recursive=True)):
    txt = open(f, encoding="utf-8").read()
    for m in re.finditer(r'<Instrument id="([^"]+)">(.*?)</Instrument>', txt, re.S):
        iid, body = m.group(1), m.group(2)
        if iid not in IDS:
            continue
        def g(tag):
            x = re.search(rf"<{tag}>(.*?)</{tag}>", body, re.S)
            return x.group(1).strip() if x else None
        row = (g("longName"), g("minPitchA"), g("maxPitchA"), g("minPitchP"), g("maxPitchP"), g("transposeChromatic"),
               g("transposeDiatonic"), g("instrumentId"), re.search(r'<program value="(\d+)"', body) and re.search(r'<program value="(\d+)"', body).group(1))
        seen.setdefault(iid, {}).setdefault(row, []).append(f.split("templates/")[1])
for iid in IDS:
    for row, files in seen.get(iid, {}).items():
        print(iid, "long=%s A=%s-%s P=%s-%s chrom=%s diat=%s sound=%s prog=%s" % row, "|", files[0], f"(+{len(files)-1})")
