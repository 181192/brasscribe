#!/usr/bin/env python3
"""Check an Android App Bundle (.aab) before it goes to Google Play.

    .github/scripts/check-aab.py --cert SHA256 --package ID [--version-name N] [--version-code C] [--like APK] app.aab
    .github/scripts/check-aab.py --print package|versionName|versionCode app.aab   # one value, nothing checked

Fails (exit 1) unless the bundle
- is signed, every entry of it, by exactly one signer whose certificate SHA-256 is --cert (colons and case
  do not matter). Play App Signing must hold that same key, so a phone takes Play's build over the GitHub one
  and the other way round; a bundle that is unsigned or signed with any other key is refused here;
- is the app --package, not debuggable, with --version-name and --version-code when given;
- with --like: has the package, versionName, versionCode and permissions of that APK (the same app from the
  same build), so the bundle asks for no permission the APK does not.
Prints the package, version, SDK range and the permissions it asks for (also into $GITHUB_STEP_SUMMARY when set).

Needs jarsigner and keytool (a JDK; JAVA_HOME/bin is searched too), and for --like the build tools' aapt2
(ANDROID_HOME). The bundle's manifest is in aapt2's protobuf format; it is read here with the standard library.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

ANDROID_NS = "http://schemas.android.com/apk/res/android"
MANIFEST = "base/manifest/AndroidManifest.xml"


class Refused(Exception):
    pass


# --- aapt2's protobuf XML (frameworks/base/tools/aapt2/Resources.proto), only the fields read here ---------------
# XmlNode { XmlElement element = 1; string text = 2; }
# XmlElement { string namespace_uri = 2; string name = 3; repeated XmlAttribute attribute = 4; repeated XmlNode child = 5; }
# XmlAttribute { string namespace_uri = 1; string name = 2; string value = 3; }


def _fields(data: bytes):
    """(field number, wire type, value) for each field of one protobuf message."""
    i = 0

    def varint() -> int:
        nonlocal i
        shift = result = 0
        while True:
            if i >= len(data):
                raise Refused("its manifest is not a protobuf message (cut short)")
            b = data[i]
            i += 1
            result |= (b & 0x7F) << shift
            if not b & 0x80:
                return result
            shift += 7

    while i < len(data):
        key = varint()
        number, wire = key >> 3, key & 7
        if wire == 0:
            yield number, wire, varint()
        elif wire == 1:
            yield number, wire, data[i:i + 8]
            i += 8
        elif wire == 2:
            n = varint()
            yield number, wire, data[i:i + n]
            i += n
        elif wire == 5:
            yield number, wire, data[i:i + 4]
            i += 4
        else:
            raise Refused(f"its manifest is not a protobuf message (wire type {wire})")


@dataclass
class Element:
    name: str = ""
    attrs: dict[str, str] = field(default_factory=dict)  # android:name -> value; no namespace -> "name"
    children: list["Element"] = field(default_factory=list)

    def all(self, name: str) -> list["Element"]:
        return [c for c in self.children if c.name == name]


def _element(data: bytes) -> Element:
    el = Element()
    for number, wire, value in _fields(data):
        if wire != 2:
            continue
        if number == 3:
            el.name = value.decode()
        elif number == 4:
            ns = name = text = ""
            for n, w, v in _fields(value):
                if w == 2 and n in (1, 2, 3):
                    s = v.decode()
                    ns, name, text = (s, name, text) if n == 1 else (ns, s, text) if n == 2 else (ns, name, s)
            el.attrs[("android:" if ns == ANDROID_NS else "") + name] = text
        elif number == 5:
            for n, w, v in _fields(value):
                if n == 1 and w == 2:
                    el.children.append(_element(v))
    return el


def manifest(aab: Path) -> Element:
    try:
        with zipfile.ZipFile(aab) as z:
            names = set(z.namelist())
            if "BundleConfig.pb" not in names or MANIFEST not in names:
                raise Refused("is not an app bundle (no BundleConfig.pb or no base module manifest)")
            data = z.read(MANIFEST)
    except zipfile.BadZipFile as e:
        raise Refused(f"is not a zip file ({e})") from e
    root = None
    for number, wire, value in _fields(data):
        if number == 1 and wire == 2:
            root = _element(value)
    if root is None or root.name != "manifest":
        raise Refused("its base manifest has no <manifest> element")
    return root


@dataclass
class Facts:
    package: str
    version_name: str
    version_code: str
    min_sdk: str
    target_sdk: str
    debuggable: bool
    permissions: list[str]


def facts(root: Element) -> Facts:
    sdk = (root.all("uses-sdk") or [Element()])[0].attrs
    app = (root.all("application") or [Element()])[0].attrs
    perms = sorted({p.attrs.get("android:name", "") for p in root.all("uses-permission") + root.all("uses-permission-sdk-23")})
    return Facts(
        package=root.attrs.get("package", ""),
        version_name=root.attrs.get("android:versionName", ""),
        version_code=root.attrs.get("android:versionCode", ""),
        min_sdk=sdk.get("android:minSdkVersion", ""),
        target_sdk=sdk.get("android:targetSdkVersion", ""),
        debuggable=app.get("android:debuggable", "false").lower() == "true",
        permissions=[p for p in perms if p],
    )


# --- tools ------------------------------------------------------------------------------------------------------


def tool(name: str, *dirs: Path) -> str:
    for d in dirs:
        found = sorted(d.glob(name), key=lambda p: [int(x) if x.isdigit() else x for x in re.split(r"(\d+)", str(p))])
        if found:
            return str(found[-1])
    on_path = shutil.which(name)
    if not on_path:
        raise SystemExit(f"check-aab: needs {name} (not on PATH or under {', '.join(map(str, dirs)) or '-'})")
    return on_path


def java_tool(name: str) -> str:
    home = os.environ.get("JAVA_HOME")
    return tool(name, *([Path(home) / "bin"] if home else []))


def aapt2() -> str:
    sdk = Path(os.environ.get("ANDROID_HOME") or "/opt/homebrew/share/android-commandlinetools")
    return tool("aapt2", *sorted((sdk / "build-tools").glob("*"))[::-1][:1])


def run(*cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=False)


def signers(aab: Path) -> list[str]:
    """The SHA-256 of each signer's certificate, after jarsigner has checked every entry against its signature."""
    verify = run(java_tool("jarsigner"), "-verify", str(aab))
    out = verify.stdout + verify.stderr
    if "jar is unsigned" in out:
        raise Refused("is not signed")
    if verify.returncode != 0 or "jar verified." not in out:
        raise Refused(f"its signature does not verify: {out.strip().splitlines()[0] if out.strip() else verify.returncode}")
    if "unsigned entries" in out:
        raise Refused("has entries that no signature covers")
    printed = run(java_tool("keytool"), "-printcert", "-jarfile", str(aab))
    certs = re.findall(r"SHA256:\s*([0-9A-Fa-f:]+)", printed.stdout)
    if printed.returncode != 0 or not certs:
        raise Refused(f"no signer certificate could be read: {printed.stdout.strip() or printed.stderr.strip()}")
    return [norm(c) for c in certs]


