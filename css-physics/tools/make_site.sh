#!/bin/bash
# tools/make_site.sh : build the published multi-page site into site/ (run from the repo root, ~2-4 min)
# site/rigid3d-N.html per body count (48 and 64 link split rigid3d-N.k.css files), site/rigid3d.html = the 24 page,
# site/index_artifact.html = the 24 page as a bare fragment for the artifact host.
set -e; mkdir -p site
DEFAULT=${DEFAULT:-24} python3 src/build3d.py site/rigid3d.html
python3 tools/artifact_index.py site/rigid3d.html site/index_artifact.html
ls -la site
