#!/usr/bin/env python3
"""Writes what the WinUI XAML compiler would generate for code-behind: a partial class per x:Class
with InitializeComponent and the x:Name fields. Lets the app's C# be type-checked where the XAML
compiler cannot run (macOS, Linux). The XAML markup and x:Bind expressions are not checked."""
import sys
from pathlib import Path
import xml.etree.ElementTree as ET

app = Path(sys.argv[1])
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
X = "{http://schemas.microsoft.com/winfx/2006/xaml}"
DEFAULT = "http://schemas.microsoft.com/winfx/2006/xaml/presentation"

for f in app.rglob("*.xaml"):
    if "obj" in f.parts or "bin" in f.parts:
        continue
    root = ET.parse(f).getroot()
    cls = root.get(X + "Class")
    if not cls:
        continue

    def type_of(tag):
        ns, local = tag[1:].split("}", 1)
        if ns == DEFAULT:
            if local in ("ToggleButton", "RepeatButton", "Thumb"):
                return f"Microsoft.UI.Xaml.Controls.Primitives.{local}"
            return f"Microsoft.UI.Xaml.Controls.{local}"
        if ns.startswith("using:"):
            return f"{ns[6:]}.{local}"
        return f"Microsoft.UI.Xaml.Controls.{local}"

    base = type_of(root.tag)
    if root.tag.endswith("}Application"):
        base = "Microsoft.UI.Xaml.Application"
    if root.tag.endswith("}Window"):
        base = "Microsoft.UI.Xaml.Window"
    fields = []
    for el in root.iter():
        name = el.get(X + "Name")
        if name:
            fields.append((type_of(el.tag), name))
    ns, _, name = cls.rpartition(".")
    lines = [f"namespace {ns};", f"partial class {name} : {base}", "{"]
    lines.append("    private void InitializeComponent() { }")
    for t, n in fields:
        lines.append(f"    internal {t} {n} = null!;")
    lines.append("}")
    (out / f"{name}.g.cs").write_text("\n".join(lines) + "\n")
    print(cls, len(fields))
