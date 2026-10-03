# Whether a pixi version meets a version spec such as requires-pixi in pixi.toml.
#
#   awk -v spec='>=0.80,<1' -v version=0.81.0 -f pixi-spec.awk
#
# Exits 0 when it does, 1 when it doesn't, 2 when the spec can't be read (the message is on stderr).
# The spec is a conda-style version spec, as pixi reads it: constraints separated by `,` must all hold,
# alternatives separated by `|` need one to hold. A constraint is `*`, `OP VERSION` with OP one of
# >= > <= < == != ~= =, or a bare VERSION. `1.2.*` (bare, `==` or `=`) and `=1.2` match every 1.2
# release, `!=1.2.*` none of them, a bare `1.2` only 1.2 itself, and `~=1.2.3` means >=1.2.3 and 1.2.*.
# Versions compare by their numeric parts, missing parts counting as 0 (0.80 is 0.80.0); a pre-release
# suffix is not part of the comparison.

function bad(why) {
  printf "pixi-spec: %s in '%s'\n", why, spec > "/dev/stderr"
  exit 2
}

function trim(s) { gsub(/^[ \t]+|[ \t]+$/, "", s); return s }

# -1, 0 or 1 as a is lower than, equal to or higher than b.
function cmp(a, b,    na, nb, pa, pb, i, n, x, y) {
  na = split(a, pa, ".")
  nb = split(b, pb, ".")
  n = na > nb ? na : nb
  for (i = 1; i <= n; i++) {
    x = (i <= na) ? pa[i] + 0 : 0
    y = (i <= nb) ? pb[i] + 0 : 0
    if (x < y) return -1
    if (x > y) return 1
  }
  return 0
}

# The numeric parts of a version: "0.81.0" from "v0.81.0" or "0.81.0rc1".
function numeric(v,    m) {
  sub(/^v/, "", v)
  if (match(v, /^[0-9]+(\.[0-9]+)*/) == 0) return ""
  return substr(v, 1, RLENGTH)
}

# v is a release of the series `prefix` (1.2 for 1.2.*): its first parts equal prefix's.
function inseries(v, prefix,    pv, pp, n, i) {
  n = split(prefix, pp, ".")
  split(v, pv, ".")
  for (i = 1; i <= n; i++) if (pv[i] + 0 != pp[i] + 0) return 0
  return 1
}

function holds(c, v,    op, rest, want, star, parts, n, i, series) {
  c = trim(c)
  if (c == "") bad("an empty constraint")
  if (c == "*") return 1
  if (match(c, /^(>=|<=|==|!=|~=|>|<|=)/)) {
    op = substr(c, 1, RLENGTH)
    rest = trim(substr(c, RLENGTH + 1))
  } else {
    op = ""
    rest = c
  }
  star = 0
  if (rest ~ /\.\*$/) { star = 1; rest = substr(rest, 1, length(rest) - 2) }
  else if (rest ~ /\*$/) bad("a wildcard that isn't a whole part (`" c "`)")
  if (rest !~ /^[0-9]+(\.[0-9]+)*$/) bad("no version in `" c "`")
  if (star && op != "" && op != "==" && op != "=" && op != "!=") bad("a wildcard after `" op "`")

  if (op == "=" || star) {
    series = inseries(v, rest)
    return op == "!=" ? !series : series
  }
  if (op == "" || op == "==") return cmp(v, rest) == 0
  if (op == "!=") return cmp(v, rest) != 0
  if (op == ">=") return cmp(v, rest) >= 0
  if (op == ">")  return cmp(v, rest) > 0
  if (op == "<=") return cmp(v, rest) <= 0
  if (op == "<")  return cmp(v, rest) < 0
  if (op == "~=") {
    n = split(rest, parts, ".")
    if (n < 2) bad("`~=` with only one part (`" c "`)")
    series = parts[1]
    for (i = 2; i < n; i++) series = series "." parts[i]
    return cmp(v, rest) >= 0 && inseries(v, series)
  }
  bad("an unknown operator in `" c "`")
}

BEGIN {
  v = numeric(version)
  if (v == "") { printf "pixi-spec: no version in '%s'\n", version > "/dev/stderr"; exit 2 }
  if (trim(spec) == "") bad("no constraint")
  nalt = split(spec, alts, "|")
  ok = 0
  for (a = 1; a <= nalt; a++) {
    nall = split(alts[a], all, ",")
    this = 1
    for (k = 1; k <= nall; k++) if (!holds(all[k], v)) this = 0
    if (this) ok = 1
  }
  exit ok ? 0 : 1
}