def norm(sha: str) -> str:
    return sha.replace(":", "").lower()


def apk_facts(apk: Path) -> Facts:
    a = aapt2()
    badging = run(a, "dump", "badging", str(apk))
    if badging.returncode != 0:
        raise SystemExit(f"check-aab: aapt2 cannot read {apk}: {badging.stderr.strip()}")
    head = re.search(r"^package: name='([^']*)' versionCode='([^']*)' versionName='([^']*)'", badging.stdout, re.M)
    if not head:
        raise SystemExit(f"check-aab: no package line in aapt2's badging of {apk}")
    perms = run(a, "dump", "permissions", str(apk)).stdout
    return Facts(
        package=head[1], version_code=head[2], version_name=head[3], min_sdk="", target_sdk="", debuggable=False,
        permissions=sorted(set(re.findall(r"^uses-permission(?:-sdk-23)?: name='([^']+)'", perms, re.M))),
    )


# --- the check --------------------------------------------------------------------------------------------------


def check(aab: Path, cert: str, package: str, version_name: str | None, version_code: str | None,
          like: Path | None) -> Facts:
    f = facts(manifest(aab))
    if f.package != package:
        raise Refused(f"is {f.package or 'no package'}, not {package}")
    if f.debuggable:
        raise Refused("is debuggable")
    if version_name is not None and f.version_name != version_name:
        raise Refused(f"has versionName '{f.version_name}', not '{version_name}'")
    if version_code is not None and f.version_code != version_code:
        raise Refused(f"has versionCode '{f.version_code}', not '{version_code}'")
    if like is not None:
        a = apk_facts(like)
        for what, mine, theirs in (("package", f.package, a.package), ("versionName", f.version_name, a.version_name),
                                   ("versionCode", f.version_code, a.version_code)):
            if mine != theirs:
                raise Refused(f"has {what} '{mine}', but {like.name} has '{theirs}'")
        if f.permissions != a.permissions:
            more, fewer = sorted(set(f.permissions) - set(a.permissions)), sorted(set(a.permissions) - set(f.permissions))
            raise Refused(f"asks for other permissions than {like.name}: "
                          f"{'only in the bundle: ' + ', '.join(more) if more else ''}"
                          f"{'; ' if more and fewer else ''}{'only in the APK: ' + ', '.join(fewer) if fewer else ''}")
    certs = signers(aab)
    if len(certs) != 1:
        raise Refused(f"has {len(certs)} signers, not one: {', '.join(certs)}")
    if certs[0] != norm(cert):
        raise Refused(f"is signed with certificate {certs[0]}, not {norm(cert)}")
    return f


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("aab", type=Path)
    p.add_argument("--cert", help="the SHA-256 of the one certificate the bundle must be signed with")
    p.add_argument("--package", help="the application id the bundle must have")
    p.add_argument("--print", choices=("package", "versionName", "versionCode"), dest="show",
                   help="print this value of the bundle's manifest and check nothing")
    p.add_argument("--version-name")
    p.add_argument("--version-code")
    p.add_argument("--like", type=Path, help="an APK of the same app and build: same version and permissions")
    a = p.parse_args(argv)
    if a.show:
        try:
            f = facts(manifest(a.aab))
        except Refused as e:
            print(f"check-aab: {a.aab.name} {e}", file=sys.stderr)
            return 1
        print({"package": f.package, "versionName": f.version_name, "versionCode": f.version_code}[a.show])
        return 0
    if not a.cert or not a.package:
        p.error("--cert and --package are required (or --print)")
    try:
        f = check(a.aab, a.cert, a.package, a.version_name, a.version_code, a.like)
    except Refused as e:
        print(f"check-aab: {a.aab.name} {e}", file=sys.stderr)
        return 1
    report = (f"{a.aab.name}: {f.package} {f.version_name} ({f.version_code}), API {f.min_sdk} to {f.target_sdk}, "
              f"signed with {norm(a.cert)[:16]}..., permissions: {', '.join(f.permissions) or 'none'}")
    print(f"check-aab: {report}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as s:
            s.write(f"- {report}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
