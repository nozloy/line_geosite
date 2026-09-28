#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_REPOSITORY:?}" "${GITHUB_SHA:?}" "${GITHUB_REF:?}" "${GITHUB_EVENT_NAME:?}"
: "${GITHUB_RUN_ID:?}" "${GITHUB_RUN_ATTEMPT:?}" "${GH_TOKEN:?}"

if [[ "$GITHUB_REF" != refs/heads/main ]] ||
   [[ "$GITHUB_EVENT_NAME" != push && "$GITHUB_EVENT_NAME" != workflow_dispatch ]]; then
  echo 'Publication is allowed only for main pushes and manual main runs.' >&2
  exit 1
fi

main_head() {
  gh api "repos/$GITHUB_REPOSITORY/git/ref/heads/main" --jq '.object.sha'
}

current_head="$(main_head)"
if [[ "$current_head" != "$GITHUB_SHA" ]]; then
  echo 'Skipping an obsolete build; main already points to another commit.'
  exit 0
fi

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root/dist"
assets=()
for extension in dat srs mrs; do
  name="geosite_line.$extension"
  test -s "$name"
  sha256sum --check "$name.sha256sum"
  assets+=("$name" "$name.sha256sum")
done

temporary="$(mktemp -d)"
trap 'rm -rf -- "$temporary"' EXIT
tag="build-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}"
cat > "$temporary/notes.md" <<EOF
Domain lists built from commit $GITHUB_SHA.

- Xray / 3x-ui: geosite_line.dat, category line.
- sing-box / OpenWrt: geosite_line.srs, binary rule-set version 2 (sing-box 1.10+).
- Mihomo / Clash Mi: geosite_line.mrs, behavior domain, format mrs.
- All three files cover the same root domains and their subdomains.
- SHA-256 checksums are included for all three files.
EOF

gh release create "$tag" --repo "$GITHUB_REPOSITORY" --target "$GITHUB_SHA" \
  --draft --title "Domain lists $tag" --notes-file "$temporary/notes.md" "${assets[@]}"

# Confirm the draft contains the exact verified artifacts before making it public.
# A failed batch can leave partial files. Retry this read with --clobber so every
# file is downloaded again; never skip a partial file or retry release mutations.
for attempt in 1 2 3 4; do
  if gh release download "$tag" --repo "$GITHUB_REPOSITORY" --dir "$temporary/download" \
    --pattern 'geosite_line.*' --clobber; then
    break
  fi
  if [[ "$attempt" == 4 ]]; then
    echo 'Release verification download failed after 4 attempts; Latest is unchanged.' >&2
    exit 1
  fi
  delay=$((2 ** attempt))
  printf 'Download attempt %s/4 failed; retrying in %s seconds.\n' "$attempt" "$delay" >&2
  sleep "$delay"
done
for asset in "${assets[@]}"; do
  cmp -- "$asset" "$temporary/download/$asset"
done

current_head="$(main_head)"
if [[ "$current_head" != "$GITHUB_SHA" ]]; then
  echo "Main changed during upload; $tag stays a draft and Latest is unchanged."
  exit 0
fi
gh release edit "$tag" --repo "$GITHUB_REPOSITORY" --draft=false --latest

if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  for extension in dat srs mrs; do
    printf '[geosite_line.%s](https://github.com/%s/releases/latest/download/geosite_line.%s)\n\n' \
      "$extension" "$GITHUB_REPOSITORY" "$extension" >> "$GITHUB_STEP_SUMMARY"
  done
fi
