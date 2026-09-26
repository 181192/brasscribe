#!/usr/bin/env python3
"""Stands in for the WinUI XAML compiler where it cannot run (macOS, Linux).

For every XAML file with an x:Class it writes a partial class with:
- what the XAML compiler generates for code-behind: InitializeComponent, the x:Name fields and a
  Bindings object with Update();
- a check method the C# compiler type-checks: every attribute becomes a member access on the
  element's type (so unknown properties fail), attached properties call their Get accessor, event
  attributes subscribe the named handler (so wrong handler signatures fail), and every x:Bind path
  or function call is emitted as an expression against the page or the DataTemplate's x:DataType.

It does not check values (enum names, resources, conversions) or two-way bindability; the real
XAML compiler on Windows CI does.
Usage: gen_stubs.py <app project dir> <output dir>
"""
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

app = Path(sys.argv[1])
out = Path(sys.argv[2])
out.mkdir(parents=True, exist_ok=True)
for old in out.glob("*.g.cs"):
    old.unlink()

X = "{http://schemas.microsoft.com/winfx/2006/xaml}"
DEFAULT = "http://schemas.microsoft.com/winfx/2006/xaml/presentation"
PRIMITIVES = {"ToggleButton", "RepeatButton", "Thumb", "FlyoutBase"}
# Elements outside Microsoft.UI.Xaml.Controls.
NAMESPACES = {
    **{t: "Microsoft.UI.Xaml.Documents" for t in ("Run", "Span", "Bold", "Italic", "Underline", "LineBreak", "Hyperlink", "Paragraph")},
    **{t: "Microsoft.UI.Xaml.Shapes" for t in ("Rectangle", "Ellipse", "Path", "Line", "Polyline", "Polygon")},
    **{t: "Microsoft.UI.Xaml.Media" for t in ("SolidColorBrush", "FontFamily", "ThemeShadow", "TranslateTransform", "ScaleTransform")},
    **{t: "Microsoft.UI.Xaml.Media.Imaging" for t in ("BitmapImage", "SvgImageSource")},
    **{t: "Microsoft.UI.Xaml.Media.Animation" for t in ("TransitionCollection", "EntranceThemeTransition", "ContentThemeTransition",
                                                       "NavigationThemeTransition", "DrillInNavigationTransitionInfo",
                                                       "SuppressNavigationTransitionInfo")},
    **{t: "Microsoft.UI.Xaml.Input" for t in ("KeyboardAccelerator",)},
    **{t: "Microsoft.UI.Xaml" for t in ("Application", "Window", "ResourceDictionary", "Setter", "Style", "DataTemplate",
                                          "VisualStateManager", "VisualState", "VisualStateGroup", "AdaptiveTrigger")},
}
ATTACHED_OWNERS = {
    "Grid": "Microsoft.UI.Xaml.Controls.Grid",
    "Canvas": "Microsoft.UI.Xaml.Controls.Canvas",
    "ScrollViewer": "Microsoft.UI.Xaml.Controls.ScrollViewer",
    "ToolTipService": "Microsoft.UI.Xaml.Controls.ToolTipService",
    "AutomationProperties": "Microsoft.UI.Xaml.Automation.AutomationProperties",
}
SKIP_ATTRS = {"Style"}  # resource references: value not checkable here
# Resource entries (values, not elements with members to check).
SKIP_TAGS = {"StaticResource", "ThemeResource", "Thickness", "CornerRadius", "Color", "String", "Double", "Boolean"}


def csharp_type(tag, prefixes):
    ns, local = tag[1:].split("}", 1)
    if ns == DEFAULT:
        if local in PRIMITIVES:
            return f"Microsoft.UI.Xaml.Controls.Primitives.{local}"
        if local in NAMESPACES:
            return f"{NAMESPACES[local]}.{local}"
        return f"Microsoft.UI.Xaml.Controls.{local}"
    if ns.startswith("using:"):
        return f"{ns[6:]}.{local}"
    return None


def split_top(s, sep=","):
    parts, depth, cur = [], 0, ""
    for ch in s:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == sep and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip() for p in parts]


