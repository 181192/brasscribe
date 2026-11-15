#!/usr/bin/env bash
# Uploads one app's signed bundle (.aab) to Google Play's internal testing track (docs/shared/dev/release.md):
#
#   scripts/play-upload.sh [--dry-run] --track internal --cert SHA256 --notes-en FILE --notes-nb FILE app.aab
#
# The service account's JSON key comes from the environment, PLAY_SERVICE_ACCOUNT_JSON (its contents, not a path).
# The package is read from the bundle, and the bundle must be signed with --cert alone (check-aab.py), so a wrong or
# replaced file is refused before anything reaches Play. Steps (Android Publisher API v3): sign a JWT (RS256) for the service account
# and trade it for an access token with the androidpublisher scope; open an edit; upload the bundle; give the internal
# track a completed release of that version code with the notes in en-US and no-NO; commit the edit. On any failure
# after the edit is open, the edit is deleted, so nothing half-done is left for the next run. Only `internal` is
# accepted. --dry-run checks the bundle, the notes and the key's fields, prints what it would do and calls nothing.
#
# The private key is kept in shell variables only: the variable is taken out of the environment before any other
# program starts, openssl reads the key from a pipe, it is never written to a file or printed, and in GitHub Actions
# the key's lines, the signed JWT and the access token are masked. It refuses to run with xtrace on (bash -x would
# print the key). Needs curl, openssl and python3.
case $- in *x*) echo "play-upload: refusing to run with xtrace on (set -x or bash -x): it would print the key" >&2; exit 2 ;; esac
# Out of the environment first: no program this script starts inherits the key.
account=${PLAY_SERVICE_ACCOUNT_JSON:-}
unset PLAY_SERVICE_ACCOUNT_JSON
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API="https://androidpublisher.googleapis.com"
SCOPE="https://www.googleapis.com/auth/androidpublisher"
NOTES_LIMIT=500

die() { echo "play-upload: $*" >&2; exit 1; }
mask() { [ -z "${GITHUB_ACTIONS:-}" ] || echo "::add-mask::$1"; }
usage() { sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//' >&2; exit 2; }

dry=false track="" cert="" notes_en="" notes_nb="" aab=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) dry=true ;;
    --track) track=${2:-}; shift ;;
    --cert) cert=${2:-}; shift ;;
    --notes-en) notes_en=${2:-}; shift ;;
    --notes-nb) notes_nb=${2:-}; shift ;;
    -h|--help) usage ;;
    -*) die "unknown option $1" ;;
    *) [ -z "$aab" ] || die "one bundle at a time"; aab=$1 ;;
  esac
  shift
done
[[ -n $aab && -n $track && -n $cert && -n $notes_en && -n $notes_nb ]] || usage
[ "$track" = internal ] || die "only the internal testing track is allowed, not '$track'"
[ -f "$aab" ] || die "no bundle at $aab"
for f in "$notes_en" "$notes_nb"; do
  [ -f "$f" ] || die "no notes file at $f"
  n=$(python3 -c 'import sys; print(len(open(sys.argv[1], encoding="utf-8").read().rstrip("\n")))' "$f")
  (( n > 0 && n <= NOTES_LIMIT )) || die "$f has $n characters; Play takes 1 to $NOTES_LIMIT"
done

package=$("$ROOT/.github/scripts/check-aab.py" --print package "$aab") || die "cannot read the package of $aab"
code=$("$ROOT/.github/scripts/check-aab.py" --print versionCode "$aab") || die "cannot read the version code of $aab"
[[ $package =~ ^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$ ]] || die "'$package' is not a package name"
[[ $code =~ ^[0-9]+$ ]] || die "'$code' is not a version code"
"$ROOT/.github/scripts/check-aab.py" --cert "$cert" --package "$package" "$aab" >/dev/null \
  || die "$(basename "$aab") is not signed with the given certificate alone; nothing was uploaded"

# The service account's fields. The key goes from python straight into a shell variable.
[ -n "$account" ] || die "PLAY_SERVICE_ACCOUNT_JSON is not set"
field() {
  printf '%s' "$account" | python3 -c '
import json, sys
try:
    v = json.load(sys.stdin).get(sys.argv[1], "")
except ValueError:
    sys.exit("PLAY_SERVICE_ACCOUNT_JSON is not JSON")
sys.stdout.write(v if isinstance(v, str) else "")' "$1"
}
email=$(field client_email) || die "cannot read the service account key"
token_uri=$(field token_uri) || die "cannot read the service account key"
key=$(field private_key) || die "cannot read the service account key"
[[ -n $email && -n $key ]] || die "the service account key has no client_email or private_key"
[[ $key == "-----BEGIN PRIVATE KEY-----"* ]] || die "the service account's private_key is not a PEM private key"
unset account
# GitHub masks the secret as a whole; its lines are masked too, should one ever be printed on its own.
while IFS= read -r line; do
  [[ -z $line || $line == -----* ]] || mask "$line"
