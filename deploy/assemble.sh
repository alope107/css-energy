#!/usr/bin/env bash
# Assemble one project's deployable site: deploy/assemble.sh <project> <outdir>
# CI runs this in the build job and uploads <outdir> to a Cloudflare Worker unchanged; run it locally to see exactly
# what will be deployed. See deploy/README.md.
set -euo pipefail
project=${1:?usage: assemble.sh css-physics|js-minus-js|paint <outdir>}
out=${2:?usage: assemble.sh <project> <outdir>}
root=$(cd "$(dirname "$0")/.." && pwd)

rm -rf "$out"
mkdir -p "$out"
out=$(cd "$out" && pwd)

case "$project" in
  css-physics)
    # the 16-body page as index.html, linking index-N.html for 8–64 (~35 s, stdlib Python)
    (cd "$root/css-physics" && python3 src/build3d.py "$out/index.html")
    # the face-widgets experiment the pages link to (widgets.html + widgets-tv.webm)
    (cd "$root/css-physics" && python3 experiments/widgets/build.py "$out/widgets.html")
    ;;
  js-minus-js)
    # dist/ is the released page (make page && make l5-smoke, then make dist); serve it at /
    cp "$root/js-minus-js/dist/js_in_css.xhtml" "$out/"
    cp "$root/js-minus-js/dist/repl.xhtml" "$out/"       # the REPL's page, which the program page links to
    printf '/ /js_in_css.xhtml 302\n' > "$out/_redirects"
    ;;
  paint)
    # site/ is committed and deployed as is: its d/*.png bytes must never change (paint/CLAUDE.md)
    cp -R "$root/paint/site/." "$out/"
    ;;
  *)
    echo "unknown project: $project" >&2
    exit 2
    ;;
esac

echo "$project -> $out: $(find "$out" -type f | wc -l) files, $(du -sh "$out" | cut -f1)" >&2
