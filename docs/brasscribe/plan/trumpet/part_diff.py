"""Notes that differ per part between two arranged MusicXML files (onset, sounding pitch)."""
import sys
sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
from lead_octaves import parts
a = parts(sys.argv[1]); b = parts(sys.argv[2])
for name in a:
    x, y = sorted(a[name]), sorted(b.get(name, []))
    sx, sy = set(x), set(y)
    if sx != sy:
        print(f"{name:16} {len(x):4} -> {len(y):4}  changed {len(sx ^ sy)//1:4}  top {max(p for _,p in x) if x else '-'} -> {max(p for _,p in y) if y else '-'}")
