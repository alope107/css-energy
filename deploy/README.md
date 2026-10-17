# Deploying to Cloudflare Pages

`.github/workflows/deploy.yml` uploads each project's built site to its own Cloudflare Pages project (Pages "direct
upload"; Cloudflare doesn't build anything).

| Event | Result |
|---|---|
| push to `main` | production deploy of each project the push changed |
| push to any other branch | preview of each project the branch changed since leaving `main`: `https://<hash>.<project>.pages.dev` (this commit) and `https://<branch>.<project>.pages.dev` (the branch's latest) |
| Actions → deploy → Run workflow | the projects you name, from the branch you pick |

A change under `deploy/` or to the workflow deploys all three. `shared/`, `engine/` and docs outside the projects
deploy nothing.

| Project | Site | Pages project (override with a repo variable) |
|---|---|---|
| css-physics | built in CI: `src/build3d.py` → `index.html` + `index-N.html` (~35 s) | `css-physics` (`PAGES_PROJECT_CSS_PHYSICS`) |
| js-minus-js | the committed `dist/js_in_css.xhtml`; `/` redirects to it. CI warns if `make dist` no longer reproduces it | `js-minus-js` (`PAGES_PROJECT_JS_MINUS_JS`) |
| paint | the committed `site/`, unchanged | `dictionary-paint` (`PAGES_PROJECT_PAINT`) |

`deploy/assemble.sh <project> <dir>` produces exactly what CI uploads. It's the same script.

## One-time setup

1. **Cloudflare projects.** Pages project names are global subdomains: pick free ones. Create them as direct-upload
   projects with `main` as the production branch, e.g. `npx wrangler pages project create css-physics
   --production-branch main`, or in the dashboard (Workers & Pages → Create → Pages → Upload assets). For paint's
   existing project, check its name and production branch (`npx wrangler pages project list`, or the dashboard). If
   the production branch isn't `main`, every deploy is a preview, and the workflow fails saying so.
2. **API token.** My Profile → API Tokens → Create custom token: *Account · Cloudflare Pages · Edit*, this account
   only, nothing else. Pages permissions can't be narrowed to one project, so this token can deploy, and delete,
   any Pages project in the account.
3. **GitHub** (Settings of the repo):
   - Environments → `production`: Deployment branches → Selected branches → `main`. Add secret
     `CLOUDFLARE_API_TOKEN`.
   - Environments → `preview`: no branch rule. Add the same secret.
   - Secrets and variables → Actions → Variables: `CLOUDFLARE_ACCOUNT_ID` (Workers & Pages overview, right
     column), plus any `PAGES_PROJECT_*` overrides.
4. **The devcontainer's `GH_TOKEN`** (fine-grained, this repo only). Contents and Pull requests: read/write.
   Actions: read, which is enough for `deploy/status.sh`. **Workflows, Secrets, Environments, Deployments,
   Administration: no access.** The trust model below depends on Workflows being no-access. No Cloudflare token
   goes in `~/.config/agent-tokens/css-energy.env`.

## Trust model

Agents write code and can push branches. A push runs the workflow with a token that can deploy. The design keeps the
token out of reach of anything an agent writes:

- **Agents can't change the workflow.** GitHub rejects a push that touches `.github/workflows/` from a token
  without the Workflows permission. So the workflow run on an agent's branch is one you wrote.
- **The deploy job runs no repository code.** `build` checks out the branch and runs `assemble.sh`, the Python
  builds, and `make`, all agent-editable, with no secrets. `deploy` has no checkout. It downloads the built site as
  data and runs only the shell in the workflow file and a pinned wrangler.
- **Checks that matter run in `deploy`, not `build`.** A build step can tamper with later steps in the same job
  (`$GITHUB_PATH`, replaced tools), so the guards live where repo code never ran:
  - no `_worker.js`, `_routes.json` or `functions/` (any of them would turn a static site into a Worker);
  - Pages' limits: 20,000 files, 25 MiB per file;
  - **paint's dictionaries**: every `site/d/*.png` must match the bytes production serves. Changed bytes blank every
    visitor's stored canvas (paint/CLAUDE.md), so overriding this takes a human: run the workflow by hand with
    `reset_dictionaries`. Agents can't, because their token has Actions: read.
  - the branch name must match `[A-Za-z0-9._/-]+` before it reaches wrangler's command line.
- **Production is `main`, and `main` is yours.** Only the `production` environment holds a deployment for `main`.
  Its branch rule doesn't stop a preview token from deploying to production, though. It's the same Cloudflare
  token, and Cloudflare can't scope it more finely. What stops it is the two points above.
- After each deploy the workflow checks the headers each site depends on, as Cloudflare serves them:
  `application/xhtml+xml` for js-minus-js; `Use-As-Dictionary` and `Content-Encoding: dcz` for paint (Cloudflare's
  Shared dictionaries setting can strip these, paint/README.md).
- Actions are pinned by commit SHA, and wrangler by exact version, all at least two weeks old when pinned.
  Dependabot (`.github/dependabot.yml`) proposes updates monthly, after a two-week cooldown.

Stronger, if you want it later: give agents their own GitHub identity (a machine user or a GitHub App) instead of a
PAT acting as you. Then a ruleset can make `main` PR-only for them, and `production` can require your approval
without that approval being available to them.

## For agents

- **Pushing a branch publishes it** at a public `*.pages.dev` URL. Push only when the user asks.
- After a push: `deploy/status.sh` waits for the run on `HEAD` and prints its jobs and one notice per deployment
  with its URL. Exits non-zero if the run failed. `gh run view <id> --log-failed` shows why.
- The `<hash>` URL is this commit's build and never changes; the `<branch>` URL follows the branch. Hand the user
  the `<hash>` one alongside the local link CLAUDE.md asks for.
- Hand-test links for a build: css-physics and js-minus-js through the repo-root server on 8765, paint through
  `node paint/serve.js <dir> 8766` (paint/CLAUDE.md).
- To check Pages behaviour itself before pushing: `npx wrangler pages dev <dir> --port 8770 --ip 127.0.0.1`. It
  emulates `_headers`, `_redirects` and the `.html` → extensionless redirect, without credentials. Each instance opens
  ~7 loopback ports, and VS Code's auto-forwarding gives up past ~20, so stop it when done. It isn't a hand-test
  server.

## Pages behaviour these sites depend on

- `*.html` 308-redirects to the extensionless path. css-physics's `index-8.html` links rely on that; paint uses
  extensionless URLs throughout.
- Without a `404.html`, a missing path is answered with `/index.html` and status 200 (single-page-app fallback). The
  paint check reads a `text/html` answer for `/d/N.png` as "not in production yet".
- Headers set by two overlapping `_headers` rules are joined with `, ` (paint/CLAUDE.md).
- Text responses are compressed at the edge; the 12 MB js-minus-js page and css-physics's 12 MB CSS parts go out
  gzip/brotli.
- Each preview is its own origin, so paint previews keep their own dictionaries and never touch production's.

## Not done yet

- **Tests in CI.** The projects' test suites need Chromium (minutes each). Running them in
  `mcr.microsoft.com/playwright` before the production deploy would be the next step.
- **Preview cleanup.** Branch aliases outlive their branches. Old deployments can be deleted in the dashboard;
  nothing removes them automatically.
- **Custom domains.** Add them per project in the dashboard; nothing here changes.
