# Playwright's image: Ubuntu 24.04, Node 24, git, Python 3.12, and Playwright's browsers with their system
# libraries, for amd64 and arm64. v1.63.0 bundles Chromium 153.0.8010.12, the engine the tests and
# docs/ENGINE_NOTES.md were checked on. A newer tag means a newer Chrome: run make l3 and make l5-smoke after bumping.
FROM mcr.microsoft.com/playwright:v1.63.0-noble

# Added: make; pip; DejaVu Sans Mono (readback/mkfont2.py builds the readback font from it).
# /usr/local/bin/chromium gives CHROME one path on both architectures (chrome-linux64 / chrome-linux-arm64).
# ~/.claude is created owned by pwuser so the volume mounted there starts out writable.
RUN apt-get update \
 && apt-get install -y --no-install-recommends make python3-pip fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/* \
 && ln -s /ms-playwright/chromium-*/chrome-linux*/chrome /usr/local/bin/chromium \
 && install -d -o pwuser -g pwuser /home/pwuser/.claude