FROM mcr.microsoft.com/playwright:v1.63.0-noble

# Delete conflicting user with host ubuntu
RUN if id ubuntu >/dev/null 2>&1; then userdel -r ubuntu; fi \
 && apt-get update \
 && apt-get install -y --no-install-recommends make python3-pip fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/* \
 && ln -s /ms-playwright/chromium-*/chrome-linux*/chrome /usr/local/bin/chromium \
 && install -d -o pwuser -g pwuser /home/pwuser/.claude