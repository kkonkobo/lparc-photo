#!/usr/bin/env bash
set -euo pipefail

root="$(cd "$(dirname "$0")" && pwd)"
script="$root/dokploy-deploy.sh"
fail() { printf 'FAIL: %s\n' "$*" >&2; exit 1; }
pass() { printf 'ok: %s\n' "$*"; }

tmpdir=$(mktemp -d)
trap 'rm -rf "$tmpdir"' EXIT
mkdir -p "$tmpdir/bin"

cat > "$tmpdir/bin/curl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
log="${MOCK_CURL_LOG:?}"
body_file=""
write_out=""
header_file=""
args=("$@")
i=0
while [[ $i -lt ${#args[@]} ]]; do
  case "${args[$i]}" in
    --output)
      i=$((i + 1)); body_file="${args[$i]}" ;;
    --write-out)
      i=$((i + 1)); write_out="${args[$i]}" ;;
    --dump-header)
      i=$((i + 1)); header_file="${args[$i]}" ;;
  esac
  i=$((i + 1))
done
printf '%s\n' "${args[*]}" >> "$log"
case "${MOCK_CURL_MODE:-ok}" in
  ok)
    [[ -n "$body_file" ]] && printf '{"ok":true}\n' > "$body_file"
    [[ "$write_out" == '%{http_code}' ]] && printf '200'
    ;;
  cf1010)
    [[ -n "$body_file" ]] && printf 'error code: 1010\n' > "$body_file"
    [[ "$write_out" == '%{http_code}' ]] && printf '403'
    ;;
  htmlblock)
    [[ -n "$body_file" ]] && printf '<!DOCTYPE html><html><head><title>Just a moment...</title></head><body>secret-looking-body</body></html>' > "$body_file"
    [[ -n "$header_file" ]] && printf 'HTTP/2 403\r\ncf-ray: 8f00test-LHR\r\ncf-mitigated: challenge\r\n\r\n' > "$header_file"
    [[ "$write_out" == '%{http_code}' ]] && printf '403'
    ;;
  unauthorized)
    [[ -n "$body_file" ]] && printf '{"message":"Unauthorized"}\n' > "$body_file"
    [[ "$write_out" == '%{http_code}' ]] && printf '401'
    ;;
  connectfail)
    # Fail to connect the first $MOCK_CONNECT_FAILURES times (counted in a file), then behave like ok.
    count_file="${MOCK_COUNT_FILE:?}"
    count=$(cat "$count_file" 2>/dev/null || echo 0)
    if [[ $count -lt ${MOCK_CONNECT_FAILURES:-2} ]]; then
      echo $((count + 1)) > "$count_file"
      echo 'curl: (28) Failed to connect to panel port 443 after 15002 ms: Timeout was reached' >&2
      exit 28
    fi
    [[ -n "$body_file" ]] && printf '{"ok":true}\n' > "$body_file"
    [[ "$write_out" == '%{http_code}' ]] && printf '200'
    ;;
  transport)
    [[ -n "$body_file" ]] && printf '{"partial":' > "$body_file"
    printf '200'
    exit 18
    ;;
  *)
    exit 99
    ;;
esac
EOF
chmod +x "$tmpdir/bin/curl"

export PATH="$tmpdir/bin:/usr/bin:/bin"
export DOKPLOY_URL='https://dokploy.example.test'
export DOKPLOY_API_KEY='test-key-not-real'
unset GHCR_PULL_USER GHCR_PULL_TOKEN || true

log1="$tmpdir/curl-ok.log"
: > "$log1"
MOCK_CURL_LOG="$log1" MOCK_CURL_MODE=ok \
  bash "$script" 'app-id-1' 'ghcr.io/example/app:abc123' >"$tmpdir/out-ok.txt" 2>"$tmpdir/err-ok.txt"
grep -q 'Deployment requested for ghcr.io/example/app:abc123' "$tmpdir/out-ok.txt" || fail 'success message missing'
grep -q 'User-Agent: Dokploy-Deploy/1.0' "$log1" || fail 'User-Agent not sent'
grep -q 'application.saveDockerProvider' "$log1" || fail 'provider call missing'
grep -q 'application.deploy' "$log1" || fail 'deploy call missing'
grep -q -- '--header @' "$log1" || fail 'api key should be passed via header file'
! grep -q 'test-key-not-real' "$log1" || fail 'api key value leaked into curl argv'
pass 'happy path sends UA and both endpoints'

log2="$tmpdir/curl-cf.log"
: > "$log2"
set +e
MOCK_CURL_LOG="$log2" MOCK_CURL_MODE=cf1010 \
  bash "$script" 'app-id-1' 'ghcr.io/example/app:abc123' >"$tmpdir/out-cf.txt" 2>"$tmpdir/err-cf.txt"
rc=$?
set -e
[[ "$rc" -eq 22 ]] || fail "expected exit 22 on CF 1010, got $rc"
grep -q 'HTTP 403 category=cloudflare_1010_browser_signature' "$tmpdir/err-cf.txt" || fail "missing CF category: $(cat "$tmpdir/err-cf.txt")"
grep -q 'User-Agent: Dokploy-Deploy/1.0' "$log2" || fail 'UA missing on error path'
pass 'CF 1010 classified without leaking body noise'

log3="$tmpdir/curl-401.log"
: > "$log3"
set +e
MOCK_CURL_LOG="$log3" MOCK_CURL_MODE=unauthorized \
  bash "$script" 'app-id-1' 'ghcr.io/example/app:abc123' >"$tmpdir/out-401.txt" 2>"$tmpdir/err-401.txt"
