# Ai-Lens security model

How Ai-Lens is protected, what to check when it changes, and how to run a deeper audit. The
structure follows Cloudflare's [security-audit skill](https://github.com/cloudflare/security-audit-skill):
name the trust boundary, trace untrusted input to where it is used, and report only a real
boundary failure with its smallest fix. A missing best practice with no reachable attack is a
hardening note, not a vulnerability.

## What there is to protect

Ai-Lens is a static site on GitHub Pages with no accounts, forms or server-side state. What
matters is:

- **Visitors' browsers**: no script injection through news, timeline or deal content.
- **The published data**: timeline and deal entries are only changed through reviewed
  pull requests.
- **Secrets**: the Anthropic API key (repository secret) and the GitHub token used by the
  Cloudflare Worker (Worker secret). Neither appears in the repository.
- **Spend**: Anthropic API usage by the weekly check.

## Trust boundaries and their controls

| # | Untrusted input | Where it goes | Controls |
|---|---|---|---|
| 1 | RSS/Atom feeds and blog pages from 25 outlets, Google News headlines | `python/news.py` → `api/news.json` → browser | Feeds parsed with ElementTree; `<!ENTITY` refused; 5 MB cap per response. In the browser every text value passes `esc()` and every link `safeUrl()` (http/https only); category, language, impact and echo are coerced to known values by `clean()` in `assets/js/common.js`. |
| 2 | Web pages read by Claude in the weekly check (prompt injection) | `python/weekly_milestones.py` → `assets/data/*.json` | Output constrained to a JSON schema; Python re-validates dates, `https` links, enum fields and lengths, and drops duplicates; changes reach the site only through a pull request; rendering is escaped as in row 1. |
| 3 | The previous `api/store.json`, downloaded from the live site at each build | `python/build_static.py` | Parsed as JSON only; rendered through the same escaping. |
| 4 | Pull requests | `tools/merge-weekly-pr.sh` (the only merge Claude may run unattended) | Only open PRs from a `weekly/` branch of this repository, targeting `main`, that *modify* only `assets/data/milestones.json`, `assets/data/investments.json` and `README.md` (no added, removed or renamed files); merges the exact commit it checked. |
| 5 | GitHub Actions | `.github/workflows/*.yml` | Third-party actions pinned to commit SHAs; minimal `permissions`; `persist-credentials: false`; the API key is given only to the step that calls Claude, and the GitHub token only to the steps that call GitHub (opening the pull request, checking earlier runs). |
| 6 | Scheduling | `tools/cron-worker/` (Cloudflare Worker) | No public URL (`workers_dev = false`, no `fetch` handler); its GitHub token is fine-grained: this repository only, Actions read/write only. |
| 7 | Requests to the local development server | `python/server.py` | Paths are decoded and normalised before an allow-list check and must resolve inside `assets/`; binds to 127.0.0.1 by default; manual refresh is rate-limited; CSP and `X-Frame-Options` headers. |

Pages also carry a Content-Security-Policy (`script-src 'self'`, no inline scripts, images
only from the site itself), so even a missed escape could not load outside scripts.

## Spending limits

- The weekly check stops itself at **$2 per run** (`WEEKLY_MAX_USD`), computed from the API's
  own usage figures; set a monthly limit in the Anthropic console as the backstop.
- Headline translation is off unless the repository variable `ENRICH_NEWS` is `true`.

## Checklist for changes

Before merging a change to code or workflows, check the boundaries it touches:

1. **New data shown on a page**: render text with `esc()` and links with `esc(safeUrl(...))`;
   never put a data value into an attribute, `style`, or `innerHTML` unescaped. Fields used
   in class names or attributes must be coerced in `clean()`.
2. **New feed or source**: it is untrusted input; keep the size cap and XML rules in
   `news.py`.
3. **Claude output**: treat it as untrusted; validate it in Python before it is written,
   and keep it behind a pull request.
4. **Workflows**: pin new actions to a full commit SHA, give each job the least
   `permissions` it needs, and pass secrets only to the step that uses them.
5. **Secrets**: never in files, commit messages, PR text or logs. Store them as GitHub or
   Cloudflare secrets.
6. **Personal information**: keep personal names, emails, local paths and account IDs out of
   the public repository (commits are authored as `maghreb.me`).

## Known hardening notes (no reachable vulnerability)

- Python dependencies (`anthropic` in `python/requirements.txt`) are pinned to a major
  version range, not to exact versions with hashes. A compromised release would run in the
  weekly job with the Anthropic API key.
- `npx wrangler` deploys the Worker with the latest wrangler release; pin a version in a
  `package.json` if the Worker changes often.
- GitHub Pages cannot send HTTP headers, so `frame-ancestors` is not enforced; the site has
  no actions a framing page could abuse.

## Running a full audit

For a full review, install Cloudflare's skill in Claude Code and ask for an audit:

```sh
npx skills add https://github.com/cloudflare/security-audit-skill --skill security-audit
```

Then, in this repository: *"security audit this codebase, output to
~/security-audit-skill/ai-lens"*. The full workflow runs many sub-agents (reconnaissance,
hunters, independent verifiers) and writes `REPORT.md`, `findings.json` and a coverage
ledger outside the repository. Relevant companion files for Ai-Lens: `CLIENT-SIDE.md`,
`AI-AND-LLM.md`, `SUPPLY-CHAIN-AND-RELEASE.md`, `CLOUD-AND-DEPLOYMENT.md` and
`RESOURCE-EXHAUSTION-AND-AVAILABILITY.md`. Repeat runs add coverage.

## Reporting a vulnerability

See [SECURITY.md](../SECURITY.md).
