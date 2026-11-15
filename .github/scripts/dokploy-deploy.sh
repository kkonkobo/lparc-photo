#!/usr/bin/env bash
# Points a Dokploy application at a new image and redeploys it.
# Usage: dokploy-deploy.sh <applicationId> <image>
# Env: DOKPLOY_URL, DOKPLOY_API_KEY; optional GHCR_PULL_USER + GHCR_PULL_TOKEN for private images.
# Optional DOKPLOY_ORIGIN_IP: connect straight to the server instead of whatever DNS returns. Use it when
# the panel hostname is proxied by Cloudflare, which challenges GitHub's datacenter runners with an HTML
# 403. TLS is still verified against the panel hostname (curl --resolve keeps SNI and the certificate check).
set -euo pipefail
set +x

if [[ $# -ne 2 || -z "$1" || -z "$2" ]]; then
  printf 'Usage: bash dokploy-deploy.sh <application-id> <full-sha-image-or-digest>\n' >&2
  exit 2
fi

: "${DOKPLOY_URL:?Set DOKPLOY_URL}"
: "${DOKPLOY_API_KEY:?Set DOKPLOY_API_KEY}"
[[ "$DOKPLOY_URL" == https://* ]] || { printf 'DOKPLOY_URL must use HTTPS\n' >&2; exit 2; }
[[ "$DOKPLOY_API_KEY" != *$'\n'* && "$DOKPLOY_API_KEY" != *$'\r'* ]] || exit 2
resolve_args=()
if [[ -n "${DOKPLOY_ORIGIN_IP:-}" ]]; then
  [[ "$DOKPLOY_ORIGIN_IP" =~ ^[0-9]{1,3}(\.[0-9]{1,3}){3}$ ]] || { printf 'DOKPLOY_ORIGIN_IP must be an IPv4 address\n' >&2; exit 2; }
  dokploy_host=${DOKPLOY_URL#https://}
  dokploy_host=${dokploy_host%%/*}
  dokploy_host=${dokploy_host%%:*}
  resolve_args=(--resolve "$dokploy_host:443:$DOKPLOY_ORIGIN_IP")
fi
if [[ -n "${GHCR_PULL_USER:-}" && -z "${GHCR_PULL_TOKEN:-}" ]] || [[ -z "${GHCR_PULL_USER:-}" && -n "${GHCR_PULL_TOKEN:-}" ]]; then
  printf 'Set both GHCR_PULL_USER and GHCR_PULL_TOKEN, or neither\n' >&2
  exit 2
fi

application_id="$1"
image="$2"
umask 077
request_dir=$(mktemp -d)
trap 'rm -rf "$request_dir"' EXIT
printf 'x-api-key: %s\n' "$DOKPLOY_API_KEY" > "$request_dir/headers"
jq -n --arg id "$application_id" --arg image "$image" '
  {applicationId: $id, dockerImage: $image}
  + (if (env.GHCR_PULL_TOKEN // "") != "" then
      {username: env.GHCR_PULL_USER, password: env.GHCR_PULL_TOKEN, registryUrl: "ghcr.io"}
     else {username: null, password: null, registryUrl: null} end)
' > "$request_dir/provider.json"
jq -n --arg id "$application_id" '{applicationId: $id}' > "$request_dir/deploy.json"

classify_error() {
  local body="$1"
  local low
  low=$(printf '%s' "$body" | tr '[:upper:]' '[:lower:]')
  if [[ "$low" == *error-1010* || "$low" == *'error code: 1010'* ]]; then
    printf 'cloudflare_1010_browser_signature'
  elif [[ "$low" == *cloudflare* ]]; then
    printf 'cloudflare_block'
  elif [[ "$low" == *unauthorized* ]]; then
    printf 'unauthorized'
  elif [[ "$low" == *forbidden* || "$low" == *permission* || "$low" == *'not allowed'* ]]; then
    printf 'permission_or_forbidden'
  elif [[ "$low" == *'<!doctype'* || "$low" == *'<html'* ]]; then
    printf 'html_block_page'
  elif [[ -z "${body//[[:space:]]/}" ]]; then
    printf 'empty_body'
  else
    printf 'other'
  fi
}

call_api() {
  local endpoint="$1"
  local payload="$2"
  local status
  # Retry only when no connection was ever made (nothing reached Dokploy, so nothing can be applied
  # twice). A failure after connecting is not retried: application.deploy would queue a second build.
  local attempt=1 rc
  while :; do
    : > "$request_dir/response.body"
    : > "$request_dir/response.headers"
    set +e
    status=$(curl --silent --show-error --connect-timeout 15 --max-time 90 \
      ${resolve_args[@]+"${resolve_args[@]}"} \
      --request POST "${DOKPLOY_URL%/}/api/$endpoint" \
      --dump-header "$request_dir/response.headers" \
      --header @"$request_dir/headers" \
      --header 'Content-Type: application/json' \
      --header 'User-Agent: Dokploy-Deploy/1.0' \
      --data-binary @"$payload" \
      --output "$request_dir/response.body" \
      --write-out '%{http_code}' 2>"$request_dir/curl.err")
    rc=$?
    set -e
    [[ $rc -eq 0 ]] && break
    if [[ $attempt -lt 3 ]] && grep -qE 'Failed to connect|Could not resolve host|Connection refused|Connection timed out' "$request_dir/curl.err"; then
      printf 'Dokploy API %s: no connection (attempt %d/3), retrying\n' "$endpoint" "$attempt" >&2
      sleep $(( attempt * ${DOKPLOY_RETRY_DELAY:-10} ))
      attempt=$((attempt + 1))
      continue
    fi
    cat "$request_dir/curl.err" >&2
    printf 'Dokploy API %s failed: category=transport_error\n' "$endpoint" >&2
    exit 22
  done
  if [[ "$status" =~ ^2[0-9][0-9]$ ]]; then
    return 0
  fi
  local body category title ray mitigated
  body=$(tr -d '\0' < "$request_dir/response.body" | tr '\n' ' ' | cut -c1-4000)
  category=$(classify_error "$body")
  # Safe diagnostics only: the block page's title and the proxy's request id, never the body or headers wholesale.
  title=$(printf '%s' "$body" | sed -n 's:.*<title>\([^<]*\)</title>.*:\1:p' | cut -c1-120)
  ray=$(grep -i '^cf-ray:' "$request_dir/response.headers" 2>/dev/null | tr -d '\r' | cut -d' ' -f2 | head -1 || true)
  mitigated=$(grep -i '^cf-mitigated:' "$request_dir/response.headers" 2>/dev/null | tr -d '\r' | cut -d' ' -f2 | head -1 || true)
  printf 'Dokploy API %s failed: HTTP %s category=%s title=%q cf-ray=%s cf-mitigated=%s via=%s\n' \
    "$endpoint" "$status" "$category" "${title:-}" "${ray:-none}" "${mitigated:-none}" "$( [[ -n "${DOKPLOY_ORIGIN_IP:-}" ]] && printf origin || printf dns )" >&2
  exit 22
}

call_api application.saveDockerProvider "$request_dir/provider.json"
call_api application.deploy "$request_dir/deploy.json"
printf 'Deployment requested for %s. Verify Dokploy completion and running version.\n' "$image"