rc=$?
set -e
[[ "$rc" -eq 22 ]] || fail "expected exit 22 on 401, got $rc"
grep -q 'HTTP 401 category=unauthorized' "$tmpdir/err-401.txt" || fail "missing unauthorized category: $(cat "$tmpdir/err-401.txt")"
pass '401 classified as unauthorized'

log4="$tmpdir/curl-transport.log"
: > "$log4"
set +e
MOCK_CURL_LOG="$log4" MOCK_CURL_MODE=transport \
  bash "$script" 'app-id-1' 'ghcr.io/example/app:abc123' >"$tmpdir/out-transport.txt" 2>"$tmpdir/err-transport.txt"
rc=$?
set -e
[[ "$rc" -eq 22 ]] || fail "expected exit 22 on transport failure, got $rc"
grep -q 'category=transport_error' "$tmpdir/err-transport.txt" || fail 'missing transport error'
! grep -q 'application.deploy' "$log4" || fail 'transport failure must stop deployment'
pass 'transport failure does not accept a partial HTTP 200'

log5="$tmpdir/curl-html.log"
: > "$log5"
set +e
MOCK_CURL_LOG="$log5" MOCK_CURL_MODE=htmlblock \
  bash "$script" 'app-id-1' 'ghcr.io/example/app:abc123' >"$tmpdir/out-html.txt" 2>"$tmpdir/err-html.txt"
rc=$?
set -e
[[ "$rc" -eq 22 ]] || fail "expected exit 22 on HTML block page, got $rc"
grep -q 'cf-ray=8f00test-LHR cf-mitigated=challenge via=dns' "$tmpdir/err-html.txt" || fail "missing proxy diagnostics: $(cat "$tmpdir/err-html.txt")"
grep -q "title=Just" "$tmpdir/err-html.txt" || fail "missing page title: $(cat "$tmpdir/err-html.txt")"
! grep -q 'secret-looking-body' "$tmpdir/err-html.txt" || fail 'body leaked into the log'
! grep -q -- '--resolve' "$log5" || fail 'no --resolve expected without DOKPLOY_ORIGIN_IP'
pass 'HTML block page reports title, cf-ray and cf-mitigated without the body'

log6="$tmpdir/curl-origin.log"
: > "$log6"
DOKPLOY_URL='https://panel.example.test/' DOKPLOY_ORIGIN_IP='203.0.113.7' MOCK_CURL_LOG="$log6" MOCK_CURL_MODE=ok \
  bash "$script" 'app-id-1' 'ghcr.io/example/app:abc123' >/dev/null
[[ $(grep -c -- '--resolve panel.example.test:443:203.0.113.7' "$log6") -eq 2 ]] || fail "both calls must pin the origin: $(cat "$log6")"
grep -q 'https://panel.example.test/api/application.saveDockerProvider' "$log6" || fail 'URL must keep the hostname for TLS verification'
pass 'DOKPLOY_ORIGIN_IP pins both calls to the origin and keeps the hostname'

set +e
DOKPLOY_ORIGIN_IP='not-an-ip' MOCK_CURL_LOG="$tmpdir/unused.log" bash "$script" 'app-id-1' 'img' >/dev/null 2>"$tmpdir/err-badip.txt"
rc=$?
set -e
[[ "$rc" -eq 2 ]] || fail "expected exit 2 on a bad origin IP, got $rc"
pass 'invalid DOKPLOY_ORIGIN_IP is rejected before any request'

export DOKPLOY_RETRY_DELAY=0

log7="$tmpdir/curl-connect.log"
: > "$log7"
MOCK_CURL_LOG="$log7" MOCK_CURL_MODE=connectfail MOCK_CONNECT_FAILURES=2 MOCK_COUNT_FILE="$tmpdir/count7" \
  bash "$script" 'app-id-1' 'ghcr.io/example/app:abc123' >"$tmpdir/out-connect.txt" 2>"$tmpdir/err-connect.txt"
grep -q 'Deployment requested' "$tmpdir/out-connect.txt" || fail "expected success after connect retries: $(cat "$tmpdir/err-connect.txt")"
[[ $(grep -c 'no connection' "$tmpdir/err-connect.txt") -eq 2 ]] || fail 'expected two retry notices'
pass 'connection failures are retried until the request gets through'

log8="$tmpdir/curl-connect-down.log"
: > "$log8"
set +e
MOCK_CURL_LOG="$log8" MOCK_CURL_MODE=connectfail MOCK_CONNECT_FAILURES=99 MOCK_COUNT_FILE="$tmpdir/count8" \
  bash "$script" 'app-id-1' 'ghcr.io/example/app:abc123' >/dev/null 2>"$tmpdir/err-down.txt"
rc=$?
set -e
[[ "$rc" -eq 22 ]] || fail "expected exit 22 when the panel stays unreachable, got $rc"
[[ $(grep -c 'saveDockerProvider' "$log8") -eq 3 ]] || fail 'expected exactly three attempts'
! grep -q 'application.deploy' "$log8" || fail 'must not deploy when the provider update never connected'
grep -q 'Failed to connect' "$tmpdir/err-down.txt" || fail 'curl error should be shown'
pass 'an unreachable panel stops after three connection attempts'

printf 'All dokploy-deploy tests passed.\n'
