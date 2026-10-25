"""Compare the solo layer with the lead part of an arranged MusicXML: octave moves per note."""
import json
import sys
import xml.etree.ElementTree as ET

STEP = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def parts(path):
    root = ET.parse(path).getroot()
    names = {sp.get("id"): sp.findtext("part-name") for sp in root.iter("score-part")}
    out = {}
    for part in root.iter("part"):
        name = names[part.get("id")]
        t = 0
        div = 1
        chrom = 0
        notes = []
        for m in part.iter("measure"):
            for el in m:
                if el.tag == "attributes":
                    if el.findtext("divisions"):
                        div = int(el.findtext("divisions"))
                    tr = el.find("transpose")
                    if tr is not None:
                        chrom = int(tr.findtext("chromatic") or 0) + 12 * int(tr.findtext("octave-change") or 0)
                elif el.tag == "backup":
                    t -= int(el.findtext("duration"))
                elif el.tag == "forward":
                    t += int(el.findtext("duration"))
                elif el.tag == "note":
                    d = int(el.findtext("duration") or 0)
                    chord = el.find("chord") is not None
                    if chord:
                        t -= last
                    p = el.find("pitch")
                    tie_stop = any(x.get("type") == "stop" for x in el.findall("tie"))
                    if p is not None and not tie_stop:
                        midi = 12 * (int(p.findtext("octave")) + 1) + STEP[p.findtext("step")] + int(float(p.findtext("alter") or 0))
                        notes.append((round(t * 24 / div), midi + chrom))
                    if el.find("grace") is None:
                        t += d
                        last = d
        out[name] = notes
    return out


def main(xml, comp, lead="Solo Cornet"):
    c = json.load(open(comp))
    solo = [n for v in c["voices"] if v.get("layer") == "solo" for n in v["notes"]]
    tpb = c["ticks_per_beat"]
    assert tpb == 24, tpb
    got = {}
    for t, p in parts(xml)[lead]:
        got.setdefault(t, []).append(p)
    moved = []
    missing = 0
    for n in solo:
        ps = got.get(n["start"])
        if not ps:
            missing += 1
            continue
        best = min(ps, key=lambda q: abs(q - n["pitch"]))
        if best != n["pitch"]:
            moved.append((n["start"], n["pitch"], best))
    lp = [p for _, p in parts(xml)[lead]]
    print(f"{xml}: solo {len(solo)}, lead notes {len(lp)} range {min(lp)}-{max(lp)}, moved {len(moved)}, not found {missing}")
    if "-v" in sys.argv:
        for m in moved:
            print("  ", m)
    return moved


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], *(a for a in sys.argv[3:] if a != "-v"))
