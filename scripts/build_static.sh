#!/usr/bin/env bash
# Build the public static site into web/out (hosted on GitHub Pages by .github/workflows/pages.yml).
#   scripts/build_static.sh [base-path]     e.g. scripts/build_static.sh /argus-aiops
# Data comes from web/public/snapshot, recorded by `python -m scripts.snapshot`. The API proxy route cannot be exported,
# so it is moved aside for the build and always put back.
set -euo pipefail
cd "$(dirname "$0")/../web"
BASE="${1:-}"
[[ -d public/snapshot ]] || { echo "no web/public/snapshot: run  uv run python -m scripts.snapshot  first" >&2; exit 1; }
pgrep -f "next dev" >/dev/null && { echo "stop the Next dev server first: it holds web/.next open" >&2; exit 1; }
ASIDE="$(mktemp -d)"
mv app/api "$ASIDE/api"
trap 'mv "$ASIDE/api" app/api; rmdir "$ASIDE"' EXIT
rm -rf out .next  # a stale .next (from `next dev`) still points at the moved route
NEXT_PUBLIC_STATIC=1 NEXT_PUBLIC_BASE_PATH="$BASE" npx next build
touch out/.nojekyll
echo "built web/out ($(find out -type f | wc -l | tr -d ' ') files, $(du -sh out | cut -f1))"