def bind_expr(expr, ctx, prefixes):
    """C# for an x:Bind path or function call, relative to ctx ('this' or a DataTemplate type)."""
    expr = expr.strip()
    if not expr:
        return None
    m = re.match(r"^(\w+):(\w+)\.(\w+)\((.*)\)$", expr)
    if m:
        prefix, cls, fn, args = m.groups()
        ns = prefixes.get(prefix)
        if ns is None:
            return None
        cargs = [bind_expr(a, ctx, prefixes) or "default!" for a in split_top(args)] if args.strip() else []
        return f"{ns}.{cls}.{fn}({', '.join(cargs)})"
    if re.match(r"^[A-Za-z_][\w.]*$", expr):
        return f"{ctx}.{expr}" if ctx != "this" else f"this.{expr}"
    return None


def handlers_in(code):
    return set(re.findall(r"\bvoid\s+(\w+)\s*\(", code))


for f in sorted(app.rglob("*.xaml")):
    if "obj" in f.parts or "bin" in f.parts:
        continue
    text = f.read_text()
    root = ET.fromstring(text)
    cls = root.get(X + "Class")
    if not cls:
        continue
    prefixes = dict(re.findall(r'xmlns:(\w+)="using:([^"]+)"', text))
    code_behind = f.with_suffix(".xaml.cs")
    handlers = handlers_in(code_behind.read_text()) if code_behind.exists() else set()

    base = csharp_type(root.tag, prefixes)
    fields, checks = [], []
    counter = [0]
    uses_bind = "{x:Bind" in text

    def visit(el, ctx):
        tag_local = el.tag.split("}", 1)[1]
        if "." in tag_local:  # property element, e.g. Grid.RowDefinitions
            for child in el:
                visit(child, ctx)
            return
        if tag_local in SKIP_TAGS:
            return
        t = csharp_type(el.tag, prefixes)
        data_type = el.get(X + "DataType")
        if data_type and ":" in data_type:
            p, local = data_type.split(":", 1)
            if p in prefixes:
                ctx = f"default({prefixes[p]}.{local})!"
        if el.get(X + "Name"):
            fields.append((t, el.get(X + "Name")))
        if t is not None and el is not root and tag_local not in ("Setter", "ResourceDictionary"):
            counter[0] += 1
            var = f"e{counter[0]}"
            checks.append(f"        {t} {var} = default!;")
            for attr, value in el.attrib.items():
                if attr.startswith("{") or attr.startswith("xmlns") or attr in SKIP_ATTRS:
                    continue
                if "." in attr:
                    owner, prop = attr.split(".", 1)
                    if owner in ATTACHED_OWNERS:
                        checks.append(f"        _ = {ATTACHED_OWNERS[owner]}.Get{prop}({var});")
                elif re.match(r"^[A-Za-z_]\w*$", value) and value in handlers:
                    checks.append(f"        {var}.{attr} += {value};")
                else:
                    checks.append(f"        _ = {var}.{attr};")
                m = re.match(r"^\{x:Bind\s*(.*)\}$", value)
                if m and m.group(1).strip():
                    first = split_top(m.group(1))[0]
                    if first.startswith("Path="):
                        first = first[5:]
                    if "=" not in first:
                        e = bind_expr(first, ctx, prefixes)
                        if e:
                            checks.append(f"        _ = {e};")
        for child in el:
            visit(child, ctx)

    # The root's own attributes (events like Drop on the UserControl) are checked on 'this'.
    for attr, value in root.attrib.items():
        if attr.startswith("{") or attr.startswith("xmlns") or "." in attr:
            continue
        if re.match(r"^[A-Za-z_]\w*$", value) and value in handlers:
            checks.append(f"        this.{attr} += {value};")
        else:
            checks.append(f"        _ = this.{attr};")
    for child in root:
        visit(child, "this")

    ns, _, name = cls.rpartition(".")
    lines = [
        "#pragma warning disable CS0169, CS0219, CS0414, CS0649, CS8321",
        f"namespace {ns};",
        f"partial class {name} : {base}",
        "{",
        "    private void InitializeComponent() { }",
    ]
    for t, n in fields:
        lines.append(f"    internal {t} {n} = null!;")
    if uses_bind:
        lines.append("    private readonly __Bindings Bindings = new();")
        lines.append("    private sealed class __Bindings { public void Update() { } public void StopTracking() { } public void Initialize() { } }")
    lines.append("    private void __CheckXaml()")
    lines.append("    {")
    lines.extend(checks)
    lines.append("    }")
    lines.append("}")
    (out / f"{name}.g.cs").write_text("\n".join(lines) + "\n")
    print(f"{cls}: {len(fields)} named elements, {len(checks)} checks")
