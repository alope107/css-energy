# Deploying to Cloudflare Workers

`.github/workflows/deploy.yml` uploads each project's built site to its own Worker as static assets (no Worker
script). `deploy/assemble.sh <project> <dir>` builds exactly what CI uploads.

| Event | Result |
|---|---|
| push to `main` | production deploy of each changed project: `https://<worker>.auberon.workers.dev` |
| push to any other branch | a preview version (no production traffic) of each project changed since leaving `main`: `https://<version>-<worker>.auberon.workers.dev` (this commit) and `https://<branch>-<worker>.auberon.workers.dev` (latest) |
| Actions → deploy → Run workflow | the projects you name, from the branch you pick |

A change under `deploy/` or to the workflow deploys all three; `shared/`, `engine/` and top-level docs deploy nothing.

| Project | Site | Worker |
|---|---|---|
| css-physics | built in CI: `src/build3d.py` → `index.html` + `index-N.html` (~35 s) | `css-physics` |
| js-minus-js | the committed `dist/js_in_css.xhtml` (`/` redirects to it); CI warns if `make dist` no longer reproduces it | `js-minus-js` |
| paint | the committed `site/`, unchanged | `paint` |

Repo variables can override the names (`WORKER_CSS_PHYSICS`, `WORKER_JS_MINUS_JS`, `WORKER_PAINT`,
`WORKERS_DEV_SUBDOMAIN`). The deploy job writes the Worker's whole configuration (assets directory,
`html_handling: auto-trailing-slash`, `not_found_handling: none`, `workers_dev` and `preview_urls` on, a fixed
compatibility date), so dashboard changes are overwritten.

**Cost:** static-asset requests are free and unlimited. Keep it that way: no Worker script, no `run_worker_first`, no
`cache` block (with Workers Cache on, every request is billed).

## Setup (done)

- Cloudflare API token: *Account · Workers Scripts · Edit*, this account only. It can deploy or delete any Worker in
  the account.
- GitHub: environment `production` restricted to `main`, environment `preview` unrestricted, both with secret
  `CLOUDFLARE_API_TOKEN`; Actions variable `CLOUDFLARE_ACCOUNT_ID`.
- The devcontainer's `GH_TOKEN` (fine-grained, this repo): Contents and Pull requests read/write, Actions read.
  **Workflows, Secrets, Environments, Deployments, Administration: no access** — the trust model depends on it. No
  Cloudflare token in the devcontainer.
- A new Worker is created by its first production deploy, which also turns on its preview URLs.

## Trust model

Agents write code and push branches; a push runs a workflow holding a token that can deploy. The token stays out of
reach of anything an agent writes:

- **Agents can't change the workflow:** GitHub rejects pushes touching `.github/workflows/` from a token without the
  Workflows permission.
- **The deploy job runs no repository code.** `build` runs the agent-editable builds with no secrets; `deploy` has no
  checkout, downloads the built site as data, and runs only the workflow's shell and a pinned wrangler, with a Worker
  configuration it writes itself.
- **Guards run in `deploy`, not `build`** (a build step can tamper with later steps in its own job): no `_worker.js`,
  `_routes.json`, `functions/` or `.assetsignore`; the static-assets limits (20,000 files per version, 25 MiB per
  file); the branch name matches `[A-Za-z0-9._/-]+`; and **every `paint/site/d/*.png` must match the bytes production
  serves** (changed bytes blank every visitor's canvas). Overriding that takes a human running the workflow by hand
  with `reset_dictionaries`; a file production 404s is new and passes.
- **Only a run on `main` calls `wrangler deploy`**; other branches call `wrangler versions upload`. The environment
  branch rule alone wouldn't stop a preview run deploying to production (same token); the two points above do.
- After each deploy the workflow checks the headers the sites need as Cloudflare serves them: `application/xhtml+xml`
  for js-minus-js; `Use-As-Dictionary` and `Content-Encoding: dcz` for paint.
- Actions are pinned by SHA and wrangler by exact version, each at least two weeks old; Dependabot proposes updates
  monthly after a two-week cooldown.

Stronger later: a separate GitHub identity for agents, so a ruleset can make `main` PR-only and `production` can
require an approval they can't give.

## After a push

`deploy/status.sh` waits for the run on `HEAD`, prints its jobs and each deployment's URL, and exits non-zero on
failure (`gh run view <id> --log-failed` shows why). The `<version>` URL never changes; the `<branch>` URL follows the
branch.

## Workers behaviour the sites depend on (2026-10-18)

- `*.html` 307-redirects to the extensionless path: css-physics's `index-8.html` links rely on it; paint uses
  extensionless URLs throughout.
- A missing path is a 404 with an empty body.
- `_headers` and `_redirects` work as on Pages, `:placeholder`s and 200 rewrites included (paint's cell URLs and
  dictionary headers). Not checked yet: whether two overlapping `_headers` rules are joined with `, ` (paint's don't
  overlap).
- `.xhtml` is served as `application/xhtml+xml`; text is compressed at the edge.
- **paint previews share production's dictionary budget.** A dictionary only matches its own origin, so a preview
  never reads or overwrites production's canvas, but `workers.dev` is a public suffix: every Worker and preview is on
  the site `auberon.workers.dev`, and Chrome keeps 500 dictionaries per site (paint uses up to 480). Open paint
  previews in another Chrome profile or a guest window.

## Not done

- Tests in CI (each suite needs Chromium for minutes; `mcr.microsoft.com/playwright` before the production deploy).
- Preview cleanup: preview aliases outlive their branches.
- Custom domains: add per Worker in the dashboard; deploys don't remove them.
