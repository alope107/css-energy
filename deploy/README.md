# Deploying to Cloudflare Workers

`.github/workflows/deploy.yml` uploads each project's built site to its own Cloudflare Worker as static assets (no
Worker script; Cloudflare doesn't build anything).

| Event | Result |
|---|---|
| push to `main` | production deploy of each project the push changed: `https://<worker>.<subdomain>.workers.dev` |
| push to any other branch | preview of each project the branch changed since leaving `main`, a version that takes no production traffic: `https://<version>-<worker>.<subdomain>.workers.dev` (this commit) and `https://<branch>-<worker>.<subdomain>.workers.dev` (the branch's latest) |
| Actions → deploy → Run workflow | the projects you name, from the branch you pick |

A change under `deploy/` or to the workflow deploys all three. `shared/`, `engine/` and docs outside the projects
deploy nothing.

| Project | Site | Worker (override with a repo variable) |
|---|---|---|
| css-physics | built in CI: `src/build3d.py` → `index.html` + `index-N.html` (~35 s) | `css-physics` (`WORKER_CSS_PHYSICS`) |
| js-minus-js | the committed `dist/js_in_css.xhtml`; `/` redirects to it. CI warns if `make dist` no longer reproduces it | `js-minus-js` (`WORKER_JS_MINUS_JS`) |
| paint | the committed `site/`, unchanged | `paint` (`WORKER_PAINT`) |

The account's workers.dev subdomain is `auberonlopez` (`WORKERS_DEV_SUBDOMAIN`). `deploy/assemble.sh <project> <dir>`
produces exactly what CI uploads. It's the same script.

The Worker's whole configuration is written by the deploy job, not read from the repo: the assets directory,
`html_handling: auto-trailing-slash`, `not_found_handling: none`, `workers_dev` and `preview_urls` on, and a fixed
compatibility date. A deploy replaces settings changed in the dashboard (wrangler warns in the log and goes on).

## One-time setup

1. **Workers.** `css-physics`, `js-minus-js` and `paint` exist on `auberonlopez.workers.dev`. A new one needs nothing
   beforehand: the first production deploy creates it.
2. **API token.** My Profile → API Tokens → Create custom token: *Account · Workers Scripts · Edit*, this account
   only, nothing else. If the first run fails on a permission error, add *Account · Account Settings · Read*. The
   permission can't be narrowed to one Worker, so this token can deploy, and delete, any Worker in the account.
3. **GitHub** (Settings of the repo):
   - Environments → `production`: Deployment branches → Selected branches → `main`. Add secret
     `CLOUDFLARE_API_TOKEN`.
   - Environments → `preview`: no branch rule. Add the same secret.
   - Secrets and variables → Actions → Variables: `CLOUDFLARE_ACCOUNT_ID` (Workers & Pages overview, right
     column), plus any `WORKER_*` or `WORKERS_DEV_SUBDOMAIN` overrides.
4. **The devcontainer's `GH_TOKEN`** (fine-grained, this repo only). Contents and Pull requests: read/write.
   Actions: read, which is enough for `deploy/status.sh`. **Workflows, Secrets, Environments, Deployments,
   Administration: no access.** The trust model below depends on Workflows being no-access. No Cloudflare token
   goes in `~/.config/agent-tokens/css-energy.env`.

Previews need Preview URLs on for the Worker. The first production deploy turns them on; before that, a preview run
fails saying so (or turn them on in the Worker's Settings → Domains & Routes).

## Trust model

Agents write code and can push branches. A push runs the workflow with a token that can deploy. The design keeps the
token out of reach of anything an agent writes:

- **Agents can't change the workflow.** GitHub rejects a push that touches `.github/workflows/` from a token
  without the Workflows permission. So the workflow run on an agent's branch is one you wrote.
- **The deploy job runs no repository code.** `build` checks out the branch and runs `assemble.sh`, the Python
  builds, and `make`, all agent-editable, with no secrets. `deploy` has no checkout. It downloads the built site as
  data and runs only the shell in the workflow file and a pinned wrangler, from a directory outside the site, with a
  Worker configuration it writes itself. The site can't add a Worker script or change the Worker's settings.
- **Checks that matter run in `deploy`, not `build`.** A build step can tamper with later steps in the same job
  (`$GITHUB_PATH`, replaced tools), so the guards live where repo code never ran:
  - no `_worker.js`, `_routes.json`, `functions/` or `.assetsignore` (Pages' ways in, and a way to hide files from
    the upload; a Worker would serve the first three as plain files);
  - the static-assets limits: 20,000 files per version (free plan), 25 MiB per file;
  - **paint's dictionaries**: every `site/d/*.png` must match the bytes production serves. Changed bytes blank every
    visitor's stored canvas (paint/CLAUDE.md), so overriding this takes a human: run the workflow by hand with
    `reset_dictionaries`. Agents can't, because their token has Actions: read. A file production answers with 404
    is new and passes.
  - the branch name must match `[A-Za-z0-9._/-]+` before it reaches wrangler's command line.
- **Production is `main`, and `main` is yours.** Only a run on `main` calls `wrangler deploy`; every other branch
  calls `wrangler versions upload`, which takes no production traffic. The `production` environment's branch rule
  doesn't stop a preview run's token from deploying to production, though. It's the same Cloudflare token, and
  Cloudflare can't scope it more finely. What stops it is the two points above.
- After each deploy the workflow checks the headers each site depends on, as Cloudflare serves them:
  `application/xhtml+xml` for js-minus-js; `Use-As-Dictionary` and `Content-Encoding: dcz` for paint (Cloudflare's
  Shared dictionaries setting can strip these, paint/docs/HISTORY.md).
- Actions are pinned by commit SHA, and wrangler by exact version, all at least two weeks old when pinned.
  Dependabot (`.github/dependabot.yml`) proposes updates monthly, after a two-week cooldown.

Stronger, if you want it later: give agents their own GitHub identity (a machine user or a GitHub App) instead of a
PAT acting as you. Then a ruleset can make `main` PR-only for them, and `production` can require your approval
without that approval being available to them.

## For agents

- **Pushing a branch publishes it** at a public `*.workers.dev` URL. Push only when the user asks.
- After a push: `deploy/status.sh` waits for the run on `HEAD` and prints its jobs and one notice per deployment
  with its URL. Exits non-zero if the run failed. `gh run view <id> --log-failed` shows why.
- The `<version>` URL is this commit's build and never changes; the `<branch>` URL follows the branch. Hand the user
  the `<version>` one alongside the local link CLAUDE.md asks for.
- Hand-test links for a build: css-physics and js-minus-js through the repo-root server on 8765, paint through
  `node paint/serve.js <dir> 8766` (paint/CLAUDE.md).

## Workers behaviour these sites depend on

Seen on the `*.auberonlopez.workers.dev` Workers (2026-10-18):

- `*.html` 307-redirects to the extensionless path (`html_handling: auto-trailing-slash`). css-physics's
  `index-8.html` links rely on that; paint uses extensionless URLs throughout.
- A missing path is a 404 with an empty body (`not_found_handling: none`). Pages answered with `/index.html` and 200
  instead.
- `_headers` and `_redirects` work as on Pages, `:placeholder`s and 200 rewrites included: paint's cell URLs, its
  `Use-As-Dictionary` headers and its `Content-Encoding: dcz` responses come through unchanged.
- `.xhtml` is served as `application/xhtml+xml`.
- Each preview URL is its own origin, so paint previews keep their own dictionaries and never touch production's.

Not checked on Workers yet: whether two overlapping `_headers` rules are joined with `, ` as on Pages (paint's rules
don't overlap), and whether the 12 MB js-minus-js page and css-physics's 12 MB CSS parts are compressed at the edge.

## Not done yet

- **Tests in CI.** The projects' test suites need Chromium (minutes each). Running them in
  `mcr.microsoft.com/playwright` before the production deploy would be the next step.
- **Preview cleanup.** Preview aliases outlive their branches, and nothing removes them.
- **Custom domains.** Add them per Worker in the dashboard. A deploy doesn't remove them: the workflow passes no
  routes.