done < <(printf "%s\n" "$key")
token_uri=${token_uri:-https://oauth2.googleapis.com/token}
[[ $token_uri == https://* ]] || die "the service account's token_uri is not https"

if $dry; then
  echo "play-upload: dry run: would upload $(basename "$aab") ($package, version code $code) to the $track track"
  echo "play-upload: as $email; notes: $(wc -c < "$notes_en" | tr -d ' ') bytes en-US, $(wc -c < "$notes_nb" | tr -d ' ') bytes no-NO"
  exit 0
fi

b64url() { openssl base64 -A | tr '+/' '-_' | tr -d '='; }

# JWT (RS256), valid ten minutes.
now=$(date +%s)
header=$(printf '{"alg":"RS256","typ":"JWT"}' | b64url)
claims=$(python3 -c 'import json, sys; print(json.dumps({"iss": sys.argv[1], "scope": sys.argv[2], "aud": sys.argv[3],
  "iat": int(sys.argv[4]), "exp": int(sys.argv[4]) + 600}, separators=(",", ":")), end="")' \
  "$email" "$SCOPE" "$token_uri" "$now" | b64url)
signature=$(printf '%s' "$header.$claims" | openssl dgst -sha256 -sign <(printf '%s\n' "$key") | b64url) \
  || die "cannot sign the token request with the service account's key"
unset key
jwt="$header.$claims.$signature"
mask "$jwt"

# One call: the body on stdin (or the file given), the response on stdout; a non-2xx status fails with Google's
# message. The token goes to curl through a pipe (-K), so it is not in the process list.
call() {  # METHOD URL [content-type [file]]
  local out status body data=(--data-binary @-)
  [ -z "${4:-}" ] || data=(--upload-file "$4")
  out=$(curl -sS -K <(printf 'header = "Authorization: Bearer %s"\n' "$token") -X "$1" "$2" \
        -H "Content-Type: ${3:-application/json}" "${data[@]}" -w '\n%{http_code}') || return 1
  status=${out##*$'\n'} body=${out%$'\n'*}
  [[ $status == 2* ]] || { echo "play-upload: $1 ${2#"$API"} answered $status: $body" >&2; return 1; }
  printf '%s' "$body"
}
json() { python3 -c 'import json, sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"; }

out=$(curl -sS -X POST "$token_uri" -H "Content-Type: application/x-www-form-urlencoded" \
      --data-urlencode "grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer" --data-urlencode "assertion@-" \
      -w '\n%{http_code}' < <(printf '%s' "$jwt")) || die "the token request failed"
[[ ${out##*$'\n'} == 2* ]] || die "the token request was refused (${out##*$'\n'}): ${out%$'\n'*}"
token=$(printf '%s' "${out%$'\n'*}" | json access_token) || die "no access token in the answer"
mask "$token"
unset jwt out

app="$API/androidpublisher/v3/applications/$package"
edit=$(call POST "$app/edits" </dev/null | json id) || die "cannot open an edit for $package"
cleanup() {
  if [ -n "${edit:-}" ]; then
    call DELETE "$app/edits/$edit" </dev/null >/dev/null && echo "play-upload: the edit was deleted; nothing changed on Play" >&2 \
      || echo "play-upload: the edit could not be deleted either; it expires on its own" >&2
  fi
}
trap cleanup EXIT

uploaded=$(call POST "${API}/upload/androidpublisher/v3/applications/$package/edits/$edit/bundles?uploadType=media" \
           application/octet-stream "$aab" | json versionCode) || die "the bundle upload failed"
[ "$uploaded" = "$code" ] || die "Play read version code $uploaded from the bundle, not $code"

python3 - "$code" "$notes_en" "$notes_nb" <<'EOF' | call PUT "$app/edits/$edit/tracks/internal" >/dev/null || die "cannot set the internal track"
import json, sys
code, en, nb = sys.argv[1:4]
read = lambda p: open(p, encoding="utf-8").read().rstrip("\n")
print(json.dumps({"track": "internal", "releases": [{"versionCodes": [code], "status": "completed", "releaseNotes": [
    {"language": "en-US", "text": read(en)}, {"language": "no-NO", "text": read(nb)}]}]}))
EOF

call POST "$app/edits/$edit:commit" </dev/null >/dev/null || die "the edit could not be committed"
edit=""
echo "play-upload: $package version code $code is on the internal testing track"
