"""`brasscribe` command line.

    brasscribe run <audio> [--profile P] [--out DIR] [--reuse DIR] [--no-heavy] [--cold STAGES] [--check-golden DIR]
    brasscribe bench <suite|group> [--mode cached|live] [--json FILE] [--allow-improved] [--require-data]
    brasscribe serve [--host H] [--port N] [--lan] [--no-advertise] [--no-trust-local]
    brasscribe studio [--port N] [--lan] [--no-advertise] [--no-browser]   (opens the default browser)
    brasscribe manifest rerun <manifest.json> [--no-heavy] [--cold STAGES]
    brasscribe compare <candidate dir> <reference dir>
    brasscribe devices [list | revoke <device id> | reset]   (paired Play devices; takes effect in a running engine)
    brasscribe profiles | suites
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from brasscribe_music.instruments import SEAT_IDS

from . import bass_tab, config, profiles, runner, tab


def _print_event(e: dict) -> None:
    if e.get("type") == "stage" and e["status"] != "started":
        extra = f" {e['seconds']:.1f}s" if "seconds" in e else ""
        if "device" in e:
            extra += f" [{e['device']}]"
        if "matches_cache" in e:
            extra += f" matches cache: {e['matches_cache']}"
        if e["status"] == "failed":
            extra += f" {e.get('error')}"
        print(f"  {e['stage']:32s} {e['status']}{extra}", flush=True)


def _cold(value: str | None) -> set[str]:
    return {c.strip() for c in value.split(",") if c.strip()} if value else set()


def cmd_run(args) -> int:
    s = config.load()
    if tab.is_tab(args.profile):
        try:  # before any model runs: the last stage needs the core
            bass_tab.core_cli()
        except bass_tab.CoreCliMissing as e:
            raise runner.RunRefused(str(e)) from e
    m = runner.run(s, args.audio, args.profile, title=args.title, out=args.out, reuse=args.reuse,
                   allow_heavy=not args.no_heavy, cold=_cold(args.cold), params={"audio": not args.no_audio, "lineup": args.lineup,
                                                                     "difficulty": args.difficulty, "key": args.key,
                                                                     "transpose": args.transpose, "seat": args.seat,
                                                                     "reads": args.reads, "lead": args.lead,
                                                                     **({"muscriptor": False} if args.no_muscriptor else {}),
                                                                     **bass_tab.given(**vars(args))},
                   emit=_print_event)
    run_dir = s.runs_dir / m["run_id"]
    print(f"{m['status']}: {run_dir}  ({m['seconds']:.1f}s, devices {', '.join(m['devices']) or '-'})")
    if m["status"] != "succeeded":
        print(m.get("error", ""), file=sys.stderr)
        return 1
    mismatched = [st["stage"] for st in m["stages"] if st.get("matches_cache") is False]
    if mismatched:
        print(f"cold stages that differ from the cache: {', '.join(mismatched)}")
    if args.check_golden:
        from .compare import compare

        c = compare(run_dir / "outputs", args.check_golden)
        print(c.report())
        (run_dir / "golden-check.json").write_text(json.dumps(c.to_dict(), indent=1))
        return 0 if c.ok else 2
    return 0


def cmd_bench(args) -> int:
    from brasscribe_eval import suites

    if args.suite in ("list", "--list"):
        for name, st in suites.SUITES.items():
            print(f"{name:24s} {'cpu' if st.cpu else 'gpu'}  {st.description}")
        return 0
    from . import history

    s = config.load()
    results = suites.run_many(args.suite, mode=args.mode, data=s.data_dir)
    report = suites.gate(results, allow_improved=args.allow_improved, require_data=args.require_data)
    print(suites.format_report(report))
    if not args.no_history:
        history.save(s, report, args.suite, args.mode)
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1))
    return 0 if report["passed"] else 1


def lan_addresses() -> list[str]:
    """IPv4 addresses of this machine that LAN clients can reach, private (RFC 1918) ranges first."""
    import ipaddress
    import socket

    found: list[str] = []
    for target in ("192.168.255.255", "10.255.255.255", "172.31.255.255", "8.8.8.8"):
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            try:
                sock.connect((target, 1))  # no packet is sent; this only picks the outgoing interface
                found.append(sock.getsockname()[0])
            except OSError:
                pass
    try:
        found += socket.gethostbyname_ex(socket.gethostname())[2]
    except OSError:
        pass
    # A VPN can own the default route, so also read every interface address.
    import re
    import shutil
    import subprocess

    for cmd in (["ifconfig"], ["ip", "-4", "-o", "addr"], ["ipconfig"]):
        if shutil.which(cmd[0]):
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, timeout=5).stdout
            except (OSError, subprocess.TimeoutExpired):
                continue
            found += re.findall(r"(?:inet |IPv4[^:]*:\s*)(\d+\.\d+\.\d+\.\d+)", out)
            break
    ips = [ipaddress.ip_address(a) for a in dict.fromkeys(found)]
    ips = [ip for ip in ips if not ip.is_loopback and not ip.is_link_local]
    return [str(ip) for ip in sorted(ips, key=lambda ip: (not ip.is_private or ip in ipaddress.ip_network("100.64.0.0/10"), str(ip)))]


def serve_banner(app, host: str, port: int, ips: list[str] | None = None) -> tuple[str, list[str]]:
    """(URL to open locally, lines to print). Records the LAN addresses in the pairing payload."""
    local = f"http://{'127.0.0.1' if host in ('0.0.0.0', '::') else host}:{port}/"
    lines = [f"brasscribe engine on {local}"]
    if host not in ("127.0.0.1", "localhost", "::1"):
        if ips is None:
            ips = lan_addresses() if host in ("0.0.0.0", "::") else [host]
        app.state.hosts = [f"{ip}:{port}" for ip in ips]
        lines += [f"LAN URL: http://{ip}:{port}/" for ip in ips] or ["LAN URL: no network address found"]
        lines.append(f"LAN pairing code: {app.state.pairing.code}  (type it once on each phone or tablet; "
                     f"paired devices stay paired across restarts)")
        n = len(app.state.devices.list())
        if n:
            lines.append(f"Paired devices: {n}  (brasscribe devices list)")
    if not app.state.trust_loopback:
        lines.append("Local trust is off: clients on this computer need a token too")
    if app.state.admin_token:
        lines.append("Device management needs the admin token (BRASSCRIBE_ADMIN_TOKEN)")
    return local, lines


def cmd_serve(args, open_browser: bool = False) -> int:
    import uvicorn

    from .api import create_app

    from .discovery import advertise

    host = "0.0.0.0" if args.lan else args.host
    try:
        app = create_app(trust_loopback=False if args.no_trust_local else None)
    except (OSError, ValueError) as e:  # an unusable admin token file
        print(f"cannot start: {e}", file=sys.stderr)
        return 2
    for name in config.CREDENTIAL_ENV:  # read by create_app; nothing the engine starts inherits them
        os.environ.pop(name, None)
    url, lines = serve_banner(app, host, args.port)
    print("\n".join(lines), flush=True)
    if open_browser:
        import threading
        import webbrowser

        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    on_lan = host not in ("127.0.0.1", "localhost", "::1") and not args.no_advertise
    addresses = (lan_addresses() if host in ("0.0.0.0", "::") else [host]) if on_lan else []
    with advertise(args.port, addresses, server_id=app.state.identity.server_id) as name:
        if name:
            print(f"Advertised on the LAN as \"{name}\" (_brasscribe._tcp)", flush=True)
        uvicorn.run(app, host=host, port=args.port, log_level="warning")
    return 0


def cmd_devices(args) -> int:
    from .companion import DeviceRegistry, ServerIdentity, reset_server

    s = config.load()
    registry = DeviceRegistry(s.state_dir / "devices.json", idle_days=s.device_idle_days)
    if args.action == "list":
        print(f"server id {ServerIdentity.load(s.state_dir).server_id}")
        for d in registry.list():
            p = d.public()
            print(f"{p['device_id']}  {p['name']:32s} {p['platform']:8s} paired {p['paired_at']}  last seen {p['last_seen']}")
        return 0
    if args.action == "revoke":
        if not args.device_id or not registry.revoke(args.device_id):
            print(f"no device {args.device_id}", file=sys.stderr)
            return 1
        print(f"revoked {args.device_id}")
        return 0
    ident = reset_server(s.state_dir)
    print(f"all devices forgotten; new server id {ident.server_id}. Every phone and tablet must pair again.")
    return 0


def cmd_manifest(args) -> int:
    s = config.load()
    if args.action == "show":
        print(Path(args.manifest).read_text())
        return 0
    overrides = {"emit": _print_event}
    if args.no_heavy:
        overrides["allow_heavy"] = False
    if args.cold:
        overrides["cold"] = _cold(args.cold)
    old, new = runner.rerun(s, args.manifest, **overrides)
    d = runner.diff_manifests(old, new)
    print(f"{new['status']}: {s.runs_dir / new['run_id']}")
    print(json.dumps(d, indent=1))
    return 0 if new["status"] == "succeeded" and not d["outputs_different"] else 1


def cmd_compare(args) -> int:
    from .compare import compare

    c = compare(args.candidate, args.reference)
    print(c.report())
    return 0 if c.ok else 2


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="brasscribe", description="brasscribe engine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a profile on a recording")
    r.add_argument("audio", type=Path)
    r.add_argument("--profile", default="orchestra-with-soloist", choices=list(profiles.PROFILES))
    r.add_argument("--out", type=Path, help="also copy final outputs here (never inside data/golden)")
    r.add_argument("--title")
    r.add_argument("--reuse", type=Path, help="song-pipeline output dir (mix.beats, stems/, layers/) to seed the cache from")
    r.add_argument("--no-heavy", action="store_true", help="fail instead of running a heavy model on a cache miss")
    r.add_argument("--cold", help="comma-separated stages or kinds to run even on a cache hit (e.g. layers,arrange,export)")
    r.add_argument("--no-audio", action="store_true", help="skip the MP3 rendering")
    r.add_argument("--lineup", choices=["full", "minimal", "quartet"],
                   help="default: the profile's (minimal for solo; quartet needs a recording of the whole group)")
    r.add_argument("--no-muscriptor", action="store_true", help="solo, brass-band: Basic Pitch in MuScriptor's place, as on device")
    r.add_argument("--difficulty", choices=["faithful", "standard", "easier"], default="faithful")
    r.add_argument("--key", help="target concert key: tonic (Bb, F#, Am) or FIFTHS[:MODE]")
    r.add_argument("--transpose", type=int, help="semitones (instead of --key)")
    r.add_argument("--seat", choices=SEAT_IDS, help="the player's seat: a solo take is written for it")
    r.add_argument("--reads", choices=["treble", "bass"], help="the clef of the seat's part (bass: at concert pitch)")
    r.add_argument("--lead", choices=["lineup", "seat"], default="lineup", help="who plays the tune (band lineups)")
    r.add_argument("--instrument", choices=list(tab.TUNINGS),
                   help="tab: the instrument (default guitar-6; bass-tab: a bass, default bass-4)")
    r.add_argument("--tuning", help="tab: the instrument's tuning, e.g. standard, drop-d, low-g (default: its first)")
    r.add_argument("--capo", type=int, help="tab: the capo's fret (default 0, none)")
    r.add_argument("--style", choices=list(bass_tab.STYLES), help="tab: where the notes sit on the neck (default as-played)")
    r.add_argument("--recording", choices=list(bass_tab.RECORDINGS),
                   help="tab: song separates the instrument from a band or a record (default); instrument: the instrument alone "
                        "(the default, and the only choice, for a ukulele or a mandolin)")
    r.add_argument("--octave", choices=list(bass_tab.OCTAVES),
                   help="tab: the octave the notes are written in, in semitones from what was heard (default auto: "
                        "moved an octave when they were heard an octave from the instrument)")
    r.add_argument("--layout", choices=list(bass_tab.LAYOUTS),
                   help="tab: what the page shows: the tab staff alone (default), with notation above it, or notation alone")
    r.add_argument("--check-golden", type=Path, help="compare outputs with a reference directory; exit 2 on difference")
    r.set_defaults(fn=cmd_run)

    b = sub.add_parser("bench", help="run a benchmark suite (or group: cpu, all) against eval/baselines.json")
    b.add_argument("suite")
    b.add_argument("--mode", choices=["cached", "live"], default="cached",
                   help="cached: score existing model outputs only; live: run adapters for missing outputs")
    b.add_argument("--json", type=Path)
    b.add_argument("--allow-improved", action="store_true", help="do not fail on improvements beyond the tolerance")
    b.add_argument("--require-data", action="store_true", help="fail when a suite is skipped for missing data")
    b.add_argument("--no-history", action="store_true", help="do not store the result under <data>/bench/history")
    b.set_defaults(fn=cmd_bench)

    for name, browser in (("serve", False), ("studio", True)):
        sv = sub.add_parser(name, help="start the HTTP engine" + (" and open Studio" if browser else ""))
        sv.add_argument("--host", default="127.0.0.1")
        sv.add_argument("--port", type=int, default=8765)
        sv.add_argument("--lan", action="store_true",
                        help="listen on all interfaces and print the LAN URL and pairing code for the Play apps")
        sv.add_argument("--no-advertise", action="store_true",
                        help="do not announce the engine over Bonjour/mDNS (_brasscribe._tcp) when on the LAN")
        sv.add_argument("--no-trust-local", action="store_true",
                        help="require a token from clients on this computer too (as BRASSCRIBE_TRUST_LOCAL=0); use "
                             "it when a proxy or tunnel on this computer forwards outside traffic to the engine")
        if browser:
            sv.add_argument("--no-browser", action="store_true")
            sv.set_defaults(fn=lambda a: cmd_serve(a, open_browser=not a.no_browser))
        else:
            sv.set_defaults(fn=cmd_serve)

    mf = sub.add_parser("manifest", help="show or re-run a run manifest")
    mf.add_argument("action", choices=["rerun", "show"])
    mf.add_argument("manifest", type=Path)
    mf.add_argument("--no-heavy", action="store_true")
    mf.add_argument("--cold")
    mf.set_defaults(fn=cmd_manifest)

    c = sub.add_parser("compare", help="compare score outputs with a reference directory")
    c.add_argument("candidate", type=Path)
    c.add_argument("reference", type=Path)
    c.set_defaults(fn=cmd_compare)

    dv = sub.add_parser("devices", help="list or revoke paired Play devices, or reset the engine's identity")
    dv.add_argument("action", nargs="?", choices=["list", "revoke", "reset"], default="list")
    dv.add_argument("device_id", nargs="?")
    dv.set_defaults(fn=cmd_devices)

    p = sub.add_parser("profiles", help="list profiles")
    p.set_defaults(fn=lambda a: print("\n".join(
        f"{x.name:24s} {x.pipeline:8s} {'validated' if x.validated else 'unvalidated'}  {x.description}"
        for x in profiles.PROFILES.values())) or 0)

    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except runner.RunRefused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
